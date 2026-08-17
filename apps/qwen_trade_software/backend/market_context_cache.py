"""Persistent, provenance-first market context for the local Qwen shadow path.

The module deliberately does not import or call the paper executor.  It builds
and validates a cache-backed challenger while the existing demo strategy stays
the execution champion.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import inspect
import json
import logging
import logging.handlers
import msvcrt
import os
import re
import sqlite3
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import MetaTrader5 as mt5

import live_mapped_levels


SCHEMA_VERSION = 1
QUALIFICATION_VERSION = 2
# Kept in lockstep with review_shared.MODEL -- both processes must talk to the
# same model or the qualification certificate (keyed on model_digest) is
# invalidated on every cycle. See CURRICULUM_AND_DATA_PREP.md 3.0.
MODEL = os.environ.get("QWEN_MODEL", "qwen-trading-v004:latest")
OLLAMA_GENERATE = "http://127.0.0.1:11434/api/generate"
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
OLLAMA_PS = "http://127.0.0.1:11434/api/ps"
APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = APP_DIR / "cache"
# Previously hardcoded to %LOCALAPPDATA%\QwenTradeReviewer\cache regardless of
# where this script actually lives -- meaning a copy of the app running from
# anywhere else would still silently read/write the old location's database.
# Deriving both paths from APP_DIR instead makes the whole app relocatable:
# wherever these .py files run from, the cache travels with them.
DEFAULT_DB = CACHE_DIR / "market_context.sqlite3"
MODEL_LOCK_FILE = CACHE_DIR / "qwen-model.lock"
CONTEXT_CYCLE_LOCK_FILE = CACHE_DIR / "context-cycle.lock"
# The knowledge store (core_skill.md, sop.md, etc.) now lives at the app's
# own root -- APP_DIR.parents[2] resolves to that root the same way the git
# HEAD lookup elsewhere in this file already does, so this needs no
# hardcoded absolute path and keeps working if the app is relocated again.
# Override with QUANT_STORE_ROOT if the store ever lives somewhere else.
DEFAULT_STORE_ROOT = Path(
    os.environ.get("QUANT_STORE_ROOT", str(APP_DIR.parents[2] / "store"))
)
TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
    "D1": 86400,
}
# Minute packet must outlive the cache worker interval with slack. Runtime uses
# --interval 30; a 2-minute TTL was expiring whenever a cycle stalled past the
# next refresh and blocked entry with entry_cache:minute:expired while the
# structural manifest still looked ready.
MINUTE_PACKET_TTL = timedelta(minutes=4)
MT5_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}
LOOKBACKS = {
    "D1": timedelta(weeks=8),
    # Pull near-max broker depth so mapped H4/M15 shelves have real evidence.
    "H4": timedelta(weeks=16),
    "H1": timedelta(weeks=4),
    "M30": timedelta(days=45),
    "M15": timedelta(days=45),
}
MINIMUM_COUNTS = {
    "D1": 35,
    "H4": 200,
    "H1": 200,
    "M30": 1,
    "M15": 1,
    "M5": 1,
    "M1": 1,
}
MAPPED_TRADE_LEVELS_PATH = APP_DIR / "mapped_trade_levels.json"
COMPLETED_BROKER_METADATA_FIELDS = ("tick_volume", "spread", "real_volume")
COMPLETED_IMMUTABLE_FIELDS = (
    "symbol",
    "timeframe",
    "open_time_utc",
    "close_time_utc",
    "open",
    "high",
    "low",
    "close",
    "source",
    "evidence_id",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | str | int | float) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, timezone.utc)
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("naive datetime is not valid cache evidence")
    return parsed.astimezone(timezone.utc)


def iso_utc(value: datetime | str | int | float) -> str:
    return as_utc(value).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def content_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def candle_id(symbol: str, timeframe: str, opened: str | datetime) -> str:
    return f"candle:{symbol}:{timeframe}:{iso_utc(opened)}"


def git_version() -> str:
    head = APP_DIR.parents[2] / ".git" / "HEAD"
    try:
        value = head.read_text(encoding="utf-8").strip()
        if value.startswith("ref: "):
            ref = APP_DIR.parents[2] / ".git" / value[5:]
            value = ref.read_text(encoding="utf-8").strip()
        return f"git:{value[:12]}"
    except OSError:
        return "git:deployed"


@contextlib.contextmanager
def _exclusive_file_lock(path: Path, *, timeout: float | None, label: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if handle.seek(0, os.SEEK_END) == 0:
        handle.write(b"0")
        handle.flush()
    started = time.monotonic()
    while True:
        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            break
        except OSError:
            if timeout is not None and time.monotonic() - started >= timeout:
                handle.close()
                raise TimeoutError(f"{label} timed out")
            time.sleep(0.1)
    try:
        yield
    finally:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()


@contextlib.contextmanager
def model_generation_lock(timeout: float | None = None):
    """Serialize Ollama generations across reviewer and cache processes."""
    with _exclusive_file_lock(
        MODEL_LOCK_FILE, timeout=timeout, label="Qwen model generation lock"
    ):
        yield


@contextlib.contextmanager
def context_cycle_lock(timeout: float | None = None):
    """Serialize full context-cache cycles so workers cannot race the SQLite cache."""
    with _exclusive_file_lock(
        CONTEXT_CYCLE_LOCK_FILE, timeout=timeout, label="Context cache cycle lock"
    ):
        yield


def load_prompt_section(
    name: str,
    store_root: Path = DEFAULT_STORE_ROOT,
    *,
    keep_comments: bool = False,
) -> str:
    """Return one prompt section from sop.md.

    HTML comments are stripped by default, because everything this function
    returns is sent verbatim to the model as instructions. Version markers and
    maintainer notes are for humans reading sop.md -- shipping them to the model
    is at best token noise and at worst active priming: a note explaining that a
    past contract "returned confidence 0" is itself an instruction to return
    confidence 0.

    Pass ``keep_comments=True`` when you need the markers for tooling, e.g.
    reviewer.entry_contract_version().
    """
    sop = (store_root / "sop.md").read_text(encoding="utf-8")
    marker = f"<!-- prompt:{name} -->"
    start = sop.find(marker)
    if start < 0:
        raise RuntimeError(f"Missing canonical SOP prompt section: {name}")
    body_start = sop.find("\n", start) + 1
    next_marker = sop.find("<!-- prompt:", body_start)
    body = sop[body_start : next_marker if next_marker >= 0 else len(sop)]
    if not keep_comments:
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


class OllamaClient:
    def __init__(self, model: str = MODEL) -> None:
        self.model = model

    @staticmethod
    def _get(url: str, timeout: float = 5.0) -> dict:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def model_info(self) -> dict:
        tags = self._get(OLLAMA_TAGS).get("models", [])
        running = self._get(OLLAMA_PS).get("models", [])
        installed = next((row for row in tags if row.get("name") == self.model), None)
        resident = next((row for row in running if row.get("name") == self.model), None)
        return {
            "installed": installed is not None,
            "resident": resident is not None,
            "digest": (installed or {}).get("digest"),
            "resident_digest": (resident or {}).get("digest"),
            "size": (installed or {}).get("size"),
            "size_vram": (resident or {}).get("size_vram"),
            "expires_at": (resident or {}).get("expires_at"),
        }

    def generate(
        self,
        prompt: str,
        *,
        num_ctx: int = 4096,
        num_predict: int = -1,
        timeout: float | None = None,
        format_schema: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "temperature": 0,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
            },
        }
        if prompt:
            payload["format"] = format_schema or "json"
        request = urllib.request.Request(
            OLLAMA_GENERATE,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with model_generation_lock():
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            result["client_wall_duration_ns"] = int(
                (time.perf_counter() - started) * 1_000_000_000
            )
            return result

    def warm(self) -> dict:
        return self.generate("", num_ctx=4096, num_predict=1, timeout=None)


@dataclass(frozen=True)
class Quote:
    symbol: str
    time_utc: str
    bid: float
    ask: float
    spread: float
    flags: int


class MT5MarketSource:
    def __init__(self, symbol: str = "XAUUSDr") -> None:
        self.requested_symbol = symbol
        self.symbol = symbol

    def connect(self) -> None:
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"MT5 account unavailable: {mt5.last_error()}")
        if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Context shadow is restricted to an MT5 demo account")
        info = mt5.symbol_info(self.requested_symbol)
        if info is None:
            symbols = mt5.symbols_get(group="*XAUUSD*") or []
            if not symbols:
                raise RuntimeError("No XAUUSD symbol is available in MT5")
            self.symbol = symbols[0].name
        else:
            self.symbol = self.requested_symbol
        if not mt5.symbol_select(self.symbol, True):
            raise RuntimeError(f"Unable to select {self.symbol}: {mt5.last_error()}")

    @staticmethod
    def close() -> None:
        mt5.shutdown()

    def quote(self) -> Quote:
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            raise RuntimeError(f"No MT5 tick for {self.symbol}: {mt5.last_error()}")
        timestamp = getattr(tick, "time_msc", 0) / 1000 or tick.time
        return Quote(
            symbol=self.symbol,
            time_utc=iso_utc(timestamp),
            bid=float(tick.bid),
            ask=float(tick.ask),
            spread=round(float(tick.ask) - float(tick.bid), 6),
            flags=int(tick.flags),
        )

    @staticmethod
    def _normalize_rate(
        symbol: str,
        timeframe: str,
        rate: Any,
        as_of: datetime,
    ) -> dict:
        opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
        closed = opened + timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
        complete = closed <= as_of
        return {
            "evidence_id": candle_id(symbol, timeframe, opened),
            "symbol": symbol,
            "timeframe": timeframe,
            "open_time_utc": iso_utc(opened),
            "close_time_utc": iso_utc(closed),
            "open": float(rate["open"]),
            "high": float(rate["high"]),
            "low": float(rate["low"]),
            "close": float(rate["close"]),
            "tick_volume": int(rate["tick_volume"]),
            "spread": int(rate["spread"]),
            "real_volume": int(rate["real_volume"]),
            "is_complete": complete,
            "source": "MT5",
            "ingested_at_utc": iso_utc(utc_now()),
        }

    @staticmethod
    def _start_for(timeframe: str, as_of: datetime) -> datetime:
        if timeframe in LOOKBACKS:
            return as_of - LOOKBACKS[timeframe] - timedelta(
                seconds=TIMEFRAME_SECONDS[timeframe] * 2
            )
        day_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        if timeframe == "M1":
            return as_of.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
        if timeframe == "M5":
            return as_of - timedelta(days=3)
        return day_start

    def history(
        self,
        as_of: datetime,
        starts: dict[str, datetime] | None = None,
    ) -> tuple[dict[str, list[dict]], dict[str, dict]]:
        completed: dict[str, list[dict]] = {}
        forming: dict[str, dict] = {}
        for timeframe, mt5_timeframe in MT5_TIMEFRAMES.items():
            start = (starts or {}).get(timeframe, self._start_for(timeframe, as_of))
            rates = mt5.copy_rates_range(self.symbol, mt5_timeframe, start, as_of)
            if rates is None:
                raise RuntimeError(
                    f"MT5 {timeframe} history failed: {mt5.last_error()}"
                )
            rows = [
                self._normalize_rate(self.symbol, timeframe, rate, as_of)
                for rate in sorted(rates, key=lambda item: int(item["time"]))
            ]
            completed[timeframe] = [row for row in rows if row["is_complete"]]
            unfinished = [row for row in rows if not row["is_complete"]]
            if unfinished:
                forming[timeframe] = unfinished[-1]
            else:
                current = mt5.copy_rates_from_pos(self.symbol, mt5_timeframe, 0, 1)
                if current is not None and len(current):
                    row = self._normalize_rate(self.symbol, timeframe, current[0], as_of)
                    if not row["is_complete"]:
                        forming[timeframe] = row
        return completed, forming


class MarketContextCache:
    def __init__(
        self,
        path: Path | str = DEFAULT_DB,
        *,
        report_metadata_corrections: bool = True,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(
            self.path, timeout=10.0, isolation_level=None, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA busy_timeout=10000")
        self.report_metadata_corrections = report_metadata_corrections
        self._reported_metadata_corrections: set[tuple] = set()
        self._create_schema()

    def close(self) -> None:
        self.connection.close()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS completed_candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time_utc TEXT NOT NULL,
                close_time_utc TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                tick_volume INTEGER NOT NULL,
                spread INTEGER NOT NULL,
                real_volume INTEGER NOT NULL,
                source TEXT NOT NULL,
                ingested_at_utc TEXT NOT NULL,
                evidence_id TEXT NOT NULL UNIQUE,
                row_hash TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe, open_time_utc)
            );
            CREATE INDEX IF NOT EXISTS idx_completed_tf_time
                ON completed_candles(symbol, timeframe, open_time_utc);
            CREATE TABLE IF NOT EXISTS forming_candles (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time_utc TEXT NOT NULL,
                close_time_utc TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                tick_volume INTEGER NOT NULL,
                spread INTEGER NOT NULL,
                real_volume INTEGER NOT NULL,
                source TEXT NOT NULL,
                ingested_at_utc TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                row_hash TEXT NOT NULL,
                PRIMARY KEY (symbol, timeframe)
            );
            CREATE TABLE IF NOT EXISTS ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                time_utc TEXT NOT NULL,
                bid REAL NOT NULL,
                ask REAL NOT NULL,
                spread REAL NOT NULL,
                flags INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ticks_symbol_time
                ON ticks(symbol, time_utc DESC);
            CREATE TABLE IF NOT EXISTS cache_objects (
                cache_type TEXT NOT NULL,
                cache_epoch TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL,
                valid_as_of_utc TEXT NOT NULL,
                source_start_utc TEXT,
                source_end_utc TEXT,
                source_hash TEXT NOT NULL,
                producer_version TEXT NOT NULL,
                model_digest TEXT,
                expires_at_utc TEXT,
                invalidated_at_utc TEXT,
                invalidation_reason TEXT,
                evidence_ids_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_cache_current
                ON cache_objects(symbol, cache_type, is_current, valid_as_of_utc DESC);
            CREATE TABLE IF NOT EXISTS readiness_manifests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                validated_at_utc TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_readiness_latest
                ON readiness_manifests(symbol, id DESC);
            CREATE TABLE IF NOT EXISTS qwen_validations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                validation_type TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                response_json TEXT,
                raw_response TEXT,
                passed INTEGER NOT NULL,
                failures_json TEXT NOT NULL,
                metrics_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS latency_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                cycle_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                stage TEXT NOT NULL,
                duration_ms REAL NOT NULL,
                details_json TEXT NOT NULL
            );
            """
        )

    @staticmethod
    def _candle_storage(row: dict) -> dict:
        stable = {
            key: row[key]
            for key in (
                "symbol",
                "timeframe",
                "open_time_utc",
                "close_time_utc",
                "open",
                "high",
                "low",
                "close",
                "tick_volume",
                "spread",
                "real_volume",
                "source",
                "evidence_id",
            )
        }
        stable["row_hash"] = content_hash(stable)
        stable["ingested_at_utc"] = row.get("ingested_at_utc", iso_utc(utc_now()))
        return stable

    def ingest_completed(self, rows: Iterable[dict]) -> dict[str, int]:
        inserted = 0
        unchanged = 0
        metadata_corrections = 0
        with self.connection:
            for raw in rows:
                if not raw.get("is_complete", True):
                    raise ValueError("forming candle cannot enter completed_candles")
                row = self._candle_storage(raw)
                existing = self.connection.execute(
                    "SELECT * FROM completed_candles "
                    "WHERE symbol=? AND timeframe=? AND open_time_utc=?",
                    (row["symbol"], row["timeframe"], row["open_time_utc"]),
                ).fetchone()
                if existing:
                    if existing["row_hash"] != row["row_hash"]:
                        immutable_changes = [
                            field
                            for field in COMPLETED_IMMUTABLE_FIELDS
                            if existing[field] != row[field]
                        ]
                        if immutable_changes:
                            raise ValueError(
                                "immutable completed candle changed: "
                                f"{row['evidence_id']} fields={','.join(immutable_changes)}"
                            )
                        metadata_changes = {
                            field: {"cached": existing[field], "broker": row[field]}
                            for field in COMPLETED_BROKER_METADATA_FIELDS
                            if existing[field] != row[field]
                        }
                        correction_key = (
                            row["evidence_id"],
                            tuple(
                                (field, values["cached"], values["broker"])
                                for field, values in metadata_changes.items()
                            ),
                        )
                        if (
                            self.report_metadata_corrections
                            and correction_key not in self._reported_metadata_corrections
                        ):
                            logging.warning(
                                "Ignoring broker metadata correction for immutable "
                                "completed candle %s: %s",
                                row["evidence_id"],
                                canonical_json(metadata_changes),
                            )
                            self._reported_metadata_corrections.add(correction_key)
                        metadata_corrections += 1
                    unchanged += 1
                    continue
                self.connection.execute(
                    """INSERT INTO completed_candles (
                        symbol,timeframe,open_time_utc,close_time_utc,open,high,low,
                        close,tick_volume,spread,real_volume,source,ingested_at_utc,
                        evidence_id,row_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(
                        row[key]
                        for key in (
                            "symbol",
                            "timeframe",
                            "open_time_utc",
                            "close_time_utc",
                            "open",
                            "high",
                            "low",
                            "close",
                            "tick_volume",
                            "spread",
                            "real_volume",
                            "source",
                            "ingested_at_utc",
                            "evidence_id",
                            "row_hash",
                        )
                    ),
                )
                self.connection.execute(
                    "DELETE FROM forming_candles WHERE symbol=? AND timeframe=? "
                    "AND open_time_utc=?",
                    (row["symbol"], row["timeframe"], row["open_time_utc"]),
                )
                inserted += 1
        return {
            "inserted": inserted,
            "unchanged": unchanged,
            "metadata_corrections": metadata_corrections,
        }

    def upsert_forming(self, rows: Iterable[dict]) -> int:
        count = 0
        with self.connection:
            for raw in rows:
                if raw.get("is_complete"):
                    raise ValueError("completed candle cannot enter forming_candles")
                row = self._candle_storage(raw)
                self.connection.execute(
                    """INSERT INTO forming_candles (
                        symbol,timeframe,open_time_utc,close_time_utc,open,high,low,
                        close,tick_volume,spread,real_volume,source,ingested_at_utc,
                        evidence_id,row_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(symbol,timeframe) DO UPDATE SET
                        open_time_utc=excluded.open_time_utc,
                        close_time_utc=excluded.close_time_utc,
                        open=excluded.open,high=excluded.high,low=excluded.low,
                        close=excluded.close,tick_volume=excluded.tick_volume,
                        spread=excluded.spread,real_volume=excluded.real_volume,
                        source=excluded.source,ingested_at_utc=excluded.ingested_at_utc,
                        evidence_id=excluded.evidence_id,row_hash=excluded.row_hash""",
                    tuple(
                        row[key]
                        for key in (
                            "symbol",
                            "timeframe",
                            "open_time_utc",
                            "close_time_utc",
                            "open",
                            "high",
                            "low",
                            "close",
                            "tick_volume",
                            "spread",
                            "real_volume",
                            "source",
                            "ingested_at_utc",
                            "evidence_id",
                            "row_hash",
                        )
                    ),
                )
                count += 1
        return count

    def add_quote(self, quote: Quote) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO ticks(symbol,time_utc,bid,ask,spread,flags) VALUES(?,?,?,?,?,?)",
                (
                    quote.symbol,
                    quote.time_utc,
                    quote.bid,
                    quote.ask,
                    quote.spread,
                    quote.flags,
                ),
            )
            self.connection.execute(
                "DELETE FROM ticks WHERE id IN (SELECT id FROM ticks WHERE symbol=? "
                "ORDER BY id DESC LIMIT -1 OFFSET 10000)",
                (quote.symbol,),
            )

    def completed(self, symbol: str, timeframe: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM completed_candles WHERE symbol=? AND timeframe=? "
            "ORDER BY open_time_utc",
            (symbol, timeframe),
        ).fetchall()
        return [dict(row) for row in rows]

    def latest_completed(self, symbol: str, timeframe: str, count: int = 1) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM completed_candles WHERE symbol=? AND timeframe=? "
            "ORDER BY open_time_utc DESC LIMIT ?",
            (symbol, timeframe, count),
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def completed_counts(self, symbol: str) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT timeframe,COUNT(*) AS count FROM completed_candles "
            "WHERE symbol=? GROUP BY timeframe",
            (symbol,),
        ).fetchall()
        found = {row["timeframe"]: int(row["count"]) for row in rows}
        return {timeframe: found.get(timeframe, 0) for timeframe in TIMEFRAME_SECONDS}

    def evidence_exists(self, evidence_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM completed_candles WHERE evidence_id=? LIMIT 1",
            (evidence_id,),
        ).fetchone() is not None

    def forming(self, symbol: str) -> dict[str, dict]:
        rows = self.connection.execute(
            "SELECT * FROM forming_candles WHERE symbol=? ORDER BY timeframe", (symbol,)
        ).fetchall()
        return {row["timeframe"]: dict(row) for row in rows}

    def raw_hash(self, symbol: str) -> str:
        rows = self.connection.execute(
            "SELECT timeframe,open_time_utc,row_hash FROM completed_candles "
            "WHERE symbol=? ORDER BY timeframe,open_time_utc",
            (symbol,),
        ).fetchall()
        forming = self.connection.execute(
            "SELECT timeframe,open_time_utc,row_hash FROM forming_candles "
            "WHERE symbol=? ORDER BY timeframe",
            (symbol,),
        ).fetchall()
        return content_hash(
            {"completed": [dict(row) for row in rows], "forming": [dict(row) for row in forming]}
        )

    def subset_hash(
        self,
        symbol: str,
        timeframes: Iterable[str],
        *,
        include_forming: bool = False,
    ) -> str:
        names = tuple(timeframes)
        placeholders = ",".join("?" for _ in names)
        rows = self.connection.execute(
            f"SELECT timeframe,open_time_utc,row_hash FROM completed_candles "
            f"WHERE symbol=? AND timeframe IN ({placeholders}) "
            "ORDER BY timeframe,open_time_utc",
            (symbol, *names),
        ).fetchall()
        forming = []
        if include_forming:
            forming = self.connection.execute(
                f"SELECT timeframe,open_time_utc,row_hash FROM forming_candles "
                f"WHERE symbol=? AND timeframe IN ({placeholders}) ORDER BY timeframe",
                (symbol, *names),
            ).fetchall()
        return content_hash(
            {"completed": [dict(row) for row in rows], "forming": [dict(row) for row in forming]}
        )

    def incremental_starts(self, symbol: str, as_of: datetime) -> dict[str, datetime]:
        starts = {}
        for timeframe, seconds in TIMEFRAME_SECONDS.items():
            row = self.connection.execute(
                "SELECT open_time_utc FROM completed_candles WHERE symbol=? AND timeframe=? "
                "ORDER BY open_time_utc DESC LIMIT 1",
                (symbol, timeframe),
            ).fetchone()
            if row:
                starts[timeframe] = as_utc(row["open_time_utc"]) - timedelta(seconds=seconds)
            else:
                starts[timeframe] = MT5MarketSource._start_for(timeframe, as_of)
        return starts

    def source_bounds(self, symbol: str) -> tuple[str | None, str | None]:
        row = self.connection.execute(
            "SELECT MIN(open_time_utc) AS first, MAX(open_time_utc) AS last "
            "FROM completed_candles WHERE symbol=?",
            (symbol,),
        ).fetchone()
        return row["first"], row["last"]

    def put_object(
        self,
        cache_type: str,
        symbol: str,
        valid_as_of: datetime | str,
        payload: dict,
        *,
        source_hash: str,
        evidence_ids: Iterable[str],
        model_digest: str | None = None,
        expires_at: datetime | str | None = None,
    ) -> dict:
        valid = iso_utc(valid_as_of)
        evidence = sorted(set(evidence_ids))
        identity = content_hash(
            {
                "cache_type": cache_type,
                "symbol": symbol,
                "source_hash": source_hash,
                "payload": payload,
                "evidence_ids": evidence,
                "model_digest": model_digest,
            }
        )
        epoch = f"{cache_type}-{symbol}-{identity.split(':', 1)[1][:16]}"
        source_start, source_end = self.source_bounds(symbol)
        now = iso_utc(utc_now())
        expires = iso_utc(expires_at) if expires_at else None
        with self.connection:
            current = self.connection.execute(
                "SELECT cache_epoch FROM cache_objects WHERE symbol=? AND cache_type=? "
                "AND is_current=1",
                (symbol, cache_type),
            ).fetchone()
            if current and current["cache_epoch"] != epoch:
                self.connection.execute(
                    "UPDATE cache_objects SET is_current=0,invalidated_at_utc=?,"
                    "invalidation_reason='superseded' WHERE cache_epoch=?",
                    (now, current["cache_epoch"]),
                )
            self.connection.execute(
                """INSERT OR IGNORE INTO cache_objects (
                    cache_type,cache_epoch,symbol,schema_version,created_at_utc,
                    valid_as_of_utc,source_start_utc,source_end_utc,source_hash,
                    producer_version,model_digest,expires_at_utc,evidence_ids_json,
                    payload_json,is_current
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    cache_type,
                    epoch,
                    symbol,
                    SCHEMA_VERSION,
                    now,
                    valid,
                    source_start,
                    source_end,
                    source_hash,
                    git_version(),
                    model_digest,
                    expires,
                    canonical_json(evidence),
                    canonical_json(payload),
                ),
            )
            self.connection.execute(
                "UPDATE cache_objects SET is_current=1,invalidated_at_utc=NULL,"
                "invalidation_reason=NULL WHERE cache_epoch=?",
                (epoch,),
            )
        return self.object(cache_type, symbol) or {}

    def object(self, cache_type: str, symbol: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM cache_objects WHERE cache_type=? AND symbol=? AND is_current=1 "
            "ORDER BY valid_as_of_utc DESC LIMIT 1",
            (cache_type, symbol),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["evidence_ids"] = json.loads(result.pop("evidence_ids_json"))
        return result

    def write_manifest(self, symbol: str, manifest: dict) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO readiness_manifests(symbol,validated_at_utc,status,payload_json) "
                "VALUES(?,?,?,?)",
                (
                    symbol,
                    manifest["validated_at_utc"],
                    manifest["status"],
                    canonical_json(manifest),
                ),
            )

    def latest_manifest(self, symbol: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload_json FROM readiness_manifests WHERE symbol=? ORDER BY id DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def record_qwen_validation(
        self,
        symbol: str,
        validation_type: str,
        input_value: dict,
        response: dict | None,
        raw_response: str,
        passed: bool,
        failures: list[str],
        metrics: dict,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO qwen_validations(
                    symbol,validation_type,created_at_utc,input_hash,response_json,
                    raw_response,passed,failures_json,metrics_json
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    symbol,
                    validation_type,
                    iso_utc(utc_now()),
                    content_hash(input_value),
                    canonical_json(response) if response is not None else None,
                    raw_response,
                    int(passed),
                    canonical_json(failures),
                    canonical_json(metrics),
                ),
            )

    def latest_qwen_response(
        self, symbol: str, validation_type: str, input_value: dict
    ) -> tuple[dict, str] | None:
        row = self.connection.execute(
            "SELECT response_json,raw_response FROM qwen_validations "
            "WHERE symbol=? AND validation_type=? AND input_hash=? "
            "AND response_json IS NOT NULL ORDER BY id DESC LIMIT 1",
            (symbol, validation_type, content_hash(input_value)),
        ).fetchone()
        if not row:
            return None
        response = json.loads(row["response_json"])
        return response, row["raw_response"] or canonical_json(response)

    def record_latency(
        self, symbol: str, cycle_id: str, stage: str, duration_ms: float, details: dict
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO latency_events(symbol,cycle_id,created_at_utc,stage,duration_ms,details_json) "
                "VALUES(?,?,?,?,?,?)",
                (
                    symbol,
                    cycle_id,
                    iso_utc(utc_now()),
                    stage,
                    round(duration_ms, 3),
                    canonical_json(details),
                ),
            )


# Playbook-condition vocabulary.
#
# 2026-08-10 INCIDENT: qualification failed and took the whole trading chain
# down with it. v004 wrote `sell: "invalidated below H1_PREVIOUS_HIGH"` -- a
# correct structural condition -- but "invalidat" was absent from the accepted
# tokens, so it scored not_closed_response. A retry 22s later happened to phrase
# the same idea as "rejection below" and passed.
#
# That is the real defect: the gate was a coin flip on synonym choice. A
# non-deterministic gate that halts trading on a wording preference is worse
# than no gate, because it fails in a way nobody can attribute.
#
# These lists are the intent, spelled out: a condition must reference a
# *response at the level*, and a counter-side condition must describe a
# reversal rather than a continuation. Extend them when a model uses a
# legitimate synonym -- do not tighten them to force one phrasing.
RESPONSE_TOKENS = (
    "close", "closed",
    "accept", "acceptance",
    "retest",
    "reject", "rejection",
    "reclaim",
    "fail", "failure",
    "invalidat",          # invalidated / invalidation -- v004's usual phrasing
    "sweep", "swept",
    "break", "broke",
    "hold", "held",
    "respect",
)
BUY_REVERSAL_TOKENS = ("back above", "reject", "reclaim", "invalidat", "fail", "sweep")
SELL_REVERSAL_TOKENS = ("back below", "reject", "fail", "invalidat", "sweep")


def session_at(moment: datetime) -> dict:
    hour = moment.hour
    if 0 <= hour < 7:
        name, end, permitted = "asia", 7, True
    elif 7 <= hour < 8:
        name, end, permitted = "pre_london", 8, False
    elif 8 <= hour < 13:
        name, end, permitted = "london", 13, True
    elif 13 <= hour < 16:
        name, end, permitted = "overlap", 16, True
    elif 16 <= hour < 17:
        # 2026-08-13: NY entries cut at 17:00 UTC. Was 16:00-21:00; late NY
        # (after 17:00) stays off-session for new entries while broker data can
        # still flow. Overlap ends at 16:00; this leaves a one-hour NY window.
        name, end, permitted = "new_york", 17, True
    else:
        name, end, permitted = "off_session", 24, False
    end_time = moment.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=end)
    return {
        "trading_date_utc": moment.date().isoformat(),
        "session": name,
        "session_end_utc": iso_utc(end_time),
        "seconds_remaining": max(0, int((end_time - moment).total_seconds())),
        "trade_permitted": permitted,
    }


def _auction_state(latest: dict, previous: dict) -> str:
    if latest["close"] > previous["high"] or latest["close"] < previous["low"]:
        return "acceptance"
    if latest["high"] > previous["high"] or latest["low"] < previous["low"]:
        return "rejection"
    overlap = min(latest["high"], previous["high"]) - max(latest["low"], previous["low"])
    return "balance" if overlap >= 0 else "transition"


def _location(price: float, candle: dict) -> str:
    if price > candle["high"]:
        return "above_previous_range"
    if price < candle["low"]:
        return "below_previous_range"
    return "inside_previous_range"


class ContextProjectionBuilder:
    def __init__(self, cache: MarketContextCache, symbol: str) -> None:
        self.cache = cache
        self.symbol = symbol

    def _nearest_touch_candle(
        self, timeframe: str, zone_low: float, zone_high: float
    ) -> dict | None:
        """Pick a completed candle that touched the mapped zone for gate_b evidence."""
        rows = self.cache.completed(self.symbol, timeframe)
        if not rows:
            # Fall back across higher frames so mapped shelves still cite evidence
            # when the preferred TF has not warmed yet.
            for fallback in ("H4", "H1", "M30", "M15", "D1"):
                if fallback == timeframe:
                    continue
                rows = self.cache.completed(self.symbol, fallback)
                if rows:
                    break
        if not rows:
            return None
        mid = (float(zone_low) + float(zone_high)) / 2.0
        touching = [
            row
            for row in rows
            if float(row["low"]) <= zone_high and float(row["high"]) >= zone_low
        ]
        pool = touching or rows
        return min(
            pool,
            key=lambda row: min(
                abs(float(row["high"]) - mid),
                abs(float(row["low"]) - mid),
                abs(((float(row["high"]) + float(row["low"])) / 2.0) - mid),
            ),
        )

    def _mapped_trade_levels(self, as_of: datetime) -> list[dict]:
        if not MAPPED_TRADE_LEVELS_PATH.exists():
            return []
        try:
            payload = json.loads(MAPPED_TRADE_LEVELS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if str(payload.get("symbol") or self.symbol) not in {self.symbol, "XAUUSDr", "XAUUSD"}:
            return []
        mapped: list[dict] = []
        for row in payload.get("levels") or []:
            level_id = str(row.get("level_id") or "").strip()
            timeframe = str(row.get("timeframe") or "").strip().upper()
            if not level_id or timeframe not in TIMEFRAME_SECONDS:
                continue
            try:
                zone_low = float(row["zone_low"])
                zone_high = float(row.get("zone_high", zone_low))
            except (KeyError, TypeError, ValueError):
                continue
            if zone_low > zone_high:
                zone_low, zone_high = zone_high, zone_low
            source = self._nearest_touch_candle(timeframe, zone_low, zone_high)
            if not source:
                continue
            mapped.append(
                {
                    "level_id": level_id,
                    "timeframe": timeframe,
                    "zone_low": zone_low,
                    "zone_high": zone_high,
                    "role": str(row.get("role") or "mapped_important"),
                    "label": row.get("label"),
                    "source_candle_ids": [source["evidence_id"]],
                    "calculation_method": str(
                        row.get("calculation_method") or "operator_mapped"
                    ),
                    "valid_from_utc": source.get("close_time_utc") or iso_utc(as_of),
                }
            )
        return mapped

    def build_levels(self, as_of: datetime, price: float, raw_hash: str) -> dict:
        levels: list[dict] = []
        evidence: list[str] = []
        for timeframe in ("D1", "H4", "H1", "M30", "M15", "M5", "M1"):
            rows = self.cache.latest_completed(self.symbol, timeframe)
            if not rows:
                continue
            latest = rows[-1]
            evidence.append(latest["evidence_id"])
            for role, field in (("previous_high", "high"), ("previous_low", "low")):
                level_id = f"{timeframe}_{role.upper()}"
                levels.append(
                    {
                        "level_id": level_id,
                        "timeframe": timeframe,
                        "zone_low": latest[field],
                        "zone_high": latest[field],
                        "role": role,
                        "source_candle_ids": [latest["evidence_id"]],
                        "calculation_method": "latest_completed_candle",
                        "valid_from_utc": latest["close_time_utc"],
                    }
                )
        daily = self.cache.latest_completed(self.symbol, "D1")
        if daily:
            prior = daily[-1]
            pivot = round((prior["high"] + prior["low"] + prior["close"]) / 3, 6)
            levels.append(
                {
                    "level_id": "D1_FLOOR_PIVOT",
                    "timeframe": "D1",
                    "zone_low": pivot,
                    "zone_high": pivot,
                    "role": "floor_pivot",
                    "source_candle_ids": [prior["evidence_id"]],
                    "calculation_method": "floor_pp_hlc3",
                    "valid_from_utc": prior["close_time_utc"],
                }
            )
        seen_ids = {row["level_id"] for row in levels}
        for row in self._mapped_trade_levels(as_of):
            if row["level_id"] in seen_ids:
                continue
            levels.append(row)
            seen_ids.add(row["level_id"])
            evidence.extend(row["source_candle_ids"])
        completed_by_tf = {
            timeframe: self.cache.latest_completed(
                self.symbol, timeframe, live_mapped_levels.LOOKBACK[timeframe]
            )
            for timeframe in live_mapped_levels.LOOKBACK
        }
        closed_m1 = (completed_by_tf.get("M1") or [None])[-1]
        for row in live_mapped_levels.build_from_completed(
            completed_by_tf, closed_m1, price, as_of=as_of
        ):
            width = live_mapped_levels.ZONE_WIDTH.get(row["timeframe"], 3.0)
            merged = False
            for existing in levels:
                if existing["timeframe"] != row["timeframe"]:
                    continue
                if not live_mapped_levels.overlaps_existing(row, [existing], width):
                    continue
                if int(row.get("test_count") or 0) > int(existing.get("test_count") or 0):
                    existing["test_count"] = row["test_count"]
                if row.get("pattern") in {"double_top", "double_bottom"}:
                    existing["pattern"] = row["pattern"]
                    existing["label"] = row.get("label")
                    existing["left_after_first"] = row.get("left_after_first")
                merged = True
                break
            if merged or row["level_id"] in seen_ids:
                continue
            levels.append(row)
            seen_ids.add(row["level_id"])
            evidence.extend(row.get("source_candle_ids") or [])
        levels.sort(key=lambda item: (item["zone_low"], item["level_id"]))
        lower = [row for row in levels if row["zone_high"] <= price]
        upper = [row for row in levels if row["zone_low"] > price]
        payload = {
            "price": price,
            "levels": levels,
            "nearest_lower": lower[-1] if lower else None,
            "nearest_upper": upper[0] if upper else None,
        }
        return self.cache.put_object(
            "levels",
            self.symbol,
            as_of,
            payload,
            source_hash=raw_hash,
            evidence_ids=evidence,
        )

    def build_structure(
        self, as_of: datetime, price: float, raw_hash: str, levels: dict
    ) -> dict:
        forming = self.cache.forming(self.symbol)
        roles = {}
        evidence: list[str] = []
        for timeframe in ("D1", "H4", "H1"):
            rows = self.cache.latest_completed(self.symbol, timeframe, 2)
            if len(rows) < 2:
                continue
            previous, latest = rows[-2], rows[-1]
            ids = [previous["evidence_id"], latest["evidence_id"]]
            evidence.extend(ids)
            roles[timeframe] = {
                "location": _location(latest["close"], previous),
                "auction_state": _auction_state(latest, previous),
                "latest_completed": {
                    "evidence_id": latest["evidence_id"],
                    "open": latest["open"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "close": latest["close"],
                    "close_time_utc": latest["close_time_utc"],
                },
                "forming_evidence_id": (
                    forming[timeframe]["evidence_id"] if timeframe in forming else None
                ),
                "evidence_ids": ids,
            }
        h4 = roles.get("H4", {})
        h4_forming = forming.get("H4") or {}
        reference_price = (
            roles.get("H1", {}).get("latest_completed", {}).get("close", price)
        )
        structural_levels = [
            row
            for row in levels["payload"]["levels"]
            if row["timeframe"] in ("D1", "H4", "H1")
        ]
        lower = [row for row in structural_levels if row["zone_high"] <= reference_price]
        upper = [row for row in structural_levels if row["zone_low"] > reference_price]
        payload = {
            "timeframe_location": roles,
            "current_h4_open": h4_forming.get("open"),
            "current_h4_state": "forming_active" if h4_forming else "unavailable",
            "nearest_lower_zone": lower[-1] if lower else None,
            "nearest_upper_zone": upper[0] if upper else None,
            "unresolved_fact": "next closed response at the nearest active zone",
        }
        return self.cache.put_object(
            "structural",
            self.symbol,
            as_of,
            payload,
            source_hash=raw_hash,
            evidence_ids=evidence,
        )

    def build_session(self, as_of: datetime, price: float, raw_hash: str) -> dict:
        base = session_at(as_of)
        m5 = self.cache.completed(self.symbol, "M5")
        # L3 is closed-evidence state.  The live quote and countdown belong in
        # the L5 minute packet; including either here would rotate the heavy
        # session cache on every poll even though no candle had closed.
        base.pop("seconds_remaining", None)
        reference_price = m5[-1]["close"] if m5 else price
        day = as_of.date()
        asia = [
            row
            for row in m5
            if as_utc(row["open_time_utc"]).date() == day
            and 0 <= as_utc(row["open_time_utc"]).hour < 7
        ]
        evidence = [row["evidence_id"] for row in asia]
        if asia:
            asia_high = max(row["high"] for row in asia)
            asia_low = min(row["low"] for row in asia)
            if reference_price > asia_high:
                relation = "above_asia_high"
            elif reference_price < asia_low:
                relation = "below_asia_low"
            else:
                relation = "inside_asia_range"
            bias = (
                "up"
                if asia[-1]["close"] > asia[0]["open"]
                else "down"
                if asia[-1]["close"] < asia[0]["open"]
                else "flat"
            )
        else:
            asia_high = asia_low = None
            relation = "asia_range_incomplete"
            bias = "incomplete"
        payload = {
            **base,
            "asia_high": asia_high,
            "asia_low": asia_low,
            "asia_bias": bias,
            "asia_relation": relation,
            "evidence_ids": evidence,
        }
        return self.cache.put_object(
            "session",
            self.symbol,
            as_of,
            payload,
            source_hash=raw_hash,
            evidence_ids=evidence,
            expires_at=base["session_end_utc"],
        )

    def build_playbooks(
        self,
        as_of: datetime,
        raw_hash: str,
        levels: dict,
        model_digest: str | None,
        qwen_playbooks: list[dict] | None = None,
    ) -> dict:
        # 2026-08-06: M30 included so the watched-zone candidates (what Qwen
        # actually sees for entry timing) refresh every half hour instead of
        # only on a D1/H4/H1 close. build_structure's separate D1/H4/H1
        # narrative filter is intentionally left untouched.
        all_levels = [
            row
            for row in levels["payload"]["levels"]
            if row["timeframe"] in ("D1", "H4", "H1", "M30")
        ]
        h1_rows = self.cache.latest_completed(self.symbol, "H1")
        price = h1_rows[-1]["close"] if h1_rows else levels["payload"]["price"]
        ordered = sorted(all_levels, key=lambda row: row["zone_low"])
        nearest = sorted(
            ordered,
            key=lambda row: (abs(row["zone_low"] - price), row["level_id"]),
        )[:3]
        qwen_by_id = {
            str(row.get("level_id")): row for row in (qwen_playbooks or [])
        }
        playbooks = []
        evidence: list[str] = []
        for level in nearest:
            index = ordered.index(level)
            lower = ordered[index - 1] if index > 0 else None
            upper = ordered[index + 1] if index + 1 < len(ordered) else None
            if not lower or not upper:
                continue
            qwen = qwen_by_id.get(level["level_id"], {})
            ids = [level["level_id"], *level["source_candle_ids"]]
            evidence.extend(level["source_candle_ids"])
            # 2026-08-06: anchor on the M30 boundary (was H4) so a playbook_id
            # actually changes -- and the watch list visibly refreshes -- every
            # half hour rather than every four hours.
            m30_anchor = datetime.fromtimestamp(
                int(as_of.timestamp()) // TIMEFRAME_SECONDS["M30"] * TIMEFRAME_SECONDS["M30"],
                timezone.utc,
            )
            playbooks.append(
                {
                    "playbook_id": f"M30-{m30_anchor:%Y%m%dT%H%MZ}-{level['level_id']}",
                    "level_id": level["level_id"],
                    "level_price": level["zone_low"],
                    "approach_state": (
                        "below_approaching" if price < level["zone_low"] else "above_approaching"
                    ),
                    "buy_condition": qwen.get("buy_condition")
                    or f"closed bullish response at {level['level_id']}",
                    "sell_condition": qwen.get("sell_condition")
                    or f"closed bearish response at {level['level_id']}",
                    # Identity, geometry, targets, and invalidations are
                    # deterministic cache wiring.  Qwen may describe the two
                    # response conditions but can never rewrite this mapping.
                    "buy_invalidation_level_id": lower["level_id"],
                    "sell_invalidation_level_id": upper["level_id"],
                    "lower_target_id": lower["level_id"],
                    "upper_target_id": upper["level_id"],
                    "missing_evidence": qwen.get(
                        "missing_evidence", ["closed response at level"]
                    ),
                    "evidence_ids": ids,
                    "semantic_source": (
                        "qwen_validated" if qwen else "deterministic_contract"
                    ),
                    "status": "watch",
                }
            )
        m30_seconds = TIMEFRAME_SECONDS["M30"]
        next_m30 = datetime.fromtimestamp(
            (int(as_of.timestamp()) // m30_seconds + 1) * m30_seconds, timezone.utc
        )
        return self.cache.put_object(
            "playbooks",
            self.symbol,
            as_of,
            {"playbooks": playbooks},
            source_hash=raw_hash,
            evidence_ids=evidence,
            model_digest=model_digest,
            expires_at=next_m30,
        )

    def build_minute(
        self,
        as_of: datetime,
        quote: Quote,
        raw_hash: str,
        structure: dict,
        levels: dict,
        session: dict,
        playbooks: dict,
    ) -> dict:
        latest_m1 = self.cache.latest_completed(self.symbol, "M1")[-1]
        forming = self.cache.forming(self.symbol)
        level_rows = levels["payload"]["levels"]
        nearby = live_mapped_levels.select_nearby(level_rows, quote.bid, latest_m1)
        live_map = live_mapped_levels.live_map_packet(level_rows, quote.bid, latest_m1)
        active = (playbooks["payload"].get("playbooks") or [None])[0]
        m1_rows = self.cache.latest_completed(self.symbol, "M1", 21)
        m5_rows = self.cache.latest_completed(self.symbol, "M5", 21)

        def volume_ratio(rows: list[dict]) -> float | None:
            if len(rows) < 2:
                return None
            baseline = sorted(row["tick_volume"] for row in rows[:-1])
            median = baseline[len(baseline) // 2]
            return round(rows[-1]["tick_volume"] / median, 3) if median else None

        payload = {
            "decision_time_utc": iso_utc(as_of),
            "epochs": {
                "structure": structure["cache_epoch"],
                "levels": levels["cache_epoch"],
                "session": session["cache_epoch"],
                "playbook": playbooks["cache_epoch"],
            },
            "quote": {
                "bid": quote.bid,
                "ask": quote.ask,
                "spread": quote.spread,
                "time_utc": quote.time_utc,
                "age_ms": max(
                    0, int((as_of - as_utc(quote.time_utc)).total_seconds() * 1000)
                ),
            },
            "closed_m1": {
                "id": latest_m1["evidence_id"],
                "open_time_utc": latest_m1["open_time_utc"],
                "open": latest_m1["open"],
                "high": latest_m1["high"],
                "low": latest_m1["low"],
                "close": latest_m1["close"],
                "tick_volume": latest_m1["tick_volume"],
            },
            "forming": {
                timeframe: {
                    "id": row["evidence_id"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "current": row["close"],
                }
                for timeframe, row in forming.items()
                if timeframe in ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
            },
            "volume": {"M1_ratio": volume_ratio(m1_rows), "M5_ratio": volume_ratio(m5_rows)},
            "market_location": {
                timeframe: value.get("location")
                for timeframe, value in structure["payload"]["timeframe_location"].items()
            },
            "session": {
                key: session["payload"].get(key)
                for key in ("session", "trade_permitted", "asia_relation", "asia_high", "asia_low")
            },
            "nearby_levels": live_mapped_levels.nearby_payload(nearby, quote.bid),
            "live_map": live_map,
            "playbook": active,
            "position": None,
        }
        evidence = [latest_m1["evidence_id"]]
        evidence.extend(row["level_id"] for row in nearby)
        return self.cache.put_object(
            "minute",
            self.symbol,
            as_of,
            payload,
            source_hash=raw_hash,
            evidence_ids=evidence,
            expires_at=as_of + MINUTE_PACKET_TTL,
        )


class ContextValidator:
    def __init__(self, cache: MarketContextCache, symbol: str) -> None:
        self.cache = cache
        self.symbol = symbol

    @staticmethod
    def _geometry(row: dict) -> bool:
        return (
            row["low"] <= min(row["open"], row["close"])
            and row["high"] >= max(row["open"], row["close"])
            and row["low"] <= row["high"]
            and row["tick_volume"] >= 0
        )

    @staticmethod
    def _active_data_session_start(moment: datetime) -> datetime | None:
        """Return the UTC day boundary while intraday broker data is expected."""
        moment = as_utc(moment)
        if moment.weekday() >= 5 or not 0 <= moment.hour < 21:
            return None
        return moment.replace(hour=0, minute=0, second=0, microsecond=0)

    @classmethod
    def _active_freshness_failure(
        cls,
        as_of: datetime,
        timeframe: str,
        rows: list[dict],
    ) -> str | None:
        """Flag only a stale latest close during the active data session.

        Historical discontinuities, rollover pauses, and off-session gaps are
        intentionally not treated as missing data.  A timeframe is checked
        only after enough of the current active UTC session has elapsed for
        one completed candle to exist.
        """
        active_start = cls._active_data_session_start(as_of)
        seconds = TIMEFRAME_SECONDS[timeframe]
        if (
            active_start is None
            or (as_utc(as_of) - active_start).total_seconds() < seconds
            or not rows
        ):
            return None
        latest_close = max(as_utc(row["close_time_utc"]) for row in rows)
        age_seconds = (as_utc(as_of) - latest_close).total_seconds()
        if age_seconds <= seconds * 2.1:
            return None
        return (
            f"raw:{timeframe}:active_session_stale:"
            f"{iso_utc(latest_close)}:{iso_utc(as_of)}"
        )

    def gate_a(self, as_of: datetime) -> tuple[bool, list[str], dict]:
        failures: list[str] = []
        counts = {}
        for timeframe, seconds in TIMEFRAME_SECONDS.items():
            rows = self.cache.completed(self.symbol, timeframe)
            counts[timeframe] = len(rows)
            if len(rows) < MINIMUM_COUNTS[timeframe]:
                failures.append(
                    f"raw:{timeframe}:count {len(rows)} < {MINIMUM_COUNTS[timeframe]}"
                )
                continue
            opened = [as_utc(row["open_time_utc"]) for row in rows]
            if opened != sorted(set(opened)):
                failures.append(f"raw:{timeframe}:duplicate_or_non_monotonic")
            for row, timestamp in zip(rows, opened):
                if int(timestamp.timestamp()) % seconds:
                    failures.append(f"raw:{timeframe}:misaligned:{row['evidence_id']}")
                    break
                if not self._geometry(row):
                    failures.append(f"raw:{timeframe}:bad_ohlc:{row['evidence_id']}")
                    break
                if as_utc(row["close_time_utc"]) > as_of:
                    failures.append(f"raw:{timeframe}:forming_in_completed")
                    break
            freshness_failure = self._active_freshness_failure(
                as_of, timeframe, rows
            )
            if freshness_failure:
                failures.append(freshness_failure)
        forming = self.cache.forming(self.symbol)
        if self._active_data_session_start(as_of) is not None:
            for timeframe in TIMEFRAME_SECONDS:
                if timeframe not in forming:
                    failures.append(f"raw:{timeframe}:active_session_forming_missing")
        return not failures, failures, {"counts": counts, "raw_hash": self.cache.raw_hash(self.symbol)}

    def gate_a_incremental(
        self,
        as_of: datetime,
        incoming: dict[str, list[dict]],
    ) -> tuple[bool, list[str], dict]:
        failures: list[str] = []
        counts = self.cache.completed_counts(self.symbol)
        for timeframe, seconds in TIMEFRAME_SECONDS.items():
            if counts[timeframe] < MINIMUM_COUNTS[timeframe]:
                failures.append(
                    f"raw:{timeframe}:count {counts[timeframe]} < {MINIMUM_COUNTS[timeframe]}"
                )
            for row in incoming.get(timeframe, []):
                opened = as_utc(row["open_time_utc"])
                if int(opened.timestamp()) % seconds:
                    failures.append(f"raw:{timeframe}:misaligned:{row['evidence_id']}")
                if not self._geometry(row):
                    failures.append(f"raw:{timeframe}:bad_ohlc:{row['evidence_id']}")
                if as_utc(row["close_time_utc"]) > as_of:
                    failures.append(f"raw:{timeframe}:forming_in_completed")
            latest = self.cache.latest_completed(self.symbol, timeframe, 1)
            freshness_failure = self._active_freshness_failure(
                as_of, timeframe, latest
            )
            if freshness_failure:
                failures.append(freshness_failure)
        forming = self.cache.forming(self.symbol)
        if self._active_data_session_start(as_of) is not None:
            for timeframe in TIMEFRAME_SECONDS:
                if timeframe not in forming:
                    failures.append(f"raw:{timeframe}:active_session_forming_missing")
        return not failures, failures, {
            "counts": counts,
            "raw_hash": self.cache.raw_hash(self.symbol),
            "validation_mode": "incremental",
        }

    def gate_b(self) -> tuple[bool, list[str], dict]:
        failures: list[str] = []
        objects = {
            name: self.cache.object(name, self.symbol)
            for name in ("levels", "structural", "session", "playbooks", "minute")
        }
        for name, value in objects.items():
            if not value:
                failures.append(f"derived:{name}:missing")
        if failures:
            return False, failures, {"objects": objects}
        levels = objects["levels"]["payload"]["levels"]
        level_ids = {row["level_id"] for row in levels}
        for row in levels:
            if row["zone_low"] > row["zone_high"]:
                failures.append(f"level:{row['level_id']}:reversed")
            if not all(self.cache.evidence_exists(value) for value in row["source_candle_ids"]):
                failures.append(f"level:{row['level_id']}:unknown_source")
        for row in objects["playbooks"]["payload"]["playbooks"]:
            if row["level_id"] not in level_ids:
                failures.append(f"playbook:{row['playbook_id']}:unknown_level")
            for key in (
                "buy_invalidation_level_id",
                "sell_invalidation_level_id",
                "lower_target_id",
                "upper_target_id",
            ):
                if row.get(key) not in level_ids:
                    failures.append(f"playbook:{row['playbook_id']}:{key}:unknown")
        expected_hashes = {
            "levels": self.cache.subset_hash(self.symbol, TIMEFRAME_SECONDS),
            "structural": self.cache.subset_hash(self.symbol, ("D1", "H4", "H1")),
            "session": self.cache.subset_hash(self.symbol, ("M5", "M15", "M30")),
            # Mirrors run_once()'s playbook_hash: playbooks now refresh on M30
            # closes too, so this integrity hash must match that composition.
            "playbooks": self.cache.subset_hash(
                self.symbol, ("D1", "H4", "H1", "M30")
            ),
            "minute": self.cache.raw_hash(self.symbol),
        }
        for name, expected in expected_hashes.items():
            if objects[name]["source_hash"] != expected:
                failures.append(f"derived:{name}:source_hash_mismatch")
        return not failures, failures, {
            "epochs": {name: value["cache_epoch"] for name, value in objects.items()},
            "level_count": len(levels),
        }

    @staticmethod
    def validate_warmup(
        response: dict,
        expected_epochs: dict,
        known_evidence: set[str],
        known_levels: set[str],
        expected_structure: dict,
    ) -> tuple[bool, list[str]]:
        failures = []
        acknowledged = response.get("acknowledged_epochs")
        if acknowledged != expected_epochs:
            failures.append("warmup:epoch_mismatch")
        locations = response.get("timeframe_location")
        if not isinstance(locations, dict) or set(locations) != {"D1", "H4", "H1"}:
            failures.append("warmup:timeframe_localization_incomplete")
        else:
            expected_locations = expected_structure.get("timeframe_location", {})
            for timeframe in ("D1", "H4", "H1"):
                actual = locations.get(timeframe) or {}
                expected = expected_locations.get(timeframe) or {}
                for key in ("location", "auction_state"):
                    if actual.get(key) != expected.get(key):
                        failures.append(f"warmup:{timeframe}:{key}_mismatch")
                cited_ids = set(actual.get("evidence_ids") or [])
                if not cited_ids or not cited_ids.issubset(
                    set(expected.get("evidence_ids") or [])
                ):
                    failures.append(f"warmup:{timeframe}:localized_evidence_mismatch")
        h4_path = response.get("h4_path") or {}
        if h4_path.get("current_open") != expected_structure.get("current_h4_open"):
            failures.append("warmup:h4_open_mismatch")
        if h4_path.get("current_state") != expected_structure.get("current_h4_state"):
            failures.append("warmup:h4_state_mismatch")
        for response_key, structure_key in (
            ("nearest_lower_zone", "nearest_lower_zone"),
            ("nearest_upper_zone", "nearest_upper_zone"),
        ):
            actual = response.get(response_key) or {}
            expected = expected_structure.get(structure_key) or {}
            if actual.get("level_id") != expected.get("level_id") or actual.get(
                "price"
            ) != expected.get("zone_low"):
                failures.append(f"warmup:{response_key}_mismatch")
        cited = set(response.get("evidence_ids") or [])
        for value in (locations or {}).values():
            if isinstance(value, dict):
                cited.update(value.get("evidence_ids") or [])
        if not cited:
            failures.append("warmup:evidence_missing")
        if not cited.issubset(known_evidence | known_levels):
            failures.append("warmup:invented_evidence")
        return not failures, sorted(set(failures))

    @staticmethod
    def validate_playbook_interpretation(
        response: dict,
        expected_epochs: dict,
        pending_playbooks: list[dict],
    ) -> tuple[bool, list[str]]:
        failures: list[str] = []
        if response.get("acknowledged_epochs") != expected_epochs:
            failures.append("playbook:epoch_mismatch")
        expected = {row["playbook_id"]: row for row in pending_playbooks}
        interpretations = response.get("interpretations")
        if not isinstance(interpretations, dict):
            return False, ["playbook:interpretations_missing"]
        if set(interpretations) != set(expected):
            failures.append("playbook:id_set_mismatch")
        all_known: set[str] = set()
        for playbook_id, source in expected.items():
            all_known.update(source.get("evidence_ids") or [])
            item = interpretations.get(playbook_id)
            if not isinstance(item, dict):
                failures.append(f"playbook:{playbook_id}:missing")
                continue
            level_id = source["level_id"]
            if item.get("level_id") != level_id:
                failures.append(f"playbook:{playbook_id}:level_mismatch")
            cited = set(item.get("evidence_ids") or [])
            if not cited or not cited.issubset(set(source.get("evidence_ids") or [])):
                failures.append(f"playbook:{playbook_id}:evidence_invalid")
            for side in ("buy", "sell"):
                condition = str(item.get(f"{side}_condition", ""))
                lowered = condition.lower()
                if level_id.lower() not in lowered:
                    failures.append(f"playbook:{playbook_id}:{side}:level_not_named")
                if not any(token in lowered for token in RESPONSE_TOKENS):
                    failures.append(f"playbook:{playbook_id}:{side}:not_closed_response")
                if side == "buy" and "below" in lowered and not any(
                    token in lowered for token in BUY_REVERSAL_TOKENS
                ):
                    failures.append(f"playbook:{playbook_id}:buy:wrong_side")
                if side == "sell" and "above" in lowered and not any(
                    token in lowered for token in SELL_REVERSAL_TOKENS
                ):
                    failures.append(f"playbook:{playbook_id}:sell:wrong_side")
        top_cited = set(response.get("evidence_ids") or [])
        if not top_cited or not top_cited.issubset(all_known):
            failures.append("playbook:top_evidence_invalid")
        return not failures, sorted(set(failures))

    @staticmethod
    def validate_challenge(response: dict, challenge: dict) -> tuple[bool, list[str]]:
        failures: list[str] = []
        exact = challenge["expected_exact"]
        for key, expected in exact.items():
            if response.get(key) != expected:
                failures.append(f"challenge:{key}:mismatch")
        expected_tests = {row["test_id"]: row["answer"] for row in challenge["localization_tests"]}
        answers = response.get("localization_answers")
        if isinstance(answers, list):
            received = {row.get("test_id"): row.get("answer") for row in answers if isinstance(row, dict)}
        elif isinstance(answers, dict):
            received = answers
        else:
            received = {}
        for test_id, answer in expected_tests.items():
            if received.get(test_id) != answer:
                failures.append(f"challenge:localization:{test_id}")
        if response.get("data_requests") != challenge["expected_data_requests"]:
            failures.append("challenge:bounded_data_request_mismatch")
        cited = set(response.get("evidence_ids") or [])
        if not cited or not cited.issubset(set(challenge["known_evidence_ids"])):
            failures.append("challenge:evidence_ids_invalid")
        return not failures, failures

    @staticmethod
    def validate_minute_response(response: dict, packet: dict) -> tuple[bool, list[str]]:
        failures = []
        if response.get("action") not in {"open", "wait", "skip", "request_data"}:
            failures.append("minute:invalid_action")
        if response.get("direction") not in {"buy", "sell", "none"}:
            failures.append("minute:invalid_direction")
        known = {packet["closed_m1"]["id"]}
        known.update(row["id"] for row in packet["nearby_levels"])
        if packet.get("playbook"):
            known.add(packet["playbook"]["playbook_id"])
            known.update(packet["playbook"].get("evidence_ids") or [])
        cited = set(response.get("evidence_ids") or [])
        if not cited.issubset(known):
            failures.append("minute:invented_evidence")
        requests = response.get("data_requests") or []
        if len(requests) > 1:
            failures.append("minute:too_many_data_requests")
        for request in requests:
            if request.get("timeframe") not in TIMEFRAME_SECONDS:
                failures.append("minute:request_timeframe_invalid")
            if not 1 <= int(request.get("completed_bars", 0)) <= 50:
                failures.append("minute:request_bar_count_invalid")
            if not set(request.get("fields") or []).issubset(
                {"ohlc", "tick_volume", "spread", "time"}
            ):
                failures.append("minute:request_fields_invalid")
        return not failures, failures


def compact_history(cache: MarketContextCache, symbol: str) -> dict:
    result = {}
    for timeframe in ("D1", "H4", "H1", "M30", "M15", "M5", "M1"):
        rows = cache.completed(symbol, timeframe)
        if not rows:
            result[timeframe] = {"rows": []}
            continue
        start = as_utc(rows[0]["open_time_utc"])
        result[timeframe] = {
            "start_utc": iso_utc(start),
            "columns": [
                "seconds_from_start",
                "open_milli",
                "high_milli",
                "low_milli",
                "close_milli",
                "tick_volume",
            ],
            "price_scale": 1000,
            "rows": [
                [
                    int((as_utc(row["open_time_utc"]) - start).total_seconds()),
                    round(row["open"] * 1000),
                    round(row["high"] * 1000),
                    round(row["low"] * 1000),
                    round(row["close"] * 1000),
                    row["tick_volume"],
                ]
                for row in rows
            ],
        }
    return result


def deterministic_history_digest(
    cache: MarketContextCache, symbol: str, timeframe: str
) -> dict:
    """Summarize every cached bar into provenance-tagged chronological blocks."""
    rows = cache.completed(symbol, timeframe)
    size = max(1, (len(rows) + 3) // 4)
    blocks = []
    for offset in range(0, len(rows), size):
        group = rows[offset : offset + size]
        high_bar = max(group, key=lambda row: row["high"])
        low_bar = min(group, key=lambda row: row["low"])
        ranges = [row["high"] - row["low"] for row in group]
        blocks.append(
            [
                group[0]["open_time_utc"],
                group[-1]["close_time_utc"],
                len(group),
                group[0]["open"],
                high_bar["high"],
                high_bar["evidence_id"],
                low_bar["low"],
                low_bar["evidence_id"],
                group[-1]["close"],
                round(group[-1]["close"] - group[0]["open"], 6),
                round(sum(ranges) / len(ranges), 6),
                sum(row["tick_volume"] for row in group),
                sum(row["close"] > row["open"] for row in group),
                sum(row["close"] < row["open"] for row in group),
            ]
        )
    recent = [
        [
            row["evidence_id"],
            row["open_time_utc"],
            row["open"],
            row["high"],
            row["low"],
            row["close"],
            row["tick_volume"],
        ]
        for row in rows[-4:]
    ]
    return {
        "timeframe": timeframe,
        "source_bar_count": len(rows),
        "source_start_utc": rows[0]["open_time_utc"] if rows else None,
        "source_end_utc": rows[-1]["close_time_utc"] if rows else None,
        "source_hash": content_hash(
            [[row["evidence_id"], row["row_hash"]] for row in rows]
        ),
        "block_columns": [
            "start_utc",
            "end_utc",
            "count",
            "open",
            "high",
            "high_evidence_id",
            "low",
            "low_evidence_id",
            "close",
            "net_change",
            "average_range",
            "tick_volume_sum",
            "up_bars",
            "down_bars",
        ],
        "chronological_blocks": blocks,
        "recent_columns": [
            "evidence_id",
            "open_time_utc",
            "open",
            "high",
            "low",
            "close",
            "tick_volume",
        ],
        "recent_exact_bars": recent,
    }


def parse_model_json(result: dict) -> tuple[dict | None, str, list[str]]:
    raw = result.get("response", "")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as error:
        return None, raw, [f"invalid_json:{error}"]
    if not isinstance(value, dict):
        return None, raw, ["response_is_not_object"]
    return value, raw, []


class QwenContextShadow:
    def __init__(
        self,
        cache: MarketContextCache,
        source: MT5MarketSource,
        ollama: OllamaClient,
        store_root: Path = DEFAULT_STORE_ROOT,
    ) -> None:
        self.cache = cache
        self.source = source
        self.ollama = ollama
        self.store_root = store_root
        self.symbol = source.symbol
        self.builder = ContextProjectionBuilder(cache, self.symbol)
        self.validator = ContextValidator(cache, self.symbol)
        # keep_comments=True is REQUIRED here, not cosmetic.
        #
        # 2026-08-10 incident: load_prompt_section() was changed to strip HTML
        # comments before text reaches the model (correct -- maintainer notes
        # were being shipped as instructions). But this hash is the identity of
        # the qualification certificate stored in cache_objects. Stripping
        # comments changed the hash from aa0f5f0c... to 3d1bb9d3..., so
        # _qualification_is_valid() stopped matching a certificate that was
        # still current, passing and bound to the right model digest.
        #
        # The always-on cache child runs with --no-qwen (see
        # software_runtime.py), so it can never re-run the challenge to mint a
        # replacement. The result was a permanent 'qwen_validation_not_run'
        # block: cache never reached ready, and entry decisions waited forever
        # on cache_readiness_not_ready.
        #
        # Hashing the RAW section text keeps this identity stable across
        # loader changes and preserves continuity with every certificate
        # already on disk. Changing what is hashed here silently invalidates
        # every stored qualification -- do not do it without also arranging a
        # re-qualification run.
        self.qualification_contract_hash = content_hash(
            {
                "qualification_version": QUALIFICATION_VERSION,
                "prompts": {
                    name: load_prompt_section(
                        name, self.store_root, keep_comments=True
                    )
                    for name in (
                        "qwen_history_chunk",
                        "qwen_cache_warmup",
                        "qwen_playbook_interpretation",
                        "qwen_session_warmup",
                        "qwen_context_challenge",
                        "qwen_minute_shadow",
                    )
                },
            }
        )

    def _model_metrics(self, result: dict) -> dict:
        return {
            key: result.get(key)
            for key in (
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
                "client_wall_duration_ns",
            )
        }

    def _qualification_is_valid(self, model_digest: str | None) -> bool:
        certificate = self.cache.object("context_qualification", self.symbol)
        return bool(
            certificate
            and certificate.get("source_hash") == self.qualification_contract_hash
            and certificate.get("model_digest") == model_digest
            and certificate["payload"].get("passed") is True
        )

    def _store_qualification_certificate(
        self, response: dict, model_digest: str | None
    ) -> None:
        self.cache.put_object(
            "context_qualification",
            self.symbol,
            utc_now(),
            {
                "passed": True,
                "qualification_contract_hash": self.qualification_contract_hash,
                "validated_at_utc": iso_utc(utc_now()),
                "response_hash": content_hash(response),
            },
            source_hash=self.qualification_contract_hash,
            evidence_ids=response.get("evidence_ids") or [],
            model_digest=model_digest,
        )

    def _history_analysis(
        self,
        timeframe: str,
        digest: dict,
        model_digest: str | None,
        as_of: datetime,
    ) -> tuple[dict, list[str], dict]:
        cache_type = f"history_analysis_{timeframe}"
        existing = self.cache.object(cache_type, self.symbol)
        if (
            existing
            and existing.get("source_hash") == digest["source_hash"]
            and existing.get("model_digest") == model_digest
        ):
            return existing["payload"], [], {"reused": True}
        contract = load_prompt_section("qwen_history_chunk", self.store_root)
        facts = {"timeframe_digest": digest}
        prompt = contract + "\n\nTIMEFRAME DIGEST:\n" + canonical_json(facts)
        known = {row[0] for row in digest.get("recent_exact_bars", [])}
        known.update(
            block[index]
            for block in digest.get("chronological_blocks", [])
            for index in (5, 7)
        )
        known_values = sorted(known)
        result = self.ollama.generate(
            prompt,
            num_ctx=8192,
            num_predict=300,
            timeout=None,
            format_schema={
                "type": "object",
                "properties": {
                    "timeframe": {"type": "string", "enum": [timeframe]},
                    "source_start_utc": {
                        "type": "string", "enum": [digest["source_start_utc"]]
                    },
                    "source_end_utc": {
                        "type": "string", "enum": [digest["source_end_utc"]]
                    },
                    "market_path": {"type": "string", "maxLength": 120},
                    "dominant_swing_evidence_ids": {
                        "type": "array",
                        "items": {"type": "string", "enum": known_values},
                        "minItems": 1,
                        "maxItems": 2,
                    },
                    "unresolved_fact": {"type": "string", "maxLength": 100},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string", "enum": known_values},
                        "minItems": 1,
                        "maxItems": 2,
                    },
                },
                "required": [
                    "timeframe",
                    "source_start_utc",
                    "source_end_utc",
                    "market_path",
                    "dominant_swing_evidence_ids",
                    "unresolved_fact",
                    "evidence_ids",
                ],
                "additionalProperties": False,
            },
        )
        response, raw, parse_failures = parse_model_json(result)
        failures = list(parse_failures)
        if response is None:
            response = {}
        else:
            if response.get("timeframe") != timeframe:
                failures.append(f"history:{timeframe}:timeframe_mismatch")
            if response.get("source_start_utc") != digest["source_start_utc"]:
                failures.append(f"history:{timeframe}:source_start_mismatch")
            if response.get("source_end_utc") != digest["source_end_utc"]:
                failures.append(f"history:{timeframe}:source_end_mismatch")
            cited = set(response.get("evidence_ids") or [])
            if not cited or not cited.issubset(known):
                failures.append(f"history:{timeframe}:evidence_invalid")
            dominant = set(response.get("dominant_swing_evidence_ids") or [])
            if not dominant or not dominant.issubset(known):
                failures.append(f"history:{timeframe}:dominant_evidence_invalid")
        metrics = self._model_metrics(result)
        self.cache.record_qwen_validation(
            self.symbol,
            cache_type,
            facts,
            response,
            raw,
            not failures,
            failures,
            metrics,
        )
        if not failures:
            self.cache.put_object(
                cache_type,
                self.symbol,
                as_of,
                response,
                source_hash=digest["source_hash"],
                evidence_ids=response.get("evidence_ids") or [],
                model_digest=model_digest,
            )
        return response, failures, metrics

    def _run_playbook_interpretation(
        self,
        core: str,
        structural_response: dict,
        pending_playbooks: list[dict],
        structural_epochs: dict,
        model_digest: str | None,
        raw_hash: str,
        as_of: datetime,
    ) -> tuple[list[dict], dict, list[str], dict]:
        """Let Qwen describe conditions without giving it control of wiring."""
        playbook_epochs = {
            **structural_epochs,
            "playbook_contract": content_hash(
                [
                    {
                        key: row[key]
                        for key in (
                            "playbook_id",
                            "level_id",
                            "buy_invalidation_level_id",
                            "sell_invalidation_level_id",
                            "lower_target_id",
                            "upper_target_id",
                            "evidence_ids",
                        )
                    }
                    for row in pending_playbooks
                ]
            ),
        }
        facts = {
            "epochs": playbook_epochs,
            "validated_structural_localization": {
                key: structural_response.get(key)
                for key in (
                    "timeframe_location",
                    "h4_path",
                    "nearest_lower_zone",
                    "nearest_upper_zone",
                    "unresolved_fact",
                    "evidence_ids",
                )
            },
            "deterministic_playbooks": pending_playbooks,
        }
        source_hash = content_hash(
            {"htf_source": raw_hash, "playbook_epochs": playbook_epochs}
        )
        cached = self.cache.object("playbook_semantic_analysis", self.symbol)
        if (
            cached
            and cached.get("source_hash") == source_hash
            and cached.get("model_digest") == model_digest
            and cached["payload"].get("acknowledged_epochs") == playbook_epochs
        ):
            response = cached["payload"]
            interpretations = response.get("interpretations") or {}
            rows = [
                {**interpretations[row["playbook_id"]]}
                for row in pending_playbooks
            ]
            return rows, response, [], {"reused": True}

        # A condition is already bound to an exact object key and exact
        # level_id.  Qwen sometimes returns a compact semantic token such as
        # ``acceptance_above`` without repeating that ID.  Canonicalize only
        # when it names no competing supplied level; never repair a cross-level
        # answer.
        def bind_conditions(value: dict) -> dict:
            normalized = json.loads(canonical_json(value))
            interpretations = normalized.get("interpretations") or {}
            supplied_levels = {row["level_id"] for row in pending_playbooks}
            for row in pending_playbooks:
                item = interpretations.get(row["playbook_id"])
                if not isinstance(item, dict) or item.get("level_id") != row["level_id"]:
                    continue
                for side in ("buy", "sell"):
                    key = f"{side}_condition"
                    condition = str(item.get(key, ""))
                    if row["level_id"].lower() in condition.lower():
                        continue
                    competing = {
                        level_id
                        for level_id in supplied_levels - {row["level_id"]}
                        if level_id.lower() in condition.lower()
                    }
                    if not competing and condition:
                        item[key] = f"{condition} at {row['level_id']}"
            return normalized

        prior = self.cache.latest_qwen_response(
            self.symbol, "playbook_interpretation", facts
        )
        if prior:
            prior_response, prior_raw = prior
            normalized = bind_conditions(prior_response)
            normalized_passed, _ = (
                self.validator.validate_playbook_interpretation(
                    normalized, playbook_epochs, pending_playbooks
                )
            )
            if normalized_passed:
                metrics = {"revalidated_prior": True, "normalization": "level_binding"}
                self.cache.record_qwen_validation(
                    self.symbol,
                    "playbook_interpretation",
                    facts,
                    normalized,
                    prior_raw,
                    True,
                    [],
                    metrics,
                )
                self.cache.put_object(
                    "playbook_semantic_analysis",
                    self.symbol,
                    as_of,
                    normalized,
                    source_hash=source_hash,
                    evidence_ids=normalized.get("evidence_ids") or [],
                    model_digest=model_digest,
                )
                rows = [
                    normalized["interpretations"][row["playbook_id"]]
                    for row in pending_playbooks
                ]
                return rows, normalized, [], metrics

        contract = load_prompt_section("qwen_playbook_interpretation", self.store_root)
        prompt = core + "\n\n" + contract + "\n\nPLAYBOOK FACTS:\n" + canonical_json(facts)
        interpretation_properties = {}
        for row in pending_playbooks:
            known_evidence = sorted(set(row.get("evidence_ids") or []))
            interpretation_properties[row["playbook_id"]] = {
                "type": "object",
                "properties": {
                    "level_id": {"type": "string", "enum": [row["level_id"]]},
                    "buy_condition": {"type": "string", "maxLength": 120},
                    "sell_condition": {"type": "string", "maxLength": 120},
                    "missing_evidence": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 100},
                        "maxItems": 1,
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string", "enum": known_evidence},
                        "minItems": 1,
                        "maxItems": len(known_evidence),
                    },
                },
                "required": [
                    "level_id",
                    "buy_condition",
                    "sell_condition",
                    "missing_evidence",
                    "evidence_ids",
                ],
                "additionalProperties": False,
            }
        schema = {
            "type": "object",
            "properties": {
                "acknowledged_epochs": {
                    "type": "object",
                    "properties": {
                        key: {"type": "string", "enum": [value]}
                        for key, value in playbook_epochs.items()
                    },
                    "required": list(playbook_epochs),
                    "additionalProperties": False,
                },
                "interpretations": {
                    "type": "object",
                    "properties": interpretation_properties,
                    "required": list(interpretation_properties),
                    "additionalProperties": False,
                },
                "evidence_ids": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": sorted(
                            {
                                evidence_id
                                for row in pending_playbooks
                                for evidence_id in row.get("evidence_ids") or []
                            }
                        ),
                    },
                    "minItems": 1,
                    "maxItems": 3,
                },
            },
            "required": ["acknowledged_epochs", "interpretations", "evidence_ids"],
            "additionalProperties": False,
        }
        result = self.ollama.generate(
            prompt,
            num_ctx=8192,
            num_predict=650,
            timeout=None,
            format_schema=schema,
        )
        response, raw, parse_failures = parse_model_json(result)
        if response is None:
            response = {}
            failures = list(parse_failures)
        else:
            response = bind_conditions(response)
            _, failures = self.validator.validate_playbook_interpretation(
                response, playbook_epochs, pending_playbooks
            )
            failures = list(parse_failures) + failures
        metrics = self._model_metrics(result)
        passed = not failures
        self.cache.record_qwen_validation(
            self.symbol,
            "playbook_interpretation",
            facts,
            response,
            raw,
            passed,
            failures,
            metrics,
        )
        if passed:
            self.cache.put_object(
                "playbook_semantic_analysis",
                self.symbol,
                as_of,
                response,
                source_hash=source_hash,
                evidence_ids=response.get("evidence_ids") or [],
                model_digest=model_digest,
            )
        interpretations = response.get("interpretations") or {}
        rows = [
            interpretations[row["playbook_id"]]
            for row in pending_playbooks
            if row["playbook_id"] in interpretations
        ]
        return rows, response, failures, metrics

    def _run_warmup(
        self,
        structure: dict,
        levels: dict,
        session: dict,
        playbooks: dict,
        model_digest: str | None,
        raw_hash: str,
        as_of: datetime,
    ) -> tuple[dict, dict, list[str]]:
        core = (self.store_root / "core_skill.md").read_text(encoding="utf-8")
        contract = load_prompt_section("qwen_cache_warmup", self.store_root)
        session_epochs = {
            "structural": structure["cache_epoch"],
            "session": session["cache_epoch"],
            "playbooks": playbooks["cache_epoch"],
        }
        structural_epochs = {
            "structural": structure["cache_epoch"],
            "playbook_basis": f"htf:{raw_hash}",
        }
        history = {
            timeframe: deterministic_history_digest(self.cache, self.symbol, timeframe)
            for timeframe in TIMEFRAME_SECONDS
        }
        history_analyses = {}
        history_metrics = {}
        history_failures: list[str] = []
        for timeframe in ("D1", "H4", "H1"):
            analysis, analysis_failures, analysis_metrics = self._history_analysis(
                timeframe, history[timeframe], model_digest, as_of
            )
            history_analyses[timeframe] = analysis
            history_metrics[timeframe] = analysis_metrics
            history_failures.extend(analysis_failures)
        if history_failures:
            return {}, playbooks, history_failures
        forming = self.cache.forming(self.symbol)
        all_level_rows = levels["payload"]["levels"]
        important_level_ids = {
            row["level_id"]
            for row in all_level_rows
            if row["timeframe"] in ("D1", "H4", "H1")
        }
        for key in ("nearest_lower", "nearest_upper"):
            if levels["payload"].get(key):
                important_level_ids.add(levels["payload"][key]["level_id"])
        important_levels = [
            row for row in all_level_rows if row["level_id"] in important_level_ids
        ]
        compact_levels = [
            [
                row["level_id"],
                row["timeframe"],
                row["zone_low"],
                row["zone_high"],
                row["role"],
                row["source_candle_ids"],
            ]
            for row in important_levels
        ]
        pending_playbooks = [
            {
                "level_id": row["level_id"],
                "playbook_id": row["playbook_id"],
                "buy_invalidation_level_id": row["buy_invalidation_level_id"],
                "sell_invalidation_level_id": row["sell_invalidation_level_id"],
                "lower_target_id": row["lower_target_id"],
                "upper_target_id": row["upper_target_id"],
                "evidence_ids": row["evidence_ids"],
            }
            for row in playbooks["payload"].get("playbooks", [])[:3]
        ]
        structural_facts = {
            "epochs": structural_epochs,
            "history_analysis_contract": (
                "Each analysis was separately validated against a deterministic digest "
                "covering every cached source bar for its timeframe."
            ),
            "history_analyses": {
                timeframe: history_analyses[timeframe]
                for timeframe in ("D1", "H4", "H1")
            },
            "deterministic_levels": {
                "price": levels["payload"]["price"],
                "columns": [
                    "level_id",
                    "timeframe",
                    "zone_low",
                    "zone_high",
                    "role",
                    "source_candle_ids",
                ],
                "rows": compact_levels,
                "nearest_lower": levels["payload"].get("nearest_lower"),
                "nearest_upper": levels["payload"].get("nearest_upper"),
            },
            "deterministic_structure": structure["payload"],
        }
        prompt = (
            core
            + "\n\n"
            + contract
            + "\n\nSTRUCTURAL CACHE FACTS:\n"
            + canonical_json(structural_facts)
        )
        # A bounded validation response leaves the consolidation prompt room
        # for output. ``-1`` can reserve excessive output space and silently
        # truncate the supplied summaries.
        epoch_schema = {
            "type": "object",
            "properties": {
                key: {"type": "string", "enum": [value]}
                for key, value in structural_epochs.items()
            },
            "required": list(structural_epochs),
            "additionalProperties": False,
        }
        location_schema = {
            "type": "object",
            "properties": {
                "location": {"type": "string", "maxLength": 80},
                "auction_state": {
                    "type": "string",
                    "enum": ["acceptance", "rejection", "balance", "transition", "unclear"],
                },
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 1,
                },
            },
            "required": ["location", "auction_state", "evidence_ids"],
            "additionalProperties": False,
        }
        expected_role_rows = structure["payload"].get("timeframe_location", {})
        location_schemas = {}
        for timeframe in ("D1", "H4", "H1"):
            expected_role = expected_role_rows.get(timeframe, {})
            location_schemas[timeframe] = {
                **location_schema,
                "properties": {
                    **location_schema["properties"],
                    "location": {
                        "type": "string",
                        "enum": [expected_role.get("location")],
                    },
                    "auction_state": {
                        "type": "string",
                        "enum": [expected_role.get("auction_state")],
                    },
                    "evidence_ids": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": expected_role.get("evidence_ids") or ["unavailable"],
                        },
                        "minItems": 1,
                        "maxItems": 1,
                    },
                },
            }
        zone_schema = {
            "type": "object",
            "properties": {
                "level_id": {"type": "string"},
                "price": {"type": "number"},
            },
            "required": ["level_id", "price"],
            "additionalProperties": False,
        }
        zone_schemas = {}
        for response_key, structure_key in (
            ("nearest_lower_zone", "nearest_lower_zone"),
            ("nearest_upper_zone", "nearest_upper_zone"),
        ):
            expected_zone = structure["payload"].get(structure_key) or {}
            zone_schemas[response_key] = {
                **zone_schema,
                "properties": {
                    "level_id": {
                        "type": "string",
                        "enum": [expected_zone.get("level_id")],
                    },
                    "price": {
                        "type": "number",
                        "enum": [expected_zone.get("zone_low")],
                    },
                },
            }
        structural_schema = {
            "type": "object",
            "properties": {
                "acknowledged_epochs": epoch_schema,
                "timeframe_location": {
                    "type": "object",
                    "properties": location_schemas,
                    "required": ["D1", "H4", "H1"],
                    "additionalProperties": False,
                },
                "h4_path": {
                    "type": "object",
                    "properties": {
                        "current_open": {
                            "type": ["number", "null"],
                            "enum": [structure["payload"].get("current_h4_open")],
                        },
                        "current_state": {
                            "type": "string",
                            "enum": [structure["payload"].get("current_h4_state")],
                        },
                        "unfinished_movement": {"type": "string", "maxLength": 120},
                        "evidence_ids": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": [
                                    forming.get("H4", {}).get("evidence_id", "unavailable")
                                ],
                            },
                            "minItems": 1,
                            "maxItems": 1,
                        },
                    },
                    "required": ["current_open", "current_state", "unfinished_movement", "evidence_ids"],
                    "additionalProperties": False,
                },
                "nearest_lower_zone": zone_schemas["nearest_lower_zone"],
                "nearest_upper_zone": zone_schemas["nearest_upper_zone"],
                "unresolved_fact": {"type": "string", "maxLength": 120},
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 2,
                },
            },
            "required": [
                "acknowledged_epochs", "timeframe_location", "h4_path",
                "nearest_lower_zone", "nearest_upper_zone", "unresolved_fact",
                "evidence_ids"
            ],
            "additionalProperties": False,
        }
        known_candles = {
            row["evidence_id"]
            for timeframe in TIMEFRAME_SECONDS
            for row in self.cache.completed(self.symbol, timeframe)
        }
        known_candles.update(
            row["evidence_id"] for row in forming.values() if row.get("evidence_id")
        )
        known_levels = {
            row["level_id"] for row in levels["payload"]["levels"]
        }
        phase = self.cache.object("structural_phase_analysis", self.symbol)
        if (
            phase
            and phase.get("source_hash") == raw_hash
            and phase.get("model_digest") == model_digest
            and phase["payload"].get("acknowledged_epochs") == structural_epochs
        ):
            response = phase["payload"]
            passed, failures = True, []
            metrics = {"history": history_metrics, "structural": {"reused": True}}
        else:
            structural_result = self.ollama.generate(
                prompt,
                num_ctx=12288,
                # 550 truncated mid-evidence_ids (~1320 chars). Pinning + 1024
                # leaves headroom for the two long candle evidence ids.
                num_predict=1024,
                timeout=None,
                format_schema=structural_schema,
            )
            response, raw, parse_failures = parse_model_json(structural_result)
            if response is None:
                passed, failures = False, parse_failures
                response = {}
            else:
                passed, failures = self.validator.validate_warmup(
                    response,
                    structural_epochs,
                    known_candles,
                    known_levels,
                    structure["payload"],
                )
                failures = parse_failures + failures
                passed = not failures
            metrics = {
                "history": history_metrics,
                "structural": self._model_metrics(structural_result),
            }
            self.cache.record_qwen_validation(
                self.symbol,
                "structural_warmup",
                structural_facts,
                response,
                raw,
                passed,
                failures,
                metrics["structural"],
            )
            if passed:
                self.cache.put_object(
                    "structural_phase_analysis",
                    self.symbol,
                    as_of,
                    response,
                    source_hash=raw_hash,
                    evidence_ids=response.get("evidence_ids") or [],
                    model_digest=model_digest,
                )
        if passed:
            (
                qwen_playbooks,
                playbook_response,
                playbook_failures,
                playbook_metrics,
            ) = self._run_playbook_interpretation(
                core,
                response,
                pending_playbooks,
                structural_epochs,
                model_digest,
                raw_hash,
                as_of,
            )
            metrics["playbooks"] = playbook_metrics
            failures.extend(playbook_failures)
            response["playbook_analysis"] = playbook_response
            passed = passed and not playbook_failures
            if passed:
                playbooks = self.builder.build_playbooks(
                    as_of, raw_hash, levels, model_digest, qwen_playbooks
                )
                session_epochs["playbooks"] = playbooks["cache_epoch"]
        if passed:
            session_contract = load_prompt_section("qwen_session_warmup", self.store_root)
            compact_forming = {
                timeframe: {
                    key: row.get(key)
                    for key in (
                        "evidence_id", "open_time_utc", "open", "high", "low", "close"
                    )
                }
                for timeframe, row in forming.items()
            }
            session_facts = {
                "epochs": session_epochs,
                "phase_one_structural_result": response,
                "history_digest_contract": (
                    "Each deterministic digest covers every cached source bar, "
                    "is bound by source_hash, and includes recent exact bars."
                ),
                "history_digests": {
                    timeframe: history[timeframe]
                    for timeframe in ("M30", "M15", "M5", "M1")
                },
                "forming_candles": compact_forming,
                "deterministic_session": session["payload"],
                "active_playbook_ids": [
                    row["playbook_id"]
                    for row in playbooks["payload"].get("playbooks", [])
                ],
            }
            session_prompt = (
                core
                + "\n\n"
                + session_contract
                + "\n\nSESSION CACHE FACTS:\n"
                + canonical_json(session_facts)
            )
            expected_session = session["payload"]
            expected_ids = {
                row["playbook_id"]
                for row in playbooks["payload"].get("playbooks", [])
            }
            session_schema = {
                "type": "object",
                "properties": {
                    "acknowledged_epochs": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string", "enum": [value]}
                            for key, value in session_epochs.items()
                        },
                        "required": list(session_epochs),
                        "additionalProperties": False,
                    },
                    "session_read": {
                        "type": "object",
                        "properties": {
                            "session": {
                                "type": "string",
                                "enum": [expected_session.get("session")],
                            },
                            "asia_relation": {
                                "type": "string",
                                "enum": [expected_session.get("asia_relation")],
                            },
                            "asia_high": {
                                "type": ["number", "null"],
                                "enum": [expected_session.get("asia_high")],
                            },
                            "asia_low": {
                                "type": ["number", "null"],
                                "enum": [expected_session.get("asia_low")],
                            },
                            "evidence_ids": {
                                "type": "array", "items": {"type": "string"},
                                "maxItems": 2,
                            },
                        },
                        "required": [
                            "session", "asia_relation", "asia_high", "asia_low",
                            "evidence_ids",
                        ],
                        "additionalProperties": False,
                    },
                    "intermediate_path": {
                        "type": "object",
                        "properties": {
                            "M30": {"type": "string", "maxLength": 100},
                            "M15": {"type": "string", "maxLength": 100},
                        },
                        "required": ["M30", "M15"],
                        "additionalProperties": False,
                    },
                    "local_map": {
                        "type": "object",
                        "properties": {
                            "M5": {"type": "string", "maxLength": 100},
                            "M1": {"type": "string", "maxLength": 100},
                        },
                        "required": ["M5", "M1"],
                        "additionalProperties": False,
                    },
                    "active_playbook_ids": {
                        "type": "array",
                        "items": {"type": "string", "enum": sorted(expected_ids)},
                        "maxItems": len(expected_ids),
                    },
                    "structural_consistency": {"type": "string", "maxLength": 100},
                    "unresolved_fact": {"type": "string", "maxLength": 100},
                    "evidence_ids": {
                        "type": "array", "items": {"type": "string"}, "maxItems": 4,
                    },
                },
                "required": [
                    "acknowledged_epochs", "session_read", "intermediate_path",
                    "local_map", "active_playbook_ids", "structural_consistency",
                    "unresolved_fact", "evidence_ids",
                ],
                "additionalProperties": False,
            }
            session_source_hash = content_hash(
                {
                    "session_source": session["source_hash"],
                    "structural_source": raw_hash,
                    "session_epochs": session_epochs,
                }
            )
            session_phase = self.cache.object("session_phase_analysis", self.symbol)
            session_metrics: dict
            if (
                session_phase
                and session_phase.get("source_hash") == session_source_hash
                and session_phase.get("model_digest") == model_digest
                and session_phase["payload"].get("acknowledged_epochs") == session_epochs
            ):
                session_response = session_phase["payload"]
                session_raw = canonical_json(session_response)
                session_failures = []
                session_metrics = {"reused": True}
            else:
                # 8192 (not 16384): on this GPU, v004 + constrained JSON schema
                # at 16k ctx kills the Ollama runner mid-generate
                # ("connection forcibly closed" / HTTP 500). Session prompts
                # are ~7-8k tokens; 8k ctx is enough and stays resident.
                session_result = self.ollama.generate(
                    session_prompt,
                    num_ctx=8192,
                    num_predict=600,
                    timeout=None,
                    format_schema=session_schema,
                )
                session_response, session_raw, session_parse_failures = parse_model_json(
                    session_result
                )
                session_failures = list(session_parse_failures)
                if session_response is None:
                    session_response = {}
                else:
                    if session_response.get("acknowledged_epochs") != session_epochs:
                        session_failures.append("session_warmup:epoch_mismatch")
                    session_read = session_response.get("session_read") or {}
                    for key in ("session", "asia_relation", "asia_high", "asia_low"):
                        if session_read.get(key) != expected_session.get(key):
                            session_failures.append(f"session_warmup:{key}:mismatch")
                    if set(session_response.get("active_playbook_ids") or []) != expected_ids:
                        session_failures.append("session_warmup:playbook_ids_mismatch")
                    cited = set(session_response.get("evidence_ids") or [])
                    if not cited or not cited.issubset(known_candles | known_levels):
                        session_failures.append("session_warmup:evidence_invalid")
                session_metrics = self._model_metrics(session_result)
            session_passed = not session_failures
            metrics["session"] = session_metrics
            self.cache.record_qwen_validation(
                self.symbol,
                "session_warmup",
                session_facts,
                session_response,
                session_raw,
                session_passed,
                session_failures,
                metrics["session"],
            )
            if session_passed and not session_metrics.get("reused"):
                self.cache.put_object(
                    "session_phase_analysis",
                    self.symbol,
                    as_of,
                    session_response,
                    source_hash=session_source_hash,
                    evidence_ids=session_response.get("evidence_ids") or [],
                    model_digest=model_digest,
                )
            failures.extend(session_failures)
            response["session_analysis"] = session_response
            response["session_read"] = session_response.get("session_read")
            passed = passed and session_passed
        if passed:
            self.cache.put_object(
                "structural_analysis",
                self.symbol,
                as_of,
                response,
                source_hash=raw_hash,
                evidence_ids=response.get("evidence_ids") or [],
                model_digest=model_digest,
            )
        return response, playbooks, failures

    def _challenge_payload(
        self, structure: dict, levels: dict, session: dict, playbooks: dict
    ) -> dict:
        structural = structure["payload"]
        session_payload = session["payload"]
        playbook_rows = playbooks["payload"].get("playbooks") or []
        active = playbook_rows[0] if playbook_rows else {}
        locations = {
            timeframe: structural["timeframe_location"].get(timeframe, {}).get("location")
            for timeframe in ("D1", "H4", "H1")
        }
        lower = structural.get("nearest_lower_zone")
        upper = structural.get("nearest_upper_zone")
        exact = {
            "acknowledged_epochs": {
                "structural": structure["cache_epoch"],
                "levels": levels["cache_epoch"],
                "session": session["cache_epoch"],
                "playbooks": playbooks["cache_epoch"],
            },
            "timeframe_location": locations,
            "h4_open": structural.get("current_h4_open"),
            "h4_state": structural.get("current_h4_state"),
            "session": session_payload.get("session"),
            "asia_relation": session_payload.get("asia_relation"),
            "nearest_lower_zone": (
                {"level_id": lower["level_id"], "price": lower["zone_low"]}
                if lower
                else None
            ),
            "nearest_upper_zone": (
                {"level_id": upper["level_id"], "price": upper["zone_low"]}
                if upper
                else None
            ),
            "active_playbook_ids": [row["playbook_id"] for row in playbook_rows],
            "conditional_buy_path": active.get("buy_condition"),
            "conditional_sell_path": active.get("sell_condition"),
            "unresolved_fact": structural.get("unresolved_fact"),
        }
        h1_completed = structural["timeframe_location"].get("H1", {}).get("latest_completed") or {}
        h1_forming_id = structural["timeframe_location"].get("H1", {}).get(
            "forming_evidence_id"
        )
        h4_level = next(
            (row for row in levels["payload"]["levels"] if row["timeframe"] == "H4"),
            None,
        )
        tests = [
            {"test_id": "price_vs_asia", "answer": session_payload.get("asia_relation")},
            {
                "test_id": "h1_completed_vs_forming",
                "answer": {
                    "completed_id": h1_completed.get("evidence_id"),
                    "forming_id": h1_forming_id,
                },
            },
            {
                "test_id": "h4_level_source",
                "answer": (
                    {
                        "level_id": h4_level["level_id"],
                        "source_candle_id": h4_level["source_candle_ids"][0],
                    }
                    if h4_level
                    else None
                ),
            },
            {
                "test_id": "playbook_invalidations",
                "answer": {
                    "buy": active.get("buy_invalidation_level_id"),
                    "sell": active.get("sell_invalidation_level_id"),
                },
            },
        ]
        known = set(structure["evidence_ids"])
        known.update(levels["evidence_ids"])
        known.update(session["evidence_ids"])
        known.update(playbooks["evidence_ids"])
        known.update(row["level_id"] for row in levels["payload"]["levels"])
        request = {
            "timeframe": "M1",
            "completed_bars": 20,
            "fields": ["ohlc", "tick_volume"],
            "reason": "latest M1 tick_volume deliberately omitted",
        }
        supplied = {
            "exact_facts": exact,
            "localization_tests": tests,
            "deliberately_omitted_fact": "latest M1 tick_volume",
            "allowed_request": request,
            "evidence_catalog": sorted(known),
        }
        return {
            "supplied": supplied,
            "expected_exact": exact,
            "localization_tests": tests,
            "expected_data_requests": [request],
            "known_evidence_ids": sorted(known),
        }

    def _run_challenge(
        self, structure: dict, levels: dict, session: dict, playbooks: dict
    ) -> tuple[bool, list[str], dict]:
        model_digest = self.ollama.model_info().get("digest")
        if self._qualification_is_valid(model_digest):
            return True, [], {"reused_certificate": True}
        challenge = self._challenge_payload(structure, levels, session, playbooks)
        contract = load_prompt_section("qwen_context_challenge", self.store_root)
        prompt = contract + "\n\nCACHE CHALLENGE:\n" + canonical_json(challenge["supplied"])

        prior = self.cache.latest_qwen_response(
            self.symbol, "context_challenge", challenge["supplied"]
        )
        if prior:
            prior_response, _ = prior
            prior_passed, prior_failures = self.validator.validate_challenge(
                prior_response, challenge
            )
            if prior_passed:
                self._store_qualification_certificate(prior_response, model_digest)
                return True, [], {"revalidated_prior": True}

        def exact_schema(value):
            if isinstance(value, dict):
                return {
                    "type": "object",
                    "properties": {
                        key: exact_schema(item) for key, item in value.items()
                    },
                    "required": list(value),
                    "additionalProperties": False,
                }
            if isinstance(value, list):
                # Pin the whole list; Ollama format schemas accept array enums.
                return {"type": "array", "enum": [value]}
            if value is None:
                return {"type": "null"}
            if isinstance(value, bool):
                return {"type": "boolean", "enum": [value]}
            if isinstance(value, (int, float)):
                return {"type": "number", "enum": [value]}
            return {"type": "string", "enum": [value]}

        localization_properties = {
            row["test_id"]: exact_schema(row["answer"])
            for row in challenge["localization_tests"]
        }
        # Pin every exact_facts field to the packet values so the model cannot
        # invent timestamps / bar indexes / alternate epoch shapes (v003 habit).
        exact = challenge["expected_exact"]
        known_ids = list(challenge["known_evidence_ids"])
        expected_request = (challenge["expected_data_requests"] or [None])[0]
        pinned_properties = {
            key: exact_schema(value) for key, value in exact.items()
        }
        pinned_properties["localization_answers"] = {
            "type": "object",
            "properties": localization_properties,
            "required": list(localization_properties),
            "additionalProperties": False,
        }
        pinned_properties["evidence_ids"] = {
            "type": "array",
            "items": (
                {"type": "string", "enum": known_ids}
                if known_ids
                else {"type": "string"}
            ),
            "minItems": 1,
            "maxItems": min(4, max(1, len(known_ids) or 1)),
            "uniqueItems": True,
        }
        if expected_request is not None:
            pinned_properties["data_requests"] = {
                "type": "array",
                "items": exact_schema(expected_request),
                "minItems": 1,
                "maxItems": 1,
            }
        else:
            pinned_properties["data_requests"] = {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
            }
        challenge_schema = {
            "type": "object",
            "properties": pinned_properties,
            "required": [
                "acknowledged_epochs", "timeframe_location", "h4_open", "h4_state",
                "session", "asia_relation", "nearest_lower_zone", "nearest_upper_zone",
                "active_playbook_ids", "conditional_buy_path", "conditional_sell_path",
                "unresolved_fact", "localization_answers", "evidence_ids", "data_requests",
            ],
            "additionalProperties": False,
        }
        result = self.ollama.generate(
            prompt,
            num_ctx=8192,
            num_predict=1024,
            timeout=None,
            format_schema=challenge_schema,
        )
        response, raw, parse_failures = parse_model_json(result)
        if response is None:
            passed, failures = False, parse_failures
            response = {}
        else:
            passed, failures = self.validator.validate_challenge(response, challenge)
            failures = parse_failures + failures
        metrics = self._model_metrics(result)
        self.cache.record_qwen_validation(
            self.symbol,
            "context_challenge",
            challenge["supplied"],
            response,
            raw,
            passed,
            failures,
            metrics,
        )
        if passed:
            self._store_qualification_certificate(response, model_digest)
        return passed, failures, metrics

    def _run_minute_shadow(self, minute: dict) -> tuple[bool, list[str], dict]:
        packet = minute["payload"]
        contract = load_prompt_section("qwen_minute_shadow", self.store_root)
        prompt = contract + "\n\nMINUTE PACKET:\n" + canonical_json(packet)
        started = time.perf_counter()
        minute_schema = {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["open", "wait", "skip", "request_data"]},
                "direction": {"type": "string", "enum": ["buy", "sell", "none"]},
                "playbook_id": {"type": ["string", "null"]},
                "observed_trigger": {"type": ["string", "null"], "maxLength": 100},
                "invalidation_level_id": {"type": ["string", "null"]},
                "target_level_id": {"type": ["string", "null"]},
                "confidence_score": {"type": "number", "minimum": 0, "maximum": 100},
                "buy_thesis": {"type": "string", "maxLength": 100},
                "sell_thesis": {"type": "string", "maxLength": 100},
                "evidence_ids": {
                    "type": "array", "items": {"type": "string"}, "maxItems": 4,
                },
                "data_requests": {"type": "array", "maxItems": 1},
            },
            "required": [
                "action", "direction", "playbook_id", "observed_trigger",
                "invalidation_level_id", "target_level_id", "confidence_score",
                "buy_thesis", "sell_thesis", "evidence_ids", "data_requests",
            ],
            "additionalProperties": False,
        }
        result = self.ollama.generate(
            prompt,
            num_ctx=4096,
            num_predict=300,
            timeout=None,
            format_schema=minute_schema,
        )
        wall_ms = (time.perf_counter() - started) * 1000
        response, raw, parse_failures = parse_model_json(result)
        if response is None:
            passed, failures = False, parse_failures
            response = {}
        else:
            passed, failures = self.validator.validate_minute_response(response, packet)
            failures = parse_failures + failures
        metrics = self._model_metrics(result)
        metrics.update(
            {
                "wall_ms": round(wall_ms, 3),
                "packet_bytes": len(canonical_json(packet).encode("utf-8")),
                "packet_token_estimate": round(len(canonical_json(packet)) / 4),
                "full_prompt_bytes": len(prompt.encode("utf-8")),
            }
        )
        self.cache.record_qwen_validation(
            self.symbol,
            "minute_shadow",
            packet,
            response,
            raw,
            passed,
            failures,
            metrics,
        )
        return passed, failures, metrics

    def run_once(self, *, run_qwen: bool = True, benchmark_minute: bool = True) -> dict:
        cycle_id = f"context-{utc_now():%Y%m%dT%H%M%S}-{os.getpid()}"
        timings: dict[str, float] = {}
        prior_manifest = self.cache.latest_manifest(self.symbol)
        started = time.perf_counter()
        quote = self.source.quote()
        as_of = as_utc(quote.time_utc)
        starts = self.cache.incremental_starts(self.symbol, as_of)
        completed, forming = self.source.history(as_of, starts)
        inserted = {}
        for timeframe, rows in completed.items():
            inserted[timeframe] = self.cache.ingest_completed(rows)
        self.cache.upsert_forming(forming.values())
        self.cache.add_quote(quote)
        timings["cache_update_ms"] = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        raw_hash = self.cache.raw_hash(self.symbol)
        levels_hash = self.cache.subset_hash(self.symbol, TIMEFRAME_SECONDS)
        structural_hash = self.cache.subset_hash(
            self.symbol, ("D1", "H4", "H1")
        )
        session_hash = self.cache.subset_hash(
            self.symbol, ("M5", "M15", "M30")
        )
        # 2026-08-06 M30 entry granularity: the watched-zone playbook list is
        # what actually times entries (qwen_cached_entry), so it must react to
        # a fresh M30 close, not just D1/H4/H1. Deliberately decoupled from
        # structural_hash so the D1/H4/H1 warmup/narrative cache (and its Qwen
        # calls) keeps its existing hourly-or-slower cadence -- only the
        # playbook layer gets the faster refresh.
        playbook_hash = self.cache.subset_hash(
            self.symbol, ("D1", "H4", "H1", "M30")
        )
        model_info = self.ollama.model_info()
        levels = self.builder.build_levels(as_of, quote.bid, levels_hash)
        structure = self.builder.build_structure(
            as_of, quote.bid, structural_hash, levels
        )
        session = self.builder.build_session(as_of, quote.bid, session_hash)
        existing_playbooks = self.cache.object("playbooks", self.symbol)
        if (
            existing_playbooks
            and existing_playbooks["source_hash"] == playbook_hash
            and all(
                row.get("buy_condition") and row.get("sell_condition")
                for row in existing_playbooks["payload"].get("playbooks", [])
            )
        ):
            playbooks = existing_playbooks
        else:
            playbooks = self.builder.build_playbooks(
                as_of, playbook_hash, levels, model_info.get("digest")
            )
        timings["projection_ms"] = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        if prior_manifest and prior_manifest.get("raw_data_valid"):
            gate_a, gate_a_failures, raw_metrics = self.validator.gate_a_incremental(
                as_of, completed
            )
        else:
            gate_a, gate_a_failures, raw_metrics = self.validator.gate_a(as_of)
        timings["raw_validation_ms"] = (time.perf_counter() - started) * 1000

        prior_qualification_reusable = self._qualification_is_valid(
            model_info.get("digest")
        )
        warmup_failures: list[str] = []
        challenge_valid = prior_qualification_reusable
        challenge_failures: list[str] = []
        challenge_metrics: dict = {}
        structural_analysis = self.cache.object("structural_analysis", self.symbol)
        needs_warmup = not (
            structural_analysis
            and structural_analysis.get("model_digest") == model_info.get("digest")
            and structural_analysis["payload"].get("acknowledged_epochs", {}).get("structural")
            == structure["cache_epoch"]
            and structural_analysis["payload"].get("session_analysis", {})
            .get("acknowledged_epochs", {})
            .get("session")
            == session["cache_epoch"]
            and structural_analysis["payload"].get("session_analysis", {})
            .get("acknowledged_epochs", {})
            .get("playbooks")
            == playbooks["cache_epoch"]
            and all(
                row.get("buy_condition") and row.get("sell_condition")
                for row in playbooks["payload"].get("playbooks", [])
            )
        )
        if (
            run_qwen
            and gate_a
            and needs_warmup
            and not prior_qualification_reusable
        ):
            _, playbooks, warmup_failures = self._run_warmup(
                structure,
                levels,
                session,
                playbooks,
                model_info.get("digest"),
                playbook_hash,
                as_of,
            )

        started = time.perf_counter()
        # Warmup can take minutes; recompute raw_hash so the minute packet is
        # not written with a stale hash while another worker ingested ticks.
        raw_hash = self.cache.raw_hash(self.symbol)
        minute = self.builder.build_minute(
            as_of, quote, raw_hash, structure, levels, session, playbooks
        )
        timings["minute_packet_ms"] = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        gate_b, gate_b_failures, derived_metrics = self.validator.gate_b()
        # If another cycle raced between minute write and gate_b, rebuild once.
        if not gate_b and "derived:minute:source_hash_mismatch" in gate_b_failures:
            raw_hash = self.cache.raw_hash(self.symbol)
            minute = self.builder.build_minute(
                as_of, quote, raw_hash, structure, levels, session, playbooks
            )
            gate_b, gate_b_failures, derived_metrics = self.validator.gate_b()
        timings["derived_validation_ms"] = (time.perf_counter() - started) * 1000

        prior_epochs = (prior_manifest or {}).get("compatible_epochs", {})
        can_reuse_challenge = bool(
            prior_qualification_reusable
            and prior_epochs.get("structural") == structure["cache_epoch"]
            and prior_epochs.get("playbooks") == playbooks["cache_epoch"]
        )
        if can_reuse_challenge:
            challenge_valid = True
            challenge_metrics = {"reused": True}
        elif run_qwen and gate_a and gate_b and not warmup_failures:
            challenge_valid, challenge_failures, challenge_metrics = self._run_challenge(
                structure, levels, session, playbooks
            )

        minute_valid = True
        minute_failures: list[str] = []
        minute_metrics: dict = {
            "packet_bytes": len(canonical_json(minute["payload"]).encode("utf-8")),
            "packet_token_estimate": round(len(canonical_json(minute["payload"])) / 4),
        }
        if run_qwen and benchmark_minute and gate_a and gate_b:
            minute_valid, minute_failures, minute_metrics = self._run_minute_shadow(minute)

        incremental = run_incremental_self_test()
        resident = self.ollama.model_info()
        model_resident = bool(
            resident.get("resident")
            and resident.get("digest") == resident.get("resident_digest")
        )
        # Long warmup/challenge generations can drop residency briefly; a
        # one-token warm restores keep_alive=-1 before the manifest is written.
        if not model_resident and challenge_valid:
            try:
                self.ollama.warm()
            except Exception:
                logging.exception("Post-challenge model warm failed")
            resident = self.ollama.model_info()
            model_resident = bool(
                resident.get("resident")
                and resident.get("digest") == resident.get("resident_digest")
            )
        failures = (
            gate_a_failures
            + gate_b_failures
            + warmup_failures
            + challenge_failures
            + minute_failures
            + incremental["failures"]
        )
        flags = {
            "model_resident": model_resident,
            "raw_data_valid": gate_a,
            "structural_cache_valid": gate_b and bool(structure),
            "level_cache_valid": gate_b and bool(levels["payload"].get("levels")),
            "playbooks_valid": gate_b
            and bool(playbooks["payload"].get("playbooks"))
            and all(
                row.get("buy_condition") and row.get("sell_condition")
                for row in playbooks["payload"].get("playbooks", [])
            ),
            "session_cache_valid": gate_b and bool(session),
            "minute_delta_valid": incremental["passed"] and minute_valid,
            "context_challenge_valid": challenge_valid,
        }
        if not run_qwen and not prior_qualification_reusable:
            failures.append("qwen_validation_not_run")
        if not model_resident:
            failures.append("model_not_resident_or_digest_mismatch")
        for name, passed in flags.items():
            if not passed and not any(name in item for item in failures):
                failures.append(name)
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "status": "ready" if all(flags.values()) else "blocked",
            **flags,
            "qualification_contract_hash": self.qualification_contract_hash,
            "compatible_epochs": derived_metrics.get("epochs", {}),
            "model": {"name": self.ollama.model, **resident},
            "validated_at_utc": iso_utc(utc_now()),
            "failures": sorted(set(failures)),
            "metrics": {
                **{key: round(value, 3) for key, value in timings.items()},
                "raw": raw_metrics,
                "derived": derived_metrics,
                "challenge": challenge_metrics,
                "minute": minute_metrics,
                "incremental": incremental,
                "ingestion": inserted,
            },
        }
        self.cache.write_manifest(self.symbol, manifest)
        for stage, duration in timings.items():
            self.cache.record_latency(self.symbol, cycle_id, stage, duration, {})
        return manifest


