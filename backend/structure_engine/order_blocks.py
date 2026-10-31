"""Order blocks: the last opposite candle before a move that broke structure.

Definition (bullish; bearish is the mirror image)
-------------------------------------------------
Triggered by a BOS or CHoCH UP on the same timeframe (trend.py):

1. Leg origin = the candle with the LOWEST low between the broken swing high
   and the breaking candle — where the up-move started.
2. Order block = the last BEARISH candle (close < open) at or before the
   origin, searching back at most ``lookback_bars`` candles.
3. If ``require_displacement``: some candle from the origin to the breaking
   candle must be an up displacement candle (displacement.py). No
   displacement = no institutional footprint = no order block.
4. Zone = that candle's low .. high.

Lifecycle (on CLOSED M1 bars after it is known), like supply/demand zones:
    FRESH -> TESTED (price trades back into it; counted once per visit)
    BROKEN  an M1 close beyond its far side (low - buffer for bullish)
    EXPIRED older than max_age_bars of its timeframe, or tested > max_tests

Known at the close of the breaking candle.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bars import Bar


@dataclass
class OrderBlock:
    id: str
    tf: str
    direction: str            # "up" (bullish, demand) | "down" (bearish, supply)
    low: float
    high: float
    time: int                 # open time of the order-block candle
    origin_time: int
    break_kind: str           # bos | choch
    break_time: int
    atr: float
    created_at: int
    status: str = "FRESH"
    tests: int = 0
    age_bars: int = 0
    inside: bool = False
    closed_at: int | None = None
    close_reason: str | None = None

    def as_dict(self) -> dict:
        return {"id": self.id, "tf": self.tf, "direction": self.direction, "low": self.low,
                "high": self.high, "time": self.time, "origin_time": self.origin_time,
                "break_kind": self.break_kind, "break_time": self.break_time,
                "status": self.status, "tests": self.tests, "age_bars": self.age_bars,
                "created_at": self.created_at, "closed_at": self.closed_at,
                "close_reason": self.close_reason}


class OrderBlockBook:
    def __init__(self, cfg: dict, make_id) -> None:
        self.c = cfg["order_blocks"]
        self.make_id = make_id
        self.active: list[OrderBlock] = []
        self.closed: list[OrderBlock] = []
        # A candle is an order block at most once per timeframe and direction,
        # even after that block was broken or expired (found 2026-10-31: the
        # same candle re-detected by a later break produced duplicate ids).
        self.used: set[str] = set()

    def on_break(self, tf: str, brk: dict, bars: list[Bar], disps: list[dict | None],
                 atr: float | None, now: int) -> OrderBlock | None:
        """``bars``/``disps``: this timeframe's recent closed candles (oldest
        first) ending with the breaking candle, and their displacement info."""
        if atr is None or not bars:
            return None
        up = brk["direction"] == "up"
        # candles from the broken swing up to the breaking candle
        span = [i for i, b in enumerate(bars) if b.time >= brk["level_time"]]
        if not span:
            return None
        origin = min(span, key=lambda i: (bars[i].low, -i)) if up else max(span, key=lambda i: (bars[i].high, -i))
        if self.c["require_displacement"]:
            if not any(d and d["direction"] == brk["direction"] for d in disps[origin:]):
                return None
        ob_i = None
        for i in range(origin, max(-1, origin - self.c["lookback_bars"] - 1), -1):
            b = bars[i]
            if (up and b.bearish) or (not up and b.bullish):
                ob_i = i
                break
        if ob_i is None:
            return None
        b = bars[ob_i]
        oid = self.make_id(tf, b.time, brk["direction"])
        if oid in self.used:
            return None
        self.used.add(oid)
        ob = OrderBlock(oid, tf, brk["direction"], b.low, b.high,
                        b.time, bars[origin].time, brk["kind"], brk["break_time"], atr, now)
        self.active.append(ob)
        return ob

    def age(self, tf: str, now: int) -> list[OrderBlock]:
        out = []
        for o in list(self.active):
            if o.tf == tf and now > o.created_at:
                o.age_bars += 1
                if o.age_bars > self.c["max_age_bars"]:
                    out.append(self._close(o, "EXPIRED", now, "max_age"))
        return out

    def on_m1(self, bar: Bar, now: int) -> list[tuple[str, OrderBlock]]:
        out = []
        buf = self.c["break_buffer_atr"]
        for o in list(self.active):
            if bar.time < o.created_at:
                continue
            if o.direction == "up":
                broken, touched = bar.close < o.low - buf * o.atr, bar.low <= o.high
            else:
                broken, touched = bar.close > o.high + buf * o.atr, bar.high >= o.low
            if broken:
                out.append(("order_block_broken", self._close(o, "BROKEN", now, "close_beyond")))
                continue
            if touched and not o.inside:
                o.inside, o.tests, o.status = True, o.tests + 1, "TESTED"
                out.append(("order_block_tested", o))
                if o.tests > self.c["max_tests"]:
                    out.append(("order_block_expired", self._close(o, "EXPIRED", now, "max_tests")))
            elif not touched:
                o.inside = False
        return out

    def _close(self, o: OrderBlock, status: str, now: int, reason: str) -> OrderBlock:
        o.status, o.closed_at, o.close_reason = status, now, reason
        self.active.remove(o)
        self.closed.append(o)
        del self.closed[:-200]
        return o
