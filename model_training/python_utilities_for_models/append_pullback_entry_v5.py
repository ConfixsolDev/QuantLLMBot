#!/usr/bin/env python3
"""V5 pack: with-trend entry only after a pullback — never sell the low / buy the high.

Why this pack exists
--------------------
2026-08-13 Asia: gold was on the sell (bearish after the failed spike), but two
shorts entered at/near the structure low with M1/M5 pin stories:

    paper-20260813T003249  sell ~4429  (into/after spike)   -> -147 SL+$3
    paper-20260813T020635  sell ~4406  (low of the giveback)-> -162 SL+$3

Bias was right; timing was wrong. Distilled topic 07: with-trend entries are
pullbacks (H2/L2 in the channel, breakout-pullback, sell rallies in a bear).
Selling the extreme of the impulse is late chase / climax restraint, not a
setup. Cooldown cannot teach this — curriculum must.

Doctrine anchors (topics/07_trend_trading.md, core_skill [entry-veto]):
- L2 / breakout-pullback is the standard with-trend sell, not the spike low
- Never chase after price has expanded away from the mapped zone
- Climax rule of restraint: do not enter "continuation" at the exhaustion print

Usage
-----
    python python_utilities_for_models/append_pullback_entry_v5.py --dry-run
    python python_utilities_for_models/append_pullback_entry_v5.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"
TICKS = ROOT / "tick_data"

HOLDOUT_IDS = [
    "02_35",
    "09_100",
    "01_14",
    "01_16",
    "09_99",
    "04_28",
    "07_19",
    "08_21",
    "09_85",
    "02_31",
]

# Live Asia levels from day plan / hourly path (discussion + ledger).
SPIKE_HIGH = 4449.92
H1_PREV_HIGH = 4414.61
DAY_LOW_ZONE = 4406.32
PULLBACK_RESIST = 4418.50  # illustrative lower-high / retest band after fail


def load(name: str) -> list[dict]:
    path = KNOW / name
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save(name: str, rows: list[dict]) -> None:
    (KNOW / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def day_atr(day: str) -> dict:
    path = TICKS / day / "atr-m1.jsonl"
    if not path.exists():
        return {
            "atr_m1_51": None,
            "atr_m1_3": None,
            "atr_ratio_3_51": None,
            "atr_timeframe": "M1",
            "atr_source": "unavailable",
        }
    eod = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") == "eod" and row.get("ok"):
            eod = row
    if not eod:
        return {
            "atr_m1_51": None,
            "atr_m1_3": None,
            "atr_ratio_3_51": None,
            "atr_timeframe": "M1",
            "atr_source": "unavailable",
        }
    a51 = eod.get("atr_m1_51")
    a3 = eod.get("atr_m1_3")
    ratio = eod.get("atr_ratio_3_51")
    if ratio is None and a3 is not None and a51:
        try:
            ratio = round(float(a3) / float(a51), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            ratio = None
    return {
        "atr_m1_51": a51,
        "atr_m1_3": a3,
        "atr_ratio_3_51": ratio,
        "atr_timeframe": "M1",
        "atr_source": f"mt5_m1_eod:{day}",
        "atr_as_of_utc": eod.get("as_of_utc") or eod.get("last_closed_time_utc"),
    }


def s2(eid, topic, title, setup, decision, invalidation, why, evidence="strong"):
    return {
        "example_id": eid,
        "topic": topic,
        "title": title,
        "setup": setup,
        "decision": decision,
        "invalidation": invalidation,
        "why": why,
        "evidence": evidence,
        "bucket": "A",
    }


def s3(eid, detector, logic, inputs, outputs):
    return {
        "example_id": eid,
        "detector_name": detector,
        "detector_logic": logic,
        "required_inputs": inputs,
        "expected_outputs": outputs,
    }


def s4(
    *,
    eid,
    detector,
    decision,
    conditions,
    action,
    direction,
    confidence,
    auction,
    key_levels,
    trade_reason,
    confirmation_reason,
    atr,
    skip_code=None,
    missing_fact=None,
    entry=0.0,
    sl=0.0,
    tp=0.0,
    frame="H1",
    role=None,
):
    is_open = action == "open"
    return {
        "example_id": eid,
        "detector_output": detector,
        "trade_decision": decision,
        "decision_conditions": conditions,
        "evidence_label": "strong",
        "conviction_score": round(min(0.9, max(0.2, confidence / 100)), 2),
        "risk_control": (
            f"SL beyond pullback extreme | TP next opposing named level | frame {frame}"
            if is_open
            else "No entry until pullback to mapped resistance/support"
        ),
        "key_levels": key_levels,
        "entry_price": entry if is_open else 0.0,
        "sl_price": sl if is_open else 0.0,
        "tp_price": tp if is_open else 0.0,
        "sl_usd": round(abs(entry - sl), 1) if is_open else 0.0,
        "tp_usd": round(abs(tp - entry), 1) if is_open else 0.0,
        "action": action,
        "direction": direction,
        "confidence": confidence,
        "auction_state": auction,
        "skip_reason_code": skip_code,
        "target_mode": "scalp" if is_open else "none",
        "role": role or ("entry" if is_open else action),
        "missing_fact": missing_fact,
        "structure_timeframe": frame,
        "trade_reason": trade_reason,
        "confirmation_reason": confirmation_reason,
        **atr,
    }


def build_examples(atr: dict) -> list[tuple[dict, dict, dict]]:
    kl_asia = (
        f"H1_PREVIOUS_HIGH={H1_PREV_HIGH}, SPIKE_EXTREME={SPIKE_HIGH}, "
        f"DAY_LOW_ZONE={DAY_LOW_ZONE}, PULLBACK_RESISTANCE={PULLBACK_RESIST}"
    )
    concept = (
        "Concept: In a bearish auction, with-trend sells are taken on a pullback "
        "to mapped resistance (lower high / breakout-retest), not at the impulse "
        "low. Selling the low is late chase after the move has already printed "
        "(Brooks L2 / breakout-pullback; core_skill entry-veto)."
    )

    rows: list[tuple[dict, dict, dict]] = []

    # 1) WAIT — bias sell, price at structure low, no pullback yet (−162 lesson)
    rows.append(
        (
            s2(
                "pb_001",
                "07_trend_trading",
                "Bearish day — wait for pullback, do not sell the low",
                (
                    f"After a failed spike to {SPIKE_HIGH}, price is pressing "
                    f"{DAY_LOW_ZONE}. Bias is sell, but there is no closed "
                    f"rejection at a mapped resistance above price."
                ),
                "Wait for pullback to resistance",
                f"Closed M15 acceptance back above {H1_PREV_HIGH}",
                (
                    "wait because the side is correct but location is the "
                    "structure low; a with-trend short needs a rally into "
                    f"{PULLBACK_RESIST} / {H1_PREV_HIGH} first."
                ),
            ),
            s3(
                "pb_001",
                "pullback_required_before_with_trend_entry",
                (
                    "If always-in / active scenario is bearish AND live price is "
                    "at or near the session/structure low AND no closed rejection "
                    "exists at a mapped resistance above price → wait|skip. "
                    "Do not emit ready sell on an M1 pin at the low alone."
                ),
                [
                    "active_scenario",
                    "mapped_resistance_above",
                    "live_price_vs_session_low",
                    "closed_M5_or_M15_rejection",
                ],
                ["action=wait|skip", "missing_fact=pullback_to_resistance"],
            ),
            s4(
                eid="pb_001",
                detector="pullback_required_before_with_trend_entry",
                decision="Wait for pullback to resistance",
                conditions=(
                    f"bearish bias, price at day low ~{DAY_LOW_ZONE}, "
                    "no pullback rejection yet"
                ),
                action="wait",
                direction="none",
                confidence=48,
                auction="transition",
                key_levels=kl_asia,
                skip_code=None,
                missing_fact="closed_rejection_at_pullback_resistance",
                frame="H1",
                atr=atr,
                trade_reason=(
                    f"{concept} Reason: wait — gold is on sell but price is at "
                    f"the low ({DAY_LOW_ZONE}); selling here is before the "
                    "pullback the bear entry requires."
                ),
                confirmation_reason=(
                    f"Confirmation still missing: one closed M5/M15 bearish "
                    f"rejection at {PULLBACK_RESIST} or held retest of "
                    f"{H1_PREV_HIGH} as resistance. An M1 pin at the low is not "
                    "that confirmation."
                ),
            ),
        )
    )

    # 2) SKIP — sell into/after spike extreme (−147 lesson)
    rows.append(
        (
            s2(
                "pb_002",
                "07_trend_trading",
                "Skip short at spike extreme — climax / late chase",
                (
                    f"Price spiked to {SPIKE_HIGH} through {H1_PREV_HIGH}. "
                    "A bearish M5 pin prints near the extreme. Always-in may "
                    "still flip, but entry location is the far side of the impulse."
                ),
                "Skip short at spike high",
                "N/A — no short until pullback",
                (
                    "skip because this is climax/late location; Grimes climax "
                    "restraint and Brooks late with-trend stop entry both forbid "
                    "shorting the extreme. Wait for the pullback short."
                ),
            ),
            s3(
                "pb_002",
                "late_impulse_extreme_skip",
                (
                    "If the proposed sell is within a small distance of the "
                    "impulse high after a multi-ATR spike and no pullback has "
                    "formed → skip. Alias: do not sell the high of a bear "
                    "transition print; sell the pullback after."
                ),
                ["spike_extreme", "atr_m1_51", "atr_m1_3", "atr_ratio_3_51", "pullback_started"],
                ["action=skip", "skip_reason_code=late_impulse_chase"],
            ),
            s4(
                eid="pb_002",
                detector="late_impulse_chase",
                decision="Skip short at spike extreme",
                conditions=(
                    f"sell proposed near spike {SPIKE_HIGH} after break of "
                    f"{H1_PREV_HIGH}; no pullback"
                ),
                action="skip",
                direction="none",
                confidence=50,
                auction="transition",
                key_levels=kl_asia,
                skip_code="late_impulse_chase",
                frame="H4",
                atr=atr,
                trade_reason=(
                    f"{concept} Reason: skip sell near {SPIKE_HIGH} — that is "
                    "the impulse extreme, not a pullback to resistance. Same "
                    "class as the live −147 short that sold before the pullback."
                ),
                confirmation_reason=(
                    "Confirmation for a with-trend short would be a closed "
                    f"failure back below {H1_PREV_HIGH} THEN a rally into that "
                    "level (or a lower high) that rejects. The spike wick alone "
                    "is not entry."
                ),
            ),
        )
    )

    # 3) OPEN — correct with-trend sell after pullback
    rows.append(
        (
            s2(
                "pb_003",
                "07_trend_trading",
                "Open short after pullback rejection at broken H1 high",
                (
                    f"Spike to {SPIKE_HIGH} failed; closed hour accepted back "
                    f"below {H1_PREV_HIGH}. Price rallies into "
                    f"{PULLBACK_RESIST}/{H1_PREV_HIGH} and prints a closed "
                    "M15 rejection."
                ),
                "Short scalp on pullback rejection",
                f"Closed M15 acceptance back above {H1_PREV_HIGH}",
                (
                    "sell because bias is bearish AND location is the pullback "
                    "to mapped resistance with a closed rejection — not the low."
                ),
            ),
            s3(
                "pb_003",
                "with_trend_pullback_rejection",
                (
                    "Bearish context + prior closed fail below resistance + "
                    "pullback into that resistance + closed M5/M15 rejection → "
                    "open sell. Stop beyond pullback extreme; target next "
                    "opposing support."
                ),
                [
                    "bearish_context",
                    "broken_resistance_now_supply",
                    "closed_rejection_on_pullback",
                ],
                ["action=open", "direction=sell"],
            ),
            s4(
                eid="pb_003",
                detector="with_trend_pullback_rejection",
                decision="Short scalp on pullback rejection",
                conditions=(
                    f"pullback into {H1_PREV_HIGH}/{PULLBACK_RESIST} after "
                    "failed spike; closed M15 rejection"
                ),
                action="open",
                direction="sell",
                confidence=74,
                auction="rejection",
                key_levels=kl_asia,
                entry=PULLBACK_RESIST,
                sl=4424.5,
                tp=4407.0,
                frame="H1",
                atr=atr,
                trade_reason=(
                    f"{concept} Reason: sell the pullback rejection at "
                    f"{PULLBACK_RESIST} after acceptance failed below "
                    f"{H1_PREV_HIGH} — with-trend, correct location."
                ),
                confirmation_reason=(
                    f"Confirmation: closed M15 bearish rejection at/under "
                    f"{H1_PREV_HIGH} on the pullback. Do not enter on the "
                    f"prior low at {DAY_LOW_ZONE}."
                ),
            ),
        )
    )

    # 4) Mirror WAIT for buys — don't buy the high in a bullish structure
    rows.append(
        (
            s2(
                "pb_004",
                "07_trend_trading",
                "Bullish day — wait for pullback, do not buy the high",
                (
                    "Active scenario bullish; price is pressing the session high "
                    "after an impulse. No closed rejection at mapped support below."
                ),
                "Wait for pullback to support",
                "Closed M15 acceptance back below the breakout support",
                (
                    "wait because buying the high is the mirror error of selling "
                    "the low; with-trend longs need a pullback to support."
                ),
            ),
            s3(
                "pb_004",
                "pullback_required_before_with_trend_entry",
                (
                    "Bullish context + price at/near session/structure high + "
                    "no closed rejection at mapped support below → wait. "
                    "Symmetric to the bearish pullback rule."
                ),
                [
                    "active_scenario",
                    "mapped_support_below",
                    "live_price_vs_session_high",
                    "closed_M5_or_M15_rejection",
                ],
                ["action=wait", "missing_fact=pullback_to_support"],
            ),
            s4(
                eid="pb_004",
                detector="pullback_required_before_with_trend_entry",
                decision="Wait for pullback to support",
                conditions="bullish bias, price at session high, no pullback yet",
                action="wait",
                direction="none",
                confidence=48,
                auction="transition",
                key_levels=(
                    "SESSION_HIGH=4425.0, BREAKOUT_SUPPORT=4414.61, "
                    "PULLBACK_SUPPORT=4416.0"
                ),
                missing_fact="closed_rejection_at_pullback_support",
                frame="H1",
                atr=atr,
                trade_reason=(
                    "Concept: In a bullish auction, with-trend buys are taken on "
                    "a pullback to mapped support, not at the impulse high. "
                    "Reason: wait — side is buy but location is the high."
                ),
                confirmation_reason=(
                    "Confirmation missing: closed M5/M15 bullish rejection at "
                    "mapped support on the pullback. An M1 pin at the high is "
                    "not entry."
                ),
            ),
        )
    )

    # 5) SKIP — same-thesis re-fire at the low after a micro-stop loss
    rows.append(
        (
            s2(
                "pb_005",
                "07_trend_trading",
                "Skip repeating sell-the-low after a noise stop",
                (
                    f"Prior short at ~{DAY_LOW_ZONE} stopped for a tiny $3 hit. "
                    "A new M1 pin prints again at the same low with the same "
                    "bearish summary. No new pullback to resistance has formed."
                ),
                "Skip repeated sell at structure low",
                "N/A",
                (
                    "skip because repeating the same low-of-structure pin after "
                    "a noise stop is not a new pullback setup; fix location, "
                    "do not re-fire the same extreme."
                ),
            ),
            s3(
                "pb_005",
                "repeat_extreme_entry_skip",
                (
                    "If the last short stopped at the structure low and the new "
                    "ready sell is again at that low without an intervening "
                    "pullback to resistance → skip. Cooldown is not the lesson; "
                    "location is."
                ),
                ["last_exit_reason", "last_entry_location", "new_entry_location", "pullback_intervened"],
                ["action=skip", "skip_reason_code=repeat_structure_low_entry"],
            ),
            s4(
                eid="pb_005",
                detector="repeat_structure_low_entry",
                decision="Skip repeated sell at structure low",
                conditions=(
                    f"re-fire sell at ~{DAY_LOW_ZONE} after prior micro-stop; "
                    "no pullback"
                ),
                action="skip",
                direction="none",
                confidence=50,
                auction="balance",
                key_levels=kl_asia,
                skip_code="repeat_structure_low_entry",
                frame="H1",
                atr=atr,
                trade_reason=(
                    f"{concept} Reason: skip — selling {DAY_LOW_ZONE} again after "
                    "the −162 noise stop is the same before-pullback error, not "
                    "a matured setup. Wait for resistance pullback."
                ),
                confirmation_reason=(
                    "Confirmation would require a fresh closed rejection at "
                    f"pullback resistance ({PULLBACK_RESIST}/{H1_PREV_HIGH}), "
                    "not another pin at the low."
                ),
            ),
        )
    )

    return rows


NEW_PRINCIPLES = [
    {
        "principle_id": "with_trend_entry_needs_pullback",
        "topic": "trend_trading",
        "lesson": (
            "Correct side is not enough: in a bearish auction sell the pullback "
            "to mapped resistance; in a bullish auction buy the pullback to "
            "mapped support. Selling the structure low or buying the structure "
            "high is late chase after the impulse (Brooks L2/H2 and "
            "breakout-pullback; Grimes climax restraint)."
        ),
        "practice": (
            "Before ready open, require a pullback into a named opposing level "
            "and one closed M5/M15 rejection there. If price is still at the "
            "impulse extreme, wait or skip."
        ),
        "guardrail": (
            "An M1 pin at the session low/high is timing noise, not pullback "
            "confirmation. Do not teach cooldown as the fix for this error."
        ),
        "evidence_label": "strong",
    }
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    atr = day_atr("2026-08-13")
    examples = build_examples(atr)
    print(f"examples={len(examples)} atr={atr}")

    if args.dry_run:
        print(json.dumps(examples[0][2], indent=2)[:1200])
        print("(dry run — nothing written)")
        return 0

    s1 = load("stage_01_principle_foundation.jsonl")
    s2_rows = load("stage_02_structured_data.jsonl")
    s3_rows = load("stage_03_detector_definitions.jsonl")
    s4_rows = load("stage_04_decision_contract.jsonl")

    existing_p = {r.get("principle_id") for r in s1}
    for p in NEW_PRINCIPLES:
        if p["principle_id"] not in existing_p:
            s1.append(p)

    new_ids = {a["example_id"] for a, _, _ in examples}
    s2_rows = [r for r in s2_rows if r["example_id"] not in new_ids]
    s3_rows = [r for r in s3_rows if r["example_id"] not in new_ids]
    s4_rows = [r for r in s4_rows if r["example_id"] not in new_ids]

    hold_s2 = [r for r in s2_rows if r["example_id"] in HOLDOUT_IDS]
    train_s2 = [r for r in s2_rows if r["example_id"] not in HOLDOUT_IDS]
    hold_ids = {r["example_id"] for r in hold_s2}
    train_s3 = [r for r in s3_rows if r["example_id"] not in hold_ids]
    hold_s3 = [r for r in s3_rows if r["example_id"] in hold_ids]
    train_s4 = [r for r in s4_rows if r["example_id"] not in hold_ids]
    hold_s4 = [r for r in s4_rows if r["example_id"] in hold_ids]

    new_s2 = [e[0] for e in examples]
    new_s3 = [e[1] for e in examples]
    new_s4 = [e[2] for e in examples]

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", train_s2 + new_s2 + hold_s2)
    save("stage_03_detector_definitions.jsonl", train_s3 + new_s3 + hold_s3)
    save("stage_04_decision_contract.jsonl", train_s4 + new_s4 + hold_s4)

    total = len(train_s4) + len(new_s4) + len(hold_s4)
    print(
        f"appended pullback-entry examples={len(examples)} "
        f"stage_04_total={total} holdout={len(hold_s4)}"
    )
    print(
        f"bump scripts/config.py training_lines_end={total - len(hold_s4)} "
        f"test_lines_end={total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