def fixture_candle(
    symbol: str,
    timeframe: str,
    opened: datetime,
    base: float,
    *,
    complete: bool = True,
) -> dict:
    seconds = TIMEFRAME_SECONDS[timeframe]
    return {
        "evidence_id": candle_id(symbol, timeframe, opened),
        "symbol": symbol,
        "timeframe": timeframe,
        "open_time_utc": iso_utc(opened),
        "close_time_utc": iso_utc(opened + timedelta(seconds=seconds)),
        "open": base,
        "high": base + 1,
        "low": base - 1,
        "close": base + 0.25,
        "tick_volume": 100,
        "spread": 8,
        "real_volume": 0,
        "is_complete": complete,
        "source": "fixture",
        "ingested_at_utc": iso_utc(utc_now()),
    }


def run_incremental_self_test() -> dict:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qwen-context-") as folder:
        path = Path(folder) / "fixture.sqlite3"
        symbol = "XAUUSDr"
        opened = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
        cache = MarketContextCache(path, report_metadata_corrections=False)
        row = fixture_candle(symbol, "M1", opened, 4000)
        first = cache.ingest_completed([row])
        before = cache.raw_hash(symbol)
        second = cache.ingest_completed([row])
        after = cache.raw_hash(symbol)
        if first["inserted"] != 1 or second["unchanged"] != 1 or before != after:
            failures.append("incremental:idempotence")
        metadata_revision = {
            **row,
            "tick_volume": row["tick_volume"] - 5,
            "spread": row["spread"] + 1,
        }
        metadata_result = cache.ingest_completed([metadata_revision])
        metadata_cached = cache.latest_completed(symbol, "M1", 1)[-1]
        if (
            metadata_result["metadata_corrections"] != 1
            or metadata_cached["tick_volume"] != row["tick_volume"]
            or metadata_cached["spread"] != row["spread"]
            or cache.raw_hash(symbol) != before
        ):
            failures.append("incremental:metadata_correction_not_isolated")
        try:
            cache.ingest_completed([{**row, "close": row["close"] + 0.1}])
        except ValueError as exc:
            if "fields=close" not in str(exc):
                failures.append("incremental:ohlc_correction_diagnostic")
        else:
            failures.append("incremental:ohlc_correction_accepted")
        try:
            cache.ingest_completed(
                [{**row, "close_time_utc": iso_utc(opened + timedelta(minutes=2))}]
            )
        except ValueError as exc:
            if "fields=close_time_utc" not in str(exc):
                failures.append("incremental:timestamp_correction_diagnostic")
        else:
            failures.append("incremental:timestamp_correction_accepted")
        forming = fixture_candle(
            symbol, "M5", opened, 4000, complete=False
        )
        cache.upsert_forming([forming])
        if cache.forming(symbol).get("M5", {}).get("open_time_utc") != iso_utc(opened):
            failures.append("incremental:forming_upsert")
        completed_m5 = {**forming, "is_complete": True}
        cache.ingest_completed([completed_m5])
        if "M5" in cache.forming(symbol):
            failures.append("incremental:forming_promotion")
        first_obj = cache.put_object(
            "playbooks",
            symbol,
            opened,
            {"version": 1},
            source_hash=cache.raw_hash(symbol),
            evidence_ids=[row["evidence_id"]],
        )
        second_obj = cache.put_object(
            "playbooks",
            symbol,
            opened + timedelta(hours=4),
            {"version": 2},
            source_hash=cache.raw_hash(symbol),
            evidence_ids=[row["evidence_id"]],
        )
        stale = cache.connection.execute(
            "SELECT is_current, invalidation_reason FROM cache_objects WHERE cache_epoch=?",
            (first_obj["cache_epoch"],),
        ).fetchone()
        if (
            first_obj["cache_epoch"] == second_obj["cache_epoch"]
            or stale["is_current"] != 0
            or stale["invalidation_reason"] != "superseded"
        ):
            failures.append("incremental:h4_epoch_expiry")
        final_hash = cache.raw_hash(symbol)
        cache.close()
        restarted = MarketContextCache(path)
        if restarted.raw_hash(symbol) != final_hash:
            failures.append("incremental:restart_hash")
        restarted.close()
    source = inspect.getsource(QwenContextShadow.run_once)
    if ".jsonl" in source or "read_text" in source:
        failures.append("incremental:minute_path_full_scan")
    playbook_epochs = {"structural": "S1", "playbook_contract": "P1"}
    pending = [
        {
            "playbook_id": "PB-H1-HIGH",
            "level_id": "H1_PREVIOUS_HIGH",
            "evidence_ids": ["H1_PREVIOUS_HIGH", "candle:H1:1"],
        }
    ]
    valid_playbook_response = {
        "acknowledged_epochs": playbook_epochs,
        "interpretations": {
            "PB-H1-HIGH": {
                "level_id": "H1_PREVIOUS_HIGH",
                "buy_condition": "closed acceptance above H1_PREVIOUS_HIGH",
                "sell_condition": "rejection closing back below H1_PREVIOUS_HIGH",
                "missing_evidence": ["closed response"],
                "evidence_ids": ["H1_PREVIOUS_HIGH"],
            }
        },
        "evidence_ids": ["H1_PREVIOUS_HIGH"],
    }
    valid, _ = ContextValidator.validate_playbook_interpretation(
        valid_playbook_response, playbook_epochs, pending
    )
    if not valid:
        failures.append("incremental:valid_playbook_contract_rejected")
    corrupted = json.loads(canonical_json(valid_playbook_response))
    corrupted["interpretations"]["PB-H1-HIGH"]["level_id"] = "H4_PREVIOUS_LOW"
    corrupted_valid, _ = ContextValidator.validate_playbook_interpretation(
        corrupted, playbook_epochs, pending
    )
    if corrupted_valid:
        failures.append("incremental:corrupt_playbook_mapping_accepted")
    active_time = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)
    fresh_m1 = fixture_candle(
        symbol, "M1", active_time - timedelta(minutes=1), 4000
    )
    stale_m1 = fixture_candle(
        symbol, "M1", active_time - timedelta(minutes=5), 4000
    )
    if ContextValidator._active_freshness_failure(
        active_time, "M1", [fresh_m1]
    ):
        failures.append("incremental:active_fresh_candle_rejected")
    if not ContextValidator._active_freshness_failure(
        active_time, "M1", [stale_m1]
    ):
        failures.append("incremental:active_stale_candle_accepted")
    off_session = active_time.replace(hour=22)
    if ContextValidator._active_freshness_failure(
        off_session, "M1", [stale_m1]
    ):
        failures.append("incremental:off_session_gap_rejected")
    return {"passed": not failures, "failures": failures}


