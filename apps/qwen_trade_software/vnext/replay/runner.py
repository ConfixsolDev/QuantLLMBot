"""Replay immutable events in causal order with a supplied reducer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier


@dataclass(frozen=True, slots=True)
class ReplayResult:
    processed: int
    rejected: int
    state: Any
    event_ids: tuple[str, ...]


def replay(events: Iterable[EventEnvelope], *, frontier: TimeFrontier,
           reducer: Callable[[Any, EventEnvelope], Any], initial: Any) -> ReplayResult:
    state = initial
    processed = rejected = 0
    event_ids: list[str] = []
    for event in sorted(events, key=lambda row: (row.observed_at_utc, row.event_id)):
        try:
            event.validate_against(frontier)
        except ValueError:
            rejected += 1
            continue
        state = reducer(state, event)
        processed += 1
        event_ids.append(event.event_id)
    return ReplayResult(processed, rejected, state, tuple(event_ids))
