"""Getting CLOSED M1 bars: MT5 history, MT5 live polling, and CSV files.

All three produce ``structure_engine.bars.Bar`` objects with UTC open times.

MT5 rules applied here (and nowhere else)
-----------------------------------------
* MT5 bar times are broker-clock; converted with ``mt5_connection.server_to_utc_epoch``
  (rule ``server_time`` in config/mt5_connection.json).
* ``copy_rates_from_pos(symbol, M1, 1, n)`` starts at position 1: position 0
  is the still-forming minute and never enters the system.
* History is fetched in chunks; MT5 returns only what the terminal holds, so
  set Tools > Options > Charts > "Max bars in chart" to Unlimited.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Iterator

from structure_engine.bars import Bar
from structure_engine.feeds import RecordedFeed

from . import mt5_connection

log = logging.getLogger("quantllm")


def _rate_to_bar(r) -> Bar:
    t = mt5_connection.server_to_utc_epoch(int(r["time"]))
    return Bar(t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
               float(r["tick_volume"]))


def connect_mt5():
    """Import MetaTrader5 and connect with the configured settings, or raise."""
    import MetaTrader5 as mt5                       # Windows only
    if not mt5_connection.initialize(mt5):
        raise RuntimeError(f"MT5 connection failed: {mt5.last_error()}")
    symbol = mt5_connection.settings().broker_symbol
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"symbol {symbol} not available in MT5 Market Watch")
    # Broker clock: checked against the data BEFORE any bar is converted or stored
    clock = mt5_connection.resolve_server_time(mt5, symbol)
    log.info("broker clock: %s (configured %r, %d daily breaks checked)",
             clock["using"], clock["configured"], clock["breaks"])
    return mt5


def mt5_history(mt5, symbol: str, since: int, until: int | None = None, chunk_days: int = 20) -> Iterator[list[Bar]]:
    """Yield chunks of closed M1 bars from ``since`` (UTC epoch) to now."""
    until = until or int(time.time())
    cursor = datetime.fromtimestamp(since, tz=timezone.utc)
    end = datetime.fromtimestamp(until, tz=timezone.utc)
    last = None
    while cursor < end:
        upto = min(cursor + timedelta(days=chunk_days), end)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, cursor, upto)
        chunk = []
        for r in (rates if rates is not None else []):
            b = _rate_to_bar(r)
            if (last is not None and b.time <= last) or b.close_time > until:
                continue
            chunk.append(b)
            last = b.time
        if chunk:
            yield chunk
        cursor = upto


class LivePoller:
    """Return newly CLOSED M1 bars each time ``poll()`` is called."""

    def __init__(self, mt5, symbol: str, last_time: int | None) -> None:
        self.mt5, self.symbol, self.last = mt5, symbol, last_time

    def poll(self) -> list[Bar]:
        rates = self.mt5.copy_rates_from_pos(self.symbol, self.mt5.TIMEFRAME_M1, 1, 500)
        if rates is None:
            mt5_connection.initialize(self.mt5)          # terminal hiccup: reconnect, try next time
            return []
        new = []
        for r in rates:
            b = _rate_to_bar(r)
            if self.last is None or b.time > self.last:
                new.append(b)
                self.last = b.time
        return new


def csv_bars(paths) -> Iterator[Bar]:
    """Closed M1 bars from CSV/JSONL files or folders (UTC times)."""
    return iter(RecordedFeed(paths))