def latest_readiness(
    symbol: str = "XAUUSDr", path: Path | str = DEFAULT_DB
) -> dict | None:
    try:
        cache = MarketContextCache(path)
        try:
            return cache.latest_manifest(symbol)
        finally:
            cache.close()
    except (OSError, sqlite3.Error):
        return None


def latest_entry_context(
    symbol: str = "XAUUSDr",
    path: Path | str = DEFAULT_DB,
    *,
    now: datetime | None = None,
) -> dict:
    """Return the current cache-qualified packet permitted to reach entry Qwen."""
    checked_at = as_utc(now or utc_now())
    cache = MarketContextCache(path)
    try:
        manifest = cache.latest_manifest(symbol)
        if not manifest or manifest.get("status") != "ready":
            return {
                "status": "blocked",
                "reason": "cache_readiness_not_ready",
                "failures": (manifest or {}).get("failures", ["readiness_missing"]),
            }
        objects = {
            name: cache.object(name, symbol)
            for name in ("structural", "levels", "session", "playbooks", "minute")
        }
        missing = [name for name, value in objects.items() if not value]
        if missing:
            return {
                "status": "blocked",
                "reason": "cache_object_missing",
                "failures": [f"entry_cache:{name}:missing" for name in missing],
            }
        compatible = manifest.get("compatible_epochs", {})
        epoch_failures = [
            f"entry_cache:{name}:epoch_mismatch"
            for name, value in objects.items()
            if value["cache_epoch"] != compatible.get(name)
        ]
        minute = objects["minute"]
        minute_soft_ok = False
        if minute.get("expires_at_utc") and as_utc(minute["expires_at_utc"]) < checked_at:
            # Soft-extend only when the closed M1 in the packet is still the
            # latest completed M1. A new M1 requires a rebuilt minute packet.
            closed_m1_id = (minute.get("payload") or {}).get("closed_m1", {}).get("id")
            latest_m1 = cache.latest_completed(symbol, "M1", 1)
            latest_m1_id = latest_m1[-1]["evidence_id"] if latest_m1 else None
            if closed_m1_id and closed_m1_id == latest_m1_id:
                minute_soft_ok = True
            else:
                epoch_failures.append("entry_cache:minute:expired")
        if epoch_failures:
            return {
                "status": "blocked",
                "reason": "cache_provenance_invalid",
                "failures": epoch_failures,
            }

        structure = objects["structural"]
        levels = objects["levels"]
        session = objects["session"]
        playbooks = objects["playbooks"]
        level_rows = levels["payload"].get("levels", [])
        recent_closed = {}
        for timeframe, count in (("M1", 5), ("M5", 5), ("M15", 3), ("M30", 3)):
            rows = cache.latest_completed(symbol, timeframe, count)
            recent_closed[timeframe] = [
                {
                    key: row[key]
                    for key in (
                        "evidence_id", "open_time_utc", "close_time_utc",
                        "open", "high", "low", "close", "tick_volume",
                    )
                }
                for row in rows
            ]
        known_evidence = set()
        known_evidence.update(row["level_id"] for row in level_rows)
        for timeframe in structure["payload"].get("timeframe_location", {}).values():
            known_evidence.update(timeframe.get("evidence_ids") or [])
        for playbook in playbooks["payload"].get("playbooks", []):
            known_evidence.update(playbook.get("evidence_ids") or [])
        for rows in recent_closed.values():
            known_evidence.update(row["evidence_id"] for row in rows)
        closed_m1_id = minute["payload"].get("closed_m1", {}).get("id")
        if closed_m1_id:
            known_evidence.add(closed_m1_id)
        session_payload = session["payload"]
        return {
            "status": "ready",
            "validated_at_utc": manifest["validated_at_utc"],
            "decision_time_utc": minute["payload"].get("decision_time_utc"),
            "expires_at_utc": minute.get("expires_at_utc"),
            "minute_ttl_soft_ok": minute_soft_ok,
            "epochs": {
                "structural": structure["cache_epoch"],
                "levels": levels["cache_epoch"],
                "session": session["cache_epoch"],
                "playbooks": playbooks["cache_epoch"],
                "minute": minute["cache_epoch"],
            },
            "model_digest": manifest.get("model", {}).get("digest"),
            "structure": structure["payload"],
            "session": {
                key: session_payload.get(key)
                for key in (
                    "trading_date_utc",
                    "session",
                    "session_end_utc",
                    "trade_permitted",
                    "asia_high",
                    "asia_low",
                    "asia_bias",
                    "asia_relation",
                )
            },
            "playbooks": playbooks["payload"].get("playbooks", []),
            "minute": minute["payload"],
            "recent_closed": recent_closed,
            "levels": level_rows,
            "known_evidence_ids": sorted(known_evidence),
        }
    finally:
        cache.close()


