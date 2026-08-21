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


def test_stop_is_monotonic_and_never_widens():
    decision = evaluate(side="sell", entry=100, current=97, peak=96,
                        broker_sl=97.5, atr=1, spread=0.1, point=0.01,
                        initial_risk=2)
    assert decision.armed
    assert decision.candidate_stop >= 96
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
