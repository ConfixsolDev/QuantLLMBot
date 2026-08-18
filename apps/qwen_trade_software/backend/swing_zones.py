"""Swing zone detection with dual-level (wick vs body) zone construction.

Every swing point produces a ZONE, not a line:
    - body_level  = max(open, close) for swing highs, min(open, close) for lows
    - wick_level  = high for swing highs, low for swing lows
    - zone        = the band between body and wick — the "hunt zone"

Price can poke into the hunt zone and come back (stop hunt / liquidity grab).
Whether the violation is real or fake is Qwen's call, using volume + body ratio
+ bars spent in zone.

Uses scipy.signal.argrelextrema on COMPLETED bars only — no look-ahead bias.
Swing detection is stable on streaming: once a swing is confirmed, it stays.

2026-08-17
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Literal

import numpy as np
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SwingZone:
    """A swing point with a body-to-wick zone."""
    type: Literal["swing_high", "swing_low"]
    bar_index: int                  # index in the input array
    bar_time: str                   # open_time_utc of the swing bar
    timeframe: str                  # M1, M5, M15, etc.

    # Dual levels
    wick_level: float               # high (swing high) or low (swing low)
    body_level: float               # max(open,close) or min(open,close)
    zone_width: float               # abs(wick - body)

    # Context at formation
    tick_volume_at_swing: int        # volume of the swing bar itself
    atr_at_swing: float | None       # ATR at the time, if available
    zone_width_atr_pct: float | None # zone_width / ATR — how wide is the hunt zone?

    # Tracking
    touch_count: int = 0            # how many times price returned to this zone
    is_active: bool = True          # deactivated after decisive close through


@dataclass
class ZoneViolation:
    """What happened when price entered a swing zone — Qwen's input."""
    zone: SwingZone
    violation_bar_index: int
    violation_bar_time: str

    # Where did the candle close relative to the zone?
    close_location: Literal[
        "before_zone",       # didn't reach zone
        "inside_zone",       # closed between body and wick (the hunt band)
        "beyond_wick",       # closed past even the wick — likely real break
    ]

    # Violation metrics
    bars_in_zone: int               # consecutive M1 closes inside the hunt band
    bars_beyond_wick: int           # closes past the wick extreme
    deepest_penetration: float      # how far past body_level did it go?

    # Volume context
    volume_during_violation: int    # total tick volume during violation bars
    avg_volume_20: int              # 20-bar average volume (baseline)
    volume_ratio: float             # violation volume / avg volume

    # Candle quality of the violation bar
    body_ratio: float               # body / range of violation bar (conviction)
    body_direction: Literal["with_break", "against_break"]  # is the body pushing through or rejecting?

    # Trust assessment hints (deterministic, not judgment)
    hunt_probability_hints: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core swing detection — no look-ahead
# ---------------------------------------------------------------------------

