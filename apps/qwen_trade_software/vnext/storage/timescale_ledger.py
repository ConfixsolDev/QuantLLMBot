"""Production TimescaleDB adapter for the clean-room V2 event ledger."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vnext_event_ledger (
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    pair TEXT NOT NULL,
    observed_at_utc TIMESTAMPTZ NOT NULL,
    confirmed_at_utc TIMESTAMPTZ,
    effective_from_utc TIMESTAMPTZ,
    invalidated_at_utc TIMESTAMPTZ,
    source TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    PRIMARY KEY (event_id, observed_at_utc)
);
SELECT create_hypertable('vnext_event_ledger', 'observed_at_utc', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS vnext_event_ledger_pair_time
    ON vnext_event_ledger(pair, observed_at_utc DESC);
"""


class TimescaleEventLedger:
    """Idempotent durable ledger; it never chooses a strategy or trade."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("Timescale DSN is required")
        self.dsn = dsn

    def _connect(self):
        import psycopg
        return psycopg.connect(self.dsn, connect_timeout=3)

    def ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)

    def append(self, event: EventEnvelope, *, frontier: TimeFrontier | None = None) -> bool:
        if frontier is not None:
            event.validate_against(frontier)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT content_hash FROM vnext_event_ledger WHERE event_id=%s LIMIT 1",
                (event.event_id,),
            )
            row = cursor.fetchone()
            if row is not None:
                if str(row[0]) != event.content_hash:
                    raise ValueError(f"event ID collision: {event.event_id}")
                return False
            cursor.execute(
                "INSERT INTO vnext_event_ledger "
                "(event_id,event_type,pair,observed_at_utc,confirmed_at_utc," 
                "effective_from_utc,invalidated_at_utc,source,schema_version," 
                "content_hash,payload_json) VALUES "
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) "
                "ON CONFLICT (event_id, observed_at_utc) DO NOTHING",
                (event.event_id, event.event_type, event.pair,
                 event.observed_at_utc, event.confirmed_at_utc,
                 event.effective_from_utc, event.invalidated_at_utc,
                 event.source, event.schema_version, event.content_hash,
                 json.dumps(dict(event.payload), sort_keys=True, default=str)),
            )
            return cursor.rowcount == 1

    def count(self, *, pair: str | None = None) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            if pair is None:
                cursor.execute("SELECT COUNT(*) FROM vnext_event_ledger")
            else:
                cursor.execute("SELECT COUNT(*) FROM vnext_event_ledger WHERE pair=%s", (pair,))
            return int(cursor.fetchone()[0])

    def latest_magic_positions(self, magic_number: int) -> list[dict[str, Any]]:
        """Read the latest durable broker-truth snapshot for one magic namespace."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM vnext_event_ledger WHERE event_type='MAGIC_POSITION_SNAPSHOT' "
                "AND payload_json->>'magic_number'=%s ORDER BY observed_at_utc DESC LIMIT 1",
                (str(magic_number),),
            )
            row = cursor.fetchone()
        if row is None:
            return []
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        positions = payload.get("positions", ()) if isinstance(payload, dict) else ()
        return [dict(position) for position in positions if isinstance(position, dict)]

    def latest_news_calendar(self, day_utc: str) -> dict[str, Any] | None:
        """Return the latest durable calendar payload for one UTC day."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM vnext_event_ledger "
                "WHERE event_type='NEWS_CALENDAR_REFRESHED' "
                "AND payload_json->>'day_utc'=%s ORDER BY observed_at_utc DESC LIMIT 1",
                (day_utc,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return dict(payload) if isinstance(payload, dict) else None

    def latest_timeframe_expectation(self, *, pair: str, strategy_id: str,
                                     target_close_utc: str) -> dict[str, Any] | None:
        """Read the immutable expectation that was recorded before one M15 close."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_id,payload_json FROM vnext_event_ledger "
                "WHERE event_type='TIMEFRAME_EXPECTATION_RECORDED' AND pair=%s "
                  "AND payload_json->>'strategy_id'=%s "
                  "AND (payload_json->>'target_close_utc')::timestamptz=%s::timestamptz "
                "ORDER BY observed_at_utc DESC LIMIT 1",
                (pair, strategy_id, target_close_utc),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        return {"event_id": str(row[0]), **dict(payload)}

    def latest_completed_candles(self, *, pair: str, timeframes: tuple[str, ...],
                                 as_of_utc: datetime) -> dict[str, dict[str, Any]]:
        """Return the latest completed durable candle per timeframe as-of a frontier."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT DISTINCT ON (timeframe) timeframe,open_time_utc,close_time_utc,"
                "open,high,low,close,tick_volume,spread,source FROM completed_candles "
                "WHERE symbol=%s AND timeframe = ANY(%s) AND close_time_utc <= %s "
                "ORDER BY timeframe,close_time_utc DESC",
                (pair, list(timeframes), as_of_utc),
            )
            rows = cursor.fetchall()
        return {str(row[0]): {"timeframe": row[0], "start_utc": row[1].isoformat(),
                              "end_utc": row[2].isoformat(), "open": row[3], "high": row[4],
                              "low": row[5], "close": row[6], "tick_volume": row[7],
                              "spread": row[8], "source": row[9]} for row in rows}
