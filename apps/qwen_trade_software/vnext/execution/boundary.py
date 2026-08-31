"""Final modular boundary before the existing validated executor."""

from __future__ import annotations

from vnext.strategy.contracts import TradeCandidate


def validate_candidate_for_execution(candidate: TradeCandidate) -> dict[str, object]:
    """Return auditable candidate facts; never approves, sizes, or submits orders."""
    if candidate.direction not in {"buy", "sell"}:
        raise ValueError("candidate must have one committed direction")
    return {
        "candidate_id": candidate.candidate_id,
        "pair": candidate.pair,
        "direction": candidate.direction,
        "zone_id": candidate.zone_id,
        "invalidation": candidate.invalidation,
        "target_zone_ids": list(candidate.target_zone_ids),
        "state_hash": candidate.state_hash,
        "execution_authority": "vnext_deterministic_oms",
    }
