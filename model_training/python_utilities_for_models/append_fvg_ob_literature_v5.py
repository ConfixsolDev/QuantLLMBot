#!/usr/bin/env python3
"""V5 pack: FVG/OB as literature ancestors only (topics 05–06) — 3 examples.

Maps:
- FVG → Brooks micro measuring gap / Dalton thin print (context zone or target)
- Order block → impulse-origin / failed-reversal signal bar as magnet

Not ICT confluence stacks. One HTF bias + one zone + one closed M5 trigger.

Usage
-----
    python python_utilities_for_models/append_fvg_ob_literature_v5.py --dry-run
    python python_utilities_for_models/append_fvg_ob_literature_v5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
GAP_LO = 4410.0
GAP_HI = 4412.5
ORIGIN = 4416.0
SUPPORT = 4406.32


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl = (
        f"MICRO_GAP={GAP_LO}-{GAP_HI}, IMPULSE_ORIGIN={ORIGIN}, "
        f"SUPPORT={SUPPORT}"
    )
    concept = (
        "Concept: Treat 'FVG' as a micro measuring gap / thin print (Brooks/"
        "Dalton) and 'order block' as the impulse-origin signal bar — location "
        "context under HTF bias, not a standalone ICT stack."
    )
    rows: list[tuple[dict, dict, dict]] = []

    # fvg_001 — gap as pullback zone after bearish displacement (with bias)
    rows.append(
        (
            s2(
                "fvg_001",
                "06_fvg_imbalance",
                "Micro gap as pullback sell zone — with HTF bearish",
                (
                    f"Bearish displacement left a thin print {GAP_LO}-{GAP_HI}. "
                    "Price pulls back into the band; closed M5 rejects."
                ),
                "Short at micro-gap pullback",
                f"Closed M5 acceptance above {GAP_HI}",
                "sell the pullback into the thin print under bearish regime",
            ),
            s3(
                "fvg_001",
                "micro_gap_pullback_with_bias",
                (
                    "HTF/always-in bearish + three-bar non-overlap thin print "
                    "above price + pullback into that band + closed M5 rejection "
                    "→ open sell. Alias word FVG allowed only as this geometry."
                ),
                ["htf_bearish", "micro_gap_band", "closed_M5_rejection"],
                ["action=open", "direction=sell"],
            ),
            s4(
                eid="fvg_001",
                detector="micro_gap_pullback_with_bias",
                decision="Short at micro-gap pullback",
                conditions=f"bearish + pullback into {GAP_LO}-{GAP_HI} + closed M5",
                action="open",
                direction="sell",
                confidence=68,
                auction="rejection",
                key_levels=kl,
                entry=(GAP_LO + GAP_HI) / 2,
                sl=4418.0,
                tp=SUPPORT,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell — thin print is the pullback "
                    "location under bearish bias, confirmed by closed M5."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 rejection inside/at {GAP_LO}-"
                    f"{GAP_HI}. Do not buy the gap as a standalone fill myth."
                ),
            ),
        )
    )

    # fvg_002 — gap alone without bias → wait
    rows.append(
        (
            s2(
                "fvg_002",
                "06_fvg_imbalance",
                "Thin print alone — wait (no HTF bias)",
                (
                    f"A three-bar non-overlap prints {GAP_LO}-{GAP_HI} with no "
                    "clear always-in / range-edge context."
                ),
                "Wait — gap is not a trade by itself",
                "HTF regime + closed M5 at the band",
                "wait because FVG geometry without regime is incomplete",
            ),
            s3(
                "fvg_002",
                "micro_gap_without_regime_wait",
                (
                    "Micro gap / FVG geometry with unclear HTF regime → wait. "
                    "Brooks uses the structure to project; Dalton reads thin "
                    "prints as auction endings — neither is a blind fill entry."
                ),
                ["micro_gap_band", "htf_regime"],
                ["action=wait", "missing_fact=htf_regime"],
            ),
            s4(
                eid="fvg_002",
                detector="micro_gap_without_regime_wait",
                decision="Wait — gap is not a trade by itself",
                conditions="thin print present; regime unclear",
                action="wait",
                direction="none",
                confidence=50,
                auction="unclear",
                key_levels=kl,
                missing_fact="htf_regime_before_gap_entry",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — do not stack ICT fill claims; "
                    "regime first."
                ),
                confirmation_reason=(
                    "Confirmation needs named HTF regime plus closed M5 at the "
                    "band — the gap alone is not enough."
                ),
            ),
        )
    )

    # fvg_003 — impulse origin (order-block ancestor) as magnet
    rows.append(
        (
            s2(
                "fvg_003",
                "05_ict_concepts",
                "Impulse-origin bar as pullback magnet (OB ancestor)",
                (
                    f"Bearish impulse launched from signal bar near {ORIGIN}. "
                    "Price later revisits that origin; closed M5 rejects."
                ),
                "Short at impulse-origin revisit",
                f"Closed M5 acceptance above {ORIGIN}",
                "sell the origin revisit under bearish always-in",
            ),
            s3(
                "fvg_003",
                "impulse_origin_revisit_entry",
                (
                    "Bearish always-in + revisit of the impulse-origin / "
                    "failed-reversal signal bar + closed M5 rejection → open "
                    "sell. Alias 'order block' only as this origin zone — not "
                    "a multi-confluence ICT stack."
                ),
                ["always_in_bearish", "impulse_origin_zone", "closed_M5_rejection"],
                ["action=open", "direction=sell"],
            ),
            s4(
                eid="fvg_003",
                detector="impulse_origin_revisit_entry",
                decision="Short at impulse-origin revisit",
                conditions=f"revisit {ORIGIN} + closed M5 reject; bearish context",
                action="open",
                direction="sell",
                confidence=66,
                auction="rejection",
                key_levels=kl,
                entry=ORIGIN,
                sl=4422.0,
                tp=SUPPORT,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell — impulse-origin magnet (Brooks "
                    "signal-bar ancestor) with closed M5; one zone only."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 rejection at impulse origin "
                    f"{ORIGIN}. Do not require FVG+OB+breaker confluence."
                ),
            ),
        )
    )

    return rows


PRINCIPLES = [
    {
        "principle_id": "fvg_ob_as_literature_zones_only",
        "topic": "ict_concepts",
        "lesson": (
            "FVG and order-block words are aliases for micro measuring gap / "
            "thin print and impulse-origin signal bar. They refine location "
            "under HTF bias; they are never a standalone multi-confluence stack."
        ),
        "practice": (
            "One bias, one zone (gap band or origin), one closed M5 trigger. "
            "If regime is unclear, wait even when geometry is pretty."
        ),
        "guardrail": (
            "Do not train ICT fill myths or stacked confluence. Prefer "
            "Brooks/Dalton ancestor language in trade_reason."
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
        examples, principles=PRINCIPLES, dry_run=args.dry_run, label="fvg-ob-lit"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
