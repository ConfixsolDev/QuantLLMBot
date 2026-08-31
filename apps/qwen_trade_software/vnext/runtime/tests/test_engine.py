from datetime import datetime, timedelta, timezone

import pytest

from vnext.strategy.contracts import StrategyDefinition
from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine
from vnext.storage.ledger import InMemoryLedger
from vnext.strategy.definition import StrategySpec


def bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [Bar("XAUUSD", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i + 1), 10 + i, 12 + i, 9 + i, 11 + i, i + 1) for i in range(5)]


def spec():
    return StrategySpec(StrategyDefinition("XAUUSD", "SCALP_V1", "1", 1001, "SCALP"), trigger="reclaim", invalidation_policy="break", target_zone_policy="next")


def test_engine_composes_state_and_requires_approval_before_order():
    engine = VNextEngine(pair="XAUUSD", frontier=TimeFrontier.from_value("2026-01-01T00:05:00Z"))
    state = engine.compose_state(bars())
    result = engine.evaluate(state, spec())
    assert state.schema_version == "PAIR_MARKET_STATE_V1"
    assert len(state.mtf_relationships) == 6
    assert result.arbitration is None
    with pytest.raises(RuntimeError):
        engine.submit(result, order={"candidate_id": "c1"})


def test_engine_recovery_fails_closed_on_mismatch():
    result = VNextEngine.recover(broker_positions=[{"position_id": 1}], ledger_positions=[], broker_healthy=True, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert result.safe_to_resume is False


class FakeBroker:
    def __init__(self):
        self.orders = []

    def submit(self, order):
        self.orders.append(dict(order))
        return {"broker_order_id": "b1", "state": "SUBMITTED"}


def test_approved_candidate_passes_risk_then_broker_adapter():
    broker = FakeBroker()
    engine = VNextEngine(pair="XAUUSD", frontier=TimeFrontier.from_value("2026-01-01T00:05:00Z"), broker=broker)
    state = engine.compose_state(bars())
    result = engine.evaluate(
        state, spec(),
        response={"decision": "APPROVE", "candidate_id": "c1", "state_hash": state.state_hash},
        candidate_inputs={"candidate_id": "c1", "direction": "buy", "zone_id": "z1", "invalidation": "z1-low", "target_zone_ids": ("z2",)},
        risk_inputs={"account_equity": 10000, "risk_fraction": .01, "entry": 10, "stop": 9, "point_value": 1},
    )
    assert result.arbitration.decision == "APPROVE"
    assert result.risk.approved
    assert engine.submit(result, order={"candidate_id": "c1", "volume": 1})["state"] == "SUBMITTED"
    assert broker.orders == [{"candidate_id": "c1", "volume": 1}]


def test_engine_without_qwen_response_fails_closed_to_wait():
    engine = VNextEngine(pair="XAUUSD", frontier=TimeFrontier.from_value("2026-01-01T00:05:00Z"))
    state = engine.compose_state(bars())
    result = engine.evaluate(state, spec(), candidate_inputs={"candidate_id": "c1", "direction": "buy",
        "zone_id": "z1", "invalidation": "z1-low", "target_zone_ids": ("z2",)})
    assert result.arbitration.decision == "WAIT"


def test_engine_persists_state_and_evaluation_events():
    ledger = InMemoryLedger()
    engine = VNextEngine(pair="XAUUSD", frontier=TimeFrontier.from_value("2026-01-01T00:05:00Z"), ledger=ledger)
    state = engine.compose_state(bars())
    engine.evaluate(state, spec())
    assert {event.event_type for event in ledger.read(pair="XAUUSD")} == {"PAIR_MARKET_STATE_COMPOSED", "STRATEGY_EVALUATION"}
    assert len(ledger.read(pair="XAUUSD")) == 2
