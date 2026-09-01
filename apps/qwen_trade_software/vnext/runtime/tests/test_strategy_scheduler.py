from datetime import datetime, timezone

from vnext.runtime.strategy_scheduler import MultiStrategyScheduler
from vnext.strategy.contracts import StrategyDefinition


def test_multi_strategy_scheduler_keeps_due_times_isolated():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = StrategyDefinition("XAUUSD", "S1", "1", 1001, "SCALP", evaluation_cadence_seconds=5)
    second = StrategyDefinition("XAUUSD", "S2", "1", 1002, "HTF", evaluation_cadence_seconds=60)
    scheduler = MultiStrategyScheduler((first, second), now=now)

    assert scheduler.due(now=now) == ("S1", "S2")
    scheduler.mark_evaluated("S1", now=now, reason="state_changed")
    assert scheduler.due(now=now) == ("S2",)
    assert scheduler.state("S1").reason == "state_changed"
    assert scheduler.due(now=now.replace(second=5)) == ("S1", "S2")


def test_scheduler_rejects_duplicate_strategy_ids():
    definition = StrategyDefinition("XAUUSD", "S1", "1", 1001, "SCALP")
    try:
        MultiStrategyScheduler((definition, definition))
    except ValueError as error:
        assert "unique" in str(error)
    else:
        raise AssertionError("duplicate strategy IDs must be rejected")
