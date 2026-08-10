#!/usr/bin/env python3
"""
Append H1/H4 underlying-candle examples, small M15 gold pullbacks, and level-ID
trade management (SL/TP on every row).

Distilled from CANDLE_MOMENT_AND_SESSION_DISTILLATION.md + core_skill.md:
- Read order D1→H4→H1→M15→M5→M1; underlying bars inside parent
- XAU routine day = $60–$90 range; D1 trend shift ~1–2×/month
- Named level IDs (H4_PREVIOUS_HIGH, M15_PREVIOUS_LOW, D1_PIVOT_PP, …)
- Every trade row: Entry, zone SL/TP in gold price (M15≥$5/$5, H1≥$7/$10, H4≥$10/$20)
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"
TEST_IDS = {f"09_{i:02d}" for i in range(5, 15)}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def ex(
    eid, topic, title, setup, decision, invalidation, why, evidence, bucket,
    detector_name, logic, detector_output, trade_decision, conditions, conviction,
    key_levels: str, entry: float, sl: float, tp: float, sl_usd: float, tp_usd: float,
    det_out="enum(valid, invalid)",
):
    levels_line = f"LEVELS: {key_levels} | "
    risk = f"SL ${sl_usd} at {sl} | TP ${tp_usd} at {tp} | Entry {entry}"
    s2 = {
        "example_id": eid, "topic": topic, "title": title,
        "setup": levels_line + setup, "decision": decision,
        "invalidation": invalidation, "why": why, "evidence": evidence, "bucket": bucket,
    }
    s3 = {
        "example_id": eid, "detector_type": "heuristic", "detector_name": detector_name,
        "input_signals": ["price", "volume", "time", "bars", "levels"],
        "logic": logic, "thresholds": {"tp_usd": [5, 20], "sl_usd": [5, 10]}, "output": det_out,
    }
    s4 = {
        "example_id": eid, "detector_output": detector_output, "trade_decision": trade_decision,
        "decision_conditions": conditions, "evidence_label": evidence,
        "conviction_score": conviction, "risk_control": risk,
        "key_levels": key_levels, "entry_price": entry, "sl_price": sl, "tp_price": tp,
        "sl_usd": sl_usd, "tp_usd": tp_usd,
    }
    return s2, s3, s4


NEW_PRINCIPLES = [
    {
        "principle_id": "P045",
        "topic": "04_timeframe_relations",
        "principle_name": "H1/H4 Underlying Candle Path — Child Bars Inside Parent",
        "core_concept": "An H4 moment is built from 4 closed H1 bars; each H1 from 4 M15 bars. State the underlying sequence: e.g. H4(NY) bull developing | H1[-4,-3,-2,-1]: bull bear bear bull | M15 inside H1[-1]: bear bear bull bull. The path shows whether LTF fades or follows HTF.",
        "foundational_rule": "Never decide from one M5 bar alone. List closed child bars inside the active parent before entry. H4 last 30min = last 2 M15 bars — spike there may complete H4, not start new trend.",
        "why_matters": "Distillation framework requires HTF→LTF influence in every sample. Without underlying bar lists the model cannot learn nested rejection at levels.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["h1_inside_h4_path", "underlying_m15_in_h1", "h4_child_bar_sequence"],
    },
    {
        "principle_id": "P046",
        "topic": "01_market",
        "principle_name": "XAU Daily Rhythm — $60–$90 Routine, D1 Trend Rare",
        "core_concept": "Most XAUUSD sessions trade a $60–$90 daily range between mapped levels. True D1 trend shifts occur roughly 1–2× per month. Intraday edge = M15/H1 pullbacks ($6–$10) inside the daily range, not betting every day is a trend day.",
        "foundational_rule": "Tag day type: range_day (fade edges, $5–$9 TP) vs trend_day (with-trend pullbacks, TP to next HTF level). If price mid daily range with no level — skip. Major trend entries need D1/H4 alignment + acceptance.",
        "why_matters": "Training on large swing examples alone teaches wrong baseline; operator bread-and-butter is small M15 pullbacks inside the routine daily auction.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["xau_daily_range_rhythm", "m15_pullback_in_daily_range", "d1_trend_rarity_filter"],
    },
    {
        "principle_id": "P047",
        "topic": "02_market_structure",
        "principle_name": "Named Level IDs + Mandatory SL/TP on Every Decision",
        "core_concept": "Use dashboard level IDs: H4_PREVIOUS_HIGH, H1_SUPPORT, M15_PREVIOUS_LOW, D1_PIVOT_PP, ASIA_SESSION_HIGH. Every actionable decision states Entry plus zone-based Stop/Target in gold price (not account dollars): M15/M30 SL≥$5 TP≥$5; H1 SL≥$7 TP≥$10; H4/D1 SL≥$10 TP≥$20 on named S/R. Wait/Skip = SL/TP N/A.",
        "foundational_rule": "SL beyond named structure invalidation; TP at next opposing named level. Pad beyond the level to TF mins when nearer. Never invent levels.",
        "why_matters": "Model weakness is trade management; explicit SL/TP + level map in every training response teaches executable output, not narrative only.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["level_id_map", "sl_tp_contract", "zone_to_trigger_playbook"],
    },
]

NEW = [
    # --- H1/H4 underlying candle path (04) ---
    ex("04_28", "04_timeframe_relations", "H4 bull — 4 H1 underlying bars, M15 dip LONG",
       "Underlying nest | H4(NY) CLOSED bull HL 2645 | H1[-4,-3,-2,-1]: bull $6, bear $4, bear $5, bull $7 at H4_PREVIOUS_LOW zone | M15 inside H1[-1]: bear bear bull bull | M5 two-bar bull | With-trend pullback.",
       "Long continuation", "H4 HL 2645 breaks", "H1 path inside H4 bull", "strong", "A",
       "h1_inside_h4_path", "h4_bull AND h1_dip_sequence AND m15_bull_confirm", "h4_h1_underlying_long_valid",
       "Long continuation", "Four H1 bars inside H4 bull — M15 dip buy at H4 level", 0.86,
       "H4_PREVIOUS_LOW=2645, H1_SUPPORT=2646, M15_PREVIOUS_LOW=2647", 2648.0, 2645.0, 2656.0, 3.0, 8.0),
    ex("04_29", "04_timeframe_relations", "H4 bear — 4 H1 underlying bars, M15 rally SHORT",
       "Underlying nest | H4(NY) CLOSED bear LH 2662 | H1[-4,-3,-2,-1]: bear $7, bull $5, bull $6, bear $8 at H4_PREVIOUS_HIGH | M15 inside H1[-1]: bull bull bear bear | M5 bear engulf | Fade rally in H4 bear.",
       "Short continuation", "H4 LH 2662 breaks up", "H1 path inside H4 bear", "strong", "A",
       "h1_inside_h4_path", "h4_bear AND h1_rally_sequence AND m15_bear_confirm", "h4_h1_underlying_short_valid",
       "Short continuation", "Four H1 bars inside H4 bear — M15 rally fade at H4 level", 0.86,
       "H4_PREVIOUS_HIGH=2662, H1_RESISTANCE=2661, M15_PREVIOUS_HIGH=2660", 2659.0, 2662.0, 2651.0, 3.0, 8.0),
    ex("04_30", "04_timeframe_relations", "Developing H4 — H1[-1] builds from 4 M15 LONG",
       "Underlying nest | H4 50% elapsed developing bull | H1[-1] forming: M15[-4,-3,-2,-1] bull $4, bull $3, bear $2, bull $5 = H1 bull when closes | H4 at M30_MA | Long on H1 close break.",
       "Long scalp", "M15[-1] bear engulf breaks sequence", "M15 compose H1 bar", "moderate", "A",
       "underlying_m15_in_h1", "four_m15_bullish AND h4_developing_bull", "m15_compose_h1_long_valid",
       "Long scalp", "Four M15 bars compose developing H1 bull inside H4", 0.79,
       "H4_DEVELOPING_LOW=2648, M30_MA=2649, M15_CURRENT_OPEN=2650", 2651.0, 2648.0, 2657.0, 3.0, 6.0),
    ex("04_31", "04_timeframe_relations", "Developing H4 — H1[-1] builds from 4 M15 SHORT",
       "Underlying nest | H4 60% bear developing | H1[-1]: M15[-4,-3,-2,-1] bear bear bull bear = H1 bear forming | At H4_PREVIOUS_HIGH 2663 | Short H1 close.",
       "Short scalp", "M15 bull sequence breaks bear compose", "M15 compose H1 bar", "moderate", "A",
       "underlying_m15_in_h1", "four_m15_bearish AND h4_developing_bear", "m15_compose_h1_short_valid",
       "Short scalp", "Four M15 bars compose developing H1 bear at H4 resistance", 0.78,
       "H4_PREVIOUS_HIGH=2663, H1_RESISTANCE=2662, M15_PREVIOUS_HIGH=2661", 2660.0, 2663.0, 2653.0, 3.0, 7.0),
    ex("04_32", "04_timeframe_relations", "H4 range — H1 oscillation underlying, edge SHORT",
       "Underlying nest | H4 bracket 2648–2665 ($17 width) | H1[-3,-2,-1]: bull $8, bull $7, bear $6 into H4_PREVIOUS_HIGH | M15[-2,-1]: bull trap bear | Range edge fade not trend reversal.",
       "Short reversal", "H1 closes above 2665", "H1 push to H4 range high", "strong", "A",
       "h4_range_h1_underlying", "h4_range AND h1_into_high AND m15_reject", "h4_range_edge_short_valid",
       "Short reversal", "H1 underlying bars push to H4 range high — fade", 0.84,
       "H4_RANGE_HIGH=2665, H1_RESISTANCE=2664, M15_PREVIOUS_HIGH=2663", 2662.0, 2665.0, 2655.0, 3.0, 7.0),
    ex("04_33", "04_timeframe_relations", "H4 range — H1 oscillation underlying, edge LONG",
       "Underlying nest | H4 bracket 2648–2665 | H1[-3,-2,-1]: bear $7, bear $6, bull $8 at H4_PREVIOUS_LOW | M15 hammer + bull | Long range edge.",
       "Long reversal", "H1 closes below 2648", "H1 push to H4 range low", "strong", "A",
       "h4_range_h1_underlying", "h4_range AND h1_into_low AND m15_reject", "h4_range_edge_long_valid",
       "Long reversal", "H1 underlying bars push to H4 range low — long fade", 0.84,
       "H4_RANGE_LOW=2648, H1_SUPPORT=2649, M15_PREVIOUS_LOW=2650", 2651.0, 2648.0, 2659.0, 3.0, 8.0),
    ex("04_34", "04_timeframe_relations", "H4 last 30min — 2 M15 underlying spike fade SHORT",
       "Underlying nest | H4 85% | Last 30min = M15[-2,-1]: bull $9, bull $4 spike to D1_PIVOT_R1 2668 | M5 bear reversal | H1 wick only | Fade H4 completion spike.",
       "Short reversal", "H4 closes above 2668", "H4 end segment underlying M15", "strong", "A",
       "h4_last_30m_m15_path", "h4_late AND two_m15_bull_spike AND m5_reversal", "h4_endbar_short_valid",
       "Short reversal", "Last two M15 bars spike H4 end — fade at D1 pivot", 0.87,
       "D1_PIVOT_R1=2668, H4_DEVELOPING_HIGH=2667, M15_PREVIOUS_HIGH=2666", 2665.0, 2668.0, 2656.0, 3.0, 9.0),
    ex("04_35", "04_timeframe_relations", "H4 last 30min — 2 M15 underlying dip fade LONG",
       "Underlying nest | H4 80% | Last 30min M15[-2,-1]: bear $8, bear $5 to H4_PREVIOUS_LOW 2646 | M5 two-bar bull | Long H4 completion dip.",
       "Long reversal", "H4 closes below 2646", "H4 end segment underlying M15", "strong", "A",
       "h4_last_30m_m15_path", "h4_late AND two_m15_bear_dip AND m5_bull", "h4_endbar_long_valid",
       "Long reversal", "Last two M15 bars dip H4 end — long at support", 0.87,
       "H4_PREVIOUS_LOW=2646, D1_PIVOT_S1=2645, M15_PREVIOUS_LOW=2647", 2648.0, 2645.0, 2656.0, 3.0, 8.0),
    ex("04_36", "04_timeframe_relations", "H1 CLOSED reversal — full M15 path underneath SHORT",
       "Underlying nest | H4 bear bias | H1[-1] CLOSED: bear $10 at H1_RESISTANCE 2660 | Underlying M15[-4,-3,-2,-1]: bull $5, bull $4, bear $3, bear $6 | M5 bear trigger | H1 moment complete.",
       "Short reversal", "H1[-1] reclaimed above 2660", "Closed H1 + M15 path", "strong", "A",
       "closed_h1_m15_underlying", "h1_bear_close AND m15_bull_trap_bear", "closed_h1_underlying_short_valid",
       "Short reversal", "Closed H1 bear at 2660 with underlying M15 bull trap", 0.88,
       "H1_RESISTANCE=2660, H4_PREVIOUS_HIGH=2662, M15_PREVIOUS_HIGH=2659", 2658.0, 2661.0, 2651.0, 3.0, 7.0),
    ex("04_37", "04_timeframe_relations", "H1 CLOSED reversal — full M15 path underneath LONG",
       "Underlying nest | H4 bull bias | H1[-1] CLOSED: bull $9 at H1_SUPPORT 2648 | M15[-4,-3,-2,-1]: bear $6, bear $5, bull $4, bull $7 | M5 long trigger | H1 moment complete.",
       "Long reversal", "H1 closes below 2648", "Closed H1 + M15 path", "strong", "A",
       "closed_h1_m15_underlying", "h1_bull_close AND m15_bear_trap_bull", "closed_h1_underlying_long_valid",
       "Long reversal", "Closed H1 bull at 2648 with underlying M15 bear trap", 0.88,
       "H1_SUPPORT=2648, H4_PREVIOUS_LOW=2646, M15_PREVIOUS_LOW=2649", 2650.0, 2647.0, 2657.0, 3.0, 7.0),
    # --- Level ID knowledge (02) ---
    ex("02_19", "02_market_structure", "H4 zone double-check — rejection SHORT at band",
       "Level nest | H4_REFERENCE_BAND 2658–2663 (4–5 unit zone) | Price probes 2662, M15 close 2659 INSIDE band | H1 upper wick | M5 bear | Double-check = touch + close inside + rejection.",
       "Short reversal", "M15 accepts above 2663", "Level double-check reject", "strong", "A",
       "level_double_check", "zone_touch AND close_inside AND rejection", "h4_zone_reject_short_valid",
       "Short reversal", "H4 band rejection — close back inside after probe", 0.85,
       "H4_REFERENCE_BAND=2658-2663, H1_RESISTANCE=2660, M15_PREVIOUS_HIGH=2661", 2659.0, 2662.0, 2652.0, 3.0, 7.0),
    ex("02_20", "02_market_structure", "H4 zone double-check — acceptance LONG breakout",
       "Level nest | H4_REFERENCE_BAND 2658–2663 | M15[-1]: close 2664 OUTSIDE band | M15[-2]: close 2663 outside | 2 closes = acceptance | M5 retest hold | Long break.",
       "Long breakout", "Close back inside band", "Level double-check accept", "strong", "A",
       "level_double_check", "two_m15_closes_outside AND retest_hold", "h4_zone_accept_long_valid",
       "Long breakout", "H4 band acceptance — two M15 closes outside", 0.84,
       "H4_REFERENCE_BAND=2658-2663, H1_RESISTANCE=2660, M15_BREAK_LEVEL=2663", 2664.0, 2661.0, 2672.0, 3.0, 8.0),
    ex("02_21", "02_market_structure", "D1 pivot PP cluster — fade SHORT",
       "Level nest | D1_PIVOT_PP=2650 cluster with H1_MA | M15 spike +$8 to 2652, close 2649 below PP | M5 bear | Pivot = location not command.",
       "Short reversal", "M15 holds above 2652", "D1 pivot rejection", "moderate", "A",
       "d1_pivot_location", "pivot_probe AND close_below_pp", "d1_pivot_fade_short_valid",
       "Short reversal", "D1 pivot PP probe rejected — short fade", 0.81,
       "D1_PIVOT_PP=2650, H1_MA=2651, M15_PREVIOUS_HIGH=2652", 2649.0, 2652.0, 2642.0, 3.0, 7.0),
    ex("02_22", "02_market_structure", "D1 pivot PP cluster — bounce LONG",
       "Level nest | D1_PIVOT_PP=2650 | M15 dip -$7 to 2648, close 2651 above PP | M5 bull pin | Long pivot bounce.",
       "Long scalp", "M15 closes below 2648", "D1 pivot bounce", "moderate", "A",
       "d1_pivot_location", "pivot_probe AND close_above_pp", "d1_pivot_bounce_long_valid",
       "Long scalp", "D1 pivot PP hold — long bounce", 0.82,
       "D1_PIVOT_PP=2650, H1_SUPPORT=2649, M15_PREVIOUS_LOW=2648", 2651.0, 2648.0, 2658.0, 3.0, 7.0),
    ex("02_23", "02_market_structure", "ASIA_SESSION_HIGH sweep — close inside SHORT",
       "Level nest | ASIA_SESSION_HIGH=4162 | Pre-London sweep 4164 (+$2), M15 close 4160 INSIDE | H4 range | M5 bull trap bear | Session level fakeout.",
       "Short reversal", "M15 accepts above 4164", "Asia high sweep fade", "strong", "A",
       "session_level_sweep", "asia_high_breach AND m15_close_inside", "asia_high_sweep_short_valid",
       "Short reversal", "Asia session high swept, M15 close back inside", 0.86,
       "ASIA_SESSION_HIGH=4162, H4_RANGE_HIGH=4165, M15_PREVIOUS_HIGH=4163", 4160.0, 4163.0, 4153.0, 3.0, 7.0),
    ex("02_24", "02_market_structure", "ASIA_SESSION_LOW sweep — close inside LONG",
       "Level nest | ASIA_SESSION_LOW=4154 | Sweep 4152 (-$2), M15 close 4157 INSIDE | H4 support confluence | M5 hammer | Session level fakeout long.",
       "Long scalp", "M15 below 4152", "Asia low sweep fade", "strong", "A",
       "session_level_sweep", "asia_low_breach AND m15_close_inside", "asia_low_sweep_long_valid",
       "Long scalp", "Asia session low swept, M15 close back inside", 0.86,
       "ASIA_SESSION_LOW=4154, H4_PREVIOUS_LOW=4153, M15_PREVIOUS_LOW=4152", 4157.0, 4152.0, 4165.0, 3.0, 8.0),
    # --- Daily rhythm context (07) ---
    ex("07_19", "07_trend_trading", "Range day mid — SKIP (no level edge)",
       "Daily rhythm | Day range so far $72 (2648–2720) | Price mid-range 2684 — no H4/H1 level within $5 | M15 chop | D1 neutral | Skip — routine range, not at edge.",
       "Skip", "Price reaches H4 range edge with rejection", "Mid daily range no edge", "strong", "A",
       "xau_daily_range_rhythm", "mid_range AND no_level_proximity", "daily_mid_skip_valid",
       "Skip", "Mid $60–$90 daily range with no level — no trade", 0.82,
       "H4_RANGE_MID=2684, D1_PIVOT_PP=2680, M15_MA=2683", 0.0, 0.0, 0.0, 0.0, 0.0),
    ex("07_20", "07_trend_trading", "Range day — fade H4 high SHORT ($78 day range)",
       "Daily rhythm | Day high 2720, low 2648 ($72 range) | Price at H4_RANGE_HIGH 2718 | M15 rejection | H1 bull into edge exhausted | Fade edge TP toward mid.",
       "Short reversal", "H1 closes above 2720", "Range day edge fade", "strong", "A",
       "xau_daily_range_rhythm", "range_day AND at_h4_high AND m15_reject", "daily_edge_short_valid",
       "Short reversal", "Routine range day — fade H4 high after $72 day", 0.85,
       "H4_RANGE_HIGH=2720, H1_RESISTANCE=2718, M15_PREVIOUS_HIGH=2717", 2716.0, 2719.0, 2704.0, 3.0, 12.0),
    ex("07_21", "07_trend_trading", "Range day — fade H4 low LONG ($65 day range)",
       "Daily rhythm | Day range $65 (2650–2715) | At H4_RANGE_LOW 2651 | M15 hammer | H1 bear into support | Long edge toward mid.",
       "Long reversal", "H1 closes below 2650", "Range day edge fade", "strong", "A",
       "xau_daily_range_rhythm", "range_day AND at_h4_low AND m15_reject", "daily_edge_long_valid",
       "Long reversal", "Routine range day — long H4 low fade", 0.85,
       "H4_RANGE_LOW=2650, H1_SUPPORT=2652, M15_PREVIOUS_LOW=2651", 2653.0, 2650.0, 2665.0, 3.0, 12.0),
    ex("07_22", "07_trend_trading", "Trend day — with-trend M15 pullback LONG",
       "Daily rhythm | D1 bull (monthly trend day 2 of ~2) | Day +$58 from open | H4 bull | M15 pullback -$8 to H1_MA | M5 bull — with trend not fade.",
       "Long continuation", "H1_MA breaks down", "Trend day pullback buy", "strong", "A",
       "d1_trend_rarity_filter", "d1_trend AND m15_pullback_to_ma", "trend_day_long_valid",
       "Long continuation", "Rare D1 trend day — M15 pullback to H1 MA long", 0.87,
       "D1_TREND_BULL=active, H1_MA=2655, M15_PREVIOUS_LOW=2654", 2656.0, 2653.0, 2668.0, 3.0, 12.0),
    ex("07_23", "07_trend_trading", "Trend day — with-trend M15 pullback SHORT",
       "Daily rhythm | D1 bear active | Day -$62 | H4 bear | M15 rally +$9 to H1_MA | M5 bear — short pullback in trend.",
       "Short continuation", "H1_MA breaks up", "Trend day pullback sell", "strong", "A",
       "d1_trend_rarity_filter", "d1_bear AND m15_rally_to_ma", "trend_day_short_valid",
       "Short continuation", "Rare D1 trend day — M15 rally fade at H1 MA", 0.87,
       "D1_TREND_BEAR=active, H1_MA=2660, M15_PREVIOUS_HIGH=2661", 2659.0, 2662.0, 2647.0, 3.0, 12.0),
    ex("07_24", "07_trend_trading", "False trend day — H4 range reasserts SKIP",
       "Daily rhythm | Morning +$45 looked trend | H4 still bracket 2648–2665 | M15 back mid-range | D1 not accepted — revert to range_day | Skip trend entry.",
       "Skip", "H4 bracket breaks with acceptance", "False trend day filter", "moderate", "A",
       "d1_trend_rarity_filter", "false_trend AND h4_range_intact", "false_trend_skip_valid",
       "Skip", "False trend day — H4 range intact, skip trend bet", 0.78,
       "H4_RANGE_HIGH=2665, H4_RANGE_LOW=2648, D1_PIVOT_PP=2656", 0.0, 0.0, 0.0, 0.0, 0.0),
]

# Small M15 pullback examples — bread-and-butter $6–$10 pullbacks inside daily range
M15_PULLBACKS = [
    ("09_65", "Long scalp", "M15 -$6 pullback to H1_SUPPORT — two-bar bull", "M15 nest | Range day $68 so far | M15[-2]: bear $6 to H1_SUPPORT 2652 | M15[-1]: bull engulf | M5 confirm | Micro long.", "Long scalp", 2653.0, 2650.0, 2660.0, 3.0, 7.0, "H1_SUPPORT=2652, M15_PREVIOUS_LOW=2651, H4_RANGE_MID=2658"),
    ("09_66", "Short reversal", "M15 +$7 rally to H1_RESISTANCE — two-bar bear", "M15 nest | Range day | M15[-2]: bull $7 to H1_RESISTANCE 2660 | M15[-1]: bear engulf | M5 bear | Micro short.", "Short reversal", 2659.0, 2662.0, 2652.0, 3.0, 7.0, "H1_RESISTANCE=2660, M15_PREVIOUS_HIGH=2659, H4_RANGE_MID=2655"),
    ("09_67", "Long scalp", "M15 -$8 dip — three M5 bears compose M15 hammer", "M15 nest | M15 forming: M5[-3,-2,-1] bear bear hammer at M15_PREVIOUS_LOW 2649 | H4 support zone | Long M15 close.", "Long scalp", 2650.0, 2647.0, 2657.0, 3.0, 7.0, "M15_PREVIOUS_LOW=2649, H4_PREVIOUS_LOW=2648, H1_SUPPORT=2650"),
    ("09_68", "Short reversal", "M15 +$9 spike — three M5 bulls compose M15 star", "M15 nest | M15 forming: M5 bull bull shooting_star at M15_PREVIOUS_HIGH 2661 | H1 resistance | Short M15 close.", "Short reversal", 2660.0, 2663.0, 2653.0, 3.0, 7.0, "M15_PREVIOUS_HIGH=2661, H1_RESISTANCE=2662, H4_PREVIOUS_HIGH=2663"),
    ("09_69", "Long scalp", "M15 shallow -$5 pullback in H4 bull — buy", "M15 nest | H4 bull | M15[-1]: bear $5 only (shallow) | M5 bull pin at rising M15_MA | With-trend micro.", "Long scalp", 2654.0, 2651.0, 2661.0, 3.0, 7.0, "M15_MA=2653, H4_PREVIOUS_LOW=2650, H1_SUPPORT=2652"),
    ("09_70", "Short scalp", "M15 shallow +$6 rally in H4 bear — sell", "M15 nest | H4 bear | M15[-1]: bull $6 rally to falling M15_MA | M5 bear | With-trend micro short.", "Short scalp", 2657.0, 2660.0, 2650.0, 3.0, 7.0, "M15_MA=2658, H4_PREVIOUS_HIGH=2662, H1_RESISTANCE=2659"),
    ("09_71", "Long scalp", "M15 -$7 to round $2650 — bounce", "M15 nest | Round 2650 magnet | M15 dip -$7 to 2649, close 2651 | M5 two-bar bull | Round hold long.", "Long scalp", 2651.0, 2648.0, 2658.0, 3.0, 7.0, "ROUND_2650=2650, M15_PREVIOUS_LOW=2649, D1_PIVOT_PP=2650"),
    ("09_72", "Short scalp", "M15 +$8 to round $2650 — fade", "M15 nest | Round 2650 | M15 rally +$8 to 2652, close 2649 | M5 bear | Round rejection short.", "Short scalp", 2649.0, 2652.0, 2642.0, 3.0, 7.0, "ROUND_2650=2650, M15_PREVIOUS_HIGH=2652, D1_PIVOT_PP=2650"),
    ("09_73", "Reverse", "M15 sweep low + close inside — long fade", "M15 nest | M15 swing low 2646 swept to 2644, CLOSE 2648 inside | H4 support | M5 hammer | Sweep long.", "Reverse", 2648.0, 2645.0, 2655.0, 3.0, 7.0, "M15_SWING_LOW=2646, H4_PREVIOUS_LOW=2645, H1_SUPPORT=2647"),
    ("09_74", "Reverse", "M15 sweep high + close inside — short fade", "M15 nest | M15 high 2660 swept 2662, CLOSE 2658 inside | H1 resistance | M5 bear | Sweep short.", "Reverse", 2658.0, 2661.0, 2651.0, 3.0, 7.0, "M15_SWING_HIGH=2660, H1_RESISTANCE=2661, H4_PREVIOUS_HIGH=2662"),
    ("09_75", "Long scalp", "M15 BRG — break retrace go long", "M15 nest | M15 swing high broken $8, retrace to break 2655 within $2, M5 go bar bull | BRG complete.", "Reversal entry", 2656.0, 2653.0, 2663.0, 3.0, 7.0, "M15_BREAK_LEVEL=2655, H1_SUPPORT=2654, H4_PREVIOUS_LOW=2652"),
    ("09_76", "Short reversal", "M15 BRG — break retrace go short", "M15 nest | M15 low broken -$7, retrace to 2648 break, M5 go bear | BRG short.", "Reversal entry", 2647.0, 2650.0, 2640.0, 3.0, 7.0, "M15_BREAK_LEVEL=2648, H1_RESISTANCE=2649, H4_PREVIOUS_HIGH=2651"),
    ("09_77", "Skip", "M15 -$4 pullback — too shallow", "M15 nest | M15[-1]: bear only $4 to level | Below $6 micro threshold | H4 mid-range | Skip shallow.", "Skip", 0.0, 0.0, 0.0, 0.0, 0.0, "H4_RANGE_MID=2656, M15_MA=2655, H1_MA=2657"),
    ("09_78", "Skip", "M15 +$5 rally — no level confluence", "M15 nest | M15 bull $5 but no H1/H4 level within $3 | Open space mid-range | Skip.", "Skip", 0.0, 0.0, 0.0, 0.0, 0.0, "H4_RANGE_MID=2654, M15_MA=2653, D1_PIVOT_PP=2655"),
    ("09_79", "Long scalp", "M15 last 5min -$8 into H1 level — London", "M15 nest | London session | M15 90%: last 5min -$8 to H1_SUPPORT 2651 | M5 bull close | End-bar moment long.", "Long scalp", 2652.0, 2649.0, 2659.0, 3.0, 7.0, "H1_SUPPORT=2651, M15_PREVIOUS_LOW=2650, LONDON_OPEN=2654"),
    ("09_80", "Short reversal", "M15 last 5min +$9 into H1 level — overlap", "M15 nest | Overlap | M15 85%: last 5min +$9 to H1_RESISTANCE 2663 | M5 bear close | End-bar fade.", "Short reversal", 2662.0, 2665.0, 2655.0, 3.0, 7.0, "H1_RESISTANCE=2663, M15_PREVIOUS_HIGH=2662, OVERLAP_MID=2658"),
    ("09_81", "Long continuation", "M15 pullback -$7 in H4 bull channel — buy", "M15 nest | H4 bull channel | M15 touches channel low 2653 (-$7) | M5 bull | Channel pullback long.", "Long continuation", 2654.0, 2651.0, 2662.0, 3.0, 8.0, "H4_CHANNEL_LOW=2653, M15_PREVIOUS_LOW=2652, H1_SUPPORT=2654"),
    ("09_82", "Short continuation", "M15 rally +$8 in H4 bear channel — sell", "M15 nest | H4 bear channel | M15 rally +$8 to channel top 2661 | M5 bear | Channel fade short.", "Short continuation", 2660.0, 2663.0, 2652.0, 3.0, 8.0, "H4_CHANNEL_HIGH=2661, M15_PREVIOUS_HIGH=2660, H1_RESISTANCE=2662"),
    ("09_83", "Long scalp", "M15 two-bar at M15_MA — support hold", "M15 nest | M15[-2]: bear $6 to M15_MA 2654 | M15[-1]: bull $5 | H4 bull context | MA hold long.", "Long scalp", 2655.0, 2652.0, 2662.0, 3.0, 7.0, "M15_MA=2654, H1_SUPPORT=2653, H4_PREVIOUS_LOW=2651"),
    ("09_84", "Short scalp", "M15 two-bar at M15_MA — resistance reject", "M15 nest | M15[-2]: bull $7 to M15_MA 2659 | M15[-1]: bear $6 | H4 bear context | MA reject short.", "Short scalp", 2658.0, 2661.0, 2651.0, 3.0, 7.0, "M15_MA=2659, H1_RESISTANCE=2660, H4_PREVIOUS_HIGH=2662"),
]

for row in M15_PULLBACKS:
    eid, trade_dec, title, setup_body, decision, entry, sl, tp, sl_usd, tp_usd, levels = row
    NEW.append(ex(
        eid, "09_reversal_trading", title, setup_body, decision,
        f"Structure breaks SL at {sl}" if sl else "N/A",
        "M15 micro pullback in daily range", "strong", "A",
        "m15_pullback_in_daily_range", "pullback_usd>=6 AND at_level AND m15_confirm",
        f"m15_pullback_{eid}_valid", trade_dec,
        f"M15 ${abs(tp_usd)} pullback with level confluence — {decision.lower()}",
        0.84 if sl else 0.76,
        levels, entry, sl, tp, sl_usd, tp_usd,
    ))


def main():
    s1 = load_jsonl(KNOW / "stage_01_principle_foundation.jsonl")
    s2 = load_jsonl(KNOW / "stage_02_structured_data.jsonl")
    s3 = load_jsonl(KNOW / "stage_03_detector_definitions.jsonl")
    s4 = load_jsonl(KNOW / "stage_04_decision_contract.jsonl")

    new_ids = {e[0]["example_id"] for e in NEW}
    s1.extend(NEW_PRINCIPLES)

    test_s2 = [r for r in s2 if r["example_id"] in TEST_IDS]
    train_s2 = [r for r in s2 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]
    new_s2 = [e[0] for e in NEW]
    new_s3 = [e[1] for e in NEW]
    new_s4 = [e[2] for e in NEW]

    test_s3 = [r for r in s3 if r["example_id"] in TEST_IDS]
    train_s3 = [r for r in s3 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]
    test_s4 = [r for r in s4 if r["example_id"] in TEST_IDS]
    train_s4 = [r for r in s4 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]

    s2_out = train_s2 + new_s2 + test_s2
    s3_out = train_s3 + new_s3 + test_s3
    s4_out = train_s4 + new_s4 + test_s4

    save_jsonl(KNOW / "stage_01_principle_foundation.jsonl", s1)
    save_jsonl(KNOW / "stage_02_structured_data.jsonl", s2_out)
    save_jsonl(KNOW / "stage_03_detector_definitions.jsonl", s3_out)
    save_jsonl(KNOW / "stage_04_decision_contract.jsonl", s4_out)

    train_n = len(s2_out) - len(test_s2)
    print(f"Added {len(NEW)} examples, {len(NEW_PRINCIPLES)} principles")
    print(f"Total: {len(s2_out)} | Train: {train_n} | Test: {len(test_s2)}")
    print(f"Principles total: {len(s1)}")


if __name__ == "__main__":
    main()
