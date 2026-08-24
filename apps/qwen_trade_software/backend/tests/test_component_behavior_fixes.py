from __future__ import annotations

import os
import inspect
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paper_executor  # noqa: E402
import reviewer  # noqa: E402


def test_executor_initializes_instrument_before_position_sizing():
    source = inspect.getsource(paper_executor.submit_single_position)
    assert source.index("instrument = instrument_for(args.symbol)") < source.index(
        "instrument.contract_value_per_price_unit_lot"
    )


def test_geometry_omission_triggers_one_bounded_contract_correction():
    review = {
        "bias": "buy",
        "confidence": 68,
        "execution_plan": {"status": "ready", "reason": "mapped buy"},
    }
    reason = reviewer.qwen_contract_correction_reason(review)
    assert reason.startswith("ready_missing_fields:")
    assert "stop_level_id" in reason
    assert "target_level_id" in reason


def test_entry_schema_uses_flat_top_level_required_plan_contract():
    cache = {
        "epochs": {"minute": "m1"},
        "known_evidence_ids": ["m1"],
    }
    decision_levels = {
        "M1": [{"id": "M1_LEVEL", "price": 100.0}],
    }
    schema = reviewer.entry_decision_schema(cache, decision_levels)
    assert "execution_plan" not in schema["properties"]
    for field in (
        "plan_status", "plan_side", "entry_low_id", "entry_high_id",
        "stop_level_id", "target_level_id", "target_mode", "volume_each",
        "plan_reason", "data_requests",
    ):
        assert field in schema["required"]
    assert "M1_LEVEL" in schema["properties"]["stop_level_id"]["enum"]


def test_flat_wire_ready_is_adapted_to_internal_execution_plan():
    wire = {
        "bias": "sell", "confidence": 68, "summary": "confirmed rejection",
        "acknowledged_epochs": {"minute": "m1"}, "evidence_ids": ["m1"],
        "plan_status": "ready", "plan_side": "sell",
        "entry_low_id": "M1_SUPPORT", "entry_high_id": "M1_RESISTANCE",
        "stop_level_id": "M15_STOP", "target_level_id": "M15_TARGET",
        "target_mode": "scalp", "volume_each": 0.5,
        "plan_reason": "entry_condition_met", "data_requests": [],
    }
    review = reviewer.decode_entry_response(json.dumps(wire))
    assert review["execution_plan"] == {
        "status": "ready", "reason": "entry_condition_met", "side": "sell",
        "entry_low_id": "M1_SUPPORT", "entry_high_id": "M1_RESISTANCE",
        "stop_level_id": "M15_STOP", "target_level_id": "M15_TARGET",
        "target_mode": "scalp", "volume_each": 0.5,
    }
    assert "plan_status" not in review


def test_flat_wire_wait_removes_non_applicable_sentinels():
    none = reviewer.entry_contract.NONE
    wire = {
        "bias": "wait", "confidence": 40, "summary": "trigger incomplete",
        "acknowledged_epochs": {"minute": "m1"}, "evidence_ids": ["m1"],
        "plan_status": "wait", "plan_side": none,
        "entry_low_id": none, "entry_high_id": none,
        "stop_level_id": none, "target_level_id": none,
        "target_mode": none, "volume_each": 0.5,
        "plan_reason": "missing_trigger", "data_requests": [],
    }
    review = reviewer.decode_entry_response(json.dumps(wire))
    assert review["execution_plan"] == {
        "status": "wait", "reason": "missing_trigger",
    }


def test_today_malformed_ready_response_reports_both_contract_faults():
    review = {
        "bias": "sell",
        "confidence": 68,
        "execution_plan": {
            "status": "ready",
            "side": "sell",
            "entry_low_id": "M15_PREVIOUS_HIGH",
            "entry_high_id": "M15_PREVIOUS_HIGH",
            "reason": "missing_trigger",
        },
    }
    reason = reviewer.qwen_contract_correction_reason(review)
    assert "stop_level_id" in reason
    assert "target_level_id" in reason
    assert "ready_contradicts_own_reason" in reason


def test_uncorrected_contract_is_not_mislabeled_as_cache_failure():
    reason = reviewer.wait_reason_for(
        None,
        {"execution_plan": {"status": "ready"}},
        "ready_missing_fields:stop_level_id,target_level_id",
    )
    assert "Qwen returned ready" in reason
    assert "Cache provenance" not in reason


def _normalization_inputs():
    levels = {
        "M1": [
            {"id": "M1_SUPPORT", "price": 100.0},
            {"id": "M1_RESISTANCE", "price": 104.0},
        ],
        "M15": [
            {"id": "M15_STOP", "price": 108.0},
            {"id": "M15_TARGET", "price": 96.0},
        ],
    }
    snapshot = {
        "decision_levels": levels, "price": 103.0,
        "qwen_evidence_ids": ["m1"],
    }
    cache = {
        "minute": {"quote": {"bid": 103.0, "ask": 103.1}},
        "epochs": {"minute": "m1"},
        "model_digest": "digest",
        "decision_time_utc": "2026-08-24T08:00:00Z",
    }
    return snapshot, cache


def test_incomplete_ready_plan_fails_closed_without_cache_geometry():
    snapshot, cache = _normalization_inputs()
    plan = reviewer.normalize_execution_plan(
        {"status": "ready", "side": "sell", "entry_high_id": "M1_SUPPORT"},
        snapshot, cache, bias="sell", confidence=68,
    )
    assert plan["status"] == "wait"
    assert plan["reason_code"] == "entry:ready_missing_geometry"


