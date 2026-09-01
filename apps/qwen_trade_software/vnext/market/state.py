"""Immutable canonical pair market state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from vnext.platform.events import _canonical
from vnext.platform.time_frontier import utc


@dataclass(frozen=True, slots=True)
class PairMarketState:
    pair: str
    time_frontier_utc: datetime
    data_quality: Mapping[str, Any]
    timeframes: Mapping[str, Any]
    zones: tuple[Mapping[str, Any], ...] = ()
    structure: Mapping[str, Any] = None  # type: ignore[assignment]
    structural_events: tuple[Mapping[str, Any], ...] = ()
    mtf_relationships: tuple[Mapping[str, Any], ...] = ()
    temporal_state: Mapping[str, Any] = None  # type: ignore[assignment]
    statistics: Mapping[str, Any] = None  # type: ignore[assignment]
    indicators: Mapping[str, Any] = None  # type: ignore[assignment]
    active_levels: tuple[Mapping[str, Any], ...] = ()
    graph_references: tuple[str, ...] = ()
    strategy_evidence: Mapping[str, Any] = None  # type: ignore[assignment]
    schema_version: str = "PAIR_MARKET_STATE_V1"

    def __post_init__(self) -> None:
        if not self.pair or self.schema_version != "PAIR_MARKET_STATE_V1":
            raise ValueError("invalid pair market state identity")
        object.__setattr__(self, "time_frontier_utc", utc(self.time_frontier_utc))
        for name in ("data_quality", "timeframes", "structure", "temporal_state", "statistics", "indicators", "strategy_evidence"):
            if getattr(self, name) is None:
                object.__setattr__(self, name, {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version, "pair": self.pair,
            "time_frontier_utc": self.time_frontier_utc.isoformat(),
            "data_quality": dict(self.data_quality), "timeframes": dict(self.timeframes),
            "zones": [dict(row) for row in self.zones], "structure": dict(self.structure),
            "structural_events": [dict(row) for row in self.structural_events],
            "mtf_relationships": [dict(row) for row in self.mtf_relationships],
            "temporal_state": dict(self.temporal_state), "statistics": dict(self.statistics),
            "indicators": dict(self.indicators), "active_levels": [dict(row) for row in self.active_levels],
            "graph_references": list(self.graph_references),
            "strategy_evidence": dict(self.strategy_evidence),
        }

    @property
    def state_hash(self) -> str:
        import hashlib
        return hashlib.sha256(_canonical(self.as_dict()).encode("utf-8")).hexdigest()
