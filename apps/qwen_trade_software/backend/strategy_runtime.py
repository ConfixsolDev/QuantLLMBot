"""Replayable lifecycle state machine for strategy candidates."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_contract import ALLOWED_TRANSITIONS, STRATEGY_STATES, TERMINAL_STATES, TradeCandidate


@dataclass(frozen=True, slots=True)
class StrategyRuntimeState:
    strategy_id: str
    candidate_id: str | None = None
    state: str = "INACTIVE"
    state_hash: str | None = None
    updated_at_utc: str | None = None


def transition(current: StrategyRuntimeState, new_state: str, *, candidate: TradeCandidate | None = None, at_utc: str | None = None) -> StrategyRuntimeState:
    if new_state not in STRATEGY_STATES:
        raise ValueError(f"unknown strategy state: {new_state}")
    if current.state in TERMINAL_STATES:
        raise ValueError(f"terminal strategy state cannot transition: {current.state}")
    if new_state not in ALLOWED_TRANSITIONS.get(current.state, set()):
        raise ValueError(f"invalid strategy transition {current.state}->{new_state}")
    if candidate is not None and candidate.strategy.strategy_id != current.strategy_id:
        raise ValueError("candidate belongs to another strategy")
    candidate_id = candidate.candidate_id if candidate else current.candidate_id
    state_hash = candidate.state_hash if candidate else current.state_hash
    return StrategyRuntimeState(current.strategy_id, candidate_id, new_state, state_hash, at_utc or current.updated_at_utc)


def replay_transitions(strategy_id: str, transitions: list[dict]) -> StrategyRuntimeState:
    state = StrategyRuntimeState(strategy_id)
    for item in transitions:
        state = transition(state, str(item["state"]), at_utc=item.get("at_utc"))
    return state
