"""Bars: the only input the structure engine understands.

Everything starts from CLOSED one-minute (M1) bars. Higher timeframes (M5 ...
H4) are built here by aggregation, never fetched separately, so that live
trading and back-testing see exactly the same higher-timeframe candles:

    M1 bar --> Aggregator("M5")  --> closed M5 bar (when its last minute closes)
          \-> Aggregator("H1")  --> closed H1 bar
          \-> ...

Time convention (used everywhere in this package)
-------------------------------------------------
* ``bar.time`` is the bar's OPEN time as an integer UTC epoch in seconds.
* ``bar.close_time`` = open + duration. A bar is knowable only at close_time.
* Buckets are aligned to UTC midnight (an H4 bar opens at 00, 04, 08 ... UTC).

When does a higher-timeframe bar close?
---------------------------------------
Normally when the M1 bar covering its LAST minute arrives (e.g. the 10:59 M1
bar closes the 10:00 H1 bar at 11:00). If minutes are missing (weekend, data
gap) the bucket is closed by the first M1 bar of a LATER bucket instead; the
partial bar is still emitted (``m1_count < minutes`` tells you it was partial)
and is known only at that later bar's close. Either way nothing is ever
emitted before it could have been known live — the no-repaint guarantee.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Iterator

SECONDS_PER_MINUTE = 60


@dataclass(slots=True)
class Bar:
    """One OHLCV candle. ``minutes`` is its duration (1 for M1)."""

    time: int            # open time, UTC epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0  # tick volume (MT5 'tick_volume')
    minutes: int = 1
    m1_count: int = 1    # how many M1 bars were merged into it
    tf: str = "M1"

    @property
    def close_time(self) -> int:
        return self.time + self.minutes * SECONDS_PER_MINUTE

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    def as_dict(self) -> dict:
        return {"tf": self.tf, "time": self.time, "open": self.open, "high": self.high,
                "low": self.low, "close": self.close, "volume": self.volume,
                "m1_count": self.m1_count}


class BarError(ValueError):
    """Malformed bar (bad OHLC, misaligned or out-of-order time)."""


def validate_m1(bar: Bar, previous_time: int | None) -> None:
    """Reject anything that would make results unreproducible."""
    if bar.time % SECONDS_PER_MINUTE:
        raise BarError(f"M1 bar time {bar.time} is not on a minute boundary")
    if previous_time is not None and bar.time <= previous_time:
        raise BarError(f"bars must be strictly increasing in time ({bar.time} after {previous_time})")
    if not (bar.low <= min(bar.open, bar.close) and bar.high >= max(bar.open, bar.close)):
        raise BarError(f"inconsistent OHLC at {bar.time}: {bar.as_dict()}")


@dataclass
class Aggregator:
    """Streams M1 bars into one higher timeframe. See module docstring."""

    tf: str
    minutes: int
    current: Bar | None = None      # the FORMING bar (never treat as closed)
    _seconds: int = field(init=False)

    def __post_init__(self) -> None:
        self._seconds = self.minutes * SECONDS_PER_MINUTE

    def update(self, m1: Bar) -> list[Bar]:
        """Feed one closed M1 bar; return 0, 1 or 2 newly CLOSED bars, oldest first."""
        closed: list[Bar] = []
        start = m1.time - m1.time % self._seconds
        # 1) A gap: this minute belongs to a later bucket -> close the old one.
        if self.current is not None and self.current.time != start:
            closed.append(self.current)
            self.current = None
        # 2) Merge the minute into the forming bucket.
        if self.current is None:
            self.current = Bar(start, m1.open, m1.high, m1.low, m1.close, m1.volume,
                               minutes=self.minutes, m1_count=1, tf=self.tf)
        else:
            c = self.current
            c.high = max(c.high, m1.high)
            c.low = min(c.low, m1.low)
            c.close = m1.close
            c.volume += m1.volume
            c.m1_count += 1
        # 3) This minute was the bucket's last one -> the bucket is complete.
        if m1.close_time == start + self._seconds:
            closed.append(self.current)
            self.current = None
        return closed


def aggregate(m1_bars: Iterable[Bar], tf: str, minutes: int) -> list[Bar]:
    """Offline helper: all closed bars of one timeframe (tests, references).

    The final, still-forming bucket is NOT returned — same as live.
    """
    agg = Aggregator(tf, minutes)
    out: list[Bar] = []
    for bar in m1_bars:
        out.extend(agg.update(bar))
    return out


# --------------------------------------------------------------------------
# Loading recorded history
# --------------------------------------------------------------------------

def parse_time(text: str) -> int:
    """Accept epoch seconds, ISO-8601, or MT5 export style ``2024.01.02 13:05``.

    Strings without a timezone are taken as UTC. Convert broker-clock data
    with ``time_shift`` in :func:`load_m1` (see goldflow.core.mt5_connection).
    """
    text = text.strip()
    if text.lstrip("-").isdigit():
        value = int(text)
        return value // 1000 if value > 10**11 else value   # milliseconds -> seconds
    text = text.replace(".", "-", 2) if text[:4].isdigit() and text[4:5] == "." else text
    dt = datetime.fromisoformat(text.replace("T", " ").replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _row_to_bar(row: dict, time_shift: Callable[[int], int] | None) -> Bar:
    lower = {k.strip().lower().lstrip("<").rstrip(">"): v for k, v in row.items() if k}
    if "date" in lower:                                     # MT5 "Export Bars": <DATE> <TIME>
        lower["time"] = f"{lower['date']} {lower.get('time', '')}".strip()
    t = parse_time(str(lower["time"]))
    if time_shift:
        t = time_shift(t)
    volume = lower.get("tick_volume", lower.get("tickvol", lower.get("volume", 0))) or 0
    return Bar(t, float(lower["open"]), float(lower["high"]), float(lower["low"]),
               float(lower["close"]), float(volume))


def load_m1(path: str | Path, *, time_shift: Callable[[int], int] | None = None,
            start: int | None = None, end: int | None = None) -> Iterator[Bar]:
    """Stream M1 bars from CSV/TSV (header row) or JSONL (one object per line).

    Required columns: time, open, high, low, close; optional tick_volume.
    ``start``/``end`` (UTC epoch, end exclusive) filter by bar open time.
    Rows are yielded in file order; the engine rejects out-of-order data.
    """
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        if path.suffix.lower() in (".jsonl", ".ndjson"):
            rows: Iterable[dict] = (json.loads(line) for line in fh if line.strip())
        else:
            sample = fh.read(4096)
            fh.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            rows = csv.DictReader(fh, dialect=dialect)
        for row in rows:
            bar = _row_to_bar(row, time_shift)
            if start is not None and bar.time < start:
                continue
            if end is not None and bar.time >= end:
                break
            yield bar
