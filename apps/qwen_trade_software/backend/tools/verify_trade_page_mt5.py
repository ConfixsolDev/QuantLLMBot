#!/usr/bin/env python3
"""Verify that the /trades headline statistics match authoritative MT5 deals.

The page filters by the computer's local calendar day. This command applies the
same boundary to broker deal timestamps and to the SQLite trade journal, then
compares closed trades, net P&L, wins, losses, and win rate.

Examples:
    python tools/verify_trade_page_mt5.py
    python tools/verify_trade_page_mt5.py --date 2026-08-27
    python tools/verify_trade_page_mt5.py --date 2026-08-27 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from market_intelligence.store import IntelligenceStore  # noqa: E402
from tools.reconcile_broker_truth import broker_positions, our_fills  # noqa: E402

DEFAULT_DB = BACKEND / "cache" / "market-intelligence.sqlite3"


def _summary(values: list[float]) -> dict:
    count = len(values)
    wins = sum(value > 0 for value in values)
    losses = sum(value < 0 for value in values)
    return {
        "closed_trades": count,
        "net_pnl": round(sum(values), 2),
        "wins": wins,
        "losses": losses,
        "win_rate": round((wins / count * 100.0) if count else 0.0, 1),
    }


def _broker_rows(target: date, days: int, local_tz) -> dict[str, float]:
    import MetaTrader5 as mt5

    rows = {}
    recorded_fills = our_fills(days)
    for position_id, deals in broker_positions(days).items():
        entries = [deal for deal in deals if deal.entry == mt5.DEAL_ENTRY_IN]
        exits = [deal for deal in deals if deal.entry != mt5.DEAL_ENTRY_IN]
        entry_volume = sum(float(deal.volume) for deal in entries)
        exit_volume = sum(float(deal.volume) for deal in exits)
        if not entries or not exits or exit_volume + 1e-9 < entry_volume:
            continue
        final_exit = max(exits, key=lambda deal: (deal.time_msc, deal.ticket))
        closed_local = datetime.fromtimestamp(
            final_exit.time_msc / 1000.0, timezone.utc
        ).astimezone(local_tz)
        if closed_local.date() != target:
            continue
        proposal_id = (recorded_fills.get(position_id) or {}).get("proposal_id")
        key = str(proposal_id or f"mt5-position-{position_id}")
        rows[key] = sum(
            float(deal.profit) + float(deal.commission)
            + float(deal.swap) + float(deal.fee)
            for deal in deals
        )
    return rows


def _journal_rows(target: date, db_path: Path, local_tz) -> dict[str, float]:
    local_start = datetime.combine(target, time.min, tzinfo=local_tz)
    local_end = local_start + timedelta(days=1)
    store = IntelligenceStore(db_path)
    try:
        rows = store.trade_journals(
            limit=10000,
            start_utc=local_start.astimezone(timezone.utc).isoformat(),
            end_utc=local_end.astimezone(timezone.utc).isoformat(),
        )
    finally:
        store.db.close()
    return {
        str(row["proposal_id"]): float(row.get("net_pnl") or 0.0)
        for row in rows
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="local page date in YYYY-MM-DD format")
    parser.add_argument("--days", type=int, default=7, help="MT5 history lookback")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    local_tz = datetime.now().astimezone().tzinfo
    target = date.fromisoformat(args.date) if args.date else datetime.now(local_tz).date()
    broker_rows = _broker_rows(target, max(1, args.days), local_tz)
    page_rows = _journal_rows(target, args.db, local_tz)
    broker = _summary(list(broker_rows.values()))
    page = _summary(list(page_rows.values()))
    differences = {
        key: {"mt5": broker[key], "page": page[key]}
        for key in broker
        if broker[key] != page[key]
    }
    result = {
        "date": target.isoformat(),
        "timezone": str(local_tz),
        "match": not differences,
        "mt5": broker,
        "page": page,
        "differences": differences,
        "missing_from_page": {
            key: round(value, 2) for key, value in broker_rows.items()
            if key not in page_rows
        },
        "pnl_mismatches": {
            key: {"mt5": round(value, 2), "page": round(page_rows[key], 2)}
            for key, value in broker_rows.items()
            if key in page_rows and round(value, 2) != round(page_rows[key], 2)
        },
        "extra_on_page": {
            key: round(value, 2) for key, value in page_rows.items()
            if key not in broker_rows
        },
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Trade-page verification for {target.isoformat()} ({local_tz})")
        print(f"{'Metric':<16}{'MT5':>12}{'Page':>12}{'Match':>9}")
        for key in broker:
            print(f"{key:<16}{broker[key]:>12}{page[key]:>12}{str(broker[key] == page[key]):>9}")
        if result["missing_from_page"]:
            print(f"\nMissing from page: {result['missing_from_page']}")
        if result["pnl_mismatches"]:
            print(f"P&L mismatches: {result['pnl_mismatches']}")
        if result["extra_on_page"]:
            print(f"Extra on page: {result['extra_on_page']}")
        print("\nMATCH" if not differences else "\nMISMATCH")
    return 0 if not differences else 1


if __name__ == "__main__":
    raise SystemExit(main())
