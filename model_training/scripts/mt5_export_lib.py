"""Shared MT5 historical export helpers for v003 dataset Layer 0."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "apps" / "qwen_trade_software" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import MetaTrader5 as mt5  # noqa: E402

from review_shared import connect_mt5  # noqa: E402

NY = ZoneInfo("America/New_York")

TIMEFRAME_SECONDS = {
    "M1": 60,
    "M5": 300,
    "M15": 900,
    "M30": 1800,
    "H1": 3600,
    "H4": 14400,
}

MT5_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1,
    "H1": mt5.TIMEFRAME_H1,
}

CANDLE_COLUMNS = [
    "symbol",
    "timeframe",
    "time_utc",
    "open",
    "high",
    "low",
    "close",
    "tick_volume",
    "spread",
    "real_volume",
    "source",
    "derived_from",
    "bar_timezone",
]

TICK_COLUMNS = [
    "symbol",
    "time_utc",
    "time_msc",
    "bid",
    "ask",
    "last",
    "volume",
    "flags",
    "source",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def month_key(value: datetime) -> str:
    return value.strftime("%Y-%m")


def day_key(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def normalize_rate(symbol: str, timeframe: str, rate: Any, *, derived_from: str = "MT5", bar_timezone: str = "UTC") -> dict[str, Any]:
    opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "time_utc": iso_utc(opened),
        "open": float(rate["open"]),
        "high": float(rate["high"]),
        "low": float(rate["low"]),
        "close": float(rate["close"]),
        "tick_volume": int(rate["tick_volume"]),
        "spread": int(rate["spread"]),
        "real_volume": int(rate["real_volume"]),
        "source": "MT5",
        "derived_from": derived_from,
        "bar_timezone": bar_timezone,
    }


def _tick_field(tick: Any, name: str, default: Any = 0) -> Any:
    try:
        return tick[name]
    except (TypeError, KeyError, IndexError):
        return getattr(tick, name, default)


def normalize_tick(symbol: str, tick: Any) -> dict[str, Any]:
    time_msc = int(_tick_field(tick, "time_msc", 0) or 0)
    tick_time = int(_tick_field(tick, "time", 0) or 0)
    ts = time_msc / 1000 if time_msc else tick_time
    opened = datetime.fromtimestamp(ts, timezone.utc)
    return {
        "symbol": symbol,
        "time_utc": iso_utc(opened),
        "time_msc": time_msc or int(ts * 1000),
        "bid": float(_tick_field(tick, "bid", 0.0)),
        "ask": float(_tick_field(tick, "ask", 0.0)),
        "last": float(_tick_field(tick, "last", 0.0) or 0.0),
        "volume": int(_tick_field(tick, "volume", 0) or 0),
        "flags": int(_tick_field(tick, "flags", 0) or 0),
        "source": "MT5",
    }


def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Symbol {symbol} not found: {mt5.last_error()}")
    if not info.visible and not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Could not select {symbol}: {mt5.last_error()}")


def probe_earliest_bar(symbol: str, timeframe: str) -> datetime | None:
    mt5_tf = MT5_TIMEFRAMES.get(timeframe)
    if mt5_tf is None:
        raise ValueError(f"Unsupported probe timeframe: {timeframe}")

    if timeframe in {"M1", "H1"}:
        return _probe_earliest_via_pos(symbol, mt5_tf)

    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = utc_now()
    rates = mt5.copy_rates_range(symbol, mt5_tf, start, end)
    if rates is None or len(rates) == 0:
        return None
    return datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc)


def _bar_time_at_pos(symbol: str, mt5_tf: int, pos: int) -> datetime | None:
    rates = mt5.copy_rates_from_pos(symbol, mt5_tf, pos, 1)
    if rates is None or len(rates) == 0:
        return None
    return datetime.fromtimestamp(int(rates[0]["time"]), timezone.utc)


def _probe_earliest_via_pos(symbol: str, mt5_tf: int, max_search: int = 200_000) -> datetime | None:
    lo, hi = 0, max_search
    best: datetime | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        ts = _bar_time_at_pos(symbol, mt5_tf, mid)
        if ts is None:
            hi = mid - 1
        else:
            best = ts
            lo = mid + 1
    return best


def copy_m1_via_positions(
    symbol: str,
    start: datetime,
    end: datetime,
    *,
    chunk: int = 5000,
    max_search: int = 200_000,
) -> list[dict[str, Any]]:
    mt5_tf = MT5_TIMEFRAMES["M1"]
    lo, hi = 0, max_search
    max_pos = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _bar_time_at_pos(symbol, mt5_tf, mid) is None:
            hi = mid - 1
        else:
            max_pos = mid
            lo = mid + 1

    rows: list[dict[str, Any]] = []
    pos = max_pos
    while pos >= 0:
        count = min(chunk, pos + 1)
        start_pos = pos - count + 1
        rates = mt5.copy_rates_from_pos(symbol, mt5_tf, start_pos, count)
        if rates is None:
            err = mt5.last_error()
            raise RuntimeError(f"copy_rates_from_pos M1 pos={start_pos} count={count} failed: {err}")
        for rate in rates:
            opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
            if opened < start:
                continue
            if opened >= end:
                continue
            rows.append(normalize_rate(symbol, "M1", rate))
        pos = start_pos - 1
    rows.sort(key=lambda item: item["time_utc"])
    return rows


def probe_earliest_tick(symbol: str) -> datetime | None:
    start = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    while end <= utc_now():
        ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
        if ticks is not None and len(ticks) > 0:
            first = ticks[0]
            time_msc = int(_tick_field(first, "time_msc", 0) or 0)
            tick_time = int(_tick_field(first, "time", 0) or 0)
            ts = time_msc / 1000 if time_msc else tick_time
            return datetime.fromtimestamp(ts, timezone.utc)
        start = end
        end = min(end + timedelta(days=30), utc_now())
    return None


def copy_rates_chunk(symbol: str, timeframe: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    mt5_tf = MT5_TIMEFRAMES[timeframe]
    rates = mt5.copy_rates_range(symbol, mt5_tf, start, end)
    if rates is None:
        err = mt5.last_error()
        raise RuntimeError(f"copy_rates_range {timeframe} {start}..{end} failed: {err}")
    return [
        normalize_rate(symbol, timeframe, rate)
        for rate in sorted(rates, key=lambda item: int(item["time"]))
    ]


def copy_ticks_chunk(symbol: str, start: datetime, end: datetime, *, max_ticks: int = 100_000) -> list[dict[str, Any]]:
    if start >= end:
        return []
    ticks = mt5.copy_ticks_range(symbol, start, end, mt5.COPY_TICKS_ALL)
    if ticks is None:
        err = mt5.last_error()
        raise RuntimeError(f"copy_ticks_range {start}..{end} failed: {err}")
    if len(ticks) >= max_ticks and (end - start) > timedelta(seconds=1):
        mid = start + (end - start) / 2
        left = copy_ticks_chunk(symbol, start, mid, max_ticks=max_ticks)
        right = copy_ticks_chunk(symbol, mid, end, max_ticks=max_ticks)
        return left + right
    return [normalize_tick(symbol, tick) for tick in ticks]


def write_csv(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def append_log(log_path: Path, record: dict[str, Any]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def read_candles_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def floor_utc(ts: datetime, seconds: int) -> datetime:
    epoch = int(ts.timestamp())
    floored = epoch - (epoch % seconds)
    return datetime.fromtimestamp(floored, timezone.utc)


def resample_utc(rows: list[dict[str, Any]], target_tf: str, *, derived_from: str) -> list[dict[str, Any]]:
    if not rows:
        return []
    seconds = TIMEFRAME_SECONDS[target_tf]
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ts = parse_utc(row["time_utc"])
        buckets[floor_utc(ts, seconds)].append(row)

    out: list[dict[str, Any]] = []
    for bucket_start in sorted(buckets):
        group = sorted(buckets[bucket_start], key=lambda item: item["time_utc"])
        first = group[0]
        out.append(
            {
                "symbol": first["symbol"],
                "timeframe": target_tf,
                "time_utc": iso_utc(bucket_start),
                "open": float(first["open"]),
                "high": max(float(item["high"]) for item in group),
                "low": min(float(item["low"]) for item in group),
                "close": float(group[-1]["close"]),
                "tick_volume": sum(int(item["tick_volume"]) for item in group),
                "spread": int(group[-1]["spread"]),
                "real_volume": sum(int(item["real_volume"]) for item in group),
                "source": "derived",
                "derived_from": derived_from,
                "bar_timezone": "UTC",
            }
        )
    return out


def h4_ny_bucket_start(open_utc: datetime) -> datetime:
    ny = open_utc.astimezone(NY)
    bucket_hour = (ny.hour // 4) * 4
    bucket_ny = ny.replace(hour=bucket_hour, minute=0, second=0, microsecond=0)
    return bucket_ny.astimezone(timezone.utc)


def resample_h4_ny_from_h1(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    buckets: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        ts = parse_utc(row["time_utc"])
        buckets[h4_ny_bucket_start(ts)].append(row)

    out: list[dict[str, Any]] = []
    for bucket_start in sorted(buckets):
        group = sorted(buckets[bucket_start], key=lambda item: item["time_utc"])
        first = group[0]
        out.append(
            {
                "symbol": first["symbol"],
                "timeframe": "H4",
                "time_utc": iso_utc(bucket_start),
                "open": float(first["open"]),
                "high": max(float(item["high"]) for item in group),
                "low": min(float(item["low"]) for item in group),
                "close": float(group[-1]["close"]),
                "tick_volume": sum(int(item["tick_volume"]) for item in group),
                "spread": int(group[-1]["spread"]),
                "real_volume": sum(int(item["real_volume"]) for item in group),
                "source": "derived",
                "derived_from": "H1",
                "bar_timezone": "America/New_York",
            }
        )
    return out


@dataclass
class ExportStats:
    rows: int = 0
    files: int = 0
    skipped: int = 0


def month_range(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    cursor = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ranges: list[tuple[datetime, datetime]] = []
    while cursor < end:
        if cursor.month == 12:
            nxt = cursor.replace(year=cursor.year + 1, month=1)
        else:
            nxt = cursor.replace(month=cursor.month + 1)
        chunk_start = max(cursor, start)
        chunk_end = min(nxt, end)
        if chunk_start < chunk_end:
            ranges.append((chunk_start, chunk_end))
        cursor = nxt
    return ranges


def day_range(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0)
    ranges: list[tuple[datetime, datetime]] = []
    while cursor < end:
        nxt = cursor + timedelta(days=1)
        chunk_start = max(cursor, start)
        chunk_end = min(nxt, end)
        if chunk_start < chunk_end:
            ranges.append((chunk_start, chunk_end))
        cursor = nxt
    return ranges


def shutdown_mt5() -> None:
    mt5.shutdown()
