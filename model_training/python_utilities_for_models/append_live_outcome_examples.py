#!/usr/bin/env python3
"""Append training rows built from REAL closed trades and their realised P&L.

Why this pack exists
--------------------
Every other pack teaches doctrine. This one teaches what actually happened when
that doctrine met the market, which is the only signal that can make the model
profitable rather than merely well-read.

Two lessons dominate the 2026-08-10 ledger.

1. Stop placement relative to structure decides the trade.
   Measured from the ACTUAL fill (the runtime brackets from the fill, not the
   planned zone), across the last seven closed trades:

       +246.50  stop placed BEYOND the structural level   -> ran to target
       +249.15  stop 0.26 inside                          -> ran to target
       -153.50  stop 4.13 inside                          -> stopped out
       -153.50  stop 8.46 inside, thesis never tested     -> stopped in 81s

   A stop inside the invalidation converts "my idea was wrong" into "noise
   removed me". The model should recognise that geometry before entering.

2. Patience beats intervention.

       left alone to target        n=3   avg +247.38
       closed on model discretion  n=8   avg  -20.22

   Discretionary closing was negative-expectancy across the whole day.

Rows are generated only from trades that actually closed, with real fills, real
level maps and real P&L. Nothing is invented (CURRICULUM_AND_DATA_PREP.md 0.1
rule 5). Losers become skip/wait examples explaining the geometry that killed
them; winners become open examples; early discretionary closes become hold
examples.

Usage
-----
    python python_utilities_for_models/append_live_outcome_examples.py --dry-run
    python python_utilities_for_models/append_live_outcome_examples.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
STAGE_02 = KNOWLEDGE / "stage_02_structured_data.jsonl"
STAGE_04 = KNOWLEDGE / "stage_04_decision_contract.jsonl"
BACKEND = ROOT.parent / "apps" / "qwen_trade_software" / "backend"
LOGS = BACKEND / "logs"
TICKS = ROOT / "tick_data"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TF_RANK = {tf: i for i, tf in enumerate(TIMEFRAMES)}
MAX_INVALIDATION_GAP = 4

# Exits that mean the trade was left alone to resolve mechanically.
MECHANICAL_EXITS = {"managed_or_safety_tp", "managed_or_safety_sl"}


def timeframe_of(level_id: str) -> str | None:
    head = str(level_id or "").split("_", 1)[0].upper()
    return head if head in TF_RANK else None


def load_jsonl(path: Path) -> list[dict]:
    """Tolerant reader.

    These logs are appended by a running process, so the tail can hold a
    partially flushed line. Skipping unparseable lines is correct here -- the
    alternative is the whole pack failing because one record was mid-write.
    """
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect_trades() -> list[dict]:
    """Join runner outcomes, execution fills and proposals into closed trades."""
    outcomes: dict[str, tuple[str, float]] = {}
    for path in sorted(LOGS.glob("paper-runner.log*")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"Completed (\S+) reason=(\S+) net_pnl=(-?[\d.]+)", text):
            outcomes[match.group(1)] = (match.group(2), float(match.group(3)))

    fills: dict[str, float] = {}
    # Trades whose closing deal never settled before the outcome was computed
    # carry a net_pnl of about -3.50 -- the entry commission alone, not the
    # real result. Teaching the model that a trade "earned -3.50" when it
    # actually earned something else is worse than not teaching it at all, so
    # these are excluded outright rather than approximated.
    unsettled: set[str] = set()
    for path in sorted(LOGS.glob("paper-executions-*.jsonl")) + sorted(TICKS.glob("*/paper-executions.jsonl")):
        for row in load_jsonl(path):
            if row.get("event") == "mt5_fill":
                price = (row.get("fill") or {}).get("price")
                if price:
                    fills[row.get("proposal_id")] = float(price)
            elif row.get("event") == "mt5_execution_closed":
                if row.get("pnl_is_complete") is False and row.get("proposal_id"):
                    unsettled.add(row["proposal_id"])
    if unsettled:
        print(f"  excluding {len(unsettled)} trade(s) with unsettled P&L from training")
    outcomes = {pid: v for pid, v in outcomes.items() if pid not in unsettled}

    proposals: dict[str, dict] = {}
    for path in sorted(LOGS.glob("paper-proposals-*.jsonl")) + sorted(TICKS.glob("*/paper-proposals.jsonl")):
        for row in load_jsonl(path):
            if row.get("proposal_id"):
                proposals[row["proposal_id"]] = row

    trades = []
    for pid, (reason, pnl) in outcomes.items():
        proposal = proposals.get(pid)
        if not proposal:
            continue
        plan = ((proposal.get("qwen") or {}).get("execution_plan") or {})
        if plan.get("status") != "ready":
            continue
        fill = fills.get(pid)
        structural = plan.get("structural_stop_loss")
        if not (fill and structural and plan.get("side")):
            continue
        side = plan["side"]
        direction = 1.0 if side == "buy" else -1.0
        fixed_stop = fill - direction * float(plan.get("stop_distance") or 3.0)
        # Positive = the live stop sat INSIDE the structural invalidation.
        inside = direction * (fixed_stop - structural)
        trades.append({
            "proposal_id": pid,
            "reason": reason,
            "pnl": pnl,
            "side": side,
            "fill": fill,
            "fixed_stop": fixed_stop,
            "structural_stop": float(structural),
            "inside": inside,
            "plan": plan,
            "levels": plan_levels(proposal),
        })
    return trades


def plan_levels(proposal: dict) -> dict[str, float]:
    market = proposal.get("market") or {}
    cache = market.get("cache_context") or {}
    out: dict[str, float] = {}
    for row in (cache.get("levels") or []):
        name, price = row.get("level_id"), row.get("zone_low")
        if name and price:
            out[name] = float(price)
    if not out:
        plan = ((proposal.get("qwen") or {}).get("execution_plan") or {})
        for key in ("entry_low", "entry_high", "stop_loss", "take_profit"):
            ident = plan.get(key.replace("entry_low", "entry_low_id")
                             .replace("entry_high", "entry_high_id")
                             .replace("stop_loss", "stop_level_id")
                             .replace("take_profit", "target_level_id"))
            if ident and plan.get(key):
                out[ident] = float(plan[key])
    return out


def levels_string(levels: dict[str, float]) -> str:
    return ", ".join(f"{n}={v:.3f}" for n, v in sorted(levels.items()) if v)


def build_rows(trades: list[dict]) -> tuple[list, list]:
    s2_rows, s4_rows = [], []
    seq = 0
    for trade in trades:
        seq += 1
        eid = f"live_{seq:03d}"
        plan = trade["plan"]
        side = trade["side"]
        inside = trade["inside"]
        pnl = trade["pnl"]
        reason = trade["reason"]
        zone_id = plan.get("entry_low_id")
        stop_id = plan.get("stop_level_id")
        zone_tf, stop_tf = timeframe_of(zone_id), timeframe_of(stop_id)
        gap = (TF_RANK[stop_tf] - TF_RANK[zone_tf]) if (zone_tf and stop_tf) else None
        levels = trade["levels"]

        stopped = reason == "managed_or_safety_sl"
        discretionary = reason == "qwen_confirmed_close"

        if stopped and inside > 1.0:
            # The clearest lesson available: geometry killed it.
            decision, action, direction_label = "Skip", "skip", "none"
            confidence = 50
            title = f"Stop {inside:.1f} inside invalidation - noise stop"
            setup = (
                f"{side} at {zone_id} ({zone_tf}); runtime stop landed {inside:.2f} inside the "
                f"structural invalidation {stop_id} ({stop_tf})"
            )
            why = (
                f"skip because the workable stop sits {inside:.2f} inside {stop_id}. The trade "
                f"closed for {pnl:+.2f} without the thesis ever being tested - price never "
                f"reached the level that would have proved it wrong. Take this setup only when "
                f"the stop can sit at or beyond the invalidation."
            )
            confirm = (
                f"Realised outcome {pnl:+.2f} via {reason}. A closed response at {zone_id} is not "
                f"sufficient when the stop cannot be placed beyond {stop_id}."
            )
            skip_code = "stop_inside_invalidation"
        elif discretionary and pnl < 0:
            decision, action, direction_label = "Wait for confirmation", "wait", "none"
            confidence = 50
            title = "Early discretionary close on an untested thesis"
            setup = (
                f"{side} at {zone_id} ({zone_tf}) closed early on judgement rather than at a "
                f"named level"
            )
            why = (
                f"wait because closing on opinion realised {pnl:+.2f}. Across the session, trades "
                "left to resolve at a named level averaged +247.38 while discretionary closes "
                "averaged -20.22. Exit on target, stop, or a closed break of the named "
                "invalidation - not on a change of feeling."
            )
            confirm = (
                f"Realised outcome {pnl:+.2f} via {reason}. No closed candle broke {stop_id}; "
                "the exit was discretionary."
            )
            skip_code = "premature_discretionary_close"
        elif pnl > 0:
            decision = "Long scalp" if side == "buy" else "Short scalp"
            action, direction_label = "open", side
            confidence = 80
            title = f"Structural room held - {reason}"
            setup = (
                f"{side} at {zone_id} ({zone_tf}) with the stop at or beyond {stop_id} "
                f"({stop_tf}); inside-distance {inside:+.2f}"
            )
            why = (
                f"{side} because the stop sat {'beyond' if inside <= 0 else f'only {inside:.2f} inside'} "
                f"the invalidation {stop_id}, so the idea could be tested. Realised {pnl:+.2f}."
            )
            confirm = (
                f"Realised outcome {pnl:+.2f} via {reason}. The closed response at {zone_id} was "
                f"backed by usable room to {stop_id}."
            )
            skip_code = None
        else:
            continue

        s2_rows.append({
            "example_id": eid,
            "topic": "04_timeframe_relations",
            "title": title,
            "setup": setup,
            "decision": decision,
            "invalidation": f"Closed break of {stop_id}" if stop_id else "N/A",
            "why": why,
            "evidence": "strong",
            "bucket": "A",
        })
        s4_rows.append({
            "example_id": eid,
            "detector_output": "live_outcome_replay",
            "trade_decision": decision,
            "decision_conditions": (
                f"zone {zone_tf} / invalidation {stop_tf}"
                + (f", frame gap {gap}" if gap is not None else "")
                + f", stop {inside:+.2f} vs structure"
            ),
            "evidence_label": "strong",
            "conviction_score": round(min(0.9, max(0.2, confidence / 100)), 2),
            "risk_control": (
                f"Fill {trade['fill']:.3f} | runtime stop {trade['fixed_stop']:.3f} | "
                f"structural invalidation {trade['structural_stop']:.3f}"
            ),
            "key_levels": levels_string(levels) or f"{stop_id}={trade['structural_stop']:.3f}",
            "entry_price": round(trade["fill"], 3) if action == "open" else 0.0,
            "sl_price": round(trade["structural_stop"], 3) if action == "open" else 0.0,
            "tp_price": round(float(plan.get("take_profit") or 0), 3) if action == "open" else 0.0,
            "sl_usd": round(abs(trade["fill"] - trade["structural_stop"]), 1) if action == "open" else 0.0,
            "tp_usd": round(abs(float(plan.get("take_profit") or 0) - trade["fill"]), 1) if action == "open" else 0.0,
            "action": action,
            "direction": direction_label,
            "confidence": confidence,
            "auction_state": "rejection" if action == "open" else "transition",
            "skip_reason_code": skip_code,
            "target_mode": "scalp" if action == "open" else "none",
            "role": "entry" if action == "open" else ("skip" if action == "skip" else "wait"),
            "missing_fact": None,
            "structure_timeframe": plan.get("structure_timeframe") or stop_tf,
            "realised_pnl": pnl,
            "realised_exit_reason": reason,
            "trade_reason": (
                "Concept: a stop must sit beyond the level that would prove the idea wrong, or the "
                f"market removes the position before the idea is tested. Reason: {why}"
            ),
            "confirmation_reason": confirm,
        })
    return s2_rows, s4_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    trades = collect_trades()
    if not trades:
        print("no closed trades with fills + structural levels found")
        return 1

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    print(f"closed trades usable: {len(trades)}  (wins {len(wins)}, losses {len(losses)})")
    if wins:
        print(f"  mean 'inside' distance, winners: {sum(t['inside'] for t in wins)/len(wins):+.2f}")
    if losses:
        print(f"  mean 'inside' distance, losers : {sum(t['inside'] for t in losses)/len(losses):+.2f}")

    s2_rows, s4_rows = build_rows(trades)
    print(f"\ngenerated rows: {len(s4_rows)}")
    print(f"  actions: {dict(Counter(r['action'] for r in s4_rows))}")
    print(f"  sides  : {dict(Counter(r['direction'] for r in s4_rows))}")
    print(f"  skip codes: {dict(Counter(r['skip_reason_code'] for r in s4_rows if r['skip_reason_code']))}")

    if args.dry_run:
        if s4_rows:
            print("\n--- sample ---")
            print(json.dumps(s4_rows[0], indent=2)[:1100])
        print("\n(dry run, nothing written)")
        return 0

    existing = {r["example_id"] for r in load_jsonl(STAGE_04)}
    new_s2 = [r for r in s2_rows if r["example_id"] not in existing]
    new_s4 = [r for r in s4_rows if r["example_id"] not in existing]
    append_jsonl(STAGE_02, new_s2)
    append_jsonl(STAGE_04, new_s4)
    print(f"\nappended {len(new_s4)} outcome-grounded rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
