#!/usr/bin/env python3
"""
Append expanded curriculum: M15/H1/H4 nested moments, balanced buy/sell, fakeouts/sweeps.

Training sample standard (Meta LIMA / instruction-tuning surveys):
- Quality > quantity; consistent schema; no hallucinated fields
- Each example: LEVEL + HTF + MTF(M15) + LTF(M5/M1) nested path
- Balanced long/short; zone SL/TP in gold price (M15≥$5/$5, H4≥$10/$20)
- Fakeout = breach + close back inside (Grimes/Dalton), not narrative
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


def ex(eid, topic, title, setup, decision, invalidation, why, evidence, bucket,
       detector_name, logic, detector_output, trade_decision, conditions, conviction, risk, det_out="enum(valid, invalid)"):
    """Build stage_02/03/04 triple."""
    return (
        {"example_id": eid, "topic": topic, "title": title, "setup": setup, "decision": decision,
         "invalidation": invalidation, "why": why, "evidence": evidence, "bucket": bucket},
        {"example_id": eid, "detector_type": "heuristic", "detector_name": detector_name,
         "input_signals": ["price", "volume", "time", "bars", "levels"],
         "logic": logic, "thresholds": {"tp_usd": [5, 20], "sl_usd": [5, 10]}, "output": det_out},
        {"example_id": eid, "detector_output": detector_output, "trade_decision": trade_decision,
         "decision_conditions": conditions, "evidence_label": evidence,
         "conviction_score": conviction, "risk_control": risk},
    )


NEW_PRINCIPLES = [
    {
        "principle_id": "P042",
        "topic": "04_timeframe_relations",
        "principle_name": "M15 Moment — Last 5–10 Minutes at Level",
        "core_concept": "On XAUUSD, the actionable part of an M15 bar is often the final 5–10 minutes: acceleration into a level, wick rejection, or acceptance. Read M15 from closed M5 segments inside; M1 is timing-only after M5 confirms.",
        "foundational_rule": "State M15[-n] path built from M5[-k..]: e.g. last 5min M15 move $7 into H1 level + M5 bear engulf = M15 rejection. Do not trade M1 spike before M5 close.",
        "why_matters": "Operator uses zone gold SL/TP (M15≥$5/$5); M15 end-bar moments at levels bridge H1 structure to executable entries.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["m15_endbar_moment", "m15_fractal_from_m5"],
    },
    {
        "principle_id": "P043",
        "topic": "05_ict_concepts",
        "principle_name": "Sweep / Fakeout = Breach + Close Back Inside",
        "core_concept": "A liquidity sweep (fakeout) requires: price breaches a reference level on M15/M5, then the SAME bar or next bar CLOSES back inside. Close beyond level = breakout candidate, not sweep.",
        "foundational_rule": "Wait 1–3 M15 bars follow-through rule: extension <0.5 ATR and close inside → fade. Acceptance (2 closes outside) → with breakout. Asia/London first move may be the juke — require close-back-inside before fade.",
        "why_matters": "Most gold fakeouts are stop runs at session highs/lows; training must distinguish sweep from real break using close location only.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["liquidity_sweep_close_inside", "session_juke_fakeout"],
    },
    {
        "principle_id": "P044",
        "topic": "09_reversal_trading",
        "principle_name": "Balanced Long/Short — Same Nested Template Both Ways",
        "core_concept": "Reversal curriculum must pair long and short examples with identical nested structure (H4/H1/M15/M5) so the model learns location + path, not directional bias.",
        "foundational_rule": "For every support reversal long, include resistance reversal short with same dollar move sizes ($6–$10 pullback, $5–$9 TP). Include skip examples when structure forbids trade.",
        "why_matters": "Imbalanced training causes model to default to 'Reverse' or 'Long' regardless of context.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["nested_reversal_template"],
    },
]

# 42 examples — 21 long-bias / 21 short-bias decisions
NEW = [
    # --- Session fakeouts (01) ---
    ex("01_14", "01_market", "Asia high sweep — London juke fakeout SHORT",
       "Session nest | Asia closed bull +$6 (4156→4162) | Pre-London 07:30: sweep Asia high 4163 (+$4), M15 close 4160 INSIDE | H4: range | H1[-1]: bear pin | M5[-1,-2]: bull trap bear engulf | FAKEOUT=breach+close inside. Short TP $7.",
       "Short reversal", "2 M15 closes above 4163", "Session juke fade", "strong", "A",
       "session_juke_fakeout", "asia_high_sweep AND m15_close_inside", "asia_high_sweep_valid",
       "Short reversal", "Asia high swept, M15 close back inside — pre-London juke fade", 0.84,
       "stop $3 above 4163; TP $7"),
    ex("01_15", "01_market", "Asia low sweep — London juke fakeout LONG",
       "Session nest | Asia closed bear -$5 | Pre-London: sweep Asia low 4154 (-$5), M15 close 4157 INSIDE | H4 support 4155 | H1[-1]: bull hammer | M5 two-bar bull | Long after fakeout. TP $8.",
       "Long scalp", "M15 accepts below 4154", "Session juke fade", "strong", "A",
       "session_juke_fakeout", "asia_low_sweep AND m15_close_inside", "asia_low_sweep_valid",
       "Long scalp", "Asia low swept, close back inside — London juke long", 0.85,
       "stop $3 below 4154; TP $8"),
    ex("01_16", "01_market", "London open first move FAKE — wait real deal",
       "Session nest | London 08:00: first M15 spikes +$9 (Lien false move) | M15[-1]: long wick, close mid-bar NOT acceptance | H1 not broken | M5: no follow-through 3 bars | Classify undecided — wait acceptance. Skip.",
       "Wait for confirmation", "M15 acceptance 2 closes beyond open direction", "London false first move", "moderate", "A",
       "london_open_fake_move", "spike_no_acceptance AND no_follow_through_3bars", "london_open_undecided",
       "Wait for confirmation", "London first +$9 spike without M15 acceptance — wait real deal", 0.76,
       "no entry until 2 M15 closes show direction"),
    ex("01_17", "01_market", "London open fake down — real up LONG",
       "Session nest | Asia bull | London 08:05: M15 fake -$7 (Judas swing) | 08:20: M15 bull engulf +$8, 2 M5 closes up | H4 developing bull | Real deal after fake. Long TP $9.",
       "Long trend entry", "M15 closes back below fake low", "London real deal after juke", "strong", "A",
       "london_real_deal_after_juke", "fake_down_then_acceptance_up", "london_continuation_valid",
       "Long trend entry", "London fake down then M15 acceptance up — continue Asia bias", 0.86,
       "stop $3 below fake low; TP $9"),
    ex("01_18", "01_market", "NY overlap fake breakout — fade SHORT",
       "Session nest | Overlap 13:30: M15 breaks London high +$6, tick vol spike | M15[-1]: close INSIDE London range | H1: wick only | M5 bear sequence | Fake breakout at overlap. Short TP $6.",
       "Short scalp", "H1 closes above London high", "Overlap fake breakout", "moderate", "A",
       "overlap_fake_breakout", "m15_pierce AND m15_close_inside_range", "overlap_fake_break_valid",
       "Short scalp", "NY overlap fake above London high — fade inside range", 0.79,
       "stop $3 above spike; TP $6"),
    # --- M15 / H1 / H4 nested (04) ---
    ex("04_20", "04_timeframe_relations", "M15 moment — last 5min $8 into H1 resistance SHORT",
       "M15 nest | H4: range | H1: resistance 2658 | M15 forming 90%: last 5min +$8 (M5[-1] bull $5, M5[0] wick) | M5[-1]: shooting star at 2658 | M1: do not trade until M5 close | Short on M5 close. TP $7.",
       "Short reversal", "M15 closes above 2658", "M15 endbar at level", "strong", "A",
       "m15_endbar_moment", "m15_final_5min_usd>=7 AND at_h1_level AND m5_rejection", "m15_endbar_short_valid",
       "Short reversal", "M15 last 5min $8 into H1 2658, M5 star rejection", 0.87,
       "stop $3 above 2658; TP $7"),
    ex("04_21", "04_timeframe_relations", "M15 moment — last 5min $6 into H1 support LONG",
       "M15 nest | H4: bull | H1 support 2647 | M15 85% elapsed: last 5min -$6, M5[-2,-1] bear bear, M5[0] bull pin | M15 rejection forming at support | Long M5 close. TP $6.",
       "Long scalp", "M15 closes below 2647", "M15 endbar at level", "strong", "A",
       "m15_endbar_moment", "m15_final_5min_usd>=6 AND h1_support AND m5_pin", "m15_endbar_long_valid",
       "Long scalp", "M15 last 5min dip $6 to H1 2647, M5 pin bar", 0.86,
       "stop $3 below 2647; TP $6"),
    ex("04_22", "04_timeframe_relations", "H1 closed bear — 4 M15 bars nested SHORT fade",
       "Nest | H4: bear bias | H1[-1] CLOSED: bear $10 body at 2660 resistance | Inside: M15[-4,-3,-2,-1] bull bull bear bear — M15 fade at H1 high | M5[-1]: bear engulf | Short with H4/H1. TP $8.",
       "Short reversal", "H1[-1] reclaimed above 2660", "H1 closed + M15 nested", "strong", "A",
       "h1_closed_m15_nested", "h1_bear_close AND m15_sequence_at_h1_high", "h1_m15_short_valid",
       "Short reversal", "H1 bear close at 2660, nested M15 bull trap then bear", 0.85,
       "stop $3 above H1 high; TP $8"),
    ex("04_23", "04_timeframe_relations", "H1 closed bull — 4 M15 bars nested LONG",
       "Nest | H4: bull | H1[-1] CLOSED: bull $9 at 2648 support | M15[-4..-1]: bear bear bull bull | M5: two-bar bull | Long with H4/H1 tide. TP $7.",
       "Long scalp", "H1 closes below 2648", "H1 closed + M15 nested", "strong", "A",
       "h1_closed_m15_nested", "h1_bull_close AND m15_sequence_at_support", "h1_m15_long_valid",
       "Long scalp", "H1 bull close at 2648, M15 bear trap then bull sequence", 0.86,
       "stop $3 below 2648; TP $7"),
    ex("04_24", "04_timeframe_relations", "H4(NY) closed bull — M15 pullbacks LONG trend",
       "Nest | H4(NY) CLOSED: bull, HL 2645 | H1[-2,-1]: bear $5 then bull $4 — shallow | M15[-3,-2,-1]: bear bear bull at rising M15 MA | M5 H2 long | With-trend not reversal. TP $8.",
       "Long continuation", "H4 HL 2645 breaks", "H4 trend H1 dip", "strong", "A",
       "h4_trend_m15_pullback_long", "h4_bull AND h1_shallow AND m15_bounce", "h4_trend_long_valid",
       "Long continuation", "H4 bull closed, H1/M15 shallow pullback buy", 0.84,
       "stop $3 below M15 low; TP $8"),
    ex("04_25", "04_timeframe_relations", "H4(NY) closed bear — M15 rally SHORT trend",
       "Nest | H4(NY) CLOSED: bear, LH 2662 | H1[-2,-1]: bull $6 then bear $5 | M15[-3,-2,-1]: bull bull bear at falling MA | M5 two-bar bear | With-trend short. TP $7.",
       "Short continuation", "H4 LH 2662 breaks up", "H4 trend H1 rally fade", "strong", "A",
       "h4_trend_m15_pullback_short", "h4_bear AND h1_rally_fade AND m15_bear", "h4_trend_short_valid",
       "Short continuation", "H4 bear closed, H1/M15 rally fade short", 0.84,
       "stop $3 above M15 high; TP $7"),
    ex("04_26", "04_timeframe_relations", "M15 develops H1 bar — fractal LONG",
       "Fractal | H1 bar 50% elapsed | M15[-2] CLOSED bull | M15[-1] forming: 3 M5 bull bull bull = M15 bull when closes | H4 bull | Entry on M15 close break. TP $6.",
       "Long scalp", "M15 closes bear engulfing", "M15 fractal inside H1", "moderate", "A",
       "m15_fractal_from_m5", "three_m5_bull AND h1_midbar", "m15_fractal_long_valid",
       "Long scalp", "Three M5 bulls compose developing M15 bull inside H1", 0.78,
       "stop $3 below M15 low; TP $6"),
    ex("04_27", "04_timeframe_relations", "M15 develops H1 bar — fractal SHORT",
       "Fractal | H1 60% elapsed | M15[-2] bear | M15[-1]: M5 bear bear bear forming | H4 range top | Short M15 close. TP $5.",
       "Short scalp", "M15 bull engulf", "M15 fractal inside H1", "moderate", "A",
       "m15_fractal_from_m5", "three_m5_bear AND h1_midbar", "m15_fractal_short_valid",
       "Short scalp", "Three M5 bears compose M15 bear at H4 range top", 0.77,
       "stop $3 above M15 high; TP $5"),
    # --- Sweeps / fakeouts (05) ---
    ex("05_13", "05_ict_concepts", "M15 swing high sweep — close inside SHORT",
       "Sweep nest | Level: M15 swing high 2655 | M15[-1]: high 2657 (+$2 sweep), CLOSE 2654 inside | H1: wick only | M5[-1,-2]: bull trap bear | Grimes failed breakout. Short TP $6.",
       "Reverse", "M15 close above 2657", "Liquidity sweep", "strong", "A",
       "liquidity_sweep_close_inside", "breach AND close_inside_m15", "m15_sweep_short_valid",
       "Reverse", "M15 swing high swept, close back inside — fade", 0.85,
       "stop $3 above 2657; TP $6"),
    ex("05_14", "05_ict_concepts", "M15 swing low sweep — close inside LONG",
       "Sweep nest | M15 swing low 2646 | M15[-1]: low 2644 (-$2), CLOSE 2648 inside | H4 support | M5 hammer | Long fade of sweep. TP $7.",
       "Reverse", "M15 close below 2644", "Liquidity sweep", "strong", "A",
       "liquidity_sweep_close_inside", "breach AND close_inside_m15", "m15_sweep_long_valid",
       "Reverse", "M15 swing low swept, close back inside — long", 0.86,
       "stop $3 below 2644; TP $7"),
    ex("05_15", "05_ict_concepts", "Round $2650 sweep fakeout SHORT",
       "Sweep nest | Gold round 2650 | M5 spikes 2652 (+$2), M15 close 2649 | H4 range | Magnet bar then fade | Short scalp TP $5.",
       "Short scalp", "M15 accepts above 2652", "Round number sweep", "moderate", "A",
       "round_number_sweep", "spike_past_2650 AND close_inside", "round_sweep_short_valid",
       "Short scalp", "$2650 round sweep, M15 close back inside", 0.8,
       "stop $3 above 2652; TP $5"),
    ex("05_16", "05_ict_concepts", "Round $2650 sweep fakeout LONG",
       "Sweep nest | Round 2650 | M5 dips 2648 (-$2), M15 close 2651 | H1 support confluence | Long fade. TP $6.",
       "Long scalp", "M15 below 2648", "Round number sweep", "moderate", "A",
       "round_number_sweep", "dip_past_2650 AND close_inside", "round_sweep_long_valid",
       "Long scalp", "$2650 sweep below, M15 close back above", 0.81,
       "stop $3 below 2648; TP $6"),
    ex("05_17", "05_ict_concepts", "Failed sweep — breakout real LONG",
       "Sweep fail nest | M15 breaks prior high 2655, CLOSE 2657 OUTSIDE | 2nd M15 close 2658 | NOT a sweep — accepted breakout | H4 range break attempt. Long breakout TP $8.",
       "Long breakout", "Close back inside range", "Accepted breakout", "strong", "A",
       "accepted_breakout", "close_beyond AND follow_through_2bars", "breakout_long_valid",
       "Long breakout", "M15 close beyond high with follow-through — not fakeout", 0.83,
       "stop $3 below break level; TP $8"),
    ex("05_18", "05_ict_concepts", "Failed sweep — breakout real SHORT",
       "Sweep fail nest | M15 breaks low 2645, CLOSE 2643 OUTSIDE | 2 M15 bear closes | Accepted down break. Short TP $7.",
       "Short breakout", "Close back inside", "Accepted breakout", "strong", "A",
       "accepted_breakout", "close_beyond AND follow_through_2bars", "breakout_short_valid",
       "Short breakout", "M15 close below low with follow-through — real break", 0.83,
       "stop $3 above break level; TP $7"),
    # --- Range fakeouts (08) ---
    ex("08_21", "08_range_trading", "H4 range bottom fakeout LONG",
       "Range nest | H4 box 2640-2660 | Push to 2638 (-$2 sweep), M15 close 2642 INSIDE | H1[-1]: hammer | M5 two-bar bull | 80% fail rule fade. TP $7.",
       "Long scalp", "H4 close below 2640", "Range edge sweep", "strong", "A",
       "h4_range_sweep_fade", "edge_sweep AND m15_close_inside", "h4_bottom_fade_valid",
       "Long scalp", "H4 range bottom sweep, close inside — long fade", 0.85,
       "stop $3 below 2638; TP $7 to mid"),
    ex("08_22", "08_range_trading", "H4 range top fakeout SHORT",
       "Range nest | H4 2640-2660 | Spike 2662, M15 close 2657 inside | M5 bear engulf | Fade top. TP $6.",
       "Short scalp", "H4 accepts above 2660", "Range edge sweep", "strong", "A",
       "h4_range_sweep_fade", "edge_sweep AND m15_close_inside", "h4_top_fade_valid",
       "Short scalp", "H4 range top sweep, close inside — short fade", 0.85,
       "stop $3 above 2662; TP $6"),
    ex("08_23", "08_range_trading", "H1 range $14 — M15 fake breakout both sides WAIT",
       "Range nest | H1 bracket 2650-2664 | M15 fake up then fake down same hour | Barbwire middle | Skip — no edge.",
       "Wait", "Clean edge approach with $7+ push", "Range chop", "strong", "A",
       "range_chop_skip", "double_fake_same_hour", "range_chop_no_edge",
       "Wait", "H1 range double fakeout hour — stand aside", 0.82,
       "wait for edge rejection"),
    ex("08_24", "08_range_trading", "H1 range bottom — M5 trend to edge LONG fade failed SHORT",
       "Range nest | H1 2648-2660 | M5 uptrend to 2659 | M15 rejection | Actually SHORT fade at top (not long at top). TP $6.",
       "Short scalp", "M15 closes above 2660", "LTF trend to H1 edge", "moderate", "A",
       "h1_range_edge_fade", "m5_to_h1_top AND m15_rejection", "h1_top_fade_valid",
       "Short scalp", "M5 trend to H1 top — fade not chase", 0.79,
       "stop $3 above top; TP $6"),
    ex("08_25", "08_range_trading", "H1 range — M5 trend to bottom LONG",
       "Range nest | H1 2648-2660 | M5 clean downtrend to 2649 | M15 bull pin at bottom | Long fade. TP $7.",
       "Long scalp", "M15 below 2648", "LTF trend to H1 edge", "moderate", "A",
       "h1_range_edge_fade", "m5_to_h1_bottom AND m15_pin", "h1_bottom_fade_valid",
       "Long scalp", "M5 trend to H1 bottom — long fade", 0.8,
       "stop $3 below bottom; TP $7"),
    ex("08_26", "08_range_trading", "Magnet bar at H4 top then fade SHORT",
       "Range nest | Brooks magnet: large M15 bull at 2660 edge | Next M15 bear engulf | H4 range | Short TP $8.",
       "Short scalp", "Next M15 bull continuation", "Magnet bar fade", "moderate", "A",
       "magnet_bar_fade", "large_bar_at_edge AND next_bar_reversal", "magnet_fade_valid",
       "Short scalp", "Magnet bull at H4 top, M15 bear engulf fade", 0.81,
       "stop $3 above magnet high; TP $8"),
    ex("08_27", "08_range_trading", "Magnet bar at H4 bottom then fade LONG",
       "Range nest | Large M15 bear at 2640 edge | Next M15 bull engulf | Long TP $7.",
       "Long scalp", "Next M15 bear continuation", "Magnet bar fade", "moderate", "A",
       "magnet_bar_fade", "large_bar_at_edge AND next_bar_reversal", "magnet_fade_long_valid",
       "Long scalp", "Magnet bear at H4 bottom, M15 bull engulf", 0.81,
       "stop $3 below magnet low; TP $7"),
    ex("08_28", "08_range_trading", "Final flag fake breakout SHORT",
       "Range nest | H4 uptrend late | Tight H1 flag at top | M15 breakout +$5 FAIL close inside | Final flag fail. Short TP $9.",
       "Reverse", "H1 accepts above flag", "Final flag fail", "moderate", "A",
       "final_flag_fail", "tight_flag AND failed_breakout", "final_flag_short_valid",
       "Reverse", "H1 final flag fake breakout — short reversal", 0.78,
       "stop $3 above flag; TP $9"),
    # --- Reversals M15/H1/H4 balanced (09) ---
    ex("09_40", "09_reversal_trading", "M15 two-bar at H4 level — LONG",
       "Rev nest | H4 support 2648 | M15[-2]: bear $5 extreme | M15[-1]: bull close above | M5 confirm | H1[-1]: bull | Long TP $6.",
       "Long scalp", "M15[-1] fails", "M15 two-bar at H4", "strong", "A",
       "m15_two_bar_h4_level", "m15_two_bar AND h4_support", "m15_two_bar_long_valid",
       "Long scalp", "M15 two-bar reversal at H4 2648 support", 0.84,
       "stop $3 below M15 low; TP $6"),
    ex("09_41", "09_reversal_trading", "M15 two-bar at H4 level — SHORT",
       "Rev nest | H4 resistance 2662 | M15[-2]: bull $6 | M15[-1]: bear below | M5 bear | Short TP $7.",
       "Short reversal", "M15[-1] fails", "M15 two-bar at H4", "strong", "A",
       "m15_two_bar_h4_level", "m15_two_bar AND h4_resistance", "m15_two_bar_short_valid",
       "Short reversal", "M15 two-bar reversal at H4 2662 resistance", 0.85,
       "stop $3 above M15 high; TP $7"),
    ex("09_42", "09_reversal_trading", "H1 three-bar reversal at D1 pivot LONG",
       "Rev nest | D1 pivot 2650 | H1[-3,-2,-1]: bear bear bull ($4,$3,$5) | M15 bull engulf | M5 entry | Long TP $8.",
       "Long scalp", "H1 closes below pivot", "H1 reversal D1 level", "strong", "A",
       "h1_reversal_d1_level", "three_h1_bear_then_bull AND d1_pivot", "h1_d1_long_valid",
       "Long scalp", "H1 three-bar reversal at D1 pivot 2650", 0.86,
       "stop $3 below pivot; TP $8"),
    ex("09_43", "09_reversal_trading", "H1 three-bar reversal at D1 pivot SHORT",
       "Rev nest | D1 pivot 2650 | H1[-3,-2,-1]: bull bull bear | M15 bear engulf | Short TP $7.",
       "Short reversal", "H1 closes above pivot", "H1 reversal D1 level", "strong", "A",
       "h1_reversal_d1_level", "three_h1_bull_then_bear AND d1_pivot", "h1_d1_short_valid",
       "Short reversal", "H1 three-bar reversal at D1 pivot — short", 0.86,
       "stop $3 above pivot; TP $7"),
    ex("09_44", "09_reversal_trading", "H4 last 30min spike fade SHORT (duplicate pattern sell)",
       "Rev nest | H4 80% | Last 30min +$12 to 2668 D1 level | M15[-2,-1]: bull bull | M5 bear reversal | H1 wick | Short TP $9.",
       "Short reversal", "H4 close above 2668", "H4 endbar fade", "strong", "A",
       "h4_endbar_spike_fade", "h4_last_30min_spike AND m5_reversal", "h4_spike_short_valid",
       "Short reversal", "H4 end segment spike to D1 level — fade", 0.87,
       "stop $4 above 2668; TP $9"),
    ex("09_45", "09_reversal_trading", "H4 last 30min dip fade LONG",
       "Rev nest | H4 75% | Last 30min -$10 to 2646 support | M15 hammer | M5 two-bar bull | Long TP $8.",
       "Long scalp", "H4 close below 2646", "H4 endbar fade", "strong", "A",
       "h4_endbar_spike_fade", "h4_last_30min_dip AND m5_bull", "h4_dip_long_valid",
       "Long scalp", "H4 end segment dip to support — long fade", 0.87,
       "stop $3 below 2646; TP $8"),
    ex("09_46", "09_reversal_trading", "Fake H1 breakout up — SHORT",
       "Fakeout nest | H1 resistance 2655 | M15 breaks +$4, 2 bars later close inside | M5 bear | H4 range | Short TP $6.",
       "Reverse", "H1 accepts above 2655", "H1 fake breakout", "strong", "A",
       "h1_fake_breakout", "break AND close_back_inside", "h1_fake_short_valid",
       "Reverse", "H1 fake breakout above 2655 — short fade", 0.84,
       "stop $3 above spike; TP $6"),
    ex("09_47", "09_reversal_trading", "Fake H1 breakout down — LONG",
       "Fakeout nest | H1 support 2648 | M15 break -$5, close back inside | M5 bull | Long TP $7.",
       "Long scalp", "H1 below 2648", "H1 fake breakout", "strong", "A",
       "h1_fake_breakout", "break AND close_back_inside", "h1_fake_long_valid",
       "Long scalp", "H1 fake breakdown below 2648 — long", 0.85,
       "stop $3 below spike; TP $7"),
    ex("09_48", "09_reversal_trading", "H4 bear channel — H1 fake up SHORT",
       "Rev nest | H4 bear channel | H1 fake rally +$8 to channel mid (not breakout) | M15 bear | M5 short | TP $6.",
       "Short continuation", "H1 closes above channel", "Fake rally in bear", "moderate", "A",
       "h4_channel_fake_rally", "h4_bear AND h1_rally_fade", "h4_channel_short_valid",
       "Short continuation", "H1 fake rally inside H4 bear channel — short", 0.8,
       "stop $3 above rally high; TP $6"),
    ex("09_49", "09_reversal_trading", "H4 bull channel — H1 fake down LONG",
       "Rev nest | H4 bull channel | H1 fake dip -$7 | M15 bull | Long TP $7.",
       "Long continuation", "H1 closes below channel", "Fake dip in bull", "moderate", "A",
       "h4_channel_fake_dip", "h4_bull AND h1_dip_buy", "h4_channel_long_valid",
       "Long continuation", "H1 fake dip inside H4 bull channel — long", 0.81,
       "stop $3 below dip low; TP $7"),
    ex("09_50", "09_reversal_trading", "Double fake at level — SKIP",
       "Fakeout nest | Level 2655 | M15 fake up then fake down within 30min | No acceptance | H4 chop | Skip.",
       "Skip", "Clear single rejection one direction", "Double fake", "moderate", "A",
       "double_fake_skip", "two_fakes_same_level_30min", "double_fake_no_edge",
       "Skip", "Double fakeout at 2655 — no trade", 0.75,
       "wait for acceptance or clean sweep+reject"),
    ex("09_51", "09_reversal_trading", "M15 climax bar fake — SHORT",
       "Rev nest | M15 volume climax $11 range bar at 2660 | Next M15 bear | H1 at resistance | Short TP $8.",
       "Short reversal", "Climax follow-through bull", "Climax fake", "moderate", "A",
       "m15_climax_reversal", "climax_bar AND next_bar_reversal", "m15_climax_short_valid",
       "Short reversal", "M15 climax at high, next bar bear — short", 0.79,
       "stop $3 above climax; TP $8"),
    ex("09_52", "09_reversal_trading", "M15 climax bar fake — LONG",
       "Rev nest | M15 climax at 2644 low | Next M15 bull | H4 support | Long TP $7.",
       "Long scalp", "Climax follow-through bear", "Climax fake", "moderate", "A",
       "m15_climax_reversal", "climax_bar AND next_bar_reversal", "m15_climax_long_valid",
       "Long scalp", "M15 climax at low, next bar bull — long", 0.8,
       "stop $3 below climax; TP $7"),
    ex("09_53", "09_reversal_trading", "H4 MTR long side — failure test LONG",
       "MTR nest | H4 bear broke, retest low FAILS SHORT of low | H1[-1]: stops $3 above low, bull | M15 engulf | Long MTR. TP $9.",
       "Reverse", "Retest breaks low", "H4 MTR failure test long", "moderate", "A",
       "h4_mtr_failure_test_long", "failure_test_low AND h1_bull", "h4_mtr_long_valid",
       "Reverse", "H4 MTR failure test at low — long reversal", 0.81,
       "stop $3 below test; TP $9"),
    ex("09_54", "09_reversal_trading", "H4 MTR short side — failure test SHORT",
       "MTR nest | H4 bull broke, retest high fails below | H1 bear engulf | M15 LH | Short. TP $8.",
       "Reverse", "Retest exceeds high", "H4 MTR failure test short", "moderate", "A",
       "h4_mtr_failure_test_short", "failure_test_high AND h1_bear", "h4_mtr_short_valid",
       "Reverse", "H4 MTR failure test at high — short", 0.82,
       "stop $3 above test; TP $8"),
    ex("09_55", "09_reversal_trading", "Nested bull trap at H4 — SHORT",
       "Trap nest | H4 2660 | H1[-2,-1]: bull bull | M15 breaks +$3, closes back | M5 bear | Bull trap. TP $6.",
       "Short reversal", "H1 new high above trap", "Bull trap", "strong", "A",
       "bull_trap_h4", "h1_bull AND m15_fake_break", "bull_trap_short_valid",
       "Short reversal", "H1 bull trap at H4 2660 — short", 0.86,
       "stop $3 above trap; TP $6"),
    ex("09_56", "09_reversal_trading", "Nested bear trap at H4 — LONG",
       "Trap nest | H4 2648 | H1 bear bear | M15 fake down close inside | M5 bull | Bear trap long. TP $7.",
       "Long scalp", "H1 new low below trap", "Bear trap", "strong", "A",
       "bear_trap_h4", "h1_bear AND m15_fake_break", "bear_trap_long_valid",
       "Long scalp", "H1 bear trap at H4 2648 — long", 0.86,
       "stop $3 below trap; TP $7"),
    ex("09_57", "09_reversal_trading", "H1 BRG short at H4 resistance",
       "BRG nest | H4 2662 resistance | H1 break $8, retrace, go bear | M15 bear sequence | Short entry. TP $7.",
       "Reversal entry", "Go bar fails", "BRG short H4", "strong", "A",
       "h1_brg_h4_short", "h1_brg AND h4_resistance", "h1_brg_short_valid",
       "Reversal entry", "H1 BRG short at H4 2662 resistance", 0.85,
       "stop $3 above retrace; TP $7"),
    ex("09_58", "09_reversal_trading", "H1 BRG long at H4 support",
       "BRG nest | H4 2648 support | H1 break down $7, retrace, go bull | M15 bull | Long. TP $8.",
       "Reversal entry", "Go bar fails", "BRG long H4", "strong", "A",
       "h1_brg_h4_long", "h1_brg AND h4_support", "h1_brg_long_valid",
       "Reversal entry", "H1 BRG long at H4 2648 support", 0.86,
       "stop $3 below retrace; TP $8"),
    ex("09_59", "09_reversal_trading", "Parabolic H4 — SKIP reversal both ways",
       "Veto nest | H4 3 large bull bars $25 no overlap | M15 parabolic | Any counter short = veto | Skip.",
       "Skip", "H4 base 2+ overlapping bars", "Parabolic veto", "strong", "A",
       "parabolic_veto", "h4_parabolic AND no_base", "parabolic_skip",
       "Skip", "H4 parabolic — no reversal long or short", 0.88,
       "stand aside until H4 pause"),
    ex("09_60", "09_reversal_trading", "H4 range mid fake — SKIP",
       "Skip nest | H4 mid 2650 | M15 fake both directions | No level | Skip.",
       "Skip", "Edge $7+ push", "Range mid fake", "moderate", "A",
       "range_mid_skip", "h4_mid AND double_fake", "h4_mid_skip",
       "Skip", "H4 range midpoint fakeouts — no edge", 0.8,
       "wait for edge"),
    ex("09_61", "09_reversal_trading", "Wedge 3-push H4 top SHORT",
       "Rev nest | H4 three pushes 2654,2658,2661 | M15[-1]: bear | H1 LH | Wedge reversal short. TP $10.",
       "Reverse", "Push 4 new high", "Wedge 3-push", "moderate", "A",
       "h4_wedge_reversal", "three_push AND m15_bear", "h4_wedge_short_valid",
       "Reverse", "H4 three-push wedge top — short", 0.79,
       "stop $3 above 2661; TP $10 to mid"),
    ex("09_62", "09_reversal_trading", "Wedge 3-push H4 bottom LONG",
       "Rev nest | H4 three pushes down to 2644 | M15 bull | H1 HL | Long wedge. TP $9.",
       "Reverse", "Push 4 new low", "Wedge 3-push", "moderate", "A",
       "h4_wedge_reversal", "three_push AND m15_bull", "h4_wedge_long_valid",
       "Reverse", "H4 three-push wedge bottom — long", 0.8,
       "stop $3 below 2644; TP $9"),
    ex("09_63", "09_reversal_trading", "Session sweep NY low LONG",
       "Session nest | NY 16:00 | Sweep prior NY low -$6, M15 close inside | H4 bull bias | M5 bull | Long TP $7.",
       "Long scalp", "NY low break accepted", "NY session sweep", "moderate", "A",
       "session_sweep_fade", "ny_low_sweep AND close_inside", "ny_sweep_long_valid",
       "Long scalp", "NY open sweep of low, close inside — long", 0.78,
       "stop $3 below sweep; TP $7"),
    ex("09_64", "09_reversal_trading", "Session sweep NY high SHORT",
       "Session nest | NY | Sweep prior NY high +$7, M15 close inside | H4 range | M5 bear | Short TP $6.",
       "Short reversal", "NY high accepted", "NY session sweep", "moderate", "A",
       "session_sweep_fade", "ny_high_sweep AND close_inside", "ny_sweep_short_valid",
       "Short reversal", "NY sweep of high, close inside — short", 0.78,
       "stop $3 above sweep; TP $6"),
]


def main() -> None:
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
    longish = sum(1 for e in NEW if "Long" in e[0]["decision"] or e[0]["decision"] in ("Reverse", "Reversal entry") and "Short" not in e[2]["trade_decision"])
    print(f"Added {len(NEW)} examples, {len(NEW_PRINCIPLES)} principles")
    print(f"Total: {len(s2_out)} | Train: {train_n} | Test: {len(test_s2)}")
    print(f"Principles total: {len(s1)}")


if __name__ == "__main__":
    main()
