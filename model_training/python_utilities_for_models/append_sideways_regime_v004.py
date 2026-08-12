#!/usr/bin/env python3
"""
v004 sideways pack — teach range/balance behaviour from distilled topic 08
(Brooks/Dalton/Grimes), with contrast to trend (07) and reversal (09).

Focus (operator gap): model cuts gold too fast on temporary giveback inside a
sideways H4/H1 box even when price recovers to the magnet/mid. Pack teaches:

1. Classify sideways before choosing a playbook
2. Skip mid-range / barbwire / tight box
3. Fade edges + failed breakouts with zone gold SL/TP
4. Manage open fades: HOLD through normal rotation/giveback; CLOSE only on
   accepted break against the entry edge

Ids: 08_40+ entry/skip/wait, sw_mgmt_001+ management, 07_swc_* / 09_swc_* contrasts.
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


def entry_ex(
    eid, topic, title, setup, decision, invalidation, why, evidence, bucket,
    detector_name, logic, detector_output, trade_decision, conditions, conviction,
    key_levels, entry, sl, tp, sl_usd, tp_usd,
    *,
    auction_state="balance",
    skip_reason_code=None,
    target_mode="scalp",
    missing_fact=None,
    pattern_type="range",
    action=None,
    direction=None,
    trade_reason=None,
    confirmation_reason=None,
):
    risk = (
        f"SL N/A | TP N/A | Entry N/A - {skip_reason_code or missing_fact or 'wait/skip'}"
        if entry in (0, 0.0, None)
        else f"SL ${sl_usd} gold at {sl} | TP ${tp_usd} gold at {tp} | Entry {entry}"
    )
    if action is None:
        td = trade_decision.lower()
        if td.startswith("skip") or skip_reason_code:
            action, direction = "skip", "none"
        elif td.startswith("wait"):
            action, direction = "wait", "none"
        elif "short" in td or "sell" in td:
            action, direction = "open", "sell"
        else:
            action, direction = "open", "buy"
    s2 = {
        "example_id": eid,
        "topic": topic,
        "title": title,
        "setup": setup,
        "decision": decision,
        "invalidation": invalidation,
        "why": why,
        "evidence": evidence,
        "bucket": bucket,
    }
    s3 = {
        "example_id": eid,
        "detector_type": "heuristic",
        "detector_name": detector_name,
        "input_signals": ["price", "volume", "time", "bars", "levels"],
        "logic": logic,
        "thresholds": {"tp_usd": [5, 20], "sl_usd": [5, 10], "regime": "sideways"},
        "output": detector_output,
    }
    conf = int(round(max(0, min(100, conviction * 100))))
    if action in ("wait", "skip"):
        conf = min(conf, 50)
    elif action == "open" and conf < 51:
        conf = 51
    s4 = {
        "example_id": eid,
        "role": "entry",
        "detector_output": detector_output,
        "trade_decision": trade_decision,
        "decision_conditions": conditions,
        "evidence_label": evidence,
        "conviction_score": conviction,
        "risk_control": risk,
        "key_levels": key_levels,
        "entry_price": float(entry or 0),
        "sl_price": float(sl or 0),
        "tp_price": float(tp or 0),
        "sl_usd": float(sl_usd or 0),
        "tp_usd": float(tp_usd or 0),
        "pattern_type": pattern_type,
        "action": action,
        "direction": direction or "none",
        "confidence": conf,
        "auction_state": auction_state,
        "skip_reason_code": skip_reason_code,
        "target_mode": target_mode if action == "open" else "none",
        "missing_fact": missing_fact,
        "trade_reason": trade_reason or why,
        "confirmation_reason": confirmation_reason
        or (
            "Confirmation: N/A - skip/wait gate."
            if action != "open"
            else conditions
        ),
    }
    return s2, s3, s4


def mgmt_ex(
    eid, topic, title, setup, why, evidence,
    detector_name, logic, detector_output, conditions, conviction,
    key_levels, *,
    management_action, thesis_state, confirmation_type, direction,
    decision_level_ref, next_target_ref, close_confirmed=False,
    trade_reason=None,
    confirmation_reason=None,
    pattern_type="sideways_management",
):
    s2 = {
        "example_id": eid,
        "topic": topic,
        "title": title,
        "setup": (
            f"LEVELS: {key_levels} | PATTERN={pattern_type} | ROLE=management | "
            f"MGMT={management_action} | THESIS={thesis_state} | REGIME=sideways | " + setup
        ),
        "decision": management_action.title(),
        "invalidation": "Accepted close through entry-edge of H4/H1 box against thesis",
        "why": why,
        "evidence": evidence,
        "bucket": "A",
    }
    s3 = {
        "example_id": eid,
        "detector_type": "heuristic",
        "detector_name": detector_name,
        "input_signals": ["price", "levels", "m1", "m5", "position", "regime"],
        "logic": logic,
        "thresholds": {"regime": "sideways"},
        "output": "enum(hold, protect, close)",
    }
    s4 = {
        "example_id": eid,
        "role": "management",
        "detector_output": detector_output,
        "trade_decision": management_action.title(),
        "decision_conditions": conditions,
        "evidence_label": evidence,
        "conviction_score": conviction,
        "risk_control": f"management={management_action}; thesis={thesis_state}; regime=sideways",
        "key_levels": key_levels,
        "entry_price": 0.0,
        "sl_price": 0.0,
        "tp_price": 0.0,
        "sl_usd": 0.0,
        "tp_usd": 0.0,
        "pattern_type": pattern_type,
        "action": "open",
        "direction": direction,
        "confidence": int(conviction * 100),
        "management_action": management_action,
        "thesis_state": thesis_state,
        "confirmation_type": confirmation_type,
        "decision_level_ref": decision_level_ref,
        "next_target_ref": next_target_ref,
        "close_confirmed": close_confirmed,
        "auction_state": "transition" if management_action == "close" else "balance",
        "skip_reason_code": None,
        "target_mode": "none",
        "missing_fact": None,
        "trade_reason": trade_reason or why,
        "confirmation_reason": confirmation_reason or conditions,
    }
    return s2, s3, s4


NEW_PRINCIPLES = [
    {
        "principle_id": "P057",
        "topic": "08_range_trading",
        "principle_name": "Sideways First - Classify Before Playbook",
        "core_concept": (
            "Most of the time gold is two-sided (Brooks/Dalton). Declare sideways/balance "
            "on H4/H1 when bars overlap, swings stay inside a box, and there is no unfinished "
            "acceptance. Trend and reversal playbooks are wrong until that label is set."
        ),
        "foundational_rule": (
            "If H4/H1 is sideways, only outer-third fades or failed-breakout fades are allowed; "
            "mid-box is skip. Do not manage a range fade as if it were a trend runner."
        ),
        "why_matters": (
            "Model cuts winners too early in chop because it treats every M1 giveback as trend failure."
        ),
        "evidence_strength": "strong",
        "applies_to_detectors": [
            "sideways_regime_label",
            "range_outer_third_only",
            "range_mid_skip",
        ],
    },
    {
        "principle_id": "P058",
        "topic": "08_range_trading",
        "principle_name": "Sideways Management - Hold Rotation, Cut Only Accepted Break",
        "core_concept": (
            "Inside a named H4/H1 box, temporary adverse M1/M5 spikes toward the mid magnet are "
            "normal path (Brooks vacuum/magnet; Dalton balance). Open edge-fades HOLD through "
            "giveback that stays inside the box and recovers. CLOSE only after accepted closes "
            "through the entry-edge against the thesis."
        ),
        "foundational_rule": (
            "Peak P&L / giveback dollars are path context, never the exit trigger in sideways. "
            "Wick beyond the edge is range expansion, not breakout. Do not panic-close a fading "
            "short just because gold spiked to mid and then rotated back."
        ),
        "why_matters": (
            "Live failure mode: model closes sideways fades in small loss right as price returns "
            "to the fade edge / mid target."
        ),
        "evidence_strength": "strong",
        "applies_to_detectors": [
            "sideways_hold_giveback",
            "sideways_close_accepted_break",
            "range_magnet_mid_target",
        ],
    },
    {
        "principle_id": "P059",
        "topic": "08_range_trading",
        "principle_name": "Three Regimes - Sideways vs Trend vs Reversal",
        "core_concept": (
            "Sideways: fade edges / failed breaks, small targets to mid. Trend: pullback with "
            "the unfinished auction, do not fade acceptance. Reversal: needs prior trend + "
            "trendline break + failed retest; usual result is a new range, not an instant opposite trend."
        ),
        "foundational_rule": (
            "Never apply sideways fade rules to an unfinished H4 acceptance, and never apply "
            "trend-hold urgency to a balanced box mid-rotation."
        ),
        "why_matters": "Wrong regime is the root of both over-trading mid-range and premature cuts.",
        "evidence_strength": "strong",
        "applies_to_detectors": [
            "regime_sideways",
            "regime_trend",
            "regime_reversal_gate",
        ],
    },
]


NEW: list[tuple[dict, dict, dict]] = []

# ----- Entry: skip / wait discipline inside sideways -----
NEW.append(
    entry_ex(
        "08_40",
        "08_range_trading",
        "SKIP sideways mid-box - no edge",
        "REGIME=sideways | H4 box 2648-2666 | Price mid 2657 (55% of box) | M15 overlapping dojis | "
        "No outer-third touch | Brooks middle = 50/50 | skip_reason_code=empty_midrange.",
        "Skip",
        "Price reaches outer third of H4 box",
        "Sideways middle has no edge - pass",
        "strong",
        "A",
        "range_mid_skip",
        "sideways AND mid_box",
        "skip_midrange_sideways",
        "Skip",
        "H4 sideways mid - skip until outer third",
        0.92,
        "H4_RANGE_LOW=2648, H4_RANGE_HIGH=2666, H4_RANGE_MID=2657",
        0,
        0,
        0,
        0,
        0,
        auction_state="balance",
        skip_reason_code="empty_midrange",
        target_mode="none",
        pattern_type="range",
        action="skip",
        direction="none",
        trade_reason=(
            "Concept: Inside the middle of a sideways box directional odds are ~50/50 "
            "(Brooks/Grimes/Dalton). Reason: skip - price is mid-box, not an edge fade."
        ),
        confirmation_reason=(
            "Confirmation: N/A - skip gate empty_midrange. Do not invent a mid-box entry candle."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_41",
        "08_range_trading",
        "SKIP barbwire - no breakout entry",
        "REGIME=sideways | H1 barbwire 3 overlapping large dojis at 2654-2658 | M5 tries stop-entry "
        "break | Brooks: never enter on barbwire breakout | skip_reason_code=compressed.",
        "Skip",
        "Trend bar breaks then fails back into barbwire - then fade failure",
        "Barbwire breakout entries are lethal",
        "strong",
        "A",
        "barbwire_skip_breakout",
        "barbwire AND breakout_attempt",
        "skip_barbwire_breakout",
        "Skip",
        "Barbwire - skip breakout chase",
        0.93,
        "H1_BARBWIRE_LOW=2654, H1_BARBWIRE_HIGH=2658, M5_BREAK_ATTEMPT=2659",
        0,
        0,
        0,
        0,
        0,
        auction_state="balance",
        skip_reason_code="compressed",
        target_mode="none",
        pattern_type="range",
        action="skip",
        direction="none",
        trade_reason=(
            "Concept: Barbwire is agreement chop; most breakouts fail (Brooks). "
            "Reason: skip breakout entry - wait for failure fade only."
        ),
        confirmation_reason=(
            "Confirmation: N/A - compressed/barbwire skip. Forming breakout bar is not permission."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_42",
        "08_range_trading",
        "WAIT sideways - need closed fade at edge",
        "REGIME=sideways | H4 high 2665 vacuum spike in progress | M5 large bull bar into edge | "
        "Brooks vacuum: strong bar at edge favors fade AFTER reclaim | Forming only.",
        "Wait for confirmation",
        "M5 closes back inside box below 2665",
        "Wait for closed reclaim before fading vacuum",
        "strong",
        "A",
        "range_edge_vacuum_wait",
        "sideways AND edge_vacuum AND forming",
        "wait_edge_reclaim",
        "Wait for confirmation",
        "Vacuum into H4 high - wait closed reclaim inside",
        0.78,
        "H4_RANGE_HIGH=2665, H4_RANGE_MID=2656, M5_SPIKE=2666.5",
        0,
        0,
        0,
        0,
        0,
        auction_state="transition",
        target_mode="none",
        missing_fact="closed M5 reclaim back inside below H4_RANGE_HIGH 2665",
        pattern_type="range",
        action="wait",
        direction="none",
        trade_reason=(
            "Concept: Magnet/vacuum accelerates into the extreme before the fade works "
            "(Brooks). Reason: wait - spike is at the edge but reclaim is not closed yet."
        ),
        confirmation_reason=(
            "Confirmation needed: closed M5 reclaim back inside below 2665. "
            "Do not short the open of the vacuum bar."
        ),
    )
)

# ----- Entry: open fades / failed breaks -----
NEW.append(
    entry_ex(
        "08_43",
        "08_range_trading",
        "OPEN short - sideways fade H4 high",
        "REGIME=sideways | H4 box 2648-2665 | Price rejects H4_RANGE_HIGH | M15 bear pin + M5 bear engulf "
        "close back inside | Target mid 2656 | SL beyond high.",
        "Short scalp",
        "Accepted M15 close above 2665",
        "Outer-third fade in sideways box",
        "strong",
        "A",
        "range_edge_fade_short",
        "sideways AND outer_third AND closed_reject",
        "sideways_fade_high_valid",
        "Short scalp",
        "H4 sideways high rejected - short to mid",
        0.86,
        "H4_RANGE_HIGH=2665, H4_RANGE_MID=2656, H4_RANGE_LOW=2648, M15_PREVIOUS_HIGH=2664",
        2663.0,
        2673.0,
        2656.0,
        10.0,
        7.0,
        auction_state="rejection",
        pattern_type="range",
        action="open",
        direction="sell",
        trade_reason=(
            "Concept: Buy low / sell high scalps from box edges; mid is the target not the entry "
            "(Brooks). Reason: sell - closed rejection at H4 high in a labelled sideways box."
        ),
        confirmation_reason=(
            "Confirmation: M15 pin + M5 bear engulf close back inside H4_RANGE_HIGH. "
            "Closed-bar location proves the fade; wick alone would not."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_44",
        "08_range_trading",
        "OPEN long - sideways fade H4 low",
        "REGIME=sideways | H4 box 2648-2665 | Sweep H4_RANGE_LOW then M15 hammer close back inside | "
        "M5 bull two-bar | Target mid | SL beyond low.",
        "Long scalp",
        "Accepted M15 close below 2648",
        "Spring/fade at sideways low",
        "strong",
        "A",
        "range_edge_fade_long",
        "sideways AND outer_third AND spring",
        "sideways_fade_low_valid",
        "Long scalp",
        "H4 sideways low spring - long to mid",
        0.86,
        "H4_RANGE_LOW=2648, H4_RANGE_MID=2656, H4_RANGE_HIGH=2665, M15_PREVIOUS_LOW=2649",
        2650.0,
        2640.0,
        2656.0,
        10.0,
        6.0,
        auction_state="rejection",
        pattern_type="range",
        action="open",
        direction="buy",
        trade_reason=(
            "Concept: Failed probe beyond a well-defined box edge often precedes mean reversion "
            "to mid (Grimes spring; Brooks failed breakout). Reason: buy after closed reclaim."
        ),
        confirmation_reason=(
            "Confirmation: sweep then M15 hammer + M5 bull two-bar close back inside 2648. "
            "Forming spike under the low is not enough."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_45",
        "08_range_trading",
        "OPEN short - failed upside breakout of balance",
        "REGIME=sideways/balance | H4 balance 2650-2662 | M30 closes 2664 then next M30 closes back 2660 "
        "inside | Dalton/Brooks failed breakout - fade to opposite extreme.",
        "Short reversal",
        "Accepted hold above 2662 with follow-through",
        "Failed balance breakout is high-quality fade",
        "strong",
        "A",
        "balance_failed_break_short",
        "balance AND close_outside THEN close_back_inside",
        "failed_breakout_fade_short",
        "Short reversal",
        "Failed upside break of balance - short to opposite edge",
        0.88,
        "H4_BALANCE_HIGH=2662, H4_BALANCE_LOW=2650, M30_FAIL_CLOSE=2660",
        2660.0,
        2670.0,
        2650.0,
        10.0,
        10.0,
        auction_state="rejection",
        pattern_type="range",
        action="open",
        direction="sell",
        trade_reason=(
            "Concept: On a breakout that fails, reverse and target the opposite balance extreme "
            "(Dalton). Reason: sell - accepted reclaim inside after the upside poke."
        ),
        confirmation_reason=(
            "Confirmation: M30 close outside then next M30 close back inside balance. "
            "One wick above the high without reclaim is not the fade yet."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_46",
        "08_range_trading",
        "SKIP first breakout of converging range",
        "REGIME=compressing sideways | Triangle into apex | First M15 closes outside upper line | "
        "Grimes: do not fade the first breakout from a converging range | skip chasing fade.",
        "Skip",
        "Second test / failed follow-through after first break",
        "Do not fade first converging breakout",
        "strong",
        "A",
        "converging_range_no_fade_first",
        "converging_range AND first_breakout",
        "skip_fade_first_triangle_break",
        "Skip",
        "First triangle breakout - no fade",
        0.9,
        "H1_TRIANGLE_HIGH=2660, H1_TRIANGLE_LOW=2652, M15_FIRST_BREAK=2661",
        0,
        0,
        0,
        0,
        0,
        auction_state="transition",
        skip_reason_code="htf_conflict",
        target_mode="none",
        pattern_type="range",
        action="skip",
        direction="none",
        trade_reason=(
            "Concept: Volatility compression puts you in breakout mode; do not fade the first "
            "break (Grimes). Reason: skip the early fade."
        ),
        confirmation_reason=(
            "Confirmation: N/A - first converging breakout is not a fade permission."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_47",
        "08_range_trading",
        "OPEN long - Asia range low fade into London",
        "REGIME=sideways Asia box | Asia 4318-4332 held | London open sweeps Asia low then M15 closes "
        "back inside | Lien session range as balance | Long to mid/Asia high scalp.",
        "Long scalp",
        "Accepted hold below Asia low",
        "Session-range spring into London",
        "strong",
        "A",
        "asia_range_spring_long",
        "asia_box AND london_sweep_low AND close_inside",
        "asia_balance_fade_long",
        "Long scalp",
        "Asia low sweep reclaim - long inside session balance",
        0.84,
        "ASIA_SESSION_LOW=4318, ASIA_SESSION_HIGH=4332, ASIA_MID=4325, M15_RECLAIM=4320",
        4320.0,
        4310.0,
        4325.0,
        10.0,
        5.0,
        auction_state="rejection",
        pattern_type="range",
        action="open",
        direction="buy",
        trade_reason=(
            "Concept: Completed Asia range is a balance the next session either accepts, sweeps, "
            "or breaks (Lien). Reason: buy the failed sweep reclaim, not a mid-Asia chase."
        ),
        confirmation_reason=(
            "Confirmation: London sweep of Asia low then M15 close back inside. "
            "Closed reclaim confirms spring; open spike alone does not."
        ),
    )
)
NEW.append(
    entry_ex(
        "08_48",
        "08_range_trading",
        "WAIT sideways - LTF looks trendy but H4 is box",
        "REGIME=sideways H4 | M5 prints clean bull stairs mid-box | Grimes: sharp LTF trends live "
        "inside HTF ranges - do not promote M5 trend playbook.",
        "Wait for confirmation",
        "M5 reaches H4 outer third with closed rejection/acceptance",
        "Do not mistake M5 trend inside H4 sideways for a new regime",
        "strong",
        "A",
        "ltf_trend_inside_htf_range_wait",
        "h4_sideways AND m5_stairs AND mid_box",
        "wait_htf_box_not_m5_trend",
        "Wait for confirmation",
        "M5 trend is path inside H4 sideways - wait for edge",
        0.8,
        "H4_RANGE_LOW=2648, H4_RANGE_HIGH=2666, M5_STAIRS=2655",
        0,
        0,
        0,
        0,
        0,
        auction_state="balance",
        target_mode="none",
        missing_fact="price at H4 outer third with closed response",
        pattern_type="range",
        action="wait",
        direction="none",
        trade_reason=(
            "Concept: Inside an HTF box expect clean LTF trends edge-to-edge (Grimes) - they are "
            "path, not a regime change. Reason: wait - still mid H4 sideways."
        ),
        confirmation_reason=(
            "Confirmation needed: closed response at H4 outer third. M5 stairs mid-box are not entry proof."
        ),
    )
)

# ----- Management: the operator pain point -----
NEW.append(
    mgmt_ex(
        "sw_mgmt_001",
        "08_range_trading",
        "MGMT HOLD - sideways giveback then recover",
        "Short fade from H4 high 2665 open 2663 | Gave back to 2658 (-$5 path) toward mid magnet | "
        "Still inside box | M1 spike against then M5 closes back down | Price recovers toward 2661 | "
        "Do NOT close the -$5 giveback - HOLD for mid target.",
        "Sideways fade: hold normal rotation/giveback inside the box; mid magnet is path not invalidation.",
        "strong",
        "sideways_hold_giveback",
        "sideways AND inside_box AND giveback_then_recover",
        "hold_sideways_giveback_recover",
        "Temporary adverse path to mid magnet - thesis still valid - HOLD",
        0.9,
        "ENTRY=2663, H4_RANGE_HIGH=2665, H4_RANGE_MID=2656, SL_REF=2673, PATH_LOW=2658",
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="sell",
        decision_level_ref="H4_RANGE_MID_2656",
        next_target_ref="H4_RANGE_MID_2656",
        close_confirmed=False,
        trade_reason=(
            "Concept: In sideways, mid is a magnet/target and path often gives back before working "
            "(Brooks). Reason: HOLD - giveback stayed inside the H4 box and recovered; do not cut "
            "on temporary gold loss."
        ),
        confirmation_reason=(
            "Confirmation: no accepted close above entry-edge 2665. M1 adverse spike then M5 resume "
            "down is rotation, not thesis invalidation."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_002",
        "08_range_trading",
        "MGMT HOLD - long spring giveback recovers fast",
        "Long from H4 low spring 2650 | Spike adverse to 2647 then snaps to 2653 in minutes | "
        "Still above structural low | Operator temptation: close small loss | Correct: HOLD - "
        "sideways recovers into mid fast.",
        "Do not panic-close a sideways spring on a fast adverse spike that reclaims.",
        "strong",
        "sideways_hold_fast_recover",
        "sideways AND spring_long AND adverse_spike_reclaim",
        "hold_sideways_fast_recover",
        "Fast adverse spike reclaimed - HOLD toward mid",
        0.91,
        "ENTRY=2650, H4_RANGE_LOW=2648, H4_RANGE_MID=2656, PATH_DIP=2647, NOW=2653",
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="buy",
        decision_level_ref="H4_RANGE_MID_2656",
        next_target_ref="H4_RANGE_MID_2656",
        close_confirmed=False,
        trade_reason=(
            "Concept: Springs/failed lows in a box often produce sharp two-sided bursts "
            "(Grimes/Brooks). Reason: HOLD - price reclaimed above entry after the spike; "
            "closing the tiny loss throws away the mid magnet."
        ),
        confirmation_reason=(
            "Confirmation: no accepted M15 close below H4_RANGE_LOW. Reclaim after spike keeps thesis valid."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_003",
        "08_range_trading",
        "MGMT HOLD - wick beyond edge is expansion not break",
        "Short from balance high | M5 wick prints 2667 above high then closes 2662 inside | "
        "Grimes: penetration != breakout | Do not close on the wick.",
        "Wick outside a sideways boundary is expansion; close only on accepted hold outside.",
        "strong",
        "sideways_hold_wick_expansion",
        "sideways AND wick_outside AND close_inside",
        "hold_wick_not_breakout",
        "Wick beyond edge closed back inside - HOLD",
        0.89,
        "ENTRY=2661, H4_BALANCE_HIGH=2662, WICK_HIGH=2667, M5_CLOSE=2662",
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="sell",
        decision_level_ref="H4_BALANCE_HIGH_2662",
        next_target_ref="H4_BALANCE_LOW_2650",
        close_confirmed=False,
        trade_reason=(
            "Concept: Boundary broken only by accepted closes outside, not a wick "
            "(Grimes/Murphy). Reason: HOLD - expansion wick reclaimed inside."
        ),
        confirmation_reason=(
            "Confirmation: M5 closed back inside balance after the wick. Wick alone is not close permission."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_004",
        "08_range_trading",
        "MGMT CLOSE - accepted break against fade",
        "Short fade from H4 high failed | Two M15 closes hold above 2665 with M5 continuation | "
        "Brooks/Dalton: breakout acceptance - stop fading, CLOSE.",
        "Close sideways fade only after accepted break through the entry edge against you.",
        "strong",
        "sideways_close_accepted_break",
        "sideways_fade AND two_closes_outside_against",
        "close_sideways_accepted_break",
        "Accepted hold above entry-edge - CLOSE short fade",
        0.92,
        "ENTRY=2663, H4_RANGE_HIGH=2665, M15_CLOSE1=2666, M15_CLOSE2=2668",
        management_action="close",
        thesis_state="invalidated",
        confirmation_type="thesis_invalidation_confirmed",
        direction="sell",
        decision_level_ref="H4_RANGE_HIGH_2665",
        next_target_ref="none",
        close_confirmed=True,
        trade_reason=(
            "Concept: Escalate out of sideways only after accepted close outside + hold "
            "(Brooks strength list). Reason: CLOSE - thesis invalidated by acceptance above the fade edge."
        ),
        confirmation_reason=(
            "Confirmation: two M15 closes holding above 2665 with M5 continuation. "
            "This is breakout acceptance, not a wick."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_005",
        "08_range_trading",
        "MGMT PROTECT - mid magnet reached in sideways",
        "Long spring from low working | Price accepted at H4 mid 2656 | Remaining room to high is optional | "
        "Protect: tighten stop under mid - do not give full edge risk back.",
        "After mid magnet is reached on a sideways fade, protect - do not re-risk full edge stop.",
        "strong",
        "sideways_protect_at_mid",
        "sideways AND mid_reached AND acceptance",
        "protect_sideways_mid_hit",
        "Mid magnet accepted - PROTECT stop under mid",
        0.85,
        "ENTRY=2650, H4_RANGE_MID=2656, H4_RANGE_HIGH=2665, DECISION=M5_MID_ACCEPT",
        management_action="protect",
        thesis_state="valid",
        confirmation_type="continuation_acceptance_confirmed",
        direction="buy",
        decision_level_ref="H4_RANGE_MID_2656",
        next_target_ref="H4_RANGE_HIGH_2665",
        close_confirmed=False,
        trade_reason=(
            "Concept: Take profit / reduce risk at mid; never overstay hoping for a breakout "
            "(Brooks). Reason: PROTECT after mid acceptance."
        ),
        confirmation_reason=(
            "Confirmation: M5 acceptance at H4 mid. Protect is allowed; panic-close before mid was wrong."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_006",
        "08_range_trading",
        "MGMT HOLD - do not cut on dollar giveback alone",
        "Sideways short open | Peak +$4 then giveback to -$3 while still under H4 high | "
        "No M15 acceptance above edge | Model must not close because 'in loss'.",
        "Dollar giveback inside a sideways thesis is path context, never a fixed exit rule.",
        "strong",
        "sideways_hold_ignore_pnl_path",
        "sideways AND inside_box AND pnl_giveback_only",
        "hold_ignore_pnl_sideways",
        "In loss but structure intact - HOLD",
        0.9,
        "ENTRY=2662, H4_RANGE_HIGH=2665, PEAK_PNL=+4, NOW_PNL=-3, M15_STATE=inside",
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="sell",
        decision_level_ref="H4_RANGE_HIGH_2665",
        next_target_ref="H4_RANGE_MID_2656",
        close_confirmed=False,
        trade_reason=(
            "Concept: Peak P&L/giveback is path context never a fixed-$ exit (management doctrine) - "
            "especially in sideways. Reason: HOLD despite -$3 while under the entry edge."
        ),
        confirmation_reason=(
            "Confirmation: still no accepted close above 2665. Loss size is not confirmation to close."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_007",
        "08_range_trading",
        "MGMT CLOSE - failed failure resumes breakout",
        "Tried fade of upside break | Fade itself fails - price holds outside and continues | "
        "Brooks failed-failure = with-trend second signal | CLOSE the fade.",
        "When the fade of a breakout fails, exit the fade immediately.",
        "strong",
        "sideways_close_failed_failure",
        "fade_attempt AND holds_outside AND continuation",
        "close_failed_failure",
        "Failed failure - CLOSE fade, breakout resumes",
        0.91,
        "ENTRY=2661, BREAK_LEVEL=2662, HOLD_OUTSIDE=2664, M5_CONT=2666",
        management_action="close",
        thesis_state="invalidated",
        confirmation_type="thesis_invalidation_confirmed",
        direction="sell",
        decision_level_ref="BREAK_LEVEL_2662",
        next_target_ref="none",
        close_confirmed=True,
        trade_reason=(
            "Concept: Failed failure turns the structure into a breakout pullback "
            "(Brooks) - more reliable with-trend than the fade. Reason: CLOSE the fade."
        ),
        confirmation_reason=(
            "Confirmation: holds outside break level with continuation bar. Fade thesis is dead."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "sw_mgmt_008",
        "08_range_trading",
        "MGMT HOLD - overlapping chop after edge fill",
        "Long from low working to mid | Path becomes overlapping M5 chop still above entry spring | "
        "Uncertainty is the sideways state - HOLD unless edge breaks.",
        "Uncertainty/chop after an edge fill is normal sideways behaviour, not an auto-close.",
        "moderate",
        "sideways_hold_chop_path",
        "sideways AND overlapping_path AND above_entry_edge",
        "hold_sideways_chop",
        "Chop toward mid - HOLD",
        0.82,
        "ENTRY=2650, H4_RANGE_LOW=2648, H4_RANGE_MID=2656, M5_CHOP=2653-2655",
        management_action="hold",
        thesis_state="valid",
        confirmation_type="none",
        direction="buy",
        decision_level_ref="H4_RANGE_MID_2656",
        next_target_ref="H4_RANGE_MID_2656",
        close_confirmed=False,
        trade_reason=(
            "Concept: Uncertainty is the diagnostic of a range (Brooks) - expect overlapping path. "
            "Reason: HOLD while above the spring edge."
        ),
        confirmation_reason=(
            "Confirmation: no accepted break below 2648. Overlapping M5 bars are regime noise, not invalidation."
        ),
    )
)

# ----- Regime contrast: trend vs sideways vs reversal -----
NEW.append(
    entry_ex(
        "07_swc_01",
        "07_trend_trading",
        "CONTRAST trend - do not sideways-fade acceptance",
        "REGIME=trend | H4 unfinished bull acceptance above prior high | M1 reject wick at 2668 looks "
        "like fade | Wrong: short like sideways | Right: wait pullback buy or skip.",
        "Wait for confirmation",
        "H4 rejection after failed acceptance",
        "Never apply sideways fade to unfinished HTF acceptance",
        "strong",
        "A",
        "regime_trend_no_sideways_fade",
        "h4_acceptance AND m1_reject_wick",
        "wait_not_fade_acceptance",
        "Wait for confirmation",
        "Trend acceptance - do not sideways-fade the M1 wick",
        0.88,
        "H4_BROKEN_HIGH=2660, M1_WICK=2668, H1_SUPPORT=2658",
        0,
        0,
        0,
        0,
        0,
        auction_state="acceptance",
        target_mode="none",
        missing_fact="H1/H4 rejection after failed acceptance, or pullback to support",
        pattern_type="trend",
        action="wait",
        direction="none",
        trade_reason=(
            "Concept: Trend = unfinished acceptance; sideways fade rules do not apply. "
            "Reason: wait - M1 wick at broken high is not a short."
        ),
        confirmation_reason=(
            "Confirmation needed: true HTF rejection or a with-trend pullback buy. "
            "Local wick is not a regime change."
        ),
    )
)
NEW.append(
    entry_ex(
        "09_swc_01",
        "09_reversal_trading",
        "CONTRAST reversal - needs prior trend then usually becomes range",
        "REGIME=candidate reversal | Prior H4 bull | Trendline break + failed HH test | M15 reject | "
        "Brooks: successful reversal usually births a range first, not opposite spike - target as range.",
        "Short reversal",
        "Accepted reclaim of HH with continuation",
        "Reversal permission then manage as new sideways box",
        "strong",
        "A",
        "reversal_to_range_expectation",
        "prior_trend AND tl_break AND failed_retest",
        "reversal_open_range_target",
        "Short reversal",
        "MTR short - expect range not instant bear trend",
        0.84,
        "H4_TREND_HIGH=2670, TL_BREAK=2662, FAILED_HH=2669, RANGE_TARGET_MID=2658",
        2666.0,
        2676.0,
        2658.0,
        10.0,
        8.0,
        auction_state="rejection",
        pattern_type="reversal",
        action="open",
        direction="sell",
        trade_reason=(
            "Concept: After a valid major reversal sequence the usual next state is a trading range "
            "(Brooks/Grimes), not a clean opposite trend. Reason: short the failed retest, target mid-range."
        ),
        confirmation_reason=(
            "Confirmation: trendline break already done + failed HH + M15 reject close. "
            "Size/target as range, do not demand opposite spike."
        ),
    )
)
NEW.append(
    mgmt_ex(
        "07_swc_02",
        "07_trend_trading",
        "CONTRAST trend MGMT - giveback can invalidate",
        "REGIME=trend long | Acceptance under way | Adverse M15 closes back through breakout level | "
        "Unlike sideways mid magnet, this can be always-in flip - CLOSE/protect per trend rules.",
        "In trend, accepted loss of the breakout level is not 'normal mid rotation'.",
        "strong",
        "trend_close_lost_breakout",
        "trend AND lose_breakout_level_accepted",
        "close_trend_lost_level",
        "Accepted loss of breakout level - CLOSE (not sideways hold)",
        0.88,
        "ENTRY=2662, BREAKOUT=2660, M15_BACK=2658, REGIME=trend",
        management_action="close",
        thesis_state="invalidated",
        confirmation_type="thesis_invalidation_confirmed",
        direction="buy",
        decision_level_ref="BREAKOUT_2660",
        next_target_ref="none",
        close_confirmed=True,
        pattern_type="trend_management",
        trade_reason=(
            "Concept: Trend management is not sideways magnet logic. Reason: CLOSE - accepted "
            "loss of breakout level can flip always-in."
        ),
        confirmation_reason=(
            "Confirmation: M15 accepted back through breakout. Do not hold this as if it were box mid-rotation."
        ),
    )
)


def main() -> None:
    s1 = load("stage_01_principle_foundation.jsonl")
    s2 = load("stage_02_structured_data.jsonl")
    s3 = load("stage_03_detector_definitions.jsonl")
    s4 = load("stage_04_decision_contract.jsonl")

    existing_pids = {r.get("principle_id") for r in s1}
    for p in NEW_PRINCIPLES:
        if p["principle_id"] not in existing_pids:
            s1.append(p)

    new_ids = {row[0]["example_id"] for row in NEW}
    # Drop prior pack rows if re-run.
    s2 = [r for r in s2 if r["example_id"] not in new_ids]
    s3 = [r for r in s3 if r["example_id"] not in new_ids]
    s4 = [r for r in s4 if r["example_id"] not in new_ids]

    holdout_s2 = [r for r in s2 if r["example_id"] in HOLDOUT_IDS]
    train_s2 = [r for r in s2 if r["example_id"] not in HOLDOUT_IDS]
    holdout_ids = {r["example_id"] for r in holdout_s2}
    train_s3 = [r for r in s3 if r["example_id"] not in holdout_ids]
    holdout_s3 = [r for r in s3 if r["example_id"] in holdout_ids]
    train_s4 = [r for r in s4 if r["example_id"] not in holdout_ids]
    holdout_s4 = [r for r in s4 if r["example_id"] in holdout_ids]

    new_s2 = [e[0] for e in NEW]
    new_s3 = [e[1] for e in NEW]
    new_s4 = [e[2] for e in NEW]

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", train_s2 + new_s2 + holdout_s2)
    save("stage_03_detector_definitions.jsonl", train_s3 + new_s3 + holdout_s3)
    save("stage_04_decision_contract.jsonl", train_s4 + new_s4 + holdout_s4)

    print(
        f"appended sideways pack examples={len(NEW)} "
        f"principles={[p['principle_id'] for p in NEW_PRINCIPLES]} "
        f"total_s2={len(train_s2) + len(new_s2) + len(holdout_s2)}"
    )


if __name__ == "__main__":
    main()
