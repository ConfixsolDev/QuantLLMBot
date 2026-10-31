"""Fair value gaps (FVG): three-candle imbalances, with a lifecycle.

::

    bullish FVG                      bearish FVG
                 ┌─┐ c3                 c1 ┌─┐
         gap  ...│ │... c3.low          ...│ │... c1.low
        (unfilled│ │                       │ │  gap
         price)  └─┘                       └─┘
         ┌──┐ c2 (big up candle)            ┌──┐ c2 (big down candle)
    ...──┤  ├... c1.high               ...──┤  ├... c3.high
    c1 ┌─┐                                       ┌─┐ c3

    bullish: c3.low  > c1.high   gap = [c1.high, c3.low]
    bearish: c3.high < c1.low    gap = [c3.high, c1.low]
    and gap size >= min_gap_atr x ATR (ATR as of before c3)
    and c1, c2, c3 are CONSECUTIVE candles (no weekend / daily-break hole)

Price moved so fast through the gap that one side barely traded there. Price
often returns to "rebalance" it. Detected at the CLOSE of c3.

Lifecycle (checked on every CLOSED M1 bar after the gap is known)
    OPEN       untouched
    MITIGATED  price traded into the gap (first touch) — event once
    FILLED     price traded through the whole gap — final
    EXPIRED    older than max_age_bars of its timeframe — final
"""

from __future__ import annotations

from dataclasses import dataclass

from .bars import Bar


@dataclass
class Gap:
    id: str
    tf: str
    direction: str        # "up" (bullish) | "down" (bearish)
    low: float
    high: float
    time: int             # open time of c1
    c2_displacement: bool
    size_atr: float
    created_at: int
    status: str = "OPEN"
    age_bars: int = 0
    closed_at: int | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "tf": self.tf, "direction": self.direction, "low": self.low,
                "high": self.high, "time": self.time, "size_atr": round(self.size_atr, 4),
                "c2_displacement": self.c2_displacement, "status": self.status,
                "created_at": self.created_at, "age_bars": self.age_bars, "closed_at": self.closed_at}


def find_gap(c1: Bar, c2: Bar, c3: Bar, atr: float | None, min_gap_atr: float) -> tuple[str, float, float] | None:
    """Pure geometry (shared with the offline reference test)."""
    if atr is None or atr <= 0:
        return None
    if c3.low > c1.high and (c3.low - c1.high) >= min_gap_atr * atr:
        return "up", c1.high, c3.low
    if c3.high < c1.low and (c1.low - c3.high) >= min_gap_atr * atr:
        return "down", c3.high, c1.low
    return None


class GapBook:
    def __init__(self, cfg: dict, make_id) -> None:
        self.c = cfg["fvg"]
        self.make_id = make_id
        self.active: list[Gap] = []
        self.closed: list[Gap] = []

    def on_tf_bar(self, tf: str, last3: list[Bar], atr_before_c3: float | None, c2_disp: bool, now: int) -> list[tuple[str, Gap]]:
        out = []
        for g in list(self.active):                     # age first
            if g.tf == tf and now > g.created_at:
                g.age_bars += 1
                if g.age_bars > self.c["max_age_bars"]:
                    out.append(("fvg_expired", self._close(g, "EXPIRED", now)))
        # The three candles must be consecutive. Across the weekend or the
        # daily 21-22 UTC break, the "gap" is a market closure, not an
        # imbalance (found in the first real-data review, 2026-10-31).
        contiguous = len(last3) == 3 and last3[2].time - last3[0].time == 2 * last3[0].minutes * 60
        if contiguous:
            found = find_gap(*last3, atr_before_c3, self.c["min_gap_atr"])
            if found:
                d, lo, hi = found
                g = Gap(self.make_id(tf, last3[0].time, d), tf, d, lo, hi, last3[0].time, c2_disp,
                        (hi - lo) / atr_before_c3, now)
                self.active.append(g)
                out.append(("fvg_created", g))
        return out

    def on_m1(self, bar: Bar, now: int) -> list[tuple[str, Gap]]:
        out = []
        for g in list(self.active):
            if bar.time < g.created_at:
                continue
            if g.direction == "up":
                touched, filled = bar.low <= g.high, bar.low <= g.low
            else:
                touched, filled = bar.high >= g.low, bar.high >= g.high
            if filled:
                out.append(("fvg_filled", self._close(g, "FILLED", now)))
            elif touched and g.status == "OPEN":
                g.status = "MITIGATED"
                out.append(("fvg_mitigated", g))
        return out

    def _close(self, g: Gap, status: str, now: int) -> Gap:
        g.status, g.closed_at = status, now
        self.active.remove(g)
        self.closed.append(g)
        del self.closed[:-200]
        return g
