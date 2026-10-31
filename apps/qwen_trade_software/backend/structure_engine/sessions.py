"""Session and prior-day highs/lows — where resting liquidity (stops) sits.

Traders park stop orders just beyond obvious extremes: the Asian range, the
London high, yesterday's low. Price is drawn to those pools, so they are
"liquidity levels". This module tracks them from M1 bars.

FORMING vs CONFIRMED (Rule 5)
-----------------------------
* While a session is open, its running high/low is FORMING: it can still
  change, so it is only exposed in ``snapshot()['forming']``.
* The moment the session's last minute closes, its high/low becomes a
  CONFIRMED level and is emitted once as a ``session_level`` event.
The same applies to the trading day (``prior_day_level`` at day close).

Windows come from config ``sessions.windows_utc`` as [start_hour, end_hour)
in UTC, within one day starting at ``day_start_utc_hour``. Default:
ASIA 00-07, LONDON 07-13, NEW_YORK 13-21 UTC. A minute outside every window
(21:00-24:00 here) belongs to no session but still counts for the day.

If data has a gap (weekend), a session or day is confirmed by the first bar
that arrives after it ended, with ``complete: false`` if minutes were missing.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .bars import Bar

DAY = 86_400


@dataclass
class _Range:
    """A running high/low over a time window."""
    name: str
    start: int           # window start (UTC epoch)
    end: int             # window end (exclusive)
    high: float
    low: float
    high_time: int
    low_time: int
    minutes: int = 1

    def add(self, bar: Bar) -> None:
        if bar.high > self.high:
            self.high, self.high_time = bar.high, bar.time
        if bar.low < self.low:
            self.low, self.low_time = bar.low, bar.time
        self.minutes += 1

    def as_dict(self) -> dict:
        expected = (self.end - self.start) // 60
        return {"name": self.name, "start": self.start, "end": self.end,
                "high": self.high, "low": self.low, "high_time": self.high_time,
                "low_time": self.low_time, "minutes": self.minutes,
                "complete": self.minutes >= expected}


class SessionTracker:
    def __init__(self, cfg: dict) -> None:
        s = cfg["sessions"]
        self.day_offset = s["day_start_utc_hour"] * 3600
        self.windows = sorted(((v[0] * 3600, v[1] * 3600, k) for k, v in s["windows_utc"].items()))
        self.session: _Range | None = None     # forming session
        self.day: _Range | None = None         # forming day
        self.levels: deque[dict] = deque(maxlen=s["history"] * (len(self.windows) + 1))

    def _day_start(self, t: int) -> int:
        return (t - self.day_offset) // DAY * DAY + self.day_offset

    def _window_of(self, t: int) -> tuple[str, int, int] | None:
        d0 = self._day_start(t)
        for start, end, name in self.windows:
            if d0 + start <= t < d0 + end:
                return name, d0 + start, d0 + end
        return None

    def update(self, bar: Bar, now: int) -> list[tuple[str, dict]]:
        """Feed one closed M1 bar. Returns (event_kind, level_dict) pairs."""
        out: list[tuple[str, dict]] = []
        # 1) Close anything that ended before this bar (data gap case).
        if self.session and bar.time >= self.session.end:
            out.append(("session_level", self._confirm_session()))
        if self.day and bar.time >= self.day.end:
            out.append(("prior_day_level", self._confirm_day()))
        # 2) Add the bar to the forming day and session.
        if self.day is None:
            d0 = self._day_start(bar.time)
            self.day = _Range("DAY", d0, d0 + DAY, bar.high, bar.low, bar.time, bar.time)
        else:
            self.day.add(bar)
        win = self._window_of(bar.time)
        if win and self.session is None:
            name, start, end = win
            self.session = _Range(name, start, end, bar.high, bar.low, bar.time, bar.time)
        elif win and self.session:
            self.session.add(bar)
        # 3) This bar was the last minute of the session / day -> confirm now.
        if self.session and now >= self.session.end:
            out.append(("session_level", self._confirm_session()))
        if self.day and now >= self.day.end:
            out.append(("prior_day_level", self._confirm_day()))
        return out

    def _confirm_session(self) -> dict:
        level = self.session.as_dict()
        self.session = None
        self.levels.append(level)
        return level

    def _confirm_day(self) -> dict:
        level = self.day.as_dict()
        self.day = None
        self.levels.append(level)
        return level

    def confirmed_prices(self) -> list[float]:
        """Every confirmed high and low (scoring uses these as liquidity)."""
        return [p for lv in self.levels for p in (lv["high"], lv["low"])]

    def forming(self) -> dict:
        return {"session": self.session.as_dict() if self.session else None,
                "day": self.day.as_dict() if self.day else None}