def detect_swings(
    highs: np.ndarray,
    lows: np.ndarray,
    order: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """Find swing highs and lows using scipy argrelextrema on completed bars.

    Parameters
    ----------
    highs : array of high prices (oldest first)
    lows  : array of low prices (oldest first)
    order : number of bars on each side required to confirm a swing.
            For M5: order=3 means 15 min each side (30 min total window).
            For M1: order=3 means 3 min each side.

    Returns
    -------
    swing_high_indices, swing_low_indices : arrays of indices where swings occur.

    Note: the last `order` bars can NEVER be swing points (not yet confirmed).
    This is the honest confirmation lag — no future data used.
    """
    swing_high_idx = argrelextrema(highs, np.greater_equal, order=order)[0]
    swing_low_idx = argrelextrema(lows, np.less_equal, order=order)[0]
    return swing_high_idx, swing_low_idx


def _enforce_alternation(
    highs: np.ndarray,
    lows: np.ndarray,
    sh_idx: np.ndarray,
    sl_idx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Remove consecutive same-type swings, keeping the more extreme one.

    If two swing highs appear in a row (no swing low between them), keep
    the higher one. If two swing lows in a row, keep the lower one.
    This matches Brooks's swing definition and the smartmoneyconcepts cleanup.
    """
    if len(sh_idx) == 0 or len(sl_idx) == 0:
        return sh_idx, sl_idx

    # Merge into a single sorted sequence with labels
    all_idx = np.concatenate([sh_idx, sl_idx])
    all_type = np.concatenate([
        np.ones(len(sh_idx), dtype=int),       # 1 = swing high
        -np.ones(len(sl_idx), dtype=int),      # -1 = swing low
    ])
    sort_order = np.argsort(all_idx)
    all_idx = all_idx[sort_order]
    all_type = all_type[sort_order]

    # Walk through and enforce alternation
    cleaned_idx = [all_idx[0]]
    cleaned_type = [all_type[0]]

    for i in range(1, len(all_idx)):
        if all_type[i] == cleaned_type[-1]:
            # Same type in a row — keep the more extreme
            if all_type[i] == 1:  # consecutive highs
                if highs[all_idx[i]] >= highs[cleaned_idx[-1]]:
                    cleaned_idx[-1] = all_idx[i]
            else:  # consecutive lows
                if lows[all_idx[i]] <= lows[cleaned_idx[-1]]:
                    cleaned_idx[-1] = all_idx[i]
        else:
            cleaned_idx.append(all_idx[i])
            cleaned_type.append(all_type[i])

    cleaned_idx = np.array(cleaned_idx)
    cleaned_type = np.array(cleaned_type)

    return (
        cleaned_idx[cleaned_type == 1],
        cleaned_idx[cleaned_type == -1],
    )


# ---------------------------------------------------------------------------
# Zone construction
# ---------------------------------------------------------------------------

def build_swing_zones(
    bars: list[dict],
    timeframe: str,
    order: int = 3,
    atr_value: float | None = None,
) -> list[SwingZone]:
    """Build swing zones from a list of completed OHLCV bar dicts.

    Each bar must have: open, high, low, close, tick_volume, open_time_utc.
    Returns zones sorted by bar_index (oldest first).

    Stability guarantee: only swings confirmed by at least `order` bars
    after them are emitted. A swing at index i is only returned when
    len(bars) > i + order.  This means the most recent `order` bars
    NEVER produce swings — that's the honest confirmation lag.
    """
    if len(bars) < (order * 2 + 1):
        return []

    opens = np.array([b["open"] for b in bars], dtype=np.float64)
    highs = np.array([b["high"] for b in bars], dtype=np.float64)
    lows = np.array([b["low"] for b in bars], dtype=np.float64)
    closes = np.array([b["close"] for b in bars], dtype=np.float64)

    sh_idx, sl_idx = detect_swings(highs, lows, order=order)

    # Stability filter: discard swings too close to the right edge.
    # A swing at index i needs `order` bars AFTER it to be confirmed.
    # Without this, adding one new bar can retroactively invalidate a swing.
    max_confirmed = len(bars) - 1 - order
    sh_idx = sh_idx[sh_idx <= max_confirmed]
    sl_idx = sl_idx[sl_idx <= max_confirmed]

    sh_idx, sl_idx = _enforce_alternation(highs, lows, sh_idx, sl_idx)

    zones: list[SwingZone] = []

    for idx in sh_idx:
        bar = bars[idx]
        wick = highs[idx]
        body = max(opens[idx], closes[idx])
        width = abs(wick - body)
        zones.append(SwingZone(
            type="swing_high",
            bar_index=int(idx),
            bar_time=bar.get("open_time_utc", ""),
            timeframe=timeframe,
            wick_level=round(wick, 2),
            body_level=round(body, 2),
            zone_width=round(width, 2),
            tick_volume_at_swing=bar.get("tick_volume", 0),
            atr_at_swing=atr_value,
            zone_width_atr_pct=round(width / atr_value, 4) if atr_value else None,
        ))

    for idx in sl_idx:
        bar = bars[idx]
        wick = lows[idx]
        body = min(opens[idx], closes[idx])
        width = abs(body - wick)
        zones.append(SwingZone(
            type="swing_low",
            bar_index=int(idx),
            bar_time=bar.get("open_time_utc", ""),
            timeframe=timeframe,
            wick_level=round(wick, 2),
            body_level=round(body, 2),
            zone_width=round(width, 2),
            tick_volume_at_swing=bar.get("tick_volume", 0),
            atr_at_swing=atr_value,
            zone_width_atr_pct=round(width / atr_value, 4) if atr_value else None,
        ))

    zones.sort(key=lambda z: z.bar_index)
    return zones


# ---------------------------------------------------------------------------
# Swing sequence classification (HH/HL/LH/LL → regime hint)
# ---------------------------------------------------------------------------

def classify_swing_sequence(
    zones: list[SwingZone],
    last_n: int = 6,
) -> dict:
    """Classify the last N swing points into a market structure sequence.

    Returns:
        sequence: list of labels like ["HL", "HH", "HL", "HH"]
        trend: "bullish" | "bearish" | "mixed"
        recent_highs: list of (bar_index, wick_level, body_level) for recent swing highs
        recent_lows: list of (bar_index, wick_level, body_level) for recent swing lows
    """
    if len(zones) < 4:
        return {
            "sequence": [],
            "trend": "insufficient_data",
            "recent_highs": [],
            "recent_lows": [],
        }

    recent = zones[-last_n:]

    # Separate highs and lows
    highs = [z for z in recent if z.type == "swing_high"]
    lows = [z for z in recent if z.type == "swing_low"]

    # Label each swing relative to the previous of same type
    labels = []
    for z in recent:
        if z.type == "swing_high":
            prev_highs = [h for h in highs if h.bar_index < z.bar_index]
            if prev_highs:
                prev = prev_highs[-1]
                labels.append("HH" if z.wick_level > prev.wick_level else "LH")
            else:
                labels.append("SH")  # first swing high, no comparison
        else:
            prev_lows = [l for l in lows if l.bar_index < z.bar_index]
            if prev_lows:
                prev = prev_lows[-1]
                labels.append("HL" if z.wick_level > prev.wick_level else "LL")
            else:
                labels.append("SL")  # first swing low

    # Classify trend from labels (ignoring the initial SH/SL markers)
    meaningful = [l for l in labels if l in ("HH", "HL", "LH", "LL")]
    if len(meaningful) < 2:
        trend = "insufficient_data"
    else:
        bullish_count = sum(1 for l in meaningful if l in ("HH", "HL"))
        bearish_count = sum(1 for l in meaningful if l in ("LH", "LL"))
        total = len(meaningful)
        if bullish_count / total >= 0.7:
            trend = "bullish"
        elif bearish_count / total >= 0.7:
            trend = "bearish"
        else:
            trend = "mixed"

    return {
        "sequence": labels,
        "trend": trend,
        "recent_highs": [
            {"bar_index": z.bar_index, "wick": z.wick_level, "body": z.body_level}
            for z in highs[-3:]
        ],
        "recent_lows": [
            {"bar_index": z.bar_index, "wick": z.wick_level, "body": z.body_level}
            for z in lows[-3:]
        ],
    }


# ---------------------------------------------------------------------------
# Violation detection — is price poking into a zone?
# ---------------------------------------------------------------------------

def check_zone_violations(
    zones: list[SwingZone],
    bars: list[dict],
    lookback_bars: int = 20,
) -> list[ZoneViolation]:
    """Check the most recent bars against active swing zones.

    For each active zone, if any of the last `lookback_bars` bars entered
    the zone, build a ZoneViolation with volume and conviction metrics.
    """
    if not zones or not bars:
        return []

    n = len(bars)
    start = max(0, n - lookback_bars)
    recent_bars = bars[start:]

    # 20-bar average volume for baseline
    vol_window = bars[max(0, n - 20):]
    avg_vol_20 = int(np.mean([b.get("tick_volume", 0) for b in vol_window])) or 1

    violations: list[ZoneViolation] = []

    for zone in zones:
        if not zone.is_active:
            continue
        # Skip zones that formed too recently (inside the lookback window)
        if zone.bar_index >= start:
            continue

        bars_in_zone = 0
        bars_beyond_wick = 0
        total_violation_volume = 0
        deepest = 0.0
        last_violation_bar = None

        for bar in recent_bars:
            close = bar["close"]
            high = bar["high"]
            low = bar["low"]

            if zone.type == "swing_high":
                # Zone is above: body_level (bottom of zone) to wick_level (top)
                entered = high >= zone.body_level
                if entered:
                    penetration = high - zone.body_level
                    deepest = max(deepest, penetration)
                    total_violation_volume += bar.get("tick_volume", 0)
                    last_violation_bar = bar

                    if close >= zone.body_level and close <= zone.wick_level:
                        bars_in_zone += 1
                    elif close > zone.wick_level:
                        bars_beyond_wick += 1

            else:  # swing_low
                # Zone is below: wick_level (bottom) to body_level (top of zone)
                entered = low <= zone.body_level
                if entered:
                    penetration = zone.body_level - low
                    deepest = max(deepest, penetration)
                    total_violation_volume += bar.get("tick_volume", 0)
                    last_violation_bar = bar

                    if close <= zone.body_level and close >= zone.wick_level:
                        bars_in_zone += 1
                    elif close < zone.wick_level:
                        bars_beyond_wick += 1

        if last_violation_bar is None:
            continue

        # Analyze the most recent violation bar
        bar = last_violation_bar
        bar_open = bar["open"]
        bar_close = bar["close"]
        bar_high = bar["high"]
        bar_low = bar["low"]
        bar_range = bar_high - bar_low
        bar_body = abs(bar_close - bar_open)
        body_ratio = round(bar_body / bar_range, 4) if bar_range > 0 else 0.0

        # Determine close location
        if zone.type == "swing_high":
            if bar_close > zone.wick_level:
                close_loc = "beyond_wick"
            elif bar_close >= zone.body_level:
                close_loc = "inside_zone"
            else:
                close_loc = "before_zone"
            # Body direction: bullish close above open = pushing through
            body_dir = "with_break" if bar_close > bar_open else "against_break"
        else:
            if bar_close < zone.wick_level:
                close_loc = "beyond_wick"
            elif bar_close <= zone.body_level:
                close_loc = "inside_zone"
            else:
                close_loc = "before_zone"
            body_dir = "with_break" if bar_close < bar_open else "against_break"

        volume_ratio = round(total_violation_volume / avg_vol_20, 2) if avg_vol_20 > 0 else 0.0

        # Build hunt probability hints (deterministic flags, not judgment)
        hints: list[str] = []
        if bars_beyond_wick == 0 and bars_in_zone > 0:
            hints.append("no_close_beyond_wick")
        if bars_beyond_wick >= 2:
            hints.append("multiple_closes_beyond_wick")
        if body_ratio < 0.3:
            hints.append("small_body_indecision")
        if body_ratio > 0.7:
            hints.append("large_body_conviction")
        if body_dir == "against_break":
            hints.append("body_rejecting")
        if body_dir == "with_break" and body_ratio > 0.5:
            hints.append("body_pushing_through")
        if volume_ratio > 1.5:
            hints.append("high_volume_violation")
        if volume_ratio < 0.7:
            hints.append("low_volume_violation")
        if zone.zone_width_atr_pct and zone.zone_width_atr_pct < 0.1:
            hints.append("very_tight_zone")

        zone.touch_count += 1

        violations.append(ZoneViolation(
            zone=zone,
            violation_bar_index=n - 1,
            violation_bar_time=bar.get("open_time_utc", ""),
            close_location=close_loc,
            bars_in_zone=bars_in_zone,
            bars_beyond_wick=bars_beyond_wick,
            deepest_penetration=round(deepest, 2),
            volume_during_violation=total_violation_volume,
            avg_volume_20=avg_vol_20,
            volume_ratio=volume_ratio,
            body_ratio=body_ratio,
            body_direction=body_dir,
            hunt_probability_hints=hints,
        ))

    return violations


# ---------------------------------------------------------------------------
# Qwen packet builder — the bridge to LLM management
# ---------------------------------------------------------------------------

def build_qwen_swing_packet(
    bars: list[dict],
    timeframe: str,
    order: int = 3,
    atr_value: float | None = None,
    violation_lookback: int = 10,
) -> dict:
    """One-call convenience: detect swings → build zones → check violations → classify.

    Returns a dict ready to inject into Qwen's management prompt:
    {
        "swing_zones": [...],          # all active zones
        "swing_sequence": {...},       # HH/HL/LH/LL classification + trend
        "active_violations": [...],    # zones currently being tested
        "zone_count": int,
        "timeframe": str,
    }
    """
    zones = build_swing_zones(bars, timeframe, order=order, atr_value=atr_value)
    sequence = classify_swing_sequence(zones)
    violations = check_zone_violations(zones, bars, lookback_bars=violation_lookback)

    # Serialize for Qwen prompt
    zone_dicts = []
    for z in zones:
        if z.is_active:
            zone_dicts.append({
                "type": z.type,
                "wick": z.wick_level,
                "body": z.body_level,
                "zone_width": z.zone_width,
                "zone_atr_pct": z.zone_width_atr_pct,
                "volume": z.tick_volume_at_swing,
                "touches": z.touch_count,
                "timeframe": z.timeframe,
                "bar_time": z.bar_time,
            })

    violation_dicts = []
    for v in violations:
        violation_dicts.append({
            "zone_type": v.zone.type,
            "zone_wick": v.zone.wick_level,
            "zone_body": v.zone.body_level,
            "close_location": v.close_location,
            "bars_in_zone": v.bars_in_zone,
            "bars_beyond_wick": v.bars_beyond_wick,
            "deepest_penetration": v.deepest_penetration,
            "volume_ratio": v.volume_ratio,
            "body_ratio": v.body_ratio,
            "body_direction": v.body_direction,
            "hints": v.hunt_probability_hints,
        })

    return {
        "timeframe": timeframe,
        "zone_count": len(zone_dicts),
        "swing_zones": zone_dicts,
        "swing_sequence": sequence,
        "active_violations": violation_dicts,
    }


# ---------------------------------------------------------------------------
# Multi-timeframe convenience
# ---------------------------------------------------------------------------

def build_multi_tf_swing_packet(
    bars_by_tf: dict[str, list[dict]],
    orders: dict[str, int] | None = None,
    atr_value: float | None = None,
) -> dict[str, dict]:
    """Build swing packets for multiple timeframes at once.

    Parameters
    ----------
    bars_by_tf : {"M1": [...], "M5": [...], "M15": [...]}
    orders : per-timeframe swing order, e.g. {"M1": 2, "M5": 3, "M15": 5}
    atr_value : current ATR (M1 slow)

    Returns dict keyed by timeframe.
    """
    default_orders = {"M1": 2, "M5": 3, "M15": 5, "M30": 5, "H1": 5, "H4": 3}
    orders = orders or default_orders

    result = {}
    for tf, bars in bars_by_tf.items():
        order = orders.get(tf, 3)
        result[tf] = build_qwen_swing_packet(
            bars, tf, order=order, atr_value=atr_value,
        )

    return result
