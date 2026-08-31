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
from timescale_context_store import TimescaleMarketContextCache  # noqa: E402
from timescale_store import TimescaleIntelligenceStore  # noqa: E402
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
    try:
        intelligence_target = TimescaleIntelligenceStore(target_dsn)
        context_target = TimescaleMarketContextCache(target_dsn)
        result["target_counts"] = {
            "intelligence": intelligence_target.counts(),
            "context": context_target.counts(),
        }
        intelligence_target.close()
        context_target.close()
        expected = result["source_counts"]
        actual = result["target_counts"]
        expected_intelligence = {"events": "intelligence_events", "projections": "structure_projections", "retrievals": "retrieval_audit", "journals": "trade_journal"}
        expected_context = {key: key for key in expected["context"]}
        mismatches = []
        for source_key, target_key in expected_intelligence.items():
            if expected["intelligence"][source_key] > actual["intelligence"][target_key]:
                mismatches.append(f"intelligence.{source_key}: source={expected['intelligence'][source_key]} target={actual['intelligence'][target_key]}")
        for source_key, target_key in expected_context.items():
            if expected["context"][source_key] > actual["context"][target_key]:
                mismatches.append(f"context.{source_key}: source={expected['context'][source_key]} target={actual['context'][target_key]}")
        if mismatches:
            result["reason"] = "Target row counts are behind the read-only source snapshot"
            result["mismatches"] = mismatches
            return result
    except Exception as exc:
        result["reason"] = f"target parity check failed: {exc}"
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
