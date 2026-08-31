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
                "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)",
                (event.event_id, event.event_type, event.pair,
                 event.observed_at_utc, event.confirmed_at_utc,
                 event.effective_from_utc, event.invalidated_at_utc,
                 event.source, event.schema_version, event.content_hash,
                 json.dumps(dict(event.payload), sort_keys=True, default=str)),
            )
            return True

    def count(self, *, pair: str | None = None) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            if pair is None:
                cursor.execute("SELECT COUNT(*) FROM vnext_event_ledger")
            else:
                cursor.execute("SELECT COUNT(*) FROM vnext_event_ledger WHERE pair=%s", (pair,))
            return int(cursor.fetchone()[0])
