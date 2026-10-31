"""VWAP: volume-weighted average price, daily / weekly / per session, with bands.

Where the average trader in the period is positioned. Institutions benchmark
execution against it, so price often reacts at VWAP and at its bands.

Computed from CLOSED M1 bars only (Rule 4)::

    typical price  tp = (high + low + close) / 3
    VWAP           = sum(tp x volume) / sum(volume)          since the anchor
    sigma          = sqrt( sum(tp^2 x volume) / sum(volume) - VWAP^2 )
    bands          VWAP +/- k x sigma for each k in ``bands`` (default 1, 2)

Volume is MT5 TICK volume: gold has no central exchange, so this is the
standard retail approximation of VWAP, not exchange VWAP.

Anchors (config ``vwap.anchors``)
--------------------------------
day      resets at the gold trading-day open, 17:00 New York (``day_anchor``)
week     resets at the trading-week open, Sunday 17:00 New York
         (``sessions.week_anchor``)
session  resets at each Asia / London / New York window start
         (``sessions.windows_utc``); none between sessions

Events (judged on CLOSED ``detect_timeframe`` candles, M5 by default; only
once ``min_bars`` M1 bars have built the period, so a fresh VWAP is not noise)
------------------------------------------------------------------------------
vwap_cross        the candle closed on the other side of VWAP than the
                  previous candle (direction up / down)
vwap_band_reject  the candle traded beyond the ``reject_band`` band but closed
                  back inside it (upper or lower)

The current VWAP and bands of every anchor are in ``engine.snapshot()``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .bars import Bar
from .clock import anchored_day, anchored_week


@dataclass
class _Period:
    start: int
    name: str
    v: float = 0.0
    pv: float = 0.0
    pv2: float = 0.0
    bars: int = 0

    def value(self) -> tuple[float, float] | None:
        if self.v <= 0:
            return None
        vw = self.pv / self.v
        var = max(0.0, self.pv2 / self.v - vw * vw)
        return vw, math.sqrt(var)


class VwapTracker:
    def __init__(self, cfg: dict) -> None:
        self.c = cfg["vwap"]
        self.week = cfg["sessions"]["week_anchor"]
        self.windows = sorted((v[0] * 3600, v[1] * 3600, k) for k, v in cfg["sessions"]["windows_utc"].items())
        self.day_offset = cfg["sessions"]["day_start_utc_hour"] * 3600
        self.periods: dict[str, _Period | None] = {a: None for a in self.c["anchors"]}
        self.prev_close: float | None = None

    def _anchor(self, anchor: str, t: int) -> tuple[int, str] | None:
        if anchor == "day":
            a = self.c["day_anchor"]
            return anchored_day(t, a["timezone"], a["hour"])[0], "day"
        if anchor == "week":
            return anchored_week(t, self.week["timezone"], self.week["weekday"], self.week["hour"])[0], "week"
        d0 = (t - self.day_offset) // 86400 * 86400 + self.day_offset    # session
        for start, end, name in self.windows:
            if d0 + start <= t < d0 + end:
                return d0 + start, name
        return None

    def on_m1(self, bar: Bar) -> None:
        tp = (bar.high + bar.low + bar.close) / 3
        v = bar.volume if bar.volume > 0 else 1.0
        for anchor in self.periods:
            a = self._anchor(anchor, bar.time)
            if a is None:
                self.periods[anchor] = None
                continue
            p = self.periods[anchor]
            if p is None or p.start != a[0]:
                p = self.periods[anchor] = _Period(a[0], a[1])
            p.v += v
            p.pv += tp * v
            p.pv2 += tp * tp * v
            p.bars += 1

    def values(self) -> dict:
        out = {}
        for anchor, p in self.periods.items():
            val = p.value() if p else None
            if val is None:
                out[anchor] = None
                continue
            vw, sd = val
            out[anchor] = {"vwap": round(vw, 4), "sd": round(sd, 4), "start": p.start, "name": p.name,
                           "bars": p.bars,
                           "bands": {str(k): [round(vw - k * sd, 4), round(vw + k * sd, 4)] for k in self.c["bands"]}}
        return out

    def on_detect_bar(self, bar: Bar) -> list[tuple[str, dict]]:
        """A detect-timeframe candle closed (after its M1 bars were added)."""
        out = []
        prev, self.prev_close = self.prev_close, bar.close
        k = self.c["reject_band"]
        for anchor, p in self.periods.items():
            if p is None or p.bars < self.c["min_bars"]:
                continue
            vw, sd = p.value()
            base = {"anchor": anchor, "name": p.name, "vwap": round(vw, 4), "sd": round(sd, 4),
                    "candle": bar.as_dict()}
            if prev is not None and (prev < vw <= bar.close or prev > vw >= bar.close):
                out.append(("vwap_cross", {**base, "direction": "up" if bar.close >= vw else "down"}))
            if sd > 0:
                up, dn = vw + k * sd, vw - k * sd
                if bar.high > up and bar.close < up:
                    out.append(("vwap_band_reject", {**base, "side": "upper", "band": k, "level": round(up, 4)}))
                elif bar.low < dn and bar.close > dn:
                    out.append(("vwap_band_reject", {**base, "side": "lower", "band": k, "level": round(dn, 4)}))
        return out
