#!/usr/bin/env python3
"""
Live-derived sideways pack from 2026-08-12 after 17:20 UTC (22:20 PKT).

Observed box ~4396.86-4413.06 (width ~$16) with repeated $3+ two-way swings.
Paper paths show tight SL$3 stops out trades that later rotate the other way
(SL zone becomes TP zone and back) — classic sideways identification.

Sources: paper-path / paper-executions 2026-08-12..13.
Doctrine: knowledge/topics/08_range_trading.md (Brooks/Dalton/Grimes).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"

HOLDOUT_IDS = [
    "02_35", "09_100", "01_14", "01_16", "09_99",
    "04_28", "07_19", "08_21", "09_85", "02_31",
]

# Live anchors (gold price)
BOX_LO = 4396.86
BOX_HI = 4413.06
BOX_MID = 4404.96
BOX_W = round(BOX_HI - BOX_LO, 2)  # ~16.2


def load(name: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (KNOW / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save(name: str, rows: list[dict]) -> None:
    (KNOW / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def entry_ex(**kw):
    eid = kw["eid"]
    action = kw["action"]
    direction = kw.get("direction", "none")
    entry = float(kw.get("entry") or 0)
    sl = float(kw.get("sl") or 0)
    tp = float(kw.get("tp") or 0)
    sl_usd = float(kw.get("sl_usd") or 0)
    tp_usd = float(kw.get("tp_usd") or 0)
    risk = (
        f"SL N/A | TP N/A | Entry N/A - {kw.get('skip_reason_code') or kw.get('missing_fact') or 'wait/skip'}"
        if action != "open"
        else f"SL ${sl_usd} gold at {sl} | TP ${tp_usd} gold at {tp} | Entry {entry}"
    )
    conf = int(round(max(0, min(100, float(kw["conviction"]) * 100))))
    if action in ("wait", "skip"):
        conf = min(conf, 50)
    elif action == "open" and conf < 51:
        conf = 51
    s2 = {
        "example_id": eid,
        "topic": kw.get("topic", "08_range_trading"),
        "title": kw["title"],
        "setup": kw["setup"],
        "decision": kw["decision"],
        "invalidation": kw["invalidation"],
        "why": kw["why"],
        "evidence": kw.get("evidence", "strong"),
        "bucket": "A",
    }
    s3 = {
        "example_id": eid,
        "detector_type": "heuristic",
        "detector_name": kw["detector_name"],
        "input_signals": ["price", "bars", "levels", "path"],
        "logic": kw["logic"],
        "thresholds": {
            "regime": "sideways",
            "box_width_gold": BOX_W,
            "sl_usd": [8, 12],
            "tp_usd": [5, 10],
            "source_day": "2026-08-12",
        },
        "output": kw["detector_output"],
    }
    s4 = {
        "example_id": eid,
        "role": "entry",
        "detector_output": kw["detector_output"],
        "trade_decision": kw["decision"],
        "decision_conditions": kw["conditions"],
        "evidence_label": kw.get("evidence", "strong"),
        "conviction_score": float(kw["conviction"]),
        "risk_control": risk,
        "key_levels": kw["key_levels"],
        "entry_price": entry,
        "sl_price": sl,
        "tp_price": tp,
        "sl_usd": sl_usd,
        "tp_usd": tp_usd,
        "pattern_type": "sideways_live",
        "action": action,
        "direction": direction,
        "confidence": conf,
        "auction_state": kw.get("auction_state", "balance"),
        "skip_reason_code": kw.get("skip_reason_code"),
        "target_mode": "scalp" if action == "open" else "none",
        "missing_fact": kw.get("missing_fact"),
        "trade_reason": kw["trade_reason"],
        "confirmation_reason": kw["confirmation_reason"],
    }
    return s2, s3, s4


def mgmt_ex(**kw):
    eid = kw["eid"]
    s2 = {
        "example_id": eid,
        "topic": "08_range_trading",
        "title": kw["title"],
        "setup": (
            f"LEVELS: {kw['key_levels']} | PATTERN=sideways_live | ROLE=management | "
            f"MGMT={kw['management_action']} | THESIS={kw['thesis_state']} | "
            f"REGIME=sideways | LIVE=2026-08-12_after_17:20UTC | " + kw["setup"]
        ),
        "decision": kw["management_action"].title(),
        "invalidation": "Accepted close outside live box against thesis",
        "why": kw["why"],
        "evidence": kw.get("evidence", "strong"),
        "bucket": "A",
    }
    s3 = {
        "example_id": eid,
        "detector_type": "heuristic",
        "detector_name": kw["detector_name"],
        "input_signals": ["price", "path", "levels", "position", "regime"],
        "logic": kw["logic"],
        "thresholds": {"regime": "sideways", "source_day": "2026-08-12"},
        "output": "enum(hold, protect, close)",
    }
    s4 = {
        "example_id": eid,
        "role": "management",
        "detector_output": kw["detector_output"],
        "trade_decision": kw["management_action"].title(),
        "decision_conditions": kw["conditions"],
        "evidence_label": kw.get("evidence", "strong"),
        "conviction_score": float(kw["conviction"]),
        "risk_control": (
            f"management={kw['management_action']}; thesis={kw['thesis_state']}; "
            f"regime=sideways; live_box={BOX_LO}-{BOX_HI}"
        ),
        "key_levels": kw["key_levels"],
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_usd": 0.0,
        "tp_usd": 0.0,
        "pattern_type": "sideways_live_management",
        "action": "open",
        "direction": kw["direction"],
        "confidence": int(float(kw["conviction"]) * 100),
        "management_action": kw["management_action"],
        "thesis_state": kw["thesis_state"],
        "confirmation_type": kw.get("confirmation_type", "none"),
        "decision_level_ref": kw["decision_level_ref"],
        "next_target_ref": kw.get("next_target_ref", "none"),
        "close_confirmed": bool(kw.get("close_confirmed", False)),
        "auction_state": "transition" if kw["management_action"] == "close" else "balance",
        "skip_reason_code": None,
        "target_mode": "none",
        "missing_fact": None,
        "trade_reason": kw["trade_reason"],
        "confirmation_reason": kw["confirmation_reason"],
    }
    return s2, s3, s4


NEW_PRINCIPLES = [
    {
        "principle_id": "P060",
        "topic": "08_range_trading",
        "principle_name": "Live Sideways ID - Two-Way Swings Inside a Box",
        "core_concept": (
            "Identify sideways when price prints both up and down swings of several gold dollars "
            "inside a stable high-low box without accepted breakout. Example 2026-08-12 after "
            "17:20 UTC: box ~4397-4413 (~$16) with repeated $3+ flips both ways."
        ),
        "foundational_rule": (
            "Checklist: overlapping M5/M15, both-direction $3+ swings, closes stay inside prior "
            "extremes, no follow-through acceptance. Then use large edge-beyond SL (often $8-$12 "
            "gold), not micro $3 pads - because SL side and TP side swap during rotation."
        ),
        "why_matters": (
            "Tight SL in identified sideways gets stopped into what becomes the TP rotation."
        ),
        "evidence_strength": "strong",
        "applies_to_detectors": [
            "sideways_box_id_live",
            "sideways_large_sl_benefit",
            "sl_tp_flip_path",
        ],
    },
]


NEW: list[tuple[dict, dict, dict]] = []

NEW.append(
    entry_ex(
        eid="08_50",
        title="IDENTIFY sideways box after 17:20 UTC 2026-08-12",
        setup=(
            f"LIVE 2026-08-12 after 17:20 UTC (22:20 PKT) | Marks lo={BOX_LO} hi={BOX_HI} "
            f"mid={BOX_MID} width=${BOX_W} | 5m bars both ways with $3+ swings: "
            "4403->4410 up, 4410->4397 down, 4397->4400 up, then more flips | "
            "Overlapping path, no accepted breakout hold | REGIME=sideways."
        ),
        decision="Wait for confirmation",
        invalidation=f"Accepted M15 closes hold outside {BOX_LO}-{BOX_HI}",
        why="First job is label sideways from two-way swings inside a stable box",
        detector_name="sideways_box_id_live",
        logic="two_way_swings AND stable_box AND no_accepted_break",
        detector_output="label_sideways_box",
        conditions="Live box ~$16 with repeated $3+ up/down swings - label sideways before entry",
        conviction=0.9,
        key_levels=(
            f"H1_BOX_LOW={BOX_LO}, H1_BOX_HIGH={BOX_HI}, H1_BOX_MID={BOX_MID}, "
            "SESSION_SLICE=after_17:20_UTC"
        ),
        entry=0,
        sl=0,
        tp=0,
        sl_usd=0,
        tp_usd=0,
        action="wait",
        direction="none",
        auction_state="balance",
        missing_fact=f"closed response at outer third of {BOX_LO}-{BOX_HI}",
        trade_reason=(
            "Concept: Sideways = two-sided trade inside a box (Brooks). Reason: wait/label - "
            f"live path after 17:20 UTC oscillates in {BOX_LO}-{BOX_HI} with both-way swings; "
            "do not treat as one-way trend yet."
        ),
        confirmation_reason=(
            "Confirmation of regime: multiple $3+ up AND down swings without accepted outside "
            "closes. Forming one M5 trend stair inside the box does not change the label."
        ),
    )
)

NEW.append(
    entry_ex(
        eid="08_51",
        title="SKIP mid-box chase in live sideways 4397-4413",
        setup=(
            f"LIVE sideways box {BOX_LO}-{BOX_HI} | Price near mid {BOX_MID} | "
            "M5 looks trendy for $4 | Mid has no edge | skip_reason_code=empty_midrange."
        ),
        decision="Skip",
        invalidation="Price reaches outer third with closed rejection/acceptance",
        why="Live mid-box has no edge even when M5 looks clean",
        detector_name="sideways_mid_skip_live",
        logic="sideways_box AND mid_third",
        detector_output="skip_mid_live_box",
        conditions="Live sideways mid - skip until outer third",
        conviction=0.92,
        key_levels=f"H1_BOX_LOW={BOX_LO}, H1_BOX_HIGH={BOX_HI}, H1_BOX_MID={BOX_MID}",
        entry=0,
        sl=0,
        tp=0,
        sl_usd=0,
        tp_usd=0,
        action="skip",
        direction="none",
        skip_reason_code="empty_midrange",
        trade_reason=(
            "Concept: Middle of a range is ~50/50 (Brooks/Grimes/Dalton). Reason: skip - "
            f"live price near {BOX_MID} inside the identified box."
        ),
        confirmation_reason=(
            "Confirmation: N/A - empty_midrange skip. Do not invent mid-box confirmation."
        ),
    )
)

NEW.append(
    entry_ex(
        eid="08_52",
        title="OPEN short edge with LARGE SL - live box high",
        setup=(
            f"LIVE sideways {BOX_LO}-{BOX_HI} | Fade near high after reject close | "
            "Path lesson: SL$3 earlier stopped sells that later worked | Use SL beyond box "
            f"high (~$10 gold), TP toward mid {BOX_MID}."
        ),
        decision="Short scalp",
        invalidation=f"Accepted M15 hold above {BOX_HI}",
        why="Sideways edge fade needs large SL because path flips SL<->TP",
        detector_name="sideways_edge_fade_large_sl",
        logic="sideways_box AND outer_third_high AND closed_reject AND large_sl",
        detector_output="sideways_short_large_sl",
        conditions="Live box high fade - large SL beyond high, TP mid",
        conviction=0.86,
        key_levels=(
            f"H1_BOX_HIGH={BOX_HI}, H1_BOX_MID={BOX_MID}, H1_BOX_LOW={BOX_LO}, "
            "M15_REJECT_REF=4411.0"
        ),
        entry=4410.0,
        sl=4420.0,
        tp=BOX_MID,
        sl_usd=10.0,
        tp_usd=5.04,
        action="open",
        direction="sell",
        auction_state="rejection",
        trade_reason=(
            "Concept: In sideways, adverse spikes toward/through the edge often reverse "
            "(vacuum/magnet). Reason: sell edge with LARGE SL beyond the box - micro $3 SL "
            "is noise width on this live path."
        ),
        confirmation_reason=(
            "Confirmation: closed reject near box high. Also regime confirmation from prior "
            "two-way $3+ swings inside the same box after 17:20 UTC."
        ),
    )
)

NEW.append(
    entry_ex(
        eid="08_53",
        title="OPEN long edge with LARGE SL - live box low spring",
        setup=(
            f"LIVE sideways | Sweep toward {BOX_LO} then reclaim | Live buy example around 4411 "
            "showed max adverse ~$3.8 then recovered to green - SL$3 would have stopped a winner. "
            f"Use SL ${10} beyond low, TP mid."
        ),
        decision="Long scalp",
        invalidation=f"Accepted M15 hold below {BOX_LO}",
        why="Large SL preserves the trade when sideways path tags SL then rotates to TP",
        detector_name="sideways_spring_large_sl",
        logic="sideways_box AND spring_low AND large_sl",
        detector_output="sideways_long_large_sl",
        conditions="Live spring at box low - large SL, TP mid",
        conviction=0.86,
        key_levels=(
            f"H1_BOX_LOW={BOX_LO}, H1_BOX_MID={BOX_MID}, H1_BOX_HIGH={BOX_HI}, "
            "LIVE_BUY_REF=4411.13"
        ),
        entry=4399.0,
        sl=4389.0,
        tp=BOX_MID,
        sl_usd=10.0,
        tp_usd=5.96,
        action="open",
        direction="buy",
        auction_state="rejection",
        trade_reason=(
            "Concept: Springs fail beyond the edge then reclaim (Grimes). Reason: buy reclaim "
            "with large SL - live path proved SL$3 turns a recovering long into a loss."
        ),
        confirmation_reason=(
            "Confirmation: sweep/reclaim closed back inside the box. Live sim: buy 4411.13 "
            "hit ~$3.8 adverse then finished positive - tight SL false-killed it."
        ),
    )
)

NEW.append(
    entry_ex(
        eid="08_54",
        title="CONTRAST tight SL$3 fails in live sideways",
        setup=(
            "LIVE sims after 17:20 UTC | sell 4406.90: SL3 hits ~22:33 while max fav later path "
            "still rotating | buy 4411.13: SL3 hits ~23:28 then price climbs back through entry "
            "to +$1.9 fav | Lesson: tight SL and TP sides swap in chop."
        ),
        decision="Skip",
        invalidation="N/A - geometry lesson",
        why="Do not use micro SL geometry once sideways is identified",
        detector_name="sideways_reject_micro_sl",
        logic="sideways_box AND micro_sl_plan",
        detector_output="skip_micro_sl_in_sideways",
        conditions="Identified sideways + planned SL$3 - skip/replan with large SL",
        conviction=0.93,
        key_levels=(
            f"H1_BOX_LOW={BOX_LO}, H1_BOX_HIGH={BOX_HI}, BAD_SL_USD=3, GOOD_SL_USD=10"
        ),
        entry=0,
        sl=0,
        tp=0,
        sl_usd=0,
        tp_usd=0,
        action="skip",
        direction="none",
        skip_reason_code="fixed_profile_mismatch",
        trade_reason=(
            "Concept: Trading-range dilemma - small targets need room, and noise width is large "
            "relative to $3 (Brooks). Reason: skip micro-SL plan inside live sideways box."
        ),
        confirmation_reason=(
            "Confirmation: live path shows SL$3 hit then rotation toward what would have been TP. "
            "That flip is the sideways fingerprint."
        ),
    )
)

# Management from live path
NEW.append(
    mgmt_ex(
        eid="sw_live_001",
        title="MGMT HOLD - live buy tagged SL zone then recovered",
        setup=(
            "LIVE buy entry~4411.13 after 17:20 UTC | Adverse to ~4407.34 (~$3.8) - SL$3 zone | "
            "Then recovered to ~4413 / closed +$1.3 fav | Correct management: HOLD through the "
            "adverse tag while still inside box; wrong: close at SL$3 loss."
        ),
        why="Live sideways: price tagged SL zone then became TP-side recovery",
        detector_name="sideways_hold_sl_to_tp_flip",
        logic="sideways AND adverse_tag AND reclaim_inside_box",
        detector_output="hold_sl_zone_recover",
        conditions="Adverse into SL zone then reclaim - HOLD, do not crystallize loss",
        conviction=0.92,
        key_levels=(
            f"ENTRY=4411.13, PATH_LOW=4407.34, BOX_LOW={BOX_LO}, BOX_HIGH={BOX_HI}, "
            "LIVE_EXEC=demo-20260812T182705-b943d553"
        ),
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="buy",
        decision_level_ref=f"H1_BOX_MID_{BOX_MID}",
        next_target_ref=f"H1_BOX_HIGH_{BOX_HI}",
        close_confirmed=False,
        trade_reason=(
            "Concept: In sideways, SL and TP sides can swap during rotation. Reason: HOLD - "
            "live long tagged the SL zone (~$3.8 adverse) then recovered; cutting there is the bug."
        ),
        confirmation_reason=(
            "Confirmation: still inside box (no accepted close below box low). Reclaim after "
            "adverse spike keeps thesis valid."
        ),
    )
)

NEW.append(
    mgmt_ex(
        eid="sw_live_002",
        title="MGMT HOLD - live sell adverse then still in box",
        setup=(
            "LIVE sell entry~4406.90 | Adverse to ~4410.87 (~$4) | SL$3 would already be dead | "
            "Still under box high 4413 | Sideways rotation - HOLD/protect only after structure, "
            "not because dollars went red."
        ),
        why="Live sell: small SL dies in noise; structure still inside box",
        detector_name="sideways_hold_sell_noise",
        logic="sideways AND sell AND adverse_lt_box_edge",
        detector_output="hold_sell_inside_box",
        conditions="Sell adverse <$ box-high distance - HOLD inside sideways",
        conviction=0.88,
        key_levels=(
            f"ENTRY=4406.90, PATH_HIGH=4410.87, BOX_HIGH={BOX_HI}, BOX_MID={BOX_MID}, "
            "LIVE_EXEC=demo-20260812T172612-7bdf2f86"
        ),
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="sell",
        decision_level_ref=f"H1_BOX_MID_{BOX_MID}",
        next_target_ref=f"H1_BOX_MID_{BOX_MID}",
        close_confirmed=False,
        trade_reason=(
            "Concept: Noise width in this live box exceeds $3. Reason: HOLD while below box high - "
            "dollar drawdown alone is not invalidation."
        ),
        confirmation_reason=(
            "Confirmation: no accepted hold above box high. Adverse $4 is inside-box rotation."
        ),
    )
)

NEW.append(
    mgmt_ex(
        eid="sw_live_003",
        title="MGMT CLOSE - only after accepted break of live box",
        setup=(
            f"LIVE box {BOX_LO}-{BOX_HI} | If two M15 closes hold above {BOX_HI} with continuation, "
            "sideways label ends - CLOSE fades. Until then, wick/expansion is not enough."
        ),
        why="Exit sideways fades only on accepted box break, not on SL/TP flip noise",
        detector_name="sideways_close_box_break",
        logic="sideways_fade AND accepted_closes_outside",
        detector_output="close_on_box_acceptance",
        conditions="Accepted hold outside live box against fade - CLOSE",
        conviction=0.9,
        key_levels=f"BOX_LOW={BOX_LO}, BOX_HIGH={BOX_HI}, RULE=two_M15_holds_outside",
        management_action="close",
        thesis_state="invalidated",
        confirmation_type="thesis_invalidation_confirmed",
        direction="sell",
        decision_level_ref=f"H1_BOX_HIGH_{BOX_HI}",
        next_target_ref="none",
        close_confirmed=True,
        trade_reason=(
            "Concept: Penetration/wick is expansion; acceptance ends the range "
            "(Grimes/Brooks). Reason: CLOSE only after accepted outside holds."
        ),
        confirmation_reason=(
            "Confirmation required: two M15 closes holding outside the live box with follow-through. "
            "SL<->TP flips inside the box are not that signal."
        ),
    )
)


def main() -> None:
    s1 = load("stage_01_principle_foundation.jsonl")
    s2 = load("stage_02_structured_data.jsonl")
    s3 = load("stage_03_detector_definitions.jsonl")
    s4 = load("stage_04_decision_contract.jsonl")

    existing = {r.get("principle_id") for r in s1}
    for p in NEW_PRINCIPLES:
        if p["principle_id"] not in existing:
            s1.append(p)

    new_ids = {row[0]["example_id"] for row in NEW}
    s2 = [r for r in s2 if r["example_id"] not in new_ids]
    s3 = [r for r in s3 if r["example_id"] not in new_ids]
    s4 = [r for r in s4 if r["example_id"] not in new_ids]

    holdout_s2 = [r for r in s2 if r["example_id"] in HOLDOUT_IDS]
    train_s2 = [r for r in s2 if r["example_id"] not in HOLDOUT_IDS]
    hold_ids = {r["example_id"] for r in holdout_s2}
    train_s3 = [r for r in s3 if r["example_id"] not in hold_ids]
    hold_s3 = [r for r in s3 if r["example_id"] in hold_ids]
    train_s4 = [r for r in s4 if r["example_id"] not in hold_ids]
    hold_s4 = [r for r in s4 if r["example_id"] in hold_ids]

    new_s2 = [e[0] for e in NEW]
    new_s3 = [e[1] for e in NEW]
    new_s4 = [e[2] for e in NEW]

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", train_s2 + new_s2 + holdout_s2)
    save("stage_03_detector_definitions.jsonl", train_s3 + new_s3 + hold_s3)
    save("stage_04_decision_contract.jsonl", train_s4 + new_s4 + hold_s4)
    print(f"appended live sideways examples={len(NEW)} box={BOX_LO}-{BOX_HI} width={BOX_W}")


if __name__ == "__main__":
    main()
