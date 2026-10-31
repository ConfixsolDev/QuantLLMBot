"""Close spikes: a fast M1 burst into the CLOSE of an H1 / H4 candle.

The question this module exists to answer
-----------------------------------------
"Gold sometimes moves $10-15 in a few one-minute candles right before an H1
or H4 candle closes, then either reverses or keeps going. The higher
timeframe drives the market; the lower timeframe is doing something else
(stop runs, manipulation, painting the close)." That is a precise, testable
claim. This module turns it into data: it DETECTS every such burst with the
exact same rule every time, records the CONTEXT it happened in, and later
LABELS what price did next. A study over months or years of bars then gives
the real base rates (count the close_spike_outcome labels per context).

Detection (when an H1 / H4 candle closes normally, i.e. not across a gap)
--------------------------------------------------------------------------
::

    H1 candle  |-------------------------------------|-- window --|  close
                                                      ref = open of the first
                                                      M1 in the last
                                                      window_minutes

    up move   = highest high in the window - ref
    down move = ref - lowest low in the window
    the larger one is the spike; it counts when
        move >= min_move_atr x ATR(atr_timeframe)     (ATR as of BEFORE this push)
        and move >= min_move_price                     (0 = off; dollars, if wanted)

ATR, not dollars, by default: $15 meant something different at $1,800 gold
than at $4,500. Set ``min_move_price`` to also require an absolute size.

Context recorded with each spike (all known at the close)
---------------------------------------------------------
held / rejected   did the candle CLOSE near the spike extreme (held) or give
                  most of it back inside the same candle (rejected, a wick)
close_pos         where the close sits in the candle range (0 = low, 1 = high)
swept_prev        the spike took out the previous candle's high (up) / low (down)
swept_levels      confirmed session / prior-day highs or lows (finished within
                  the last level_lookback_hours) crossed by the spike
at_zone           an active supply/demand zone the spike ran into
htf_trend         H4 swing structure: up (HH+HL), down (LH+LL) or mixed
volume_ratio      window M1 volume vs the preceding volume_lookback minutes
session           which session the close happened in

Outcome labels (emitted later, when each horizon has passed)
------------------------------------------------------------
For each ``horizons_minutes`` h, at the first M1 close at or after close+h:

    reversal      price is back beyond the spike's start:
                  close <= ref - (reversal_retrace - 1) x move   (up spike)
    continuation  price is beyond the spike's extreme: close > extreme (up spike)
    partial       anything in between

plus how far price ran beyond the extreme and how deep it retraced, in units
of the spike move. Outcome events are ordinary events: known only when they
happen, so the no-repaint guarantee still holds.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .bars import Bar


@dataclass
class Spike:
    id: str
    tf: str
    direction: str            # "up" | "down"
    close_time: int           # the HTF candle's close (= detection time)
    ref: float
    extreme: float
    extreme_time: int
    move: float
    data: dict
    pending: list = field(default_factory=list)     # horizons not yet labelled
    post_high: float = float("-inf")
    post_low: float = float("inf")


class CloseSpikeDetector:
    def __init__(self, cfg: dict, make_id) -> None:
        self.c = cfg["close_spikes"]
        self.tfs = set(self.c["timeframes"])
        self.make_id = make_id
        keep = max(self.c["window_minutes"], self.c["volume_lookback"]) + self.c["window_minutes"] + 5
        self.m1: deque[Bar] = deque(maxlen=keep)
        self.prev_bar: dict[str, Bar] = {}
        self.open: list[Spike] = []

    # ---------------------------------------------------------------- M1 feed
    def on_m1(self, bar: Bar, now: int) -> list[tuple[str, Spike, dict]]:
        """Track price after open spikes and emit outcome labels that are due."""
        self.m1.append(bar)
        out = []
        for s in list(self.open):
            if bar.time < s.close_time:
                continue
            s.post_high = max(s.post_high, bar.high)
            s.post_low = min(s.post_low, bar.low)
            while s.pending and now >= s.close_time + s.pending[0] * 60:
                h = s.pending.pop(0)
                out.append(("close_spike_outcome", s, self._label(s, h, bar, now)))
            if not s.pending:
                self.open.remove(s)
        return out

    def _label(self, s: Spike, h: int, bar: Bar, now: int) -> dict:
        up = s.direction == "up"
        sign = 1 if up else -1
        price = bar.close
        rev_line = s.ref - sign * (self.c["reversal_retrace"] - 1) * s.move
        if (price <= rev_line) if up else (price >= rev_line):
            label = "reversal"
        elif (price > s.extreme) if up else (price < s.extreme):
            label = "continuation"
        else:
            label = "partial"
        run_beyond = ((s.post_high - s.extreme) if up else (s.extreme - s.post_low)) / s.move
        max_retrace = ((s.extreme - s.post_low) if up else (s.post_high - s.extreme)) / s.move
        return {"spike_id": s.id, "tf": s.tf, "direction": s.direction, "horizon_minutes": h,
                "label": label, "price": price,
                "move_from_extreme": round(sign * (price - s.extreme) / s.move, 4),
                "run_beyond_extreme": round(max(0.0, run_beyond), 4),
                "max_retrace": round(max(0.0, max_retrace), 4),
                "late": now > s.close_time + h * 60 + 60}     # labelled after a data gap

    # --------------------------------------------------------- HTF candle close
    def on_htf_close(self, tf: str, htf: Bar, now: int, atr: float | None,
                     levels: list[dict], zones: list, trend: str, session: str | None):
        """An H1/H4 candle just closed. Return a new Spike or None."""
        prev = self.prev_bar.get(tf)
        self.prev_bar[tf] = htf
        c = self.c
        if tf not in self.tfs or atr is None or htf.m1_count < htf.minutes or htf.close_time != now:
            return None                                   # partial candle (gap) or no ATR yet
        start = now - c["window_minutes"] * 60
        window = [b for b in self.m1 if b.time >= start]
        if len(window) < c["window_minutes"]:
            return None
        ref = window[0].open
        hi = max(window, key=lambda b: b.high)
        lo = min(window, key=lambda b: b.low)
        up_move, down_move = hi.high - ref, ref - lo.low
        up = up_move >= down_move
        move = up_move if up else down_move
        if move < c["min_move_atr"] * atr or move < c["min_move_price"]:
            return None
        extreme, ext_time = (hi.high, hi.time) if up else (lo.low, lo.time)
        before = [b for b in self.m1 if b.time < start][-c["volume_lookback"]:]
        vol_before = sum(b.volume for b in before) / len(before) if before else 0.0
        vol_window = sum(b.volume for b in window) / len(window)
        rng = htf.high - htf.low
        close_pos = (htf.close - htf.low) / rng if rng > 0 else 0.5
        kept = close_pos if up else 1 - close_pos          # 1 = closed right at the spike end
        crossed = []
        recent = [lv for lv in levels if lv["end"] >= now - c["level_lookback_hours"] * 3600]
        for lv in recent:
            for side in ("high", "low"):
                p = lv[side]
                if (ref < p <= extreme) if up else (extreme <= p < ref):
                    crossed.append({"name": lv["name"], "side": side, "price": p, "start": lv["start"]})
        zone_hits = [{"id": z.id, "tf": z.tf, "side": z.side} for z in zones
                     if z.active and z.low <= max(ref, extreme) and z.high >= min(ref, extreme)]
        data = {
            "direction": "up" if up else "down", "htf_open": htf.time, "close_time": now,
            "window_minutes": c["window_minutes"], "ref": ref, "extreme": extreme,
            "extreme_time": ext_time, "move": round(move, 4), "move_atr": round(move / atr, 4),
            "atr": round(atr, 6), "atr_timeframe": c["atr_timeframe"],
            "htf": htf.as_dict(), "close_pos": round(close_pos, 4),
            "held": kept >= 1 - c["held_close_fraction"],
            "swept_prev": prev is not None and ((extreme > prev.high) if up else (extreme < prev.low)),
            "swept_levels": crossed, "at_zone": zone_hits, "htf_trend": trend,
            "volume_ratio": round(vol_window / vol_before, 4) if vol_before > 0 else None,
            "session": session,
        }
        sid = self.make_id(tf, now)
        data["spike_id"] = sid                          # outcome events refer to this
        spike = Spike(sid, tf, data["direction"], now, ref, extreme, ext_time,
                      move, data, pending=sorted(c["horizons_minutes"]))
        self.open.append(spike)
        return spike
