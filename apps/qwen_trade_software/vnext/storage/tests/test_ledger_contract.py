from datetime import datetime, timezone

from vnext.platform.events import EventEnvelope


def test_event_identity_is_stable_for_idempotent_retries():
    first = EventEnvelope("same", "bar", "XAUUSD", datetime(2026, 1, 1, tzinfo=timezone.utc), {"close": 1}, "test")
    retry = EventEnvelope("same", "bar", "XAUUSD", datetime(2026, 1, 1, tzinfo=timezone.utc), {"close": 1}, "test")
    assert first.content_hash == retry.content_hash


def test_event_identity_detects_payload_mutation():
    first = EventEnvelope("same", "bar", "XAUUSD", datetime(2026, 1, 1, tzinfo=timezone.utc), {"close": 1}, "test")
    changed = EventEnvelope("same", "bar", "XAUUSD", datetime(2026, 1, 1, tzinfo=timezone.utc), {"close": 2}, "test")
    assert first.content_hash != changed.content_hash
