"""Immutable vNext pair-market-state boundary.

This is a shadow/replay contract only.  It composes deterministic facts for a
strategy or narrator; it cannot create a trade candidate or call execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "PAIR_MARKET_STATE_V1"
TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
_TIME_KEYS = ("event_time_utc", "observed_at", "confirmation_time_utc", "time_utc")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _parse_utc(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value!r}")
    return parsed


def _assert_not_after_frontier(rows: Sequence[Mapping[str, Any]], frontier: datetime) -> None:
    for row in rows:
        for key in _TIME_KEYS:
            value = row.get(key)
            if value is not None and _parse_utc(str(value)) > frontier:
                raise ValueError(f"future evidence at {value!r} exceeds time frontier")


@dataclass(frozen=True)
class PairMarketState:
    """Frozen, replayable snapshot of facts known at one UTC frontier."""

    pair: str
    time_frontier: str
    data_quality: Mapping[str, Any]
    timeframes: Mapping[str, Any]
    zones: tuple[Any, ...]
    structure: tuple[Any, ...]
    structural_events: tuple[Any, ...]
    mtf_relationships: tuple[Any, ...]
    temporal_state: Mapping[str, Any]
    statistics: Mapping[str, Any]
    indicators: Mapping[str, Any]
    active_levels: tuple[Any, ...]
    graph_references: tuple[Any, ...]
    versions: Mapping[str, str]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly copy without exposing mutable internals."""
        return _thaw({
            "schema_version": SCHEMA_VERSION,
            "pair": self.pair,
            "time_frontier": self.time_frontier,
            "data_quality": self.data_quality,
            "timeframes": self.timeframes,
            "zones": self.zones,
            "structure": self.structure,
            "structural_events": self.structural_events,
            "mtf_relationships": self.mtf_relationships,
            "temporal_state": self.temporal_state,
            "statistics": self.statistics,
            "indicators": self.indicators,
            "active_levels": self.active_levels,
            "graph_references": self.graph_references,
            "versions": self.versions,
        })


def build_pair_market_state(
    pair: str,
    time_frontier: str,
    *,
    data_quality: Mapping[str, Any] | None = None,
    timeframes: Mapping[str, Any] | None = None,
    zones: Sequence[Mapping[str, Any]] = (),
    structure: Sequence[Mapping[str, Any]] = (),
    structural_events: Sequence[Mapping[str, Any]] = (),
    mtf_relationships: Sequence[Mapping[str, Any]] = (),
    temporal_state: Mapping[str, Any] | None = None,
    statistics: Mapping[str, Any] | None = None,
    indicators: Mapping[str, Any] | None = None,
    active_levels: Sequence[Mapping[str, Any]] = (),
    graph_references: Sequence[Mapping[str, Any]] = (),
    versions: Mapping[str, str] | None = None,
) -> PairMarketState:
    """Compose a validated state without selecting direction or execution."""
    if not pair.strip():
        raise ValueError("pair is required")
    frontier = _parse_utc(time_frontier)
    frames = dict(timeframes or {tf: {} for tf in TIMEFRAMES})
    invalid = sorted(set(frames) - set(TIMEFRAMES))
    if invalid:
        raise ValueError(f"unsupported timeframe(s): {', '.join(invalid)}")

    rows = tuple(dict(row) for group in (zones, structure, structural_events,
                                         mtf_relationships, active_levels,
                                         graph_references) for row in group)
    _assert_not_after_frontier(rows, frontier)
    return PairMarketState(
        pair=pair,
        time_frontier=frontier.isoformat().replace("+00:00", "Z"),
        data_quality=_freeze(dict(data_quality or {})),
        timeframes=_freeze(frames),
        zones=_freeze(tuple(dict(row) for row in zones)),
        structure=_freeze(tuple(dict(row) for row in structure)),
        structural_events=_freeze(tuple(dict(row) for row in structural_events)),
        mtf_relationships=_freeze(tuple(dict(row) for row in mtf_relationships)),
        temporal_state=_freeze(dict(temporal_state or {})),
        statistics=_freeze(dict(statistics or {})),
        indicators=_freeze(dict(indicators or {})),
        active_levels=_freeze(tuple(dict(row) for row in active_levels)),
        graph_references=_freeze(tuple(dict(row) for row in graph_references)),
        versions=_freeze({"state_version": SCHEMA_VERSION, **dict(versions or {})}),
    )
