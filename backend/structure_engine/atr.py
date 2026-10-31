"""Streaming Wilder ATR — the engine's universal "ruler".

Every distance threshold in the config is written in ATR units ("departure
of at least 2.0 ATR", "peaks within 0.35 ATR"). That makes one config work
whether gold trades at 1,800 or 4,000 and whether the market is quiet or wild.

Wilder's ATR (the classic definition, same as MT5's ATR indicator):

    true_range = max(high - low, |high - prev_close|, |low - prev_close|)
    first ATR  = simple average of the first ``period`` true ranges
    later ATR  = (prev_ATR * (period - 1) + true_range) / period

``value`` is None during warm-up (fewer than ``period`` bars). Detectors that
need ATR simply wait — they never guess.

Causality note: detectors read ``value`` BEFORE pushing the bar they are
judging (``engine.py`` keeps the order), so a big departure candle cannot
inflate the very ATR used to measure it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bars import Bar


@dataclass
class WilderATR:
    period: int
    value: float | None = None
    _prev_close: float | None = None
    _warmup: list[float] = field(default_factory=list)

    def update(self, bar: Bar) -> float | None:
        """Add one CLOSED bar and return the ATR including it."""
        if self._prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(bar.high - bar.low, abs(bar.high - self._prev_close),
                     abs(bar.low - self._prev_close))
        self._prev_close = bar.close
        if self.value is None:
            self._warmup.append(tr)
            if len(self._warmup) == self.period:
                self.value = sum(self._warmup) / self.period
                self._warmup.clear()
        else:
            self.value = (self.value * (self.period - 1) + tr) / self.period
        return self.value
