"""Fail-closed preflight before enabling the V2 live order path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vnext.recovery.reconcile import RecoveryPlan, reconcile
from vnext.storage.persistence import VNextPersistence


@dataclass(frozen=True, slots=True)
class CutoverPreflight:
    plan: RecoveryPlan
    persistence_ready: bool
    broker_snapshot: Mapping[str, Any]

    @property
    def allowed(self) -> bool:
        return self.persistence_ready and self.plan.safe_to_resume


def run_preflight(*, persistence: VNextPersistence, broker: Any,
                  ledger_positions: list[Mapping[str, Any]],
                  redis_rebuilt: bool) -> CutoverPreflight:
    """Check all durable/runtime prerequisites; never enable trading itself."""
    try:
        health = persistence.ensure_ready()
        snapshot = broker.snapshot()
    except Exception as exc:
        plan = reconcile(broker_positions=[], ledger_positions=ledger_positions,
                         broker_healthy=False, data_healthy=False,
                         timescale_healthy=False, redis_rebuilt=redis_rebuilt)
        return CutoverPreflight(plan, False, {"healthy": False, "error": type(exc).__name__})
    positions = list(snapshot.get("positions", ()))
    plan = reconcile(broker_positions=positions, ledger_positions=ledger_positions,
                     broker_healthy=bool(snapshot.get("healthy")),
                     data_healthy=True, timescale_healthy=health.timescale,
                     redis_rebuilt=redis_rebuilt, neo4j_status="ready" if health.neo4j else "unavailable")
    return CutoverPreflight(plan, health.ready, snapshot)
