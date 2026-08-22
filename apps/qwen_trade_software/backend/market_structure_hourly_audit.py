"""Build or append the two-month hourly market-structure supervision audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from market_intelligence.hourly_structure_audit import build_hourly_audit
from market_intelligence.store import IntelligenceStore

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"
DEFAULT_REPORT = APP_DIR / "cache" / "market-structure-quality.json"


def _write_report(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--symbol", default="XAUUSDr")
    parser.add_argument("--cross-symbol", default="DXY")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--forward-hours", type=int, default=4)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--write", action="store_true",
                        help="Append audit events to SQLite/outbox; default is dry-run.")
    args = parser.parse_args()
    events, summary = build_hourly_audit(
        args.db, symbol=args.symbol, cross_symbol=args.cross_symbol,
        days=args.days, forward_hours=args.forward_hours,
    )
    inserted = IntelligenceStore(args.db).append_events(events) if args.write else 0
    report = {
        **summary,
        "mode": "write" if args.write else "dry_run",
        "generated": len(events),
        "inserted": inserted,
        "sample_defects": [
            {"event_time_utc": row["event_time_utc"],
             "quality_status": row["payload"]["quality_status"],
             "quality_score": row["payload"]["quality_score"],
             "defects": row["payload"]["defects"],
             "supervised_analysis": row["payload"]["supervised_analysis"]}
            for row in events if row["payload"]["defects"]
        ][:20],
    }
    _write_report(args.report, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
