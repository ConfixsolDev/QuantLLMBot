"""Dependency-injected event ledger for the clean-room runtime."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier


class LedgerConflict(ValueError):
    """Raised when the same event ID is reused with different content."""


class InMemoryLedger:
    """Deterministic test/replay ledger; production adapter will be TimescaleDB."""

    def __init__(self) -> None:
        self._events: dict[str, EventEnvelope] = {}

    def append(self, event: EventEnvelope, *, frontier: TimeFrontier | None = None) -> bool:
        if frontier is not None:
            event.validate_against(frontier)
        previous = self._events.get(event.event_id)
        if previous is not None:
            if previous.content_hash != event.content_hash:
                raise LedgerConflict(f"event ID collision: {event.event_id}")
            return False
        self._events[event.event_id] = event
        return True

    def append_many(self, events: Iterable[EventEnvelope], *, frontier: TimeFrontier | None = None) -> int:
        return sum(self.append(event, frontier=frontier) for event in events)

    def read(self, *, pair: str | None = None, event_type: str | None = None,
             since: datetime | None = None) -> list[EventEnvelope]:
        rows = list(self._events.values())
        if pair is not None:
            rows = [row for row in rows if row.pair == pair]
        if event_type is not None:
            rows = [row for row in rows if row.event_type == event_type]
        if since is not None:
            rows = [row for row in rows if row.observed_at_utc >= since]
        return sorted(rows, key=lambda row: (row.observed_at_utc, row.event_id))

    def replay(self, frontier: TimeFrontier) -> list[EventEnvelope]:
        return [event for event in self.read() if frontier.permits(event.observed_at_utc)]
