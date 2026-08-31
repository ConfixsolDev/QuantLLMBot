"""Clean-room strategy definition and candidate factory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from vnext.strategy.contracts import StrategyDefinition, TradeCandidate


@dataclass(frozen=True, slots=True)
class StrategySpec:
    definition: StrategyDefinition
    structural_requirements: tuple[str, ...] = ()
    temporal_requirements: tuple[str, ...] = ()
    trigger: str = ""
    invalidation_policy: str = ""
    target_zone_policy: str = ""
    management_policy: str = ""
    statistical_qualification: Mapping[str, Any] = field(default_factory=dict)
    narrator_request: Mapping[str, Any] = field(default_factory=dict)
    management_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trigger or not self.invalidation_policy or not self.target_zone_policy:
            raise ValueError("strategy requires trigger, invalidation, and target policies")

    def as_dict(self) -> dict[str, Any]:
        return {"definition": self.definition, "structural_requirements": list(self.structural_requirements),
                "temporal_requirements": list(self.temporal_requirements), "trigger": self.trigger,
                "invalidation_policy": self.invalidation_policy, "target_zone_policy": self.target_zone_policy,
                "management_policy": self.management_policy,
                "statistical_qualification": dict(self.statistical_qualification),
                "narrator_request": dict(self.narrator_request),
                "management_parameters": dict(self.management_parameters)}


def create_candidate(spec: StrategySpec, *, candidate_id: str, direction: str,
                     zone_id: str, invalidation: str, target_zone_ids: tuple[str, ...],
                     state_hash: str, created_at_utc: str | None = None,
                     metadata: Mapping[str, Any] | None = None) -> TradeCandidate:
    created = datetime.fromisoformat((created_at_utc or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00"))
    expires = created.timestamp() + spec.definition.expiry_seconds
    expires_at = datetime.fromtimestamp(expires, tz=timezone.utc).isoformat()
    candidate = TradeCandidate(
        candidate_id=candidate_id, pair=spec.definition.pair, strategy=spec.definition,
        direction=direction, entry_trigger=spec.trigger, zone_id=zone_id,
        invalidation=invalidation, target_zone_ids=target_zone_ids,
        created_at_utc=created.isoformat(), expires_at_utc=expires_at,
        state_hash=state_hash, metadata=metadata or {},
    )
    return candidate