def test_sell_anchor_requires_confirmed_resistance_response():
    snapshot, cache = _normalization_inputs()
    value = {
        "status": "ready", "side": "sell",
        "entry_low_id": "M1_SUPPORT", "entry_high_id": "M1_RESISTANCE",
        "stop_level_id": "M15_STOP", "target_level_id": "M15_TARGET",
    }
    plan = reviewer.normalize_execution_plan(
        value, snapshot, cache, bias="sell", confidence=68,
        structural_responses=[{
            "level_id": "M1_RESISTANCE", "confirmed": True,
            "zone_side": "support", "direction": "buy",
        }],
        active_idea_context={
            "watching_zone": "M1_RESISTANCE", "watching_side": "sell",
        },
    )
    assert plan["status"] == "wait"
    assert plan["reason_code"] == "entry:anchor_response_mismatch"


def test_sell_anchor_preserves_qwen_resistance_zone():
    snapshot, cache = _normalization_inputs()
    value = {
        "status": "ready", "side": "sell",
        "entry_low_id": "M1_SUPPORT", "entry_high_id": "M1_RESISTANCE",
        "stop_level_id": "M15_STOP", "target_level_id": "M15_TARGET",
    }
    plan = reviewer.normalize_execution_plan(
        value, snapshot, cache, bias="sell", confidence=68,
        structural_responses=[{
            "level_id": "M1_RESISTANCE", "confirmed": True,
            "zone_side": "resistance", "direction": "sell",
        }],
        active_idea_context={
            "watching_zone": "M1_RESISTANCE", "watching_side": "sell",
        },
    )
    assert plan["status"] == "ready"
    assert plan["entry_high_id"] == "M1_RESISTANCE"
    assert plan["geometry_source"] == "qwen_sr_zone_fixed_3_5"


def test_live_geometry_defaults_are_fail_closed():
    assert paper_executor.SKIP_ON_GEOMETRY_REJECTION == (
        paper_executor._GEOMETRY_SKIP_CANDIDATES
    )
    assert paper_executor.ENFORCE_HTF_MICRO_BRACKET is True


def test_breakout_promotion_requires_m5_and_m15_closed_alignment(tmp_path, monkeypatch):
    import qualified_levels

    monkeypatch.setattr(
        qualified_levels, "QUALIFIED_LEVELS_PATH", tmp_path / "qualified.json"
    )
    review = {
        "execution_plan": {
            "status": "ready", "side": "buy",
            "entry_low": 109.0, "entry_high": 111.0,
            "optimal_entry_price": 109.0,
        }
    }
    facts = {
        "regime_context": {
            "regime_hint": "trend", "regime_state": "trending_range",
            "current_price": 111.0, "range_support": 100.0,
            "range_resistance": 110.0, "trend_direction": "buy",
        },
        "confirmation_context": {
            "m5": {"choch": {"direction": "bullish"}},
            "m15": {"bos": {"direction": "bullish"}},
        },
    }
    reviewer._stamp_regime_target_mode(review, facts)
    assert review["execution_plan"]["status"] == "ready"
    assert review["execution_plan"]["regime_state"] == "breakout_confirmed"


def test_directional_breakout_blocks_opposite_plan(tmp_path, monkeypatch):
    import qualified_levels

    monkeypatch.setattr(
        qualified_levels, "QUALIFIED_LEVELS_PATH", tmp_path / "qualified.json"
    )
    review = {"execution_plan": {"status": "ready", "side": "sell"}}
    facts = {
        "regime_context": {
            "regime_state": "breakout_confirmed", "trend_direction": "buy"
        }
    }
    reviewer._stamp_regime_target_mode(review, facts)
    assert review["execution_plan"]["status"] == "wait"
    assert "opposes_breakout_confirmed_buy" in review["execution_plan"]["reason"]


def test_valid_m1_failure_can_fill_in_favorable_half_of_zone(monkeypatch):
    monkeypatch.setattr(
        paper_executor.live_mapped_levels,
        "m1_failure_for_entry",
        lambda *args: True,
    )
    ready, reason = paper_executor.entry_fill_ready(
        "buy", 101.8, 100.0, 104.0, 97.0,
        {"open": 101, "high": 102, "low": 100, "close": 101},
        optimal_entry_price=100.0,
    )
    assert ready is True
    assert reason == "armed_m1_failure_at_optimal"


def test_qwen_snapshot_stays_fresh_inside_atr_drift_allowance():
    facts = {
        "quote": {"bid": 4400.0},
        "closed_m1": {"id": "m1-old"},
        "regime_context": {"atr_m1_51": 4.0},
    }
    cache = {
        "minute": {
            "quote": {"bid": 4402.5},
            "closed_m1": {"id": "m1-new"},
        }
    }
    result = reviewer.decision_snapshot_freshness(facts, cache)
    assert result["fresh"] is True
    assert result["maximum_drift"] == 3.0
    assert result["closed_m1_changed"] is True


def test_qwen_snapshot_recovers_after_material_price_drift():
    facts = {
        "quote": {"bid": 4400.0},
        "closed_m1": {"id": "m1-old"},
        "regime_context": {"atr_m1_51": 4.0},
    }
    cache = {
        "minute": {
            "quote": {"bid": 4403.1},
            "closed_m1": {"id": "m1-new"},
        }
    }
    result = reviewer.decision_snapshot_freshness(facts, cache)
    assert result["fresh"] is False
    assert result["reason"] == "decision_snapshot_price_drift"
