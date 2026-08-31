"""Auditable strategy lifecycle facade with no broker or LLM calls."""

from __future__ import annotations

from datetime import datetime, timezone

from strategy_contract import TradeCandidate
from strategy_runtime import StrategyRuntimeState, transition


class CandidateLifecycle:
    """State transitions are explicit and persisted only through the caller."""

    def __init__(self, strategy_id: str, state: StrategyRuntimeState | None = None) -> None:
        self.state = state or StrategyRuntimeState(strategy_id)

    def advance(self, new_state: str, *, candidate: TradeCandidate | None = None) -> StrategyRuntimeState:
        self.state = transition(
            self.state, new_state, candidate=candidate,
            at_utc=datetime.now(timezone.utc).isoformat(),
        )
        return self.state

    def as_dict(self) -> dict[str, object]:
        return {
            "strategy_id": self.state.strategy_id,
            "candidate_id": self.state.candidate_id,
            "state": self.state.state,
            "state_hash": self.state.state_hash,
            "updated_at_utc": self.state.updated_at_utc,
        }
