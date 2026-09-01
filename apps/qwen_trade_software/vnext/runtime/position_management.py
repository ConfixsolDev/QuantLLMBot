"""Common deterministic position-management orchestration.

Strategies provide their own management profile; this module only schedules,
validates, applies, and audits the resulting actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol

from vnext.strategy.management import (
    ManagementDecision, ManagementReview, ScalpManagementParameters,
    emergency_close_required, manage_scalp, qwen_review_due,
    validate_qwen_management_review,
)


class PositionBroker(Protocol):
    def modify_position(self, *, position_id: str | int, pair: str, stop: float,
                        target: float, comment: str = ...) -> Any: ...
    def close_position(self, *, position_id: str | int, pair: str, direction: str,
                       volume: float, comment: str = ...) -> Any: ...


@dataclass(frozen=True, slots=True)
class ManagementProfile:
    """Strategy-owned parameters consumed by the common orchestrator."""
    strategy_id: str
    parameters: ScalpManagementParameters
    allowed_qwen_actions: tuple[str, ...] = ("hold", "protect", "close")

    def __post_init__(self) -> None:
        if not self.strategy_id or not set(self.allowed_qwen_actions).issubset({"hold", "protect", "close"}):
            raise ValueError("invalid strategy management profile")


@dataclass(frozen=True, slots=True)
class ManagedPosition:
    position_id: str
    strategy_id: str
    pair: str
    direction: str
    volume: float
    entry: float
    current: float
    peak: float
    opened_at: datetime
    broker_stop: float
    broker_target: float
    atr: float
    spread: float
    point: float
    latest_m1: Mapping[str, Any] | None = None
    latest_m5: Mapping[str, Any] | None = None
    latest_m1_id: str = ""
    latest_m5_id: str = ""


@dataclass(frozen=True, slots=True)
class PositionManagementResult:
    decision: ManagementDecision | None
    review: ManagementReview | None
    review_failures: tuple[str, ...]
    applied_action: str | None


ReviewProvider = Callable[[ManagedPosition], Mapping[str, Any]]


class PositionManagementService:
    """Run every tick; request Qwen only at the profile's review cadence."""

    def __init__(self, *, profiles: Mapping[str, ManagementProfile], broker: PositionBroker,
                 reviewer: ReviewProvider | None = None) -> None:
        self.profiles, self.broker, self.reviewer = dict(profiles), broker, reviewer
        self._last_reviews: dict[str, datetime] = {}

    def on_tick(self, position: ManagedPosition, *, now: datetime) -> PositionManagementResult:
        profile = self.profiles.get(position.strategy_id)
        if profile is None:
            raise ValueError("position has no registered management profile")
        decision = manage_scalp(side=position.direction, entry=position.entry, current=position.current,
                                peak=position.peak, opened_at=position.opened_at, now=now,
                                atr=position.atr, broker_stop=position.broker_stop, spread=position.spread,
                                point=position.point, parameters=profile.parameters)
        # Approved emergency rule takes precedence over every ordinary action.
        if position.latest_m1 and position.latest_m5 and emergency_close_required(
                side=position.direction, invalidation_price=position.broker_stop,
                latest_m1=position.latest_m1, latest_m5=position.latest_m5):
            decision = ManagementDecision("CLOSE", "INVALIDATED", "dual_timeframe_invalidation",
                                          decision.favorable_move, decision.adverse_move, decision.mfe_atr)
        applied = self._apply_decision(position, decision)
        if applied == "close":
            return PositionManagementResult(decision, None, (), applied)
        if self.reviewer is None or not qwen_review_due(opened_at=position.opened_at, now=now,
                                                         last_review_at=self._last_reviews.get(position.position_id),
                                                         parameters=profile.parameters):
            return PositionManagementResult(decision, None, (), applied)
        self._last_reviews[position.position_id] = now
        response = self.reviewer(position)
        review, failures = validate_qwen_management_review(
            response=response, side=position.direction, current_stop=position.broker_stop,
            current_target=position.broker_target, latest_m1_id=position.latest_m1_id,
            latest_m5_id=position.latest_m5_id)
        if review.action not in profile.allowed_qwen_actions:
            return PositionManagementResult(decision, review, ("management:action_not_allowed_by_strategy",), applied)
        applied_review = self._apply_review(position, review)
        return PositionManagementResult(decision, review, failures, applied_review or applied)

    def _apply_decision(self, position: ManagedPosition, decision: ManagementDecision) -> str | None:
        if decision.action == "CLOSE":
            self.broker.close_position(position_id=position.position_id, pair=position.pair,
                                       direction=position.direction, volume=position.volume)
            return "close"
        if decision.action == "MOVE_STOP" and decision.candidate_stop is not None:
            self.broker.modify_position(position_id=position.position_id, pair=position.pair,
                                        stop=decision.candidate_stop, target=position.broker_target)
            return "protect"
        return None

    def _apply_review(self, position: ManagedPosition, review: ManagementReview) -> str | None:
        if review.action == "close":
            self.broker.close_position(position_id=position.position_id, pair=position.pair,
                                       direction=position.direction, volume=position.volume)
            return "close"
        if review.action == "protect":
            self.broker.modify_position(position_id=position.position_id, pair=position.pair,
                                        stop=review.candidate_stop or position.broker_stop,
                                        target=review.candidate_target or position.broker_target)
            return "protect"
        return None
