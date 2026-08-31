"""Auditable strategy lifecycle facade with no broker or LLM calls."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass, field
import hashlib
import json

from vnext.strategy.contracts import TradeCandidate


STATES = frozenset({"INACTIVE", "ELIGIBLE", "WATCHING", "ARMED", "TRIGGERED",
                    "CANDIDATE_CREATED", "LLM_APPROVED", "RISK_APPROVED",
                    "ORDER_PENDING", "POSITION_ACTIVE", "CLOSED", "INVALIDATED",
                    "EXPIRED", "REJECTED", "CANCELLED"})
TRANSITIONS = {
    "INACTIVE": {"ELIGIBLE"}, "ELIGIBLE": {"WATCHING", "INACTIVE"},
    "WATCHING": {"ARMED", "INACTIVE", "EXPIRED"},
    "ARMED": {"TRIGGERED", "EXPIRED", "INVALIDATED"},
    "TRIGGERED": {"CANDIDATE_CREATED", "REJECTED", "INVALIDATED"},
    "CANDIDATE_CREATED": {"LLM_APPROVED", "REJECTED", "EXPIRED"},
    "LLM_APPROVED": {"RISK_APPROVED", "REJECTED"},
    "RISK_APPROVED": {"ORDER_PENDING", "REJECTED"},
    "ORDER_PENDING": {"POSITION_ACTIVE", "CANCELLED", "REJECTED"},
    "POSITION_ACTIVE": {"CLOSED", "INVALIDATED"},
}


@dataclass(frozen=True, slots=True)
class StrategyRuntimeState:
    strategy_id: str
    state: str = "INACTIVE"
    candidate_id: str | None = None
    updated_at_utc: str = ""

    @property
    def state_hash(self) -> str:
        raw = json.dumps({"strategy_id": self.strategy_id, "state": self.state,
                          "candidate_id": self.candidate_id, "updated_at_utc": self.updated_at_utc}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()


class CandidateLifecycle:
    """State transitions are explicit and persisted only through the caller."""

    def __init__(self, strategy_id: str, state: StrategyRuntimeState | None = None) -> None:
        self.state = state or StrategyRuntimeState(strategy_id)

    def advance(self, new_state: str, *, candidate: TradeCandidate | None = None) -> StrategyRuntimeState:
        if new_state not in STATES or new_state not in TRANSITIONS.get(self.state.state, set()):
            raise ValueError(f"invalid strategy transition {self.state.state} -> {new_state}")
        self.state = StrategyRuntimeState(self.state.strategy_id, new_state,
                                          candidate.candidate_id if candidate else self.state.candidate_id,
                                          datetime.now(timezone.utc).isoformat())
        return self.state

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.state.strategy_id,
            "candidate_id": self.state.candidate_id,
            "state": self.state.state,
            "state_hash": self.state.state_hash,
            "updated_at_utc": self.state.updated_at_utc,
        }
