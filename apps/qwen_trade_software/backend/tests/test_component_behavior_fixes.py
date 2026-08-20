from __future__ import annotations

import os
import inspect
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paper_executor  # noqa: E402
import reviewer  # noqa: E402


def test_executor_initializes_instrument_before_position_sizing():
    source = inspect.getsource(paper_executor.submit_single_position)
    assert source.index("instrument = instrument_for(args.symbol)") < source.index(
        "instrument.contract_value_per_price_unit_lot"
    )


def test_geometry_omission_does_not_trigger_slow_second_model_call():
    review = {
        "bias": "buy",
        "confidence": 68,
        "execution_plan": {"status": "ready", "reason": "mapped buy"},
    }
    assert reviewer.qwen_contract_correction_reason(review) is None


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
