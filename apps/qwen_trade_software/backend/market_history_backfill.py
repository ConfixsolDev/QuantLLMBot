"""CLI for maximum broker history and New York-anchored H4 ingestion."""

from __future__ import annotations

import json
from pathlib import Path

import MetaTrader5 as mt5

from market_intelligence.historical_backfill import aggregate_ny_h4, candle_events, native_rows
from market_intelligence.projection import reduce_event
from market_intelligence.store import IntelligenceStore

DB = Path(__file__).resolve().parent / "cache" / "market-intelligence.sqlite3"


def main() -> int:
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialization failed: {mt5.last_error()}")
    store = IntelligenceStore(DB, busy_timeout_ms=30_000)
    report = {}
    try:
        for broker, logical in (("XAUUSDr", "XAUUSDr"), ("DXYr", "DXY")):
            inserted = {}
            # H4 has one authoritative convention: 17:00 New York trading-day
            # anchor. Remove only legacy broker H4 candle events, never Qwen or
            # execution events, before inserting their deterministic replacement.
            with store.lock, store.db:
                legacy_ids = store.db.execute(
                    "SELECT event_id FROM intelligence_events WHERE symbol=? "
                    "AND timeframe='H4' AND event_type='candle_closed' "
                    "AND COALESCE(json_extract(payload_json,'$.time_convention'),'broker') "
                    "!= 'new_york_1700_dst'", (logical,),
                ).fetchall()
                store.db.executemany(
                    "DELETE FROM graph_projection_outbox WHERE event_id=?",
                    [(row["event_id"],) for row in legacy_ids],
                )
                store.db.executemany(
                    "DELETE FROM intelligence_events WHERE event_id=?",
                    [(row["event_id"],) for row in legacy_ids],
                )
            h1 = None
            available = {}
            for timeframe in ("M1", "M15", "M30", "H1", "D1"):
                rows = native_rows(mt5, broker, logical, timeframe)
                available[timeframe] = len(rows)
                if timeframe == "H1":
                    h1 = rows
                inserted[timeframe] = store.append_events(candle_events(logical, timeframe, rows))
                with store.lock, store.db:
                    superseded = store.db.execute(
                        "SELECT event_id FROM intelligence_events WHERE symbol=? AND timeframe=? "
                        "AND event_type='candle_closed' AND "
                        "COALESCE(json_extract(payload_json,'$.time_convention'),'legacy') != 'broker'",
                        (logical, timeframe),
                    ).fetchall()
                    store.db.executemany("DELETE FROM graph_projection_outbox WHERE event_id=?",
                                         [(row["event_id"],) for row in superseded])
                    store.db.executemany("DELETE FROM intelligence_events WHERE event_id=?",
                                         [(row["event_id"],) for row in superseded])
            ny_rows = aggregate_ny_h4(h1 or [])
            inserted["H4_NY"] = store.append_events(
                candle_events(logical, "H4", ny_rows, "new_york_1700_dst")
            )
            report[logical] = {"removed_legacy_h4": len(legacy_ids),
                "inserted": inserted, "available": {**available, "H4_NY": len(ny_rows)}}
        store.rebuild(reduce_event)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
