#!/usr/bin/env python3
"""
v7 — Fib-as-supplied-H4-location + M1 EMA 3/14/31 timing only.

Model consumes named levels the live stack would emit; never invents Fib or
trades all-TF EMA relationships. Preserves skill holdout at end.
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
        row["action"] = "open"
        row["direction"] = row.get("direction") or ("sell" if "short" in td else "buy")
        row["confidence"] = int(row.get("confidence") or 70)
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
    row.setdefault("missing_fact", None)
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
        "input_signals": ["price", "levels", "h4_fib", "m1_ema", "session"],
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


NEW_PRINCIPLES = [
    {
        "principle_id": "P057",
        "topic": "04_timeframe_relations",
        "principle_name": "H4 Fib — Consume Supplied Location Only",
        "core_concept": "H4 Fibonacci 38.2/50/61.8 are deterministic prices from completed H4 swing high/low supplied by the stack. Model never invents anchors or recalculates. At a supplied fib zone, judge auction_state; not every fib touch reverses.",
        "foundational_rule": "If H4_FIB_* IDs are absent from key_levels, do not invent them. Fib is location, never direction.",
        "why_matters": "Live planner emits named fib IDs; training must match consume-not-compute.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["h4_fib_consume", "fib_location_auction"],
    },
    {
        "principle_id": "P058",
        "topic": "09_reversal_trading",
        "principle_name": "M1 EMA 3/14/31 — Timing Only at Mapped Level",
        "core_concept": "EMA 3/14/31 on M1 is reclaim timing context at an already mapped level. Never trade EMA crosses mid-range or dump all-TF EMA relationships. Periods are 3/14/31 only (not 9).",
        "foundational_rule": "Pretty EMA stack without a scored level = skip/wait. Chase after expand away from cluster = veto.",
        "why_matters": "core_skill entry timing; all-TF EMA bloat dilutes level-first discipline.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["m1_ema_reclaim", "ema_timing_only"],
    },
]

NEW = [
    # ========== H4 FIB SUPPLIED LOCATION ==========
    entry_ex(
        "04_40", "04_timeframe_relations", "H4 FIB 618 buy — supplied location + M15 reject",
        "Stack supplied completed H4 swing 2640-2680 | Price at H4_FIB_618 | London | M15 closed rejection with lower wick hold | Do NOT recalculate fib | Open long scalp toward H4_FIB_50.",
        "Long scalp", "M15 closes below 2654", "Consume H4 fib 618", "strong", "A",
        "h4_fib_consume", "supplied_fib618 AND m15_reject AND room", "h4_fib618_buy_valid",
        "Long scalp", "Supplied H4 61.8 location with M15 rejection — open buy", 0.8,
        "H4_SWING_LOW=2640, H4_SWING_HIGH=2680, H4_FIB_382=2664.8, H4_FIB_50=2660, H4_FIB_618=2655.2, M15_CLOSE=2656",
        2656.0, 2653.0, 2660.0, 3.0, 4.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fib", action="open", direction="buy",
    ),
    entry_ex(
        "04_41", "04_timeframe_relations", "H4 FIB 618 sell — supplied location + M15 reject",
        "H4 swing 2640-2680 supplied | Price at H4_FIB_618 from above in bear pullback | M15 closed rejection upper wick | Open short scalp toward H4_FIB_50 | Fib is location only.",
        "Short scalp", "M15 closes above 2666", "Consume H4 fib 618 sell", "strong", "A",
        "h4_fib_consume", "supplied_fib618 AND m15_reject_bear AND room", "h4_fib618_sell_valid",
        "Short scalp", "Supplied H4 61.8 from above with M15 rejection — open sell", 0.8,
        "H4_SWING_LOW=2640, H4_SWING_HIGH=2680, H4_FIB_382=2655.2, H4_FIB_50=2660, H4_FIB_618=2664.8, M15_CLOSE=2664",
        2664.0, 2667.0, 2660.0, 3.0, 4.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fib", action="open", direction="sell",
    ),
    entry_ex(
        "04_42", "04_timeframe_relations", "H4 FIB 50 wait — unfinished response",
        "At supplied H4_FIB_50 | Auction transition | M15 wick into zone but bar still forming | Wait — never invent alternate fib anchors.",
        "Wait for confirmation", "M15 close reject below 2660 or accept above 2661", "Fib 50 unfinished", "strong", "A",
        "h4_fib_wait", "supplied_fib50 AND response_incomplete", "wait_h4_fib50",
        "Wait for confirmation", "Supplied H4 50 — missing closed M15 response", 0.55,
        "H4_SWING_LOW=2640, H4_SWING_HIGH=2680, H4_FIB_50=2660, M15_FORMING=2660.4",
        0, 0, 0, 0, 0,
        auction_state="transition", target_mode="starter_basket",
        missing_fact="M15 close rejecting at or below 2660 after probe of H4_FIB_50",
        pattern_type="fib", action="wait", direction="none",
    ),
    entry_ex(
        "04_43", "04_timeframe_relations", "H4 FIB 382 skip — compressed at fib",
        "Price touching supplied H4_FIB_382 | M15 range compressed <0.3 ATR | Low participation | Fib touch is not a trade | skip_reason_code=compressed.",
        "Skip", "Volatility expands with closed acceptance beyond Asia box", "Fib compressed skip", "strong", "A",
        "h4_fib_compressed", "supplied_fib AND compressed", "skip_fib_compressed",
        "Skip", "Supplied H4 38.2 but compressed — skip", 0.88,
        "H4_FIB_382=2664.8, SESSION=asia, M15_ATR_FRAC=0.22",
        0, 0, 0, 0, 0,
        auction_state="balance", skip_reason_code="compressed", target_mode="none",
        pattern_type="fib", action="skip", direction="none",
    ),
    entry_ex(
        "04_44", "04_timeframe_relations", "H4 FIB 618 skip — empty midrange no room",
        "At H4_FIB_618 | Nearest opposing scored level only $3 away | Cannot fit SL/TP | Structure location ok, geometry fails | skip fixed_profile or empty room.",
        "Skip", "Room opens to next H4 fib or H1 level", "Fib no room", "strong", "A",
        "h4_fib_no_room", "supplied_fib AND room_fail", "skip_fib_no_room",
        "Skip", "Supplied H4 61.8 but no room — skip", 0.85,
        "H4_FIB_618=2655.2, NEXT_RESISTANCE=2658, PROFILE=fixed_r_3_6",
        0, 0, 0, 0, 0,
        auction_state="rejection", skip_reason_code="fixed_profile_mismatch", target_mode="none",
        pattern_type="fib", action="skip", direction="none",
    ),
    entry_ex(
        "04_45", "04_timeframe_relations", "H4 FIB accept break — directional basket",
        "Bull H4 path | Price accepted through supplied H4_FIB_50 with M15 retest hold | auction_state=acceptance | target_mode=directional_basket toward H4_FIB_382 then swing high.",
        "Long breakout", "M15 closes back below 2659", "Fib acceptance basket", "strong", "A",
        "h4_fib_accept", "supplied_fib50 AND accept_retest AND h4_bull", "h4_fib50_basket_long",
        "Long breakout", "Supplied H4 50 accepted with retest — directional basket", 0.82,
        "H4_FIB_50=2660, H4_FIB_382=2664.8, H4_SWING_HIGH=2680, RETEST=2660.5",
        2661.0, 2658.0, 2665.0, 3.0, 4.0,
        auction_state="acceptance", target_mode="directional_basket",
        pattern_type="fib", action="open", direction="buy",
    ),
    entry_ex(
        "04_46", "04_timeframe_relations", "FORBID invent fib — no H4_FIB in levels",
        "Price near 2655 | Prompt key_levels has H1_SUPPORT only — no H4_FIB_* IDs | Do not invent 61.8 from memory | Wait or trade only the supplied H1 level response.",
        "Wait for confirmation", "Closed M15 response at supplied H1_SUPPORT 2650", "No invent fib", "strong", "A",
        "fib_no_invent", "fib_ids_absent AND near_round_number", "wait_no_invent_fib",
        "Wait for confirmation", "No H4_FIB IDs supplied — do not invent fib location", 0.7,
        "H1_SUPPORT=2650, PRICE=2655, H4_FIB_IDS=none",
        0, 0, 0, 0, 0,
        auction_state="unclear", target_mode="none",
        missing_fact="M15 closed response at supplied H1_SUPPORT 2650",
        pattern_type="fib", action="wait", direction="none",
    ),
    entry_ex(
        "04_47", "04_timeframe_relations", "H4 FIB confluence with pivot — open sell",
        "Supplied H4_FIB_618 clusters with H4_PIVOT_R1 in same zone | M15 second-test reject | Confluence raises confidence of location not of magic | Open short scalp.",
        "Short scalp", "M15 accepts above 2666", "Fib+pivot confluence", "strong", "A",
        "h4_fib_pivot_cluster", "fib618_near_pivot_r1 AND m15_reject", "h4_fib_pivot_sell",
        "Short scalp", "Supplied fib 61.8 + pivot R1 cluster with reject — sell", 0.84,
        "H4_FIB_618=2664.8, H4_PIVOT_R1=2665.1, M15_CLOSE=2663.5, NEXT_SUPPORT=2658",
        2663.5, 2666.5, 2658.0, 3.0, 5.5,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fib", action="open", direction="sell",
    ),
    entry_ex(
        "04_48", "04_timeframe_relations", "H4 FIB touch mid-leg — not every touch reverses",
        "Price tags H4_FIB_382 mid strong bull impulse | Single M5 wick | No closed rejection | HTF acceptance intact | Do NOT fade fib | Skip empty midrange / wait continuation pullback deeper.",
        "Skip", "Pullback reaches supplied H4_FIB_50/618 with closed response", "Fib mid-leg no fade", "strong", "A",
        "h4_fib_no_auto_reverse", "fib_touch AND impulse_intact AND no_closed_reject", "skip_fib_midleg",
        "Skip", "Not every fib touch reverses — mid-leg 38.2 skip fade", 0.86,
        "H4_FIB_382=2664.8, H4_BIAS=bull_impulse, M5_WICK_ONLY=true",
        0, 0, 0, 0, 0,
        auction_state="acceptance", skip_reason_code="empty_midrange", target_mode="none",
        pattern_type="fib", action="skip", direction="none",
    ),
    entry_ex(
        "04_49", "04_timeframe_relations", "Daily fib pivot zone — consume PP/R/S",
        "Stack supplied daily Fibonacci pivot PP and R1 from completed prior UTC day | Price at DAILY_FIB_R1 | Overlap session | M15 reject | Open short — never recalculate PP.",
        "Short scalp", "M15 closes above 2671", "Daily fib pivot consume", "strong", "A",
        "daily_fib_pivot_consume", "supplied_daily_r1 AND m15_reject", "daily_fib_r1_sell",
        "Short scalp", "Supplied daily fib R1 with reject — sell", 0.78,
        "DAILY_FIB_PP=2658, DAILY_FIB_R1=2668, DAILY_FIB_S1=2648, M15_CLOSE=2667",
        2667.0, 2670.0, 2662.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fib", action="open", direction="sell",
    ),

    # ========== M1 EMA 3/14/31 TIMING ONLY ==========
    entry_ex(
        "09_120", "09_reversal_trading", "M1 EMA reclaim buy at mapped H1 support",
        "Mapped H1_SUPPORT 2650 | Selling fails | Bullish M1 reclaims up through EMA3 then EMA14/31 cluster | Enter next M1 open | EMA timing not reason | Periods 3/14/31 only.",
        "Long scalp", "M1 closes back below EMA31", "M1 EMA3/14/31 buy", "strong", "A",
        "m1_ema_reclaim_buy", "mapped_support AND m1_bull_reclaim_ema31431", "m1_ema31431_buy",
        "Long scalp", "M1 EMA 3/14/31 reclaim up at support — buy timing", 0.81,
        "H1_SUPPORT=2650, EMA3=2651.2, EMA14=2651.8, EMA31=2652.4",
        2652.0, 2649.0, 2657.0, 3.0, 5.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "09_121", "09_reversal_trading", "M1 EMA reclaim sell at mapped H1 resistance",
        "Mapped H1_RESISTANCE 2660 | Buying fails | Bearish M1 reclaims down through EMA3/14/31 | Enter next M1 open | Invalidation above rejection extreme.",
        "Short scalp", "M1 closes back above EMA31", "M1 EMA3/14/31 sell", "strong", "A",
        "m1_ema_reclaim_sell", "mapped_resistance AND m1_bear_reclaim_ema31431", "m1_ema31431_sell",
        "Short scalp", "M1 EMA 3/14/31 reclaim down at resistance — sell timing", 0.81,
        "H1_RESISTANCE=2660, EMA3=2659.0, EMA14=2658.4, EMA31=2657.8",
        2658.5, 2661.5, 2653.0, 3.0, 5.5,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="sell",
    ),
    entry_ex(
        "09_122", "09_reversal_trading", "EMA pretty midrange — SKIP no mapped level",
        "M1 EMA3 crossed above EMA14/31 looking bullish | Price mid daily range | No scored H4/H1 level in reach | EMA is not a reason to trade | skip empty_midrange.",
        "Skip", "Price reaches supplied scored level with closed response", "EMA midrange veto", "strong", "A",
        "ema_timing_only", "ema_cross AND no_mapped_level", "skip_ema_midrange",
        "Skip", "Pretty M1 EMA stack midrange without level — skip", 0.9,
        "EMA3=2656, EMA14=2655.5, EMA31=2655, NEAREST_LEVEL_DIST_USD=11",
        0, 0, 0, 0, 0,
        auction_state="balance", skip_reason_code="empty_midrange", target_mode="none",
        pattern_type="skip", action="skip", direction="none",
    ),
    entry_ex(
        "09_123", "09_reversal_trading", "Chase veto — expanded away from M1 EMA cluster",
        "Valid reclaim signal was at EMA cluster 2655 at H1 support | Price already ran to 2663 into resistance | Never chase | WAIT retest of cluster or level.",
        "Wait for confirmation", "Retest near 2655 EMA cluster / H1 support with fresh close", "EMA chase veto", "strong", "A",
        "ema_chase_veto", "expanded_away_from_ema_cluster", "wait_ema_retest",
        "Wait for confirmation", "Chase veto — left M1 3/14/31 cluster into opposing level", 0.87,
        "H1_SUPPORT=2650, EMA_CLUSTER=2655, NOW=2663, H1_RESISTANCE=2662",
        0, 0, 0, 0, 0,
        auction_state="acceptance", target_mode="none",
        missing_fact="Retest back to M1 EMA 3/14/31 cluster near 2655 with fresh closed response",
        pattern_type="wait", action="wait", direction="none",
    ),
    entry_ex(
        "09_124", "09_reversal_trading", "M1 EMA + supplied H4 FIB 618 confluence buy",
        "Supplied H4_FIB_618=2655.2 | Mapped zone | M1 bull reclaim through EMA3/14/31 at the fib | Location=fib, timing=EMA | Open long scalp | Do not invent other fibs.",
        "Long scalp", "M1 accepts below 2653", "Fib location + EMA timing", "strong", "A",
        "fib_plus_m1_ema", "supplied_fib618 AND m1_ema_reclaim", "fib618_ema_buy",
        "Long scalp", "Supplied H4 61.8 location with M1 EMA 3/14/31 reclaim — buy", 0.84,
        "H4_FIB_618=2655.2, EMA3=2655.5, EMA14=2656.0, EMA31=2656.6, M5_OPPOSE=2660",
        2656.0, 2653.0, 2660.0, 3.0, 4.0,
        auction_state="rejection", target_mode="scalp",
        pattern_type="fib", action="open", direction="buy",
    ),
    entry_ex(
        "09_125", "09_reversal_trading", "FORBID all-TF EMA — ignore H4 EMA9 noise",
        "Prompt mistakenly rich with H4 EMA9/H1 EMA14 crosses while M1 at mapped resistance shows no reclaim | Trade only M1 3/14/31 at level | No reclaim -> WAIT | Do not use EMA9.",
        "Wait for confirmation", "M1 bear reclaim close through EMA3/14/31 at 2660", "All-TF EMA ignore", "strong", "A",
        "ema_mtf_ignore", "htf_ema_noise AND m1_no_reclaim", "wait_m1_only",
        "Wait for confirmation", "Ignore all-TF/EMA9 noise — wait M1 3/14/31 reclaim at level", 0.75,
        "H1_RESISTANCE=2660, EMA3=2659.8, EMA14=2659.5, EMA31=2659.2, H4_EMA9=2650_noise",
        0, 0, 0, 0, 0,
        auction_state="transition", target_mode="scalp",
        missing_fact="M1 close reclaiming down through EMA 3/14/31 at H1_RESISTANCE 2660",
        pattern_type="wait", action="wait", direction="none",
    ),
    entry_ex(
        "09_126", "09_reversal_trading", "M5 beyond EMA31 confirm only — not entry reason",
        "At H1 support | M1 already reclaimed EMA cluster | M5 closed above EMA31 confirms continuation filter | Entry reason remains level+M1 reclaim not M5 EMA | Open long.",
        "Long scalp", "M5 closes back below 2649", "M5 EMA31 filter", "strong", "A",
        "m5_ema31_filter", "m1_reclaim AND m5_close_above_ema31 AND level", "m5_filter_long",
        "Long scalp", "M5 beyond EMA31 confirms filter only — entry still level+M1", 0.79,
        "H1_SUPPORT=2650, EMA3=2651, EMA14=2651.5, EMA31=2652, M5_EMA31=2651.8, M5_CLOSE=2653",
        2652.5, 2649.0, 2658.0, 3.5, 5.5,
        auction_state="rejection", target_mode="scalp",
        pattern_type="level", action="open", direction="buy",
    ),
    entry_ex(
        "09_127", "09_reversal_trading", "M1 EMA unfinished — wait close through cluster",
        "At resistance | M1 trading through EMA3 but bar not closed back below EMA14/31 | Do not sell unfinished reclaim | WAIT missing_fact.",
        "Wait for confirmation", "M1 close below EMA31 after reject at 2660", "Unfinished EMA reclaim", "strong", "A",
        "m1_ema_unfinished", "m1_forming_through_ema AND not_closed", "wait_ema_close",
        "Wait for confirmation", "M1 still forming through EMA cluster — wait closed reclaim", 0.72,
        "H1_RESISTANCE=2660, EMA3=2659.5, EMA14=2659.0, EMA31=2658.5, M1_FORMING=true",
        0, 0, 0, 0, 0,
        auction_state="transition", target_mode="scalp",
        missing_fact="M1 close back below EMA31 after rejection at 2660",
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
        s4m[e[2]["example_id"]] = enrich(e[2])

    for eid, row in s4m.items():
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

    fib_n = sum(1 for e in NEW if e[0]["example_id"].startswith("04_"))
    ema_n = sum(1 for e in NEW if e[0]["example_id"].startswith("09_"))
    print(f"Added {len(NEW)} examples (h4_fib~={fib_n}, m1_ema~={ema_n})")
    print(f"Principles: {len(s1)}")
    print(f"Total: {len(ordered)} | Train: {len(train_ids)} | Holdout: {len(HOLDOUT_IDS)}")
    print(f"Config: training_lines_end={len(train_ids)} test_end={len(ordered)}")


if __name__ == "__main__":
    main()
