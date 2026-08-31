"""Migrate the market-context SQLite database into TimescaleDB.

The source is opened read-only and remains available for rollback/parity
comparison. Re-running the command is safe for candles and cache epochs.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
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
            for row in db.execute("SELECT symbol,time_utc,bid,ask,spread,flags FROM ticks ORDER BY id"):
                target.insert_tick(dict(row))
        if "cache_objects" in tables:
            for row in db.execute("SELECT * FROM cache_objects"):
                target.copy_cache_object(dict(row))
        if "readiness_manifests" in tables:
            for row in db.execute("SELECT symbol,payload_json FROM readiness_manifests"):
                target.write_manifest(row["symbol"], json.loads(row["payload_json"]))
        if "qwen_validations" in tables:
            for row in db.execute("SELECT * FROM qwen_validations"):
                target.copy_qwen_validation(dict(row))
        if "latency_events" in tables:
            for row in db.execute("SELECT * FROM latency_events"):
                target.copy_latency(dict(row))
        return counts
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.dsn, dry_run=args.dry_run), indent=2))


if __name__ == "__main__":
    main()
