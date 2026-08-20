"""SQLite event ledger and materialized structure projections."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()[:20]


class IntelligenceStore:
    """Append-only evidence with replaceable views that can be replayed."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._schema()

    def _schema(self) -> None:
        with self.db:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS intelligence_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time_utc TEXT NOT NULL,
                    evidence_id TEXT,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    recorded_at_utc TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS intelligence_event_lookup
                    ON intelligence_events(symbol,timeframe,sequence);
                CREATE TABLE IF NOT EXISTS structure_projections (
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    structure_epoch TEXT NOT NULL,
                    last_event_id TEXT,
                    updated_at_utc TEXT NOT NULL,
                    PRIMARY KEY(symbol,timeframe)
                );
                CREATE TABLE IF NOT EXISTS retrieval_audit (
                    request_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    requested_at_utc TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    status TEXT NOT NULL
                );
            """)

    def append_event(self, event: dict) -> bool:
        payload = event.get("payload") or {}
        with self.lock, self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO intelligence_events "
                "(event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,"
                "payload_json,payload_hash,recorded_at_utc) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    event["event_id"], event["symbol"], event["timeframe"],
                    event["event_type"], event["event_time_utc"], event.get("evidence_id"),
                    canonical(payload), digest(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def events(self, symbol: str, timeframe: str | None = None, limit: int = 20) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        sql = "SELECT * FROM intelligence_events WHERE symbol=?"
        params: list[object] = [symbol]
        if timeframe:
            sql += " AND timeframe=?"
            params.append(timeframe)
        sql += " ORDER BY sequence DESC LIMIT ?"
        params.append(limit)
        rows = self.db.execute(sql, params).fetchall()
        return [
            {
                "event_id": row["event_id"], "symbol": row["symbol"],
                "timeframe": row["timeframe"], "event_type": row["event_type"],
                "event_time_utc": row["event_time_utc"],
                "evidence_id": row["evidence_id"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in reversed(rows)
        ]

    def put_projection(self, symbol: str, timeframe: str, state: dict, last_event_id: str | None) -> dict:
        epoch = f"structure-{symbol}-{timeframe}-{digest(state)}"
        now = datetime.now(timezone.utc).isoformat()
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO structure_projections VALUES (?,?,?,?,?,?) "
                "ON CONFLICT(symbol,timeframe) DO UPDATE SET state_json=excluded.state_json,"
                "structure_epoch=excluded.structure_epoch,last_event_id=excluded.last_event_id,"
                "updated_at_utc=excluded.updated_at_utc",
                (symbol, timeframe, canonical(state), epoch, last_event_id, now),
            )
        return {**state, "structure_epoch": epoch, "updated_at_utc": now}

    def projection(self, symbol: str, timeframe: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM structure_projections WHERE symbol=? AND timeframe=?",
            (symbol, timeframe),
        ).fetchone()
        if not row:
            return None
        return {
            **json.loads(row["state_json"]),
            "structure_epoch": row["structure_epoch"],
            "last_event_id": row["last_event_id"],
            "updated_at_utc": row["updated_at_utc"],
        }

    def projections(self, symbol: str) -> dict[str, dict]:
        rows = self.db.execute(
            "SELECT timeframe FROM structure_projections WHERE symbol=?", (symbol,)
        ).fetchall()
        return {row["timeframe"]: self.projection(symbol, row["timeframe"]) for row in rows}

    def record_retrieval(self, request_id: str, symbol: str, request: dict, result: dict, status: str) -> None:
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO retrieval_audit VALUES (?,?,?,?,?,?)",
                (request_id, symbol, datetime.now(timezone.utc).isoformat(),
                 canonical(request), canonical(result), status),
            )

    def recent_retrievals(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM retrieval_audit ORDER BY requested_at_utc DESC LIMIT ?",
            (max(1, min(limit, 50)),),
        ).fetchall()
        return [{"request_id": r["request_id"], "symbol": r["symbol"],
                 "requested_at_utc": r["requested_at_utc"], "status": r["status"],
                 "request": json.loads(r["request_json"]),
                 "result": json.loads(r["result_json"])} for r in rows]

    def rebuild(self, reducer) -> int:
        with self.lock, self.db:
            self.db.execute("DELETE FROM structure_projections")
            rows = self.db.execute("SELECT * FROM intelligence_events ORDER BY sequence").fetchall()
            states: dict[tuple[str, str], dict] = {}
            for row in rows:
                event = {"event_id": row["event_id"], "symbol": row["symbol"],
                         "timeframe": row["timeframe"], "event_type": row["event_type"],
                         "event_time_utc": row["event_time_utc"],
                         "evidence_id": row["evidence_id"],
                         "payload": json.loads(row["payload_json"])}
                key = (row["symbol"], row["timeframe"])
                states[key] = reducer(states.get(key), event)
                self.put_projection(*key, states[key], row["event_id"])
            return len(rows)
