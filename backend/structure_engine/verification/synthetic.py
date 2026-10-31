"""Synthetic price series with structures PLANTED on purpose (ground truth).

Real data has no answer key. Synthetic data does: we build calm noise, plant
known structures into it, and also plant NEAR-MISS NEGATIVES that look
similar but must NOT be detected. Detector output vs plants gives exact
precision, recall and localisation error (see matching.py).

Everything is seeded (``random.Random(seed)``) -> fully reproducible.

Sizes are planted in ATR units, measured with the same Wilder ATR the engine
uses, so a plant is "3 ATR" in the engine's own ruler — not in an absolute
price that might be big or small depending on the noise.

Three generators
----------------
random_walk_m1      plain M1 random walk (swings are checked against an
                    independent offline reference, not against plants)
zone_series         plants base+departure zones on a chosen timeframe (M30,
                    H1, H4) plus weak-departure negatives, then expands every
                    timeframe candle into M1 bars
pattern_series      plants M1 double/triple tops and bottoms plus negatives:
                    shallow necklines and mismatched peaks
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..atr import WilderATR
from ..bars import Bar

START = 1_767_225_600          # 2026-01-01 00:00 UTC (aligned to every UTC-grid timeframe)
# 2026-04-06 06:00 UTC = Monday 02:00 New York (EDT): a New York H4 boundary
# that is also on every UTC grid. Zone series start here and end before the
# November DST switch, so planted H4 candles line up with the engine's H4.
ZONE_START = 1_775_455_200


@dataclass
class Synthetic:
    m1: list[Bar]
    truth: list[dict] = field(default_factory=list)       # must be detected
    negatives: list[dict] = field(default_factory=list)   # must NOT be detected


# ------------------------------------------------------------------ helpers
def _bar(t: int, o: float, c: float, wick_up: float, wick_dn: float, vol: float, minutes: int = 1) -> Bar:
    return Bar(t, o, max(o, c) + wick_up, min(o, c) - wick_dn, c, vol, minutes=minutes,
               m1_count=minutes, tf="M1" if minutes == 1 else f"{minutes}m")


def expand_to_m1(tf_bars: list[Bar], minutes: int) -> list[Bar]:
    """Turn each timeframe candle into ``minutes`` M1 bars that aggregate back
    to EXACTLY the same OHLC (tests prove it).

    Path inside the candle: open -> first extreme -> second extreme -> close,
    straight lines between, extremes at 1/3 and 2/3 of the candle. A bullish
    candle visits its low first; a bearish one its high first.
    """
    out: list[Bar] = []
    for b in tf_bars:
        n = minutes
        a, z = (b.low, b.high) if b.close >= b.open else (b.high, b.low)
        anchors = [(0, b.open), (max(1, n // 3), a), (max(2, 2 * n // 3), z), (n, b.close)]
        points = []
        for (i0, v0), (i1, v1) in zip(anchors, anchors[1:]):
            for i in range(i0, i1):
                points.append(v0 + (v1 - v0) * (i - i0) / (i1 - i0))
        points.append(b.close)
        vol = b.volume / n
        for j in range(n):
            o, c = points[j], points[j + 1]
            out.append(Bar(b.time + 60 * j, o, max(o, c), min(o, c), c, vol))
    return out


class _Noise:
    """Calm, STRUCTURE-FREE chop around a level, tracking its own Wilder ATR.

    Closes are pulled hard back to the level (reversion 0.6) with a small step,
    while wicks are twice as large. So candles have normal-looking ranges (the
    ATR) but the market never wanders far enough to build a real swing
    structure by accident. That matters: a generator whose "noise" contains
    genuine double bottoms would score the detector as wrong for finding
    them. (First version used reversion 0.35 and equal wick/step size; chop
    after each planted breakout then formed real 1.5-ATR patterns.)
    """

    def __init__(self, rng: random.Random, level: float, step_sd: float, period: int = 14):
        self.rng, self.level, self.sd = rng, level, step_sd
        self.close = level
        self.atr = WilderATR(period)

    def bar(self, t: int, minutes: int = 1, vol: float = 100.0) -> Bar:
        r = self.rng
        o = self.close
        c = o + 0.6 * (self.level - o) + r.gauss(0, self.sd / 2)
        b = _bar(t, o, c, abs(r.gauss(0, self.sd)), abs(r.gauss(0, self.sd)), vol * r.uniform(0.8, 1.2), minutes)
        return self.push(b)

    def push(self, b: Bar) -> Bar:
        self.close = b.close
        self.atr.update(b)
        return b

    @property
    def unit(self) -> float:
        """Current ATR (falls back to a noise-based estimate during warm-up)."""
        return self.atr.value or self.sd * 2.5


# ------------------------------------------------------------------ swings
def random_walk_m1(seed: int, n: int = 6000, start: int = START) -> list[Bar]:
    r = random.Random(seed)
    price, out = 2000.0, []
    for i in range(n):
        o = price
        c = o + r.gauss(0, 0.4)
        out.append(_bar(start + 60 * i, o, c, abs(r.gauss(0, 0.2)), abs(r.gauss(0, 0.2)), r.randint(50, 150)))
        price = c
    return out


# ------------------------------------------------------------------ zones
def zone_series(seed: int, tf: str, minutes: int, plants: int = 10, gap: int = 40,
                weak_share: float = 0.4, start: int = ZONE_START) -> Synthetic:
    """Plant demand/supply zones on timeframe ``tf`` (``minutes`` long)."""
    r = random.Random(seed)
    sec = minutes * 60
    noise = _Noise(r, 2000.0, 0.12)
    tf_bars: list[Bar] = []
    truth, negatives = [], []
    t = start

    def calm(k: int) -> None:
        nonlocal t
        for _ in range(k):
            tf_bars.append(noise.bar(t, minutes))
            t += sec

    calm(60)                                              # ATR warm-up and settle
    for _ in range(plants):
        up = r.random() < 0.5
        weak = r.random() < weak_share
        u = noise.unit
        s = 1 if up else -1
        # base: 1-3 tight candles at the current level
        base = []
        for _ in range(r.randint(1, 3)):
            o = noise.close
            c = o + r.uniform(-0.05, 0.05) * u
            b = noise.push(_bar(t, o, c, 0.1 * u, 0.1 * u, 100.0, minutes))
            tf_bars.append(b)
            base.append(b)
            t += sec
        # departure: d candles in one direction
        d = r.randint(1, 3)
        total = (r.uniform(0.6, 1.2) if weak else r.uniform(3.0, 4.5)) * u
        dep = []
        for i in range(d):
            o = noise.close
            c = o + s * total / d
            b = noise.push(_bar(t, o, c, 0.05 * u, 0.05 * u, 250.0, minutes))
            tf_bars.append(b)
            dep.append(b)
            t += sec
        noise.level = noise.close                         # new equilibrium after the move
        base_hi = max(b.high for b in base)
        base_lo = min(b.low for b in base)
        rec = {"tf": tf, "side": "demand" if up else "supply", "time": dep[0].time,
               "low": min(base_lo, dep[0].low) if up else base_lo,
               "high": base_hi if up else max(base_hi, dep[0].high)}
        (negatives if weak else truth).append(rec)
        calm(gap)
    return Synthetic(expand_to_m1(tf_bars, minutes), truth, negatives)


# ------------------------------------------------------------------ patterns
def pattern_series(seed: int, plants: int = 12, gap: int = 80) -> Synthetic:
    """Plant M1 double/triple tops & bottoms, plus two kinds of negatives:

    * ``shallow``   correct peaks but neckline depth only 0.4-0.9 ATR
    * ``mismatch``  peaks differ by 1.0-1.5 ATR (beyond tolerance)
    """
    r = random.Random(seed)
    noise = _Noise(r, 2000.0, 0.06)
    bars: list[Bar] = []
    truth, negatives = [], []
    t = START

    def calm(k: int) -> None:
        nonlocal t
        for _ in range(k):
            bars.append(noise.bar(t))
            t += 60

    def leg(target: float, n: int, u: float) -> Bar:
        """Straight move to ``target`` over n bars; the last bar ENDS at target
        with its extreme exactly there (a clean, unambiguous swing point)."""
        nonlocal t
        start = noise.close
        last = None
        for i in range(1, n + 1):
            o = noise.close
            c = start + (target - start) * i / n
            up = target >= start
            # wicks only on the side AWAY from the travel direction's end, so
            # the leg's final bar is the exact extreme (no later bar pokes past)
            wick = 0.03 * u * (i < n)
            last = noise.push(_bar(t, o, c, wick if up else 0.0, 0.0 if up else wick, 100.0))
            bars.append(last)
            t += 60
        return last

    calm(80)
    for _ in range(plants):
        top = r.random() < 0.5
        s = 1 if top else -1
        u = noise.unit * 4          # noise ATR is tiny; plant in "leg-sized" units
        kind_roll = r.random()
        if kind_roll < 0.6:
            variant, depth, mismatch = "valid", r.uniform(2.5, 4.0), 0.0
        elif kind_roll < 0.8:
            variant, depth, mismatch = "shallow", r.uniform(0.15, 0.3), 0.0
        else:
            variant, depth, mismatch = "mismatch", r.uniform(2.5, 4.0), r.uniform(1.2, 1.8)
        n_peaks = 3 if (variant == "valid" and r.random() < 0.3) else 2
        base = noise.close
        peak = base + s * 6 * u
        peaks = [leg(peak, 10, u)]
        for k in range(1, n_peaks):
            leg(peak - s * depth * u, 8, u)                    # down to the neckline area
            this_peak = peak + s * (r.uniform(-0.05, 0.05) * u if k < n_peaks or not mismatch else 0)
            if mismatch:
                this_peak = peak - s * mismatch * u
            peaks.append(leg(this_peak, 8, u))
        leg(peak - s * (depth + 1.5) * u, 8, u)               # break the neckline
        noise.level = noise.close
        rec = {"kind": f"{'triple' if n_peaks == 3 else 'double'}_{'top' if top else 'bottom'}",
               "peak_times": [b.time for b in peaks], "variant": variant}
        (truth if variant == "valid" else negatives).append(rec)
        calm(gap)
    return Synthetic(bars, truth, negatives)
