"""Dry-run or append deterministic multi-timeframe structure shadow labels."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_intelligence.store import IntelligenceStore
from market_intelligence.structure_labeling import SWING_WINGS, STRUCTURE_TIMEFRAMES, label_structure
from instrument_config import instrument_for

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"


def completed_candles(db_path: Path, symbol: str, timeframe: str,
                      start_utc: str, warmup: int = 200) -> list[dict]:
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    before = db.execute(
        "SELECT event_time_utc FROM intelligence_events WHERE symbol=? AND timeframe=? "
        "AND event_type='candle_closed' AND event_time_utc<? "
        "ORDER BY event_time_utc DESC LIMIT 1 OFFSET ?",
        (symbol, timeframe, start_utc, max(0, warmup - 1)),
    ).fetchone()
    boundary = before["event_time_utc"] if before else start_utc
    rows = db.execute(
        "SELECT event_time_utc,evidence_id,payload_json FROM intelligence_events "
        "WHERE symbol=? AND timeframe=? AND event_type='candle_closed' "
        "AND event_time_utc>=? ORDER BY event_time_utc",
        (symbol, timeframe, boundary),
    ).fetchall()
    db.close()
    result = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if not all(payload.get(key) is not None for key in ("open", "high", "low", "close")):
            continue
        result.append({"event_time_utc": row["event_time_utc"],
                       "evidence_id": row["evidence_id"], **payload})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--symbol", default="XAUUSDr")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--timeframes", nargs="+", default=list(STRUCTURE_TIMEFRAMES))
    parser.add_argument("--write", action="store_true",
                        help="Append to SQLite/outbox. Default is a safe dry run.")
    args = parser.parse_args()
    with sqlite3.connect(args.db) as db:
        latest_h1 = db.execute(
            "SELECT MAX(event_time_utc) FROM intelligence_events WHERE symbol=? "
            "AND timeframe='H1' AND event_type='candle_closed'", (args.symbol,),
        ).fetchone()[0]
    anchor = (datetime.fromisoformat(str(latest_h1).replace("Z", "+00:00"))
              if latest_h1 else datetime.now(timezone.utc))
    start = (anchor - timedelta(days=max(1, args.days))).isoformat()
    all_events = []
    report = {}
    profile = instrument_for(args.symbol)
    for timeframe in args.timeframes:
        if timeframe not in STRUCTURE_TIMEFRAMES:
            raise SystemExit(f"unsupported timeframe: {timeframe}")
        bars = completed_candles(args.db, args.symbol, timeframe, start)
        events = [event for event in label_structure(
                    args.symbol, timeframe, bars, wing=SWING_WINGS[timeframe],
                    equal_tolerance=profile.equal_level_tolerance,
                    displacement_min_body=profile.displacement_min_body)
                  if event["event_time_utc"] >= start]
        all_events.extend(events)
        report[timeframe] = {
            "candles_with_warmup": len(bars), "events": len(events),
            "by_type": dict(sorted(Counter(row["event_type"] for row in events).items())),
        }
    inserted = IntelligenceStore(args.db).append_events(all_events) if args.write else 0
    print(json.dumps({"mode": "write" if args.write else "dry_run", "symbol": args.symbol,
                      "start_utc": start, "generated": len(all_events),
                      "inserted": inserted, "timeframes": report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
