"""Causal swing highs and lows (fractals) with HH / HL / LH / LL labels.

Definition (strength ``k`` per timeframe, from config ``swings.strength``)
-------------------------------------------------------------------------
Candle *c* is a SWING HIGH when

    c.high  >  high of each of the k candles BEFORE it   (strictly higher)
    c.high  >= high of each of the k candles AFTER it    (not exceeded)

and a SWING LOW mirrors that with lows. The asymmetric tie rule means a run
of exactly equal highs yields ONE swing (the first of them), never two.

Why "causal" matters
--------------------
We cannot know *c* is a swing until the k candles after it have CLOSED. So a
swing is emitted when candle c+k closes — its ``available_at`` — while its
``time`` is the open of candle c. A detector that labelled c a swing the
moment it printed a new high would "repaint" whenever price went higher a
minute later. Ours never does: once emitted, a swing is permanent.

Labels compare with the previous swing of the same type:
    highs:  HH (higher high) / LH (lower high) / EH (equal high)
    lows:   HL (higher low)  / LL (lower low)  / EL (equal low)
The very first swing of each type has label None.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .bars import Bar


@dataclass(frozen=True, slots=True)
class Swing:
    tf: str
    kind: str            # "high" | "low"
    time: int            # open time of the swing candle
    price: float         # its high (for highs) or low (for lows)
    index: int           # position of the swing candle in this timeframe's stream
    label: str | None    # HH/LH/EH or HL/LL/EL (None for the first)
    bar: Bar             # the swing candle itself (patterns read volume/wicks)

    def as_dict(self) -> dict:
        return {"kind": self.kind, "time": self.time, "price": self.price,
                "index": self.index, "label": self.label}


class SwingDetector:
    """One per timeframe. Feed CLOSED bars in order; get confirmed swings back."""

    def __init__(self, tf: str, strength: int, history: int) -> None:
        self.tf = tf
        self.k = strength
        self._window: deque[tuple[int, Bar]] = deque(maxlen=2 * strength + 1)
        self._index = -1                      # index of the last bar pushed
        self.last_high: Swing | None = None
        self.last_low: Swing | None = None
        self.recent: deque[Swing] = deque(maxlen=history)   # for snapshot()

    def update(self, bar: Bar) -> list[Swing]:
        self._index += 1
        self._window.append((self._index, bar))
        if len(self._window) < self._window.maxlen:
            return []                         # not enough candles on both sides yet
        k = self.k
        idx, c = self._window[k]              # the candidate sits in the middle
        left = [b for _, b in list(self._window)[:k]]
        right = [b for _, b in list(self._window)[k + 1:]]
        found: list[Swing] = []
        if all(c.high > b.high for b in left) and all(c.high >= b.high for b in right):
            found.append(self._make("high", idx, c))
        if all(c.low < b.low for b in left) and all(c.low <= b.low for b in right):
            found.append(self._make("low", idx, c))
        return found

    def _make(self, kind: str, idx: int, c: Bar) -> Swing:
        price = c.high if kind == "high" else c.low
        prev = self.last_high if kind == "high" else self.last_low
        label = None
        if prev is not None:
            if kind == "high":
                label = "HH" if price > prev.price else "LH" if price < prev.price else "EH"
            else:
                label = "HL" if price > prev.price else "LL" if price < prev.price else "EL"
        swing = Swing(self.tf, kind, c.time, price, idx, label, c)
        if kind == "high":
            self.last_high = swing
        else:
            self.last_low = swing
        self.recent.append(swing)
        return swing
