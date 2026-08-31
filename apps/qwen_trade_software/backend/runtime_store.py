"""Durable runtime observability and state with Redis working-memory mirrors.

TimescaleDB is authoritative for events and state. Redis is a disposable,
low-latency mirror used for current working context. File persistence is not
used when the live Timescale backend is configured.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _dsn() -> str | None:
    if os.environ.get("QWEN_INTELLIGENCE_BACKEND", "sqlite").strip().lower() != "timescale":
        return None
    return os.environ.get("QWEN_TIMESCALE_DSN") or None


def _key(path: Path | str) -> str:
    return Path(path).name


def _json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


class RuntimeStore:
    """Small dependency-lazy adapter for runtime events and state."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or _dsn()
        self._redis = None
        redis_url = os.environ.get("QWEN_REDIS_URL")
        if redis_url:
            try:
                from redis import Redis
                self._redis = Redis.from_url(redis_url, decode_responses=True,
                                             socket_connect_timeout=1,
                                             socket_timeout=1)
            except Exception:
                self._redis = None

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    def _connect(self):
        if not self.dsn:
            raise RuntimeError("Timescale runtime store is not configured")
        import psycopg
        return psycopg.connect(self.dsn, connect_timeout=3)

    def ensure_schema(self) -> None:
        if not self.dsn:
            return
        from timescale_store import SCHEMA_SQL
        with self._connect() as connection:
            with connection.cursor() as cur:
                cur.execute(SCHEMA_SQL)

    def append_event(self, *, owner: str, level: str, message: str,
                     event_name: str | None = None,
                     payload: dict[str, Any] | None = None) -> None:
        if not self.dsn:
            return
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cur:
            cur.execute(
                "INSERT INTO runtime_events(recorded_at_utc,owner,level,message,event_name,payload_json) "
                "VALUES(%s,%s,%s,%s,%s,%s::jsonb)",
                (now, owner, level, message[:20000], event_name,
                 _json(payload or {})),
            )

    def events(self, *, owner: str | None = None,
               event_name: str | None = None,
               since: datetime | None = None) -> list[dict[str, Any]]:
        """Read runtime events for live dashboards/workers without files."""
        if not self.dsn:
            return []
        clauses: list[str] = []
        params: list[Any] = []
        if owner:
            clauses.append("owner=%s")
            params.append(owner)
        if event_name:
            clauses.append("event_name=%s")
            params.append(event_name)
        if since:
            clauses.append("recorded_at_utc >= %s")
            params.append(since)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._connect() as connection, connection.cursor() as cur:
            cur.execute(
                "SELECT recorded_at_utc,owner,level,message,event_name,payload_json "
                f"FROM runtime_events{where} ORDER BY recorded_at_utc ASC",
                params,
            )
            rows = cur.fetchall()
        return [
            {"recorded_at_utc": row[0], "owner": row[1], "level": row[2],
             "message": row[3], "event_name": row[4],
             "payload": row[5] if isinstance(row[5], dict) else json.loads(row[5])}
            for row in rows
        ]

    def put_state(self, path: Path | str, payload: dict[str, Any], *, owner: str) -> None:
        key = _key(path)
        encoded = _json(payload)
        if self.dsn:
            with self._connect() as connection, connection.cursor() as cur:
                cur.execute(
                    "INSERT INTO runtime_state(state_key,updated_at_utc,owner,payload_json) "
                    "VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT(state_key) DO UPDATE SET "
                    "updated_at_utc=EXCLUDED.updated_at_utc,owner=EXCLUDED.owner,payload_json=EXCLUDED.payload_json",
                    (key, datetime.now(timezone.utc), owner, encoded),
                )
        if self._redis is not None:
            try:
                self._redis.set(f"qwen:working:v1:state:{key}", encoded)
            except Exception:
                pass

    def get_state(self, path: Path | str) -> dict[str, Any] | None:
        key = _key(path)
        if self._redis is not None:
            try:
                raw = self._redis.get(f"qwen:working:v1:state:{key}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        if not self.dsn:
            return None
        with self._connect() as connection, connection.cursor() as cur:
            cur.execute("SELECT payload_json FROM runtime_state WHERE state_key=%s", (key,))
            row = cur.fetchone()
        if not row:
            return None
        return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def live_runtime_store() -> RuntimeStore | None:
    store = RuntimeStore()
    return store if store.enabled else None
