#!/usr/bin/env python3
"""Append XAUUSD micro-reversal examples ($5-$10 pullbacks) to stage JSONLs."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOW = ROOT / "knowledge"

TEST_IDS = {f"09_{i:02d}" for i in range(5, 15)}


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


NEW_PRINCIPLES = [
    {
        "principle_id": "P036",
        "topic": "09_reversal_trading",
        "principle_name": "XAUUSD Micro Reversal Range ($6-$10 Pullback)",
        "core_concept": "On XAUUSD spot, most actionable reversals at intraday levels occur after $6-$10 pullbacks from a local extreme — not $30+ swings. A $5-$9 follow-through is a full TP; treat smaller moves as noise unless at a major HTF level.",
        "foundational_rule": "Valid micro reversal: (1) closed pullback $6-$10 from local extreme into a known level, (2) rejection or two-bar reversal on M5/M15, (3) session context supports (London/NY overlap preferred). TP target $5-$9; stop $3-$4 beyond extreme.",
        "why_matters": "Operator TP cluster is $5-$9 on gold. Training the model on dollar-scaled micro reversals matches live execution; large-swing examples alone miss the bread-and-butter setup.",
        "evidence_strength": "strong",
        "applies_to_detectors": [
            "micro_pullback_reversal_xau",
            "two_bar_micro_reversal_xau",
            "range_edge_fade_xau",
        ],
    },
    {
        "principle_id": "P037",
        "topic": "09_reversal_trading",
        "principle_name": "Gold Range Scalp: $10-$15 Box, $5-$7 Fade",
        "core_concept": "When gold compresses into a $10-$15 session box, reversals at the box edge are scalps — not trend reversals. Fade the $8-$10 push into the edge; target mid-range or $5-$7 back inside the box.",
        "foundational_rule": "Range day: do not label edge fade as major reversal. Enter at edge rejection after $6+ push into boundary; TP $5-$7; stop $3 beyond edge. If box breaks with follow-through, stop fading.",
        "why_matters": "Most gold sessions are range-bound. Micro edge reversals inside a tight box are high-frequency operator setups distinct from MTR or session trend flips.",
        "evidence_strength": "moderate",
        "applies_to_detectors": ["range_edge_fade_xau", "failed_micro_breakout_xau"],
    },
]

# (stage_02, stage_03, stage_04) per example
NEW_EXAMPLES = [
    (
        {
            "example_id": "09_15",
            "topic": "09_reversal_trading",
            "title": "XAU $8 pullback to H1 support — micro long reversal",
            "setup": "XAUUSD ~2650: H1 uptrend intact. Price drops $8 from session high to prior H1 support. M15 prints two-bar reversal (bear exhaustion bar + bullish close). Pullback depth $8, level held.",
            "decision": "Long scalp",
            "invalidation": "Support breaks by >$4 or no two-bar reversal on M15 close",
            "why": "Micro reversal at level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_15",
            "detector_type": "heuristic",
            "detector_name": "micro_pullback_reversal_xau",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "pullback_usd in [6,10] AND htf_support_hold AND two_bar_reversal_m15",
            "thresholds": {"pullback_usd_min": 6, "pullback_usd_max": 10, "tp_usd": [5, 9]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_15",
            "detector_output": "micro_pullback_support_valid",
            "trade_decision": "Long scalp",
            "decision_conditions": "$8 pullback to H1 support with M15 two-bar reversal confirmed",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "risk_control": "stop $3 below reversal low; TP $7 toward session mid",
        },
    ),
    (
        {
            "example_id": "09_16",
            "topic": "09_reversal_trading",
            "title": "XAU $7 rally into M15 resistance — micro short",
            "setup": "XAUUSD range day: price rallies $7 into M15 resistance cluster. M5 rejection wick ($4 upper tail), close back below level. Push into level measured $7 from local low.",
            "decision": "Short reversal",
            "invalidation": "M15 closes above resistance or rally extends >$10 without rejection",
            "why": "Micro reversal at level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_16",
            "detector_type": "heuristic",
            "detector_name": "micro_pullback_reversal_xau",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "rally_usd in [6,10] AND m15_resistance_rejection AND wick_ratio >= 0.4",
            "thresholds": {"rally_usd_min": 6, "rally_usd_max": 10, "tp_usd": [5, 7]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_16",
            "detector_output": "resistance_rejection_valid",
            "trade_decision": "Short reversal",
            "decision_conditions": "$7 push into M15 resistance with wick rejection confirmed",
            "evidence_label": "strong",
            "conviction_score": 0.82,
            "risk_control": "stop $3 above rejection high; TP $6 inside range",
        },
    ),
    (
        {
            "example_id": "09_17",
            "topic": "09_reversal_trading",
            "title": "London high sweep $10 — failed breakout short",
            "setup": "London session: XAU sweeps prior high by ~$10 ($2658 vs $2648), tick volume spike, M5 closes back inside range within 2 bars. No follow-through above sweep.",
            "decision": "Reverse",
            "invalidation": "Price holds above sweep high for 3+ M5 closes",
            "why": "Failed breakout",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_17",
            "detector_type": "heuristic",
            "detector_name": "failed_micro_breakout_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "sweep_usd in [8,12] AND close_back_inside_within_2_bars",
            "thresholds": {"sweep_usd_min": 8, "sweep_usd_max": 12, "tp_usd": [6, 9]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_17",
            "detector_output": "failed_breakout_sweep_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "$10 sweep above London high with 2-bar close back inside",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "stop $4 above sweep high; TP $8 to range mid",
        },
    ),
    (
        {
            "example_id": "09_18",
            "topic": "09_reversal_trading",
            "title": "Uptrend $6 dip — failure test at M5 swing low",
            "setup": "Intraday bull on M15: price dips $6 to prior M5 swing low (failure test — stops $2 short of breaking low), M5 bullish engulfing. H1 trend still up.",
            "decision": "Long scalp",
            "invalidation": "M5 swing low breaks by >$3 or H1 trend line breaks",
            "why": "Failure test",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_18",
            "detector_type": "heuristic",
            "detector_name": "failure_test_broken_level",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "dip_usd in [5,8] AND retest_stops_short_of_low AND engulfing_m5",
            "thresholds": {"dip_usd_min": 5, "dip_usd_max": 8, "tp_usd": [5, 7]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_18",
            "detector_output": "failure_test_confirmed",
            "trade_decision": "Long scalp",
            "decision_conditions": "$6 failure test at M5 swing low with engulfing bar",
            "evidence_label": "strong",
            "conviction_score": 0.83,
            "risk_control": "stop $3 below test low; TP $7",
        },
    ),
    (
        {
            "example_id": "09_19",
            "topic": "09_reversal_trading",
            "title": "Gold $12 range box — fade $9 push to top",
            "setup": "Session box ~$12 wide (2644-2656). Price pushes $9 from mid to top edge. M5 doji + bear close at edge. Range day, not trend day.",
            "decision": "Short scalp",
            "invalidation": "Box breaks high with M15 close outside or push < $6",
            "why": "Range edge fade",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "09_19",
            "detector_type": "heuristic",
            "detector_name": "range_edge_fade_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "box_width_usd in [10,15] AND push_to_edge_usd >= 6 AND rejection_candle_m5",
            "thresholds": {"box_usd_max": 15, "tp_usd": [5, 7]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_19",
            "detector_output": "range_edge_rejection_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "$9 push to top of $12 gold box with M5 rejection",
            "evidence_label": "moderate",
            "conviction_score": 0.78,
            "risk_control": "stop $3 above box high; TP $6 to mid",
        },
    ),
    (
        {
            "example_id": "09_20",
            "topic": "09_reversal_trading",
            "title": "Shallow $5 pullback — skip (noise)",
            "setup": "XAU at M15 resistance: only $5 pullback from high, no rejection wick, overlapping M5 bars. Move too small for $5-$9 TP after spread.",
            "decision": "Skip",
            "invalidation": "Pullback deepens to $6+ with clear rejection structure",
            "why": "Insufficient move",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "09_20",
            "detector_type": "heuristic",
            "detector_name": "micro_pullback_reversal_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "pullback_usd < 6 OR no_rejection_structure",
            "thresholds": {"pullback_usd_min": 6, "min_tp_usd": 5},
            "output": "enum(invalid)",
        },
        {
            "example_id": "09_20",
            "detector_output": "pullback_too_shallow",
            "trade_decision": "Skip",
            "decision_conditions": "$5 pullback without rejection — below minimum $6 micro reversal threshold",
            "evidence_label": "moderate",
            "conviction_score": 0.72,
            "risk_control": "wait for $6-$10 pullback or clearer rejection",
        },
    ),
    (
        {
            "example_id": "09_21",
            "topic": "09_reversal_trading",
            "title": "M15 last 5min $9 spike into level — fade",
            "setup": "M15 bar developing: last 5 minutes accelerate $9 into H1 resistance (end-of-bar momentum). M1 shows exhaustion + bear reversal in final minute. HTF level intact.",
            "decision": "Short reversal",
            "invalidation": "M15 closes above level or spike < $7",
            "why": "Intra-bar moment at level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_21",
            "detector_type": "heuristic",
            "detector_name": "m15_endbar_spike_reversal_xau",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "final_5min_move_usd in [7,12] AND into_htf_level AND m1_reversal",
            "thresholds": {"spike_usd_min": 7, "tp_usd": [5, 8]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_21",
            "detector_output": "endbar_spike_rejection_valid",
            "trade_decision": "Short reversal",
            "decision_conditions": "M15 last 5min $9 spike into H1 resistance with M1 reversal",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "stop $3 above spike high; TP $7",
        },
    ),
    (
        {
            "example_id": "09_22",
            "topic": "09_reversal_trading",
            "title": "NY overlap $8 dip to broken resistance (support)",
            "setup": "NY overlap UTC: prior M15 resistance broken earlier, now support. Price dips $8 to retest, holds with bullish M5 pin bar. Session volume rising.",
            "decision": "Long scalp",
            "invalidation": "Retest breaks support by >$4 on M15 close",
            "why": "Role reversal retest",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_22",
            "detector_type": "heuristic",
            "detector_name": "role_reversal_retest_xau",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "retest_usd in [6,10] AND role_reversal_hold AND session_ny_overlap",
            "thresholds": {"retest_usd_min": 6, "tp_usd": [5, 7]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_22",
            "detector_output": "role_reversal_retest_valid",
            "trade_decision": "Long scalp",
            "decision_conditions": "$8 NY overlap dip to broken-resistance support with pin bar",
            "evidence_label": "strong",
            "conviction_score": 0.84,
            "risk_control": "stop $3 below retest low; TP $6",
        },
    ),
    (
        {
            "example_id": "09_23",
            "topic": "09_reversal_trading",
            "title": "Micro double top within $10 — short",
            "setup": "XAU oscillating: two highs within $2 at 2655 area, total range $10. Second high shows bear engulfing on M5. No HTF trend break — scalp only.",
            "decision": "Short scalp",
            "invalidation": "Second high exceeds first by >$3 with follow-through",
            "why": "Micro double top",
            "evidence": "moderate",
            "bucket": "A",
        },
        {
            "example_id": "09_23",
            "detector_type": "heuristic",
            "detector_name": "micro_double_top_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "two_highs_within_usd <= 3 AND range_usd <= 12 AND bear_engulf_m5",
            "thresholds": {"range_usd_max": 12, "tp_usd": [5, 6]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_23",
            "detector_output": "micro_double_top_valid",
            "trade_decision": "Short scalp",
            "decision_conditions": "micro double top within $10 range, M5 bear engulfing",
            "evidence_label": "moderate",
            "conviction_score": 0.76,
            "risk_control": "stop $3 above second high; TP $5",
        },
    ),
    (
        {
            "example_id": "09_24",
            "topic": "09_reversal_trading",
            "title": "H4 bull, H1 $9 bear pullback to H4 level — long reverse",
            "setup": "H4 candle bullish. Three H1 bear bars pull price $9 into strong H4 support/resistance flip zone. M15 two-bar reversal at level. Expect $6-$8 bounce eating H1 bear sequence.",
            "decision": "Long scalp",
            "invalidation": "H4 level breaks by >$4 or H1 bear sequence continues without reversal bar",
            "why": "Nested TF reversal at level",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_24",
            "detector_type": "heuristic",
            "detector_name": "nested_tf_reversal_at_level_xau",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "htf_bull AND ltf_pullback_usd in [7,12] AND h4_level_hold AND m15_two_bar_rev",
            "thresholds": {"pullback_usd_min": 7, "tp_usd": [6, 9]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_24",
            "detector_output": "nested_reversal_at_h4_level",
            "trade_decision": "Long scalp",
            "decision_conditions": "H4 bull context, H1 $9 pullback to H4 level, M15 reversal confirmed",
            "evidence_label": "strong",
            "conviction_score": 0.87,
            "risk_control": "stop $3 below level; TP $8 toward H1 mean",
        },
    ),
    (
        {
            "example_id": "09_25",
            "topic": "09_reversal_trading",
            "title": "Failed $6 micro breakout above range",
            "setup": "Tight $11 gold range. M5 breaks high by $6, single bar, closes back inside on next bar. Volume not sustained. Classic false breakout scalp.",
            "decision": "Reverse",
            "invalidation": "M15 accepts outside range with 2+ bullish closes",
            "why": "Failed breakout",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_25",
            "detector_type": "heuristic",
            "detector_name": "failed_micro_breakout_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "break_usd in [5,8] AND close_back_inside_1bar AND volume_not_sustained",
            "thresholds": {"break_usd_max": 8, "tp_usd": [5, 6]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_25",
            "detector_output": "failed_micro_breakout_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "$6 false breakout above range, close back inside next M5",
            "evidence_label": "strong",
            "conviction_score": 0.81,
            "risk_control": "stop $3 above breakout high; TP $5",
        },
    ),
    (
        {
            "example_id": "09_26",
            "topic": "09_reversal_trading",
            "title": "Two-bar reversal after $10 session push — London",
            "setup": "London open: XAU pushes $10 to session high in 15 minutes. M5 extreme bull bar + bear reversal bar (two-bar pattern). High volume on first bar, drop on second.",
            "decision": "Reverse",
            "invalidation": "Third M5 bar makes new high above extreme bar",
            "why": "Two-bar pattern",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_26",
            "detector_type": "heuristic",
            "detector_name": "two_bar_micro_reversal_xau",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "push_usd in [8,12] AND two_bar_reversal_m5 AND session_london",
            "thresholds": {"push_usd_min": 8, "tp_usd": [6, 8]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_26",
            "detector_output": "two_bar_reversal_valid",
            "trade_decision": "Reverse",
            "decision_conditions": "$10 London push + M5 two-bar reversal at session high",
            "evidence_label": "strong",
            "conviction_score": 0.83,
            "risk_control": "stop $3 above extreme bar; TP $7",
        },
    ),
    (
        {
            "example_id": "09_27",
            "topic": "09_reversal_trading",
            "title": "$9 bounce rejection at old trend high",
            "setup": "Bear trend break on M15 earlier. Price bounces $9 back toward old trend high, M5 sharp rejection (long upper wick), fails to exceed prior high by >$2.",
            "decision": "Reversal confirmation",
            "invalidation": "Bounce exceeds old high by >$4 or no rejection wick",
            "why": "Bounce rejection",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_27",
            "detector_type": "heuristic",
            "detector_name": "bounce_rejection_old_trend",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "bounce_usd in [7,11] AND rejection_wick AND fails_new_extreme",
            "thresholds": {"bounce_usd_min": 7, "tp_usd": [5, 7]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_27",
            "detector_output": "bounce_rejection_confirmed",
            "trade_decision": "Reversal confirmation",
            "decision_conditions": "$9 bounce into old trend high rejected on M5",
            "evidence_label": "strong",
            "conviction_score": 0.85,
            "risk_control": "add short; stop $3 above bounce high; TP $6",
        },
    ),
    (
        {
            "example_id": "09_28",
            "topic": "09_reversal_trading",
            "title": "$11 deep pullback after micro reversal — wait",
            "setup": "Micro long reversal triggered at $7 dip, but counter-move retraces $11 (>50% of reversal leg). M5 bear sequence intact. Risk original trend resuming.",
            "decision": "Skip",
            "invalidation": "Pullback stalls under 50% with bullish M5 close",
            "why": "Deep pullback veto",
            "evidence": "moderate",
            "bucket": "B",
        },
        {
            "example_id": "09_28",
            "detector_type": "heuristic",
            "detector_name": "deep_pullback_discrimination",
            "input_signals": ["price", "volume", "time", "bars"],
            "logic": "post_reversal_pullback_pct > 0.50 AND pullback_usd > 10",
            "thresholds": {"pullback_pct_max": 0.5, "pullback_usd_warn": 10},
            "output": "enum(invalid)",
        },
        {
            "example_id": "09_28",
            "detector_output": "deep_pullback_risk",
            "trade_decision": "Skip",
            "decision_conditions": "$11 pullback >50% after micro reversal — continuation risk too high",
            "evidence_label": "moderate",
            "conviction_score": 0.68,
            "risk_control": "do not add; wait for new structure or failure test",
        },
    ),
    (
        {
            "example_id": "09_29",
            "topic": "09_reversal_trading",
            "title": "BRG at level after $8 break-retrace — long",
            "setup": "M15 swing high broken ($8 move), price retraces to break level within $2, M5 'go' bar bullish away from level. BRG sequence complete at H1 support confluence.",
            "decision": "Reversal entry",
            "invalidation": "Retrace exceeds break level by >$3 or go bar fails",
            "why": "BRG entry",
            "evidence": "strong",
            "bucket": "A",
        },
        {
            "example_id": "09_29",
            "detector_type": "heuristic",
            "detector_name": "break_retrace_go_sequence",
            "input_signals": ["price", "volume", "time", "bars", "levels"],
            "logic": "break_usd in [6,10] AND retrace_to_level AND go_bar_m5",
            "thresholds": {"break_usd_min": 6, "retrace_tolerance_usd": 2, "tp_usd": [6, 8]},
            "output": "enum(valid, invalid)",
        },
        {
            "example_id": "09_29",
            "detector_output": "brg_sequence_valid",
            "trade_decision": "Reversal entry",
            "decision_conditions": "$8 break + retrace to level + M5 go bar confirmed",
            "evidence_label": "strong",
            "conviction_score": 0.86,
            "risk_control": "stop $3 below retrace low; TP $7",
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

    test_s2 = [r for r in s2 if r["example_id"] in TEST_IDS]
    train_s2 = [r for r in s2 if r["example_id"] not in TEST_IDS]
    new_s2 = [e[0] for e in NEW_EXAMPLES]

    test_s3 = [r for r in s3 if r["example_id"] in TEST_IDS]
    train_s3 = [r for r in s3 if r["example_id"] not in TEST_IDS]
    new_s3 = [e[1] for e in NEW_EXAMPLES]

    test_s4 = [r for r in s4 if r["example_id"] in TEST_IDS]
    train_s4 = [r for r in s4 if r["example_id"] not in TEST_IDS]
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
    print(f"New micro-reversal IDs: 09_15 .. 09_29")


if __name__ == "__main__":
    main()