def get_cached_completed_bars(
    symbol: str | None = None,
    timeframe: str = "M1",
    count: int = 120,
    path: Path | str = DEFAULT_DB,
) -> list[dict]:
    """Closed bars from the context SQLite cache. No MT5 call."""
    symbol = symbol or "XAUUSDr"
    try:
        cache = MarketContextCache(path)
        try:
            rows = cache.latest_completed(symbol, timeframe, count)
        finally:
            cache.close()
    except (OSError, sqlite3.Error):
        return []
    out = []
    for row in rows:
        out.append(
            {
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "open": float(row["open"]),
                "evidence_id": row.get("evidence_id"),
                "open_time_utc": row.get("open_time_utc"),
                "close_time_utc": row.get("close_time_utc"),
                "tick_volume": row.get("tick_volume"),
            }
        )
    return out


def get_cached_m1_bars(
    symbol: str | None = None,
    count: int = 120,
    path: Path | str = DEFAULT_DB,
) -> list[dict]:
    """M1 closed bars for ATR / regime. No MT5 call."""
    return get_cached_completed_bars(symbol, "M1", count, path)


def run_service(args: argparse.Namespace) -> None:
    handler = logging.handlers.TimedRotatingFileHandler(
        filename=LOG_DIR / "market-context-cache.log", when="midnight", encoding="utf-8"
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    source = MT5MarketSource(args.symbol)
    source.connect()
    cache = MarketContextCache(args.db)
    ollama = OllamaClient(args.model)
    try:
        shadow = QwenContextShadow(cache, source, ollama, Path(args.store_root))
        while True:
            try:
                with context_cycle_lock():
                    manifest = shadow.run_once(
                        run_qwen=not args.no_qwen,
                        benchmark_minute=not args.no_minute_benchmark,
                    )
                print(json.dumps(manifest, indent=2), flush=True)
                logging.info(
                    "Context cycle status=%s failures=%s",
                    manifest["status"],
                    manifest["failures"],
                )
            except Exception:
                logging.exception("Context shadow cycle failed")
                if args.once:
                    raise
            if args.once:
                return
            time.sleep(max(1, args.interval))
    finally:
        cache.close()
        source.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="XAUUSDr")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-qwen", action="store_true")
    parser.add_argument("--no-minute-benchmark", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.self_test:
        result = run_incremental_self_test()
        print(json.dumps(result, indent=2))
        if not result["passed"]:
            raise SystemExit(1)
        return
    run_service(args)


if __name__ == "__main__":
    main()
