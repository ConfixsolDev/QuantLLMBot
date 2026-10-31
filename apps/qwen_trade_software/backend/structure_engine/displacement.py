"""Displacement: a strong, decisive candle — "the market meant it".

A displacement candle has a LARGE body relative to normal volatility and
little wick relative to its own range:

    body  >= min_body_atr  x ATR      (ATR of this timeframe, as of BEFORE the candle)
    body  >= min_body_ratio x range   (mostly body, not a wick-fest)

Direction = the candle's colour. Displacement is a building block:

* an ORDER BLOCK only counts when its leg contains displacement (order_blocks.py),
* a BOS/CHoCH records whether the breaking candle itself was displacement,
* a fair value gap records whether its middle candle was displacement.

Using the ATR from before the candle means a giant candle cannot shrink its
own yardstick (it would otherwise raise the ATR it is compared with).
"""

from __future__ import annotations

from .bars import Bar


def displacement(bar: Bar, atr: float | None, cfg: dict) -> dict | None:
    """Return {'direction', 'body_atr', 'body_ratio'} or None."""
    c = cfg["displacement"]
    if atr is None or atr <= 0 or bar.range <= 0 or bar.close == bar.open:
        return None
    body_atr = bar.body / atr
    ratio = bar.body / bar.range
    if body_atr < c["min_body_atr"] or ratio < c["min_body_ratio"]:
        return None
    return {"direction": "up" if bar.bullish else "down",
            "body_atr": round(body_atr, 4), "body_ratio": round(ratio, 4)}
