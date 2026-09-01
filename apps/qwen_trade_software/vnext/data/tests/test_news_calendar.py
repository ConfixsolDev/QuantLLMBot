import json
from datetime import datetime, timezone

from vnext.data.news_calendar import DailyNewsCalendar
from vnext.storage.working_memory import WorkingMemory


class Redis:
    def __init__(self): self.rows = {}; self.ttls = {}
    def setex(self, name, time, value): self.rows[name] = value; self.ttls[name] = time
    def get(self, name): return self.rows.get(name)
    def delete(self, name): self.rows.pop(name, None)


class Response:
    def __init__(self, data): self.data = data
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.data


class DurableStore:
    def __init__(self): self.events = []; self.payloads = {}
    def append_events(self, events):
        self.events.extend(events)
        for event in events: self.payloads[event.payload["day_utc"]] = dict(event.payload)
        return len(events)
    def latest_news_calendar(self, day_utc): return self.payloads.get(day_utc)


def test_calendar_fetches_once_and_applies_red_and_brown_windows_from_redis():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    rows = [{"country": "USD", "impact": "High", "title": "NFP", "date": "2026-01-01T12:20:00Z"},
            {"country": "USD", "impact": "Medium", "title": "JOLTS", "date": "2026-01-01T14:00:00Z"}]
    calendar = DailyNewsCalendar(WorkingMemory(Redis(), ttl_seconds=86400),
                                 opener=lambda *args, **kwargs: Response(json.dumps(rows).encode()))
    payload = calendar.refresh(now=now)
    assert len(payload["events"]) == 2
    assert calendar.memory.client.ttls[calendar.memory.prefix + calendar.key(now)] == 36 * 60 * 60
    assert calendar.gate(now=now).reason == "news_blackout"
    assert calendar.gate(now=datetime(2026, 1, 1, 13, 46, tzinfo=timezone.utc)).reason == "news_blackout"
    assert calendar.gate(now=datetime(2026, 1, 1, 15, tzinfo=timezone.utc)).allowed


def test_missing_calendar_fails_closed_without_network_on_entry_path():
    calendar = DailyNewsCalendar(WorkingMemory(Redis(), ttl_seconds=86400))
    assert calendar.gate(now=datetime(2026, 1, 1, tzinfo=timezone.utc)).reason == "calendar_missing"


def test_calendar_is_durable_and_rehydrates_after_cache_loss():
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    rows = [{"country": "USD", "impact": "Medium", "title": "JOLTS", "date": "2026-01-01T14:00:00Z"}]
    durable = DurableStore()
    first_memory = WorkingMemory(Redis(), ttl_seconds=120)
    first = DailyNewsCalendar(first_memory, durable_store=durable,
                              opener=lambda *args, **kwargs: Response(json.dumps(rows).encode()))
    first.refresh(now=now)
    assert len(durable.events) == 1
    second = DailyNewsCalendar(WorkingMemory(Redis(), ttl_seconds=120), durable_store=durable)
    assert second.gate(now=datetime(2026, 1, 1, 13, 50, tzinfo=timezone.utc)).reason == "news_blackout"
    assert second.memory.client.ttls[second.memory.prefix + second.key(now)] == 36 * 60 * 60
