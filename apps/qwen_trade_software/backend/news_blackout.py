"""No new entries around high-impact news.

2026-08-12 -- why
-----------------
Per-trade standard deviation in this system is 152 against a mean of -14. News
releases are where that tail comes from, and the system is unusually exposed to
them for three specific reasons:

  * An entry decision takes ~28s and the proposal TTL is 60s. On a release,
    price can travel several dollars inside that window, so the level the model
    reasoned about no longer exists by the time the order lands.
  * The whole method is level-and-response based -- "accepted close through
    support", "M15 wick rejection at level". A news spike does not respect
    levels, it gaps them. The core signal stops carrying information at exactly
    the moment volatility peaks.
  * Spreads widen. Position size is derived from a fixed risk budget, so a wider
    spread quietly worsens every fill.

Honest limit: this rule is NOT validated on our own trades. No news-event data
has ever been joined to our outcomes, so we cannot yet say whether news trades
were profitable. That is why every block is recorded (see blackout log) -- so in
a month the question can be answered from evidence instead of belief.

Scope, deliberately narrow
--------------------------
  * USD High-impact only, plus anything Fed/FOMC by title. Gold is
    USD-denominated. Today's feed also marks AUD "Cash Rate" and GBP "GDP m/m"
    as High; blocking on those would cost trading windows for releases gold
    barely notices.
  * ENTRIES only. Management is never gated -- see the note in should_block().
  * Fails OPEN. A stale or unreachable calendar must not stop a trading day.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CACHE_FILE = APP_DIR / "news-calendar.json"
LOG_DIR = APP_DIR / "logs"

FEED_URL = os.environ.get(
    "QWEN_NEWS_FEED_URL", "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
)

# Minutes either side of a release. Set by the operator on 2026-08-12.
BLACKOUT_MINUTES_BEFORE = int(os.environ.get("QWEN_NEWS_MINUTES_BEFORE", "15"))
BLACKOUT_MINUTES_AFTER = int(os.environ.get("QWEN_NEWS_MINUTES_AFTER", "15"))

# Which events matter for gold.
BLOCK_CURRENCIES = {"USD"}
BLOCK_IMPACTS = {"High"}
# Fed communication moves gold regardless of the tag the calendar gives it.
ALWAYS_BLOCK_TITLE = re.compile(r"\b(FOMC|Fed(eral)?\s+Funds|Fed\s+Chair|Powell)\b", re.I)

# Refuse a calendar older than this. A week-old file describes last week's
# events and would produce blackouts at the wrong times -- worse than none.
MAX_CACHE_AGE_HOURS = 36

NEWS_ENABLED = os.environ.get("QWEN_NEWS_BLACKOUT", "1") != "0"


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(stamp)).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def is_blocking_event(event: dict) -> bool:
    """Whether this calendar row is one we stand aside for."""
    title = str(event.get("title") or "")
    if ALWAYS_BLOCK_TITLE.search(title):
        return True
    return (
        str(event.get("country") or "").upper() in BLOCK_CURRENCIES
        and str(event.get("impact") or "") in BLOCK_IMPACTS
    )


def refresh_calendar(timeout: int = 20) -> dict:
    """Fetch the weekly calendar to the cache file.

    Called on a timer, NEVER from the entry path -- a network call inside the
    decision loop is a new way for entries to stall, and entry latency is
    already the binding constraint on this system.
    """
    try:
        request = urllib.request.Request(
            FEED_URL, headers={"User-Agent": "QuantLLMBot/1.0"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            events = json.loads(response.read().decode("utf-8"))
        if not isinstance(events, list):
            raise ValueError(f"expected a list, got {type(events).__name__}")

        payload = {
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": FEED_URL,
            "events": events,
        }
        CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")
        blocking = sum(1 for e in events if is_blocking_event(e))
        logging.info(
            "news calendar refreshed: %d events, %d blocking", len(events), blocking
        )
        return payload
    except Exception as error:
        logging.warning(
            "news calendar refresh FAILED (%s). Using the cached copy; trading "
            "continues.", error,
        )
        return load_calendar()


def load_calendar() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def calendar_age_hours(calendar: dict | None = None) -> float | None:
    calendar = calendar if calendar is not None else load_calendar()
    fetched = _parse(calendar.get("fetched_at_utc", ""))
    if not fetched:
        return None
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 3600.0


def active_event(now: datetime | None = None, calendar: dict | None = None) -> dict | None:
    """The blocking event whose window contains `now`, if any.

    Returns None when clear, when the calendar is unusable, or when the feature
    is switched off. Never raises: a calendar problem must not be able to stop
    trading.
    """
    if not NEWS_ENABLED:
        return None
    try:
        now = now or datetime.now(timezone.utc)
        calendar = calendar if calendar is not None else load_calendar()
        events = calendar.get("events") or []
        if not events:
            return None

        age = calendar_age_hours(calendar)
        if age is not None and age > MAX_CACHE_AGE_HOURS:
            # Deliberately fails OPEN and says so. A stale file lists last
            # week's release times, so honouring it would block at the wrong
            # moments -- confidently wrong is worse than off.
            logging.error(
                "ALARM news:calendar_stale :: calendar is %.1fh old (limit %dh). "
                "News blackout is NOT protecting entries. Refresh it.",
                age, MAX_CACHE_AGE_HOURS,
            )
            return None

        for event in events:
            if not is_blocking_event(event):
                continue
            when = _parse(event.get("date", ""))
            if not when:
                continue
            if (
                when - timedelta(minutes=BLACKOUT_MINUTES_BEFORE)
                <= now
                <= when + timedelta(minutes=BLACKOUT_MINUTES_AFTER)
            ):
                return {
                    "title": str(event.get("title") or "unnamed"),
                    "country": str(event.get("country") or ""),
                    "impact": str(event.get("impact") or ""),
                    "event_time_utc": when.isoformat(),
                    "window_start_utc": (
                        when - timedelta(minutes=BLACKOUT_MINUTES_BEFORE)
                    ).isoformat(),
                    "window_end_utc": (
                        when + timedelta(minutes=BLACKOUT_MINUTES_AFTER)
                    ).isoformat(),
                    "minutes_to_event": round((when - now).total_seconds() / 60.0, 1),
                }
        return None
    except Exception:
        logging.exception("news:blackout_check_failed — failing open")
        return None


def upcoming(limit: int = 3, now: datetime | None = None) -> list[dict]:
    """Next blocking events, for the dashboard and the startup line."""
    now = now or datetime.now(timezone.utc)
    rows = []
    for event in load_calendar().get("events") or []:
        if not is_blocking_event(event):
            continue
        when = _parse(event.get("date", ""))
        if when and when >= now:
            rows.append(
                {
                    "title": str(event.get("title") or ""),
                    "country": str(event.get("country") or ""),
                    "impact": str(event.get("impact") or ""),
                    "event_time_utc": when.isoformat(),
                    "minutes_away": round((when - now).total_seconds() / 60.0),
                }
            )
    rows.sort(key=lambda r: r["event_time_utc"])
    return rows[:limit]


def record_block(event: dict, proposal_id: str | None = None) -> None:
    """Write every blocked entry to its own log.

    This matters more than the rule itself. A blackout you cannot measure is a
    belief, not a strategy -- without this you would simply have fewer trades
    and no way to tell whether that helped. Each row names the event, so the
    skipped windows can later be joined to what price actually did.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        path = LOG_DIR / f"news-blackout-{datetime.now():%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "event": "entry_blocked_by_news",
                        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                        "proposal_id": proposal_id,
                        **event,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
    except Exception:
        logging.exception("news:block_record_failed")
