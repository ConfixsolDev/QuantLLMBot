"""Phase 2 management: Qwen first; safety + timeout guards."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trade_manager as tm  # noqa: E402


def _base_facts(**overrides):
    facts = {
        "latest_completed_m1": "candle:M1:2",
        "latest_completed_m5": "candle:M5:1",
        "completed_candles": [
            {
                "evidence_id": "candle:M1:2",
                "timeframe": "M1",
                "open": 4395.2,
                "high": 4395.4,
                "low": 4392.9,
                "close": 4393.1,
                "direction": "down",
            },
            {
                "evidence_id": "candle:M5:1",
                "timeframe": "M5",
                "open": 4395.0,
                "high": 4395.6,
                "low": 4392.8,
                "close": 4393.2,
                "direction": "down",
            },
        ],
        "level_references": {
            "planned_target": {"level_id": "M15_PREVIOUS_LOW", "price": 4387.0},
            "planned_invalidation": {"level_id": "M15_PREVIOUS_HIGH", "price": 4400.0},
            "current:M5_PREVIOUS_LOW": {"level_id": "M5_PREVIOUS_LOW", "price": 4393.0},
            "current:M15_PREVIOUS_LOW": {"level_id": "M15_PREVIOUS_LOW", "price": 4387.0},
        },
        "trade_path": {
            "peak_price": 4392.8,
            "reached_favorable_level_refs": ["current:M5_PREVIOUS_LOW"],
        },
        "position": {"side": "sell", "entry": 4395.5},
        "entry_thesis": {"structure_timeframe": "M15", "side": "sell"},
        "regime_context": {"regime_hint": "range"},
    }
    facts.update(overrides)
    return facts


def test_safety_guard_closes_only_on_invalidation():
    facts = _base_facts()
    assert tm.safety_guard(facts) is None
    facts["completed_candles"][0]["close"] = 4401.0
    facts["completed_candles"][0]["high"] = 4401.2
    facts["completed_candles"][0]["direction"] = "up"
    facts["completed_candles"][1]["close"] = 4400.5
    facts["completed_candles"][1]["high"] = 4401.0
    facts["completed_candles"][1]["direction"] = "up"
    stop = tm.safety_guard(facts)
    assert stop is not None
    assert stop["confirmation_type"] == "thesis_invalidation_confirmed"


def test_scalp_guard_takes_m5_while_m1_favorable():
    facts = _base_facts()
    close = tm._scalp_guard(facts)
    assert close is not None
    assert close["decision_level_ref"] == "current:M5_PREVIOUS_LOW"
    assert "while M1 favorable" in close["summary"]


def test_rejection_guard_ignores_m5_on_m15_thesis():
    facts = _base_facts(regime_context={"regime_hint": "trend"})
    facts["completed_candles"][0]["direction"] = "up"
    facts["completed_candles"][0]["close"] = 4396.0
    assert tm._rejection_guard(facts) is None


def test_timeout_guard_routes_range_to_scalp():
    facts = _base_facts()
    close = tm.timeout_guard(facts)
    assert close is not None
    assert "Range scalp" in close["summary"]


def test_qwen_range_close_not_blocked_while_favorable():
    facts = _base_facts()
    decision = {
        "action": "close",
        "thesis_state": "target_response",
        "decision_level_ref": "current:M5_PREVIOUS_LOW",
        "next_target_ref": None,
        "confirmation_type": "target_rejection_confirmed",
        "confirmation_evidence_ids": ["candle:M1:2", "candle:M5:1"],
        "close_confirmed": True,
        "summary": "Scalp at M5 while M1 still with the sell.",
    }
    parsed, failures = tm.validate_management_decision(decision, facts)
    assert failures == []
    assert parsed["action"] == "close"


def test_range_label_does_not_stale_a_sell_invalidation_close():
    """Replay the 2026-08-19 failure: sell above stop must close immediately."""
    facts = _base_facts()
    decision = {
        "action": "close",
        "decision_level_ref": "planned_invalidation",
    }
    assert tm.decision_is_currently_applicable(decision, facts, 4401.0)
    assert not tm.decision_is_currently_applicable(decision, facts, 4399.0)


def test_range_label_does_not_stale_a_buy_invalidation_close():
    facts = _base_facts(position={"side": "buy", "entry": 4401.0})
    decision = {
        "action": "close",
        "decision_level_ref": "planned_invalidation",
    }
    assert tm.decision_is_currently_applicable(decision, facts, 4399.0)
    assert not tm.decision_is_currently_applicable(decision, facts, 4401.0)


def test_hold_is_not_forced_by_old_bounce_back_guard():
    facts = _base_facts(regime_context={"regime_hint": "trend"})
    hold = {
        "action": "hold",
        "thesis_state": "valid",
        "decision_level_ref": None,
        "next_target_ref": None,
        "confirmation_type": "none",
        "confirmation_evidence_ids": [],
        "close_confirmed": False,
        "summary": "Hold M5 noise in trend.",
    }
    _, failures = tm.validate_management_decision(hold, facts)
    assert "management:confirmed_close_ignored" not in failures


def test_facts_include_regime_context():
    facts = tm.build_management_facts(
        {
            "ticket": 1,
            "symbol": "XAUUSDr",
            "side": "sell",
            "volume": 0.1,
            "open_price": 4395.5,
            "current_price": 4394.0,
            "profit": 15.0,
            "stop_loss": 4399.0,
        },
        {
            "side": "sell",
            "entry_low": 4395.0,
            "entry_high": 4396.0,
            "stop_level_id": "M15_PREVIOUS_HIGH",
            "stop_loss": 4399.0,
            "target_level_id": "M5_PREVIOUS_LOW",
            "take_profit": 4393.0,
            "reason": "range fade",
            "structure_timeframe": "M15",
        },
        {"M5_PREVIOUS_LOW": 4393.0},
        {"M1": [], "M5": []},
        regime_context={"regime_hint": "range", "regime_transition": False},
    )
    assert facts["regime_context"]["regime_hint"] == "range"
    assert facts["entry_thesis"]["structure_timeframe"] == "M15"


def test_self_test_still_passes():
    result = tm.self_test()
    assert result["passed"], result["failures"]
