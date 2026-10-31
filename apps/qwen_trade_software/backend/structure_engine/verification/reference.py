"""Offline (non-streaming) reference implementations.

Written independently of the streaming detectors, as plain loops over the
complete bar list — the way you would check a chart by hand with hindsight.
If the causal, streaming detector ever disagrees with this reference, one
of them is wrong; the tests demand they agree exactly.
"""

from __future__ import annotations

from ..bars import Bar


def reference_swings(bars: list[Bar], k: int) -> list[tuple[str, int, float]]:
    """Every (kind, time, price) fractal swing in a complete bar list.

    Same definition as swings.py: strictly beyond the k bars before, not
    exceeded by the k bars after. The last k bars can never qualify (their
    right side does not exist yet) — exactly like live.
    """
    out = []
    for i in range(k, len(bars) - k):
        c = bars[i]
        before, after = bars[i - k:i], bars[i + 1:i + k + 1]
        if all(c.high > b.high for b in before) and all(c.high >= b.high for b in after):
            out.append(("high", c.time, c.high))
        if all(c.low < b.low for b in before) and all(c.low <= b.low for b in after):
            out.append(("low", c.time, c.low))
    return out
