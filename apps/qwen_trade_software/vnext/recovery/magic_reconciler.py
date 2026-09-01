"""Broker-truth reconciliation scoped to one strategy magic namespace."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from vnext.platform.events import EventEnvelope
from vnext.recovery.reconcile import RecoveryPlan, reconcile


class SnapshotBroker(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


class PositionSnapshotStore(Protocol):
    def latest_magic_positions(self, magic_number: int) -> list[Mapping[str, Any]]: ...
    def append_events(self, events: list[EventEnvelope]) -> int: ...


class MagicPositionReconciler:
    """Persist broker truth only for the configured V2 magic number."""

    def __init__(self, *, magic_number: int, store: PositionSnapshotStore) -> None:
        if magic_number <= 0:
            raise ValueError("magic number must be positive")
        self.magic_number, self.store = magic_number, store

    def run(self, broker: SnapshotBroker, *, data_healthy: bool, timescale_healthy: bool,
            redis_rebuilt: bool) -> RecoveryPlan:
        snapshot = broker.snapshot()
        broker_positions = [dict(row) for row in snapshot.get("positions", ())]
        ledger_positions = [dict(row) for row in self.store.latest_magic_positions(self.magic_number)]
        plan = reconcile(broker_positions=broker_positions, ledger_positions=ledger_positions,
                         broker_healthy=bool(snapshot.get("healthy")), data_healthy=data_healthy,
                         timescale_healthy=timescale_healthy, redis_rebuilt=redis_rebuilt)
        # Broker truth is authoritative within this exclusive magic namespace.
        # Persist each observation so the next restart compares against the last
        # known broker state; other magic namespaces are not represented here.
        payload = {"magic_number": self.magic_number, "positions": broker_positions,
                   "prior_ledger_positions": ledger_positions, "recovery_plan": plan.as_dict()}
        observed_at_utc = datetime.now(timezone.utc)
        raw = json.dumps({"observed_at_utc": observed_at_utc.isoformat(), "payload": payload},
                         sort_keys=True, default=str)
        event = EventEnvelope("magic-snapshot-" + hashlib.sha256(raw.encode()).hexdigest()[:24],
                              "MAGIC_POSITION_SNAPSHOT", "SYSTEM", observed_at_utc,
                              payload, "vnext_magic_reconciler")
        self.store.append_events([event])
        return plan
