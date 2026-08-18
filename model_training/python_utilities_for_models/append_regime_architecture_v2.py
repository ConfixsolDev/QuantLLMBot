#!/usr/bin/env python3
"""V2 architecture Phase 4 pack: regime vocabulary, confirmations, H4 geometry.

Doctrine: store/core_skill.md [regime-reading] + sop entry 1.12.
Process: model_training/CURRICULUM_AND_DATA_PREP.md

Usage
-----
    python python_utilities_for_models/append_regime_architecture_v2.py --dry-run
    python python_utilities_for_models/append_regime_architecture_v2.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
RANGE_HIGH = 4413.0
RANGE_LOW = 4397.0
RANGE_MID = 4410.0
H1_HIGH = 4414.61
H4_SUPPORT = 4388.0
H4_RESIST = 4420.0
M5_LIVE_HIGH = 4413.0
PULLBACK = 4406.32

KL = (
    f"RANGE_HIGH={RANGE_HIGH}, RANGE_LOW={RANGE_LOW}, RANGE_MID={RANGE_MID}, "
    f"H1_PREVIOUS_HIGH={H1_HIGH}, H4_SUPPORT={H4_SUPPORT}, "
    f"H4_RESISTANCE={H4_RESIST}, M5_LIVE_H_4413={M5_LIVE_HIGH}, "
    f"M15_PULLBACK={PULLBACK}"
)
CONCEPT = (
    "Concept: Read regime_context (range|trend|breakout|exhaustion) then "
    "location then a closed trigger. Python's hint is overridable. "
    "confirmation_context labels CHoCH/BOS/FVG/sweep on closed M1/M5 — "
    "interpret at the zone, never invent. Confidence tracks stack completeness. "
    "H4 thesis needs H4-scale stop (>=10) and target (>=20) or skip."
)


def _row(
    eid,
    topic,
    title,
    setup,
    decision,
    invalidation,
    why,
    detector,
    logic,
    inputs,
    outputs,
    action,
    direction,
    confidence,
    auction,
    trade_reason,
    confirmation_reason,
    atr,
    *,
    skip_code=None,
    missing_fact=None,
    entry=0.0,
    sl=0.0,
    tp=0.0,
    frame="H1",
    trigger_tf="M5",
    target_mode=None,
    role=None,
    management_action=None,
    thesis_state=None,
):
    return (
        s2(eid, topic, title, setup, decision, invalidation, why),
        s3(eid, detector, logic, inputs, outputs),
        s4(
            eid=eid,
            detector=detector,
            decision=decision,
            conditions=setup,
            action=action,
            direction=direction,
            confidence=confidence,
            auction=auction,
            key_levels=KL,
            trade_reason=f"{CONCEPT} {trade_reason}",
            confirmation_reason=confirmation_reason,
            atr=atr,
            skip_code=skip_code,
            missing_fact=missing_fact,
            entry=entry,
            sl=sl,
            tp=tp,
            frame=frame,
            role=role,
            trigger_tf=trigger_tf,
            target_mode=target_mode,
            management_action=management_action,
            thesis_state=thesis_state,
        ),
    )


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    rows: list[tuple[dict, dict, dict]] = []

    rows.append(
        _row(
            "ra_001",
            "08_range_trading",
            "Clear range boundaries — fade edge at 70, scalp",
            (
                f"regime_context.regime_hint=range; range_support={RANGE_LOW} "
                f"range_resistance={RANGE_HIGH}; closed M5 reject at RANGE_HIGH."
            ),
            "Open scalp sell at range high",
            f"Closed M5 accept above {RANGE_HIGH}",
            "range with clear boundaries earns mid-70 confidence, not 90",
            "regime_range_fade_edge",
            (
                "If regime_hint=range AND both edges named AND closed reject at "
                "the outer third → open scalp to opposing M5 edge. Confidence ~70."
            ),
            ["regime_context", "RANGE_HIGH", "closed_m5"],
            ["action=open", "target_mode=scalp", "confidence~70"],
            "open",
            "sell",
            70,
            "rejection",
            f"Reason: fade RANGE_HIGH {RANGE_HIGH} with closed M5; target RANGE_LOW.",
            "Confirmation: closed M5 rejection at named range resistance.",
            atr,
            entry=4412.4,
            sl=4419.5,
            tp=4397.0,
            target_mode="scalp",
        )
    )
    rows.append(
        _row(
            "ra_002",
            "08_range_trading",
            "Unclear regime — wait at 40, never ready with confidence 0",
            (
                "regime_hint=unknown; mixed swings; no named range edges; "
                "M1 pin only at RANGE_MID."
            ),
            "Wait — incomplete stack",
            "Named edges plus closed reject or accept",
            "unclear regime scores ~40 and waits; ready never pairs with 0",
            "regime_unclear_wait",
            (
                "If regime_hint is unknown or mixed AND no closed response at a "
                "mapped edge → wait, confidence ~40. Never confidence=0 with ready."
            ),
            ["regime_context", "RANGE_MID"],
            ["action=wait", "confidence~40"],
            "wait",
            "none",
            40,
            "balance",
            "Reason: mid-box plus unknown regime is not a trade.",
            "Confirmation: none — forming M1 pin is not a closed response.",
            atr,
            skip_code="missing_closed_response",
            missing_fact="named_range_edge_and_closed_reject",
        )
    )
    rows.append(
        _row(
            "ra_003",
            "08_range_trading",
            "Override Python trend hint when bodies overlap the box",
            (
                "regime_hint=trend but overlapping M5 bodies between "
                f"{RANGE_LOW} and {RANGE_HIGH}; no HH/HL."
            ),
            "Treat as range — wait mid / fade only at edge",
            "Closed accept outside the box",
            "candles outrank regime_hint when they disagree",
            "regime_hint_overridable",
            (
                "If Python regime_hint=trend but closed M5 shows two-sided overlap "
                "inside named RANGE_HIGH/RANGE_LOW → override to range in summary; "
                "do not run a starter basket."
            ),
            ["regime_context", "RANGE_HIGH", "RANGE_LOW", "recent_closed"],
            ["action=wait", "target_mode=scalp"],
            "wait",
            "none",
            48,
            "balance",
            "Reason: override trend hint; this is still a box.",
            "Confirmation: overlapping M5 bodies, no closed accept outside.",
            atr,
            missing_fact="closed_accept_or_edge_reject",
        )
    )
    rows.append(
        _row(
            "ra_004",
            "07_trend_trading",
            "Trend pullback — starter_basket, not the impulse high",
            (
                f"regime_hint=trend hh_hl; pullback to M15_PULLBACK={PULLBACK}; "
                "closed M5 reclaim. Not at H1_PREVIOUS_HIGH extreme."
            ),
            "Open buy starter at pullback",
            f"Closed fail below {PULLBACK}",
            "with-trend entry is the pullback, confidence mid-60s",
            "regime_trend_pullback",
            (
                "If regime_hint=trend AND price is at mapped pullback (not impulse "
                "extreme) AND closed M5 reclaim → open starter_basket."
            ),
            ["regime_context", "M15_PULLBACK", "closed_m5"],
            ["action=open", "target_mode=starter_basket", "confidence~68"],
            "open",
            "buy",
            68,
            "acceptance",
            f"Reason: buy pullback {PULLBACK} with closed M5; keep HTF target.",
            "Confirmation: closed M5 reclaim at M15_PULLBACK.",
            atr,
            entry=4406.5,
            sl=4397.0,
            tp=4414.61,
            target_mode="starter_basket",
        )
    )
    rows.append(
        _row(
            "ra_005",
            "09_reversal_trading",
            "Exhaustion at extreme — wait pullback",
            (
                f"regime_hint=exhaustion after spike toward H1_PREVIOUS_HIGH="
                f"{H1_HIGH}; atr_ratio_3_51 elevated; no pullback."
            ),
            "Wait for pullback after exhaustion",
            "Pullback to mapped resistance then closed reject",
            "do not sell the spike",
            "regime_exhaustion_wait",
            (
                "If regime_hint=exhaustion at the impulse extreme → wait. "
                "Scalp only after a pullback reject."
            ),
            ["regime_context", "H1_PREVIOUS_HIGH", "atr_ratio_3_51"],
            ["action=wait", "missing_fact=pullback_after_exhaustion"],
            "wait",
            "none",
            52,
            "transition",
            "Reason: exhaustion is a wait, not a chase.",
            "Confirmation: none at a pullback zone yet.",
            atr,
            missing_fact="pullback_after_exhaustion",
        )
    )
    rows.append(
        _row(
            "ra_006",
            "02_market_structure",
            "CHoCH at mapped high — interpret, then M1 failure sells",
            (
                f"confirmation_context.m5.choch=bearish at RANGE_HIGH={RANGE_HIGH}; "
                "closed M1 failure back inside the zone."
            ),
            "Open scalp sell after CHoCH plus M1 fail",
            f"Closed M5 accept above {RANGE_HIGH}",
            "CHoCH is evidence at the zone, not a standalone chase",
            "choch_at_zone_with_m1_fail",
            (
                "If m5 choch is bearish AT a mapped resistance AND closed M1 failed "
                "to close through the zone → ready sell scalp. Do not sell CHoCH "
                "in the middle of the range."
            ),
            ["confirmation_context", "RANGE_HIGH", "closed_m1"],
            ["action=open", "target_mode=scalp"],
            "open",
            "sell",
            66,
            "rejection",
            "Reason: bearish CHoCH plus M1 failure at RANGE_HIGH.",
            "Confirmation: supplied m5 choch bearish and closed M1 fail inside zone.",
            atr,
            entry=4412.2,
            sl=4419.0,
            tp=4397.0,
            trigger_tf="M1",
            target_mode="scalp",
        )
    )
    rows.append(
        _row(
            "ra_007",
            "06_fvg_imbalance",
            "Unfilled FVG is context — wait without a zone response",
            (
                "confirmation_context.m5.fvg bullish unfilled; price not at "
                f"RANGE_LOW={RANGE_LOW}; no closed reclaim."
            ),
            "Wait — FVG alone is not an entry",
            f"Closed reclaim at {RANGE_LOW}",
            "do not invent or trade FVG as permission",
            "fvg_context_not_entry",
            (
                "If only an unfilled FVG is supplied and price is not responding "
                "at a mapped zone → wait. FVG is measuring context."
            ),
            ["confirmation_context", "RANGE_LOW"],
            ["action=wait", "missing_fact=closed_response_at_zone"],
            "wait",
            "none",
            42,
            "balance",
            "Reason: unfilled FVG without a zone failure is not ready.",
            "Confirmation: FVG listed; no closed M5 at RANGE_LOW.",
            atr,
            missing_fact="closed_response_at_zone",
        )
    )
    rows.append(
        _row(
            "ra_008",
            "04_timeframe_relations",
            "H4 thesis with H4-scale stop and target",
            (
                f"H4 support {H4_SUPPORT} reclaim; structure_timeframe=H4; "
                "invalidation 12 points below entry; target 20 points to H4_RESISTANCE."
            ),
            "Open H4 continuation",
            f"Closed H4 fail below {H4_SUPPORT}",
            "H4 thesis uses 10–20 point geometry, not a 3-point scalp stop",
            "h4_scale_geometry",
            (
                "If the thesis is H4, SL must be >=10 gold points beyond named "
                "H4 invalidation and TP >=20 to the next H4 opposing level, "
                "else skip. Do not compress H4 into M1 geometry."
            ),
            ["H4_SUPPORT", "H4_RESISTANCE", "structure_timeframe"],
            ["action=open", "sl_usd>=10", "tp_usd>=20"],
            "open",
            "buy",
            64,
            "acceptance",
            "Reason: H4 reclaim with H4-scale stop and target.",
            "Confirmation: closed H4 hold above H4_SUPPORT.",
            atr,
            entry=4400.0,
            sl=4388.0,
            tp=4420.0,
            frame="H4",
            trigger_tf="H4",
            target_mode="starter_basket",
        )
    )
    rows.append(
        _row(
            "ra_009",
            "04_timeframe_relations",
            "H4 thesis with 3-point room — skip",
            (
                "H4 story named but nearest invalidation is only 3 points from "
                "entry; no farther H4 level on the map."
            ),
            "Skip — H4 thesis needs H4-scale stop or skip",
            "Named H4 invalidation with >=10 points",
            "do not hide bad H4 geometry behind a 3-point stop",
            "h4_tight_geometry_skip",
            (
                "If structure_timeframe=H4 and usable stop room <10 or target "
                "room <20 → skip. Never pad by inventing a level."
            ),
            ["H4_SUPPORT", "structure_timeframe"],
            ["action=skip", "skip_reason_code=insufficient_h4_geometry"],
            "skip",
            "none",
            44,
            "balance",
            "Reason: H4 thesis cannot fit a 3-point stop.",
            "Confirmation: none — geometry fails before trigger.",
            atr,
            skip_code="insufficient_h4_geometry",
            frame="H4",
            trigger_tf="H4",
        )
    )
    rows.append(
        _row(
            "ra_010",
            "02_market_structure",
            "live_map double_top plus M1 failure — sell",
            (
                f"live_map.double_top id=M5_LIVE_H_4413 at {M5_LIVE_HIGH}; "
                "tests=2; closed M1 probed and failed to close above the zone."
            ),
            "Open scalp sell at mapped double top",
            f"Closed M5 accept above {M5_LIVE_HIGH}",
            "second test plus M1 fail is the trigger; first test is a watch",
            "live_map_double_top_m1_fail",
            (
                "If live_map.double_top is supplied AND closed M1 failure at that "
                "zone → ready sell scalp. Do not require a routine extra M5 BOS."
            ),
            ["live_map", "M5_LIVE_H_4413", "closed_m1"],
            ["action=open", "target_mode=scalp"],
            "open",
            "sell",
            72,
            "rejection",
            "Reason: mapped double top with closed M1 failure.",
            "Confirmation: live_map.double_top plus M1 fail inside the band.",
            atr,
            entry=4412.6,
            sl=4419.5,
            tp=4397.0,
            trigger_tf="M1",
            target_mode="scalp",
        )
    )
    rows.append(
        _row(
            "ra_011",
            "02_market_structure",
            "live_map first_test_high — wait, not a double top",
            (
                f"live_map near M5_LIVE_H_4413 pattern=first_test_high; "
                "tests=1; no M1 failure yet."
            ),
            "Wait for second test or closed M1 fail",
            "Second visit plus M1 fail",
            "first test maps the zone; it does not sell it",
            "live_map_first_test_wait",
            (
                "If live_map pattern is first_test_high/low → wait. A double_top "
                "requires two tests and a closed M1 failure."
            ),
            ["live_map", "M5_LIVE_H_4413"],
            ["action=wait", "missing_fact=second_test_or_m1_fail"],
            "wait",
            "none",
            46,
            "balance",
            "Reason: first test is a watch, not an entry.",
            "Confirmation: none — no M1 failure, tests=1.",
            atr,
            missing_fact="second_test_or_m1_fail",
        )
    )
    rows.append(
        _row(
            "ra_012",
            "08_range_trading",
            "Range management — close at opposing M5, do not trail as trend",
            (
                f"In-trade sell; regime_hint=range; price at RANGE_LOW={RANGE_LOW}; "
                "M1 still favorable but opposing boundary reached."
            ),
            "Close range scalp at opposing M5",
            "N/A — target response",
            "range management takes the far edge; it does not become a basket",
            "regime_range_mgmt_close",
            (
                "If regime_hint=range and the opposing M5 boundary prints a "
                "response → close. Do not hold for H1 because Python once said trend."
            ),
            ["regime_context", "RANGE_LOW"],
            ["management_action=close", "thesis_state=target_response"],
            "skip",
            "sell",
            74,
            "rejection",
            "Reason: range scalp completed at RANGE_LOW.",
            "Confirmation: opposing M5 boundary reached on closed M5.",
            atr,
            role="management",
            management_action="close",
            thesis_state="target_response",
        )
    )
    rows.append(
        _row(
            "ra_013",
            "07_trend_trading",
            "Trend management — hold M5 noise; close only on M15+ reject",
            (
                "In-trade buy; regime_hint=trend; M5 wick against; M15 still "
                f"holds above M15_PULLBACK={PULLBACK}."
            ),
            "Hold — M5 noise is not H1 invalidation",
            f"Closed M15 fail below {PULLBACK}",
            "trend hold ignores M5 bounce-back; Qwen owns the hold",
            "regime_trend_mgmt_hold",
            (
                "If regime_hint=trend and only M5 is adverse while M15+ invalidation "
                "is intact → hold. Close on closed M15/H1 reject, not M5 noise."
            ),
            ["regime_context", "M15_PULLBACK"],
            ["management_action=hold", "thesis_state=valid"],
            "wait",
            "buy",
            71,
            "acceptance",
            "Reason: trend thesis still valid on M15.",
            "Confirmation: M5 wick only; M15 close still above pullback.",
            atr,
            role="management",
            management_action="hold",
            thesis_state="valid",
        )
    )
    return rows


PRINCIPLES = [
    {
        "principle_id": "regime_hint_then_candles",
        "topic": "regime_reading",
        "lesson": (
            "regime_context is Python's range|trend|breakout|exhaustion hint. "
            "Manage and target from that hint, but override it when closed "
            "candles show overlap (range) or a closed accept (breakout)."
        ),
        "practice": (
            "Name the hint, name the override if any, then set target_mode "
            "scalp (range/exhaustion) or starter_basket (trend/breakout)."
        ),
        "guardrail": (
            "Do not treat regime_hint as a fill gate. Do not emit confidence 0 "
            "with status ready."
        ),
        "evidence_label": "strong",
    },
    {
        "principle_id": "h4_needs_h4_geometry",
        "topic": "timeframe_relations",
        "lesson": (
            "An H4 thesis needs H4-scale invalidation (>=10 gold points) and "
            "target room (>=20) or skip."
        ),
        "practice": "If the only stop is 3 points, skip the H4 idea.",
        "guardrail": "Never invent a farther H4 level to force geometry.",
        "evidence_label": "strong",
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    atr = day_atr(DAY)
    examples = build(atr)
    print(f"examples={len(examples)} atr={atr}")
    append_examples(
        examples,
        principles=PRINCIPLES,
        dry_run=args.dry_run,
        label="regime-architecture-v2",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
