"""TimescaleDB-backed replacement for MarketContextCache persistence.

The public methods mirror the persistence surface used by
``market_context_cache.py``. Market calculations remain in that module; this
class only changes where candles, projections, manifests, and audit records
are stored.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from storage_config import StorageConfig


SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS completed_candles (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time_utc TIMESTAMPTZ NOT NULL,
 close_time_utc TIMESTAMPTZ NOT NULL, open DOUBLE PRECISION NOT NULL,
 high DOUBLE PRECISION NOT NULL, low DOUBLE PRECISION NOT NULL,
 close DOUBLE PRECISION NOT NULL, tick_volume BIGINT NOT NULL DEFAULT 0,
 spread INTEGER NOT NULL DEFAULT 0, real_volume BIGINT NOT NULL DEFAULT 0,
 source TEXT NOT NULL, ingested_at_utc TIMESTAMPTZ NOT NULL,
 evidence_id TEXT NOT NULL, row_hash TEXT NOT NULL,
 PRIMARY KEY(symbol,timeframe,open_time_utc)
);
SELECT create_hypertable('completed_candles','open_time_utc',if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS completed_candles_lookup ON completed_candles(symbol,timeframe,open_time_utc DESC);
CREATE INDEX IF NOT EXISTS completed_candles_evidence ON completed_candles(evidence_id);
CREATE TABLE IF NOT EXISTS completed_candle_corrections (
 id BIGSERIAL PRIMARY KEY, evidence_id TEXT NOT NULL, corrected_at_utc TIMESTAMPTZ NOT NULL,
 reason TEXT NOT NULL, changed_fields_json JSONB NOT NULL, prior_row_json JSONB NOT NULL,
 corrected_row_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS forming_candles (
 symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open_time_utc TIMESTAMPTZ NOT NULL,
 close_time_utc TIMESTAMPTZ NOT NULL, open DOUBLE PRECISION NOT NULL,
 high DOUBLE PRECISION NOT NULL, low DOUBLE PRECISION NOT NULL,
 close DOUBLE PRECISION NOT NULL, tick_volume BIGINT NOT NULL DEFAULT 0,
 spread INTEGER NOT NULL DEFAULT 0, real_volume BIGINT NOT NULL DEFAULT 0,
 source TEXT NOT NULL, ingested_at_utc TIMESTAMPTZ NOT NULL,
 evidence_id TEXT NOT NULL, row_hash TEXT NOT NULL, PRIMARY KEY(symbol,timeframe)
);
CREATE TABLE IF NOT EXISTS ticks (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, time_utc TIMESTAMPTZ NOT NULL,
 bid DOUBLE PRECISION NOT NULL, ask DOUBLE PRECISION NOT NULL,
 spread DOUBLE PRECISION NOT NULL, flags INTEGER NOT NULL, migration_key TEXT
);
ALTER TABLE ticks ADD COLUMN IF NOT EXISTS migration_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS tick_migration_key ON ticks(migration_key) WHERE migration_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS ticks_lookup ON ticks(symbol,time_utc DESC);
CREATE TABLE IF NOT EXISTS cache_objects (
 cache_type TEXT NOT NULL, cache_epoch TEXT PRIMARY KEY, symbol TEXT NOT NULL,
 schema_version INTEGER NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL,
 valid_as_of_utc TIMESTAMPTZ NOT NULL, source_start_utc TIMESTAMPTZ,
 source_end_utc TIMESTAMPTZ, source_hash TEXT NOT NULL, producer_version TEXT NOT NULL,
 model_digest TEXT, expires_at_utc TIMESTAMPTZ, invalidated_at_utc TIMESTAMPTZ,
 invalidation_reason TEXT, evidence_ids_json JSONB NOT NULL, payload_json JSONB NOT NULL,
 is_current BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS cache_current_lookup ON cache_objects(symbol,cache_type,is_current,valid_as_of_utc DESC);
CREATE TABLE IF NOT EXISTS readiness_manifests (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, validated_at_utc TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL, payload_json JSONB NOT NULL, migration_key TEXT
);
ALTER TABLE readiness_manifests ADD COLUMN IF NOT EXISTS migration_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS readiness_manifest_migration_key ON readiness_manifests(migration_key) WHERE migration_key IS NOT NULL;
CREATE TABLE IF NOT EXISTS qwen_validations (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, validation_type TEXT NOT NULL,
 created_at_utc TIMESTAMPTZ NOT NULL, input_hash TEXT NOT NULL, response_json JSONB,
 raw_response TEXT, passed BOOLEAN NOT NULL, failures_json JSONB NOT NULL, metrics_json JSONB NOT NULL,
 migration_key TEXT
);
ALTER TABLE qwen_validations ADD COLUMN IF NOT EXISTS migration_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS qwen_validation_migration_key ON qwen_validations(migration_key) WHERE migration_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS qwen_validation_lookup ON qwen_validations(symbol,validation_type,input_hash,created_at_utc DESC);
CREATE TABLE IF NOT EXISTS latency_events (
 id BIGSERIAL PRIMARY KEY, symbol TEXT NOT NULL, cycle_id TEXT NOT NULL,
 created_at_utc TIMESTAMPTZ NOT NULL, stage TEXT NOT NULL,
 duration_ms DOUBLE PRECISION NOT NULL, details_json JSONB NOT NULL, migration_key TEXT
);
ALTER TABLE latency_events ADD COLUMN IF NOT EXISTS migration_key TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS latency_event_migration_key ON latency_events(migration_key) WHERE migration_key IS NOT NULL;
"""


