from datetime import datetime, timedelta, timezone

from vnext.runtime.position_management import (
    ManagedPosition, ManagementProfile, PositionManagementService,
)
from vnext.strategy.management import ScalpManagementParameters


class Broker:
    def __init__(self): self.actions = []
    def modify_position(self, **kwargs): self.actions.append(("protect", kwargs))
    def close_position(self, **kwargs): self.actions.append(("close", kwargs))


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def position(**changes):
    values = dict(position_id="1", strategy_id="S", pair="XAUUSDr", direction="buy", volume=.1,
                  entry=100, current=100, peak=100, opened_at=BASE, broker_stop=97,
                  broker_target=105, atr=1, spread=.1, point=.01, latest_m1={"close": 100},
                  latest_m5={"close": 100}, latest_m1_id="m1", latest_m5_id="m5")
    values.update(changes)
    return ManagedPosition(**values)


def service(broker, reviewer=None):
    return PositionManagementService(profiles={"S": ManagementProfile("S", ScalpManagementParameters())},
                                     broker=broker, reviewer=reviewer)


def test_tick_manager_closes_deterministic_max_duration():
    broker = Broker()
    result = service(broker).on_tick(position(), now=BASE + timedelta(minutes=10))
    assert result.applied_action == "close" and broker.actions[0][0] == "close"


def test_tick_manager_calls_qwen_only_every_five_minutes_and_validates_response():
    broker = Broker()
    manager = service(broker, reviewer=lambda _: {"action": "protect", "candidate_stop": 100.1,
                                                    "evidence_ids": ("m1", "m5")})
    active = position(current=100.5, peak=100.5)
    assert manager.on_tick(active, now=BASE + timedelta(minutes=4)).review is None
    result = manager.on_tick(active, now=BASE + timedelta(minutes=5))
    assert result.applied_action == "protect" and broker.actions[-1][0] == "protect"


def test_dual_completed_candle_invalidation_overrides_qwen_schedule():
    broker = Broker()
    result = service(broker).on_tick(position(latest_m1={"close": 96.9}, latest_m5={"close": 96.8}),
                                     now=BASE + timedelta(seconds=30))
    assert result.decision.reason == "dual_timeframe_invalidation"
    assert result.applied_action == "close"
