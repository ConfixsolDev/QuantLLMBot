#!/usr/bin/env python3
"""Append H1/H4 nested-candle reversal, trend, and range examples (v2 distillation)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"
TEST_IDS = {f"09_{i:02d}" for i in range(5, 15)}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


NEW_PRINCIPLES = [
    {
        "principle_id": "P038",
        "topic": "04_timeframe_relations",
        "principle_name": "Nested Candle Read Order (D1→H4→H1→M15→M5→M1)",
        "core_concept": "Every decision reads top-down: parent TF story first, then how each child TF built inside the parent bar. One H4 = 4 H1 = 16 M15. Three M5 reversal bars can be one M15 reversal at the M15 close.",
        "foundational_rule": "In every example, state closed parent bars first, then list child bars inside the active parent (e.g. H1[-3,-2,-1] inside developing H4). M1 is timing only after M5/M15 confirm. Never infer H4 close from M1 spike alone.",
        "why_matters": "Operator doctrine: levels tell WHERE; nested candles tell HOW; session + H4(NY) tell WHEN. Without nested bars in training data the model cannot learn intra-bar path at levels.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["nested_candle_read", "htf_developing_bar", "fractal_m15_from_m5"],
    },
    {
        "principle_id": "P039",
        "topic": "04_timeframe_relations",
        "principle_name": "H4 NY-Anchored Close & Last-30-Minute Moment",
        "core_concept": "Canonical H4 uses New York session close as bar boundary. End-of-H4 acceleration (last 15–30 min) often completes the level test — judge rejection/acceptance after H4 close, but developing high/low are facts from closed M15/M5 inside.",
        "foundational_rule": "Track developing_H4 high/low/range from closed lower TFs. Last 30min of H4 at a level: if M15 shows spike + rejection wicks, fade only after M15 close or H4 close confirms — not on M1 alone.",
        "why_matters": "Gold moves $8–$15 in H4 last segment at levels. Training must pair H4(NY) clock with nested M15/M5 path or the model confuses spike with acceptance.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["h4_ny_endbar_moment", "developing_h4_level_test"],
    },
    {
        "principle_id": "P040",
        "topic": "09_reversal_trading",
        "principle_name": "H1 Reversal Inside H4 — Underlying Bar Sequence Required",
        "core_concept": "H1 reversal at an H4 level is valid when H4 context permits (not parabolic veto) AND the H1 path shows test + rejection: typically 2–3 H1 bars into the level plus M15/M5 confirmation bar.",
        "foundational_rule": "Document: H4 state (bull/bear/range), H1 sequence into level, M15 rejection/engulf, M5 entry trigger. TP on XAU micro reversals $5–$9 unless H4 range target is larger.",
        "why_matters": "Most operator reversals are H1-shaped inside H4 location — not isolated M5 patterns.",
        "evidence_strength": "strong",
        "applies_to_detectors": ["h1_reversal_in_h4", "nested_reversal_at_h4_level"],
    },
    {
        "principle_id": "P041",
        "topic": "08_range_trading",
        "principle_name": "H4 Range Edge Fade — Sharp LTF Trend Into Boundary",
        "core_concept": "Inside an H4 bracket, expect clean H1/M5 trends from mid to edge (Grimes). Fade the edge when magnet bar runs into boundary + rejection on M15; TP mid-range or $6–$8 — not a full H4 reversal thesis.",
        "foundational_rule": "H4 range width $15–$25 typical on gold: trade edges only, skip middle third. Log nested: H4 box high/low, H1 push into edge, M15 wick rejection, M5 fade entry. Stop beyond edge at TF gold mins (M15≥$5, H4≥$10); TP next opposing named level (H4≥$20).",
        "why_matters": "Range is ~70–80% of sessions; H4-bracket fades with nested LTF path are high-frequency quality setups distinct from trend reversal.",
        "evidence_strength": "moderate",
        "applies_to_detectors": ["h4_range_edge_fade", "ltf_trend_to_range_edge"],
    },
]

# Each entry: (stage_02, stage_03, stage_04)
NEW_EXAMPLES = [
    # --- 04_timeframe_relations: nested read discipline ---
    (
        {
            "example_id": "04_15",
            "topic": "04_timeframe_relations",
            "title": "Nested read — H4 developing, wait for close",
            "setup": "XAUUSD nested read | D1: neutral at pivot 2650 | H4(NY): developing bar 75% elapsed, high-so-far 2654, low 2646 — NOT closed | H1[-1]: bear close 2647 | M15: retest H4 low 2646, no H4 close yet | M5: chop | Rule: LTF at H4 level but H4 close pending → wait.",
            "decision": "Wait for HTF close",
            "invalidation": "H4 closes bullish above 2650 with M15 acceptance",
            "why": "Bar-close discipline",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "04_15",
            "detector_type": "heuristic",
            "detector_name": "htf_developing_bar",
            "input_signals": ["price", "time", "bars", "levels"],
            "logic": "h4_developing AND ltf_at_level AND h4_close_pending",
            "thresholds": {"h4_elapsed_pct_min": 0.5},
            "output": "enum(pending)",
        },
        {
            "example_id": "04_15",
            "detector_output": "h4_close_pending",
            "trade_decision": "Wait for HTF close",
            "decision_conditions": "H4(NY) developing — M15 at H4 low but H4 not closed; no thesis change",
            "evidence_label": "strong",
            "conviction_score": 0.88,
            "risk_control": "wait for H4 boundary; use developing high/low only as facts",
        },
    ),
    (
        {
            "example_id": "04_16",
            "topic": "04_timeframe_relations",
            "title": "M15 break ≠ H4 break — failed probe",
            "setup": "Nested | H4: closed prior bar bull, support 2648 | H1[-1]: bear into 2648 | M15[-2]: wick below 2648 | M15[-1]: close back above 2648 (inside) | M5: failed probe sequence | M15 pierced level; H4 level NOT broken on H4/H1 close basis.",
            "decision": "Long scalp",
            "invalidation": "H1 closes below 2648 or H4 bar closes below support",
            "why": "Break hierarchy",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "04_16",
            "detector_type": "heuristic",
            "detector_name": "break_hierarchy_ltf_mtf",
            "input_signals": ["price", "bars", "levels"],
            "logic": "m15_pierce AND m15_close_inside AND h1_close_inside",
            "thresholds": {"level": "h4_support"},
            "output": "enum(valid)",
        },
        {
            "example_id": "04_16",
            "detector_output": "ltf_probe_failed",
            "trade_decision": "Long scalp",
            "decision_conditions": "M15 wick below H4 support, close inside — failed probe not H4 break",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "stop $3 below M15 probe low; TP $6",
        },
    ),
    (
        {
            "example_id": "04_17",
            "topic": "04_timeframe_relations",
            "title": "Triple Screen — H4 up, H1 dip, M15 long",
            "setup": "Triple Screen XAU | H4(NY closed): bull, higher low held 2645 | H1[-3,-2,-1]: bear bear bull — dip into 2646-2648 zone (40% H4 leg) | M15[-1]: hammer at H4 support | M5[-1,-2]: two-bar bull reversal | Analysis=H4 timing=M15.",
            "decision": "Long",
            "invalidation": "H1 closes below 2644 or H4 swing low breaks",
            "why": "Triple Screen alignment",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "04_17",
            "detector_type": "heuristic",
            "detector_name": "triple_screen_alignment",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_bull AND h1_pullback AND m15_reversal_at_support",
            "thresholds": {"pullback_pct_h4_leg": [0.38, 0.62]},
            "output": "enum(valid)",
        },
        {
            "example_id": "04_17",
            "detector_output": "triple_screen_long_valid",
            "trade_decision": "Long",
            "decision_conditions": "H4 up, H1 dip to support, M15 hammer + M5 two-bar confirm",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "stop $3 below M15 low; TP $7 toward H4 mid",
        },
    ),
    (
        {
            "example_id": "04_18",
            "topic": "04_timeframe_relations",
            "title": "M5 spike does not flip H4 read",
            "setup": "Nested | H4: closed bull, no level break | H1[-1]: small bear | M15: inside bar | M5[-3,-2,-1]: strong bull burst $5 in 3 bars — counter to H1 dip | M1: spike only | Do NOT upgrade to H4 bear from M5 momentum alone.",
            "decision": "Skip",
            "invalidation": "H1 or M15 closes bear below H4 support",
            "why": "LTF momentum veto",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "04_18",
            "detector_type": "heuristic",
            "detector_name": "ltf_momentum_htf_veto",
            "input_signals": ["price", "bars"],
            "logic": "m5_burst AND h4_closed_bull AND no_m15_m15_break",
            "thresholds": {"m5_burst_usd_max": 6},
            "output": "enum(invalid)",
        },
        {
            "example_id": "04_18",
            "detector_output": "m5_spike_insufficient",
            "trade_decision": "Skip",
            "decision_conditions": "M5 bull burst inside bullish H4 — no HTF thesis change",
            "evidence_label": "strong",
            "conviction_score": 0.8,
            "risk_control": "wait for H1/M15 closed structure",
        },
    ),
    (
        {
            "example_id": "04_19",
            "topic": "04_timeframe_relations",
            "title": "Fractal — 3 M5 bars = M15 reversal at close",
            "setup": "Fractal nest | M15 bar closing now | M5[-3]: bull extreme at 2653 | M5[-2]: inside bar | M5[-1]: bear close below M5[-3] low — M15 reversal bar forming | H1: still bull pullbacks | H4: range top 2654. Entry on M15 close, not M5[-1] mid-bar.",
            "decision": "Short scalp",
            "invalidation": "M15 closes bull above 2653 high",
            "why": "Fractal nesting",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "04_19",
            "detector_type": "heuristic",
            "detector_name": "fractal_m15_from_m5",
            "input_signals": ["price", "bars"],
            "logic": "three_m5_reversal_pattern AND m15_boundary_close",
            "thresholds": {"tp_usd": [5, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "04_19",
            "detector_output": "m15_fractal_reversal_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "Three M5 bars compose M15 reversal at H4 range top",
            "evidence_label": "strong",
            "conviction_score": 0.82,
            "risk_control": "stop $3 above M15 high; TP $6",
        },
    ),
    # --- 07_trend_trading: H1/H4 trend with nested ---
    (
        {
            "example_id": "07_14",
            "topic": "07_trend_trading",
            "title": "H4 bull trend — buy H1 dips to M15 support",
            "setup": "Trend nest XAU | H4(NY closed x3): higher highs/higher lows, always-in long | H1[-2,-1]: bear $4 then bull $3 — shallow pullback | M15[-1]: bounce off rising M15 support | M5: H2 long at MA | TP $7 continuation.",
            "decision": "Long continuation",
            "invalidation": "H1 closes below prior H1 swing low or H4 bull sequence breaks",
            "why": "With-trend nested entry",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "07_14",
            "detector_type": "heuristic",
            "detector_name": "h4_trend_h1_pullback_long",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_always_in_long AND h1_shallow_pullback AND m15_support_bounce",
            "thresholds": {"pullback_usd_max": 10, "tp_usd": [6, 9]},
            "output": "enum(valid)",
        },
        {
            "example_id": "07_14",
            "detector_output": "h4_trend_pullback_valid",
            "trade_decision": "Long continuation",
            "decision_conditions": "H4 bull intact, H1 dip $7, M15 support bounce, M5 H2 entry",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "risk_control": "stop $3 below M15 swing; TP $7",
        },
    ),
    (
        {
            "example_id": "07_15",
            "topic": "07_trend_trading",
            "title": "H4 range — trade sharp M5 trend H1 edge to edge",
            "setup": "Range nest | H4: $20 bracket 2640-2660, flat MA | H1: oscillating, no HH/HL | M5: clean micro uptrend from 2642 to 2658 (edge run) | At 2658: do NOT call H4 breakout — expect fade unless acceptance. With-trend M5 long mid→top already done; now wait fade at top.",
            "decision": "Wait",
            "invalidation": "H4 closes outside 2660 with 2 H1 acceptance bars",
            "why": "Range vs trend inversion",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "07_15",
            "detector_type": "heuristic",
            "detector_name": "ltf_trend_inside_htf_range",
            "input_signals": ["price", "bars"],
            "logic": "h4_range AND m5_clean_trend_to_edge AND at_edge",
            "thresholds": {"h4_range_usd": [15, 25]},
            "output": "enum(at_edge)",
        },
        {
            "example_id": "07_15",
            "detector_output": "ltf_trend_at_h4_edge",
            "trade_decision": "Wait",
            "decision_conditions": "Sharp M5 trend reached H4 range top — do not chase; prepare fade or breakout watch",
            "evidence_label": "moderate",
            "conviction_score": 0.74,
            "risk_control": "no long at edge; wait M15 rejection or H4 acceptance",
        },
    ),
    (
        {
            "example_id": "07_16",
            "topic": "07_trend_trading",
            "title": "H4 always-in long — H1 H2 at MA confluence",
            "setup": "Trend nest | H4: bull, last closed bar strong bull body | H1: pullback to 20-EMA + prior breakout level 2651 confluence | H1[-2,-1]: bear then bull engulf at MA | M15[-1]: higher low | M5: entry on break of pullback high | Nested confirms with-trend, not reversal.",
            "decision": "Long",
            "invalidation": "H1 close below MA and level 2651",
            "why": "H1/H2 at MA",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "07_16",
            "detector_type": "heuristic",
            "detector_name": "h1_h2_ma_confluence",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_bull AND h1_h2_at_ma AND m15_higher_low",
            "thresholds": {"tp_usd": [6, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "07_16",
            "detector_output": "h1_h2_ma_valid",
            "trade_decision": "Long",
            "decision_conditions": "H4 always-in long, H1 H2 at MA+level, M15 HL confirm",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "stop $3 below MA zone; TP $8",
        },
    ),
    (
        {
            "example_id": "07_17",
            "topic": "07_trend_trading",
            "title": "H4 overextended — skip H1 long",
            "setup": "Veto nest | H4: bull but 3+ consecutive large bull bodies, price $18 above H4 MA | H1[-1]: bull spike | M15: parabolic micro | M5: acceleration | HTF overextension veto — do not buy H1 dip until H4 retrace or range forms.",
            "decision": "Skip",
            "invalidation": "H4 prints 2+ overlapping doji/H1 retrace >$10",
            "why": "HTF overextension veto",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "07_17",
            "detector_type": "heuristic",
            "detector_name": "htf_overextension_veto",
            "input_signals": ["price", "bars"],
            "logic": "h4_stretch_gt_2atr AND h1_spike AND m15_parabolic",
            "thresholds": {"stretch_usd_min": 15},
            "output": "enum(veto)",
        },
        {
            "example_id": "07_17",
            "detector_output": "h4_overextended_veto",
            "trade_decision": "Skip",
            "decision_conditions": "H4 bull stretched $18 above MA — skip with-trend H1 long",
            "evidence_label": "strong",
            "conviction_score": 0.83,
            "risk_control": "stand aside until H4 base forms",
        },
    ),
    (
        {
            "example_id": "07_18",
            "topic": "07_trend_trading",
            "title": "H1 bear channel — M5 short at upper rail",
            "setup": "Trend nest | H4: bear bias, lower highs | H1: bear channel 2655-2645 ($10) | H1[-1]: touch upper rail 2654 | M15[-1]: bear rejection wick | M5[-1,-2]: two-bar bear at rail | Short with H4/H1 tide, not counter-trend.",
            "decision": "Short continuation",
            "invalidation": "H1 closes above channel upper rail 2655",
            "why": "Channel fade with trend",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "07_18",
            "detector_type": "heuristic",
            "detector_name": "h1_channel_rail_short",
            "input_signals": ["price", "bars"],
            "logic": "h4_bear AND h1_bear_channel AND m15_rejection_upper_rail",
            "thresholds": {"channel_usd": [8, 12], "tp_usd": [5, 7]},
            "output": "enum(valid)",
        },
        {
            "example_id": "07_18",
            "detector_output": "h1_channel_short_valid",
            "trade_decision": "Short continuation",
            "decision_conditions": "H4 bear, H1 channel upper rail rejection, M5 two-bar bear",
            "evidence_label": "moderate",
            "conviction_score": 0.79,
            "risk_control": "stop $3 above rail; TP $6 to channel mid",
        },
    ),
    # --- 08_range_trading: H4/H1 range reversals ---
    (
        {
            "example_id": "08_16",
            "topic": "08_range_trading",
            "title": "H4 $18 range — fade top, nested M15 rejection",
            "setup": "Range nest XAU | H4: bracket 2642-2660 ($18), 6 bars overlapping | H1[-2,-1]: bull push $9 into 2660 top | M15[-1]: shooting star, close inside | M5[-1]: bear engulf | Magnet bar at edge → fade, not breakout long. TP $7 to H4 mid ~2651.",
            "decision": "Short scalp",
            "invalidation": "H1 accepts above 2660 with 2 closes or H4 breakout follow-through",
            "why": "H4 range edge fade",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "08_16",
            "detector_type": "heuristic",
            "detector_name": "h4_range_edge_fade",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_range AND push_to_top_usd>=7 AND m15_rejection",
            "thresholds": {"h4_range_usd": [15, 22], "tp_usd": [6, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "08_16",
            "detector_output": "h4_range_top_fade_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "H4 $18 range top fade — H1 $9 push, M15 star, M5 engulf",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "risk_control": "stop $3 above 2660; TP $7 mid-range",
        },
    ),
    (
        {
            "example_id": "08_17",
            "topic": "08_range_trading",
            "title": "H4 range middle third — skip",
            "setup": "Range nest | H4: bracket 2640-2660 | Price at 2650 (mid) | H1: overlapping doji sequence | M15/M5: barbwire overlap | Middle third + middle clock → no edge, ~50/50. Skip per range doctrine.",
            "decision": "Wait",
            "invalidation": "Price reaches H4 edge with $7+ push and rejection structure",
            "why": "Range middle no-edge",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "08_17",
            "detector_type": "heuristic",
            "detector_name": "range_middle_skip",
            "input_signals": ["price", "bars"],
            "logic": "price_in_middle_third_h4 AND overlapping_bars",
            "thresholds": {"edge_distance_usd_min": 6},
            "output": "enum(skip)",
        },
        {
            "example_id": "08_17",
            "detector_output": "range_mid_no_edge",
            "trade_decision": "Wait",
            "decision_conditions": "H4 range midpoint 2650 — overlapping H1/M15, no trade",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "wait for edge approach",
        },
    ),
    (
        {
            "example_id": "08_18",
            "topic": "08_range_trading",
            "title": "H1 $12 box inside H4 — M5 edge-to-edge long",
            "setup": "Range nest | H4: wide balance | H1: tight $12 box 2648-2660 | M5: sharp trend from 2649→2659 (Grimes LTF trend in HTF range) | At 2659 H1 top: M15 bear wick forming — switch from long to fade short, NOT H4 breakout.",
            "decision": "Short scalp",
            "invalidation": "H1 closes above 2660 with volume expansion",
            "why": "LTF trend to H1 edge fade",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "08_18",
            "detector_type": "heuristic",
            "detector_name": "ltf_trend_to_range_edge",
            "input_signals": ["price", "bars"],
            "logic": "h1_subrange AND m5_trend_to_h1_edge AND m15_rejection",
            "thresholds": {"h1_box_usd": [10, 14], "tp_usd": [5, 7]},
            "output": "enum(valid)",
        },
        {
            "example_id": "08_18",
            "detector_output": "h1_edge_fade_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "M5 trend to H1 box top inside H4 balance — fade at 2659",
            "evidence_label": "moderate",
            "conviction_score": 0.78,
            "risk_control": "stop $3 above H1 top; TP $6",
        },
    ),
    (
        {
            "example_id": "08_19",
            "topic": "08_range_trading",
            "title": "H4 balance breakout fail — fade opposite edge",
            "setup": "Range nest | H4 balance 2645-2665 | H4[-1 attempt]: spike to 2666, close 2662 (failed) | H1[-2,-1]: bull trap then bear | M15[-1]: close inside balance | M5: reversal sequence | Fade per Dalton breakout failure → opposite edge target.",
            "decision": "Short scalp",
            "invalidation": "H4 re-attempt breaks 2665 with 2 H1 closes outside",
            "why": "Failed balance breakout",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "08_19",
            "detector_type": "heuristic",
            "detector_name": "h4_balance_breakout_fail",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_spike_outside AND h4_close_inside AND m15_confirm_inside",
            "thresholds": {"tp_usd": [8, 12], "target": "opposite_edge"},
            "output": "enum(valid)",
        },
        {
            "example_id": "08_19",
            "detector_output": "balance_breakout_fail_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "H4 failed breakout above 2665 — fade toward 2645 edge",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "stop $3 above spike 2666; TP $8 toward low edge",
        },
    ),
    (
        {
            "example_id": "08_20",
            "topic": "08_range_trading",
            "title": "H1 barbwire — fade failed M5 breakout",
            "setup": "Barbwire nest | H1: 4 overlapping M15 bars, doji cluster at 2653 | M5: barbwire 3-bar overlap | M5 breakout bar bull → immediate fail next bar | Do NOT buy breakout — fade failure back into barbwire. TP $5.",
            "decision": "Short scalp",
            "invalidation": "Clean M15 close outside barbwire with follow-through",
            "why": "Barbwire failure fade",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "08_20",
            "detector_type": "heuristic",
            "detector_name": "barbwire_breakout_fail",
            "input_signals": ["price", "bars"],
            "logic": "barbwire_detected AND m5_breakout_fail_1bar",
            "thresholds": {"tp_usd": [4, 6]},
            "output": "enum(valid)",
        },
        {
            "example_id": "08_20",
            "detector_output": "barbwire_fade_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "H1 barbwire — fade failed M5 bull breakout",
            "evidence_label": "moderate",
            "conviction_score": 0.77,
            "risk_control": "stop $3 above breakout high; TP $5",
        },
    ),
    # --- 09_reversal_trading: H1/H4 reversal with full nested candles ---
    (
        {
            "example_id": "09_30",
            "topic": "09_reversal_trading",
            "title": "H4 bear at resistance — nested H1 bulls fail",
            "setup": "Reversal nest | D1: bearish bias below pivot | H4(NY closed): bear body, test 2662 resistance | H1[-3,-2,-1]: bull bull bear — two H1 bulls into H4 resistance fail on H1[-1] bear engulf | M15[-1]: bear pin at 2662 | M5: two-bar bear | Short reversal TP $7.",
            "decision": "Reverse",
            "invalidation": "H4 closes above 2662 or H1 makes new high above 2664",
            "why": "H4 level + H1 failure",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_30",
            "detector_type": "heuristic",
            "detector_name": "h4_resistance_h1_failure",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_bear_at_resistance AND h1_bulls_fail AND m15_bear_pin",
            "thresholds": {"tp_usd": [6, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_30",
            "detector_output": "h4_h1_reversal_short_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "H4 bear at 2662, H1 bulls fail, M15/M5 bear confirm",
            "evidence_label": "strong",
            "conviction_score": 0.87,
            "risk_control": "stop $3 above 2662; TP $7",
        },
    ),
    (
        {
            "example_id": "09_31",
            "topic": "09_reversal_trading",
            "title": "H4 bull developing — 3 H1 bears into support (classic)",
            "setup": "Reversal nest — operator pattern | H4(NY): developing BULL, body +$11, not closed | H1[-3,-2,-1]: bear bear bear ($3,$4,$3) into H4 support 2648 | M15[-2]: wick reject 2648 | M15[-1]: bull engulf | M5: two-bar bull | Long to eat H1 bears, H4 may close bull. TP $8.",
            "decision": "Long scalp",
            "invalidation": "H1[-1] fails to bull engulf or 2648 breaks by >$4 on H1 close",
            "why": "Nested TF reversal at H4 level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_31",
            "detector_type": "heuristic",
            "detector_name": "nested_reversal_at_h4_level",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_developing_bull AND three_h1_bears_into_level AND m15_bull_engulf",
            "thresholds": {"h1_bear_sum_usd": [8, 12], "tp_usd": [6, 9]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_31",
            "detector_output": "nested_h4_h1_long_valid",
            "trade_decision": "Long scalp",
            "decision_conditions": "H4 bull developing, 3 H1 bears into 2648, M15 engulf — classic nested long",
            "evidence_label": "strong",
            "conviction_score": 0.88,
            "risk_control": "stop $3 below 2648; TP $8",
        },
    ),
    (
        {
            "example_id": "09_32",
            "topic": "09_reversal_trading",
            "title": "H4 last 30min $14 spike into D1 level — fade",
            "setup": "Endbar nest | H4(NY): 80% elapsed, developing high 2668 | Last 30min: M15[-2] bull $8, M15[-1] bull $6 into D1 resistance 2668 | M5[-1]: bear reversal at high | H1[-1]: long upper wick | Fade spike; wait M15 close confirm. TP $8.",
            "decision": "Short reversal",
            "invalidation": "H4 closes above 2668 with acceptance or M15 makes new high",
            "why": "H4 endbar moment at level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_32",
            "detector_type": "heuristic",
            "detector_name": "h4_ny_endbar_moment",
            "input_signals": ["price", "time", "bars", "levels"],
            "logic": "h4_last_30min_spike_usd>=12 AND at_d1_level AND m5_bear_reversal",
            "thresholds": {"spike_usd_min": 10, "tp_usd": [6, 9]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_32",
            "detector_output": "h4_endbar_spike_fade_valid",
            "trade_decision": "Short reversal",
            "decision_conditions": "H4 last 30min $14 spike to D1 2668, M5 bear reversal at high",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "stop $4 above 2668; TP $8",
        },
    ),
    (
        {
            "example_id": "09_33",
            "topic": "09_reversal_trading",
            "title": "H4 range top failed breakout — nested fade",
            "setup": "Range reversal nest | H4: range 2640-2660 | H4 developing high pierce 2661 | H1[-2,-1]: bull trap, bear close inside | M15[-3,-2,-1]: bull bull bear at top | M5: failed breakout sequence | 80% breakout fail rule. Short TP $7 to mid.",
            "decision": "Reverse",
            "invalidation": "H4 accepts above 2660 for 2 closed H1 bars",
            "why": "H4 range failed breakout",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_33",
            "detector_type": "heuristic",
            "detector_name": "h4_range_failed_breakout",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_range_top_pierce AND close_inside AND m15_bear_sequence",
            "thresholds": {"tp_usd": [6, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_33",
            "detector_output": "h4_range_fail_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "H4 range top false break — H1 bull trap, M15 bear sequence",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "risk_control": "stop $3 above 2661; TP $7",
        },
    ),
    (
        {
            "example_id": "09_34",
            "topic": "09_reversal_trading",
            "title": "H4 MTR — H1 failure test at old high",
            "setup": "MTR nest | H4: prior bull trend, trend line broken, retest old high 2660 | H1[-2]: poke 2659.5 (failure test — stops short) | H1[-1]: bear engulf | M15[-1]: lower high | M5: break H1 low | Major reversal sequence step 3 entry. TP $9 (range not full flip).",
            "decision": "Reverse",
            "invalidation": "H1 exceeds 2660.5 on retest or H4 reclaims bull trend line",
            "why": "MTR failure test",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "09_34",
            "detector_type": "heuristic",
            "detector_name": "h4_mtr_failure_test",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_trend_break AND h1_failure_test_short AND m15_lower_high",
            "thresholds": {"tp_usd": [7, 10]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_34",
            "detector_output": "h4_mtr_step3_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "H4 MTR: H1 failure test below 2660, bear engulf, M15 LH",
            "evidence_label": "moderate",
            "conviction_score": 0.8,
            "risk_control": "stop $4 above 2660; TP $9 toward H4 mid",
        },
    ),
    (
        {
            "example_id": "09_35",
            "topic": "09_reversal_trading",
            "title": "H1 bear break at H4 support — nested long",
            "setup": "H1 reversal nest | H4: bull, support 2646 | H1[-4..-1]: bear bear bear bull — three H1 bears $9 total into 2646 | M15[-2]: hammer | M15[-1]: bull close | M5: micro two-bar | H1 trend break attempt fails at H4 level → long. TP $7.",
            "decision": "Long scalp",
            "invalidation": "H1 closes below 2644 or H4 support lost on H4 close",
            "why": "H1 failure at H4 support",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_35",
            "detector_type": "heuristic",
            "detector_name": "h1_reversal_in_h4",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_support AND three_h1_bears AND h1_bull_reversal_bar",
            "thresholds": {"pullback_usd": [7, 11], "tp_usd": [5, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_35",
            "detector_output": "h1_at_h4_support_valid",
            "trade_decision": "Long scalp",
            "decision_conditions": "H1 bear sequence into H4 2646 fails, M15 hammer + bull close",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "stop $3 below 2646; TP $7",
        },
    ),
    (
        {
            "example_id": "09_36",
            "topic": "09_reversal_trading",
            "title": "H1 two-bar reversal at M15 level — full nest",
            "setup": "H1 nest | H4: neutral range | H1[-2]: bull extreme $6 body at 2655 | H1[-1]: bear close below H1[-2] low | Inside H1[-2]: M15[-6..-1] shows three M5 pushes up then M15 bear engulf | M5 entry on H1[-1] close. TP $6.",
            "decision": "Reverse",
            "invalidation": "H1[-1] reclaims above H1[-2] high",
            "why": "H1 two-bar + M15 fractal",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_36",
            "detector_type": "heuristic",
            "detector_name": "h1_two_bar_m15_fractal",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h1_two_bar_reversal AND m15_engulf_inside AND at_m15_level",
            "thresholds": {"tp_usd": [5, 7]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_36",
            "detector_output": "h1_two_bar_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "H1 two-bar reversal at 2655 with M15 bear engulf inside",
            "evidence_label": "strong",
            "conviction_score": 0.83,
            "risk_control": "stop $3 above H1[-2] high; TP $6",
        },
    ),
    (
        {
            "example_id": "09_37",
            "topic": "09_reversal_trading",
            "title": "London open H1 reversal — Asia juke then continue",
            "setup": "Session nest | Asia: closed +$5 bull | Pre-London 07-08 UTC: juke -$6 (fake) | London 08:00: H1[-1] bull engulf recovers juke | H4: developing bull | M15[-2,-1]: bear then bull at H1 support | M5: London open long trigger. TP $8 with Asia bias.",
            "decision": "Long scalp",
            "invalidation": "London H1 fails to engulf or price breaks Asia low by >$4",
            "why": "Session handoff reversal",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "09_37",
            "detector_type": "heuristic",
            "detector_name": "london_open_reversal_nested",
            "input_signals": ["price", "time", "bars", "session"],
            "logic": "asia_bull AND pre_london_juke AND h1_bull_engulf_london AND m15_confirm",
            "thresholds": {"juke_usd": [4, 8], "tp_usd": [6, 9]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_37",
            "detector_output": "london_nested_long_valid",
            "trade_decision": "Long scalp",
            "decision_conditions": "Asia bull, pre-London juke, H1 bull engulf London open, M15 confirm",
            "evidence_label": "moderate",
            "conviction_score": 0.79,
            "risk_control": "stop $3 below juke low; TP $8",
        },
    ),
    (
        {
            "example_id": "09_38",
            "topic": "09_reversal_trading",
            "title": "H1 'reversal' but H4 bull channel — deep pullback skip",
            "setup": "Discrimination nest | H4: strong bull channel, no trend line break | H1[-2,-1]: bear bear $8 | M15: break H1 swing low | Looks like H1 reversal but H4 counter-move never broke H4 trend line or MA → classify as deep pullback, not reversal. Skip short.",
            "decision": "Skip",
            "invalidation": "H4 trend line breaks with 2 H1 closes below",
            "why": "Deep pullback vs reversal",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_38",
            "detector_type": "heuristic",
            "detector_name": "h1_vs_h4_reversal_discrimination",
            "input_signals": ["price", "bars"],
            "logic": "h1_bear_break AND h4_trend_line_intact AND h4_ma_hold",
            "thresholds": {},
            "output": "enum(deep_pullback)",
        },
        {
            "example_id": "09_38",
            "detector_output": "h4_deep_pullback_not_reversal",
            "trade_decision": "Skip",
            "decision_conditions": "H1 bear break but H4 trend line unbroken — deep pullback not reversal",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "wait for H4 structure break or with-trend H1 long",
        },
    ),
    (
        {
            "example_id": "09_39",
            "topic": "09_reversal_trading",
            "title": "H1 BRG at H4 confluence — nested entry",
            "setup": "BRG nest | H4: resistance flip support 2652 | H1: break below 2652 ($7), retrace to 2652, go bar bull | M15[-3,-2,-1]: bear bear bull at level | M5[-1]: strong bull body away | H4+H1+M15 confluence. TP $7.",
            "decision": "Reversal entry",
            "invalidation": "Retrace dips below 2650 or go bar fails",
            "why": "BRG at HTF confluence",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_39",
            "detector_type": "heuristic",
            "detector_name": "h1_brg_h4_confluence",
            "input_signals": ["price", "bars", "levels"],
            "logic": "h4_level_flip AND h1_brg_sequence AND m15_bull_at_level",
            "thresholds": {"break_usd": [6, 10], "tp_usd": [6, 8]},
            "output": "enum(valid)",
        },
        {
            "example_id": "09_39",
            "detector_output": "h1_brg_h4_valid",
            "trade_decision": "Reversal entry",
            "decision_conditions": "H1 BRG at H4 2652 flip — M15 bull sequence, M5 go bar",
            "evidence_label": "strong",
            "conviction_score": 0.87,
            "risk_control": "stop $3 below 2652; TP $7",
        },
    ),
]


def main() -> None:
    s1_path = KNOW / "stage_01_principle_foundation.jsonl"
    s2_path = KNOW / "stage_02_structured_data.jsonl"
    s3_path = KNOW / "stage_03_detector_definitions.jsonl"
    s4_path = KNOW / "stage_04_decision_contract.jsonl"

    s1 = load_jsonl(s1_path)
    s2 = load_jsonl(s2_path)
    s3 = load_jsonl(s3_path)
    s4 = load_jsonl(s4_path)

    s1.extend(NEW_PRINCIPLES)

    new_ids = {e[0]["example_id"] for e in NEW_EXAMPLES}
    test_s2 = [r for r in s2 if r["example_id"] in TEST_IDS]
    train_s2 = [r for r in s2 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]
    new_s2 = [e[0] for e in NEW_EXAMPLES]

    test_s3 = [r for r in s3 if r["example_id"] in TEST_IDS]
    train_s3 = [r for r in s3 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]
    new_s3 = [e[1] for e in NEW_EXAMPLES]

    test_s4 = [r for r in s4 if r["example_id"] in TEST_IDS]
    train_s4 = [r for r in s4 if r["example_id"] not in TEST_IDS and r["example_id"] not in new_ids]
    new_s4 = [e[2] for e in NEW_EXAMPLES]

    s2_out = train_s2 + new_s2 + test_s2
    s3_out = train_s3 + new_s3 + test_s3
    s4_out = train_s4 + new_s4 + test_s4

    save_jsonl(s1_path, s1)
    save_jsonl(s2_path, s2_out)
    save_jsonl(s3_path, s3_out)
    save_jsonl(s4_path, s4_out)

    train_n = len(s2_out) - len(test_s2)
    print(f"Principles: {len(s1)} (+{len(NEW_PRINCIPLES)})")
    print(f"Examples total: {len(s2_out)} (+{len(NEW_EXAMPLES)})")
    print(f"Training: 0-{train_n - 1} ({train_n} examples)")
    print(f"Test: {train_n}-{len(s2_out) - 1} ({len(test_s2)} examples)")
    print("New IDs: 04_15-04_19, 07_14-07_18, 08_16-08_20, 09_30-09_39")


if __name__ == "__main__":
    main()
