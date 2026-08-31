from __future__ import annotations

from datetime import datetime, timezone

from vnext.platform.events import EventEnvelope
from vnext.storage.persistence import VNextPersistence


class Ledger:
    def __init__(self): self.events = []
    def ensure_schema(self): pass
    def append(self, event): self.events.append(event); return True


class Projection:
    def __init__(self): self.events = []
    def project(self, events): self.events.extend(events); return len(list(events))


class Memory:
    def __init__(self): self.values = {}
    def put(self, key, value): self.values[key] = value


def test_durable_append_precedes_projection_and_context_is_working_memory():
    ledger, projection, memory = Ledger(), Projection(), Memory()
    persistence = VNextPersistence(ledger=ledger, projection=projection, working_memory=memory)
    event = EventEnvelope("e1", "bar", "XAUUSD", datetime.now(timezone.utc), {"close": 1}, "test")
    assert persistence.append_events([event]) == 1
    assert ledger.events == [event]
    assert projection.events == [event]
    persistence.publish_context("state", {"state_hash": "h1"})
    assert memory.values["state"]["state_hash"] == "h1"


def test_empty_batch_does_not_touch_projection():
    projection = Projection()
    VNextPersistence(ledger=Ledger(), projection=projection, working_memory=Memory()).append_events([])
    assert projection.events == []
