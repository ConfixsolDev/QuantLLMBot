#!/usr/bin/env python3
"""Score the geometry observation window against realised P&L.

During the observation window (QWEN_SKIP_ON_GEOMETRY=0) the risk gate records
every entry it WOULD have refused but does not block it. This report joins those
observations to what the trades actually did, so the decision to enforce or
relax the gate is made on evidence rather than on opinion.

The question it answers:

    Of the entries geometry wanted to refuse, what did they earn?

    If refused-group P&L is clearly negative and accepted-group positive,
    the gate is earning its keep -> set QWEN_SKIP_ON_GEOMETRY=1.

    If the refused group is profitable, the gate is filtering out good trades
    -> keep it off, or lower QWEN_MIN_REWARD_RISK further.

    If neither group has enough trades, keep observing. Two or three trades
    decide nothing, whichever way they fall.

Usage
-----
    python tools/geometry_observation_report.py
    python tools/geometry_observation_report.py --days 3
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"

# Below this many closed trades in a group, say so rather than pretending the
# number means something.
MIN_SAMPLE = 8


def _rows(days: int, wanted: str):
    """Yield decoded events of one type from the execution logs, newest days only."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for path in sorted(LOG_DIR.glob("paper-executions-*.jsonl")):
        try:
            handle = path.open(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        with handle:
            for line in handle:
                # Cheap substring test first: the monitor event dominates these
                # files by roughly 200:1, so parsing every line is wasteful.
                if wanted not in line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("event") != wanted:
                    continue
                stamp = str(row.get("created_at_utc") or "")
                try:
                    when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                except ValueError:
                    when = None
                if when and when < cutoff:
                    continue
                yield row


def load_observations(days: int) -> dict[str, dict]:
    """proposal_id -> the geometry verdict recorded at entry."""
    return {
        row["proposal_id"]: row
        for row in _rows(days, "geometry_observation")
        if row.get("proposal_id")
    }


def load_outcomes(days: int) -> dict[str, tuple[str, float]]:
    """proposal_id -> (exit reason, net P&L) from the close record."""
    outcomes: dict[str, tuple[str, float]] = {}
    for row in _rows(days, "mt5_execution_closed"):
        proposal_id = row.get("proposal_id")
        if not proposal_id or row.get("net_pnl") is None:
            continue
        # A trade whose closing deal never settled reports the entry commission
        # as its result. Including it would drag both groups toward -3.50 and
        # make the comparison read as "no difference".
        if row.get("pnl_is_complete") is False:
            continue
        outcomes[proposal_id] = (
            str(row.get("reason") or "unknown"),
            float(row["net_pnl"]),
        )
    return outcomes


def summarise(name: str, pnl: list[float]) -> str:
    if not pnl:
        return f"  {name:34} no closed trades"
    wins = sum(1 for p in pnl if p > 0)
    net = sum(pnl)
    note = "" if len(pnl) >= MIN_SAMPLE else "   << sample too small to decide"
    return (
        f"  {name:34} n={len(pnl):>3}  net {net:>+9.2f}  "
        f"avg {net/len(pnl):>+8.2f}  win {100*wins/len(pnl):>3.0f}%{note}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=2)
    args = parser.parse_args()

    observations = load_observations(args.days)
    outcomes = load_outcomes(args.days)

    refused_pnl: list[float] = []
    accepted_pnl: list[float] = []
    by_reason: dict[str, list[float]] = defaultdict(list)
    exits = Counter()

    for proposal_id, (exit_reason, pnl) in outcomes.items():
        observation = observations.get(proposal_id)
        if observation:
            refused_pnl.append(pnl)
            by_reason[observation.get("reason_code", "unknown")].append(pnl)
            exits[exit_reason] += 1
        else:
            accepted_pnl.append(pnl)

    print("=" * 74)
    print(f" GEOMETRY OBSERVATION WINDOW — last {args.days} day(s)")
    print("=" * 74)
    print(f"\n  observations recorded : {len(observations)}")
    print(f"  of which closed       : {len(refused_pnl)}\n")

    print(summarise("geometry WOULD HAVE REFUSED", refused_pnl))
    print(summarise("geometry accepted", accepted_pnl))

    if by_reason:
        print("\n  by refusal reason:")
        for code, values in sorted(by_reason.items(), key=lambda kv: sum(kv[1])):
            print(summarise(f"    {code}", values))

    if exits:
        print("\n  how the would-be-refused trades ended:")
        for reason, count in exits.most_common():
            print(f"    {reason:32} {count}")

    print("\n" + "-" * 74)
    if len(refused_pnl) < MIN_SAMPLE:
        print(f"  VERDICT: keep observing — only {len(refused_pnl)} closed trades in the")
        print(f"           refused group, need at least {MIN_SAMPLE} before this means anything.")
    elif sum(refused_pnl) < 0 and sum(accepted_pnl) >= 0:
        print("  VERDICT: the gate is earning its keep — the trades it wanted to refuse")
        print("           lost money while the ones it accepted did not.")
        print("           -> set QWEN_SKIP_ON_GEOMETRY=1")
    elif sum(refused_pnl) > 0:
        print("  VERDICT: the gate is filtering out profitable trades.")
        print("           -> keep it off, or lower QWEN_MIN_REWARD_RISK further.")
    else:
        print("  VERDICT: inconclusive — both groups point the same way.")
        print("           The gate is not the variable that matters here.")
    print("-" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
