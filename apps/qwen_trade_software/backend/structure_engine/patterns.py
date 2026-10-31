r"""M1 double / triple tops and bottoms, built from confirmed M1 swings.

Double top, drawn (a double bottom is the same thing upside down)
-----------------------------------------------------------------
::

         peak 1          peak 2          <- two swing highs, within
          /\              /\                peak_tolerance_atr x ATR
         /  \            /  \
        /    \    /\    /    \
       /      \  /  \  /      \
      /        \/    \/        \         <- NECKLINE = lowest low between
                                \           the peaks; depth = lower peak
                                 \__        minus neckline, must be at least
                                    close   min_neckline_depth_atr x ATR
                                    below
                                    neckline => CONFIRMED

Life of a pattern
-----------------
1. PENDING     emitted when peak 2 is CONFIRMED as a swing (k bars after it).
               Shown in snapshot()['pending']; not yet a fact.
2. CONFIRMED   an M1 bar CLOSES beyond the neckline within
               ``confirm_within_bars`` of the last peak.
   INVALIDATED price trades beyond the peaks by ``invalidate_beyond_atr`` x
               ATR, or the time runs out.
   SUPERSEDED  a third matching peak turned the double into a TRIPLE (its
               two dips must be within triple_trough_tolerance_atr x ATR), or
               a newer, tighter double re-used this pattern's last peak.

Two geometry rules separate real patterns from noise:

* DEPTH  ``min_neckline_depth_atr``: two equal highs with only a tiny dip
  between them are not a double top ("shallow-neckline near miss").
* PRIOR MOVE  ``prior_move_min_atr`` within ``prior_move_lookback_bars``
  before peak 1: a top is a REVERSAL, so there must be an advance to reverse.
  Without this rule, ordinary sideways chop produces equal highs with a
  1.5-ATR dip all day long — the synthetic report showed ~17% precision
  before the rule was added (2026-10-31), almost all false hits in chop.
* PROPORTION  ``min_depth_prior_move_ratio``: after a big move, flat chop at
  the end of it still has wick extremes ~2.5 ATR apart. The dip must be at
  least this fraction of the advance it reverses, so a wiggle at the end of
  a trend is not mistaken for a top.

Tags (computed on the last peak's candle; descriptive, never a filter)
---------------------------------------------------------------------
sweep         the last peak poked beyond the first by >= sweep_min_atr x ATR
              (ran the stops above peak 1, then failed)
volume_spike  last peak candle volume >= volume_spike_ratio x average volume
              of the ``volume_lookback`` candles before it
exhaustion    the last peak candle's rejection wick is >= exhaustion_wick_ratio
              of its range (long upper wick on a top)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .bars import Bar
from .swings import Swing

PENDING, CONFIRMED, INVALIDATED, SUPERSEDED = "PENDING", "CONFIRMED", "INVALIDATED", "SUPERSEDED"


@dataclass
class Pattern:
    id: str
    kind: str                     # double_top | triple_top | double_bottom | triple_bottom
    top: bool                     # True for tops, False for bottoms
    peaks: list[Swing]
    neckline: float
    neckline_time: int
    depth_atr: float
    prior_move_atr: float
    atr: float
    tags: dict
    created_at: int
    status: str = PENDING
    resolved_at: int | None = None
    reason: str | None = None

    @property
    def last_index(self) -> int:
        return self.peaks[-1].index

    def as_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind,
            "peaks": [{"time": p.time, "price": p.price, "index": p.index} for p in self.peaks],
            "neckline": self.neckline, "neckline_time": self.neckline_time,
            "depth_atr": round(self.depth_atr, 4), "prior_move_atr": round(self.prior_move_atr, 4),
            "atr": round(self.atr, 6),
            "tags": self.tags, "status": self.status, "created_at": self.created_at,
            "resolved_at": self.resolved_at, "reason": self.reason,
        }


@dataclass
class PatternDetector:
    cfg: dict
    make_id: object                                   # callable(kind, time_key) -> id
    bars: deque = field(default=None)                 # (index, Bar) of recent M1 bars
    peaks: dict = field(default=None)                 # top(bool) -> deque[Swing]
    pending: list = field(default_factory=list)
    resolved: deque = field(default=None)

    def __post_init__(self) -> None:
        p = self.cfg["patterns"]
        self.p = p
        keep = (p["max_bars_between_peaks"] * 3 + p["confirm_within_bars"] + p["volume_lookback"]
                + p["prior_move_lookback_bars"] + 10)
        self.bars = deque(maxlen=keep)
        self.peaks = {True: deque(maxlen=p["history"]), False: deque(maxlen=p["history"])}
        self.resolved = deque(maxlen=p["history"])

    # helpers that make ONE code path serve both tops and bottoms
    @staticmethod
    def _beyond(a: float, b: float, top: bool) -> bool:
        """True when ``a`` is further in the peak direction than ``b``."""
        return a > b if top else a < b

    def _between(self, i_from: int, i_to: int) -> list[Bar]:
        """M1 bars strictly between two stream indexes."""
        return [b for i, b in self.bars if i_from < i < i_to]

    def _neck(self, bars: list[Bar], top: bool) -> tuple[float, int] | None:
        if not bars:
            return None
        pick = min(bars, key=lambda b: b.low) if top else max(bars, key=lambda b: b.high)
        return (pick.low, pick.time) if top else (pick.high, pick.time)

    # ------------------------------------------------------------- per bar
    def on_bar(self, bar: Bar, index: int, atr: float | None,
               new_swings: list[Swing], now: int) -> list[tuple[str, Pattern]]:
        """Feed one CLOSED M1 bar plus any M1 swings it confirmed.

        Order matters: first resolve existing patterns with this bar, THEN
        build new ones (which check the bars since their last peak themselves).
        """
        self.bars.append((index, bar))
        out: list[tuple[str, Pattern]] = []
        for pat in list(self.pending):
            res = self._resolve(pat, bar, index, now)
            if res:
                out.append(res)
        if atr is None:
            for s in new_swings:                       # still remember peaks
                self.peaks[s.kind == "high"].append(s)
            return out
        for s in new_swings:
            top = s.kind == "high"
            out.extend(self._on_peak(s, top, atr, index, now))
            self.peaks[top].append(s)
        return out

    def _resolve(self, pat: Pattern, bar: Bar, index: int, now: int):
        p = self.p
        extreme = max(x.price for x in pat.peaks) if pat.top else min(x.price for x in pat.peaks)
        limit = extreme + p["invalidate_beyond_atr"] * pat.atr * (1 if pat.top else -1)
        if self._beyond(bar.high if pat.top else bar.low, limit, pat.top):
            return ("pattern_invalidated", self._finish(pat, INVALIDATED, now, "new_extreme"))
        if (bar.close < pat.neckline) if pat.top else (bar.close > pat.neckline):
            return ("pattern_confirmed", self._finish(pat, CONFIRMED, now, "neckline_close"))
        if index - pat.last_index >= p["confirm_within_bars"]:
            return ("pattern_invalidated", self._finish(pat, INVALIDATED, now, "timeout"))
        return None

    def _finish(self, pat: Pattern, status: str, now: int, reason: str) -> Pattern:
        pat.status, pat.resolved_at, pat.reason = status, now, reason
        self.pending.remove(pat)
        self.resolved.append(pat)
        return pat

    # ------------------------------------------------------------- new peak
    def _on_peak(self, s2: Swing, top: bool, atr: float, index: int, now: int):
        p = self.p
        tol = p["peak_tolerance_atr"] * atr
        out = []
        # (a) Upgrade a pending DOUBLE into a TRIPLE?
        for pat in self.pending:
            if pat.top != top or len(pat.peaks) != 2:
                continue
            gap = s2.index - pat.last_index
            if not (p["min_bars_between_peaks"] <= gap <= p["max_bars_between_peaks"]):
                continue
            if abs(s2.price - pat.peaks[0].price) > tol:
                continue
            peaks = pat.peaks + [s2]
            built = self._build(peaks, top, atr, index, now, kind="triple")
            if built:
                out.append(("pattern_superseded", self._finish(pat, SUPERSEDED, now, "became_triple")))
                out.extend(built)
                return out
        # (b) Pair with an earlier peak into a DOUBLE (most recent match wins).
        for s1 in reversed(self.peaks[top]):
            gap = s2.index - s1.index
            if gap < p["min_bars_between_peaks"]:
                continue
            if gap > p["max_bars_between_peaks"]:
                break
            if abs(s2.price - s1.price) > tol:
                continue
            older = [pat for pat in self.pending if pat.top == top and pat.last_index == s1.index]
            built = self._build([s1, s2], top, atr, index, now, kind="double")
            if built:
                # An older pending pattern that ENDED at s1 (e.g. a far-away
                # earlier high paired with s1) is replaced by this tighter one.
                # Found 2026-10-31: without this, a coincidental old pairing
                # "used up" peak 1 and the real double top was never reported.
                for pat in older:
                    if pat in self.pending:
                        out.append(("pattern_superseded", self._finish(pat, SUPERSEDED, now, "replaced_by_newer")))
                return out + built
        return out

    def _build(self, peaks: list[Swing], top: bool, atr: float, index: int, now: int, kind: str):
        """Validate geometry, create the pattern, and check bars since the last peak."""
        p = self.p
        first, last = peaks[0], peaks[-1]
        prices = [x.price for x in peaks]
        crown = max(prices) if top else min(prices)
        weakest = min(prices) if top else max(prices)
        inner = self._between(first.index, last.index)
        if not inner:
            return []
        # the peaks must be the top of the structure: nothing between pokes above them
        if top and max(b.high for b in inner) > crown:
            return []
        if not top and min(b.low for b in inner) < crown:
            return []
        neck = self._neck(inner, top)
        neckline, neck_time = neck
        if kind == "triple":
            # The two dips of a triple must form ONE support (roughly equal).
            # Otherwise a stale, far-away high plus a fresh double top would be
            # glued into a "triple" whose neckline is far below price.
            dips = [self._neck(self._between(a.index, b.index), top) for a, b in zip(peaks, peaks[1:])]
            if any(d is None for d in dips) or abs(dips[0][0] - dips[1][0]) > p["triple_trough_tolerance_atr"] * atr:
                return []
        depth = (weakest - neckline) if top else (neckline - weakest)
        if depth < p["min_neckline_depth_atr"] * atr:
            return []                                     # shallow-neckline near miss
        # a reversal needs something to reverse: the advance into peak 1
        lead = [b for i, b in self.bars if first.index - p["prior_move_lookback_bars"] <= i < first.index]
        if not lead:
            return []
        prior_move = (first.price - min(b.low for b in lead)) if top else (max(b.high for b in lead) - first.price)
        if prior_move < p["prior_move_min_atr"] * atr:
            return []                                     # chop, not a reversal
        # the dip must be a real part of that move, not a wiggle at its end
        if depth < p["min_depth_prior_move_ratio"] * prior_move:
            return []
        # tags on the last peak candle
        lb = last.bar
        before = [b for i, b in self.bars if last.index - p["volume_lookback"] <= i < last.index]
        avg_vol = sum(b.volume for b in before) / len(before) if before else 0.0
        wick = (lb.high - max(lb.open, lb.close)) if top else (min(lb.open, lb.close) - lb.low)
        tags = {
            "sweep": self._beyond(last.price, first.price + (p["sweep_min_atr"] * atr * (1 if top else -1)), top),
            "volume_spike": avg_vol > 0 and lb.volume >= p["volume_spike_ratio"] * avg_vol,
            "exhaustion": lb.range > 0 and wick / lb.range >= p["exhaustion_wick_ratio"],
        }
        name = f"{kind}_{'top' if top else 'bottom'}"
        pat = Pattern(self.make_id(name, first.time, last.time), name, top, list(peaks),
                      neckline, neck_time, depth / atr, prior_move / atr, atr, tags, now)
        self.pending.append(pat)
        out = [("pattern_pending", pat)]
        # The last peak was confirmed k bars late; those k bars may already
        # have broken the neckline or invalidated the pattern.
        for i, b in [(i, b) for i, b in self.bars if i > last.index]:
            res = self._resolve(pat, b, i, now)
            if res:
                out.append(res)
                break
        return out
