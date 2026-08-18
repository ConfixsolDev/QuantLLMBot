#!/usr/bin/env python3
"""V5 pack: Context → Hunt → Arm (three-step trade finding).

Doctrine (topics 04, 07, 08; Elder Triple Screen; Brooks L2 / breakout-pullback):
  1. CONTEXT/PLAN — direction + named hunt band + invalidation
  2. HUNT — price outside band → wait missing_fact=at_entry_location
  3. ARMING — in band → closed M5/M1 confirm → invalidation check → ready

Does not change side doctrine. Dual-side challenger stays optional inside hunt.

Usage
-----
    python python_utilities_for_models/append_entry_location_hunt_v5.py --dry-run
    python python_utilities_for_models/append_entry_location_hunt_v5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
HUNT_LO = 4414.0
HUNT_HI = 4418.0
DAY_LOW = 4406.32
SPIKE = 4449.92
INV = 4424.5


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl = (
        f"HUNT_ZONE={HUNT_LO}-{HUNT_HI}, DAY_LOW={DAY_LOW}, "
        f"SPIKE={SPIKE}, INVALIDATION={INV}"
    )
    concept = (
        "Concept: Three-step trade finding — (1) context/plan sets direction and "
        "hunt band, (2) hunt waits until price is at that band, (3) arming uses "
        "closed M5/M1 at the band then invalidation check. Correct side at the "
        "wrong location is still wait (Brooks pullback / Elder timing)."
    )
    rows: list[tuple[dict, dict, dict]] = []
    hunt_zone = f"{HUNT_LO}-{HUNT_HI}"

    # eh_001 context set, price at low → hunt wait
    rows.append(
        (
            s2(
                "eh_001",
                "07_trend_trading",
                "Sell context set — hunt wait at low (not ready)",
                (
                    f"Plan: SELL. Hunt band {hunt_zone}. Invalidation {INV}. "
                    f"Live price ~{DAY_LOW} (outside hunt). Direction correct."
                ),
                "Wait — at_entry_location",
                f"Price enters {hunt_zone}",
                "wait because step 2 hunt is not satisfied; do not sell the low",
            ),
            s3(
                "eh_001",
                "hunt_wait_outside_entry_location",
                (
                    "If active plan has direction + hunt band and live price is "
                    "outside that band → action=wait, missing_fact=at_entry_location. "
                    "Do not emit ready/open on an M1 pin at the structure extreme."
                ),
                ["plan_side", "hunt_zone", "live_price"],
                ["action=wait", "missing_fact=at_entry_location"],
            ),
            s4(
                eid="eh_001",
                detector="hunt_wait_outside_entry_location",
                decision="Wait — at_entry_location",
                conditions=(
                    f"SELL plan hunt {hunt_zone}; price at {DAY_LOW} outside band"
                ),
                action="wait",
                direction="none",
                confidence=52,
                auction="transition",
                key_levels=kl,
                missing_fact="at_entry_location",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — sell bias OK but price is at "
                    f"{DAY_LOW}, not in hunt {hunt_zone} (live −162 class)."
                ),
                confirmation_reason=(
                    f"Arming not started until price is inside {hunt_zone}. "
                    "M1 pin at the low is not step 3."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone
    rows[-1][2]["direction"] = "sell"  # armed plan side while waiting
    rows[-1][2]["action"] = "wait"

    # eh_002 still hunting — price not arrived
    rows.append(
        (
            s2(
                "eh_002",
                "07_trend_trading",
                "Keep hunting — same band, still outside",
                (
                    f"Prior wait at_entry_location. Price rallied to 4410 but "
                    f"still below hunt {hunt_zone}."
                ),
                "Wait — at_entry_location",
                f"Price enters {hunt_zone}",
                "preserve hunt; do not invent a new lower sell zone",
            ),
            s3(
                "eh_002",
                "hunt_preserve_until_band_touched",
                (
                    "While hunting, do not relocate the sell zone down to the "
                    "live low. Keep the planned hunt band; missing_fact stays "
                    "at_entry_location until touch."
                ),
                ["hunt_zone", "live_price", "prior_missing_fact"],
                ["action=wait", "missing_fact=at_entry_location"],
            ),
            s4(
                eid="eh_002",
                detector="hunt_preserve_until_band_touched",
                decision="Wait — at_entry_location",
                conditions=f"price 4410 still outside hunt {hunt_zone}",
                action="wait",
                direction="sell",
                confidence=50,
                auction="balance",
                key_levels=kl,
                missing_fact="at_entry_location",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — still hunting {hunt_zone}; do not "
                    "collapse entry to the current low."
                ),
                confirmation_reason=(
                    f"Still missing: price inside {hunt_zone} before any M5 arming."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    # eh_003 in zone + M5 → open
    rows.append(
        (
            s2(
                "eh_003",
                "07_trend_trading",
                "In hunt zone — arm with closed M5 then open sell",
                (
                    f"Price enters {hunt_zone}. Closed M5 bearish rejection. "
                    f"Invalidation {INV} still holds."
                ),
                "Short scalp — armed",
                f"Closed M5 accept above {HUNT_HI}",
                "open because steps 1–3 complete",
            ),
            s3(
                "eh_003",
                "hunt_arm_in_zone_closed_m5",
                (
                    "Price inside hunt band + closed M5 rejection in plan "
                    "direction + invalidation intact → open. trigger_tf=M5."
                ),
                ["hunt_zone", "price_in_band", "closed_M5", "invalidation"],
                ["action=open", "direction=sell"],
            ),
            s4(
                eid="eh_003",
                detector="hunt_arm_in_zone_closed_m5",
                decision="Short scalp — armed at hunt zone",
                conditions=f"in {hunt_zone} + closed M5 reject; inv {INV} valid",
                action="open",
                direction="sell",
                confidence=70,
                auction="rejection",
                key_levels=kl,
                entry=(HUNT_LO + HUNT_HI) / 2,
                sl=INV,
                tp=DAY_LOW,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell — hunt satisfied and M5 armed at "
                    f"{hunt_zone}, not at {DAY_LOW}."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 bearish rejection inside {hunt_zone}."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    # eh_004 in zone but no M5 → wait arming
    rows.append(
        (
            s2(
                "eh_004",
                "04_timeframe_relations",
                "In hunt zone — wait for M5 arming",
                (
                    f"Price tags {hunt_zone}. Only M1 noise; no closed M5 "
                    "rejection yet. Invalidation intact."
                ),
                "Wait — closed M5 at hunt zone",
                "Closed M5 rejection in band",
                "step 3 arming incomplete",
            ),
            s3(
                "eh_004",
                "hunt_in_zone_wait_m5_arm",
                (
                    "Price in hunt band but no closed M5 (or M1-only pin) → "
                    "wait. missing_fact names the closed M5 event at the band."
                ),
                ["price_in_band", "closed_M5"],
                ["action=wait", "missing_fact=closed_M5_at_hunt_zone"],
            ),
            s4(
                eid="eh_004",
                detector="hunt_in_zone_wait_m5_arm",
                decision="Wait — closed M5 at hunt zone",
                conditions=f"in {hunt_zone}; M1 pin only",
                action="wait",
                direction="sell",
                confidence=55,
                auction="unclear",
                key_levels=kl,
                missing_fact="closed_M5_at_hunt_zone",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — location OK (step 2 done) but "
                    "arming (step 3) needs closed M5."
                ),
                confirmation_reason=(
                    f"Confirmation missing: closed M5 reject inside {hunt_zone}."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    # eh_005 spike extreme — hunt still the pullback band
    rows.append(
        (
            s2(
                "eh_005",
                "07_trend_trading",
                "After spike — hunt is pullback band not the high",
                (
                    f"Spike to {SPIKE}. Plan SELL. Hunt remains {hunt_zone}, "
                    "not the spike print."
                ),
                "Wait — at_entry_location",
                f"Price revisits {hunt_zone}",
                "do not arm at climax extreme",
            ),
            s3(
                "eh_005",
                "hunt_not_climax_extreme",
                (
                    "After an impulse/spike, hunt band is the pullback/"
                    "breakout-retest zone, never the spike extreme. Wait "
                    "at_entry_location."
                ),
                ["spike_extreme", "hunt_zone", "live_price"],
                ["action=wait", "missing_fact=at_entry_location"],
            ),
            s4(
                eid="eh_005",
                detector="hunt_not_climax_extreme",
                decision="Wait — at_entry_location",
                conditions=f"price near spike {SPIKE}; hunt is {hunt_zone}",
                action="wait",
                direction="sell",
                confidence=50,
                auction="transition",
                key_levels=kl,
                missing_fact="at_entry_location",
                frame="H4",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — −147 class; hunt is {hunt_zone}, "
                    f"not {SPIKE}."
                ),
                confirmation_reason=(
                    f"Need price back in {hunt_zone} before arming."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    # eh_006 buy mirror — hunt support
    buy_lo, buy_hi = 4405.0, 4408.0
    rows.append(
        (
            s2(
                "eh_006",
                "07_trend_trading",
                "Buy context — hunt wait at session high",
                (
                    f"Plan: BUY. Hunt support {buy_lo}-{buy_hi}. Price pressing "
                    "session high after impulse — outside hunt."
                ),
                "Wait — at_entry_location",
                f"Price enters {buy_lo}-{buy_hi}",
                "do not buy the high; hunt the pullback support",
            ),
            s3(
                "eh_006",
                "hunt_wait_outside_entry_location",
                (
                    "Bullish plan + hunt support band + price at session high → "
                    "wait at_entry_location (mirror of sell-the-low error)."
                ),
                ["plan_side", "hunt_zone", "live_price"],
                ["action=wait", "missing_fact=at_entry_location"],
            ),
            s4(
                eid="eh_006",
                detector="hunt_wait_outside_entry_location",
                decision="Wait — at_entry_location",
                conditions=f"BUY hunt {buy_lo}-{buy_hi}; price at session high",
                action="wait",
                direction="buy",
                confidence=52,
                auction="transition",
                key_levels=(
                    f"HUNT_ZONE={buy_lo}-{buy_hi}, SESSION_HIGH=4425.0, "
                    f"INVALIDATION=4399.0"
                ),
                missing_fact="at_entry_location",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — buy bias OK but location is the "
                    "high; hunt support first."
                ),
                confirmation_reason=(
                    f"Arming starts only after price is inside {buy_lo}-{buy_hi}."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = f"{buy_lo}-{buy_hi}"

    # eh_007 optional challenger during hunt
    rows.append(
        (
            s2(
                "eh_007",
                "08_range_trading",
                "Hunt challenger — opposite location stronger → keep wait",
                (
                    f"SELL hunt {hunt_zone}. Price at {DAY_LOW} prints closed M5 "
                    "hold (long location more complete). Do not open sell."
                ),
                "Wait — revise / challenger",
                "Hunt intact or plan invalidated",
                "challenger blocks opening primary at wrong place",
            ),
            s3(
                "eh_007",
                "hunt_challenger_opposite_more_complete",
                (
                    "During hunt, if opposite side's location is more complete "
                    "(e.g. closed M5 at support while hunting a sell above) → "
                    "wait/revise; never force open. Primary side unchanged."
                ),
                ["hunt_zone", "opposite_location_complete", "primary_side"],
                ["action=wait", "sanity=wait"],
            ),
            s4(
                eid="eh_007",
                detector="hunt_challenger_opposite_more_complete",
                decision="Wait — challenger",
                conditions=f"hunting sell {hunt_zone}; buy hold at {DAY_LOW} stronger",
                action="wait",
                direction="sell",
                confidence=48,
                auction="rejection",
                key_levels=kl,
                missing_fact="at_entry_location",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                side_ideas={
                    "long": {
                        "zone": f"SUPPORT={DAY_LOW}",
                        "confidence": 68,
                        "missing_fact": None,
                        "viable": True,
                    },
                    "short": {
                        "zone": f"HUNT={hunt_zone}",
                        "confidence": 45,
                        "missing_fact": "at_entry_location",
                        "viable": False,
                    },
                    "pick": "wait",
                },
                trade_reason=(
                    f"{concept} Reason: wait — optional challenger: opposite "
                    "location more complete while primary still hunting."
                ),
                confirmation_reason=(
                    "Do not open sell at the low; either continue hunt after "
                    "flush or revise plan if always-in flips."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    # eh_008 invalidation during hunt → wait/skip not open
    rows.append(
        (
            s2(
                "eh_008",
                "07_trend_trading",
                "Hunt band tagged but invalidation broken — no ready",
                (
                    f"Price reaches {hunt_zone} but closed accept above {INV}. "
                    "Plan invalid."
                ),
                "Wait/skip — invalidation failed",
                "New context/plan",
                "step 3 invalidation check fails",
            ),
            s3(
                "eh_008",
                "hunt_arm_invalidation_blocks_ready",
                (
                    "Even in hunt band with a timing candle, if invalidation is "
                    "accepted against the plan → wait|skip, never ready."
                ),
                ["hunt_zone", "invalidation", "closed_acceptance"],
                ["action=wait|skip"],
            ),
            s4(
                eid="eh_008",
                detector="hunt_arm_invalidation_blocks_ready",
                decision="Wait — invalidation failed",
                conditions=f"in {hunt_zone} but accepted above {INV}",
                action="wait",
                direction="none",
                confidence=50,
                auction="acceptance",
                key_levels=kl,
                missing_fact="new_context_after_invalidation",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — arming failed invalidation check; "
                    "remap context, do not force sell."
                ),
                confirmation_reason=(
                    "Invalidation accepted; no ready until a new plan exists."
                ),
            ),
        )
    )
    rows[-1][2]["entry_zone"] = hunt_zone

    return rows


PRINCIPLES = [
    {
        "principle_id": "context_hunt_arm_three_step",
        "topic": "trend_trading",
        "lesson": (
            "Trade finding is three steps: (1) context/plan — direction, hunt "
            "band, invalidation; (2) hunt — wait with missing_fact="
            "at_entry_location while price is outside the band; (3) arming — "
            "in-band closed M5/M1 confirm then invalidation check before ready."
        ),
        "practice": (
            "Never emit ready at the structure low/high when the hunt band is "
            "elsewhere. Preserve the hunt zone; optional challenger may only "
            "force wait/revise, not a forced open."
        ),
        "guardrail": (
            "Do not relocate the hunt band to chase live price. Do not skip "
            "hunt because direction confidence is high."
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
        examples,
        principles=PRINCIPLES,
        dry_run=args.dry_run,
        label="entry-location-hunt",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
