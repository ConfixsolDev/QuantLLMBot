"""Preflight and parity gate for the TimescaleDB/Redis cutover."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from storage_config import StorageConfig  # noqa: E402
from tools.migrate_context_sqlite_to_timescale import migrate as context_migrate  # noqa: E402
from tools.migrate_sqlite_to_timescale import migrate as intelligence_migrate  # noqa: E402


def run(source_context: Path, source_intelligence: Path, *, dsn: str | None = None) -> dict:
    config = StorageConfig.from_env()
    result = {"status": "blocked", "configuration": {
        "intelligence_backend": config.backend,
        "context_backend": os.environ.get("QWEN_CONTEXT_BACKEND", "sqlite"),
        "redis_configured": bool(config.redis_url),
    }}
    if config.backend != "timescale" or os.environ.get("QWEN_CONTEXT_BACKEND", "sqlite").lower() != "timescale":
        result["reason"] = "Both QWEN_INTELLIGENCE_BACKEND and QWEN_CONTEXT_BACKEND must be timescale for cutover"
        return result
    target_dsn = dsn or config.timescale_dsn
    if not target_dsn:
        result["reason"] = "QWEN_TIMESCALE_DSN is required"
        return result
    result["source_counts"] = {
        "intelligence": intelligence_migrate(source_intelligence, target_dsn, dry_run=True),
        "context": context_migrate(source_context, target_dsn, dry_run=True),
    }
    try:
        result["storage_health"] = config.validate_activation()
    except Exception as exc:
        result["reason"] = f"storage health failed: {exc}"
        return result
    result["status"] = "ready_for_migration"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--context-db", type=Path, default=BACKEND / "cache" / "market_context.sqlite3")
    parser.add_argument("--intelligence-db", type=Path, default=BACKEND / "cache" / "market-intelligence.sqlite3")
    parser.add_argument("--dsn")
    args = parser.parse_args()
    result = run(args.context_db, args.intelligence_db, dsn=args.dsn)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] == "ready_for_migration" else 2


if __name__ == "__main__":
    raise SystemExit(main())
