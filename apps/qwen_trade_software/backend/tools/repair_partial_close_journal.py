#!/usr/bin/env python3
"""Repair a prematurely finalized execution from authoritative MT5 exit legs."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import MetaTrader5 as mt5
import paper_executor
from market_intelligence.trade_journal import journal_closed_trade


def recorded_close(position_id: int) -> dict | None:
    for path in sorted((BACKEND / "logs").glob("paper-executions-*.jsonl"), reverse=True):
        rows = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(rows):
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "mt5_execution_closed":
                continue
            if any(int(fill.get("order") or 0) == position_id for fill in row.get("fills") or []):
                return row
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("position_id", type=int)
    parser.add_argument("--repair", action="store_true")
    args = parser.parse_args()

    close = recorded_close(args.position_id)
    if close is None:
        raise SystemExit(f"No recorded close found for position {args.position_id}")
    fills = close.get("fills") or []
    if not fills:
        raise SystemExit("Recorded close has no fills; cannot preserve its thesis context")
    if not mt5.initialize(path=paper_executor.DEFAULT_TERMINAL):
        raise SystemExit(f"MT5 unavailable: {mt5.last_error()}")
    try:
        if mt5.positions_get(ticket=args.position_id):
            raise SystemExit("Position is still open; refusing to finalize its journal")
        since = datetime.fromisoformat(str(fills[0]["filled_at_utc"]).replace("Z", "+00:00"))
        outcome = paper_executor.realized_execution_outcome(fills, since)
    finally:
        mt5.shutdown()

    broker_count = int(outcome["exit_deal_count"])
    recorded_count = int(close.get("exit_deal_count") or 0)
    summary = {
        "position_id": args.position_id,
        "proposal_id": close.get("proposal_id"),
        "recorded_exit_deals": recorded_count,
        "broker_exit_deals": broker_count,
        "corrected_net_pnl": round(float(outcome["net_pnl"]), 2),
        "exit_legs": outcome["exit_legs"],
    }
    print(json.dumps(summary, indent=2))
    if broker_count <= recorded_count and close.get("exit_legs"):
        print("Journal already contains all broker exit legs.")
        return 0
    if not args.repair:
        print("Report only. Re-run with --repair to append and materialize the correction.")
        return 0

    corrected = dict(close)
    corrected.update({
        "created_at_utc": (
            outcome["exit_legs"][-1].get("closed_at_utc")
            or datetime.now(timezone.utc).isoformat()
        ),
        "reason": outcome["reason"],
        "exit_price": outcome["exit_price"],
        "gross_pnl": outcome["gross_pnl"],
        "costs": outcome["costs"],
        "net_pnl": outcome["net_pnl"],
        "close_comments": outcome["close_comments"],
        "pnl_is_complete": outcome["pnl_is_complete"],
        "exit_deal_count": broker_count,
        "exit_legs": outcome["exit_legs"],
        "attribution_source": outcome["attribution_source"],
        "manager_close_decision": outcome["manager_close_decision"],
        "partial_close_reconciled": True,
        "supersedes_created_at_utc": close.get("created_at_utc"),
    })
    paper_executor.append_event(corrected)
    journal_closed_trade(corrected)
    print("Corrected close appended and trade journal updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
