"""Per-instrument runtime state for analysis and trade-idea lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from approach_tracker import ApproachTracker
from idea_lifecycle import IdeaManager
from instrument_config import InstrumentConfig, canonical_symbol, instrument_for
from zone_scorer import ScoringConfig


@dataclass(slots=True)
class MarketRuntime:
    config: InstrumentConfig
    idea_manager: IdeaManager = field(default_factory=IdeaManager)
    approach_tracker: ApproachTracker = field(default_factory=ApproachTracker)
    regime_memory: dict[str, float | str | None] = field(
        default_factory=lambda: {"hint": None, "atr_ratio": None}
    )

    @property
    def symbol(self) -> str:
        return self.config.key

    @property
    def scoring_config(self) -> ScoringConfig:
        return ScoringConfig(
            strong_departure_atr_multiple=self.config.scoring_strong_departure_atr,
            moderate_departure_atr_multiple=self.config.scoring_moderate_departure_atr,
            min_rr=self.config.scoring_min_rr,
            strong_rr=self.config.scoring_strong_rr,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "broker_symbol": self.config.broker_symbol,
            "idea_manager": self.idea_manager.to_state(),
            "approach_tracker": self.approach_tracker.to_state(),
            "regime_memory": dict(self.regime_memory),
        }


class MarketRuntimeRegistry:
    """Own one independent mutable runtime per canonical instrument."""

    def __init__(self) -> None:
        self._markets: dict[str, MarketRuntime] = {}

    def get(self, symbol: str) -> MarketRuntime:
        key = canonical_symbol(symbol)
        runtime = self._markets.get(key)
        if runtime is None:
            runtime = MarketRuntime(instrument_for(symbol))
            self._markets[key] = runtime
        return runtime

    def all(self) -> list[MarketRuntime]:
        return list(self._markets.values())

    def to_state(self) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "markets": {
                key: runtime.to_state() for key, runtime in self._markets.items()
            },
        }

    @classmethod
    def from_state(cls, state: dict[str, Any]) -> "MarketRuntimeRegistry":
        registry = cls()
        markets = state.get("markets")
        if not isinstance(markets, dict):
            # Legacy v1 reviewer state contained one implicit Gold runtime.
            markets = {"XAUUSD": state} if state.get("idea_manager") else {}
        for key, raw in markets.items():
            if not isinstance(raw, dict):
                continue
            runtime = registry.get(str(raw.get("broker_symbol") or key))
            if raw.get("idea_manager"):
                runtime.idea_manager = IdeaManager.from_state(raw["idea_manager"])
            if raw.get("approach_tracker"):
                runtime.approach_tracker = ApproachTracker.from_state(
                    raw["approach_tracker"]
                )
            memory = raw.get("regime_memory")
            if isinstance(memory, dict):
                runtime.regime_memory.update({
                    "hint": memory.get("hint"),
                    "atr_ratio": memory.get("atr_ratio"),
                })
        return registry
