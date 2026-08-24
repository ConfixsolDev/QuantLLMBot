from types import SimpleNamespace

from profit_protection import _partial_volume
from profit_protection_policy import evaluate
from trade_manager import validate_management_decision


def test_sell_arms_and_locks_profit_like_observed_trade():
    decision = evaluate(side="sell", entry=4340.014, current=4336.944,
                        peak=4336.944, broker_sl=4344.667, atr=2.2,
                        spread=0.09, point=0.001)
    assert decision.armed
    assert decision.should_modify
    assert 4338.6 < decision.candidate_stop < 4338.8
    assert decision.locked_move > 1.2


def test_does_not_arm_inside_normal_noise():
    decision = evaluate(side="buy", entry=100, current=100.4, peak=100.4,
                        broker_sl=98, atr=1, spread=0.1, point=0.01)
    assert not decision.armed
    assert not decision.should_modify


def test_temporal_window_secures_break_even_without_normal_arm_threshold():
    decision = evaluate(side="buy", entry=100, current=100.4, peak=100.4,
                        broker_sl=98, atr=1, spread=0.1, point=0.01,
                        force_break_even=True)
    assert decision.armed
    assert decision.should_modify
    assert decision.candidate_stop >= 100.3


def test_state_does_not_regress_after_broker_has_break_even_stop():
    decision = evaluate(side="buy", entry=100, current=100.1, peak=100.4,
                        broker_sl=100.3, atr=1, spread=0.1, point=0.01,
                        initial_risk=2, force_break_even=True)
    assert decision.armed
    assert decision.state == "costs_secured"
    assert not decision.should_modify


def test_stop_is_monotonic_and_never_widens():
    decision = evaluate(side="sell", entry=100, current=99, peak=98.5,
                        broker_sl=97.5, atr=1, spread=0.1, point=0.01,
                        initial_risk=2)
    assert decision.armed
    assert decision.candidate_stop >= 98.5
    assert not decision.should_modify


def test_crossed_candidate_requests_immediate_close():
    decision = evaluate(side="sell", entry=100, current=99, peak=96,
                        broker_sl=104, atr=1, spread=0.1, point=0.01)
    assert decision.armed
    assert decision.crossed
    assert decision.should_modify


def test_buy_side_is_symmetric():
    decision = evaluate(side="buy", entry=100, current=104, peak=104,
                        broker_sl=96, atr=1, spread=0.1, point=0.01)
    assert decision.armed
    assert decision.candidate_stop > 100
    assert decision.should_modify


def test_front_quarter_starts_only_at_one_and_half_frozen_atr():
    before = evaluate(side="buy", entry=100, current=101.49, peak=101.49,
                      broker_sl=98, atr=1, spread=0.1, point=0.01,
                      initial_risk=2)
    active = evaluate(side="buy", entry=100, current=101.5, peak=101.5,
                      broker_sl=98, atr=1, spread=0.1, point=0.01,
                      initial_risk=2)
    assert not before.front_layer_active
    assert before.front_candidate_stop is None
    assert active.front_layer_active
    assert active.front_candidate_stop == 101.25
    assert active.wide_candidate_stop is None


def test_front_quarter_advances_in_quarter_atr_steps():
    first = evaluate(side="sell", entry=100, current=98.3, peak=98.3,
                     broker_sl=102, atr=1, spread=0.1, point=0.01,
                     initial_risk=2)
    second = evaluate(side="sell", entry=100, current=98.24, peak=98.24,
                      broker_sl=102, atr=1, spread=0.1, point=0.01,
                      initial_risk=2)
    assert first.ladder_step_atr == 1.5
    assert first.front_candidate_stop == 98.75
    assert second.ladder_step_atr == 1.75
    assert second.front_candidate_stop == 98.5


def test_wide_remainder_joins_ladder_at_two_atr_not_before():
    before = evaluate(side="buy", entry=100, current=101.99, peak=101.99,
                      broker_sl=98, atr=1, spread=0.1, point=0.01,
                      initial_risk=2)
    active = evaluate(side="buy", entry=100, current=102, peak=102,
                      broker_sl=98, atr=1, spread=0.1, point=0.01,
                      initial_risk=2)
    assert before.wide_candidate_stop is None
    assert active.wide_candidate_stop == 101.5
    assert active.candidate_stop >= active.wide_candidate_stop


def test_front_close_volume_is_broker_valid_and_never_consumes_remainder():
    info = SimpleNamespace(volume_step=0.01, volume_min=0.01)
    assert _partial_volume(0.35, 0.35, info) == 0.08
    assert _partial_volume(0.03, 0.03, info) == 0.0


