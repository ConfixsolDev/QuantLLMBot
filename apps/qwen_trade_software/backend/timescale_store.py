"""PostgreSQL/TimescaleDB implementation of the intelligence store subset.

The adapter is intentionally dependency-lazy so existing SQLite tests and
offline tools continue to run. Set QWEN_INTELLIGENCE_BACKEND=timescale and
QWEN_TIMESCALE_DSN before using it in the live intelligence service.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

from market_intelligence.store import canonical, digest


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS intelligence_events (
    event_time_utc TIMESTAMPTZ NOT NULL,
    event_id TEXT NOT NULL,
    sequence BIGSERIAL NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    event_type TEXT NOT NULL,
    evidence_id TEXT,
    payload_json JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    recorded_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (event_time_utc, event_id)
);
SELECT create_hypertable('intelligence_events', 'event_time_utc', if_not_exists => TRUE);
CREATE UNIQUE INDEX IF NOT EXISTS intelligence_events_event_id ON intelligence_events(event_id, event_time_utc);
CREATE INDEX IF NOT EXISTS intelligence_event_lookup ON intelligence_events(symbol, timeframe, event_time_utc DESC);
CREATE TABLE IF NOT EXISTS structure_projections (
    symbol TEXT NOT NULL, timeframe TEXT NOT NULL, state_json JSONB NOT NULL,
    structure_epoch TEXT NOT NULL, last_event_id TEXT, updated_at_utc TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(symbol, timeframe)
);
CREATE TABLE IF NOT EXISTS retrieval_audit (
    request_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, requested_at_utc TIMESTAMPTZ NOT NULL,
    request_json JSONB NOT NULL, result_json JSONB NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graph_projection_outbox (
    event_id TEXT NOT NULL, event_time_utc TIMESTAMPTZ NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, enqueued_at_utc TIMESTAMPTZ NOT NULL,
    projected_at_utc TIMESTAMPTZ, PRIMARY KEY(event_id, event_time_utc)
);
CREATE TABLE IF NOT EXISTS trade_journal (
    proposal_id TEXT PRIMARY KEY, execution_id TEXT NOT NULL, symbol TEXT NOT NULL,
    exit_time_utc TIMESTAMPTZ NOT NULL, payload_json JSONB NOT NULL,
    source_hash TEXT NOT NULL, updated_at_utc TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS trade_journal_exit_time ON trade_journal(exit_time_utc DESC);
"""


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class TimescaleIntelligenceStore:
    """Small compatible store for the live market-intelligence service."""

    def __init__(self, dsn: str, *, connection_factory: Callable | None = None) -> None:
        try:
            if connection_factory is None:
                from psycopg_pool import ConnectionPool
                self.pool = ConnectionPool(conninfo=dsn, min_size=1, max_size=8,
                                           kwargs={"connect_timeout": 3}, open=True)
            else:
                self.pool = connection_factory(dsn)
        except Exception as exc:
            raise RuntimeError("TimescaleDB connection unavailable") from exc
        self.path = None

    def schema(self) -> None:
        with self.pool.connection() as connection:
            with connection.cursor() as cur:
                cur.execute(SCHEMA_SQL)

    def append_event(self, event: dict) -> bool:
        payload = event.get("payload") or {}
        now = datetime.now(timezone.utc)
        with self.pool.connection() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO intelligence_events(event_time_utc,event_id,symbol,timeframe,event_type,evidence_id,payload_json,payload_hash,recorded_at_utc) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING",
                    (_utc(event["event_time_utc"]), event["event_id"], event["symbol"],
                     event["timeframe"], event["event_type"], event.get("evidence_id"),
                     canonical(payload), digest(payload), now),
                )
                inserted = cur.rowcount == 1
                if inserted:
                    cur.execute(
                        "INSERT INTO graph_projection_outbox(event_id,event_time_utc,enqueued_at_utc) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (event["event_id"], _utc(event["event_time_utc"]), now),
                    )
                return inserted

    def append_events(self, events: list[dict]) -> int:
        """Append a migration batch in one transaction while preserving idempotency."""
        inserted = 0
        now = datetime.now(timezone.utc)
        with self.pool.connection() as connection, connection.cursor() as cur:
            for event in events:
                payload = event.get("payload") or {}
                event_time = _utc(event["event_time_utc"])
                cur.execute(
                    "INSERT INTO intelligence_events(event_time_utc,event_id,symbol,timeframe,event_type,evidence_id,payload_json,payload_hash,recorded_at_utc) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT DO NOTHING",
                    (event_time, event["event_id"], event["symbol"], event["timeframe"],
                     event["event_type"], event.get("evidence_id"), canonical(payload),
                     digest(payload), now),
                )
                if cur.rowcount == 1:
                    inserted += 1
                    cur.execute(
                        "INSERT INTO graph_projection_outbox(event_id,event_time_utc,enqueued_at_utc) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                        (event["event_id"], event_time, now),
                    )
        return inserted

    def projection(self, symbol: str, timeframe: str) -> dict | None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT state_json,structure_epoch,last_event_id,updated_at_utc FROM structure_projections WHERE symbol=%s AND timeframe=%s", (symbol, timeframe))
            row = cur.fetchone()
        if not row:
            return None
        state, epoch, event_id, updated = row
        state = state if isinstance(state, dict) else json.loads(state)
        return {**state, "structure_epoch": epoch, "last_event_id": event_id, "updated_at_utc": updated.isoformat()}

    def put_projection(self, symbol: str, timeframe: str, state: dict, last_event_id: str | None) -> dict:
        epoch = f"structure-{symbol}-{timeframe}-{digest(state)}"
        now = datetime.now(timezone.utc)
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(
                "INSERT INTO structure_projections VALUES(%s,%s,%s::jsonb,%s,%s,%s) ON CONFLICT(symbol,timeframe) DO UPDATE SET state_json=EXCLUDED.state_json,structure_epoch=EXCLUDED.structure_epoch,last_event_id=EXCLUDED.last_event_id,updated_at_utc=EXCLUDED.updated_at_utc",
                (symbol, timeframe, canonical(state), epoch, last_event_id, now),
            )
        return {**state, "structure_epoch": epoch, "updated_at_utc": now.isoformat()}

    def projections(self, symbol: str) -> dict[str, dict]:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT timeframe FROM structure_projections WHERE symbol=%s", (symbol,))
            timeframes = [row[0] for row in cur.fetchall()]
        return {tf: self.projection(symbol, tf) for tf in timeframes if self.projection(symbol, tf) is not None}

    def events(self, symbol: str, timeframe: str | None = None, limit: int = 100) -> list[dict]:
        clauses, params = ["symbol=%s"], [symbol]
        if timeframe:
            clauses.append("timeframe=%s"); params.append(timeframe)
        params.append(max(1, min(int(limit), 5000)))
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(f"SELECT event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,payload_json FROM intelligence_events WHERE {' AND '.join(clauses)} ORDER BY event_time_utc DESC,sequence DESC LIMIT %s", tuple(params))
            rows = cur.fetchall()
        result = []
        for event_id, sym, tf, kind, event_time, evidence, payload in reversed(rows):
            result.append({"event_id": event_id, "symbol": sym, "timeframe": tf, "event_type": kind, "event_time_utc": event_time.isoformat(), "evidence_id": evidence, "payload": payload if isinstance(payload, dict) else json.loads(payload)})
        return result

    def event(self, event_id: str) -> dict | None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,payload_json,payload_hash FROM intelligence_events WHERE event_id=%s ORDER BY event_time_utc DESC LIMIT 1", (event_id,))
            row = cur.fetchone()
        if not row:
            return None
        event, symbol, tf, kind, when, evidence, payload, payload_hash = row
        return {"event_id": event, "symbol": symbol, "timeframe": tf, "event_type": kind, "event_time_utc": when.isoformat(), "evidence_id": evidence, "payload": payload if isinstance(payload, dict) else json.loads(payload), "payload_hash": payload_hash}

    def last_event_id(self, symbol: str, timeframe: str) -> str | None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT last_event_id FROM structure_projections WHERE symbol=%s AND timeframe=%s", (symbol, timeframe))
            row = cur.fetchone()
        return row[0] if row else None

    def completed_candles(self, symbol: str, timeframe: str, limit: int = 500) -> list[dict]:
        rows = self.events(symbol, timeframe, limit)
        result = []
        for row in rows:
            if row["event_type"] != "candle_closed":
                continue
            payload = row["payload"]
            if all(payload.get(key) is not None for key in ("open", "high", "low", "close")):
                result.append({"event_time_utc": row["event_time_utc"], "evidence_id": row["evidence_id"], **payload})
        return result

    def rebuild(self, reducer: Callable) -> int:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT DISTINCT symbol,timeframe FROM structure_projections")
            keys = cur.fetchall()
            cur.execute("SELECT event_id,symbol,timeframe,event_type,event_time_utc,evidence_id,payload_json FROM intelligence_events ORDER BY event_time_utc,sequence")
            rows = cur.fetchall()
            cur.execute("DELETE FROM structure_projections")
        states: dict[tuple[str, str], tuple[dict, str]] = {}
        count = 0
        for event_id, symbol, tf, kind, when, evidence, payload in rows:
            event = {"event_id": event_id, "symbol": symbol, "timeframe": tf, "event_type": kind, "event_time_utc": when.isoformat(), "evidence_id": evidence, "payload": payload if isinstance(payload, dict) else json.loads(payload)}
            prior = states.get((symbol, tf), (None, None))[0]
            states[(symbol, tf)] = (reducer(prior, event), event_id)
            count += 1
        for (symbol, tf), (state, event_id) in states.items():
            self.put_projection(symbol, tf, state, event_id)
        return count

    def graph_outbox_batch(self, limit: int = 200, max_attempts: int = 8) -> list[dict]:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT o.event_id,o.event_time_utc,o.attempts,e.sequence,e.symbol,e.timeframe,e.event_type,e.evidence_id,e.payload_json,e.payload_hash,e.recorded_at_utc FROM graph_projection_outbox o JOIN intelligence_events e ON e.event_id=o.event_id AND e.event_time_utc=o.event_time_utc WHERE o.status='pending' AND o.attempts < %s ORDER BY e.event_time_utc,e.sequence LIMIT %s", (max(1, int(max_attempts)), max(1, min(int(limit), 10000))))
            rows = cur.fetchall()
        return [{"event_id": r[0], "event_time_utc": r[1].isoformat(), "attempts": r[2], "sequence": r[3], "symbol": r[4], "timeframe": r[5], "event_type": r[6], "evidence_id": r[7], "payload": r[8] if isinstance(r[8], dict) else json.loads(r[8]), "payload_hash": r[9], "recorded_at_utc": r[10].isoformat(), "previous_event_id": None} for r in rows]

    def mark_graph_projected(self, event_ids: list[str]) -> None:
        if not event_ids:
            return
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("UPDATE graph_projection_outbox SET status='projected',projected_at_utc=%s WHERE event_id = ANY(%s)", (datetime.now(timezone.utc), event_ids))

    def mark_graph_failed(self, event_ids: list[str], error: str) -> None:
        if not event_ids:
            return
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("UPDATE graph_projection_outbox SET attempts=attempts+1,last_error=%s WHERE event_id = ANY(%s)", (str(error)[:1000], event_ids))

    def recent_retrievals(self, limit: int = 10) -> list[dict]:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT request_id,symbol,requested_at_utc,request_json,result_json,status FROM retrieval_audit ORDER BY requested_at_utc DESC LIMIT %s", (max(1, min(int(limit), 100)),))
            rows = cur.fetchall()
        return [{"request_id": row[0], "symbol": row[1], "requested_at_utc": row[2].isoformat(), "request": row[3], "result": row[4], "status": row[5]} for row in rows]

    def upsert_trade_journal(self, journal: dict) -> None:
        payload = canonical(journal)
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(
                "INSERT INTO trade_journal(proposal_id,execution_id,symbol,exit_time_utc,payload_json,source_hash,updated_at_utc) "
                "VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT(proposal_id) DO UPDATE SET execution_id=EXCLUDED.execution_id,symbol=EXCLUDED.symbol,exit_time_utc=EXCLUDED.exit_time_utc,payload_json=EXCLUDED.payload_json,source_hash=EXCLUDED.source_hash,updated_at_utc=EXCLUDED.updated_at_utc",
                (journal["proposal_id"], journal["execution_id"], journal["symbol"], _utc(journal["exit_time_utc"]), payload, journal.get("source_hash", ""), datetime.now(timezone.utc)),
            )

    def pending_trade_journals(self, limit: int = 10) -> list[dict]:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("SELECT payload_json FROM trade_journal WHERE COALESCE(payload_json->>'qwen_analysis_status','pending') IN ('pending','retry') ORDER BY exit_time_utc LIMIT %s", (max(1, min(int(limit), 100)),))
            rows = cur.fetchall()
        return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]

    def trade_journals(self, limit: int = 100, *, start_utc: str | None = None, end_utc: str | None = None) -> list[dict]:
        clauses, params = [], []
        if start_utc:
            clauses.append("exit_time_utc >= %s"); params.append(_utc(start_utc))
        if end_utc:
            clauses.append("exit_time_utc < %s"); params.append(_utc(end_utc))
        params.append(max(1, min(int(limit), 10000)))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(f"SELECT payload_json FROM trade_journal{where} ORDER BY exit_time_utc DESC LIMIT %s", tuple(params))
            rows = cur.fetchall()
        return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]

    def update_trade_qwen_analysis(self, proposal_id: str, analysis: dict | None, status: str, model: str) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(
                "UPDATE trade_journal SET payload_json=jsonb_set(jsonb_set(jsonb_set(payload_json,'{qwen_analysis_json}',%s::jsonb),'{qwen_analysis_status}',to_jsonb(%s::text)),'{qwen_analysis_model}',to_jsonb(%s::text)),updated_at_utc=%s WHERE proposal_id=%s",
                (canonical(analysis), status, model, datetime.now(timezone.utc), proposal_id),
            )

    def record_retrieval(self, request_id: str, symbol: str, request: dict, result: dict, status: str) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO retrieval_audit VALUES(%s,%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT(request_id) DO NOTHING", (request_id, symbol, datetime.now(timezone.utc), canonical(request), canonical(result), status))

    def close(self) -> None:
        self.pool.close()

    def counts(self) -> dict[str, int]:
        """Return durable row counts used by the cutover parity gate."""
        tables = ("intelligence_events", "structure_projections", "retrieval_audit", "trade_journal")
        with self.pool.connection() as connection, connection.cursor() as cur:
            return {table: int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}
