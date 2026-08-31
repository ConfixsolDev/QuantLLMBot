from datetime import datetime, timedelta, timezone

import pytest

from strategy_contract import StrategyDefinition
from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine
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
    assert result.arbitration is None
    with pytest.raises(RuntimeError):
        engine.submit(result, order={"candidate_id": "c1"})


def test_engine_recovery_fails_closed_on_mismatch():
    result = VNextEngine.recover(broker_positions=[{"position_id": 1}], ledger_positions=[], broker_healthy=True, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert result.safe_to_resume is False
