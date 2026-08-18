#!/usr/bin/env python3
"""V5 pack: evaluate long and short ideas, then pick or wait (curriculum only).

Live dual-side entry_policy revive stays deferred — prior study found parts
inert/redundant. This pack teaches the model to emit both cases and compare
confidence from stack completeness (topics 07–08 always-in / two-sided range).

Usage
-----
    python python_utilities_for_models/append_dual_side_ideas_v5.py --dry-run
    python python_utilities_for_models/append_dual_side_ideas_v5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
SUPPORT = 4406.32
RESIST = 4418.50
MID = 4412.0


def ideas(long_c, short_c, pick, long_miss=None, short_miss=None, long_zone=None, short_zone=None):
    return {
        "long": {
            "zone": long_zone or f"SUPPORT={SUPPORT}",
            "confidence": long_c,
            "missing_fact": long_miss,
            "viable": long_miss is None and long_c >= 58,
        },
        "short": {
            "zone": short_zone or f"RESISTANCE={RESIST}",
            "confidence": short_c,
            "missing_fact": short_miss,
            "viable": short_miss is None and short_c >= 58,
        },
        "pick": pick,
    }


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl = f"SUPPORT={SUPPORT}, RESISTANCE={RESIST}, MID={MID}"
    concept = (
        "Concept: At each decision point, score the long case and the short "
        "case (zone, missing fact, confidence from stack completeness). Pick "
        "the stronger viable side, or wait if both are weak or the gap is small. "
        "Never force an open every tick (Brooks always-in / two-sided range)."
    )
    rows: list[tuple[dict, dict, dict]] = []

    # ds_001 short wins
    rows.append(
        (
            s2(
                "ds_001",
                "07_trend_trading",
                "Dual-side: short pullback beats incomplete long",
                (
                    f"Bearish always-in. Long would buy {SUPPORT} but flush still "
                    f"active. Short has closed M5 reject at {RESIST}."
                ),
                "Pick short",
                f"Closed M5 accept above {RESIST}",
                "pick short because short stack complete; long still missing",
            ),
            s3(
                "ds_001",
                "dual_side_pick_stronger_stack",
                (
                    "Emit long and short idea scores. If one side has "
                    "regime+location+closed M5 and the other is missing facts → "
                    "pick the complete side. Overall confidence = that side's score."
                ),
                ["long_case", "short_case", "closed_M5", "always_in"],
                ["pick=sell|buy|wait", "side_ideas"],
            ),
            s4(
                eid="ds_001",
                detector="dual_side_pick_stronger_stack",
                decision="Pick short over incomplete long",
                conditions="short pullback complete; long missing response",
                action="open",
                direction="sell",
                confidence=70,
                auction="rejection",
                key_levels=kl,
                entry=RESIST,
                sl=4424.5,
                tp=SUPPORT,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                side_ideas=ideas(
                    48,
                    70,
                    "sell",
                    long_miss="closed_M5_at_support",
                    short_miss=None,
                ),
                trade_reason=(
                    f"{concept} Reason: pick sell — short conf 70 with closed M5 "
                    "at resistance; long conf 48 missing support response."
                ),
                confirmation_reason=(
                    f"Short confirmation: closed M5 reject at {RESIST}. Long "
                    "case remains wait."
                ),
            ),
        )
    )

    # ds_002 both weak → wait
    rows.append(
        (
            s2(
                "ds_002",
                "08_range_trading",
                "Dual-side: both mid/incomplete → wait",
                (
                    f"Price near mid {MID}. Long and short both only have M1 pins "
                    "without closed M5 at outer thirds."
                ),
                "Wait — neither side viable",
                "Closed M5 at outer third",
                "wait because both idea confidences are weak / incomplete",
            ),
            s3(
                "ds_002",
                "dual_side_both_weak_wait",
                (
                    "If both long and short confidences are below viable threshold "
                    "or both missing closed M5 → pick=wait. Do not invent a side."
                ),
                ["long_case", "short_case"],
                ["pick=wait", "action=wait"],
            ),
            s4(
                eid="ds_002",
                detector="dual_side_both_weak_wait",
                decision="Wait — neither side viable",
                conditions="mid-range; both sides pin-only",
                action="wait",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl,
                missing_fact="viable_side_with_closed_M5",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                side_ideas=ideas(
                    52,
                    54,
                    "wait",
                    long_miss="closed_M5_at_outer_third",
                    short_miss="closed_M5_at_outer_third",
                ),
                trade_reason=(
                    f"{concept} Reason: wait — long 52 / short 54 both incomplete; "
                    "gap too small and mid-range."
                ),
                confirmation_reason=(
                    "Need closed M5 at an outer-third zone before either side "
                    "can be picked."
                ),
            ),
        )
    )

    # ds_003 long wins after flush
    rows.append(
        (
            s2(
                "ds_003",
                "07_trend_trading",
                "Dual-side: long at support beats chase short at low",
                (
                    f"After flush, closed M5 holds {SUPPORT}. Short would sell "
                    "the low again (before pullback) — incomplete."
                ),
                "Pick long",
                f"Closed M5 accept below {SUPPORT}",
                "pick long; short is sell-the-low error",
            ),
            s3(
                "ds_003",
                "dual_side_reject_sell_the_low",
                (
                    "When scoring shorts, mark missing_fact=pullback if price is "
                    "at structure low. A complete long at support can win even "
                    "on a bearish day after a flush response."
                ),
                ["long_case", "short_case", "session_low", "closed_M5"],
                ["pick=buy", "short.missing_fact=pullback"],
            ),
            s4(
                eid="ds_003",
                detector="dual_side_reject_sell_the_low",
                decision="Pick long at support",
                conditions="long M5 hold at support; short is low-chase",
                action="open",
                direction="buy",
                confidence=68,
                auction="rejection",
                key_levels=kl,
                entry=4407.8,
                sl=4400.0,
                tp=RESIST,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                side_ideas=ideas(
                    68,
                    45,
                    "buy",
                    long_miss=None,
                    short_miss="pullback_to_resistance",
                ),
                trade_reason=(
                    f"{concept} Reason: pick buy — long stack complete at "
                    f"{SUPPORT}; short conf 45 is sell-the-low (−162 class)."
                ),
                confirmation_reason=(
                    f"Long confirmation: closed M5 hold above {SUPPORT}. Short "
                    "case waits for pullback resistance."
                ),
            ),
        )
    )

    # ds_004 close gap → wait
    rows.append(
        (
            s2(
                "ds_004",
                "08_range_trading",
                "Dual-side: similar scores → wait",
                (
                    "Range day. Long fade at low and short fade at high both "
                    "have partial evidence; scores 60 vs 62."
                ),
                "Wait — confidence gap too small",
                "Clearer closed M5 at one edge",
                "wait when both sides are close; do not coin-flip",
            ),
            s3(
                "ds_004",
                "dual_side_small_gap_wait",
                (
                    "If both sides are viable-ish but confidence gap is small "
                    "(e.g. <8 points) and neither has a clear closed M5 edge → "
                    "pick=wait."
                ),
                ["long_case.confidence", "short_case.confidence"],
                ["pick=wait"],
            ),
            s4(
                eid="ds_004",
                detector="dual_side_small_gap_wait",
                decision="Wait — confidence gap too small",
                conditions="long 60 vs short 62; no clear closed M5 edge",
                action="wait",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl,
                missing_fact="clear_edge_closed_M5",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                side_ideas=ideas(
                    60,
                    62,
                    "wait",
                    long_miss="stronger_closed_M5",
                    short_miss="stronger_closed_M5",
                ),
                trade_reason=(
                    f"{concept} Reason: wait — dual scores too close; forcing a "
                    "side is coin-flip trading."
                ),
                confirmation_reason=(
                    "Wait for a clearer closed M5 at one mapped edge before pick."
                ),
            ),
        )
    )

    # ds_005 one-sided drift correction
    rows.append(
        (
            s2(
                "ds_005",
                "07_trend_trading",
                "Dual-side required — forbids silent one-sided omission",
                (
                    "Model historically emitted only sells. Schema lesson: both "
                    "long and short cases must be scored even when always-in is bearish."
                ),
                "Score both; pick short if only short complete",
                "N/A",
                "always emit both cases; omission is a contract failure",
            ),
            s3(
                "ds_005",
                "dual_side_both_cases_required",
                (
                    "Every dual-side decision must include long and short "
                    "objects. A bearish day still scores the long case (often "
                    "low conf / missing facts) rather than omitting it."
                ),
                ["long_case", "short_case"],
                ["side_ideas.long", "side_ideas.short", "side_ideas.pick"],
            ),
            s4(
                eid="ds_005",
                detector="dual_side_both_cases_required",
                decision="Score both sides; pick short",
                conditions="bearish day; long scored incomplete; short complete",
                action="open",
                direction="sell",
                confidence=66,
                auction="rejection",
                key_levels=kl,
                entry=RESIST,
                sl=4424.0,
                tp=SUPPORT,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                side_ideas=ideas(
                    40,
                    66,
                    "sell",
                    long_miss="no_bullish_context",
                    short_miss=None,
                ),
                trade_reason=(
                    f"{concept} Reason: pick sell after scoring both — long "
                    "explicitly incomplete (40), short complete (66)."
                ),
                confirmation_reason=(
                    f"Short: closed M5 reject at {RESIST}. Long case recorded "
                    "as not viable rather than omitted."
                ),
            ),
        )
    )

    return rows


PRINCIPLES = [
    {
        "principle_id": "dual_side_then_compare_confidence",
        "topic": "market_structure",
        "lesson": (
            "Always score a long idea and a short idea (zone, missing fact, "
            "confidence). Pick the stronger complete stack, or wait if both "
            "are weak or nearly tied."
        ),
        "practice": (
            "Write both cases before choosing action. Confidence is per-side "
            "from regime+location+closed M5, then overall equals the pick."
        ),
        "guardrail": (
            "Do not force an open every tick. Do not omit the non-favoured "
            "side. Live dual-side policy revive remains deferred until this "
            "curriculum is absorbed."
        ),
        "evidence_label": "moderate",
    }
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    atr = day_atr(DAY)
    examples = build(atr)
    print(f"examples={len(examples)} atr={atr}")
    append_examples(
        examples, principles=PRINCIPLES, dry_run=args.dry_run, label="dual-side"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
