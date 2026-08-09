#!/usr/bin/env python3
"""
Discipline pack v5:
1. Quarantine/rewrite poison seeds that contradict topic summaries + core_skill
2. Add sell/exit, acceptance-vs-wick, session-vol, forbid-list examples
3. Reorder so skill-focused holdout sits at end (replaces thin 09_05–09_14)

Aligned with live qwen_cached_entry: Action open|wait|skip, Direction buy|sell|none,
Confidence 0-100, named levels, Entry/SL/TP.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"

# New holdout — exercises levels, fakeout/sell, session, skip, nested path
HOLDOUT_IDS = [
    "02_35",  # D1 close reaction fade SHORT (levels)
    "09_100", # M15 false retest SHORT (fakeout + sell)
    "01_14",  # Asia high sweep SHORT (session fakeout)
    "01_16",  # London first move WAIT
    "09_99",  # M15 role-reversal retest SHORT
    "04_28",  # H4/H1 nested LONG continuation
    "07_19",  # Mid daily range SKIP
    "08_21",  # H4 range bottom fakeout LONG
    "09_85",  # M15 swing high FAKEOUT SHORT
    "02_31",  # M5 wick-only WAIT (acceptance vs wick)
]


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (KNOW / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def save(name: str, rows: list[dict]) -> None:
    (KNOW / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def map_action_direction(trade_decision: str, entry: float) -> tuple[str, str]:
    td = (trade_decision or "").lower()
    if any(w in td for w in ("skip",)):
        return "skip", "none"
    if any(w in td for w in ("wait",)):
        return "wait", "none"
    if entry in (0, 0.0, None):
        if "skip" in td:
            return "skip", "none"
        return "wait", "none"
    if any(w in td for w in ("short", "sell")) and "long" not in td:
        return "open", "sell"
    if any(w in td for w in ("long", "buy")) and "short" not in td:
        return "open", "buy"
    if "reverse" in td or "reversal" in td:
        return "open", "sell"  # default; caller may override
    return "open", "buy"


def enrich_s4(row: dict) -> dict:
    """Add Action/Direction/Confidence 0-100 for prompt bridge."""
    entry = float(row.get("entry_price") or 0)
    action, direction = map_action_direction(row.get("trade_decision", ""), entry)
    # Override reverse with geometry
    if direction in ("buy", "sell") and entry:
        if row.get("sl_price", 0) > entry:
            direction = "sell"
        elif row.get("sl_price", 0) and row.get("sl_price", 0) < entry:
            direction = "buy"
    conv = float(row.get("conviction_score") or 0.5)
    conf = int(round(max(0, min(100, conv * 100))))
    if action in ("wait", "skip"):
        conf = min(conf, 50)
    elif conf < 51 and action == "open":
        conf = max(51, conf)
    row["action"] = action
    row["direction"] = direction
    row["confidence"] = conf
    return row


def rewrite_poison(s2: dict, s3: dict, s4: dict) -> None:
    """In-place quarantine of doctrine-breaking seeds."""
    eid = s2["example_id"]

    if eid == "01_10":
        s2.update({
            "title": "High-impact release window — SKIP (news gate)",
            "setup": (
                "LEVELS: NEWS_WINDOW=blocked, SESSION=london | PATTERN=skip | "
                "High-impact release ±60min | Cache/calendar says news_window | "
                "Structure looks breakout-ready — FORBIDDEN. Skip with news_window."
            ),
            "decision": "Skip",
            "invalidation": "News window ends AND fresh closed response",
            "why": "News exclusion overrides setup",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Skip",
            "decision_conditions": "news_window active — no new entry",
            "detector_output": "news_window_skip_valid",
            "evidence_label": "strong",
            "conviction_score": 0.9,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "N/A",
            "risk_control": "SL N/A | TP N/A | Entry N/A — news_window skip",
            "pattern_type": "level",
        })
        s3.update({"detector_name": "news_window_skip", "logic": "news_guard_blocked"})

    elif eid == "03_02":
        s2.update({
            "title": "Hanging man at high — WAIT confirmation bar",
            "setup": (
                "LEVELS: H1_RESISTANCE=2660, M15_PREVIOUS_HIGH=2659 | PATTERN=level | "
                "Hanging man at swing high (small body, long lower wick) | Topic rule: "
                "hanging man needs NEXT closed bar confirmation before short | WAIT."
            ),
            "decision": "Wait for confirmation",
            "invalidation": "Next M15 closes bull and accepts above high",
            "why": "Confirmation asymmetry",
            "evidence": "moderate",
        })
        s4.update({
            "trade_decision": "Wait for confirmation",
            "decision_conditions": "hanging man printed — missing next-bar confirm close",
            "detector_output": "hanging_man_wait_confirm",
            "evidence_label": "moderate",
            "conviction_score": 0.55,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "H1_RESISTANCE=2660",
            "risk_control": "SL N/A | TP N/A | Entry N/A — wait confirm bar",
        })

    elif eid == "05_02":
        s2.update({
            "title": "Order block / impulse origin — magnet NOT entry",
            "setup": (
                "LEVELS: IMPULSE_ORIGIN=2655, H1_SUPPORT=2654 | PATTERN=level | "
                "Prior impulse origin (OB alias) approached | core_skill: FVG/OB context "
                "not entry | Partial TP location only — SKIP open on magnet alone."
            ),
            "decision": "Skip",
            "invalidation": "Closed rejection or acceptance at mapped level with room",
            "why": "Impulse origin magnet not entry",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Skip",
            "decision_conditions": "OB/impulse_origin alone is not an entry reason",
            "detector_output": "impulse_origin_magnet_skip",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "IMPULSE_ORIGIN=2655",
            "risk_control": "SL N/A | TP N/A | Entry N/A — magnet not entry",
        })

    elif eid == "05_03":
        s2.update({
            "title": "Breaker first touch — WAIT closed rejection",
            "setup": (
                "LEVELS: ROLE_REVERSAL_ZONE=2660, H1_RESISTANCE=2660 | PATTERN=level | "
                "Breaker/role-reversal zone first touch | Topic: SKIP first touch; "
                "require closed rejection before short | WAIT."
            ),
            "decision": "Wait for confirmation",
            "invalidation": "M15 closes below zone with rejection OR accepts through",
            "why": "Breaker needs closed rejection",
            "evidence": "moderate",
        })
        s4.update({
            "trade_decision": "Wait for confirmation",
            "decision_conditions": "breaker first touch — missing closed rejection",
            "detector_output": "breaker_wait_rejection",
            "evidence_label": "moderate",
            "conviction_score": 0.6,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "ROLE_REVERSAL_ZONE=2660",
            "risk_control": "SL N/A | TP N/A | Entry N/A — wait closed rejection",
        })

    elif eid == "05_10":
        s2.update({
            "title": "FVG touch — context NOT entry (core_skill)",
            "setup": (
                "LEVELS: THIN_BAND=2652-2654, H4_BULL=active | PATTERN=level | "
                "Price touches unfilled thin_band/FVG | core_skill: unfilled FVG is "
                "context not entry | Do not open because of mitigation touch | SKIP."
            ),
            "decision": "Skip",
            "invalidation": "Closed rejection/acceptance at scored HTF level with room",
            "why": "FVG context not entry",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Skip",
            "decision_conditions": "FVG/thin_band touch alone — no entry",
            "detector_output": "fvg_context_not_entry_skip",
            "evidence_label": "strong",
            "conviction_score": 0.88,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "THIN_BAND=2652-2654",
            "risk_control": "SL N/A | TP N/A | Entry N/A — FVG not entry",
        })

    elif eid == "06_02":
        s2.update({
            "title": "Thin band (3-bar non-overlap) — project NOT enter",
            "setup": (
                "LEVELS: THIN_BAND_MID=2655, H4_BULL=active | PATTERN=level | "
                "M15 three-bar non-overlap thin_band (NOT 'range <50 pips') | "
                "Brooks measuring logic: use as TARGET projection, not bid-in-band entry | SKIP open."
            ),
            "decision": "Skip",
            "invalidation": "With-trend pullback setup at H1 level separate from band",
            "why": "Thin band projection not entry",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Skip",
            "decision_conditions": "thin_band is location/target context — not entry",
            "detector_output": "thin_band_project_not_entry",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "THIN_BAND_MID=2655",
            "risk_control": "SL N/A | TP N/A | Entry N/A — project only",
        })

    elif eid == "06_05":
        s2.update({
            "title": "Measuring gap — project target, do not buy gap",
            "setup": (
                "LEVELS: MEASURING_MID=2660, LEG_START=2650 | PATTERN=level | "
                "Measuring/thin mid-leg band | Target = projection 2× mid from leg start | "
                "Do NOT long because of gap | WAIT for pullback entry elsewhere."
            ),
            "decision": "Wait for confirmation",
            "invalidation": "Band fills against trend with acceptance",
            "why": "Measuring gap projection",
            "evidence": "moderate",
        })
        s4.update({
            "trade_decision": "Wait for confirmation",
            "decision_conditions": "measuring gap sets target — wait pullback trigger",
            "detector_output": "measuring_gap_project_wait",
            "evidence_label": "moderate",
            "conviction_score": 0.7,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "MEASURING_MID=2660, TARGET=2670",
            "risk_control": "SL N/A | TP N/A | Entry N/A — project target 2670",
        })

    elif eid == "08_02":
        s2.update({
            "title": "Barbwire mid-range — SKIP (overlap + doji, not hammers)",
            "setup": (
                "LEVELS: H4_RANGE_MID=2656, M15_MA=2655 | PATTERN=level | "
                "Barbwire = overlapping M15 bodies + dojis enclosing mid bars near MA "
                "(NOT consecutive hammers) | Mid-range — disable stop entries | SKIP."
            ),
            "decision": "Skip",
            "invalidation": "Clean edge approach with room ≥2R",
            "why": "Barbwire geometry mid-range veto",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Skip",
            "decision_conditions": "barbwire mid-range — no stop entry",
            "detector_output": "barbwire_mid_skip",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "entry_price": 0.0, "sl_price": 0.0, "tp_price": 0.0,
            "sl_usd": 0.0, "tp_usd": 0.0, "key_levels": "H4_RANGE_MID=2656",
            "risk_control": "SL N/A | TP N/A | Entry N/A — barbwire skip",
        })

    elif eid == "09_02":
        s2.update({
            "title": "Failure test — beyond level ≤3 bars then close inside",
            "setup": (
                "LEVELS: M15_SWING_HIGH=2662, H1_RESISTANCE=2663 | PATTERN=fakeout | "
                "Grimes failure test: price spends ≤2–3 bars BEYOND level then CLOSES "
                "back INSIDE with momentum (not 'fails to reach') | Short fade."
            ),
            "decision": "Short reversal",
            "invalidation": "Second probe accepts with 2 closes outside",
            "why": "Failure test close-inside",
            "evidence": "strong",
        })
        s4.update({
            "trade_decision": "Short reversal",
            "decision_conditions": "≤3 bars outside then close inside — failure test short",
            "detector_output": "failure_test_close_inside_short",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "entry_price": 2661.0, "sl_price": 2664.0, "tp_price": 2654.0,
            "sl_usd": 3.0, "tp_usd": 7.0,
            "key_levels": "M15_SWING_HIGH=2662, H1_RESISTANCE=2663",
            "risk_control": "SL $3.0 at 2664.0 | TP $7.0 at 2654.0 | Entry 2661.0",
            "pattern_type": "fakeout",
        })

    elif eid == "09_37":
        # Keep long but remove "Asia bias" direction claim — acceptance is the reason
        s2["setup"] = (
            "LEVELS: ASIA_SESSION_HIGH=4162, H1_SUPPORT=4156, H4_DEVELOPING_BULL | "
            "Session nest | Asia closed +$5 | Pre-London juke -$6 | London: H1 bull engulf "
            "recovers juke with M15/M5 acceptance | Session = vol/juke context NOT direction "
            "carry | Long because of closed acceptance, not Asia bias. TP $8."
        )
        s2["why"] = "Session juke then acceptance (not Asia direction carry)"
        s4["decision_conditions"] = (
            "London acceptance after juke — session bias is context not direction command"
        )


def ex(
    eid, topic, title, setup, decision, invalidation, why, evidence, bucket,
    detector_name, logic, detector_output, trade_decision, conditions, conviction,
    key_levels, entry, sl, tp, sl_usd, tp_usd, pattern_type="level",
):
    levels_line = f"LEVELS: {key_levels} | "
    risk = f"SL ${sl_usd} at {sl} | TP ${tp_usd} at {tp} | Entry {entry}"
    s2 = {
        "example_id": eid, "topic": topic, "title": title,
        "setup": levels_line + f"PATTERN={pattern_type} | " + setup,
        "decision": decision, "invalidation": invalidation, "why": why,
        "evidence": evidence, "bucket": bucket,
    }
    s3 = {
        "example_id": eid, "detector_type": "heuristic", "detector_name": detector_name,
        "input_signals": ["price", "volume", "time", "bars", "levels"],
        "logic": logic, "thresholds": {"tp_usd": [5, 12], "sl_usd": [3, 4]},
        "output": "enum(valid, invalid)",
    }
    s4 = {
        "example_id": eid, "detector_output": detector_output,
        "trade_decision": trade_decision, "decision_conditions": conditions,
        "evidence_label": evidence, "conviction_score": conviction,
        "risk_control": risk, "key_levels": key_levels,
        "entry_price": entry, "sl_price": sl, "tp_price": tp,
        "sl_usd": sl_usd, "tp_usd": tp_usd, "pattern_type": pattern_type,
    }
    return s2, s3, s4


NEW_PRINCIPLES = [
    {
        "principle_id": "P051",
        "topic": "09_reversal_trading",
        "principle_name": "Forbid-List Before Any Reverse Entry",
        "core_concept": "Before a counter-trend or fade entry, pass the forbid list: unbroken HTF trendline, parabolic stretch, mid-range location, no room to ≥1.5R target, wrong session (pre-London/NY/news), missing closed rejection. Any fail → skip/wait.",
        "foundational_rule": "Never open reverse because a candle looks good. Gate on forbid-list first, then MTR/failure-test/second-entry.",
        "why_matters": "Human traders skip the forbid list under emotion; the model must hard-gate.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["reversal_forbid_list", "parabolic_skip", "midrange_skip"],
    },
    {
        "principle_id": "P052",
        "topic": "08_range_trading",
        "principle_name": "Sell/Exit Timing — Structure Not Hope",
        "core_concept": "Exits are structural: mid-box or opposite edge for fades; measured-move then switch playbook; counter-trend must pay in 1–3 bars or cut; trail under last HL/LH — never early BE in tight trends; plan type scalp/runner immutable.",
        "foundational_rule": "Every open example states exit location. Fade TP = mid or opposite edge, never 'hold for breakout'.",
        "why_matters": "Model was entry-strong and exit-weak; sell timing failures match this gap.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["structural_exit", "ct_payoff_window", "mm_playbook_switch"],
    },
    {
        "principle_id": "P053",
        "topic": "01_market",
        "principle_name": "Session = Permission + Volatility, Never Direction Command",
        "core_concept": "Asia→London teaches expansion volatility and juke risk, not 'Asia bull = long'. Classify open type (Drive/Test-Drive) before Judas narrative. off_session and news_window force skip regardless of setup beauty.",
        "foundational_rule": "Stamp session + trade_permitted before decision. No Asia/London direction carryover claim.",
        "why_matters": "Directional session seeds recreate human bias the curriculum must kill.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["session_permission", "open_type_classify", "asia_vol_not_direction"],
    },
]

NEW = [
    # --- Forbid list ---
    ex("09_101", "09_reversal_trading", "Forbid — unbroken H4 TL, SKIP short",
       "H4 bull TL intact | M15 bear pin at high looks shortable | Forbid: TL unbroken + always-in long | SKIP reverse.",
       "Skip", "H4 TL breaks with acceptance past MA", "Forbid list TL", "strong", "A",
       "reversal_forbid_list", "htf_tl_unbroken", "forbid_tl_skip",
       "Skip", "Unbroken H4 TL — reverse forbidden", 0.88,
       "H4_TRENDLINE=intact, H1_RESISTANCE=2662, M15_PIN=2661", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("09_102", "09_reversal_trading", "Forbid — parabolic stretch, SKIP both",
       "H1 parabolic +$28 in 3 bars into D1_R1 | Perfect hanging man | Forbid: parabolic | SKIP short AND no with-trend add.",
       "Skip", "Climax cools + new structure", "Forbid parabolic", "strong", "A",
       "parabolic_skip", "parabolic_stretch", "forbid_parabolic_skip",
       "Skip", "Parabolic stretch — no CT and no add", 0.9,
       "D1_PIVOT_R1=2675, H1_PARABOLIC=true", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("09_103", "09_reversal_trading", "Forbid — mid-range no edge, SKIP",
       "H4 box 2648–2665 | Price 2656 mid-third | M5 reverse signal | Forbid: mid-range | SKIP.",
       "Skip", "Price reaches outer third with rejection", "Forbid midrange", "strong", "A",
       "midrange_skip", "mid_third", "forbid_mid_skip",
       "Skip", "Mid-range reverse signal — forbidden", 0.87,
       "H4_RANGE_MID=2656, H4_RANGE_HIGH=2665, H4_RANGE_LOW=2648", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    # --- Sell / exit timing ---
    ex("08_37", "08_range_trading", "Fade SHORT — TP mid-box then FLAT (exit doctrine)",
       "H4 range high fakeout close inside | Short at 2663 | EXIT doctrine: TP at mid 2656 — do NOT hold for breakdown. Scalp plan immutable.",
       "Short scalp", "H4 accepts above 2665", "Structural mid-box exit", "strong", "A",
       "structural_exit", "fade AND tp_mid_box", "fade_tp_mid_short",
       "Short scalp", "Range fade short — exit at mid-box not hope for breakout", 0.86,
       "H4_RANGE_HIGH=2665, H4_RANGE_MID=2656, ENTRY=2663", 2663.0, 2666.0, 2656.0, 3.0, 7.0, "fakeout"),
    ex("08_38", "08_range_trading", "Fade LONG — TP opposite edge then FLAT",
       "H4 low sweep close inside | Long 2650 | EXIT: opposite edge 2662 or mid first | Never convert fade to 'trend long' without acceptance break.",
       "Long scalp", "H4 below 2648", "Structural opposite-edge exit", "strong", "A",
       "structural_exit", "fade AND tp_opposite_edge", "fade_tp_edge_long",
       "Long scalp", "Range fade long — exit at mid/opposite edge", 0.86,
       "H4_RANGE_LOW=2648, H4_RANGE_MID=2656, H4_RANGE_HIGH=2665", 2650.0, 2647.0, 2656.0, 3.0, 6.0, "fakeout"),
    ex("07_33", "07_trend_trading", "Measured move hit — FLATTEN / switch range (exit)",
       "Was long from H4 BP 2648 | Price reaches measured move 2665 | EXIT doctrine: flatten at MM and switch to range playbook — do NOT keep trailing as if trend continues. Management SKIP new adds.",
       "Skip", "N/A — exit management", "MM playbook switch", "strong", "A",
       "mm_playbook_switch", "mm_reached AND flatten", "mm_exit_switch",
       "Skip", "At measured move — flatten and switch range, no hope extension", 0.88,
       "H4_BREAK=2648, MEASURED_MOVE=2665, POSITION=long", 0.0, 0.0, 0.0, 0.0, 0.0, "breakout"),
    ex("09_104", "09_reversal_trading", "CT short — no payoff in 3 bars → CUT",
       "Opened short at failure test 2662 | 3 M15 bars: no progress toward mid, overlapping | EXIT: cut — CT must pay in 1–3 bars or exit. Do not hope.",
       "Skip", "N/A management example", "CT payoff window", "strong", "A",
       "ct_payoff_window", "ct_open AND no_payoff_3bars", "ct_cut_no_payoff",
       "Skip", "Management: CT short unpaid in 3 bars — cut (discipline)", 0.88,
       "ENTRY=2662, M15_BARS_SINCE=3, MID=2655", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("09_105", "09_reversal_trading", "Sell timing — failure test SHORT with structural TP",
       "M15 sweeps H1_RESISTANCE 2660 (+$2), closes 2658 inside | M5 bear | Short NOW | TP mid-range 2652 | SL 2663 | Immediate sell after close-inside (not wick chase).",
       "Short reversal", "M15 accepts above 2660", "Sell timing close-inside", "strong", "A",
       "sell_timing_close_inside", "sweep AND close_inside AND m5_confirm", "sell_timing_short_valid",
       "Short reversal", "Sell on closed failure test — TP structure mid", 0.89,
       "H1_RESISTANCE=2660, M15_CLOSE=2658, H4_RANGE_MID=2652", 2658.0, 2661.0, 2652.0, 3.0, 6.0, "fakeout"),
    ex("09_106", "09_reversal_trading", "Sell timing BAD — wick only, WAIT",
       "H1_RESISTANCE 2660 | M5 wick 2662, M5 CLOSE 2659 still below | Tempting short on wick | WAIT — wick ≠ rejection complete until close confirm on entry TF.",
       "Wait for confirmation", "M15 closes below 2658 with body", "Wick not enough to sell", "strong", "A",
       "wick_vs_close_sell", "wick_only AND no_m15_confirm", "sell_wait_wick",
       "Wait for confirmation", "Do not sell the wick — wait closed rejection", 0.86,
       "H1_RESISTANCE=2660, M5_WICK=2662, M5_CLOSE=2659", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    # --- Acceptance vs wick ---
    ex("04_50", "04_timeframe_relations", "Same probe — FAKEOUT short (close inside)",
       "Asia high 4162 | M15 high 4164, CLOSE 4160 INSIDE | Acceptance clock: close inside → FAKEOUT fade short | Twin of 04_51.",
       "Short reversal", "M15 accepts above 4162", "Acceptance discriminator fakeout", "strong", "A",
       "acceptance_vs_penetration", "breach AND close_inside", "same_probe_fakeout_short",
       "Short reversal", "Identical probe closes inside — fakeout short", 0.9,
       "ASIA_SESSION_HIGH=4162, M15_HIGH=4164, M15_CLOSE=4160", 4160.0, 4163.0, 4153.0, 3.0, 7.0, "fakeout"),
    ex("04_51", "04_timeframe_relations", "Same probe — BREAKOUT long (close outside)",
       "Asia high 4162 | M15 high 4164, CLOSE 4165 OUTSIDE | 2nd M15 close 4166 | Same first probe as 04_50 but acceptance → BREAKOUT long.",
       "Long breakout", "Closes back inside Asia range", "Acceptance discriminator breakout", "strong", "A",
       "acceptance_vs_penetration", "close_outside AND follow_through", "same_probe_breakout_long",
       "Long breakout", "Identical probe accepts outside — breakout long", 0.9,
       "ASIA_SESSION_HIGH=4162, M15_CLOSE=4165, M15_FT=4166", 4165.0, 4162.0, 4173.0, 3.0, 8.0, "breakout"),
    ex("04_52", "04_timeframe_relations", "Wick beyond H4 level — NOT broken WAIT",
       "H4_PREVIOUS_HIGH=2665 | H1 wick 2667, H1 CLOSE 2663 inside | Level NOT broken | WAIT acceptance or clean rejection body.",
       "Wait for confirmation", "H1 closes above 2665 or M15 failure-test short triggers", "Wick≠break", "strong", "A",
       "wick_vs_close_break", "wick_beyond AND close_inside", "h4_wick_wait",
       "Wait for confirmation", "H4 level wick only — wait close decision", 0.87,
       "H4_PREVIOUS_HIGH=2665, H1_WICK=2667, H1_CLOSE=2663", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    # --- Session vol not direction ---
    ex("01_25", "01_market", "Asia bull — London FAIL continue at H4 resist SKIP long",
       "Asia +$8 bull | London approaches H4_PREVIOUS_HIGH 2665 | No acceptance | Distillation: Asia positive ≠ must continue | SKIP long; optional fade only after close-inside fakeout.",
       "Skip", "H4 accepts above 2665 with 2 closes", "Asia fail continuation", "strong", "A",
       "asia_vol_not_direction", "asia_bull AND h4_resist AND no_accept", "asia_fail_continue_skip",
       "Skip", "Asia bull but London into H4 wall — no direction carry", 0.88,
       "ASIA_BIAS=bull, H4_PREVIOUS_HIGH=2665, LONDON_OPEN=2660", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("01_26", "01_market", "Open-Drive — do NOT call Judas fade",
       "London open: M15 Open-Drive holds extreme above Asia mid with initiative | Class=Drive | Forbid false-move/Judas fade | With-drive or WAIT pullback — not fade.",
       "Wait for confirmation", "Drive fails back into Asia range", "Open-Drive classify", "strong", "A",
       "open_type_classify", "open_drive AND hold_extreme", "open_drive_no_fade",
       "Wait for confirmation", "Open-Drive — no Judas fade narrative", 0.84,
       "ASIA_MID=4158, LONDON_DRIVE_HIGH=4164, OPEN_TYPE=drive", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("01_27", "01_market", "Pre-London 07–08 — SKIP new entries (off_session)",
       "Clock 07:30 UTC pre-London | Beautiful M5 pin at support | Session rules: no-new-entry | SKIP off_session.",
       "Skip", "London session open + fresh closed response", "Off session skip", "strong", "A",
       "session_permission", "pre_london AND no_new_entry", "off_session_skip",
       "Skip", "Pre-London — off_session skip despite pretty pin", 0.92,
       "SESSION=pre_london, TRADE_PERMITTED=false, H1_SUPPORT=2650", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("01_28", "01_market", "Narrow Asia — two-sided breakout PLAN not direction",
       "Asia range $12 compressed | Expect London expansion volatility BOTH sides | Arm two-sided wait — do NOT pre-commit long because Asia was 'quiet bullish'.",
       "Wait for confirmation", "M5 acceptance outside Asia high OR low", "Asia vol prior two-sided", "strong", "A",
       "asia_vol_not_direction", "narrow_asia AND two_sided_plan", "asia_two_sided_wait",
       "Wait for confirmation", "Narrow Asia — wait acceptance either side", 0.85,
       "ASIA_HIGH=2660, ASIA_LOW=2648, ASIA_WIDTH=12", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    # --- More sell discipline ---
    ex("09_107", "09_reversal_trading", "Anti preferred — WAIT first pullback after CHOCH",
       "H4 bear broke | Change of character printed | Price still at extreme | Topic: prefer Anti (first pullback) over chasing extreme | WAIT pullback short.",
       "Wait for confirmation", "Pullback into broken level then M15 reject", "Anti entry wait", "moderate", "A",
       "anti_entry_wait", "choch AND at_extreme", "anti_wait_pullback",
       "Wait for confirmation", "After CHOCH wait Anti pullback — don't chase extreme short", 0.8,
       "H4_BREAK=2655, CHOCH=true, EXTREME=2652", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("09_108", "09_reversal_trading", "Failed-failure — EXIT short, do not re-fade",
       "Was short from failed BO | Price re-accepts above break with 2 closes | Failed-failure | EXIT short; may rejoin long BP — never re-fade same level immediately.",
       "Skip", "N/A management", "Failed-failure management", "strong", "A",
       "failed_failure_mgmt", "short_open AND reaccept", "failed_failure_exit",
       "Skip", "Management: failed-failure — exit CT, do not re-fade", 0.88,
       "BREAK_LEVEL=2660, REACCEPT=2662", 0.0, 0.0, 0.0, 0.0, 0.0, "breakout"),
    ex("02_37", "02_market_structure", "Decorative level score<2 — SKIP",
       "M5 line touched twice, not HTF pivot, no session extreme, no excess | level_score<2 | Grimes random-levels | SKIP.",
       "Skip", "Level earns score≥2 from independent sources", "Level score gate", "strong", "A",
       "level_score_gate", "level_score<2", "decorative_level_skip",
       "Skip", "Decorative unscored level — no trade", 0.9,
       "M5_LINE=2657, LEVEL_SCORE=1, H4_PIVOT=none", 0.0, 0.0, 0.0, 0.0, 0.0, "level"),
    ex("07_34", "07_trend_trading", "With-trend SHORT pullback — sell timing at H1 MA",
       "D1/H4 bear trend day | M15 rally +$8 to H1_MA 2660 | M5 bear confirm | With-trend short (not reverse) | TP next M15 support 2652 | Sell the pullback on closed reject.",
       "Short continuation", "H1_MA breaks up with acceptance", "Trend-day sell pullback", "strong", "A",
       "trend_pullback_sell", "htf_bear AND m15_rally_to_ma AND m5_reject", "trend_sell_pullback_valid",
       "Short continuation", "Sell with-trend pullback at H1 MA — closed M5 reject", 0.88,
       "D1_TREND=bear, H1_MA=2660, M15_HIGH=2661, M5_CLOSE=2659", 2659.0, 2662.0, 2652.0, 3.0, 7.0, "level"),
]


def main() -> None:
    s1 = load("stage_01_principle_foundation.jsonl")
    s2 = load("stage_02_structured_data.jsonl")
    s3 = load("stage_03_detector_definitions.jsonl")
    s4 = load("stage_04_decision_contract.jsonl")

    s2m = {r["example_id"]: r for r in s2}
    s3m = {r["example_id"]: r for r in s3}
    s4m = {r["example_id"]: r for r in s4}

    poison = {"01_10", "03_02", "05_02", "05_03", "05_10", "06_02", "06_05", "08_02", "09_02", "09_37"}
    for eid in poison:
        rewrite_poison(s2m[eid], s3m[eid], s4m[eid])

    # Principles
    existing_p = {p["principle_id"] for p in s1}
    for p in NEW_PRINCIPLES:
        if p["principle_id"] not in existing_p:
            s1.append(p)

    new_ids = {e[0]["example_id"] for e in NEW}
    # Drop any prior copies of new ids
    for eid in list(s2m):
        if eid in new_ids:
            del s2m[eid]
            del s3m[eid]
            del s4m[eid]

    for e in NEW:
        s2m[e[0]["example_id"]] = e[0]
        s3m[e[1]["example_id"]] = e[1]
        s4m[e[2]["example_id"]] = e[2]

    # Enrich all s4 with action/direction/confidence
    for eid, row in s4m.items():
        s4m[eid] = enrich_s4(row)

    holdout = set(HOLDOUT_IDS)
    missing = [i for i in HOLDOUT_IDS if i not in s2m]
    if missing:
        raise SystemExit(f"Holdout IDs missing: {missing}")

    train_ids = [i for i in s2m if i not in holdout]
    # Stable-ish: sort train by original topic prefix then id
    train_ids.sort()
    ordered = train_ids + HOLDOUT_IDS

    s2_out = [s2m[i] for i in ordered]
    s3_out = [s3m[i] for i in ordered]
    s4_out = [s4m[i] for i in ordered]

    save("stage_01_principle_foundation.jsonl", s1)
    save("stage_02_structured_data.jsonl", s2_out)
    save("stage_03_detector_definitions.jsonl", s3_out)
    save("stage_04_decision_contract.jsonl", s4_out)

    print(f"Poison rewritten: {len(poison)}")
    print(f"New examples: {len(NEW)}")
    print(f"Principles: {len(s1)}")
    print(f"Total: {len(s2_out)} | Train: {len(train_ids)} | Holdout: {len(HOLDOUT_IDS)}")
    print(f"Holdout IDs: {HOLDOUT_IDS}")
    print(f"Config hint: training_lines_end={len(train_ids)} test_end={len(s2_out)}")


if __name__ == "__main__":
    main()
