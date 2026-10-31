"""Market clock: which candle a moment belongs to.

Most timeframes are cut on plain UTC boundaries (an M30 candle opens at :00
and :30 UTC). Brokers use whole-hour offsets, so M1 ... H1 candles are the
same on every clock.

H4 is different. Where an H4 candle starts decides what its "close" is, and
traders watch the New York H4 closes. Config ``alignment`` therefore builds
H4 from CLOSED H1 candles, cut at New York local hours
02, 06, 10, 14, 18, 22 — the grid that starts at the 18:00 NY gold session
open:

    New York (EDT, summer)  18:00 22:00 02:00 06:00 10:00 14:00
    UTC                     22:00 02:00 06:00 10:00 14:00 18:00
    New York (EST, winter)  18:00 22:00 02:00 06:00 10:00 14:00
    UTC                     23:00 03:00 07:00 11:00 15:00 19:00

Daylight saving is handled here with the US rule (since 2007): EDT from the
2nd Sunday of March 02:00 local to the 1st Sunday of November 02:00 local.
Standard library only, no tz database needed (Windows Python has none by
default). The switches happen on Sunday 02:00 New York, while gold is
closed, so no trading candle is ever cut in half by them.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

HOUR = 3600
DAY = 86_400


def _nth_sunday_utc(year: int, month: int, n: int, hour_utc: int) -> int:
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    offset = (6 - first.weekday()) % 7          # Monday=0 ... Sunday=6
    day = first + timedelta(days=offset + 7 * (n - 1), hours=hour_utc)
    return int(day.timestamp())


def new_york_offset_hours(utc_epoch: int) -> int:
    """UTC offset of New York at this instant: -4 (EDT) or -5 (EST)."""
    year = datetime.fromtimestamp(utc_epoch, tz=timezone.utc).year
    if year < 2007:
        raise ValueError("US DST rule implemented from 2007 onward")
    start = _nth_sunday_utc(year, 3, 2, 7)       # 02:00 EST = 07:00 UTC
    end = _nth_sunday_utc(year, 11, 1, 6)        # 02:00 EDT = 06:00 UTC
    return -4 if start <= utc_epoch < end else -5


TIMEZONES = {
    "UTC": lambda t: 0,
    "America/New_York": new_york_offset_hours,
}


def anchored_bucket(t: int, minutes: int, open_hours_local: list[int], tz: str) -> tuple[int, int]:
    """(start_utc, end_utc) of the candle containing UTC moment ``t``.

    The candle opens at the latest local ``open_hours_local`` hour at or
    before t's local time.
    """
    offset_of = TIMEZONES[tz]
    off = offset_of(t) * HOUR
    local = t + off
    day = local - local % DAY
    starts = sorted([day + h * HOUR for h in open_hours_local] +
                    [day - DAY + h * HOUR for h in open_hours_local])
    start_local = max(s for s in starts if s <= local)
    start_utc = start_local - off
    end_local = start_local + minutes * 60
    end_utc = end_local - offset_of(end_local - off) * HOUR
    return start_utc, end_utc


def utc_bucket(t: int, minutes: int) -> tuple[int, int]:
    """Plain UTC-aligned candle (M1 ... H1, and H4 when not anchored)."""
    sec = minutes * 60
    start = t - t % sec
    return start, start + sec
