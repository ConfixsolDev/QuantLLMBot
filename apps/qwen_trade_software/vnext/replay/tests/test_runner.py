from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier
from vnext.replay.runner import replay


def test_replay_orders_events_and_rejects_future():
    events = [EventEnvelope("b", "x", "XAUUSD", "2026-01-01T00:00:02Z", {"n": 2}, "test"), EventEnvelope("a", "x", "XAUUSD", "2026-01-01T00:00:01Z", {"n": 1}, "test")]
    result = replay(events, frontier=TimeFrontier.from_value("2026-01-01T00:00:01Z"), reducer=lambda state, event: state + [event.event_id], initial=[])
    assert result.processed == 1
    assert result.rejected == 1
    assert result.state == ["a"]
