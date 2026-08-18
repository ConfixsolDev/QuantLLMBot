#!/usr/bin/env python3
"""V5 pack: closed M5 confirms; M1 pin alone waits (topic 04 Triple Screen).

M1 stays for ATR timing / last-second context. M5 is the preferred confirmation
timeframe. Do not promote M5 impulse to HTF bias.

Usage
-----
    python python_utilities_for_models/append_m5_confirm_v5.py --dry-run
    python python_utilities_for_models/append_m5_confirm_v5.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _curriculum_append_lib import append_examples, day_atr, s2, s3, s4  # noqa: E402

DAY = "2026-08-13"
ZONE = 4414.61
SUPPORT = 4406.32


def build(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl = f"H1_PREVIOUS_HIGH={ZONE}, SUPPORT={SUPPORT}"
    concept = (
        "Concept: Elder/Brooks timeframe hierarchy — analysis on higher TF, "
        "timing on lower. M1 through a level is a probe; closed M5 at the mapped "
        "zone is confirmation. M1 pin alone is wait."
    )
    rows: list[tuple[dict, dict, dict]] = []

    rows.append(
        (
            s2(
                "m5c_001",
                "04_timeframe_relations",
                "M1 pin at resistance — wait for closed M5",
                (
                    f"Bearish context. M1 prints a pin at {ZONE}. No closed M5 "
                    "rejection yet."
                ),
                "Wait for closed M5",
                f"Closed M5 acceptance above {ZONE}",
                "wait because M1 is timing noise until M5 closes",
            ),
            s3(
                "m5c_001",
                "m1_pin_waits_for_m5_close",
                (
                    "Mapped zone + only an M1 pin/probe → wait. Promote to open "
                    "only after a closed M5 rejection/acceptance in the trade "
                    "direction at that zone."
                ),
                ["mapped_zone", "m1_pin", "closed_M5"],
                ["action=wait", "trigger_tf=M5", "missing_fact=closed_M5"],
            ),
            s4(
                eid="m5c_001",
                detector="m1_pin_waits_for_m5_close",
                decision="Wait for closed M5",
                conditions=f"M1 pin at {ZONE}; M5 not closed in direction",
                action="wait",
                direction="none",
                confidence=52,
                auction="unclear",
                key_levels=kl,
                missing_fact="closed_M5_rejection",
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — M1 pin at {ZONE} is not "
                    "confirmation (topic 04 break hierarchy)."
                ),
                confirmation_reason=(
                    f"Confirmation required: closed M5 bearish rejection at "
                    f"{ZONE}. Forming M1 bars do not count."
                ),
            ),
        )
    )

    rows.append(
        (
            s2(
                "m5c_002",
                "04_timeframe_relations",
                "Closed M5 rejection — open short",
                (
                    f"Same zone {ZONE}. Closed M5 prints a full rejection after "
                    "the M1 probes."
                ),
                "Short on closed M5",
                f"Closed M5 acceptance above {ZONE}",
                "sell because closed M5 confirms the mapped resistance",
            ),
            s3(
                "m5c_002",
                "closed_m5_confirms_mapped_zone",
                (
                    "HTF/context already set + mapped zone + closed M5 rejection "
                    "in trade direction → open. trigger_tf=M5."
                ),
                ["htf_context", "mapped_zone", "closed_M5_rejection"],
                ["action=open", "trigger_tf=M5"],
            ),
            s4(
                eid="m5c_002",
                detector="closed_m5_confirms_mapped_zone",
                decision="Short on closed M5",
                conditions=f"closed M5 reject at {ZONE}",
                action="open",
                direction="sell",
                confidence=68,
                auction="rejection",
                key_levels=kl,
                entry=ZONE,
                sl=4420.0,
                tp=SUPPORT,
                frame="H1",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: sell — closed M5 rejection at {ZONE} "
                    "is the timing confirmation after M1 noise."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 bearish rejection at {ZONE}."
                ),
            ),
        )
    )

    rows.append(
        (
            s2(
                "m5c_003",
                "04_timeframe_relations",
                "M1 pierce of M15 level — failed probe, not break",
                (
                    f"M15 resistance {ZONE}. Two M1 closes print above it; the "
                    "containing M5/M15 closes back below."
                ),
                "Skip breakout long",
                f"M15/M5 close accepting above {ZONE}",
                "skip — M1 cannot break an M15-defined level alone",
            ),
            s3(
                "m5c_003",
                "m1_cannot_break_higher_tf_level",
                (
                    "If a level is defined on M15+, M1 trades through it while "
                    "the higher bar closes back inside → failed probe, not a "
                    "breakout entry."
                ),
                ["level_defining_tf", "m1_pierce", "higher_tf_close"],
                ["action=skip", "skip_reason_code=failed_probe"],
            ),
            s4(
                eid="m5c_003",
                detector="m1_cannot_break_higher_tf_level",
                decision="Skip breakout long",
                conditions=f"M1 pierce of {ZONE}; higher TF closes back inside",
                action="skip",
                direction="none",
                confidence=50,
                auction="rejection",
                key_levels=kl,
                skip_code="failed_probe",
                frame="M15",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: skip long — M1 pierce of M15 level "
                    "with higher-TF close back inside is a failed probe."
                ),
                confirmation_reason=(
                    "Break would need a closed M5/M15 acceptance outside the "
                    "level, not M1 wicks."
                ),
            ),
        )
    )

    rows.append(
        (
            s2(
                "m5c_004",
                "04_timeframe_relations",
                "Do not let M5 impulse rewrite H4 bias",
                (
                    "H4 still bracketing/bearish. Three strong M5 bull bars print "
                    "into London. Temptation: flip bias to buy."
                ),
                "Wait — keep H4 regime; M5 is timing only",
                "H4 closed acceptance that flips always-in",
                "wait/skip bias flip from M5 alone",
            ),
            s3(
                "m5c_004",
                "m5_does_not_override_htf_regime",
                (
                    "M5 impulse cannot promote a new HTF bias. Use M5 only to "
                    "time entries aligned with the already-classified regime."
                ),
                ["htf_regime", "m5_impulse"],
                ["action=wait|skip", "bias_unchanged"],
            ),
            s4(
                eid="m5c_004",
                detector="m5_does_not_override_htf_regime",
                decision="Wait — keep H4 regime",
                conditions="H4 bearish/bracket; M5 bull burst only",
                action="wait",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl,
                missing_fact="htf_closed_regime_flip",
                frame="H4",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: wait — topic 04: never infer HTF bias "
                    "from lower-TF momentum."
                ),
                confirmation_reason=(
                    "A regime flip needs closed H4/H1 structure change, not "
                    "three M5 bars."
                ),
            ),
        )
    )

    rows.append(
        (
            s2(
                "m5c_005",
                "04_timeframe_relations",
                "Buy pullback — closed M5 at support after H4 bullish",
                (
                    f"H4 bullish. Price pulls back to {SUPPORT}. Closed M5 "
                    "bullish rejection; M1 had several noisy probes first."
                ),
                "Long on closed M5 at support",
                f"Closed M5 accept below {SUPPORT}",
                "buy — HTF bias + location + closed M5 timing",
            ),
            s3(
                "m5c_005",
                "triple_screen_m5_timing",
                (
                    "HTF bullish + pullback to support + closed M5 bullish "
                    "rejection → open buy. Ignore prior M1 noise at the same zone."
                ),
                ["htf_bullish", "pullback_support", "closed_M5"],
                ["action=open", "direction=buy", "trigger_tf=M5"],
            ),
            s4(
                eid="m5c_005",
                detector="triple_screen_m5_timing",
                decision="Long on closed M5 at support",
                conditions=f"H4 buy + closed M5 at {SUPPORT}",
                action="open",
                direction="buy",
                confidence=70,
                auction="rejection",
                key_levels=kl,
                entry=SUPPORT,
                sl=4399.0,
                tp=ZONE,
                frame="H4",
                atr=atr,
                trigger_tf="M5",
                trade_reason=(
                    f"{concept} Reason: buy — Triple Screen: H4 analysis, M5 "
                    "timing at support after M1 noise."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M5 bullish rejection at {SUPPORT}."
                ),
            ),
        )
    )

    return rows


PRINCIPLES = [
    {
        "principle_id": "closed_m5_confirms_m1_is_noise",
        "topic": "timeframe_relations",
        "lesson": (
            "Prefer closed M5 as the entry confirmation timeframe. M1 is for "
            "ATR/timing context and often noise; M1 probes do not break "
            "higher-TF levels or flip HTF bias."
        ),
        "practice": (
            "Set trigger_tf=M5 on opens. If only an M1 pin exists at the zone, "
            "wait. Keep M1 ATR (3/51) for regime hints."
        ),
        "guardrail": (
            "Do not replace M1 ATR with M5 ATR in this slice. Do not let M5 "
            "impulse override H4/H1 regime."
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
        examples, principles=PRINCIPLES, dry_run=args.dry_run, label="m5-confirm"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
