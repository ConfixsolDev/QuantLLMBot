r"""Higher-timeframe levels and what M1 does at them (strategy Part A4).

The liquidity book (liquidity.py) answers "what happened to the stops the
FIRST time price got there". This module follows a level for its whole life:
every TEST, how price arrived, whether M1 rejected it, whether the rejection
followed through, and whether the level finally held or broke. It describes;
it never decides a trade.

Levels (config ``htf_levels.sources``)
--------------------------------------
* confirmed swings of ``swing_timeframes`` (H1, H4)
* confirmed session / prior-day / prior-week highs and lows (``session_levels``)

A HIGH level is resistance: it is only registered while price is below it
(a swing high that price already closed above is not resistance any more).
Levels within ``merge_tolerance_atr`` of each other are ONE level with several
``sources`` (an H1 swing high at the London high = confluence); until its
first test the merged level sits at the outermost of their prices.
All distances are in ATR of ``atr_timeframe`` (M15), as of the moment.

Life of a level, drawn for a resistance (support is the mirror image)::

        level ─────────x──────────────x─────x─────────────  (x = touches)
                      /  \    test 1 /\ t2 / \  ...
        price  ______/    \_________/  \__/   \__
                    ^ away  ^ held: 1 ATR away   ^ broken: M5 close
                    (>= reset_atr below)           > level + break_buffer

  level_created     a new level (not merged into an existing one)
  level_test        the M1 high comes within touch_tolerance_atr of the level
                    after price had been at least reset_atr away. Counted:
                    test 1, 2, 3 ... Carries:
                      approach   push    — >= push.min_move_atr into the level
                                           in the last approach_bars M1 bars,
                                           efficiency (net / path) >= min_efficiency
                                 squeeze — >= squeeze.min_pressing_bars of those
                                           bars within 0.5 ATR of the level, the
                                           range contracting (<= max_range_ratio of
                                           the window before) and rising lows into
                                           resistance (falling highs into support)
                                 drift   — neither
                      stretch    how far price travelled into the level over
                                 stretch_lookback_hours, in H1 ATR
                      trend      M15 / H1 / H4 trend state (trend.py) at the touch
  level_rejection   within rejection_within_bars of the touch, an M1 candle
                    pokes beyond the level by >= rejection_min_pierce_atr and
                    CLOSES back inside ("poke and reclaim")
  level_followthrough  followthrough_bars M1 candles after the rejection:
                    "moved" if price got >= followthrough_atr away from the
                    level, else "stalled"
  level_held        after a test, price gets hold_atr away from the level
  level_broken      a ``break_timeframe`` (M5) candle CLOSES beyond the level by
                    break_buffer_atr; the level is retired
  level_expired     max_age_hours passed without a break (never during a test)
  level_pattern     an M1 double/triple top (bottom) is CONFIRMED whose peaks
                    are within pattern_link_atr of a level tested in the last
                    pattern_link_hours — the M1 pattern "formed at" that level

What the data said before this was built (study, Part B, 2026-11-01): a bare
touch holds no better than a random level; first tests break more often than
random, second tests hold more often; a rejection that does not move away
within 3 bars fails most of the time. So the events above record exactly the
facts that separated outcomes, and nothing is filtered on them.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .bars import Bar

HOUR = 3600


@dataclass
class _Test:
    no: int
    time: int
    atr: float
    bars: int = 0
    rejection: dict | None = None
    ft_left: int | None = None        # M1 bars until the follow-through verdict
    ft_best: float = 0.0              # best distance away since the rejection


@dataclass
class Level:
    id: str
    price: float
    side: str                         # "high" (resistance) | "low" (support)
    sources: list[str]
    time: int                         # time of the structure that made it
    created_at: int
    expires_at: int
    tests: int = 0
    away: bool = False
    test: _Test | None = None
    last_test_time: int | None = None
    held: int = 0
    tags: list = field(default_factory=list)

    @property
    def sgn(self) -> int:
        return 1 if self.side == "high" else -1

    def as_dict(self) -> dict:
        return {"id": self.id, "price": self.price, "side": self.side, "sources": list(self.sources),
                "time": self.time, "created_at": self.created_at, "tests": self.tests, "held": self.held}


class LevelBook:
    def __init__(self, cfg: dict, make_id) -> None:
        self.c = cfg["htf_levels"]
        self.make_id = make_id
        self.active: list[Level] = []
        n = max(2 * self.c["approach_bars"], self.c["stretch_lookback_hours"] * 60) + 1
        self.m1: deque[Bar] = deque(maxlen=n)

    # ------------------------------------------------------------ registration
    def add(self, source: str, side: str, price: float, time: int, now: int, atr: float | None,
            last_close: float | None) -> Level | None:
        """Register a level; returns it when NEW (None when merged or not a level)."""
        if atr is None or atr <= 0 or last_close is None:
            return None
        sgn = 1 if side == "high" else -1
        if sgn * (price - last_close) <= 0:          # already beyond: not this kind of level
            return None
        for lv in self.active:
            if lv.side == side and abs(lv.price - price) <= self.c["merge_tolerance_atr"] * atr:
                if source not in lv.sources:
                    lv.sources.append(source)
                # a cluster is guarded by its OUTERMOST price (a poke through the
                # inner one is not a rejection of the cluster); only while untested
                if lv.tests == 0 and sgn * (price - lv.price) > 0:
                    lv.price = price
                lv.expires_at = max(lv.expires_at, now + self.c["max_age_hours"] * HOUR)
                return None
        lv = Level(self.make_id(source, side, time, round(price, 5)), price, side, [source], time, now,
                   now + self.c["max_age_hours"] * HOUR)
        lv.away = sgn * (price - last_close) > self.c["reset_atr"] * atr
        self.active.append(lv)
        return lv

    # ------------------------------------------------------------ every M1 bar
    def on_m1(self, bar: Bar, now: int, atr: float | None, h1_atr: float | None,
              trends: dict) -> list[tuple[str, Level, dict]]:
        c, out = self.c, []
        if atr is not None and atr > 0:
            for lv in list(self.active):
                s, p = lv.sgn, lv.price
                ext = bar.high if s > 0 else bar.low          # toward / beyond the level
                opp = bar.low if s > 0 else bar.high          # away from the level
                dist = s * (p - ext)                          # > 0: not reached
                t = lv.test
                if t is not None:
                    t.bars += 1
                    if t.ft_left is not None:
                        t.ft_best = max(t.ft_best, s * (p - opp))
                        t.ft_left -= 1
                        if t.ft_left == 0:
                            moved = t.ft_best >= c["followthrough_atr"] * t.atr
                            out.append(("level_followthrough", lv, {
                                "test_no": t.no, "result": "moved" if moved else "stalled",
                                "move_atr": round(t.ft_best / t.atr, 3),
                                "rejection_time": t.rejection["candle"]["time"]}))
                            t.ft_left = None
                    self._rejection(lv, t, bar, out)
                    if s * (p - opp) >= c["hold_atr"] * t.atr:
                        if t.ft_left is not None:            # held before the verdict: it moved
                            out.append(("level_followthrough", lv, {
                                "test_no": t.no, "result": "moved", "move_atr": round(t.ft_best / t.atr, 3),
                                "rejection_time": t.rejection["candle"]["time"]}))
                        lv.held += 1
                        out.append(("level_held", lv, {"test_no": t.no, "bars": t.bars,
                                                       "rejected": t.rejection is not None}))
                        lv.test, lv.away = None, True
                    continue
                if dist > c["reset_atr"] * atr:
                    lv.away = True
                if lv.away and dist <= c["touch_tolerance_atr"] * atr:
                    lv.tests += 1
                    lv.away = False
                    lv.last_test_time = bar.time
                    lv.test = _Test(lv.tests, bar.time, atr)
                    out.append(("level_test", lv, {
                        "test_no": lv.tests, "candle": bar.as_dict(), "atr": round(atr, 4),
                        **self._approach(lv, atr), "stretch_h1_atr": self._stretch(lv, bar, h1_atr),
                        "trend": dict(trends)}))
                    self._rejection(lv, lv.test, bar, out)      # the touch candle itself may reject
        self.m1.append(bar)
        for lv in list(self.active):                            # age out (never mid-test)
            if now >= lv.expires_at and lv.test is None:
                self.active.remove(lv)
                out.append(("level_expired", lv, {"tests": lv.tests}))
        return out

    def _rejection(self, lv: Level, t: _Test, bar: Bar, out: list) -> None:
        c, s, p = self.c, lv.sgn, lv.price
        if t.rejection is not None or t.bars > c["rejection_within_bars"]:
            return
        pierce = s * ((bar.high if s > 0 else bar.low) - p)
        if pierce >= c["rejection_min_pierce_atr"] * t.atr and s * (p - bar.close) > 0:
            t.rejection = {"candle": bar.as_dict(), "pierce_atr": round(pierce / t.atr, 3)}
            t.ft_left = c["followthrough_bars"]
            t.ft_best = 0.0
            out.append(("level_rejection", lv, {"test_no": t.no, **t.rejection,
                                                 "bars_after_touch": t.bars}))

    # ------------------------------------------------------------ break (M5 close)
    def on_break_bar(self, bar: Bar, atr: float | None) -> list[tuple[str, Level, dict]]:
        out = []
        if atr is None or atr <= 0:
            return out
        for lv in list(self.active):
            if lv.sgn * (bar.close - lv.price) > self.c["break_buffer_atr"] * atr:
                out.append(("level_broken", lv, {"candle": bar.as_dict(), "tests": lv.tests,
                                                 "during_test": lv.test.no if lv.test else None}))
                self.active.remove(lv)
        return out

    # ------------------------------------------------------------ pattern link
    def on_pattern(self, pat: dict, now: int, atr: float | None) -> tuple[Level, dict] | None:
        """A confirmed M1 double/triple top/bottom: which tested level did it form at?"""
        if atr is None or atr <= 0:
            return None
        top = pat["kind"].endswith("top")
        side = "high" if top else "low"
        peak = (max if top else min)(p["price"] for p in pat["peaks"])
        best = None
        for lv in self.active:
            if lv.side != side or lv.last_test_time is None:
                continue
            if lv.last_test_time < now - self.c["pattern_link_hours"] * HOUR:
                continue
            d = abs(peak - lv.price)
            if d <= self.c["pattern_link_atr"] * atr and (best is None or d < best[0]):
                best = (d, lv)
        if best is None:
            return None
        lv = best[1]
        return lv, {"pattern_id": pat["id"], "pattern": pat["kind"], "neckline": pat["neckline"],
                    "peaks": pat["peaks"], "test_no": lv.tests, "distance_atr": round(best[0] / atr, 3),
                    "tags": pat.get("tags", {})}

    # ------------------------------------------------------------ context at a touch
    def _approach(self, lv: Level, atr: float) -> dict:
        c, n = self.c, self.c["approach_bars"]
        if len(self.m1) < 2 * n:
            return {"approach": "unknown"}
        bars = list(self.m1)
        w, prev = bars[-n:], bars[-2 * n:-n]
        s, p = lv.sgn, lv.price
        net = s * (w[-1].close - w[0].open)
        path = sum(abs(b.close - b.open) for b in w) or 1e-12
        rng = max(b.high for b in w) - min(b.low for b in w)
        rng_prev = (max(b.high for b in prev) - min(b.low for b in prev)) or 1e-12
        press = sum(1 for b in w if s * (p - (b.high if s > 0 else b.low)) <= 0.5 * atr)
        opp = [(b.low if s > 0 else -b.high) for b in w]
        mx, my = (n - 1) / 2, sum(opp) / n
        slope = sum((i - mx) * (v - my) for i, v in enumerate(opp)) / sum((i - mx) ** 2 for i in range(n))
        sq, pu = c["squeeze"], c["push"]
        if press >= sq["min_pressing_bars"] and rng / rng_prev <= sq["max_range_ratio"] \
                and slope * n >= sq["min_drift_atr"] * atr:
            kind = "squeeze"
        elif net >= pu["min_move_atr"] * atr and net / path >= pu["min_efficiency"]:
            kind = "push"
        else:
            kind = "drift"
        return {"approach": kind, "approach_detail": {
            "net_atr": round(net / atr, 3), "efficiency": round(net / path, 3), "pressing_bars": press,
            "range_ratio": round(rng / rng_prev, 3), "drift_atr": round(slope * n / atr, 3)}}

    def _stretch(self, lv: Level, bar: Bar, h1_atr: float | None) -> float | None:
        if h1_atr is None or h1_atr <= 0 or not self.m1:
            return None
        n = self.c["stretch_lookback_hours"] * 60
        w = list(self.m1)[-n:] + [bar]
        if lv.sgn > 0:
            return round((bar.high - min(b.low for b in w)) / h1_atr, 3)
        return round((max(b.high for b in w) - bar.low) / h1_atr, 3)
