#!/usr/bin/env python3
"""Export prompt -> decision -> outcome rows for v5/v6 training.

2026-08-11 -- why this could not exist until today
--------------------------------------------------
The prompt sent to the model and the raw response it returned are stored in
qwen-decisions-*.jsonl. The realised P&L is stored in paper-executions-*.jsonl.
The two were never joinable: reviewer.py wrote the decision record BEFORE the
proposal id was minted, so proposal_id was null on all 3,703 entry decisions
ever written. The field existed and was always empty.

Consequence: in months of live trading, not one training pair could be built
from a real trade. The model has never been shown "this exact prompt led to this
exact result".

Minting the id before the model call fixed it. This tool is what that fix is
for.

What is emitted, and what is refused
------------------------------------
Emitted: one row per closed trade with settled P&L, carrying the prompt, the
model's raw response, the decision, the realised outcome, the exit reason, the
manager's own close reasoning, and the build_id.

Refused:
  * trades whose closing deal never settled (pnl_is_complete false) -- their
    net_pnl is the entry commission, and teaching the model a trade "earned
    -3.50" when it earned something else is worse than not teaching it;
  * rows with no prompt -- 1,878 entry decisions are deterministic waits where
    the model was never called, so there is nothing to learn from;
  * mixed builds in one file, unless --allow-mixed. A training set assembled
    from four different behaviours teaches the average of four systems, none of
    which exists.

Usage
-----
    python tools/export_training_pairs.py --out live_pairs.jsonl
    python tools/export_training_pairs.py --build 9ee4796d3b36 --out v5_pairs.jsonl
    python tools/export_training_pairs.py --allow-mixed --out everything.jsonl
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"


def _iter(pattern: str, must_contain: str | None = None):
    for path in sorted(LOG_DIR.glob(pattern)):
        for line in path.open(encoding="utf-8", errors="ignore"):
            if must_contain and must_contain not in line:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def build_rows() -> tuple[list[dict], Counter]:
    skipped: Counter = Counter()

    decisions: dict[str, dict] = {}
    for row in _iter("qwen-decisions-*.jsonl"):
        if row.get("decision_type") != "entry":
            continue
        pid = row.get("proposal_id")
        if not pid:
            skipped["decision has no proposal_id (pre-fix record)"] += 1
            continue
        decisions[pid] = row

    proposals: dict[str, dict] = {}
    for row in _iter("paper-proposals-*.jsonl"):
        if row.get("proposal_id"):
            proposals[row["proposal_id"]] = row

    management: dict[str, dict] = {}
    for row in _iter("qwen-decisions-*.jsonl"):
        if row.get("decision_type") != "management":
            continue
        pid = (row.get("context") or {}).get("entry_proposal_id")
        if pid:
            management[pid] = row

    rows: list[dict] = []
    for close in _iter("paper-executions-*.jsonl", '"mt5_execution_closed"'):
        if close.get("event") != "mt5_execution_closed":
            continue
        pid = close.get("proposal_id")
        if not pid or close.get("net_pnl") is None:
            skipped["close has no proposal_id or no P&L"] += 1
            continue
        if close.get("pnl_is_complete") is False:
            skipped["closing deal never settled (P&L unreliable)"] += 1
            continue
        if close.get("reconstructed_from_broker"):
            # Rebuilt from MT5 deal history after the 2026-08-11 incident. The
            # P&L is the broker's and therefore trustworthy, but the trade path
            # and entry context were never recorded, so the row cannot teach
            # anything about why the trade behaved as it did.
            skipped["reconstructed from broker (no observed trade path)"] += 1
            continue
        decision = decisions.get(pid)
        if not decision:
            skipped["no decision record joinable to this trade"] += 1
            continue
        if not decision.get("prompt_text"):
            skipped["no prompt (deterministic wait, model not called)"] += 1
            continue

        proposal = proposals.get(pid) or {}
        plan = ((proposal.get("qwen") or {}).get("execution_plan") or {})
        pnl = float(close["net_pnl"])
        rows.append({
            "proposal_id": pid,
            "build_id": close.get("build_id") or "pre-manifest",
            "prompt": decision.get("prompt_text"),
            "model": decision.get("model"),
            "raw_response": decision.get("raw_response"),
            "decision": {
                "side": plan.get("side"),
                "confidence": (proposal.get("qwen") or {}).get("confidence"),
                "reason": plan.get("reason"),
                "entry_low": plan.get("entry_low"),
                "entry_high": plan.get("entry_high"),
                "stop_level_id": plan.get("stop_level_id"),
                "target_level_id": plan.get("target_level_id"),
                "structure_timeframe": plan.get("structure_timeframe"),
            },
            "outcome": {
                "net_pnl": pnl,
                "won": pnl > 0,
                "exit_reason": close.get("reason"),
                "holding_seconds": close.get("position_holding_seconds"),
                "peak_favorable_price_move": close.get("peak_favorable_price_move"),
                "price_giveback": close.get("price_giveback"),
                "maximum_drawdown": close.get("maximum_drawdown"),
                "attribution_source": close.get("attribution_source"),
            },
            "management_close": close.get("manager_close_decision"),
        })
    return rows, skipped


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="live_training_pairs.jsonl")
    parser.add_argument("--build", help="only this build_id")
    parser.add_argument("--allow-mixed", action="store_true",
                        help="permit more than one build in the output")
    args = parser.parse_args()

    rows, skipped = build_rows()
    if args.build:
        rows = [r for r in rows if r["build_id"].startswith(args.build)]

    builds = Counter(r["build_id"] for r in rows)

    print("=" * 74)
    print(" TRAINING PAIR EXPORT")
    print("=" * 74)
    print(f"\n  usable pairs : {len(rows)}")
    if skipped:
        print("\n  excluded:")
        for reason, count in skipped.most_common():
            print(f"    {count:>6}  {reason}")

    if builds:
        print("\n  builds present:")
        for build, count in builds.most_common():
            print(f"    {count:>6}  {build}")

    if len(builds) > 1 and not args.allow_mixed:
        print("\n  REFUSING TO WRITE — more than one build in the output.")
        print("  A set assembled from several behaviours teaches the average of")
        print("  systems that never existed. Pass --build <id> to pick one, or")
        print("  --allow-mixed if you have a reason.")
        return 1

    if not rows:
        print("\n  Nothing to write.")
        if skipped.get("decision has no proposal_id (pre-fix record)"):
            print("  All decisions on record predate the proposal_id fix, so no")
            print("  trade can be joined to its prompt. Rows written from now on")
            print("  will be joinable.")
        return 0

    out = Path(args.out)
    with out.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    won = sum(1 for r in rows if r["outcome"]["won"])
    print(f"\n  wrote {out}  ({len(rows)} rows, {won} winners / {len(rows)-won} losers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
