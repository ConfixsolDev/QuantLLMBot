"""Declarative, facts-only strategy candidate program for V2."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Rule:
    path: str
    operator: str
    value: Any


@dataclass(frozen=True, slots=True)
class CandidateIntent:
    candidate_id: str
    direction: str
    zone_id: str
    invalidation: str
    target_zone_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StrategyProgram:
    """A strategy may read state facts but cannot call models, brokers, or I/O."""

    trigger: str
    invalidation_policy: str
    target_zone_policy: str
    rules: tuple[Rule, ...] = ()
    minimum_acceptance_density: float = 0.0
    allowed_zone_states: tuple[str, ...] = ("FRESH", "ACTIVE", "TESTED", "RECLAIMED")

    def __post_init__(self) -> None:
        if not all((self.trigger, self.invalidation_policy, self.target_zone_policy)):
            raise ValueError("strategy program requires trigger and geometry policies")
        if not 0 <= self.minimum_acceptance_density <= 1:
            raise ValueError("minimum acceptance density must be between 0 and 1")

    def propose(self, state: Mapping[str, Any]) -> CandidateIntent | None:
        if not self._rules_pass(state):
            return None
        structure = state.get("structure") or {}
        direction = str(structure.get("direction") or "neutral")
        if direction not in {"buy", "sell"}:
            return None
        zones = [row for row in state.get("zones", ())
                 if str(row.get("lifecycle_state")) in self.allowed_zone_states
                 and float(row.get("acceptance_density", 0)) >= self.minimum_acceptance_density]
        if len(zones) < 2:
            return None
        zones.sort(key=lambda row: (-float(row.get("acceptance_density", 0)), str(row.get("zone_id"))))
        entry, target = zones[0], zones[1]
        zone_id = str(entry["zone_id"])
        candidate_id = hashlib.sha256(f"{state.get('state_hash')}|{self.trigger}|{zone_id}|{target['zone_id']}".encode()).hexdigest()[:24]
        return CandidateIntent(candidate_id, direction, zone_id,
                               f"{zone_id}:{'lower' if direction == 'buy' else 'upper'}",
                               (str(target["zone_id"]),))

    def _rules_pass(self, state: Mapping[str, Any]) -> bool:
        for rule in self.rules:
            current: Any = state
            for part in rule.path.split("."):
                current = current.get(part) if isinstance(current, Mapping) else None
            if rule.operator == "equals" and current != rule.value:
                return False
            if rule.operator == "in" and current not in rule.value:
                return False
            if rule.operator == "gte" and (current is None or current < rule.value):
                return False
            if rule.operator not in {"equals", "in", "gte"}:
                raise ValueError(f"unsupported strategy rule operator: {rule.operator}")
        return True
