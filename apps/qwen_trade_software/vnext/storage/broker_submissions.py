"""Durable broker idempotency registry in TimescaleDB."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS vnext_broker_submissions (
    order_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    result_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'SUBMITTED',
    created_at_utc TIMESTAMPTZ NOT NULL
)
"""


class TimescaleSubmissionStore:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("Timescale DSN is required")
        self.dsn = dsn

    def _connect(self):
        import psycopg
        return psycopg.connect(self.dsn, connect_timeout=3)

    def ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA)
            cursor.execute("ALTER TABLE vnext_broker_submissions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'SUBMITTED'")

    def claim(self, order_id: str, fingerprint: str) -> dict[str, Any] | None:
        """Atomically reserve an order; RESERVED means broker outcome is uncertain."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO vnext_broker_submissions(order_id,fingerprint,result_json,status,created_at_utc) "
                "VALUES (%s,%s,'{}'::jsonb,'RESERVED',%s) ON CONFLICT (order_id) DO NOTHING",
                (order_id, fingerprint, datetime.now(timezone.utc)),
            )
            cursor.execute("SELECT fingerprint,result_json,status FROM vnext_broker_submissions WHERE order_id=%s", (order_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        result = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        return {"fingerprint": str(row[0]), "result": result, "status": str(row[2])}

    def complete(self, order_id: str, fingerprint: str, result: dict[str, Any]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE vnext_broker_submissions SET result_json=%s::jsonb,status='SUBMITTED' WHERE order_id=%s AND fingerprint=%s",
                           (json.dumps(result, sort_keys=True, default=str), order_id, fingerprint))

    def release(self, order_id: str, fingerprint: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM vnext_broker_submissions WHERE order_id=%s AND fingerprint=%s AND status='RESERVED'",
                           (order_id, fingerprint))

    def get(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT fingerprint,result_json,status FROM vnext_broker_submissions WHERE order_id=%s", (order_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        result = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        return {"fingerprint": str(row[0]), "result": result, "status": str(row[2])}

    def put(self, order_id: str, fingerprint: str, result: dict[str, Any]) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO vnext_broker_submissions(order_id,fingerprint,result_json,status,created_at_utc) "
                "VALUES (%s,%s,%s::jsonb,%s,%s) ON CONFLICT (order_id) DO NOTHING",
                (order_id, fingerprint, json.dumps(result, sort_keys=True, default=str), "SUBMITTED", datetime.now(timezone.utc)),
            )
