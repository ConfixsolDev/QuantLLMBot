"""One-way, idempotent migration of the durable intelligence ledger.

Run this before enabling QWEN_INTELLIGENCE_BACKEND=timescale. The source is
read-only. Market-context candle storage is intentionally not copied into
Redis: candles remain durable data and must be migrated to the Timescale
candle schema in the next migration step before removing SQLite access.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from timescale_store import TimescaleIntelligenceStore  # noqa: E402


def migrate(source: Path, dsn: str, *, dry_run: bool = False) -> dict[str, int]:
    connection = sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {"events": 0, "projections": 0, "retrievals": 0, "journals": 0}
        if dry_run:
            counts["events"] = connection.execute("SELECT COUNT(*) FROM intelligence_events").fetchone()[0] if "intelligence_events" in tables else 0
            counts["projections"] = connection.execute("SELECT COUNT(*) FROM structure_projections").fetchone()[0] if "structure_projections" in tables else 0
            counts["retrievals"] = connection.execute("SELECT COUNT(*) FROM retrieval_audit").fetchone()[0] if "retrieval_audit" in tables else 0
            counts["journals"] = connection.execute("SELECT COUNT(*) FROM trade_journal").fetchone()[0] if "trade_journal" in tables else 0
            return counts
        target = TimescaleIntelligenceStore(dsn)
        target.schema()
        if "intelligence_events" in tables:
            for row in connection.execute("SELECT * FROM intelligence_events ORDER BY event_time_utc,sequence"):
                event = {"event_id": row["event_id"], "symbol": row["symbol"], "timeframe": row["timeframe"], "event_type": row["event_type"], "event_time_utc": row["event_time_utc"], "evidence_id": row["evidence_id"], "payload": json.loads(row["payload_json"])}
                counts["events"] += int(target.append_event(event))
        if "structure_projections" in tables:
            for row in connection.execute("SELECT * FROM structure_projections"):
                target.put_projection(row["symbol"], row["timeframe"], json.loads(row["state_json"]), row["last_event_id"])
                counts["projections"] += 1
        if "retrieval_audit" in tables:
            for row in connection.execute("SELECT * FROM retrieval_audit"):
                target.record_retrieval(row["request_id"], row["symbol"], json.loads(row["request_json"]), json.loads(row["result_json"]), row["status"])
                counts["retrievals"] += 1
        return counts
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.source, args.dsn, dry_run=args.dry_run), indent=2))


if __name__ == "__main__":
    main()
