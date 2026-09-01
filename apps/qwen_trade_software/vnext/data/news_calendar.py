"""Cached USD economic-calendar gate; network access is never on the entry path."""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol
from urllib import request

from vnext.platform.events import EventEnvelope
from vnext.storage.working_memory import WorkingMemory


FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CALENDAR_SCHEMA = "USD_NEWS_CALENDAR_V1"


@dataclass(frozen=True, slots=True)
class NewsGate:
    allowed: bool
    reason: str
    event: Mapping[str, Any] | None = None


class DurableCalendarStore(Protocol):
    def append_events(self, events: list[EventEnvelope]) -> int: ...
    def latest_news_calendar(self, day_utc: str) -> dict[str, Any] | None: ...


class DailyNewsCalendar:
    """Fetch once, cache a complete UTC day, and fail closed when unavailable."""

    # The calendar is refreshed once per UTC day, so its cache must outlive
    # the short-lived context TTL used for ordinary working memory.
    CACHE_TTL_SECONDS = 36 * 60 * 60

    def __init__(self, memory: WorkingMemory, *, url: str = FEED_URL,
                 opener: Callable[..., Any] = request.urlopen,
                 durable_store: DurableCalendarStore | None = None) -> None:
        self.memory, self.url, self.opener, self.durable_store = memory, url, opener, durable_store

    @staticmethod
    def key(now: datetime) -> str:
        return "news:USD:" + _utc(now).date().isoformat()

    def refresh(self, *, now: datetime | None = None, timeout_seconds: float = 20.0) -> dict[str, Any]:
        current = _utc(now or datetime.now(timezone.utc))
        req = request.Request(self.url, headers={"User-Agent": "QuantLLMBot-V2/1.0"})
        with self.opener(req, timeout=timeout_seconds) as response:
            rows = json.loads(response.read().decode("utf-8"))
        if not isinstance(rows, list):
            raise ValueError("calendar source did not return an event list")
        events = [_normalize(row) for row in rows if _relevant_today(row, current)]
        payload = {"schema_version": CALENDAR_SCHEMA, "day_utc": current.date().isoformat(),
                   "fetched_at_utc": current.isoformat(), "source": self.url, "events": events}
        if self.durable_store is not None:
            observed = datetime.now(timezone.utc)
            event_id = hashlib.sha256(
                f"NEWS_CALENDAR_REFRESHED|{observed.isoformat()}|{current.date().isoformat()}".encode()
            ).hexdigest()[:24]
            self.durable_store.append_events([
                EventEnvelope(event_id, "NEWS_CALENDAR_REFRESHED", "SYSTEM", observed,
                              payload, "vnext_news_calendar")
            ])
        self.memory.put(self.key(current), payload, ttl_seconds=self.CACHE_TTL_SECONDS)
        return payload

    def gate(self, *, now: datetime | None = None) -> NewsGate:
        current = _utc(now or datetime.now(timezone.utc))
        payload = self.memory.get(self.key(current))
        if payload is None and self.durable_store is not None:
            payload = self.durable_store.latest_news_calendar(current.date().isoformat())
            if isinstance(payload, Mapping):
                self.memory.put(self.key(current), dict(payload), ttl_seconds=self.CACHE_TTL_SECONDS)
        if not isinstance(payload, Mapping) or payload.get("schema_version") != CALENDAR_SCHEMA:
            return NewsGate(False, "calendar_missing")
        fetched = _parse(payload.get("fetched_at_utc"))
        if fetched is None or current - fetched > timedelta(hours=30):
            return NewsGate(False, "calendar_stale")
        for event in payload.get("events", ()):
            when = _parse(event.get("event_time_utc")) if isinstance(event, Mapping) else None
            if when is None:
                continue
            minutes = 30 if event.get("impact") == "High" else 15
            if when - timedelta(minutes=minutes) <= current <= when + timedelta(minutes=minutes):
                return NewsGate(False, "news_blackout", event)
        return NewsGate(True, "calendar_clear")


def _relevant_today(row: Any, now: datetime) -> bool:
    if not isinstance(row, Mapping) or str(row.get("country", "")).upper() != "USD":
        return False
    if str(row.get("impact", "")) not in {"High", "Medium"}:
        return False
    when = _parse(row.get("date"))
    return when is not None and when.date() == now.date()


def _normalize(row: Mapping[str, Any]) -> dict[str, Any]:
    when = _parse(row.get("date"))
    assert when is not None
    return {"title": str(row.get("title") or ""), "impact": str(row.get("impact") or ""),
            "event_time_utc": when.isoformat()}


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
