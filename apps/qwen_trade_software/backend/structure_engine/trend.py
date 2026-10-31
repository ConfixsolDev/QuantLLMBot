"""Trend state, BOS (break of structure) and CHoCH (change of character).

Per timeframe, built ONLY from confirmed swings (swings.py) and candle CLOSES.

The state machine
-----------------
::

    state "none" --close beyond the latest swing--> BOS, state up / down
    state "up":
        close ABOVE the latest unbroken swing high  -> BOS up   (continuation)
            protected low := the latest confirmed swing low at that moment
        close BELOW the protected low               -> CHoCH down, state "down"
            protected high := the latest confirmed swing high at that moment
    state "down": the mirror image

* "Protected" low = the swing low the up-trend must hold. In practice it is
  the pull-back low that launched the last BOS. Losing it by a CLOSE is the
  change of character.
* A WICK beyond a level is NOT a break. Wicks beyond levels are liquidity
  sweeps (liquidity.py); only a close counts here.
* A swing can be broken once. Swing lows broken inside an up-trend that are
  NOT the protected low (minor pull-back lows) are retired quietly: they are
  internal structure, not a change of character.
* A swing only exists once it is confirmed (k candles after it), so a level
  cannot be "broken" before the engine could know it was a swing: no
  look-ahead. A BOS is known at the close of the breaking candle.

Each event records the broken level and its swing, the breaking candle,
whether that candle was displacement, and the trend before/after. The
breaking leg's origin (lowest low before an up-break) is passed on for
order-block detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bars import Bar
from .swings import Swing


@dataclass
class _Level:
    swing: Swing
    broken: bool = False


@dataclass
class TrendTracker:
    tf: str
    buffer_atr: float
    history: int
    state: str = "none"
    highs: list = field(default_factory=list)      # _Level, oldest first
    lows: list = field(default_factory=list)
    protected: _Level | None = None                 # protected low (up) / high (down)
    last_break: dict | None = None

    def add_swings(self, swings: list[Swing]) -> None:
        for s in swings:
            (self.highs if s.kind == "high" else self.lows).append(_Level(s))
            if self.state == "up" and s.kind == "low" and self.protected is None:
                self.protected = self.lows[-1]
            if self.state == "down" and s.kind == "high" and self.protected is None:
                self.protected = self.highs[-1]
        del self.highs[:-self.history]
        del self.lows[:-self.history]

    @staticmethod
    def _latest_unbroken(levels: list) -> _Level | None:
        for lv in reversed(levels):
            if not lv.broken:
                return lv
        return None

    def on_bar(self, bar: Bar, atr: float | None, disp: dict | None) -> list[dict]:
        """A candle of this timeframe CLOSED (after its swings were added)."""
        buf = self.buffer_atr * (atr or 0.0)
        out = []
        # ----- protected level lost: change of character
        if self.protected is not None and not self.protected.broken:
            p = self.protected.swing
            if self.state == "up" and bar.close < p.price - buf:
                out.append(self._break("choch", "down", self.protected, bar, disp))
            elif self.state == "down" and bar.close > p.price + buf:
                out.append(self._break("choch", "up", self.protected, bar, disp))
        if out:
            return out
        # ----- continuation (or first) break
        hi = self._latest_unbroken(self.highs)
        lo = self._latest_unbroken(self.lows)
        if self.state in ("up", "none") and hi and bar.close > hi.swing.price + buf:
            out.append(self._break("bos", "up", hi, bar, disp))
        elif self.state in ("down", "none") and lo and bar.close < lo.swing.price - buf:
            out.append(self._break("bos", "down", lo, bar, disp))
        else:
            # internal levels taken inside the trend: retire quietly
            if self.state == "up" and lo and bar.close < lo.swing.price - buf and lo is not self.protected:
                lo.broken = True
            if self.state == "down" and hi and bar.close > hi.swing.price + buf and hi is not self.protected:
                hi.broken = True
        return out

    def _break(self, kind: str, direction: str, level: _Level, bar: Bar, disp: dict | None) -> dict:
        level.broken = True
        before = self.state
        self.state = "up" if direction == "up" else "down"
        # new protected level: the latest swing on the opposite side
        opposite = self.lows if direction == "up" else self.highs
        self.protected = self._latest_unbroken(opposite)
        # levels beyond the broken one in the old direction are now stale
        for lv in (self.highs if direction == "up" else self.lows):
            beyond = lv.swing.price <= level.swing.price if direction == "up" else lv.swing.price >= level.swing.price
            if beyond:
                lv.broken = True
        self.last_break = {
            "kind": kind, "direction": direction, "level": level.swing.price,
            "level_time": level.swing.time, "level_label": level.swing.label,
            "break_time": bar.time, "break_close": bar.close,
            "displacement": disp is not None and disp["direction"] == direction,
            "trend_before": before, "trend_after": self.state,
            "protected": self.protected.swing.price if self.protected else None,
            "protected_time": self.protected.swing.time if self.protected else None,
        }
        return dict(self.last_break)

    def state_dict(self) -> dict:
        return {"state": self.state,
                "protected": self.protected.swing.price if self.protected and not self.protected.broken else None,
                "last_break": self.last_break}
