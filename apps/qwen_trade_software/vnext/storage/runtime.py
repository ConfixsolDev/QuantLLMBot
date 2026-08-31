"""Small dependency-injected storage facade for the modular V2 path."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from runtime_store import RuntimeStore


class DurableRuntime:
    """Expose durable events/state without allowing storage to make decisions."""

    def __init__(self, store: RuntimeStore | None = None) -> None:
        self.store = store or RuntimeStore()

    @property
    def enabled(self) -> bool:
        return self.store.enabled

    def ensure_ready(self) -> None:
        self.store.ensure_schema()

    def event(self, owner: str, event_name: str, payload: dict[str, Any], *, level: str = "INFO") -> None:
        self.store.append_event(owner=owner, level=level,
                                message=f"runtime event: {event_name}",
                                event_name=event_name, payload=payload)

    def state(self, key: str, payload: dict[str, Any], *, owner: str) -> None:
        self.store.put_state(key, payload, owner=owner)

    def read_state(self, key: str) -> dict[str, Any] | None:
        return self.store.get_state(key)

    def events(self, *, owner: str | None = None,
               event_name: str | None = None,
               since: datetime | None = None) -> list[dict[str, Any]]:
        return self.store.events(owner=owner, event_name=event_name, since=since)
