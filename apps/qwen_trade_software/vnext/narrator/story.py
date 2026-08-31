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

    def __post_init__(self) -> None:
        if self.purpose not in {"ENTRY", "MANAGEMENT", "RESEARCH"}:
            raise ValueError("invalid narrator purpose")
        if self.depth not in {"COMPACT", "STANDARD", "DEEP"}:
            raise ValueError("invalid narrator depth")


class StoryNarrator:
    """Narrate supplied state only; no zone/structure discovery is performed."""

    def narrate(self, state: PairMarketState, request: NarratorRequest) -> dict[str, Any]:
        if state.pair != request.pair:
            raise ValueError("narrator request pair does not match market state")
        selected = {tf: state.timeframes.get(tf) for tf in request.context_timeframes + request.setup_timeframes + request.execution_timeframes if tf in state.timeframes}
        direction = str(state.structure.get("direction") or "neutral")
        regime = str(state.structure.get("regime") or state.structure.get("state") or "unknown")
        story = f"{state.pair} at {state.time_frontier_utc.isoformat()}: structure is {regime} with direction {direction}."
        if state.zones:
            story += f" {len(state.zones)} supplied zone(s) are available for inspection."
        if state.structural_events:
            story += f" {len(state.structural_events)} causal structural event(s) are confirmed."
        result = {"schema_version": "STORY_V1", "request": request.__dict__ if hasattr(request, "__dict__") else {
            "pair": request.pair, "purpose": request.purpose, "depth": request.depth},
            "pair": state.pair, "time_frontier_utc": state.time_frontier_utc.isoformat(),
            "facts": {"data_quality": dict(state.data_quality), "timeframes": selected,
                      "zones": [dict(zone) for zone in state.zones],
                      "structure": dict(state.structure),
                      "relationships": [dict(row) for row in state.mtf_relationships]},
            "story": story, "authority": "facts_only_no_signal_generation",
        }
        if request.include_statistics:
            result["facts"]["statistics"] = dict(state.statistics)
        if request.include_indicators:
            result["facts"]["indicators"] = {key: state.indicators.get(key) for key in request.include_indicators}
        if request.include_child_path:
            result["facts"]["temporal_state"] = dict(state.temporal_state)
        return result
