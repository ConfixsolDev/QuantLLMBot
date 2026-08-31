"""Native, dependency-free V2 strategy and candidate contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    pair: str
    strategy_id: str
    version: str
    magic_number: int
    trade_class: str
    context_requirements: tuple[str, ...] = ()
    eligible_zone_types: tuple[str, ...] = ()
    evaluation_cadence_seconds: int = 60
    expiry_seconds: int = 900
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pair or not self.strategy_id or not self.version:
            raise ValueError("pair, strategy_id, and version are required")
        if self.magic_number <= 0 or self.evaluation_cadence_seconds <= 0 or self.expiry_seconds <= 0:
            raise ValueError("strategy numeric fields must be positive")
        if self.trade_class not in {"HTF", "SCALP", "MICRO"}:
            raise ValueError("trade_class must be HTF, SCALP, or MICRO")


@dataclass(frozen=True, slots=True)
class TradeCandidate:
    candidate_id: str
    pair: str
    strategy: StrategyDefinition
    direction: str
    entry_trigger: str
    zone_id: str
    invalidation: str
    target_zone_ids: tuple[str, ...]
    created_at_utc: str
    expires_at_utc: str
    state_hash: str
    statistics_snapshot_id: str | None = None
    narrator_snapshot_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direction not in {"buy", "sell"}:
            raise ValueError("candidate direction must be buy or sell")
        if self.pair != self.strategy.pair:
            raise ValueError("candidate pair must match strategy pair")
        if not all((self.candidate_id, self.entry_trigger, self.zone_id,
                    self.invalidation, self.state_hash)) or not self.target_zone_ids:
            raise ValueError("candidate is missing required geometry")
        if datetime.fromisoformat(self.expires_at_utc.replace("Z", "+00:00")) <= datetime.fromisoformat(self.created_at_utc.replace("Z", "+00:00")):
            raise ValueError("candidate expiry must be after creation")

    def as_dict(self) -> dict[str, Any]:
        return {"candidate_id": self.candidate_id, "pair": self.pair,
                "strategy_id": self.strategy.strategy_id, "strategy_version": self.strategy.version,
                "magic_number": self.strategy.magic_number, "trade_class": self.strategy.trade_class,
                "direction": self.direction, "entry_trigger": self.entry_trigger,
                "zone_id": self.zone_id, "invalidation": self.invalidation,
                "target_zone_ids": list(self.target_zone_ids), "created_at_utc": self.created_at_utc,
                "expires_at_utc": self.expires_at_utc, "state_hash": self.state_hash,
                "statistics_snapshot_id": self.statistics_snapshot_id,
                "narrator_snapshot_id": self.narrator_snapshot_id, "metadata": dict(self.metadata)}
