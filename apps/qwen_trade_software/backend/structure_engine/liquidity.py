"""Liquidity: where stops rest, and what price does when it gets there.

Liquidity POOLS (price levels with resting orders beyond them)
--------------------------------------------------------------
swing_high / swing_low   confirmed swings of ``swing_timeframes`` (M15, H1, H4)
equal_highs / equal_lows two or more swings of the same timeframe within
                         ``equal_tolerance_atr`` x ATR of each other — the
                         classic "double stops" pool. The pool sits at the
                         most extreme of them.
session / day / week     confirmed Asia / London / New York, prior-day and
                         prior-week highs and lows (sessions.py)
range_high / range_low   boundaries of detected consolidation ranges (ranges.py)

A pool becomes ACTIVE when it is known (swing confirmed, session finished...)
and lives at most ``max_age_hours``. Each pool is used up by its FIRST
interaction.

What happens at a pool (judged on CLOSED candles of ``detect_timeframe``, M5)
----------------------------------------------------------------------------
For a HIGH pool (lows are the mirror image):

    LIQUIDITY SWEEP  the candle's high goes beyond the level by at least
                     min_pierce_atr x ATR, but the candle CLOSES back below
                     it. Stops were taken; price was rejected.
    BREAK            the candle CLOSES above level + break_buffer_atr x ATR.
                     The pool is now "pending" for ``false_break_bars`` candles:
      FALSE BREAK      a later candle closes back below level - reclaim buffer
                       within that window -> the break failed (a trap)
      ACCEPTED BREAK   the window passes without a close back inside ->
                       liquidity taken, price accepted beyond the level

All pools hit by the same candle on the same side are reported in ONE event
(an H1 swing high and the London high at the same price are one sweep).
Events are known at the close of the candle that decides them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bars import Bar
from .swings import Swing

HOUR = 3600


@dataclass
class Pool:
    id: str
    kind: str              # swing_high, equal_highs, session_high, range_low, ...
    side: str              # "high" | "low"
    price: float
    source_tf: str         # timeframe or "session"/"day"/"week"/range tf
    time: int              # time of the structure that created it
    active_from: int       # when it became known
    expires_at: int
    state: str = "active"  # active | pending (closed beyond, waiting)
    break_time: int | None = None
    bars_since_break: int = 0

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "side": self.side, "price": self.price,
                "source_tf": self.source_tf, "time": self.time, "active_from": self.active_from}


class LiquidityBook:
    def __init__(self, cfg: dict, make_id) -> None:
        self.c = cfg["liquidity"]
        self.make_id = make_id
        self.pools: list[Pool] = []
        self.recent_swings: dict[str, list[Swing]] = {}   # for equal highs/lows
        self.history: list[dict] = []                     # recent sweep/break events (snapshot)

    # ------------------------------------------------------------ registration
    def add(self, kind: str, side: str, price: float, source_tf: str, time: int, now: int) -> Pool:
        pool = Pool(self.make_id(kind, source_tf, time, side), kind, side, price, source_tf, time,
                    now, now + self.c["max_age_hours"] * HOUR)
        self.pools.append(pool)
        return pool

    def add_swings(self, tf: str, swings: list[Swing], atr: float | None, now: int) -> list[dict]:
        """Register swing pools; detect equal highs / lows. Returns equal-level records."""
        found = []
        for s in swings:
            side = "high" if s.kind == "high" else "low"
            if tf in self.c["swing_timeframes"]:
                self.add(f"swing_{side}", side, s.price, tf, s.time, now)
            if tf in self.c["equal_timeframes"] and atr:
                hist = self.recent_swings.setdefault(tf, [])
                same = [x for x in hist if x.kind == s.kind][-self.c["equal_lookback_swings"]:]
                tol = self.c["equal_tolerance_atr"] * atr
                group = [x for x in same if abs(x.price - s.price) <= tol]
                # nothing in between may stick out beyond the group (else they are
                # two separate tops, not one shelf of stops)
                if group:
                    first = group[0]
                    between = [x for x in hist if x.kind == s.kind and first.time < x.time < s.time
                               and x not in group]
                    extreme = max(g.price for g in group + [s]) if side == "high" else min(g.price for g in group + [s])
                    if all((x.price <= extreme) if side == "high" else (x.price >= extreme) for x in between):
                        pool = self.add(f"equal_{side}s", side, extreme, tf, s.time, now)
                        found.append({"pool": pool.as_dict(), "count": len(group) + 1,
                                      "times": [g.time for g in group] + [s.time],
                                      "prices": [g.price for g in group] + [s.price],
                                      "tolerance": round(tol, 4)})
                hist.append(s)
                del hist[:-50]
        return found

    # ---------------------------------------------------------------- detection
    def on_detect_bar(self, bar: Bar, atr: float | None, now: int) -> list[tuple[str, str, dict]]:
        """A detect-timeframe candle CLOSED. Returns (kind, side, data) events."""
        self.pools = [p for p in self.pools if p.expires_at > now]
        if atr is None or atr <= 0:
            return []
        c = self.c
        pierce, brk, reclaim = c["min_pierce_atr"] * atr, c["break_buffer_atr"] * atr, c["reclaim_buffer_atr"] * atr
        hits: dict[tuple[str, str], list[Pool]] = {}
        done: list[Pool] = []
        for p in self.pools:
            if bar.time < p.active_from:
                continue                                 # not known yet when this candle opened
            up = p.side == "high"
            beyond_close = (bar.close > p.price + brk) if up else (bar.close < p.price - brk)
            back_inside = (bar.close < p.price - reclaim) if up else (bar.close > p.price + reclaim)
            if p.state == "pending":
                p.bars_since_break += 1
                if back_inside:
                    hits.setdefault(("false_break", p.side), []).append(p)
                    done.append(p)
                elif p.bars_since_break >= c["false_break_bars"]:
                    hits.setdefault(("liquidity_taken", p.side), []).append(p)
                    done.append(p)
                continue
            pierced = (bar.high >= p.price + pierce) if up else (bar.low <= p.price - pierce)
            if beyond_close:
                p.state, p.break_time, p.bars_since_break = "pending", bar.time, 0
            elif pierced and back_inside:
                hits.setdefault(("liquidity_sweep", p.side), []).append(p)
                done.append(p)
        for p in done:
            self.pools.remove(p)
        out = []
        for (kind, side), pools in sorted(hits.items()):
            extreme = bar.high if side == "high" else bar.low
            data = {
                "side": side, "candle": bar.as_dict(), "extreme": extreme,
                "levels": [p.as_dict() for p in pools],
                "pierce_atr": round(max(abs(extreme - p.price) for p in pools) / atr, 4),
                "close_vs_level_atr": round((bar.close - pools[0].price) / atr, 4),
                "break_time": pools[0].break_time,
            }
            self.history.append({"kind": kind, **data})
            del self.history[:-40]
            out.append((kind, side, data))
        return out

    def nearest(self, price: float, n: int = 6) -> list[dict]:
        """The n active pools closest to price (snapshot)."""
        ranked = sorted(self.pools, key=lambda p: (abs(p.price - price), p.id))
        return [{**p.as_dict(), "state": p.state} for p in ranked[:n]]
