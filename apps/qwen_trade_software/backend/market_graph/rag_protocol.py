"""Neutral, allowlisted Neo4j RAG contract owned by Python, never Qwen."""

from __future__ import annotations

from dataclasses import dataclass

QUESTION_IDS = (
    "ZONE_HISTORY",
    "RESOLVE_TIMEFRAME_CONFLICT",
    "ACCEPTANCE_REJECTION_PROOF",
    "SIMILAR_MARKET_EPISODES",
    "DXY_CROSS_REFERENCE",
    "SESSION_STRUCTURE_HISTORY",
)

PHASE_BUDGETS = {
    "CONTEXT_WARMUP": 5,
    "ZONE_DEFINITION": 4,
    "TRADE_DECISION": 2,
    "TRADE_MANAGEMENT": 2,
}


@dataclass(frozen=True, slots=True)
class RagRequest:
    question_id: str
    symbol: str
    as_of_utc: str
    focus_zone_id: str | None = None
    timeframes: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.question_id not in QUESTION_IDS:
            raise ValueError(f"question_not_allowlisted:{self.question_id}")
        if not self.symbol or not self.as_of_utc:
            raise ValueError("symbol_and_as_of_required")


def protocol_descriptor() -> dict:
    return {
        "mode": "read_only_neutral_evidence",
        "execution_authority": False,
        "question_ids": list(QUESTION_IDS),
        "phase_budgets": dict(PHASE_BUDGETS),
        "batch_and_sequential_supported": True,
        "cache_rule": "cache_hits_do_not_consume_budget_while_evidence_epoch_unchanged",
        "missing_answer": "insufficient_evidence",
        "response_fields": [
            "question_id", "factual_answer", "supporting_evidence",
            "contradicting_evidence", "unresolved_facts", "evidence_ids",
            "as_of_utc", "freshness", "truncated", "execution_authority",
        ],
    }


def empty_answer(request: RagRequest, reason: str = "insufficient_evidence") -> dict:
    request.validate()
    return {
        "question_id": request.question_id,
        "factual_answer": reason,
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "unresolved_facts": [reason],
        "evidence_ids": [],
        "as_of_utc": request.as_of_utc,
        "freshness": "unknown",
        "truncated": False,
        "execution_authority": False,
    }
