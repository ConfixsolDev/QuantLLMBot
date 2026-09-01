"""Machine-grounded causal story builder over immutable market facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vnext.market.state import PairMarketState


@dataclass(frozen=True, slots=True)
class NarratorRequest:
    pair: str
    context_timeframes: tuple[str, ...]
    setup_timeframes: tuple[str, ...]
    execution_timeframes: tuple[str, ...]
    purpose: str = "ENTRY"
    depth: str = "STANDARD"
    include_statistics: bool = True
    include_indicators: tuple[str, ...] = ()
    include_child_path: bool = False
    focus_tags: tuple[str, ...] = ()
    excluded_timeframes: tuple[str, ...] = ()
    max_bars_per_timeframe: int = 32
    max_structure_events: int = 16
    max_zones: int = 12

    def __post_init__(self) -> None:
        if self.purpose not in {"ENTRY", "MANAGEMENT", "RESEARCH"}:
            raise ValueError("invalid narrator purpose")
        if self.depth not in {"COMPACT", "STANDARD", "DEEP"}:
            raise ValueError("invalid narrator depth")
        if min(self.max_bars_per_timeframe, self.max_structure_events, self.max_zones) <= 0:
            raise ValueError("narrator bounds must be positive")
        included = set(self.context_timeframes + self.setup_timeframes + self.execution_timeframes)
        if included.intersection(self.excluded_timeframes):
            raise ValueError("a timeframe cannot be both included and excluded")


class StoryNarrator:
    """Narrate supplied state only; no zone/structure discovery is performed."""

    def narrate(self, state: PairMarketState, request: NarratorRequest) -> dict[str, Any]:
        if state.pair != request.pair:
            raise ValueError("narrator request pair does not match market state")
        selected = {
            timeframe: _bounded_rows(state.timeframes[timeframe], request.max_bars_per_timeframe)
            for timeframe in request.context_timeframes + request.setup_timeframes + request.execution_timeframes
            if timeframe in state.timeframes and timeframe not in request.excluded_timeframes
        }
        direction = str(state.structure.get("direction") or "neutral")
        regime = str(state.structure.get("regime") or state.structure.get("state") or "unknown")
        story = f"{state.pair} at {state.time_frontier_utc.isoformat()}: structure is {regime} with direction {direction}."
        if state.zones:
            story += f" {len(state.zones)} supplied zone(s) are available for inspection."
        if state.structural_events:
            story += f" {len(state.structural_events)} causal structural event(s) are confirmed."
        result = {"schema_version": "STORY_V1", "request": {
            "pair": request.pair, "purpose": request.purpose, "depth": request.depth,
            "context_timeframes": list(request.context_timeframes),
            "setup_timeframes": list(request.setup_timeframes),
            "execution_timeframes": list(request.execution_timeframes),
            "focus_tags": list(request.focus_tags),
            "excluded_timeframes": list(request.excluded_timeframes),
            "max_bars_per_timeframe": request.max_bars_per_timeframe,
            "max_structure_events": request.max_structure_events,
            "max_zones": request.max_zones,
        },
            "pair": state.pair, "time_frontier_utc": state.time_frontier_utc.isoformat(),
            "facts": {"data_quality": dict(state.data_quality), "timeframes": selected,
                      "zones": [dict(zone) for zone in state.zones[-request.max_zones:]],
                      "structure": dict(state.structure),
                      "structural_events": [dict(event) for event in state.structural_events[-request.max_structure_events:]],
                      "relationships": [dict(row) for row in state.mtf_relationships]},
            "story": story, "authority": "facts_only_no_signal_generation",
            "strategy_focus": {"tags": list(request.focus_tags),
                               "included_timeframes": list(request.context_timeframes + request.setup_timeframes + request.execution_timeframes),
                               "excluded_timeframes": list(request.excluded_timeframes)},
        }
        if request.include_statistics:
            result["facts"]["statistics"] = dict(state.statistics)
        if request.include_indicators:
            result["facts"]["indicators"] = {key: state.indicators.get(key) for key in request.include_indicators}
        if request.include_child_path:
            result["facts"]["temporal_state"] = dict(state.temporal_state)
        return result


def _bounded_rows(value: Any, limit: int) -> Any:
    if isinstance(value, (list, tuple)):
        return [dict(row) if isinstance(row, Mapping) else row for row in value[-limit:]]
    return value