def _dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("naive timestamp is not allowed")
    return result.astimezone(timezone.utc)


class TimescaleMarketContextCache:
    def __init__(self, dsn: str | None = None, *, pool: Any = None,
                 report_metadata_corrections: bool = True) -> None:
        if pool is not None:
            self.pool = pool
        else:
            try:
                from psycopg_pool import ConnectionPool
                self.pool = ConnectionPool(
                    conninfo=dsn or StorageConfig.from_env().timescale_dsn,
                    min_size=1, max_size=8,
                    kwargs={"connect_timeout": 3}, open=True,
                )
            except Exception as exc:
                raise RuntimeError("TimescaleDB context store unavailable") from exc
        self.path = None
        self.report_metadata_corrections = report_metadata_corrections
        self._create_schema()

    def _create_schema(self) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute(SCHEMA_SQL)

    def close(self) -> None:
        self.pool.close()

    def counts(self) -> dict[str, int]:
        """Return durable row counts used by the context cutover parity gate."""
        tables = ("completed_candles", "forming_candles", "ticks", "cache_objects", "readiness_manifests", "qwen_validations", "latency_events")
        with self.pool.connection() as connection, connection.cursor() as cur:
            return {table: int(cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}

    @staticmethod
    def _storage(row: dict) -> dict:
        from market_context_cache import content_hash, iso_utc, utc_now
        stable = {key: row[key] for key in (
            "symbol", "timeframe", "open_time_utc", "close_time_utc", "open", "high",
            "low", "close", "tick_volume", "spread", "real_volume", "source", "evidence_id")}
        stable["row_hash"] = content_hash(stable)
        stable["ingested_at_utc"] = row.get("ingested_at_utc", iso_utc(utc_now()))
        return stable

    def ingest_completed(self, rows: Iterable[dict]) -> dict[str, int]:
        inserted = unchanged = corrections = 0
        immutable = {"symbol", "timeframe", "open_time_utc", "close_time_utc", "open", "high", "low", "close", "source", "evidence_id"}
        with self.pool.connection() as connection:
            with connection.cursor() as cur:
                for raw in rows:
                    if not raw.get("is_complete", True):
                        raise ValueError("forming candle cannot enter completed_candles")
                    row = self._storage(raw)
                    cur.execute("SELECT * FROM completed_candles WHERE symbol=%s AND timeframe=%s AND open_time_utc=%s", (row["symbol"], row["timeframe"], _dt(row["open_time_utc"])))
                    existing = cur.fetchone()
                    if existing:
                        # Existing candle identity is immutable. Metadata revisions
                        # are intentionally ignored, matching the SQLite contract.
                        names = [desc.name for desc in cur.description]
                        prior = dict(zip(names, existing))
                        def same_value(field: str) -> bool:
                            if field in {"open_time_utc", "close_time_utc"}:
                                return _dt(prior[field]) == _dt(row[field])
                            return str(prior[field]) == str(row[field])
                        changed = [field for field in immutable if not same_value(field)]
                        if changed:
                            raise ValueError(f"immutable completed candle changed: {row['evidence_id']} fields={','.join(changed)}")
                        unchanged += 1
                        corrections += int(prior.get("row_hash") != row["row_hash"])
                        continue
                    cur.execute("INSERT INTO completed_candles(symbol,timeframe,open_time_utc,close_time_utc,open,high,low,close,tick_volume,spread,real_volume,source,ingested_at_utc,evidence_id,row_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", (row["symbol"], row["timeframe"], _dt(row["open_time_utc"]), _dt(row["close_time_utc"]), row["open"], row["high"], row["low"], row["close"], row["tick_volume"], row["spread"], row["real_volume"], row["source"], _dt(row["ingested_at_utc"]), row["evidence_id"], row["row_hash"]))
                    cur.execute("DELETE FROM forming_candles WHERE symbol=%s AND timeframe=%s AND open_time_utc=%s", (row["symbol"], row["timeframe"], _dt(row["open_time_utc"])))
                    inserted += cur.rowcount >= 0
        return {"inserted": int(inserted), "unchanged": unchanged, "metadata_corrections": corrections}

    def upsert_forming(self, rows: Iterable[dict]) -> int:
        count = 0
        with self.pool.connection() as connection, connection.cursor() as cur:
            for raw in rows:
                if raw.get("is_complete"):
                    raise ValueError("completed candle cannot enter forming_candles")
                row = self._storage(raw)
                cur.execute("INSERT INTO forming_candles(symbol,timeframe,open_time_utc,close_time_utc,open,high,low,close,tick_volume,spread,real_volume,source,ingested_at_utc,evidence_id,row_hash) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(symbol,timeframe) DO UPDATE SET open_time_utc=EXCLUDED.open_time_utc,close_time_utc=EXCLUDED.close_time_utc,open=EXCLUDED.open,high=EXCLUDED.high,low=EXCLUDED.low,close=EXCLUDED.close,tick_volume=EXCLUDED.tick_volume,spread=EXCLUDED.spread,real_volume=EXCLUDED.real_volume,source=EXCLUDED.source,ingested_at_utc=EXCLUDED.ingested_at_utc,evidence_id=EXCLUDED.evidence_id,row_hash=EXCLUDED.row_hash", (row["symbol"], row["timeframe"], _dt(row["open_time_utc"]), _dt(row["close_time_utc"]), row["open"], row["high"], row["low"], row["close"], row["tick_volume"], row["spread"], row["real_volume"], row["source"], _dt(row["ingested_at_utc"]), row["evidence_id"], row["row_hash"]))
                count += 1
        return count

    def add_quote(self, quote: Any) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO ticks(symbol,time_utc,bid,ask,spread,flags) VALUES(%s,%s,%s,%s,%s,%s)", (quote.symbol, _dt(quote.time_utc), quote.bid, quote.ask, quote.spread, quote.flags))
            cur.execute("DELETE FROM ticks WHERE id IN (SELECT id FROM ticks WHERE symbol=%s ORDER BY id DESC OFFSET 10000)", (quote.symbol,))

    def insert_tick(self, row: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO ticks(symbol,time_utc,bid,ask,spread,flags) VALUES(%s,%s,%s,%s,%s,%s)", (row["symbol"], _dt(row["time_utc"]), row["bid"], row["ask"], row["spread"], row["flags"]))

    def copy_cache_object(self, row: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO cache_objects(cache_type,cache_epoch,symbol,schema_version,created_at_utc,valid_as_of_utc,source_start_utc,source_end_utc,source_hash,producer_version,model_digest,expires_at_utc,invalidated_at_utc,invalidation_reason,evidence_ids_json,payload_json,is_current) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT(cache_epoch) DO NOTHING", (row["cache_type"], row["cache_epoch"], row["symbol"], row["schema_version"], _dt(row["created_at_utc"]), _dt(row["valid_as_of_utc"]), _dt(row["source_start_utc"]) if row.get("source_start_utc") else None, _dt(row["source_end_utc"]) if row.get("source_end_utc") else None, row["source_hash"], row["producer_version"], row.get("model_digest"), _dt(row["expires_at_utc"]) if row.get("expires_at_utc") else None, _dt(row["invalidated_at_utc"]) if row.get("invalidated_at_utc") else None, row.get("invalidation_reason"), row["evidence_ids_json"] if isinstance(row["evidence_ids_json"], str) else json.dumps(row["evidence_ids_json"]), row["payload_json"] if isinstance(row["payload_json"], str) else json.dumps(row["payload_json"]), bool(row["is_current"])))

    def copy_qwen_validation(self, row: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO qwen_validations(symbol,validation_type,created_at_utc,input_hash,response_json,raw_response,passed,failures_json,metrics_json) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb)", (row["symbol"], row["validation_type"], _dt(row["created_at_utc"]), row["input_hash"], row.get("response_json") or "null", row.get("raw_response"), bool(row["passed"]), row["failures_json"], row["metrics_json"]))

    def copy_latency(self, row: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO latency_events(symbol,cycle_id,created_at_utc,stage,duration_ms,details_json) VALUES(%s,%s,%s,%s,%s,%s::jsonb)", (row["symbol"], row["cycle_id"], _dt(row["created_at_utc"]), row["stage"], row["duration_ms"], row["details_json"]))

    def copy_batch(self, table: str, rows: list[dict]) -> int:
        """Copy migration rows with one pooled connection and batched execution."""
        if not rows:
            return 0
        with self.pool.connection() as connection, connection.cursor() as cur:
            if table == "ticks":
                cur.executemany("INSERT INTO ticks(symbol,time_utc,bid,ask,spread,flags,migration_key) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING", [
                    (row["symbol"], _dt(row["time_utc"]), row["bid"], row["ask"], row["spread"], row["flags"], row.get("migration_key")) for row in rows])
            elif table == "cache_objects":
                cur.executemany("INSERT INTO cache_objects(cache_type,cache_epoch,symbol,schema_version,created_at_utc,valid_as_of_utc,source_start_utc,source_end_utc,source_hash,producer_version,model_digest,expires_at_utc,invalidated_at_utc,invalidation_reason,evidence_ids_json,payload_json,is_current) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT(cache_epoch) DO NOTHING", [
                    (row["cache_type"], row["cache_epoch"], row["symbol"], row["schema_version"], _dt(row["created_at_utc"]), _dt(row["valid_as_of_utc"]), _dt(row["source_start_utc"]) if row.get("source_start_utc") else None, _dt(row["source_end_utc"]) if row.get("source_end_utc") else None, row["source_hash"], row["producer_version"], row.get("model_digest"), _dt(row["expires_at_utc"]) if row.get("expires_at_utc") else None, _dt(row["invalidated_at_utc"]) if row.get("invalidated_at_utc") else None, row.get("invalidation_reason"), row["evidence_ids_json"] if isinstance(row["evidence_ids_json"], str) else json.dumps(row["evidence_ids_json"]), row["payload_json"] if isinstance(row["payload_json"], str) else json.dumps(row["payload_json"]), bool(row["is_current"])) for row in rows])
            elif table == "qwen_validations":
                cur.executemany("INSERT INTO qwen_validations(symbol,validation_type,created_at_utc,input_hash,response_json,raw_response,passed,failures_json,metrics_json,migration_key) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s) ON CONFLICT DO NOTHING", [
                    (row["symbol"], row["validation_type"], _dt(row["created_at_utc"]), row["input_hash"], row.get("response_json") or "null", row.get("raw_response"), bool(row["passed"]), row["failures_json"], row["metrics_json"], row.get("migration_key")) for row in rows])
            elif table == "readiness_manifests":
                cur.executemany("INSERT INTO readiness_manifests(symbol,validated_at_utc,status,payload_json,migration_key) VALUES(%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING", [
                    (row["symbol"], _dt(row["validated_at_utc"]), row["status"], row["payload_json"] if isinstance(row["payload_json"], str) else json.dumps(row["payload_json"]), row.get("migration_key")) for row in rows])
            elif table == "latency_events":
                cur.executemany("INSERT INTO latency_events(symbol,cycle_id,created_at_utc,stage,duration_ms,details_json,migration_key) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT DO NOTHING", [
                    (row["symbol"], row["cycle_id"], _dt(row["created_at_utc"]), row["stage"], row["duration_ms"], row["details_json"], row.get("migration_key")) for row in rows])
            else:
                raise ValueError(f"unsupported migration table: {table}")
        return len(rows)

    def completed(self, symbol: str, timeframe: str) -> list[dict]:
        return self._rows("SELECT * FROM completed_candles WHERE symbol=%s AND timeframe=%s ORDER BY open_time_utc", (symbol, timeframe))

    def latest_completed(self, symbol: str, timeframe: str, count: int = 1) -> list[dict]:
        return list(reversed(self._rows("SELECT * FROM completed_candles WHERE symbol=%s AND timeframe=%s ORDER BY open_time_utc DESC LIMIT %s", (symbol, timeframe, max(1, int(count))))))

    def forming(self, symbol: str) -> dict[str, dict]:
        return {row["timeframe"]: row for row in self._rows("SELECT * FROM forming_candles WHERE symbol=%s ORDER BY timeframe", (symbol,))}

    def completed_counts(self, symbol: str) -> dict[str, int]:
        from market_context_cache import TIMEFRAME_SECONDS
        rows = self._rows("SELECT timeframe,COUNT(*) AS count FROM completed_candles WHERE symbol=%s GROUP BY timeframe", (symbol,))
        found = {row["timeframe"]: int(row["count"]) for row in rows}
        return {tf: found.get(tf, 0) for tf in TIMEFRAME_SECONDS}

    def evidence_exists(self, evidence_id: str) -> bool:
        return bool(self._rows("SELECT 1 FROM completed_candles WHERE evidence_id=%s LIMIT 1", (evidence_id,)))

    def source_bounds(self, symbol: str) -> tuple[str | None, str | None]:
        rows = self._rows("SELECT MIN(open_time_utc) AS first,MAX(open_time_utc) AS last FROM completed_candles WHERE symbol=%s", (symbol,))
        if not rows or rows[0]["first"] is None:
            return None, None
        return str(rows[0]["first"]), str(rows[0]["last"])

    def raw_hash(self, symbol: str) -> str:
        from market_context_cache import content_hash
        return content_hash({"completed": self._rows("SELECT timeframe,open_time_utc,row_hash FROM completed_candles WHERE symbol=%s ORDER BY timeframe,open_time_utc", (symbol,)), "forming": self._rows("SELECT timeframe,open_time_utc,row_hash FROM forming_candles WHERE symbol=%s ORDER BY timeframe", (symbol,))})

    def subset_hash(self, symbol: str, timeframes: Iterable[str], *, include_forming: bool = False) -> str:
        from market_context_cache import content_hash
        names = tuple(timeframes)
        placeholders = ",".join("%s" for _ in names)
        params = (symbol, *names)
        completed = self._rows(f"SELECT timeframe,open_time_utc,row_hash FROM completed_candles WHERE symbol=%s AND timeframe IN ({placeholders}) ORDER BY timeframe,open_time_utc", params)
        forming = self._rows(f"SELECT timeframe,open_time_utc,row_hash FROM forming_candles WHERE symbol=%s AND timeframe IN ({placeholders}) ORDER BY timeframe", params) if include_forming else []
        return content_hash({"completed": completed, "forming": forming})

    def incremental_starts(self, symbol: str, as_of: datetime) -> dict[str, datetime]:
        from market_context_cache import MT5MarketSource, TIMEFRAME_SECONDS
        result = {}
        for tf, seconds in TIMEFRAME_SECONDS.items():
            rows = self._rows("SELECT open_time_utc FROM completed_candles WHERE symbol=%s AND timeframe=%s ORDER BY open_time_utc DESC LIMIT 1", (symbol, tf))
            result[tf] = _dt(rows[0]["open_time_utc"]) - timedelta(seconds=seconds) if rows else MT5MarketSource._start_for(tf, as_of)
        return result

    def needs_canonical_h4_rebuild(self, symbol: str) -> bool:
        rows = self._rows("SELECT COUNT(*) AS total,COUNT(*) FILTER (WHERE source='MT5_H1_AGGREGATED_NY') AS canonical FROM completed_candles WHERE symbol=%s AND timeframe='H4'", (symbol,))
        return int(rows[0]["total"]) != int(rows[0]["canonical"])

    def clear_h4_for_canonical_rebuild(self, symbol: str) -> int:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("DELETE FROM completed_candles WHERE symbol=%s AND timeframe='H4'", (symbol,)); deleted = cur.rowcount
            cur.execute("DELETE FROM forming_candles WHERE symbol=%s AND timeframe='H4'", (symbol,))
        return int(deleted)

    def repair_derived_h4(self, rows: Iterable[dict]) -> list[dict]:
        # Canonical rebuilds are handled atomically by clear_h4_for_canonical_rebuild.
        return []

    def put_object(self, cache_type: str, symbol: str, valid_as_of: datetime | str, payload: dict, *, source_hash: str, evidence_ids: Iterable[str], model_digest: str | None = None, expires_at: datetime | str | None = None) -> dict:
        from market_context_cache import SCHEMA_VERSION, canonical_json, content_hash, git_version
        evidence = sorted(set(evidence_ids)); identity = content_hash({"cache_type": cache_type, "symbol": symbol, "source_hash": source_hash, "payload": payload, "evidence_ids": evidence, "model_digest": model_digest}); epoch = f"{cache_type}-{symbol}-{identity.split(':',1)[1][:16]}"; start, end = self.source_bounds(symbol); now = datetime.now(timezone.utc)
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("UPDATE cache_objects SET is_current=FALSE,invalidated_at_utc=%s,invalidation_reason='superseded' WHERE symbol=%s AND cache_type=%s AND is_current=TRUE AND cache_epoch<>%s", (now, symbol, cache_type, epoch))
            cur.execute("INSERT INTO cache_objects(cache_type,cache_epoch,symbol,schema_version,created_at_utc,valid_as_of_utc,source_start_utc,source_end_utc,source_hash,producer_version,model_digest,expires_at_utc,evidence_ids_json,payload_json,is_current) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,TRUE) ON CONFLICT(cache_epoch) DO UPDATE SET is_current=TRUE,invalidation_reason=NULL,invalidated_at_utc=NULL", (cache_type, epoch, symbol, SCHEMA_VERSION, now, _dt(valid_as_of), _dt(start) if start else None, _dt(end) if end else None, source_hash, git_version(), model_digest, _dt(expires_at) if expires_at else None, canonical_json(evidence), canonical_json(payload)))
        return self.object(cache_type, symbol) or {}

    def object(self, cache_type: str, symbol: str) -> dict | None:
        rows = self._rows("SELECT * FROM cache_objects WHERE cache_type=%s AND symbol=%s AND is_current=TRUE ORDER BY valid_as_of_utc DESC LIMIT 1", (cache_type, symbol));
        if not rows: return None
        row = rows[0]; row["payload"] = row.pop("payload_json"); row["evidence_ids"] = row.pop("evidence_ids_json"); return row

    def write_manifest(self, symbol: str, manifest: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO readiness_manifests(symbol,validated_at_utc,status,payload_json) VALUES(%s,%s,%s,%s::jsonb)", (symbol, _dt(manifest["validated_at_utc"]), manifest["status"], json.dumps(manifest, separators=(",", ":"))))

    def latest_manifest(self, symbol: str) -> dict | None:
        rows = self._rows("SELECT payload_json FROM readiness_manifests WHERE symbol=%s ORDER BY id DESC LIMIT 1", (symbol,)); return rows[0]["payload_json"] if rows else None

    def record_qwen_validation(self, symbol: str, validation_type: str, input_value: dict, response: dict | None, raw_response: str, passed: bool, failures: list[str], metrics: dict) -> None:
        from market_context_cache import canonical_json, content_hash
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO qwen_validations(symbol,validation_type,created_at_utc,input_hash,response_json,raw_response,passed,failures_json,metrics_json) VALUES(%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb)", (symbol, validation_type, datetime.now(timezone.utc), content_hash(input_value), canonical_json(response) if response is not None else "null", raw_response, passed, canonical_json(failures), canonical_json(metrics)))

    def latest_qwen_response(self, symbol: str, validation_type: str, input_value: dict) -> tuple[dict, str] | None:
        from market_context_cache import canonical_json, content_hash
        rows = self._rows("SELECT response_json,raw_response FROM qwen_validations WHERE symbol=%s AND validation_type=%s AND input_hash=%s AND response_json IS NOT NULL ORDER BY id DESC LIMIT 1", (symbol, validation_type, content_hash(input_value))); return (rows[0]["response_json"], rows[0]["raw_response"] or canonical_json(rows[0]["response_json"])) if rows else None

    def record_latency(self, symbol: str, cycle_id: str, stage: str, duration_ms: float, details: dict) -> None:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("INSERT INTO latency_events(symbol,cycle_id,created_at_utc,stage,duration_ms,details_json) VALUES(%s,%s,%s,%s,%s,%s::jsonb)", (symbol, cycle_id, datetime.now(timezone.utc), stage, round(duration_ms, 3), json.dumps(details, separators=(",", ":"))))

    def flush_stale_model_objects(self, symbol: str, keep_digest: str) -> int:
        with self.pool.connection() as connection, connection.cursor() as cur:
            cur.execute("UPDATE cache_objects SET is_current=FALSE,invalidated_at_utc=%s,invalidation_reason='stale_model_digest' WHERE symbol=%s AND is_current=TRUE AND model_digest IS NOT NULL AND model_digest<>%s", (datetime.now(timezone.utc), symbol, keep_digest)); return int(cur.rowcount)

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("psycopg is required for TimescaleDB") from exc
        with self.pool.connection() as connection:
            with connection.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params); rows = cur.fetchall()
        result = []
        for row in rows:
            item = dict(row)
            for key, value in tuple(item.items()):
                if isinstance(value, datetime):
                    item[key] = value.isoformat().replace("+00:00", "Z")
            result.append(item)
        return result
