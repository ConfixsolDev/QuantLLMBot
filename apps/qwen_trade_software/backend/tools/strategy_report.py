#!/usr/bin/env python3
"""Closed-trade results, grouped by the build that produced them.

2026-08-11 -- why this refuses to pool
--------------------------------------
A study of 71 closed trades across four days concluded almost nothing, because
every split tested collapsed into a date effect. Confidence band, structure
metadata and side mix were each near-perfectly confounded with the day the code
changed:

    "high confidence loses money"          was really  "2026-08-10 lost money"
    "trades with structure metadata lose"  was really  "2026-08-10 lost money"
    "the sell side is weak"                reversed entirely within-day

Pooling across builds is not a reporting inconvenience. It manufactures
conclusions that are the opposite of the truth, and acting on them costs real
money. So this tool will not do it: results are reported per build_id, and a
build with too few trades is reported as "not enough", never as a number that
invites a decision.

Rows written before 2026-08-11 carry no build_id and are grouped under
"pre-manifest" — they are shown, but they cannot be compared to anything,
because nothing records what produced them.

Usage
-----
    python tools/strategy_report.py
    python tools/strategy_report.py --min-sample 12
    python tools/strategy_report.py --build 9ee4796d3b36
"""

from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"

# Below this, print the shortfall instead of a verdict. Matches the ledger's
# promotion threshold so the two tools never disagree about what "enough" means.
DEFAULT_MIN_SAMPLE = 12
PRE_MANIFEST = "pre-manifest"


def load_closed() -> list[dict]:
    """Closed trades with settled P&L, joined to their proposal."""
    proposals: dict[str, dict] = {}
    for path in sorted(LOG_DIR.glob("paper-proposals-*.jsonl")):
        for line in path.open(encoding="utf-8", errors="ignore"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("proposal_id"):
                proposals[row["proposal_id"]] = row

    trades: list[dict] = []
    for path in sorted(LOG_DIR.glob("paper-executions-*.jsonl")):
        for line in path.open(encoding="utf-8", errors="ignore"):
            if '"mt5_execution_closed"' not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("event") != "mt5_execution_closed":
                continue
            if row.get("net_pnl") is None:
                continue
            # A trade whose closing deal never settled reports the entry
            # commission as its result. Including it drags every average toward
            # -3.50 and makes real differences look like noise.
            if row.get("pnl_is_complete") is False:
                continue
            # Reconstructed rows carry real broker P&L but no observed path or
            # entry context. They belong in the totals -- the money was real --
            # and are flagged so a configuration breakdown built from them is
            # not mistaken for observed behaviour.
            reconstructed = bool(row.get("reconstructed_from_broker"))
            proposal = proposals.get(row.get("proposal_id")) or {}
            plan = ((proposal.get("qwen") or {}).get("execution_plan") or {})
            trades.append({
                "build_id": row.get("build_id") or PRE_MANIFEST,
                "reconstructed": reconstructed,
                "build_dirty": bool(row.get("build_dirty")),
                "pnl": float(row["net_pnl"]),
                "reason": row.get("reason"),
                "side": plan.get("side"),
                "frame": plan.get("structure_timeframe"),
                "trigger_tf": proposal.get("timeframe"),
                "session": (proposal.get("qwen") or {}).get("session")
                           or proposal.get("session"),
                "geometry_source": next(
                    (f.get("sl_source") for f in (row.get("fills") or [])), None
                ),
            })
    return trades


def configuration_key(t: dict) -> str:
    return "|".join(str(t.get(k) or "?") for k in
                    ("frame", "side", "session", "trigger_tf", "geometry_source"))


def summarise(values: list[float]) -> str:
    wins = sum(1 for v in values if v > 0)
    return (f"n={len(values):>3}  net {sum(values):>+9.2f}  "
            f"avg {st.mean(values):>+8.2f}  win {100*wins/len(values):>3.0f}%")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-sample", type=int, default=DEFAULT_MIN_SAMPLE)
    parser.add_argument("--build", help="restrict to one build_id")
    args = parser.parse_args()

    trades = load_closed()
    if not trades:
        print("No closed trades with settled P&L.")
        return 0
    if args.build:
        trades = [t for t in trades if t["build_id"].startswith(args.build)]

    by_build: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_build[t["build_id"]].append(t)

    print("=" * 78)
    print(" STRATEGY REPORT — results are never pooled across builds")
    print("=" * 78)

    if len(by_build) > 1:
        print(f"\n  {len(by_build)} distinct builds present. They are reported")
        print("  separately below and MUST NOT be combined: different code")
        print("  produced them, so a pooled average describes no real system.")

    for build_id in sorted(by_build, key=lambda b: -len(by_build[b])):
        group = by_build[build_id]
        pnl = [t["pnl"] for t in group]
        dirty = any(t["build_dirty"] for t in group)
        print("\n" + "-" * 78)
        print(f"  BUILD {build_id}{'   (DIRTY — differs from the declared freeze)' if dirty else ''}")
        print("-" * 78)
        print(f"  overall    {summarise(pnl)}")
        rebuilt = [t for t in group if t["reconstructed"]]
        if rebuilt:
            print(f"  of which reconstructed from the broker: {len(rebuilt)} "
                  f"(net {sum(t['pnl'] for t in rebuilt):+.2f}) — real money,")
            print("        but no observed trade path; excluded from training.")
        if build_id == PRE_MANIFEST:
            print("  note: these rows predate build stamping. Nothing records what")
            print("        produced them, so they cannot be compared to anything.")

        if len(pnl) < args.min_sample:
            print(f"\n  NOT ENOUGH DATA — {len(pnl)} of {args.min_sample} trades needed")
            print("  before any breakdown here is worth reading. Shown for")
            print("  completeness only; do not act on it.")

        by_config: dict[str, list[float]] = defaultdict(list)
        for t in group:
            by_config[configuration_key(t)].append(t["pnl"])
        ranked = sorted(by_config.items(), key=lambda kv: sum(kv[1]))
        print(f"\n  by configuration  (frame|side|session|trigger|geometry):")
        for key, values in ranked[:6]:
            marker = "" if len(values) >= args.min_sample else "  [under-sampled]"
            print(f"    {summarise(values)}  {key}{marker}")
        if len(ranked) > 6:
            print(f"    ... {len(ranked)-6} more configurations")

        by_reason: dict[str, list[float]] = defaultdict(list)
        for t in group:
            by_reason[str(t["reason"])].append(t["pnl"])
        print("\n  by exit reason:")
        for reason, values in sorted(by_reason.items(), key=lambda kv: sum(kv[1])):
            print(f"    {summarise(values)}  {reason}")

    print("\n" + "=" * 78)
    if len(by_build) > 1:
        print("  Reminder: the totals above belong to different systems.")
        print("  Freeze the build to make results accumulate into one sample.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
