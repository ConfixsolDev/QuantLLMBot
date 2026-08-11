#!/usr/bin/env python3
"""Compare MT5's record of Qwen trades against ours, and repair the gap.

2026-08-11 incident
-------------------
An unregistered log family made append_event raise on every monitor tick. The
exception left the executor's monitor loop, so five positions were opened and
then abandoned: no monitoring, no close record, nothing in the execution log
saying what happened to them. The runner went on to block 24 further proposals
on a position it believed was still open, while trade management reported none.

The logs cannot answer "what happened to those trades", because the records were
never written. MT5's deal history can: it is the broker's own account of every
fill and every close, and it does not depend on our process staying alive.

This tool reads that history, finds Qwen-owned positions (magic 26072401) with
no matching mt5_execution_closed in our logs, and can write the missing close
records so the trade is not lost to strategy review or to training.

Reconstructed rows are marked `reconstructed_from_broker: true` and
`pnl_is_complete: true` -- the P&L is the broker's, which is the authoritative
figure -- but they carry no entry thesis, because the process that held it died.

Usage
-----
    python tools/reconcile_broker_truth.py                 # report only
    python tools/reconcile_broker_truth.py --days 2
    python tools/reconcile_broker_truth.py --repair        # write the records
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

LOG_DIR = BACKEND / "logs"
QWEN_MAGIC = 26072401


def our_closed_position_ids(days: int) -> set[int]:
    """Position ids we have a close record for."""
    ids: set[int] = set()
    for path in sorted(LOG_DIR.glob("paper-executions-*.jsonl")):
        for line in path.open(encoding="utf-8", errors="ignore"):
            if '"mt5_execution_closed"' not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            for fill in row.get("fills") or []:
                if fill.get("order"):
                    ids.add(int(fill["order"]))
    return ids


def our_fills(days: int) -> dict[int, dict]:
    """position_id -> the fill event we recorded, so we can name the proposal."""
    fills: dict[int, dict] = {}
    for path in sorted(LOG_DIR.glob("paper-executions-*.jsonl")):
        for line in path.open(encoding="utf-8", errors="ignore"):
            if '"mt5_fill"' not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            fill = row.get("fill") or {}
            if fill.get("order"):
                fills[int(fill["order"])] = row
    return fills


def broker_positions(days: int) -> dict[int, list]:
    import MetaTrader5 as mt5
    import paper_executor

    if not mt5.initialize(path=paper_executor.DEFAULT_TERMINAL):
        raise SystemExit(f"MT5 unavailable: {mt5.last_error()}")
    try:
        now = datetime.now(timezone.utc)
        deals = mt5.history_deals_get(now - timedelta(days=days), now)
        if deals is None:
            raise SystemExit(f"No deal history: {mt5.last_error()}")
        grouped: dict[int, list] = defaultdict(list)
        for deal in deals:
            if deal.magic != QWEN_MAGIC:
                continue
            grouped[int(deal.position_id)].append(deal)
        return grouped
    finally:
        mt5.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--repair", action="store_true",
                        help="write missing close records into today's log")
    args = parser.parse_args()

    import MetaTrader5 as mt5
    import paper_executor

    grouped = broker_positions(args.days)
    recorded = our_closed_position_ids(args.days)
    fills = our_fills(args.days)

    orphans = []
    for position_id, deals in grouped.items():
        exits = [d for d in deals if d.entry != mt5.DEAL_ENTRY_IN]
        if not exits:
            continue  # still open at the broker; nothing to reconcile
        if position_id in recorded:
            continue
        gross = sum(float(d.profit) for d in deals)
        costs = sum(float(d.commission) + float(d.swap) + float(d.fee) for d in deals)
        volume = sum(float(d.volume) for d in exits)
        orphans.append({
            "position_id": position_id,
            "net_pnl": round(gross + costs, 2),
            "gross_pnl": round(gross, 2),
            "costs": round(costs, 2),
            "exit_price": round(
                sum(float(d.price) * float(d.volume) for d in exits) / volume, 3
            ) if volume else None,
            "closed_at_utc": datetime.fromtimestamp(
                max(d.time for d in exits), timezone.utc
            ).isoformat(),
            "comments": [str(d.comment) for d in exits],
            "proposal_id": (fills.get(position_id) or {}).get("proposal_id"),
            "execution_id": (fills.get(position_id) or {}).get("execution_id"),
        })

    print("=" * 76)
    print(" BROKER RECONCILIATION — MT5 truth vs our records")
    print("=" * 76)
    print(f"\n  Qwen positions closed at the broker : {sum(1 for d in grouped.values() if any(x.entry != mt5.DEAL_ENTRY_IN for x in d))}")
    print(f"  of those, missing from our logs     : {len(orphans)}")

    if not orphans:
        print("\n  Everything the broker closed, we recorded. Nothing to repair.")
        return 0

    total = sum(o["net_pnl"] for o in orphans)
    print(f"\n  UNRECORDED P&L: {total:+.2f} across {len(orphans)} trade(s)\n")
    for o in sorted(orphans, key=lambda x: x["closed_at_utc"]):
        print(f"    {o['closed_at_utc'][11:19]}  pos {o['position_id']}  "
              f"net {o['net_pnl']:>+9.2f}  {','.join(o['comments']) or '(no comment)'}"
              f"  proposal={o['proposal_id'] or 'unknown'}")

    if not args.repair:
        print("\n  Report only. Re-run with --repair to write these into the")
        print("  execution log so strategy review and training can see them.")
        return 0

    written = 0
    for o in orphans:
        paper_executor.append_event({
            "schema_version": 1,
            "event": "mt5_execution_closed",
            "execution_id": o["execution_id"],
            "proposal_id": o["proposal_id"],
            "created_at_utc": o["closed_at_utc"],
            "reason": "reconstructed_from_broker",
            "exit_price": o["exit_price"],
            "gross_pnl": o["gross_pnl"],
            "costs": o["costs"],
            "net_pnl": o["net_pnl"],
            "close_comments": o["comments"],
            "pnl_is_complete": True,
            "exit_deal_count": len(o["comments"]),
            "attribution_source": "broker_reconciliation",
            "manager_close_decision": None,
            # Loud on purpose. These rows have no entry thesis and no trade
            # path -- the process holding them died. They are valid for P&L and
            # for nothing else.
            "reconstructed_from_broker": True,
            "reconstruction_note": (
                "written by tools/reconcile_broker_truth.py after the "
                "2026-08-11 append_event incident; no monitor path, no entry "
                "context, P&L is the broker's own figure"
            ),
        })
        written += 1
    print(f"\n  Wrote {written} reconstructed close record(s).")
    print("  They are marked reconstructed_from_broker so no report or training")
    print("  export mistakes them for fully-observed trades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