def _target_management_facts(target_price=108.0):
    return {
        "position": {
            "side": "buy", "entry": 100.0, "current": 105.0,
            "gross_pnl": 50.0, "broker_target": 110.0,
        },
        "profit_protection": {"armed": True},
        "latest_completed_m1": "candle:M1:2",
        "latest_completed_m5": "candle:M5:1",
        "completed_candles": [
            {"evidence_id": "candle:M1:2", "timeframe": "M1", "open": 106,
             "high": 106.2, "low": 104.8, "close": 105, "direction": "down"},
            {"evidence_id": "candle:M5:1", "timeframe": "M5", "open": 104,
             "high": 106.2, "low": 103.5, "close": 105, "direction": "up"},
        ],
        "level_references": {
            "planned_target": {"price": 110.0},
            "current:M5_PREVIOUS_HIGH": {"price": target_price},
        },
        "trade_path": {"reached_favorable_level_refs": []},
        "regime_context": {},
    }


def test_qwen_may_reduce_tp_to_named_level_still_ahead_of_price():
    facts = _target_management_facts()
    decision = {
        "action": "protect", "thesis_state": "weakening",
        "decision_level_ref": None,
        "next_target_ref": "current:M5_PREVIOUS_HIGH",
        "confirmation_type": "target_deterioration_confirmed",
        "confirmation_evidence_ids": ["candle:M1:2"],
        "close_confirmed": False,
        "summary": "Latest completed M1 weakened; use nearer named target.",
    }
    normalized, failures = validate_management_decision(decision, facts)
    assert failures == []
    assert normalized["action"] == "protect"


def test_qwen_cannot_reduce_tp_to_level_already_through_price():
    facts = _target_management_facts(target_price=104.5)
    decision = {
        "action": "protect", "thesis_state": "weakening",
        "decision_level_ref": None,
        "next_target_ref": "current:M5_PREVIOUS_HIGH",
        "confirmation_type": "target_deterioration_confirmed",
        "confirmation_evidence_ids": ["candle:M1:2"],
        "close_confirmed": False, "summary": "Target is no longer realistic.",
    }
    normalized, failures = validate_management_decision(decision, facts)
    assert "management:reduced_target_not_ahead" in failures
    assert normalized["action"] == "hold"


def test_qwen_can_harvest_whole_profit_once_protection_is_armed():
    facts = {
        "position": {"side": "sell", "entry": 100.0, "gross_pnl": 25.0},
        "profit_protection": {"armed": True},
        "latest_completed_m1": "candle:M1:2",
        "latest_completed_m5": "candle:M5:1",
        "completed_candles": [
            {"evidence_id": "candle:M1:2", "timeframe": "M1", "open": 98,
             "high": 99, "low": 97, "close": 98, "direction": "down"},
            {"evidence_id": "candle:M5:1", "timeframe": "M5", "open": 99,
             "high": 100, "low": 97, "close": 98, "direction": "down"},
        ],
        "level_references": {
            "profit_protection_floor": {"price": 99.0},
            "planned_invalidation": {"price": 104.0},
        },
        "trade_path": {"reached_favorable_level_refs": []},
        "regime_context": {},
    }
    decision = {
        "action": "close", "thesis_state": "target_response",
        "decision_level_ref": "profit_protection_floor", "next_target_ref": None,
        "confirmation_type": "protected_profit_exit",
        "confirmation_evidence_ids": ["candle:M1:2"],
        "close_confirmed": True, "summary": "Momentum quality deteriorated; bank protected profit.",
    }
    normalized, failures = validate_management_decision(decision, facts)
    assert failures == []
    assert normalized["action"] == "close"


def test_qwen_cannot_use_profit_exit_when_not_armed():
    facts = {
        "position": {"side": "sell", "entry": 100.0, "gross_pnl": 25.0},
        "profit_protection": {"armed": False},
        "latest_completed_m1": "candle:M1:2", "latest_completed_m5": None,
        "completed_candles": [{"evidence_id": "candle:M1:2", "timeframe": "M1",
                               "open": 98, "high": 99, "low": 97, "close": 98,
                               "direction": "down"}],
        "level_references": {"profit_protection_floor": {"price": 99.0}},
        "trade_path": {"reached_favorable_level_refs": []}, "regime_context": {},
    }
    decision = {
        "action": "close", "thesis_state": "target_response",
        "decision_level_ref": "profit_protection_floor", "next_target_ref": None,
        "confirmation_type": "protected_profit_exit",
        "confirmation_evidence_ids": ["candle:M1:2"], "close_confirmed": True,
        "summary": "Take profit.",
    }
    normalized, failures = validate_management_decision(decision, facts)
    assert failures
    assert normalized["action"] == "hold"
