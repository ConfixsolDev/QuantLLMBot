from __future__ import annotations

import pytest

from strategy_contract import StrategyDefinition, TradeCandidate
from strategy_runtime import StrategyRuntimeState, replay_transitions, transition


def definition() -> StrategyDefinition:
    return StrategyDefinition("XAUUSDr", "XAUUSD_SCALP_V1", "1", 9001, "SCALP")


def candidate() -> TradeCandidate:
    return TradeCandidate("candidate-1", "XAUUSDr", definition(), "buy", "M1_probe_failure", "M15_support_1", "M15_support_1_fail", ("M15_resistance_1",), "2026-08-31T08:00:00Z", "2026-08-31T08:15:00Z", "state-hash")


def test_candidate_is_strategy_scoped_and_serializable():
    value = candidate().as_dict()
    assert value["strategy_id"] == "XAUUSD_SCALP_V1"
    assert value["magic_number"] == 9001
    assert value["direction"] == "buy"


def test_wait_cannot_become_an_execution_candidate():
    with pytest.raises(ValueError, match="buy or sell"):
        TradeCandidate("x", "XAUUSDr", definition(), "wait", "trigger", "zone", "invalid", ("target",), "2026-08-31T08:00:00Z", "2026-08-31T08:15:00Z", "hash")


def test_lifecycle_replay_is_deterministic_and_rejects_skips():
    c = candidate()
    state = transition(StrategyRuntimeState(c.strategy.strategy_id), "ELIGIBLE", at_utc="2026-08-31T08:00:00Z")
    state = transition(state, "WATCHING", at_utc="2026-08-31T08:01:00Z")
    state = transition(state, "ARMED", at_utc="2026-08-31T08:02:00Z")
    state = transition(state, "TRIGGERED", candidate=c, at_utc="2026-08-31T08:03:00Z")
    replay = replay_transitions(c.strategy.strategy_id, [{"state": "ELIGIBLE"}, {"state": "WATCHING"}, {"state": "ARMED"}, {"state": "TRIGGERED"}])
    assert state.state == replay.state == "TRIGGERED"
    with pytest.raises(ValueError, match="invalid strategy transition"):
        transition(state, "POSITION_ACTIVE")
