#!/usr/bin/env python3
"""V5 pack: ATR3/51 regime hint + pullback location + calibrated confidence.

Doctrine: topics 07 (trend/pullback), 08 (range mid skip), 09 (reversal restraint).
Ratio is a hint only — never a hard dollar/ratio gate.

Usage
-----
    python python_utilities_for_models/append_regime_atr_v5.py --dry-run
    python python_utilities_for_models/append_regime_atr_v5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
SPIKE = 4449.92
H1_HIGH = 4414.61
DAY_LOW = 4406.32
PULLBACK = 4418.50
RANGE_MID = 4410.0
RANGE_HIGH = 4413.0
RANGE_LOW = 4397.0


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl = (
        f"SPIKE_EXTREME={SPIKE}, H1_PREVIOUS_HIGH={H1_HIGH}, "
        f"DAY_LOW={DAY_LOW}, PULLBACK_RESISTANCE={PULLBACK}, "
        f"RANGE_HIGH={RANGE_HIGH}, RANGE_MID={RANGE_MID}, RANGE_LOW={RANGE_LOW}"
    )
    # Illustrative ratios for teaching (stamped ATR from day still on row).
    concept = (
        "Concept: Regime first (trend vs range; ATR3/ATR51 as expand/compress "
        "hint), then location (pullback or outer third), then a closed trigger. "
        "Confidence tracks how complete that stack is — not how loud the pin is."
    )
    rows: list[tuple[dict, dict, dict]] = []

    # rg_001 expand → wait pullback (spike sell lesson)
    rows.append(
        (
            s2(
                "rg_001",
                "07_trend_trading",
                "Expand regime — wait; do not sell the spike",
                (
                    f"atr_ratio_3_51 elevated (~1.8) after spike to {SPIKE}. "
                    "Bearish bias forming, but price is still at the impulse extreme."
                ),
                "Wait for pullback after expand",
                f"Closed fail below {H1_HIGH} then rally reject",
                "wait because expand/climax location is not a with-trend entry",
            ),
            s3(
                "rg_001",
                "atr_expand_requires_pullback",
                (
                    "If atr_ratio_3_51 is clearly elevated vs recent baseline AND "
                    "price is at the impulse extreme → wait|skip for with-trend "
                    "entry until a pullback to mapped resistance/support. Ratio "
                    "labels regime; it does not flip direction alone."
                ),
                ["atr_m1_3", "atr_m1_51", "atr_ratio_3_51", "impulse_extreme", "mapped_zone"],
                ["action=wait", "missing_fact=pullback_after_expand"],
            ),
            s4(
                eid="rg_001",
                detector="atr_expand_requires_pullback",
                decision="Wait for pullback after expand",
                conditions=f"high atr_ratio_3_51 near spike {SPIKE}; no pullback",
                action="wait",
                direction="none",
                confidence=52,
                auction="transition",
                key_levels=kl,
                missing_fact="pullback_after_expand",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — expand print at {SPIKE} is climax "
                    "location (live −147 class), not L2/pullback sell."
                ),
                confirmation_reason=(
                    f"Confirmation still missing: closed M5 rejection at "
                    f"{PULLBACK}/{H1_HIGH} after expand cools. M1 pin at the "
                    "spike is noise."
                ),
            ),
        )
    )

    # rg_002 sold the low after expand cooled — still wait
    rows.append(
        (
            s2(
                "rg_002",
                "07_trend_trading",
                "Normal ratio at day low — still wait for resistance pullback",
                (
                    f"After expand, atr_ratio_3_51 ~1.0 at day low {DAY_LOW}. "
                    "Bearish bias intact but location is the structure low."
                ),
                "Wait for rally to resistance",
                f"Closed M5 reject at {PULLBACK}",
                "wait because normal vol at the low is still before-pullback",
            ),
            s3(
                "rg_002",
                "structure_low_before_pullback_wait",
                (
                    "Bearish context + price at session/structure low + no closed "
                    "rejection at mapped resistance above → wait even if "
                    "atr_ratio_3_51 has normalized."
                ),
                ["active_scenario", "session_low", "mapped_resistance", "atr_ratio_3_51"],
                ["action=wait", "missing_fact=closed_rejection_at_pullback_resistance"],
            ),
            s4(
                eid="rg_002",
                detector="structure_low_before_pullback_wait",
                decision="Wait for rally to resistance",
                conditions=f"sell bias at day low {DAY_LOW}; ratio normal; no pullback",
                action="wait",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl,
                missing_fact="closed_rejection_at_pullback_resistance",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — same class as live −162: side OK, "
                    f"location is {DAY_LOW} before the pullback sell."
                ),
                confirmation_reason=(
                    f"Need closed M5 bearish rejection at {PULLBACK}/{H1_HIGH}. "
                    "Do not treat an M1 pin at the low as confirmation."
                ),
            ),
        )
    )

    # rg_003 compress at support → open buy (well-formed)
    rows.append(
        (
            s2(
                "rg_003",
                "07_trend_trading",
                "Compress after flush — buy closed M5 at pivot support",
                (
                    f"Flush into {DAY_LOW}; atr_ratio_3_51 compresses (~0.6). "
                    "Closed M5 bullish rejection at D1/H1 pivot support."
                ),
                "Long scalp at pivot after compress",
                f"Closed M5 acceptance back below {DAY_LOW}",
                "buy because location is support + closed M5 + quieter regime",
            ),
            s3(
                "rg_003",
                "compress_edge_closed_m5_entry",
                (
                    "After a flush, if atr_ratio_3_51 is compressed vs the spike "
                    "and a closed M5 rejection prints at mapped support → open "
                    "with moderate confidence (stack complete, not pin-only)."
                ),
                ["atr_ratio_3_51", "mapped_support", "closed_M5_rejection"],
                ["action=open", "direction=buy", "confidence=58-72"],
            ),
            s4(
                eid="rg_003",
                detector="compress_edge_closed_m5_entry",
                decision="Long scalp at pivot after compress",
                conditions="compress ratio + closed M5 reject at day-low pivot",
                action="open",
                direction="buy",
                confidence=68,
                auction="rejection",
                key_levels=kl,
                entry=4407.8,
                sl=4400.0,
                tp=4418.5,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: buy — compress after flush at pivot with "
                    "closed M5 response (well-formed +121 class), not M1 chase."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 bullish rejection holding above "
                    f"{DAY_LOW}. M1 wick alone would be wait."
                ),
            ),
        )
    )

    # rg_004 mid-range skip
    rows.append(
        (
            s2(
                "rg_004",
                "08_range_trading",
                "Sideways mid — skip both sides",
                (
                    f"Asia/London box {RANGE_LOW}-{RANGE_HIGH}; price near mid "
                    f"{RANGE_MID}. Overlapping bars; atr_ratio_3_51 normal."
                ),
                "Skip mid-range",
                "N/A",
                "skip because middle of range is ~50/50 (Brooks/Grimes/Dalton)",
            ),
            s3(
                "rg_004",
                "range_mid_skip",
                (
                    "If auction is two-sided box and live price is in the middle "
                    "third → skip. Outer-third fades only; ratio cannot invent "
                    "direction in the mid."
                ),
                ["range_high", "range_low", "live_price", "atr_ratio_3_51"],
                ["action=skip", "skip_reason_code=empty_midrange"],
            ),
            s4(
                eid="rg_004",
                detector="range_mid_skip",
                decision="Skip mid-range",
                conditions=f"price ~{RANGE_MID} inside {RANGE_LOW}-{RANGE_HIGH}",
                action="skip",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl,
                skip_code="empty_midrange",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: skip mid-range — topic 08; pins in the "
                    "middle are not outer-third fades."
                ),
                confirmation_reason=(
                    "Confirmation N/A under mid-range skip. Wait for a closed "
                    "response at the outer third, not another M1 pin mid-box."
                ),
            ),
        )
    )

    # rg_005 pullback sell after expand — open conf 70
    rows.append(
        (
            s2(
                "rg_005",
                "07_trend_trading",
                "After expand cools — sell closed M5 at pullback resistance",
                (
                    f"Spike failed; acceptance below {H1_HIGH}. Pullback into "
                    f"{PULLBACK}; closed M5 rejection; ratio no longer extreme."
                ),
                "Short scalp on pullback",
                f"Closed M5 acceptance above {H1_HIGH}",
                "sell because regime+location+closed M5 stack is complete",
            ),
            s3(
                "rg_005",
                "regime_pullback_m5_short",
                (
                    "Bearish after failed spike + pullback into mapped resistance "
                    "+ closed M5 rejection + atr_ratio_3_51 not still climaxing "
                    "at the extreme → open sell. Confidence mid (58-72), not 85+."
                ),
                ["bearish_context", "pullback_zone", "closed_M5_rejection", "atr_ratio_3_51"],
                ["action=open", "direction=sell", "confidence=58-72"],
            ),
            s4(
                eid="rg_005",
                detector="regime_pullback_m5_short",
                decision="Short scalp on pullback",
                conditions=f"pullback reject at {PULLBACK} after failed spike",
                action="open",
                direction="sell",
                confidence=70,
                auction="rejection",
                key_levels=kl,
                entry=PULLBACK,
                sl=4424.5,
                tp=DAY_LOW,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell pullback at {PULLBACK} with closed "
                    "M5 — correct location after expand, not the spike/low."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 bearish rejection at/under "
                    f"{H1_HIGH} on the pullback."
                ),
            ),
        )
    )

    # rg_006 pin-only high conf is wrong — wait / low conf
    rows.append(
        (
            s2(
                "rg_006",
                "07_trend_trading",
                "Pin-only story — do not emit high confidence ready",
                (
                    "M1 pin at a named level with no regime read, no pullback "
                    "context, and no closed M5. Model tempted to print conf 80+."
                ),
                "Wait — pin alone incomplete",
                "Closed M5 at mapped zone after regime+location",
                "wait because confidence must reflect stack completeness",
            ),
            s3(
                "rg_006",
                "pin_only_low_confidence_wait",
                (
                    "If the only evidence is an M1 pin + level name → wait (or "
                    "open only with conf 50-62 when other facts are already "
                    "present). Reserve 70+ for regime+location+closed M5."
                ),
                ["m1_pin", "mapped_level", "closed_M5", "atr_ratio_3_51"],
                ["action=wait", "confidence<=62"],
            ),
            s4(
                eid="rg_006",
                detector="pin_only_low_confidence_wait",
                decision="Wait — pin alone incomplete",
                conditions="M1 pin at level; missing pullback and closed M5",
                action="wait",
                direction="none",
                confidence=55,
                auction="unclear",
                key_levels=kl,
                missing_fact="closed_M5_at_mapped_zone_after_pullback",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — pin vocabulary without regime and "
                    "pullback must not become ready with high %."
                ),
                confirmation_reason=(
                    "Confirmation missing: closed M5 response at the mapped "
                    "pullback zone. Do not raise confidence on M1 pin alone."
                ),
            ),
        )
    )

    # rg_007 outer-third fade in range — open moderate
    rows.append(
        (
            s2(
                "rg_007",
                "08_range_trading",
                "Range outer third — fade with closed M5",
                (
                    f"Two-sided box {RANGE_LOW}-{RANGE_HIGH}; price probes "
                    f"{RANGE_HIGH} and closed M5 rejects back inside."
                ),
                "Short fade at range high",
                f"Closed M5 acceptance above {RANGE_HIGH}",
                "sell fade at outer third with closed M5, not mid-box",
            ),
            s3(
                "rg_007",
                "range_outer_third_m5_fade",
                (
                    "Balance/range + price in outer third + closed M5 rejection "
                    "back into the box → open fade. Confidence moderate."
                ),
                ["range_high", "range_low", "closed_M5_rejection"],
                ["action=open", "direction=sell", "confidence=58-68"],
            ),
            s4(
                eid="rg_007",
                detector="range_outer_third_m5_fade",
                decision="Short fade at range high",
                conditions=f"closed M5 reject at {RANGE_HIGH} inside box",
                action="open",
                direction="sell",
                confidence=64,
                auction="rejection",
                key_levels=kl,
                entry=RANGE_HIGH,
                sl=4418.0,
                tp=RANGE_MID,
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell outer-third fade with closed M5 "
                    "(topic 08) — not a mid-range pin."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 rejection from {RANGE_HIGH} back "
                    "into the box."
                ),
            ),
        )
    )

    # rg_008 reversal restraint — climax is not opposite trend entry
    rows.append(
        (
            s2(
                "rg_008",
                "09_reversal_trading",
                "Climax after trend — wait; expect range not instant reverse",
                (
                    "Protracted bear channel then large opposite spike bar. "
                    "atr_ratio_3_51 expands. Temptation: buy reversal with high %."
                ),
                "Wait — climax is not opposite-trend entry",
                "Closed structure for new range or always-in flip",
                "wait because successful reversals usually birth a range first",
            ),
            s3(
                "rg_008",
                "climax_not_instant_opposite_trend",
                (
                    "Potential climax / expand opposite bar after a trend → "
                    "wait|skip for counter-trend open. Do not print high "
                    "confidence buy/sell as a new opposite trend."
                ),
                ["prior_trend", "climax_bar", "atr_ratio_3_51"],
                ["action=wait", "confidence<=55"],
            ),
            s4(
                eid="rg_008",
                detector="climax_not_instant_opposite_trend",
                decision="Wait — climax is not opposite-trend entry",
                conditions="expand climax after trend; no new range structure yet",
                action="wait",
                direction="none",
                confidence=48,
                auction="transition",
                key_levels=kl,
                missing_fact="new_range_or_always_in_flip",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — topic 09: climax restrains "
                    "with-trend chase and does not authorize an instant "
                    "opposite-trend open at high confidence."
                ),
                confirmation_reason=(
                    "Confirmation for a new side needs closed M5 acceptance of "
                    "a new structure (range edge or always-in flip), not the "
                    "climax bar alone."
                ),
            ),
        )
    )

    # rg_009 / rg_010 more calibrated opens and waits
    rows.append(
        (
            s2(
                "rg_009",
                "07_trend_trading",
                "Complete stack open — confidence mid, not 85+",
                (
                    "Trend channel bearish; L2 pullback into EMA/resistance; "
                    "closed M5 rejection; atr_ratio_3_51 normal."
                ),
                "Short L2 pullback",
                "Closed M5 acceptance above pullback high",
                "sell with conf ~72 because stack is complete but not rare A+",
            ),
            s3(
                "rg_009",
                "complete_stack_mid_confidence_open",
                (
                    "Regime trend + pullback location + closed M5 → open with "
                    "confidence 65-75. Reserve 80+ only when multiple closed "
                    "confirmations and clear always-in align."
                ),
                ["always_in", "pullback_zone", "closed_M5", "atr_ratio_3_51"],
                ["action=open", "confidence=65-75"],
            ),
            s4(
                eid="rg_009",
                detector="complete_stack_mid_confidence_open",
                decision="Short L2 pullback",
                conditions="bear channel L2 + closed M5 reject; ratio normal",
                action="open",
                direction="sell",
                confidence=72,
                auction="rejection",
                key_levels=kl,
                entry=4416.0,
                sl=4422.0,
                tp=4406.0,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell L2 pullback with closed M5 — "
                    "complete stack earns mid confidence, not 85+."
                ),
                confirmation_reason=(
                    "Confirmation: closed M5 rejection at the L2 pullback zone."
                ),
            ),
        )
    )

    rows.append(
        (
            s2(
                "rg_010",
                "08_range_trading",
                "Breakout attempt in expand — fade not chase until accepted",
                (
                    f"Range high {RANGE_HIGH} pierced on expand atr_ratio_3_51; "
                    "no closed M5 acceptance outside the box."
                ),
                "Wait for accept or failed-break fade",
                "Closed M5 acceptance outside or reject back inside",
                "wait — most range breakouts fail; do not chase the pierce",
            ),
            s3(
                "rg_010",
                "range_breakout_expand_wait",
                (
                    "Range + first pierce with elevated atr_ratio_3_51 and no "
                    "closed M5 acceptance outside → wait. Prefer failed-break "
                    "fade after closed reject back inside."
                ),
                ["range_high", "atr_ratio_3_51", "closed_M5_acceptance_outside"],
                ["action=wait"],
            ),
            s4(
                eid="rg_010",
                detector="range_breakout_expand_wait",
                decision="Wait for accept or failed-break fade",
                conditions=f"pierce of {RANGE_HIGH} on expand; no M5 accept outside",
                action="wait",
                direction="none",
                confidence=50,
                auction="transition",
                key_levels=kl,
                missing_fact="closed_M5_accept_or_failed_break",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — topic 08 ~80% breakout failures; "
                    "expand pierce is not yet acceptance."
                ),
                confirmation_reason=(
                    "Confirmation either: closed M5 acceptance outside the box, "
                    "or closed M5 reject back inside for the fade."
                ),
            ),
        )
    )

    return rows


PRINCIPLES = [
    {
        "principle_id": "regime_then_location_then_trigger",
        "topic": "trend_trading",
        "lesson": (
            "Decide regime first (trend vs range; ATR3/ATR51 as expand/compress "
            "hint), then location (pullback or outer third), then a closed "
            "trigger — prefer closed M5. Confidence equals stack completeness."
        ),
        "practice": (
            "Before ready open, name regime, name the zone, require closed M5 "
            "at that zone. If atr_ratio_3_51 is climax-elevated at the extreme, "
            "wait for pullback."
        ),
        "guardrail": (
            "Do not hard-code ratio thresholds as live gates. Do not print "
            "80%+ confidence on M1 pin + level name alone."
        ),
        "evidence_label": "strong",
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
        examples, principles=PRINCIPLES, dry_run=args.dry_run, label="regime-atr"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
