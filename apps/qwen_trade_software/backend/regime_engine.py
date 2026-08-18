"""Regime detection engine — combined ATR + displacement + swings + range.

Python produces a hint. Qwen later judges whether the hint is right.
Phase 1: compute and log only. Do not change entry or management behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import displacement
import live_mapped_levels
from market_atr import snapshot_atr_from_cache

MAPPED_LEVEL_MAX_DISTANCE = 30.0


@dataclass
class RegimeContext:
    """Immutable regime snapshot for one review cycle."""

    atr_m1_51: float | None
    atr_m1_3: float | None
    atr_ratio_3_51: float | None
    m5_body_atr_ratio: float | None
    m5_body_pct: float | None
    displacement_at_level: str | None
    displacement_through: bool | None
    m5_swing_pattern: str
    m15_swing_pattern: str
    range_detected: bool
    range_resistance: float | None
    range_support: float | None
    range_width: float | None
    range_width_atr: float | None
    range_bounces: int
    regime_hint: str
    prev_regime_hint: str | None
    regime_transition: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mapped_level_within_distance(
    mid: float,
    current_price: float | None,
    max_distance: float = MAPPED_LEVEL_MAX_DISTANCE,
) -> bool:
    """Keep operator-mapped shelves near the live price."""
    if current_price is None:
        return True
    return abs(float(mid) - float(current_price)) <= max_distance


def _combined_swings(rows: list[dict], wing: int) -> list[dict]:
    if not rows:
        return []
    highs = live_mapped_levels.fractal_swings(rows, wing, "high")
    lows = live_mapped_levels.fractal_swings(rows, wing, "low")
    combined = highs + lows
    combined.sort(
        key=lambda item: (
            item.get("index", 0),
            str(item.get("close_time_utc") or ""),
        )
    )
    return combined


def _detect_range(
    m5_swings: list[dict],
    current_price: float,
    atr_slow: float | None,
    min_bounces: int = 3,
) -> dict | None:
    if len(m5_swings) < 4 or not atr_slow or atr_slow <= 0:
        return None

    def _kind(item: dict) -> str:
        return str(item.get("kind") or item.get("type") or "")

    recent = m5_swings[-8:] if len(m5_swings) >= 8 else m5_swings
    recent_highs = [float(item["price"]) for item in recent if _kind(item) == "high"]
    recent_lows = [float(item["price"]) for item in recent if _kind(item) == "low"]
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return None
    resistance = sum(recent_highs) / len(recent_highs)
    support = sum(recent_lows) / len(recent_lows)
    width = resistance - support
    if width <= 0:
        return None
    width_atr = width / atr_slow
    bounces = len(recent_highs) + len(recent_lows)
    inside = support - atr_slow <= current_price <= resistance + atr_slow
    if bounces >= min_bounces and 2.0 < width_atr < 12.0 and inside:
        return {
            "resistance": round(resistance, 3),
            "support": round(support, 3),
            "width": round(width, 3),
            "width_atr": round(width_atr, 2),
            "bounces": bounces,
        }
    return None


def _compute_hint(
    atr_ratio: float | None,
    displacement_ratio: float | None,
    swing_pattern: str,
    range_info: dict | None,
    displacement_through: bool | None,
    prev_atr_ratio: float | None,
    prev_regime: str | None,
) -> str:
    if atr_ratio is None:
        return "unknown"

    if (
        prev_atr_ratio is not None
        and prev_atr_ratio < 0.8
        and atr_ratio > 1.2
        and displacement_ratio is not None
        and displacement_ratio > 1.0
        and displacement_through is True
    ):
        return "breakout"

    if (
        prev_atr_ratio is not None
        and prev_atr_ratio > 1.2
        and atr_ratio < 1.0
        and displacement_through is False
    ):
        return "exhaustion"

    if swing_pattern in ("hh_hl", "lh_ll"):
        if atr_ratio > 1.0:
            return "trend"
        if displacement_ratio is not None and displacement_ratio > 1.0:
            return "trend"

    if range_info is not None and swing_pattern == "mixed":
        return "range"

    if swing_pattern == "mixed":
        return "range"
    if swing_pattern in ("hh_hl", "lh_ll"):
        return "trend"
    return "unknown"


def compute_regime(
    atr_m1_51: float | None,
    atr_m1_3: float | None,
    m5_candle: dict | None,
    m5_swings: list[dict],
    m15_swings: list[dict],
    current_price: float,
    levels: dict[str, float],
    prev_regime: str | None = None,
    prev_atr_ratio: float | None = None,
) -> RegimeContext:
    """Compute regime from combined signals. Called every M1 close."""
    atr_ratio = None
    if atr_m1_51 and atr_m1_3 and atr_m1_51 > 0:
        atr_ratio = round(atr_m1_3 / atr_m1_51, 4)

    m5_body_atr = None
    m5_body_pct = None
    disp_level = None
    disp_through = None
    if m5_candle and atr_m1_51 and atr_m1_51 > 0:
        disp = displacement.candle_displacement(m5_candle, atr_m1_51)
        m5_body_atr = disp["body_atr_ratio"]
        m5_body_pct = disp["body_pct"]
        at_level = displacement.displacement_at_level(m5_candle, levels, atr_m1_51)
        if at_level:
            disp_level = at_level["level_id"]
            disp_through = at_level["through"]

    m5_pattern = live_mapped_levels.classify_swing_sequence(m5_swings)
    m15_pattern = live_mapped_levels.classify_swing_sequence(m15_swings)
    range_info = _detect_range(m5_swings, current_price, atr_m1_51)
    hint = _compute_hint(
        atr_ratio,
        m5_body_atr,
        m5_pattern,
        range_info,
        disp_through,
        prev_atr_ratio,
        prev_regime,
    )
    transition = prev_regime is not None and hint != prev_regime
    return RegimeContext(
        atr_m1_51=atr_m1_51,
        atr_m1_3=atr_m1_3,
        atr_ratio_3_51=atr_ratio,
        m5_body_atr_ratio=m5_body_atr,
        m5_body_pct=m5_body_pct,
        displacement_at_level=disp_level,
        displacement_through=disp_through,
        m5_swing_pattern=m5_pattern,
        m15_swing_pattern=m15_pattern,
        range_detected=range_info is not None,
        range_resistance=range_info["resistance"] if range_info else None,
        range_support=range_info["support"] if range_info else None,
        range_width=range_info["width"] if range_info else None,
        range_width_atr=range_info["width_atr"] if range_info else None,
        range_bounces=range_info["bounces"] if range_info else 0,
        regime_hint=hint,
        prev_regime_hint=prev_regime,
        regime_transition=transition,
    )


def snapshot_regime(
    symbol: str,
    current_price: float,
    levels: dict[str, float],
    prev_regime: str | None = None,
    prev_atr_ratio: float | None = None,
) -> dict[str, Any]:
    """Build a loggable regime packet from cached bars. Never raises."""
    from market_context_cache import get_cached_completed_bars

    m1_bars = get_cached_completed_bars(symbol, "M1", 120)
    m5_bars = get_cached_completed_bars(symbol, "M5", 96)
    m15_bars = get_cached_completed_bars(symbol, "M15", 96)
    atr = snapshot_atr_from_cache(m1_bars, symbol) if m1_bars else {}
    m5_candle = m5_bars[-1] if m5_bars else None
    m5_wing = live_mapped_levels.WING["M5"]
    m15_wing = live_mapped_levels.WING["M15"]
    ctx = compute_regime(
        atr.get("atr_m1_51"),
        atr.get("atr_m1_3"),
        m5_candle,
        _combined_swings(m5_bars, m5_wing),
        _combined_swings(m15_bars, m15_wing),
        current_price,
        levels,
        prev_regime=prev_regime,
        prev_atr_ratio=prev_atr_ratio,
    )
    packet = ctx.to_dict()
    packet["atr_ok"] = bool(atr.get("ok"))
    packet["atr_error"] = atr.get("error")
    packet["atr_source"] = atr.get("source")
    packet["m1_bars"] = len(m1_bars)
    packet["m5_bars"] = len(m5_bars)
    return packet


def suggested_target_mode(hint: str | None) -> str | None:
    """Python suggestion for entry target_mode. Qwen may override."""
    return {
        "range": "scalp",
        "exhaustion": "scalp",
        "trend": "starter_basket",
        "breakout": "starter_basket",
    }.get(str(hint or "").strip().lower())
