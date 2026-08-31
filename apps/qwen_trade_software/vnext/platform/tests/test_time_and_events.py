from datetime import datetime, timezone

import pytest

from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier
from vnext.storage.ledger import InMemoryLedger, LedgerConflict


def event(event_id="e1", observed="2026-01-01T10:00:00Z", payload=None):
    return EventEnvelope(event_id, "M1_CANDLE", "XAUUSD", observed,
                         payload or {"close": 1}, "replay")


def test_frontier_rejects_future_evidence_and_backwards_motion():
    frontier = TimeFrontier.from_value("2026-01-01T10:00:00Z")
    assert frontier.permits("2026-01-01T10:00:00Z")
    with pytest.raises(ValueError):
        frontier.require("2026-01-01T10:00:01Z")
    with pytest.raises(ValueError):
        frontier.advance("2025-12-31T23:59:59Z")


def test_event_hash_is_stable_and_ledger_is_idempotent():
    ledger = InMemoryLedger()
    first = event()
    assert ledger.append(first) is True
    assert ledger.append(event()) is False
    assert ledger.read(pair="XAUUSD")[0].content_hash == first.content_hash


def test_event_id_collision_is_rejected():
    ledger = InMemoryLedger()
    ledger.append(event())
    with pytest.raises(LedgerConflict):
        ledger.append(event(payload={"close": 2}))


def test_event_cannot_validate_beyond_frontier():
    with pytest.raises(ValueError):
        InMemoryLedger().append(
            event(observed="2026-01-01T10:00:01Z"),
            frontier=TimeFrontier.from_value("2026-01-01T10:00:00Z"),
        )
