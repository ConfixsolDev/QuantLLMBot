"""Migrate the market-context SQLite database into TimescaleDB.

The source is opened read-only and remains available for rollback/parity
comparison. Re-running the command is conflict-safe for candles, cache epochs,
and append-only rows carrying a stable source-row migration key.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from itertools import islice
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from timescale_context_store import TimescaleMarketContextCache  # noqa: E402


def migrate(source: Path, dsn: str, *, dry_run: bool = False) -> dict[str, int]:
    db = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {name: (db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] if name in tables else 0) for name in (
            "completed_candles", "forming_candles", "ticks", "cache_objects", "readiness_manifests", "qwen_validations", "latency_events")}
        if dry_run:
            return counts
        target = TimescaleMarketContextCache(dsn)
        if "completed_candles" in tables:
            rows = [dict(row) for row in db.execute("SELECT * FROM completed_candles ORDER BY open_time_utc")]
            target.ingest_completed(rows)
        if "forming_candles" in tables:
            target.upsert_forming([dict(row) for row in db.execute("SELECT * FROM forming_candles")])
        if "ticks" in tables:
            rows = db.execute("SELECT id,symbol,time_utc,bid,ask,spread,flags FROM ticks ORDER BY id")
            while batch := list(islice(rows, 1000)):
                target.copy_batch("ticks", [_with_key(row, source, "ticks") for row in batch])
        if "cache_objects" in tables:
            rows = db.execute("SELECT * FROM cache_objects")
            while batch := list(islice(rows, 1000)):
                target.copy_batch("cache_objects", [dict(row) for row in batch])
        if "readiness_manifests" in tables:
            rows = db.execute("SELECT id,symbol,validated_at_utc,status,payload_json FROM readiness_manifests")
            while batch := list(islice(rows, 1000)):
                target.copy_batch("readiness_manifests", [_with_key(row, source, "readiness_manifests") for row in batch])
        if "qwen_validations" in tables:
            rows = db.execute("SELECT * FROM qwen_validations")
            while batch := list(islice(rows, 1000)):
                target.copy_batch("qwen_validations", [_with_key(row, source, "qwen_validations") for row in batch])
        if "latency_events" in tables:
            rows = db.execute("SELECT * FROM latency_events")
            while batch := list(islice(rows, 1000)):
                target.copy_batch("latency_events", [_with_key(row, source, "latency_events") for row in batch])
        return counts
    finally:
        db.close()


def _with_key(row: sqlite3.Row, source: Path, table: str) -> dict:
    """Attach a stable source identity for append-only migration rows."""
    result = dict(row)
    result["migration_key"] = f"{source.resolve()}::{table}::{result['id']}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.dsn, dry_run=args.dry_run), indent=2))


if __name__ == "__main__":
    main()
