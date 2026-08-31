"""Validate an LLM response against one supplied candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from strategy_contract import TradeCandidate


DECISIONS = frozenset({"APPROVE", "WAIT", "VETO", "NO_TRADE"})


@dataclass(frozen=True, slots=True)
class Arbitration:
    decision: str
    candidate_id: str | None
    reason: str
    state_hash: str
    violations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"decision": self.decision, "candidate_id": self.candidate_id,
                "reason": self.reason, "state_hash": self.state_hash,
                "violations": list(self.violations)}


def arbitrate(response: Mapping[str, Any], candidate: TradeCandidate) -> Arbitration:
    decision = str(response.get("decision") or "").upper()
    violations: list[str] = []
    if decision not in DECISIONS:
        violations.append("invalid_decision")
        decision = "NO_TRADE"
    cited = response.get("candidate_id")
    if decision == "APPROVE" and cited != candidate.candidate_id:
        violations.append("approve_must_cite_candidate")
    response_hash = response.get("state_hash")
    if response_hash not in {None, candidate.state_hash}:
        violations.append("state_hash_mismatch")
    if violations:
        return Arbitration("NO_TRADE", None, ";".join(violations), candidate.state_hash, tuple(violations))
    return Arbitration(decision, cited if cited == candidate.candidate_id else None,
                       str(response.get("reason") or ""), candidate.state_hash)
