"""Constrain LLM arbitration to a supplied, already-valid trade candidate."""

from __future__ import annotations

from dataclasses import dataclass

from strategy_contract import TradeCandidate


DECISIONS = frozenset({"APPROVE", "WAIT", "VETO", "NO_TRADE"})


@dataclass(frozen=True, slots=True)
class ArbitrationResult:
    decision: str
    candidate_id: str | None
    reason: str
    state_hash: str | None

    def as_dict(self) -> dict:
        return {"decision": self.decision, "candidate_id": self.candidate_id,
                "reason": self.reason, "state_hash": self.state_hash}


def validate_response(response: dict, candidate: TradeCandidate) -> ArbitrationResult:
    decision = str(response.get("decision") or "").upper()
    if decision not in DECISIONS:
        raise ValueError("LLM decision must be APPROVE, WAIT, VETO, or NO_TRADE")
    cited = response.get("candidate_id")
    if decision == "APPROVE" and cited != candidate.candidate_id:
        raise ValueError("APPROVE must cite the supplied candidate")
    if response.get("state_hash") not in {None, candidate.state_hash}:
        raise ValueError("LLM state hash does not match candidate")
    reason = str(response.get("reason") or "")[:500]
    if not reason:
        raise ValueError("LLM arbitration requires a bounded reason")
    return ArbitrationResult(decision, cited if cited == candidate.candidate_id else None, reason, candidate.state_hash)
