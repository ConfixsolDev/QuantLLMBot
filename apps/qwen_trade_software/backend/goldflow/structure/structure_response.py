"""Pair-agnostic closed-candle responses at mapped price zones.

Geometry is evaluated in native prices and reported in ATR-normalized units so
the same response vocabulary works for gold, FX, indices, and future markets.
The detector describes printed structure; it does not choose risk or place a
trade.
"""

from __future__ import annotations

from typing import Iterable


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _level_side(level: dict) -> str | None:
    text = " ".join(
        str(level.get(key) or "").lower()
        for key in ("id", "level_id", "pattern", "role", "label")
    )
    if "double_top" in text or "high" in text or "_h_" in text:
        return "resistance"
    if "double_bottom" in text or "low" in text or "_l_" in text:
        return "support"
    return None


def evaluate_zone_response(
    level: dict,
    closed_candle: dict,
    *,
    atr: float | None = None,
    point_size: float = 0.0,
) -> dict | None:
    """Measure one completed candle against one mapped zone.

    A zone is an interval, not an exact-price equality. ``atr`` only
    standardizes the reported distances; classification is based on probe and
    close location relative to the interval.
    """
    side = _level_side(level)
    if side is None or not closed_candle:
        return None
    lo = _number(level.get("lo", level.get("price", level.get("zone_low"))))
    hi = _number(level.get("hi", level.get("zone_high", lo)), lo)
    lo, hi = min(lo, hi), max(lo, hi)
    if lo == hi:
        # A mapped line still represents a minimum tradable zone.
        half = max(abs(_number(point_size)), 1e-12)
        lo, hi = lo - half, hi + half

    open_ = _number(closed_candle.get("open", closed_candle.get("o")))
    high = _number(closed_candle.get("high", closed_candle.get("h")))
    low = _number(closed_candle.get("low", closed_candle.get("l")))
    close = _number(closed_candle.get("close", closed_candle.get("c")))
    scale = max(abs(_number(atr)), hi - lo, abs(_number(point_size)), 1e-12)
    body = abs(close - open_)
    candle_range = max(high - low, 0.0)

    if side == "resistance":
        probed = high >= lo
        closed_back = close <= hi
        swept = high > hi and closed_back
        accepted = close > hi
        direction = "sell" if probed and closed_back else "buy" if accepted else None
        state = (
            "sweep_rejection" if swept else
            "probe_rejection" if probed and closed_back else
            "acceptance" if accepted else "no_response"
        )
        excursion = max(0.0, high - hi)
        return_distance = max(0.0, hi - close)
    else:
        probed = low <= hi
        closed_back = close >= lo
        swept = low < lo and closed_back
        accepted = close < lo
        direction = "buy" if probed and closed_back else "sell" if accepted else None
        state = (
            "sweep_rejection" if swept else
            "probe_rejection" if probed and closed_back else
            "acceptance" if accepted else "no_response"
        )
        excursion = max(0.0, lo - low)
        return_distance = max(0.0, close - lo)

    if state == "no_response":
        return None
    return {
        "level_id": level.get("id") or level.get("level_id"),
        "timeframe": level.get("tf") or level.get("timeframe"),
        "zone_low": round(lo, 8),
        "zone_high": round(hi, 8),
        "zone_side": side,
        "state": state,
        "direction": direction,
        "confirmed": state in {"sweep_rejection", "probe_rejection"},
        "swept": swept,
        "probe_depth_atr": round(excursion / scale, 4),
        "close_return_atr": round(return_distance / scale, 4),
        "body_fraction": round(body / candle_range, 4) if candle_range else 0.0,
        "candle_id": closed_candle.get("id") or closed_candle.get("evidence_id"),
    }


def evaluate_nearby_responses(
    levels: Iterable[dict],
    closed_candle: dict,
    *,
    atr: float | None = None,
    point_size: float = 0.0,
    limit: int = 8,
) -> list[dict]:
    """Return strongest current responses, with rejections before acceptance."""
    responses = [
        row for row in (
            evaluate_zone_response(
                level, closed_candle, atr=atr, point_size=point_size
            )
            for level in levels
        ) if row is not None
    ]
    rank = {"sweep_rejection": 0, "probe_rejection": 1, "acceptance": 2}
    responses.sort(
        key=lambda row: (
            rank.get(str(row.get("state")), 9),
            -_number(row.get("close_return_atr")),
            str(row.get("level_id") or ""),
        )
    )
    return responses[:limit]
