"""Fail-closed restart reconciliation between ledger and broker truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    safe_to_resume: bool
    new_trade_creation_allowed: bool
    reasons: tuple[str, ...]
    broker_positions: tuple[Mapping[str, Any], ...]
    ledger_positions: tuple[Mapping[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {"safe_to_resume": self.safe_to_resume,
                "new_trade_creation_allowed": self.new_trade_creation_allowed,
                "reasons": list(self.reasons),
                "broker_positions": [dict(row) for row in self.broker_positions],
                "ledger_positions": [dict(row) for row in self.ledger_positions]}


def reconcile(*, broker_positions: list[Mapping[str, Any]], ledger_positions: list[Mapping[str, Any]],
              broker_healthy: bool, data_healthy: bool, timescale_healthy: bool,
              redis_rebuilt: bool, neo4j_status: str = "ready") -> RecoveryPlan:
    reasons: list[str] = []
    broker_ids = {str(row.get("position_id")) for row in broker_positions}
    ledger_ids = {str(row.get("position_id")) for row in ledger_positions}
    if not broker_healthy:
        reasons.append("broker_unhealthy")
    if not data_healthy:
        reasons.append("data_unhealthy")
    if not timescale_healthy:
        reasons.append("timescale_unhealthy")
    if not redis_rebuilt:
        reasons.append("redis_not_rebuilt")
    if broker_ids != ledger_ids:
        reasons.append("broker_ledger_position_mismatch")
    # Neo4j is enrichment, not broker truth, so it does not alone prevent
    # deterministic recovery when the durable numerical ledger is healthy.
    return RecoveryPlan(not reasons, not reasons, tuple(reasons),
                        tuple(broker_positions), tuple(ledger_positions))
