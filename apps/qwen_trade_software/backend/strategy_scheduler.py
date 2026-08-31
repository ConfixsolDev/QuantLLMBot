"""Attention scheduler for strategy evaluation, independent of market logic."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationSchedule:
    strategy_id: str
    normal_seconds: int
    actionable_seconds: int
    critical_seconds: int

    def __post_init__(self) -> None:
        if min(self.normal_seconds, self.actionable_seconds, self.critical_seconds) <= 0:
            raise ValueError("schedule intervals must be positive")


def cadence(schedule: EvaluationSchedule, *, near_actionable_zone: bool,
            trigger_pending: bool, state_changed: bool) -> dict:
    if state_changed:
        reason, seconds = "state_changed", 0
    elif trigger_pending:
        reason, seconds = "critical_entry", schedule.critical_seconds
    elif near_actionable_zone:
        reason, seconds = "actionable_zone", schedule.actionable_seconds
    else:
        reason, seconds = "normal", schedule.normal_seconds
    return {"strategy_id": schedule.strategy_id, "next_in_seconds": seconds, "reason": reason,
            "state_changed": bool(state_changed)}
