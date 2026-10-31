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
vwap_cross        price has CHANGED SIDE of VWAP: the candle closed at least
                  ``cross_buffer_atr`` x ATR (of detect_timeframe; 0.5) beyond VWAP,
                  on the other side from the last confirmed side (up / down).
                  Closes inside the buffer change nothing (hysteresis). Real
                  gold Apr-Aug 2026, crosses re-crossed within 15 minutes:
                  no buffer 50 % (35 a day), 0.25 ATR 27 %, 0.5 ATR 12 %
                  (14 a day), 0.75 ATR 5 % (11 a day) — 0.5 keeps real
                  changes of side and drops most of the chop.
vwap_band_reject  the candle traded beyond the ``reject_band`` band but closed
                  back inside it (upper or lower). One event per episode: the
                  same anchor and side fire again only after a candle has
                  closed back inside the 1-sigma band.

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
        self.side: dict[str, tuple[int, str] | None] = {a: None for a in self.c["anchors"]}  # (period start, up|down)
        self.armed: dict[tuple[str, str], bool] = {}          # band-reject episode per (anchor, side)

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

    def on_detect_bar(self, bar: Bar, atr: float | None = None) -> list[tuple[str, dict]]:
        """A detect-timeframe candle closed (after its M1 bars were added).
        ``atr``: ATR of the detect timeframe as of BEFORE this candle."""
        out = []
        k = self.c["reject_band"]
        buf = self.c["cross_buffer_atr"] * atr if atr else 0.0
        for anchor, p in self.periods.items():
            if p is None or p.bars < self.c["min_bars"]:
                continue
            vw, sd = p.value()
            base = {"anchor": anchor, "name": p.name, "vwap": round(vw, 4), "sd": round(sd, 4),
                    "candle": bar.as_dict()}
            now_side = "up" if bar.close > vw + buf else "down" if bar.close < vw - buf else None
            last = self.side[anchor]
            if last is not None and last[0] != p.start:
                last = None                                   # new period: start fresh
            if now_side is not None:
                if last is not None and last[1] != now_side:
                    out.append(("vwap_cross", {**base, "direction": now_side}))
                self.side[anchor] = (p.start, now_side)
            if sd > 0:
                up, dn = vw + k * sd, vw - k * sd
                # both sides are checked: a huge candle can reject both bands
                for side, hit in (("upper", bar.high > up and bar.close < up),
                                  ("lower", bar.low < dn and bar.close > dn)):
                    key = (anchor, side)
                    if hit and self.armed.get(key, True):
                        out.append(("vwap_band_reject", {**base, "side": side, "band": k,
                                                         "level": round(up if side == "upper" else dn, 4)}))
                        self.armed[key] = False
                    elif not hit and (bar.close < vw + sd if side == "upper" else bar.close > vw - sd):
                        self.armed[key] = True                 # back inside 1 sigma: re-armed
        return out
