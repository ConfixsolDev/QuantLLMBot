"""Independent due-time scheduling for multiple V2 strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from vnext.strategy.contracts import StrategyDefinition


@dataclass(frozen=True, slots=True)
class StrategyScheduleState:
    strategy_id: str
    next_due_utc: datetime
    reason: str = "initial"


class MultiStrategyScheduler:
    """Keep strategy cadences isolated; no strategy can delay another."""

    def __init__(self, strategies: tuple[StrategyDefinition, ...], *, now: datetime | None = None) -> None:
        if not strategies:
            raise ValueError("at least one strategy is required")
        ids = [strategy.strategy_id for strategy in strategies]
        if len(set(ids)) != len(ids):
            raise ValueError("strategy ids must be unique")
        current = self._utc(now or datetime.now(timezone.utc))
        self._strategies: Mapping[str, StrategyDefinition] = {s.strategy_id: s for s in strategies}
        self._states = {
            strategy.strategy_id: StrategyScheduleState(strategy.strategy_id, current, "initial")
            for strategy in strategies
        }

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("scheduler timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    def due(self, *, now: datetime | None = None) -> tuple[str, ...]:
        current = self._utc(now or datetime.now(timezone.utc))
        return tuple(strategy_id for strategy_id, state in self._states.items()
                     if state.next_due_utc <= current)

    def state(self, strategy_id: str) -> StrategyScheduleState:
        try:
            return self._states[strategy_id]
        except KeyError as exc:
            raise KeyError(f"unknown strategy: {strategy_id}") from exc

    def mark_evaluated(self, strategy_id: str, *, now: datetime | None = None,
                       reason: str = "normal") -> StrategyScheduleState:
        current = self._utc(now or datetime.now(timezone.utc))
        strategy = self._strategies.get(strategy_id)
        if strategy is None:
            raise KeyError(f"unknown strategy: {strategy_id}")
        next_due = current + timedelta(seconds=strategy.evaluation_cadence_seconds)
        updated = StrategyScheduleState(strategy_id, next_due, reason)
        self._states[strategy_id] = updated
        return updated
