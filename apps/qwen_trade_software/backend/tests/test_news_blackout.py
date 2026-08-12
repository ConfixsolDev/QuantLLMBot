"""No new entries around high-impact news. Entries only.

2026-08-12. Approved at +/-15 minutes, USD High plus Fed/FOMC by title.

The rule is NOT validated on this system's own trades -- no news data has ever
been joined to our outcomes. That is exactly why every block is recorded: in a
month the question "did standing aside help" can be answered from evidence
rather than belief. These tests lock the mechanics, not the premise.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import news_blackout as nb  # noqa: E402

CPI = "2026-08-12T08:30:00-04:00"          # 12:30 UTC
EVENTS = [
    {"title": "CPI m/m", "country": "USD", "date": CPI, "impact": "High"},
    {"title": "Building Permits m/m", "country": "CAD",
     "date": "2026-08-12T08:30:00-04:00", "impact": "Low"},
    {"title": "Cash Rate", "country": "AUD",
     "date": "2026-08-12T09:00:00-04:00", "impact": "High"},
    {"title": "Crude Oil Inventories", "country": "USD",
     "date": "2026-08-12T10:30:00-04:00", "impact": "Low"},
    {"title": "FOMC Member Hammack Speaks", "country": "USD",
     "date": "2026-08-13T08:15:00-04:00", "impact": "Low"},
]


def cal(events=None, age_hours=0.0):
    fetched = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return {"fetched_at_utc": fetched.isoformat(),
            "events": EVENTS if events is None else events}


def at(hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(2026, 8, 12, int(h), int(m), tzinfo=timezone.utc)


# --- which events count ----------------------------------------------------

def test_usd_high_blocks():
    assert nb.is_blocking_event(EVENTS[0])


def test_non_usd_high_does_not_block():
    """Gold is USD-denominated. An RBA rate decision moves it far less, and
    blocking on every High event regardless of currency costs trading windows
    for releases gold barely notices."""
    assert not nb.is_blocking_event(EVENTS[2])


def test_usd_low_does_not_block():
    assert not nb.is_blocking_event(EVENTS[3])


def test_fed_speakers_block_despite_a_low_tag():
    """Fed communication moves gold whatever impact tag the calendar gives it."""
    assert nb.is_blocking_event(EVENTS[4])


# --- the window ------------------------------------------------------------

@pytest.mark.parametrize("when,blocked", [
    ("12:00", False),   # 30 min before — clear
    ("12:14", False),   # one minute outside
    ("12:15", True),    # window opens
    ("12:30", True),    # the release
    ("12:45", True),    # window closes
    ("12:46", False),   # clear again
])
def test_window_boundaries(when, blocked):
    event = nb.active_event(now=at(when), calendar=cal())
    assert (event is not None) is blocked, when


def test_the_blocking_event_is_named():
    """A block that does not say what caused it cannot be reviewed later."""
    event = nb.active_event(now=at("12:20"), calendar=cal())
    assert event["title"] == "CPI m/m"
    assert event["country"] == "USD"
    assert event["minutes_to_event"] == pytest.approx(10.0)


# --- failure modes: every one of them fails OPEN ---------------------------

def test_missing_calendar_does_not_block():
    """No calendar must never mean no trading day."""
    assert nb.active_event(now=at("12:30"), calendar={}) is None


def test_stale_calendar_does_not_block():
    """A week-old file lists last week's release times. Honouring it would
    black out the wrong minutes -- confidently wrong is worse than off."""
    stale = cal(age_hours=nb.MAX_CACHE_AGE_HOURS + 1)
    assert nb.active_event(now=at("12:30"), calendar=stale) is None


def test_malformed_rows_are_skipped_not_fatal():
    bad = [{"title": "x", "country": "USD", "date": "not-a-date", "impact": "High"},
           EVENTS[0]]
    assert nb.active_event(now=at("12:30"), calendar=cal(bad)) is not None


def test_feature_switch_off(monkeypatch):
    monkeypatch.setattr(nb, "NEWS_ENABLED", False)
    assert nb.active_event(now=at("12:30"), calendar=cal()) is None


# --- entries only ----------------------------------------------------------

def test_management_is_never_gated_by_news():
    """An open position has money at risk and needs looking after THROUGH a
    release more than at any other time. Abandoning a live trade because a
    calendar entry exists would be a worse decision than the one avoided.
    """
    source = (BACKEND / "trade_management.py").read_text(encoding="utf-8")
    assert "news_blackout" not in source, (
        "trade_management must never consult the news gate"
    )


def test_the_gate_is_on_the_entry_path_only():
    source = (BACKEND / "reviewer.py").read_text(encoding="utf-8")
    assert "news_blackout_active()" in source
    # and it must sit in the entry cycle, before the deal sheet is generated
    assert source.index("news_blackout_active()") < source.index(
        "generate_automatic_deal_sheet()"
    )


def test_the_fetch_is_not_on_the_decision_path():
    """A network call inside the entry loop is a new way for entries to stall,
    and entry latency is already the binding constraint here."""
    source = (BACKEND / "reviewer.py").read_text(encoding="utf-8")
    start = source.index("def news_blackout_active")
    body = source[start:start + 1800]
    assert "refresh_calendar" not in body


# --- the record ------------------------------------------------------------

def test_blocks_are_recorded(tmp_path, monkeypatch):
    """A blackout you cannot measure is a belief, not a strategy."""
    monkeypatch.setattr(nb, "LOG_DIR", tmp_path)
    event = nb.active_event(now=at("12:20"), calendar=cal())
    nb.record_block(event, proposal_id="paper-x")

    written = list(tmp_path.glob("news-blackout-*.jsonl"))
    assert written, "the block must leave a record"
    row = json.loads(written[0].read_text(encoding="utf-8").strip())
    assert row["event"] == "entry_blocked_by_news"
    assert row["title"] == "CPI m/m"
    assert row["proposal_id"] == "paper-x"


def test_recording_failure_never_raises(monkeypatch):
    monkeypatch.setattr(nb, "LOG_DIR", Path("/nonexistent/\0bad"))
    nb.record_block({"title": "x"})  # must not raise
