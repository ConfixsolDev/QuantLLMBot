"""Small DB-API compatibility layer for the fallback runtime's TimescaleDB.

The restored application historically used SQLite's ``?`` placeholders and
mapping rows.  This adapter preserves that narrow calling contract while
making PostgreSQL/TimescaleDB the only SQL authority.  Local JSON/JSONL files
remain independent operational evidence.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable


TIMESCALE_DSN_ENV = "QWEN_TIMESCALE_DSN"
TIMESCALE_SCHEMA_ENV = "QWEN_TIMESCALE_SCHEMA"


def timescale_dsn() -> str:
    dsn = os.environ.get(TIMESCALE_DSN_ENV, "").strip()
    if not dsn:
        raise RuntimeError(
            f"{TIMESCALE_DSN_ENV} is required; SQLite fallback is disabled"
        )
    return dsn


def _sql(sql: str) -> str:
    statement = sql.strip()
    ignore = bool(re.match(r"INSERT\s+OR\s+IGNORE\s+INTO", statement, re.I))
    statement = re.sub(
        r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", statement, flags=re.I
    )
    statement = statement.replace("?", "%s")
    statement = re.sub(r"\bis_current\s*=\s*0\b", "is_current=FALSE", statement, flags=re.I)
    statement = re.sub(r"\bis_current\s*=\s*1\b", "is_current=TRUE", statement, flags=re.I)
    if "is_current" in statement.lower():
        statement = re.sub(r",\s*1\s*\)(\s*$)", ",TRUE)", statement)
    statement = statement.replace("LIMIT -1 OFFSET", "OFFSET")
    if ignore:
        statement += " ON CONFLICT DO NOTHING"
    return statement


def _value(value: Any) -> Any:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


class Cursor:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self):
        row = self._cursor.fetchone()
        return _normalise_row(row)

    def fetchall(self):
        return [_normalise_row(row) for row in self._cursor.fetchall()]


def _normalise_row(row: Any):
    if row is None:
        return None
    return {key: _value(value) for key, value in dict(row).items()}


class TimescaleConnection:
    """Long-lived connection with SQLite-compatible transaction contexts."""

    def __init__(self, dsn: str | None = None, *, schema: str | None = None) -> None:
        import psycopg
        from psycopg.rows import dict_row

        self._db = psycopg.connect(
            dsn or timescale_dsn(), connect_timeout=5, row_factory=dict_row
        )
        schema = (schema or os.environ.get(
            TIMESCALE_SCHEMA_ENV, "fallback_positive"
        )).strip()
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema):
            raise RuntimeError(f"invalid {TIMESCALE_SCHEMA_ENV}: {schema!r}")
        self.schema = schema
        self._db.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        self._db.execute(f'SET search_path TO "{schema}", public')
        self._db.commit()
        self._depth = 0

    def __enter__(self):
        self._depth += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._depth -= 1
        if self._depth == 0:
            self._db.rollback() if exc_type else self._db.commit()
        return False

    def close(self) -> None:
        self._db.close()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> Cursor:
        return Cursor(self._db.execute(_sql(sql), tuple(params)))

    def executescript(self, _script: str) -> None:
        # Schema is managed centrally by ensure_timescale_schema().  Keeping
        # this method makes the restored cache class source-compatible.
        ensure_timescale_schema(self)


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS completed_candles (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time_utc TIMESTAMPTZ NOT NULL,
 close_time_utc TIMESTAMPTZ NOT NULL, open DOUBLE PRECISION NOT NULL,
 high DOUBLE PRECISION NOT NULL, low DOUBLE PRECISION NOT NULL,
 close DOUBLE PRECISION NOT NULL, tick_volume BIGINT NOT NULL, spread INTEGER NOT NULL,
 real_volume BIGINT NOT NULL, source TEXT NOT NULL, ingested_at_utc TIMESTAMPTZ NOT NULL,
 evidence_id TEXT NOT NULL, row_hash TEXT NOT NULL,
 PRIMARY KEY(symbol,timeframe,open_time_utc));
SELECT create_hypertable('completed_candles','open_time_utc',if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS completed_candles_lookup ON completed_candles(symbol,timeframe,open_time_utc DESC);
CREATE INDEX IF NOT EXISTS completed_candles_evidence ON completed_candles(evidence_id);
CREATE TABLE IF NOT EXISTS forming_candles (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time_utc TIMESTAMPTZ NOT NULL,
 close_time_utc TIMESTAMPTZ NOT NULL, open DOUBLE PRECISION NOT NULL,
 high DOUBLE PRECISION NOT NULL, low DOUBLE PRECISION NOT NULL,
 close DOUBLE PRECISION NOT NULL, tick_volume BIGINT NOT NULL, spread INTEGER NOT NULL,
 real_volume BIGINT NOT NULL, source TEXT NOT NULL, ingested_at_utc TIMESTAMPTZ NOT NULL,
 evidence_id TEXT NOT NULL, row_hash TEXT NOT NULL, PRIMARY KEY(symbol,timeframe));
CREATE TABLE IF NOT EXISTS ticks (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, time_utc TIMESTAMPTZ NOT NULL,
 bid DOUBLE PRECISION NOT NULL, ask DOUBLE PRECISION NOT NULL,
 spread DOUBLE PRECISION NOT NULL, flags INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS ticks_symbol_time ON ticks(symbol,time_utc DESC);
CREATE TABLE IF NOT EXISTS cache_objects (
 cache_type TEXT NOT NULL, cache_epoch TEXT PRIMARY KEY, symbol TEXT NOT NULL,
 schema_version INTEGER NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL,
 valid_as_of_utc TIMESTAMPTZ NOT NULL, source_start_utc TIMESTAMPTZ,
 source_end_utc TIMESTAMPTZ, source_hash TEXT NOT NULL, producer_version TEXT NOT NULL,
 model_digest TEXT, expires_at_utc TIMESTAMPTZ, invalidated_at_utc TIMESTAMPTZ,
 invalidation_reason TEXT, evidence_ids_json JSONB NOT NULL, payload_json JSONB NOT NULL,
 is_current BOOLEAN NOT NULL DEFAULT TRUE);
CREATE INDEX IF NOT EXISTS cache_current ON cache_objects(symbol,cache_type,is_current,valid_as_of_utc DESC);
CREATE TABLE IF NOT EXISTS readiness_manifests (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, validated_at_utc TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL, payload_json JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS qwen_validations (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, validation_type TEXT NOT NULL,
 created_at_utc TIMESTAMPTZ NOT NULL, input_hash TEXT NOT NULL, response_json JSONB,
 raw_response TEXT, passed BOOLEAN NOT NULL, failures_json JSONB NOT NULL,
 metrics_json JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS latency_events (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, cycle_id TEXT NOT NULL,
 created_at_utc TIMESTAMPTZ NOT NULL, stage TEXT NOT NULL,
 duration_ms DOUBLE PRECISION NOT NULL, details_json JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS intelligence_events (
 event_time_utc TIMESTAMPTZ NOT NULL, event_id TEXT NOT NULL,
 sequence BIGSERIAL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
 event_type TEXT NOT NULL, evidence_id TEXT, payload_json JSONB NOT NULL,
 payload_hash TEXT NOT NULL, recorded_at_utc TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(event_time_utc,event_id));
SELECT create_hypertable('intelligence_events','event_time_utc',if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS intelligence_event_lookup ON intelligence_events(symbol,timeframe,sequence);
CREATE TABLE IF NOT EXISTS structure_projections (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, state_json JSONB NOT NULL,
 structure_epoch TEXT NOT NULL, last_event_id TEXT, updated_at_utc TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(symbol,timeframe));
CREATE TABLE IF NOT EXISTS retrieval_audit (
 request_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, requested_at_utc TIMESTAMPTZ NOT NULL,
 request_json JSONB NOT NULL, result_json JSONB NOT NULL, status TEXT NOT NULL);
"""


def ensure_timescale_schema(connection: TimescaleConnection | None = None) -> None:
    owns = connection is None
    db = connection or TimescaleConnection()
    try:
        db._db.execute(SCHEMA_SQL)
        db._db.commit()
    finally:
        if owns:
            db.close()


def drop_timescale_schema(schema: str) -> None:
    if not re.fullmatch(r"fallback_test_[a-z0-9_]+", schema):
        raise RuntimeError(f"refusing to drop non-test schema: {schema!r}")
    db = TimescaleConnection(schema=schema)
    try:
        db._db.execute(f'DROP SCHEMA "{schema}" CASCADE')
        db._db.commit()
    finally:
        db.close()
