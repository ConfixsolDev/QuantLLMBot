"""Durable V2 recovery/reconciliation coordinator."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping

from vnext.platform.events import EventEnvelope
from vnext.recovery.reconcile import RecoveryPlan, reconcile
from vnext.storage.persistence import VNextPersistence


class RecoveryCoordinator:
    def __init__(self, persistence: VNextPersistence) -> None:
        self.persistence = persistence

    def run(self, *, broker_positions: list[Mapping[str, Any]],
            ledger_positions: list[Mapping[str, Any]], broker_healthy: bool,
            data_healthy: bool, redis_rebuilt: bool, neo4j_status: str = "ready") -> RecoveryPlan:
        plan = reconcile(broker_positions=broker_positions, ledger_positions=ledger_positions,
                         broker_healthy=broker_healthy, data_healthy=data_healthy,
                         timescale_healthy=True, redis_rebuilt=redis_rebuilt,
                         neo4j_status=neo4j_status)
        observed = datetime.now(timezone.utc)
        payload = plan.as_dict()
        raw = json.dumps(payload, sort_keys=True, default=str)
        event = EventEnvelope("recovery-" + hashlib.sha256(raw.encode()).hexdigest()[:24],
                              "V2_RECOVERY_RECONCILIATION", "SYSTEM", observed,
                              payload, "vnext_recovery")
        self.persistence.append_events([event])
        return plan
