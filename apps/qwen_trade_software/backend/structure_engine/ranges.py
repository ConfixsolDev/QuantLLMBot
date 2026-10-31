"""Trading ranges (consolidation) and how they end.

Detection (per timeframe, on each CLOSED candle, while no range is active)
-------------------------------------------------------------------------
Look at the last ``window_bars`` candles:

    top    = highest high,  bottom = lowest low
    width  = top - bottom   <= max_width_atr x ATR   (tight, sideways)
    at least ``min_touches`` candles reach within touch_tolerance_atr x ATR
    of the top, and at least ``min_touches`` reach the bottom   (both edges
    were defended more than once — a box, not a drift)

-> ``range_formed`` with the frozen top/bottom. Its edges are registered as
liquidity pools (liquidity.py), so sweeps and false breaks of a range edge
are detected exactly like any other level.

End of a range
    ``range_break``  a candle CLOSES beyond an edge by break_buffer_atr x ATR
                     (whether that break holds or fails is the liquidity
                     book's accepted / false break)
    ``range_expired`` still boxed after max_bars candles (stale)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .bars import Bar


@dataclass
class Range:
    id: str
    tf: str
    top: float
    bottom: float
    start: int
    formed_at: int
    atr: float
    bars: int = 0

    def as_dict(self) -> dict:
        return {"id": self.id, "tf": self.tf, "top": self.top, "bottom": self.bottom,
                "start": self.start, "formed_at": self.formed_at,
                "width_atr": round((self.top - self.bottom) / self.atr, 4), "bars": self.bars}


class RangeTracker:
    def __init__(self, tf: str, cfg: dict, make_id) -> None:
        self.tf = tf
        self.c = cfg["ranges"]
        self.make_id = make_id
        self.window: deque[Bar] = deque(maxlen=self.c["window_bars"])
        self.active: Range | None = None

    def on_bar(self, bar: Bar, atr: float | None, now: int) -> list[tuple[str, dict]]:
        out = []
        c = self.c
        if self.active is not None:
            r = self.active
            r.bars += 1
            buf = c["break_buffer_atr"] * r.atr
            if bar.close > r.top + buf or bar.close < r.bottom - buf:
                out.append(("range_break", {**r.as_dict(), "direction": "up" if bar.close > r.top else "down",
                                            "break_time": bar.time, "break_close": bar.close}))
                self.active = None
                self.window.clear()
            elif r.bars > c["max_bars"]:
                out.append(("range_expired", r.as_dict()))
                self.active = None
                self.window.clear()
            self.window.append(bar)
            return out
        self.window.append(bar)
        if atr is None or len(self.window) < c["window_bars"]:
            return out
        top = max(b.high for b in self.window)
        bottom = min(b.low for b in self.window)
        if top - bottom > c["max_width_atr"] * atr:
            return out
        tol = c["touch_tolerance_atr"] * atr
        top_touches = sum(1 for b in self.window if b.high >= top - tol)
        bottom_touches = sum(1 for b in self.window if b.low <= bottom + tol)
        if top_touches >= c["min_touches"] and bottom_touches >= c["min_touches"]:
            start = self.window[0].time
            self.active = Range(self.make_id(self.tf, start), self.tf, top, bottom, start, now, atr)
            out.append(("range_formed", {**self.active.as_dict(), "top_touches": top_touches,
                                         "bottom_touches": bottom_touches}))
        return out
