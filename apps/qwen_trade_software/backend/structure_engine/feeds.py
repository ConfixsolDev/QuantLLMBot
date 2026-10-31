"""Bar sources. The ONLY difference between live and back-test (Rule 2).

    RecordedFeed  closed M1 bars from a CSV/JSONL file   -> back-testing
    MT5Feed       closed M1 bars polled from MetaTrader 5 -> live / shadow
    export_mt5_history  download years of M1 history to CSV for RecordedFeed

Both feeds yield ``Bar`` objects with UTC open times, oldest first, CLOSED
bars only. The engine cannot tell which one it is talking to.

MT5 specifics (handled here, nowhere else in the package)
---------------------------------------------------------
* Connection properties (terminal path, account, symbol, broker clock) come
  from ``goldflow.core.mt5_connection`` — the single MT5 settings file
  ``backend/config/mt5_connection.json``. Imported lazily so back-tests run
  on any machine (Linux, no MetaTrader5 package).
* MT5 bar times are broker-clock; converted to UTC with the configured
  ``server_time`` rule.
* ``copy_rates_from_pos(..., start_pos=1, ...)`` skips position 0, which is
  the still-FORMING minute. Forming bars never enter the engine.
"""

from __future__ import annotations

import csv
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .bars import Bar, load_m1


class RecordedFeed:
    """Replay a recorded M1 file. ``time_shift`` converts broker clock if needed."""

    def __init__(self, path: str | Path, *, broker_time: bool = False,
                 start: int | None = None, end: int | None = None) -> None:
        self.path, self.start, self.end = Path(path), start, end
        self.time_shift = None
        if broker_time:
            from goldflow.core import mt5_connection
            self.time_shift = mt5_connection.server_to_utc_epoch

    def __iter__(self) -> Iterator[Bar]:
        return load_m1(self.path, time_shift=self.time_shift, start=self.start, end=self.end)


def _mt5():
    """Import MetaTrader5 + our connection settings, and connect."""
    import MetaTrader5 as mt5                     # Windows-only package
    from goldflow.core import mt5_connection
    if not mt5_connection.initialize(mt5):
        raise RuntimeError(f"MT5 connection failed: {mt5.last_error()}")
    cfg = mt5_connection.settings()
    if not mt5.symbol_select(cfg.broker_symbol, True):
        raise RuntimeError(f"symbol {cfg.broker_symbol} not available in Market Watch")
    return mt5, mt5_connection, cfg


def _rate_to_bar(r, to_utc) -> Bar:
    return Bar(to_utc(int(r["time"])), float(r["open"]), float(r["high"]), float(r["low"]),
               float(r["close"]), float(r["tick_volume"]))


class MT5Feed:
    """Poll MT5 for newly CLOSED M1 bars, forever.

    ``warmup`` closed bars are yielded first so ATRs, swings and zones are
    already built when live bars start arriving.
    """

    def __init__(self, warmup: int = 20_000, poll_seconds: float = 2.0) -> None:
        self.warmup, self.poll = warmup, poll_seconds

    def __iter__(self) -> Iterator[Bar]:
        mt5, conn, cfg = _mt5()
        to_utc = conn.server_to_utc_epoch
        last: int | None = None
        try:
            rates = mt5.copy_rates_from_pos(cfg.broker_symbol, mt5.TIMEFRAME_M1, 1, self.warmup)
            for r in (rates if rates is not None else []):
                bar = _rate_to_bar(r, to_utc)
                last = bar.time
                yield bar
            while True:
                time.sleep(self.poll)
                rates = mt5.copy_rates_from_pos(cfg.broker_symbol, mt5.TIMEFRAME_M1, 1, 50)
                if rates is None:                    # terminal hiccup: reconnect next loop
                    conn.initialize(mt5)
                    continue
                for r in rates:
                    bar = _rate_to_bar(r, to_utc)
                    if last is None or bar.time > last:
                        last = bar.time
                        yield bar
        finally:
            mt5.shutdown()


def export_mt5_history(out: str | Path, start: datetime, end: datetime | None = None,
                       chunk_days: int = 20) -> int:
    """Download M1 history from MT5 into a CSV (UTC epoch times). Returns rows.

    MT5 only serves what the terminal has: raise Tools > Options > Charts >
    "Max bars in chart" to Unlimited and scroll the XAUUSD M1 chart back once
    if early years come back empty.
    """
    mt5, conn, cfg = _mt5()
    to_utc = conn.server_to_utc_epoch
    end = end or datetime.now(timezone.utc)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows, last = 0, None
    try:
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["time", "open", "high", "low", "close", "tick_volume"])
            cursor = start
            while cursor < end:
                upto = min(cursor + timedelta(days=chunk_days), end)
                rates = mt5.copy_rates_range(cfg.broker_symbol, mt5.TIMEFRAME_M1, cursor, upto)
                for r in (rates if rates is not None else []):
                    bar = _rate_to_bar(r, to_utc)
                    if last is not None and bar.time <= last:
                        continue                       # chunk overlap
                    if bar.close_time > int(time.time()):
                        continue                       # still forming
                    w.writerow([bar.time, bar.open, bar.high, bar.low, bar.close, int(bar.volume)])
                    last = bar.time
                    rows += 1
                cursor = upto
    finally:
        mt5.shutdown()
    return rows
