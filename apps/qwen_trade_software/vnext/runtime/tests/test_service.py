from datetime import datetime, timedelta, timezone

from vnext.runtime.live_cycle import LiveVNextCycle
from vnext.runtime.service import VNextService
from vnext.strategy.contracts import StrategyDefinition
from vnext.strategy.definition import StrategySpec
from vnext.strategy.dsl import StrategyProgram


class Source:
    def closed_m1(self, pair, count):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"time": start + timedelta(minutes=i), "open": 10+i, "high": 12+i,
                 "low": 9+i, "close": 11+i, "tick_volume": i+1} for i in range(5)]


class Ledger:
    def __init__(self): self.events = []
    def append(self, event): self.events.append(event); return True


class Projection:
    def project(self, events): return len(list(events))


class Memory:
    def put(self, key, value): pass


def spec():
    return StrategySpec(StrategyDefinition("XAUUSD", "S1", "1", 1, "SCALP"),
                        trigger="reclaim", invalidation_policy="break", target_zone_policy="next")


def test_service_without_candidate_provider_is_no_trade():
    from vnext.storage.persistence import VNextPersistence
    p = VNextPersistence(ledger=Ledger(), projection=Projection(), working_memory=Memory())
    result = VNextService(cycle=LiveVNextCycle(pair="XAUUSD", source=Source(), persistence=p), strategy=spec()).run_once()
    assert result.evaluation is None and result.submitted is None


def test_service_rejects_missing_strategy_before_runtime():
    from vnext.storage.persistence import VNextPersistence
    p = VNextPersistence(ledger=Ledger(), projection=Projection(), working_memory=Memory())
    try:
        VNextService(cycle=LiveVNextCycle(pair="XAUUSD", source=Source(), persistence=p), strategy=None)
    except TypeError as exc:
        assert "StrategySpec" in str(exc)
    else:
        raise AssertionError("V2 service must reject a missing strategy")


def test_service_does_not_submit_without_order_provider():
    from vnext.storage.persistence import VNextPersistence
    p = VNextPersistence(ledger=Ledger(), projection=Projection(), working_memory=Memory())
    result = VNextService(cycle=LiveVNextCycle(pair="XAUUSD", source=Source(), persistence=p), strategy=spec(),
        candidate_provider=lambda state: {"candidate_id": "c1", "direction": "buy", "zone_id": "z1",
            "invalidation": "z1-low", "target_zone_ids": ("z2",)},
        risk_provider=lambda state, candidate: {"account_equity": 10000, "risk_fraction": .01,
            "entry": 10, "stop": 9, "point_value": 1},
        qwen_client=None).run_once()
    assert result.evaluation is not None and result.submitted is None


def test_service_can_use_explicit_strategy_program():
    from vnext.storage.persistence import VNextPersistence
    p = VNextPersistence(ledger=Ledger(), projection=Projection(), working_memory=Memory())
    # The composed fixture has one zone, so the program correctly remains no-trade.
    result = VNextService(cycle=LiveVNextCycle(pair="XAUUSD", source=Source(), persistence=p), strategy=spec(),
                          strategy_program=StrategyProgram("reclaim", "break", "next")).run_once()
    assert result.evaluation is None and result.submitted is None
