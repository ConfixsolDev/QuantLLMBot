#!/usr/bin/env python3
"""
v6 — fill three remaining doctrine gaps from live store prompts:

1. SOP skip codes + auction_state (sop.md decisiveness_contract / output_contract)
2. In-trade management hold|protect|close + basket/target_mode (qwen_trade_management, targets)
3. M1 EMA cluster + double-test fail close + starter-first (core_skill entry-*/zone-to-trigger)

Preserves skill holdout at end (same IDs as discipline pack v5).
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
    return [json.loads(l) for l in (KNOW / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def save(name: str, rows: list[dict]) -> None:
    (KNOW / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def enrich(row: dict) -> dict:
    entry = float(row.get("entry_price") or 0)
    td = (row.get("trade_decision") or "").lower()
    role = row.get("role") or "entry"

    if role == "management":
        mg = (row.get("management_action") or "hold").lower()
        row["action"] = "open"  # position already open; entry action N/A
        row["direction"] = row.get("direction") or ("sell" if "short" in td else "buy")
        row["management_action"] = mg
        conf = int(row.get("confidence") or 70)
        row["confidence"] = conf
        return row

    if row.get("action") and row.get("direction"):
        pass
    elif td.startswith("skip") or row.get("skip_reason_code"):
        row["action"], row["direction"] = "skip", "none"
    elif td.startswith("wait"):
        row["action"], row["direction"] = "wait", "none"
    elif entry <= 0:
        row["action"], row["direction"] = ("skip" if "skip" in td else "wait"), "none"
    elif "short" in td or "sell" in td:
        row["action"], row["direction"] = "open", "sell"
    elif "long" in td or "buy" in td:
        row["action"], row["direction"] = "open", "buy"
    else:
        row["action"] = "open"
        row["direction"] = "sell" if entry and row.get("sl_price", 0) > entry else "buy"

    if entry and row["direction"] in ("buy", "sell"):
        if row.get("sl_price", 0) > entry:
            row["direction"] = "sell"
        elif row.get("sl_price", 0) and row.get("sl_price", 0) < entry:
            row["direction"] = "buy"

    conv = float(row.get("conviction_score") or 0.5)
    conf = int(row.get("confidence") or round(max(0, min(100, conv * 100))))
    if row["action"] in ("wait", "skip"):
        conf = min(conf, 50)
    elif row["action"] == "open" and conf < 51:
        conf = max(51, conf)
    row["confidence"] = conf
    row.setdefault("role", "entry")
    row.setdefault("auction_state", "unclear")
    row.setdefault("target_mode", "none" if row["action"] != "open" else "scalp")
    if row["action"] != "skip":
        row.setdefault("skip_reason_code", None)
    return row


def entry_ex(
    eid, topic, title, setup, decision, invalidation, why, evidence, bucket,
    detector_name, logic, detector_output, trade_decision, conditions, conviction,
    key_levels, entry, sl, tp, sl_usd, tp_usd,
    *,
    auction_state="rejection",
    skip_reason_code=None,
    target_mode="scalp",
    missing_fact=None,
    pattern_type="level",
    action=None,
    direction=None,
):
    risk = f"SL ${sl_usd} at {sl} | TP ${tp_usd} at {tp} | Entry {entry}"
    if entry <= 0:
        risk = f"SL N/A | TP N/A | Entry N/A — {skip_reason_code or 'wait/skip'}"
    s2 = {
        "example_id": eid, "topic": topic, "title": title,
        "setup": f"LEVELS: {key_levels} | PATTERN={pattern_type} | AUCTION={auction_state} | " + setup,
        "decision": decision, "invalidation": invalidation, "why": why,
        "evidence": evidence, "bucket": bucket,
    }
    s3 = {
        "example_id": eid, "detector_type": "heuristic", "detector_name": detector_name,
        "input_signals": ["price", "volume", "time", "bars", "levels", "session"],
        "logic": logic, "thresholds": {"tp_usd": [5, 12], "sl_usd": [3, 4]},
        "output": "enum(valid, invalid)",
    }
    s4 = {
        "example_id": eid, "role": "entry",
        "detector_output": detector_output, "trade_decision": trade_decision,
        "decision_conditions": conditions, "evidence_label": evidence,
        "conviction_score": conviction, "risk_control": risk,
        "key_levels": key_levels, "entry_price": entry, "sl_price": sl, "tp_price": tp,
        "sl_usd": sl_usd, "tp_usd": tp_usd, "pattern_type": pattern_type,
        "auction_state": auction_state, "skip_reason_code": skip_reason_code,
        "target_mode": target_mode, "missing_fact": missing_fact,
    }
    if action:
        s4["action"] = action
    if direction:
        s4["direction"] = direction
    return s2, s3, s4


def mgmt_ex(
    eid, topic, title, setup, why, evidence,
    detector_name, logic, detector_output, conditions, conviction,
    key_levels, *,
    management_action, thesis_state, confirmation_type, direction,
    decision_level_ref, next_target_ref, close_confirmed=False,
    pattern_type="management",
):
    s2 = {
        "example_id": eid, "topic": topic, "title": title,
        "setup": (
            f"LEVELS: {key_levels} | PATTERN={pattern_type} | ROLE=management | "
            f"MGMT={management_action} | THESIS={thesis_state} | " + setup
        ),
        "decision": management_action.title(),
        "invalidation": "Thesis invalidation accepted through on M1+M5",
        "why": why, "evidence": evidence, "bucket": "A",
    }
    s3 = {
        "example_id": eid, "detector_type": "heuristic", "detector_name": detector_name,
        "input_signals": ["price", "levels", "m1", "m5", "position"],
        "logic": logic, "thresholds": {}, "output": "enum(hold, protect, close)",
    }
    s4 = {
        "example_id": eid, "role": "management",
        "detector_output": detector_output,
        "trade_decision": management_action.title(),
        "decision_conditions": conditions, "evidence_label": evidence,
        "conviction_score": conviction,
        "risk_control": f"management={management_action}; thesis={thesis_state}",
        "key_levels": key_levels, "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
        "sl_usd": 0.0, "tp_usd": 0.0, "pattern_type": pattern_type,
        "action": "open", "direction": direction, "confidence": int(conviction * 100),
        "management_action": management_action, "thesis_state": thesis_state,
        "confirmation_type": confirmation_type,
        "decision_level_ref": decision_level_ref, "next_target_ref": next_target_ref,
        "close_confirmed": close_confirmed,
        "auction_state": "transition" if management_action == "close" else "acceptance",
        "skip_reason_code": None, "target_mode": "none", "missing_fact": None,
    }
    return s2, s3, s4


NEW_PRINCIPLES = [
    {
        "principle_id": "P054",
        "topic": "01_market",
        "principle_name": "SOP Skip Codes — Named Gate Only",
        "core_concept": "Skip is allowed only with skip_reason_code: off_session, news_window, daily_risk_pause, empty_midrange, compressed, htf_conflict, fixed_profile_mismatch. Always state auction_state (acceptance|rejection|balance|transition|unclear).",
        "foundational_rule": "Pretty setup under a skip code is still skip. Wait needs one concrete missing_fact with a price — not 'more confirmation'.",
        "why_matters": "Live SOP validator rejects free-text skips; model must emit codes.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["sop_skip_codes", "auction_state_label", "armed_wait_missing_fact"],
    },
    {
        "principle_id": "P055",
        "topic": "07_trend_trading",
        "principle_name": "In-Trade Management — Hold Protect Close Level-to-Level",
        "core_concept": "After entry, manage one position: hold through acceptance toward next level; protect (tighten) only after M1+M5 continuation acceptance; close on confirmed target rejection or thesis invalidation with M1+M5 at one decision level. No average, reverse, or invent basket mid-trade.",
        "foundational_rule": "Peak P&L/giveback is path context never a fixed-$ exit. Wick alone is not confirmation.",
        "why_matters": "Entry-only training leaves the model unable to manage open trades.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["mgmt_hold", "mgmt_protect", "mgmt_close"],
    },
    {
        "principle_id": "P056",
        "topic": "09_reversal_trading",
        "principle_name": "M1 Double-Test Fail + EMA Timing + Starter-First",
        "core_concept": "At mapped double top: M1 probes zone, fails to close above, closes back inside → sell next M1 open (no mandatory M5). Inverse at double bottom. EMA 3/14/31 is timing reclaim context only. First fresh closed response at level can be starter when room + one context fact agree — do not force second test.",
        "foundational_rule": "Never chase after price expands away from M1 EMA cluster into opposing level.",
        "why_matters": "core_skill execution trigger; without examples model waits forever or chases.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["m1_double_test_fail", "m1_ema_reclaim", "starter_first"],
    },
]

NEW = [
    # ========== SOP SKIP CODES + AUCTION ==========
    entry_ex(
        "01_29", "01_market", "SKIP off_session — NY no-new-entry",
        "Clock NY 17:30 UTC | Clean M15 rejection at H1_RESISTANCE | Session rules: NY = no-new-entry | skip_reason_code=off_session.",
        "Skip", "London or overlap next day with fresh response", "SOP off_session", "strong", "A",
        "sop_skip_off_session", "session_ny AND no_new_entry", "skip_off_session_ny",
        "Skip", "NY session — off_session skip despite clean rejection", 0.92,
        "SESSION=new_york, TRADE_PERMITTED=false, H1_RESISTANCE=2662", 0, 0, 0, 0, 0,
        auction_state="rejection", skip_reason_code="off_session", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_30", "01_market", "SKIP news_window — calendar blocked",
        "London | H4 support bounce forming | news_guard=blocked high-impact ±60min | skip_reason_code=news_window.",
        "Skip", "News window ends + fresh closed review", "SOP news_window", "strong", "A",
        "sop_skip_news", "news_guard_blocked", "skip_news_window",
        "Skip", "news_window active — skip even with H4 support bounce", 0.93,
        "NEWS_GUARD=blocked, SESSION=london, H4_SUPPORT=2648", 0, 0, 0, 0, 0,
        auction_state="unclear", skip_reason_code="news_window", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_31", "01_market", "SKIP daily_risk_pause — hour memory paused",
        "Overlap | Valid M15 failure test short | day_working_memory risk_posture=pause_new_entries | skip_reason_code=daily_risk_pause.",
        "Skip", "Next hour review restores normal posture", "SOP daily_risk_pause", "strong", "A",
        "sop_skip_risk_pause", "risk_posture_pause", "skip_daily_risk_pause",
        "Skip", "daily_risk_pause — no new entry this hour", 0.9,
        "RISK_POSTURE=pause_new_entries, M15_FAIL_TEST=2660", 0, 0, 0, 0, 0,
        auction_state="rejection", skip_reason_code="daily_risk_pause", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_32", "01_market", "SKIP empty_midrange — no mapped level in reach",
        "Price mid daily range | Nearest scored level >$12 away | No mapped zone in realistic reach | skip_reason_code=empty_midrange.",
        "Skip", "Price approaches scored H4/H1 zone", "SOP empty_midrange", "strong", "A",
        "sop_skip_midrange", "no_level_in_reach", "skip_empty_midrange",
        "Skip", "empty_midrange — no tradeable mapped level", 0.88,
        "H4_RANGE_MID=2656, NEAREST_LEVEL_DIST_USD=12", 0, 0, 0, 0, 0,
        auction_state="balance", skip_reason_code="empty_midrange", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_33", "01_market", "SKIP compressed — no expansion evidence",
        "Asia mid | M15 range <0.3 ATR 8 bars | Low tick participation | Looks like micro pin | skip_reason_code=compressed.",
        "Skip", "Volatility expands with acceptance beyond Asia box", "SOP compressed", "strong", "A",
        "sop_skip_compressed", "low_vol AND no_expansion", "skip_compressed",
        "Skip", "compressed conditions — skip micro pin", 0.86,
        "SESSION=asia, M15_ATR_FRAC=0.25, TV_RATIO=0.4", 0, 0, 0, 0, 0,
        auction_state="balance", skip_reason_code="compressed", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_34", "01_market", "SKIP htf_conflict — H4 bear vs M30 demand",
        "H4 accepted breakdown below 2650 | M30 printing two closed rejections at 2652 demand | Both facts current and opposing | skip_reason_code=htf_conflict | Quote both in evidence.",
        "Skip", "M30 fails or H4 reclaims 2650", "SOP htf_conflict", "strong", "A",
        "sop_skip_htf_conflict", "h4_breakdown AND m30_demand", "skip_htf_conflict",
        "Skip", "htf_conflict — H4 breakdown vs fresh M30 demand", 0.85,
        "H4_BREAK=2650, M30_DEMAND=2652", 0, 0, 0, 0, 0,
        auction_state="unclear", skip_reason_code="htf_conflict", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_35", "01_market", "SKIP fixed_profile_mismatch — stop/target won't fit",
        "Valid H4 rejection short idea | execution_profile fixed_r 3-stop / targets 6,9,12 | Nearest opposing level only $4 away | Geometry cannot fit | skip_reason_code=fixed_profile_mismatch.",
        "Skip", "Room ≥6 units appears or profile not supplied", "SOP fixed_profile_mismatch", "strong", "A",
        "sop_skip_fixed_profile", "valid_structure AND room<min_target", "skip_fixed_profile",
        "Skip", "fixed_profile_mismatch — structure ok, room fails 6-unit min", 0.84,
        "H4_RESISTANCE=2665, NEXT_SUPPORT=2661, PROFILE=fixed_r_3_6_9_12", 0, 0, 0, 0, 0,
        auction_state="rejection", skip_reason_code="fixed_profile_mismatch", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "01_36", "01_market", "WAIT armed — missing M1 reclaim close",
        "H1 61.8 support 2650 | Auction transition | Buy thesis armed | missing_fact must be one closed-bar price event.",
        "Wait for confirmation", "M1 close above 2650.6 reclaiming EMA cluster", "Armed wait missing_fact", "strong", "A",
        "armed_wait_missing_fact", "level_ok AND response_incomplete", "wait_m1_reclaim",
        "Wait for confirmation", "Armed buy — missing M1 close above 2650.6", 0.55,
        "H1_FIB_618=2650, EMA_CLUSTER=2650.4", 0, 0, 0, 0, 0,
        auction_state="transition", skip_reason_code=None, target_mode="starter_basket",
        missing_fact="M1 close above 2650.6 reclaiming the EMA cluster",
        pattern_type="wait", action="wait", direction="none",
    ),
    entry_ex(
        "01_37", "01_market", "OPEN sell — auction rejection at mapped resistance",
        "London | H1_RESISTANCE 2660 | M15 second test closed back below with upper wick | auction_state=rejection | Room to 2653 | Scalp short.",
        "Short scalp", "M15 closes above 2660", "Auction rejection open", "strong", "A",
        "auction_rejection_open", "mapped_level AND closed_rejection AND room", "open_sell_rejection",
        "Short scalp", "rejection at H1 resistance — open sell scalp", 0.78,
        "H1_RESISTANCE=2660, M15_CLOSE=2658, NEXT_SUPPORT=2653", 2658.0, 2661.0, 2653.0, 3.0, 5.0,
        auction_state="rejection", skip_reason_code=None, target_mode="scalp",
        pattern_type="level", action="open", direction="sell",
    ),
    entry_ex(
        "01_38", "01_market", "OPEN buy — auction acceptance break+retest",
        "H4 bull | M15 broke 2655, retest holds 2656 | auction_state=acceptance | target_mode=directional_basket runner to H4 high.",
        "Long breakout", "M15 closes back below 2655", "Acceptance basket open", "strong", "A",
        "auction_acceptance_basket", "break AND retest_hold AND h4_bull", "open_buy_acceptance_basket",
        "Long breakout", "acceptance retest — directional basket long", 0.82,
        "M15_BREAK=2655, RETEST=2656, H4_PREVIOUS_HIGH=2668", 2657.0, 2654.0, 2664.0, 3.0, 7.0,
        auction_state="acceptance", skip_reason_code=None, target_mode="directional_basket",
        pattern_type="breakout", action="open", direction="buy",
    ),

    # ========== MANAGEMENT hold/protect/close ==========
    mgmt_ex(
        "10_01", "07_trend_trading", "MGMT HOLD — acceptance toward next level",
        "Long open from 2650 | Reached M5_SUPPORT flip 2656 with M1+M5 acceptance continuing up | Peak +$7 | Do NOT close on $ — HOLD to next target H1_RESISTANCE 2662.",
        "Level-to-level hold", "strong",
        "mgmt_hold_acceptance", "reached_level AND m1_m5_accept_continue", "mgmt_hold_valid",
        "Reached favorable level with continuation acceptance — hold", 0.8,
        "ENTRY=2650, DECISION_LEVEL=M5_FLIP_2656, NEXT_TARGET=H1_RESISTANCE_2662",
        management_action="hold", thesis_state="valid",
        confirmation_type="continuation_acceptance_confirmed",
        direction="buy", decision_level_ref="M5_FLIP_2656", next_target_ref="H1_RESISTANCE_2662",
    ),
    mgmt_ex(
        "10_02", "07_trend_trading", "MGMT PROTECT — tighten after continuation",
        "Long open | M1+M5 accepted through 2658 toward 2662 | Thesis valid | PROTECT: tighten stop to supplied confirmed level 2655 — never widen.",
        "Protect tighten stop", "strong",
        "mgmt_protect", "continuation_accept AND tighten_only", "mgmt_protect_valid",
        "Continuation acceptance — protect tighten to 2655", 0.78,
        "ENTRY=2650, CONFIRM_LEVEL=2658, PROTECT_STOP=2655, NEXT=2662",
        management_action="protect", thesis_state="valid",
        confirmation_type="continuation_acceptance_confirmed",
        direction="buy", decision_level_ref="M15_ACCEPT_2658", next_target_ref="H1_RESISTANCE_2662",
    ),
    mgmt_ex(
        "10_03", "09_reversal_trading", "MGMT CLOSE — target rejection confirmed",
        "Short open targeting mid 2655 | Price reached 2655 | M1 probe fails to extend, M1+M5 close back up through decision level | target_rejection_confirmed → CLOSE.",
        "Close on target rejection", "strong",
        "mgmt_close_target_reject", "reached_target AND m1_m5_reject", "mgmt_close_target",
        "Target level rejected position direction — close", 0.86,
        "ENTRY=2662, TARGET=2655, DECISION_LEVEL=2655",
        management_action="close", thesis_state="target_response",
        confirmation_type="target_rejection_confirmed",
        direction="sell", decision_level_ref="H4_RANGE_MID_2655", next_target_ref="none",
        close_confirmed=True,
    ),
    mgmt_ex(
        "10_04", "09_reversal_trading", "MGMT CLOSE — thesis invalidation accepted",
        "Short from failure test 2660 | Invalidation was M15 accept above 2660 | Now M1+M5 closed acceptance above 2661 | thesis_invalidation_confirmed → CLOSE. Do not hold hope.",
        "Close on thesis invalidation", "strong",
        "mgmt_close_invalidation", "invalidation_accepted_m1_m5", "mgmt_close_invalid",
        "Immutable invalidation accepted through — close", 0.9,
        "ENTRY=2658, INVALIDATION=2660, M15_ACCEPT=2661",
        management_action="close", thesis_state="invalidated",
        confirmation_type="thesis_invalidation_confirmed",
        direction="sell", decision_level_ref="H1_RESISTANCE_2660", next_target_ref="none",
        close_confirmed=True,
    ),
    mgmt_ex(
        "10_05", "07_trend_trading", "MGMT HOLD — adverse incomplete, wick only",
        "Long open | One M1 wick against through 2654 | M5 still closed above | Peak giveback visible | NOT confirmation | HOLD confirmation_type=none.",
        "Hold — wick not confirmation", "strong",
        "mgmt_hold_incomplete", "adverse_wick_only AND m5_holds", "mgmt_hold_wick",
        "Adverse wick without M1+M5 confirmation — hold", 0.74,
        "ENTRY=2650, WICK_LOW=2653, M5_CLOSE=2656, NEXT=2662",
        management_action="hold", thesis_state="weakening",
        confirmation_type="none",
        direction="buy", decision_level_ref="M5_SUPPORT_2654", next_target_ref="H1_RESISTANCE_2662",
    ),
    mgmt_ex(
        "10_06", "07_trend_trading", "MGMT CLOSE — momentum reversal confirmed",
        "Long open | Reached 2660 | M1+M5 print momentum reversal closes below decision level against position | CLOSE — cannot describe as hold.",
        "Close momentum reversal", "strong",
        "mgmt_close_momentum", "m1_m5_momentum_reversal", "mgmt_close_momentum",
        "Adverse momentum reversal confirmed at decision level — close", 0.87,
        "ENTRY=2650, DECISION_LEVEL=2660, M5_BEAR_CLOSE=2658",
        management_action="close", thesis_state="invalidated",
        confirmation_type="momentum_reversal_confirmed",
        direction="buy", decision_level_ref="H1_RESISTANCE_2660", next_target_ref="none",
        close_confirmed=True,
    ),

    # ========== BASKET / TARGET MODE ==========
    entry_ex(
        "07_35", "07_trend_trading", "OPEN starter_basket — first response + runner level",
        "H4 bull | First M5 rejection at H1_SUPPORT 2650 with context | target_mode=starter_basket | first_target M5 oppose 2656 | runner H1 2662 | Partial only if paid.",
        "Long scalp", "M5 closes below 2648", "Starter basket", "strong", "A",
        "starter_basket_open", "first_response AND room_runner", "open_starter_basket_long",
        "Long scalp", "starter_basket first target 2656 runner 2662", 0.76,
        "H1_SUPPORT=2650, FIRST_TARGET=2656, RUNNER=2662", 2651.0, 2648.0, 2656.0, 3.0, 5.0,
        auction_state="rejection", target_mode="starter_basket",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "07_36", "07_trend_trading", "OPEN directional_basket — multi-TF agree",
        "H4+H1+M15 bull aligned | Pullback long at M15_MA | target_mode=directional_basket | first 2660 runner 2668 H4 high.",
        "Long continuation", "H1_MA breaks down", "Directional basket", "strong", "A",
        "directional_basket_open", "multi_tf_align AND pullback", "open_directional_basket",
        "Long continuation", "directional_basket first 2660 runner 2668", 0.84,
        "M15_MA=2654, FIRST_TARGET=2660, RUNNER=H4_HIGH_2668", 2655.0, 2652.0, 2660.0, 3.0, 5.0,
        auction_state="acceptance", target_mode="directional_basket",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "07_37", "07_trend_trading", "OPEN scalp only — counter-context fade",
        "H4 bull intact | Short fade at H1 resistance (counter-context) | target_mode=scalp | Exit fully at nearest M5 oppose — no runner.",
        "Short scalp", "M15 closes above 2662", "Counter-context scalp", "strong", "A",
        "scalp_counter_context", "fade AND htf_against AND nearest_exit", "open_scalp_short",
        "Short scalp", "counter-context scalp full exit at nearest oppose", 0.72,
        "H1_RESISTANCE=2660, M5_OPPOSE=2655, H4_BIAS=bull", 2659.0, 2662.0, 2655.0, 3.0, 4.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fakeout", action="open", direction="sell",
    ),
    entry_ex(
        "07_38", "07_trend_trading", "BASKET add FORBIDDEN — not positive / compressed",
        "Long basket open small profit | New add signal mid-range compressed | Basket rules: no add when compressed or not meaningfully positive | SKIP add.",
        "Skip", "Basket positive by meaningful unit + room + not compressed", "Basket add veto", "strong", "A",
        "basket_add_veto", "compressed OR not_positive", "skip_basket_add",
        "Skip", "Basket add forbidden — compressed / not paid", 0.88,
        "BASKET_STATE=open_small, COMPRESSED=true, MIDRANGE=true", 0, 0, 0, 0, 0,
        auction_state="balance", skip_reason_code="compressed", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),

    # ========== M1 EMA / DOUBLE-TEST / STARTER-FIRST ==========
    entry_ex(
        "09_109", "09_reversal_trading", "M1 double-top fail — SELL next M1 open (no M5 wait)",
        "Mapped double top / H1_RESISTANCE zone 2660–2663 | M1 probes 2662, fails to close above, closes back inside 2659 | core_skill: sell next M1 open — do NOT demand M5 confirm | Scalp.",
        "Short scalp", "M1 accepts above 2663", "M1 double-test fail sell", "strong", "A",
        "m1_double_test_fail", "m1_probe_fail_close_inside AND mapped_dt", "m1_dt_sell_valid",
        "Short scalp", "M1 double-top fail close — sell next open, no M5 wait", 0.86,
        "H1_RESISTANCE=2660-2663, M1_HIGH=2662, M1_CLOSE=2659, M5_OPPOSE=2654", 2659.0, 2662.0, 2654.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="sell",
    ),
    entry_ex(
        "09_110", "09_reversal_trading", "M1 double-bottom fail — BUY next M1 open",
        "Mapped double bottom H1_SUPPORT 2648–2651 | M1 probes 2647, fails to close below, closes back inside 2650 | Buy next M1 open | No mandatory M5 | Scalp if counter-context.",
        "Long scalp", "M1 accepts below 2647", "M1 double-test fail buy", "strong", "A",
        "m1_double_test_fail", "m1_probe_fail_close_inside AND mapped_db", "m1_db_buy_valid",
        "Long scalp", "M1 double-bottom fail close — buy next open", 0.86,
        "H1_SUPPORT=2648-2651, M1_LOW=2647, M1_CLOSE=2650, M5_OPPOSE=2655", 2650.0, 2647.0, 2655.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "09_111", "09_reversal_trading", "M1 EMA reclaim sell — entry-sell timing",
        "At H1_RESISTANCE 2660 | Buying fails | Bearish M1 reclaims down through EMA 3/14/31 cluster | Enter next M1 open | Invalidation above rejection extreme | EMA is timing not reason.",
        "Short scalp", "M1 closes back above EMA31 with acceptance", "M1 EMA sell entry", "strong", "A",
        "m1_ema_reclaim_sell", "resistance AND m1_bear_reclaim_ema", "m1_ema_sell_valid",
        "Short scalp", "M1 EMA cluster reclaim down at resistance — sell timing", 0.8,
        "H1_RESISTANCE=2660, EMA3=2659, EMA14=2658, EMA31=2657", 2658.0, 2661.0, 2653.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="sell",
    ),
    entry_ex(
        "09_112", "09_reversal_trading", "M1 EMA reclaim buy — entry-buy timing",
        "At H1_SUPPORT 2650 | Selling fails | Bullish M1 reclaims up through EMA 3/14/31 | Enter next M1 open | Stop below rejection extreme.",
        "Long scalp", "M1 closes back below EMA31", "M1 EMA buy entry", "strong", "A",
        "m1_ema_reclaim_buy", "support AND m1_bull_reclaim_ema", "m1_ema_buy_valid",
        "Long scalp", "M1 EMA cluster reclaim up at support — buy timing", 0.8,
        "H1_SUPPORT=2650, EMA3=2651, EMA14=2652, EMA31=2653", 2652.0, 2649.0, 2657.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "09_113", "09_reversal_trading", "STARTER-FIRST — first M1 rejection OPEN sell",
        "Mapped H1 resistance | First closed M1 rejection fresh with London context + room to 2654 | Do NOT wait for second test | starter open now | Second test only raises confidence/add.",
        "Short scalp", "M1 accepts above 2661", "Starter-first sell", "strong", "A",
        "starter_first", "first_closed_response AND room AND context", "starter_first_sell",
        "Short scalp", "First-response starter sell — no forced second test", 0.77,
        "H1_RESISTANCE=2660, M1_REJECT_CLOSE=2659, CONTEXT=london", 2659.0, 2662.0, 2654.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="sell",
    ),
    entry_ex(
        "09_114", "09_reversal_trading", "STARTER-FIRST — first M5 reclaim OPEN buy",
        "Mapped support | First closed M5 reclaim with H4 bull path + room | Open starter long now | Waiting for second test is invalid when response already visible.",
        "Long scalp", "M5 closes back below 2649", "Starter-first buy", "strong", "A",
        "starter_first", "first_closed_response AND h4_bull AND room", "starter_first_buy",
        "Long scalp", "First-response starter buy — do not defer for second test", 0.78,
        "H1_SUPPORT=2650, M5_RECLAIM=2651, H4_BIAS=bull", 2651.0, 2648.0, 2657.0, 3.0, 6.0,
        auction_state="rejection", target_mode="starter_basket",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "09_115", "09_reversal_trading", "ENTRY-VETO — chase after expand away from EMA",
        "Signal was valid at EMA cluster 2655 | Price already ran to 2662 into H1 resistance | Late M5 BOS confirms move | Never chase — WAIT for retest.",
        "Wait for confirmation", "Retest back to EMA/cluster with fresh response", "Chase veto", "strong", "A",
        "entry_veto_chase", "expanded_away AND into_opposing_level", "wait_chase_retest",
        "Wait for confirmation", "Chase veto — expanded away from M1 cluster into resistance", 0.88,
        "EMA_CLUSTER=2655, NOW=2662, H1_RESISTANCE=2662", 0, 0, 0, 0, 0,
        auction_state="acceptance", skip_reason_code=None, target_mode="none",
        missing_fact="Retest back to EMA cluster near 2655 with fresh closed response",
        pattern_type="wait", action="wait", direction="none",
    ),
    entry_ex(
        "09_116", "09_reversal_trading", "M1 fail close BAD — still waiting (incomplete)",
        "Double-top zone | M1 wick above 2662 but M1 still OPEN / not closed back inside | Do not sell unfinished candle | WAIT missing_fact = M1 close back inside ≤2660.",
        "Wait for confirmation", "M1 closes back inside ≤2660 or accepts above 2663", "Unfinished M1 wait", "strong", "A",
        "m1_unfinished_wait", "m1_forming_wick AND not_closed", "wait_m1_close",
        "Wait for confirmation", "M1 still forming at double top — wait fail close", 0.7,
        "H1_RESISTANCE=2660-2663, M1_FORMING_HIGH=2662", 0, 0, 0, 0, 0,
        auction_state="transition", target_mode="scalp",
        missing_fact="M1 close back inside at or below 2660 after probe",
        pattern_type="wait", action="wait", direction="none",
    ),
]


def main() -> None:
    s1 = load("stage_01_principle_foundation.jsonl")
    s2 = load("stage_02_structured_data.jsonl")
    s3 = load("stage_03_detector_definitions.jsonl")
    s4 = load("stage_04_decision_contract.jsonl")

    s2m = {r["example_id"]: r for r in s2}
    s3m = {r["example_id"]: r for r in s3}
    s4m = {r["example_id"]: r for r in s4}

    existing_p = {p["principle_id"] for p in s1}
    for p in NEW_PRINCIPLES:
        if p["principle_id"] not in existing_p:
            s1.append(p)

    new_ids = {e[0]["example_id"] for e in NEW}
    for eid in list(new_ids):
        s2m.pop(eid, None)
        s3m.pop(eid, None)
        s4m.pop(eid, None)

    for e in NEW:
        s2m[e[0]["example_id"]] = e[0]
        s3m[e[1]["example_id"]] = e[1]
        s4m[e[2]["example_id"]] = e[2]

    # Backfill SOP fields on older rows where missing
    for eid, row in s4m.items():
        if "auction_state" not in row:
            td = (row.get("trade_decision") or "").lower()
            if "skip" in td or "wait" in td:
                row["auction_state"] = "unclear"
            elif "breakout" in td or "continuation" in td:
                row["auction_state"] = "acceptance"
            else:
                row["auction_state"] = "rejection"
        if "skip_reason_code" not in row:
            td = (row.get("trade_decision") or "").lower()
            setup = (s2m.get(eid) or {}).get("setup", "").lower()
            code = None
            if "news" in setup or "news_window" in setup:
                code = "news_window"
            elif "pre-london" in setup or "off_session" in setup or "trade_permitted=false" in setup:
                code = "off_session"
            elif "mid-range" in setup or "midrange" in setup or "no level" in setup:
                code = "empty_midrange"
            elif row.get("action") == "skip" or td.startswith("skip"):
                code = "empty_midrange"  # generic fallback only if already skip
            row["skip_reason_code"] = code if (row.get("action") == "skip" or td.startswith("skip")) else None
            if code and not (row.get("action") == "skip" or td.startswith("skip")):
                row["skip_reason_code"] = None
        if "target_mode" not in row:
            td = (row.get("trade_decision") or "").lower()
            if float(row.get("entry_price") or 0) <= 0 or "skip" in td or "wait" in td:
                row["target_mode"] = "none"
            elif "continuation" in td or "breakout" in td or "trend" in td:
                row["target_mode"] = "directional_basket"
            else:
                row["target_mode"] = "scalp"
        if "role" not in row:
            row["role"] = "management" if row.get("management_action") else "entry"
        if "missing_fact" not in row:
            row["missing_fact"] = None
        s4m[eid] = enrich(row)

    holdout = set(HOLDOUT_IDS)
    missing = [i for i in HOLDOUT_IDS if i not in s2m]
    if missing:
        raise SystemExit(f"Holdout missing: {missing}")

    train_ids = sorted(i for i in s2m if i not in holdout)
    ordered = train_ids + HOLDOUT_IDS

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", [s2m[i] for i in ordered])
    save("stage_03_detector_definitions.jsonl", [s3m[i] for i in ordered])
    save("stage_04_decision_contract.jsonl", [s4m[i] for i in ordered])

    skips = sum(1 for e in NEW if e[2].get("skip_reason_code"))
    mgmt = sum(1 for e in NEW if e[2].get("role") == "management")
    m1 = sum(1 for e in NEW if e[0]["example_id"].startswith("09_1") and int(e[0]["example_id"].split("_")[1]) >= 109)
    print(f"Added {len(NEW)} examples (skip_coded={skips}, management={mgmt}, m1_exec~={m1})")
    print(f"Principles: {len(s1)}")
    print(f"Total: {len(ordered)} | Train: {len(train_ids)} | Holdout: {len(HOLDOUT_IDS)}")
    print(f"Config: training_lines_end={len(train_ids)} test_end={len(ordered)}")


if __name__ == "__main__":
    main()
