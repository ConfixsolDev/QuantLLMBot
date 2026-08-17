"""Closed-candle displacement vs ATR baseline.

Python measures body size and whether a displacement interacted with a mapped
level. Qwen judges whether that measurement is meaningful in context.
"""

from __future__ import annotations


def candle_displacement(
    candle: dict,
    atr_slow: float | None,
) -> dict:
    """Measure a single candle's displacement relative to ATR baseline."""
    o = float(candle["open"])
    h = float(candle["high"])
    l = float(candle["low"])
    c = float(candle["close"])
    body = abs(c - o)
    full_range = h - l
    body_pct = body / full_range if full_range > 0 else 0.0
    body_atr = body / atr_slow if atr_slow and atr_slow > 0 else None
    return {
        "body": round(body, 3),
        "range": round(full_range, 3),
        "body_pct": round(body_pct, 3),
        "body_atr_ratio": round(body_atr, 4) if body_atr is not None else None,
        "is_displacement": (
            body_pct > 0.65
            and body_atr is not None
            and body_atr > 0.8
        ),
        "direction": "up" if c > o else "down" if c < o else "flat",
    }


def displacement_at_level(
    candle: dict,
    levels: dict[str, float],
    atr_slow: float | None,
) -> dict | None:
    """Check if a displacement candle interacted with a mapped level."""
    disp = candle_displacement(candle, atr_slow)
    if not disp["is_displacement"]:
        return None
    for level_id, price in levels.items():
        price = float(price)
        if float(candle["low"]) <= price <= float(candle["high"]):
            through = (
                float(candle["close"]) > price
                if disp["direction"] == "up"
                else float(candle["close"]) < price
            )
            return {
                **disp,
                "level_id": level_id,
                "level_price": price,
                "through": through,
            }
    return None
