#!/usr/bin/env python3
"""End-to-end acceptance check. Gates the freeze.

Verifies, for every closed trade, that the whole chain is present, consistent,
and joinable:

    Qwen entry log ─▶ proposal ─▶ fill ─▶ tick path ─▶ management ─▶ exit
                                                            │
                                              build identity on every link

Ten consecutive trades passing every check is the evidence for declaring a
freeze. Anything less and the verdict says so.

Why each check exists -- every one is a fault that actually happened here:

    prompt joinable      proposal_id was null on all 3,703 entry decisions, so
                         no trade could ever be joined to the prompt that
                         produced it
    build identity       nothing recorded which build produced a trade, so four
                         days of different behaviour were pooled and every
                         conclusion drawn from them was a date effect
    tick path present    the executor died on every monitor tick and seven
                         trades lost their path and their close record
    P&L settled          a close read before the exit deal reached history
                         reported the entry commission as the result
    exit attributed      the manager's own closes were filed as "external"
    management context   a close decision recorded the action but not what the
                         manager saw, so "was closing right" was unanswerable

Usage
-----
    python tools/acceptance_check.py                 # today
    python tools/acceptance_check.py --trades 10     # last 10 closed trades
    python tools/acceptance_check.py --verbose       # per-check detail
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"

REQUIRED_MANAGEMENT_CONTEXT = (
    "r_multiple", "target_progress", "decided_by", "executed",
    "planned_target_level_id", "planned_invalidation_level_id",
    "peak_favorable_price_move", "giveback_price",
)


def _rows(pattern: str, must_contain: str | None = None):
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


def gather() -> dict:
    data = {
        "entry_decisions": {},   # proposal_id -> record
        "proposals": {},
        "started": {},
        "fills": defaultdict(list),
        "closes": [],
        "path_by_execution": Counter(),
        "management_by_proposal": defaultdict(list),
    }
    for row in _rows("qwen-decisions-*.jsonl"):
        kind = row.get("decision_type")
        if kind == "entry" and row.get("proposal_id"):
            data["entry_decisions"][row["proposal_id"]] = row
        elif kind == "management":
            pid = (row.get("context") or {}).get("entry_proposal_id")
            if pid:
                data["management_by_proposal"][pid].append(row)

    for row in _rows("paper-proposals-*.jsonl"):
        if row.get("proposal_id"):
            data["proposals"][row["proposal_id"]] = row

    for row in _rows("paper-executions-*.jsonl"):
        event, pid = row.get("event"), row.get("proposal_id")
        if event == "mt5_execution_started" and pid:
            data["started"][pid] = row
        elif event == "mt5_fill" and pid:
            data["fills"][pid].append(row)
        elif event == "mt5_execution_closed":
            data["closes"].append(row)

    for row in _rows("paper-path-*.jsonl"):
        if row.get("execution_id"):
            data["path_by_execution"][row["execution_id"]] += 1
    return data


def check_trade(close: dict, data: dict) -> tuple[list[tuple[str, bool, str]], str]:
    """Return (checks, build_id) for one closed trade."""
    pid = close.get("proposal_id")
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    decision = data["entry_decisions"].get(pid)
    proposal = data["proposals"].get(pid)
    fills = data["fills"].get(pid) or []
    management = data["management_by_proposal"].get(pid) or []
    execution_id = close.get("execution_id")

    # --- entry side ---
    add("qwen entry log joinable", decision is not None,
        "" if decision else "no entry decision carries this proposal_id")
    add("prompt stored", bool(decision and decision.get("prompt_text")),
        "" if decision and decision.get("prompt_text") else "prompt missing")
    add("model response stored", bool(decision and decision.get("raw_response")))
    add("proposal recorded", proposal is not None)
    add("execution started", pid in data["started"])
    add("fill recorded", bool(fills))

    # --- trade path ---
    ticks = data["path_by_execution"].get(execution_id, 0)
    add("tick path recorded", ticks > 0, f"{ticks} monitor rows")

    # --- management ---
    add("management reviewed the trade", bool(management),
        f"{len(management)} decision(s)")
    if management:
        ctx = management[-1].get("context") or {}
        missing = [k for k in REQUIRED_MANAGEMENT_CONTEXT if k not in ctx]
        add("management decision context complete", not missing,
            f"missing {missing}" if missing else f"{len(ctx)} fields")
    else:
        add("management decision context complete", False, "no decisions")

    # --- exit side ---
    add("exit recorded", True, str(close.get("reason")))
    add("P&L settled", close.get("pnl_is_complete") is True,
        "" if close.get("pnl_is_complete") is True
        else f"pnl_is_complete={close.get('pnl_is_complete')}")
    add("exit attributed", bool(close.get("attribution_source")),
        str(close.get("attribution_source")))

    # --- identity ---
    build = close.get("build_id")
    add("build stamped on exit", bool(build), str(build))
    builds = {
        b for b in (
            build,
            (proposal or {}).get("build_id"),
            ((decision or {}).get("context") or {}).get("build_id"),
            *[(m.get("context") or {}).get("build_id") for m in management],
        ) if b
    }
    add("one build across the whole chain", len(builds) <= 1,
        f"{sorted(builds)}" if len(builds) > 1 else str(build or "-"))
    add("build not dirty", close.get("build_dirty") is not True,
        "differs from declared freeze" if close.get("build_dirty") else "")

    return checks, str(build or "unstamped")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=int, default=10,
                        help="how many of the most recent closed trades to check")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    data = gather()

    # Only trades that actually held a position. signal_expired never filled,
    # so it has no path and no management and would fail checks it should
    # never have been subject to.
    closes = [c for c in data["closes"] if c.get("net_pnl") is not None]
    closes.sort(key=lambda c: c.get("created_at_utc") or "")
    closes = closes[-args.trades:]

    print("=" * 78)
    print(f" ACCEPTANCE CHECK — {len(closes)} closed trade(s), target {args.trades}")
    print("=" * 78)

    if not closes:
        print("\n  No closed trades with a realised P&L yet. Nothing to verify.")
        return 1

    totals: Counter = Counter()
    failures: Counter = Counter()
    per_trade = []
    builds: Counter = Counter()

    for close in closes:
        checks, build = check_trade(close, data)
        builds[build] += 1
        passed = sum(1 for _, ok, _ in checks if ok)
        per_trade.append((close, checks, passed, len(checks)))
        for name, ok, _ in checks:
            totals[name] += 1
            if not ok:
                failures[name] += 1

    print(f"\n  {'when':<10}{'proposal':<34}{'result':<10}{'checks'}")
    print("  " + "-" * 74)
    for close, checks, passed, total in per_trade:
        when = (close.get("created_at_utc") or "")[11:19]
        pid = str(close.get("proposal_id") or "-")[-30:]
        pnl = close.get("net_pnl")
        mark = "PASS" if passed == total else "FAIL"
        print(f"  {when:<10}{pid:<34}{f'{pnl:+.2f}':<10}{passed}/{total} {mark}")
        if args.verbose or passed != total:
            for name, ok, detail in checks:
                if ok and not args.verbose:
                    continue
                flag = "ok  " if ok else "FAIL"
                print(f"      [{flag}] {name}" + (f"  — {detail}" if detail else ""))

    print("\n  " + "-" * 74)
    print("  checks that failed at least once:")
    if not failures:
        print("    none — every link verified on every trade")
    for name, count in failures.most_common():
        print(f"    {count:>3}/{totals[name]:<3}  {name}")

    print(f"\n  builds represented: {dict(builds)}")

    clean = sum(1 for _, checks, p, t in per_trade if p == t)
    print("\n" + "=" * 78)
    if clean == len(per_trade) == args.trades and len(builds) == 1:
        print(f"  READY TO FREEZE — {clean}/{args.trades} trades passed every check")
        print("  on a single build.")
        print("\n    python tools/freeze_build.py --declare")
        verdict = 0
    elif len(builds) > 1:
        print(f"  NOT READY — {len(builds)} builds in the sample. The code changed")
        print("  mid-window, so these trades do not describe one system. Restart")
        print("  on a settled build and gather the run again.")
        verdict = 1
    elif clean < len(per_trade):
        print(f"  NOT READY — {len(per_trade) - clean} of {len(per_trade)} trades have")
        print("  a broken link. Fix what is listed above, then re-run.")
        verdict = 1
    else:
        print(f"  KEEP GOING — {clean} clean trade(s), {args.trades} wanted.")
        verdict = 1
    print("=" * 78)
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
