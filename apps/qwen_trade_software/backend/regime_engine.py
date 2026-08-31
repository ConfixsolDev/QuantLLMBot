"""Deterministic regime and volatility classification from closed market facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import displacement
import live_mapped_levels
from market_atr import snapshot_atr_from_cache
from instrument_config import instrument_for

MAPPED_LEVEL_MAX_DISTANCE = 30.0
TRANSITION_MAX_MINUTES = 15.0
TREND_STATES = frozenset({"trend_strong", "trend_channel"})
TRANSITION_STATES = frozenset({
    "breakout_attempt",
    "reversal_attempt",
    "climax_exhaustion",
})


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
    regime_state: str
    volatility_state: str
    trend_direction: str | None
    local_swing_direction: str | None
    prior_trend_direction: str | None
    pullback_active: bool
    transition_age_minutes: float | None
    transition_expired: bool
    current_price: float
    prev_regime_hint: str | None
    prev_regime_state: str | None
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


def _volatility_state(atr_ratio: float | None, prev_atr_ratio: float | None) -> str:
    if atr_ratio is None:
        return "unknown"
    if prev_atr_ratio is not None and prev_atr_ratio <= 0.9 and atr_ratio > 1.2:
        return "expansion"
    if atr_ratio < 0.75:
        return "contraction"
    if atr_ratio < 0.9:
        return "low"
    if atr_ratio <= 1.2:
        return "normal"
    return "high"


def _regime_state(
    hint: str,
    atr_ratio: float | None,
    body_atr: float | None,
    m5_pattern: str,
    m15_pattern: str,
    range_info: dict | None,
    displacement_through: bool | None,
    prev_regime: str | None,
    prev_regime_state: str | None = None,
    prev_trend_direction: str | None = None,
    transition_age_minutes: float | None = None,
) -> str:
    aligned = m5_pattern in ("hh_hl", "lh_ll")
    same_direction = m5_pattern == m15_pattern and aligned
    current_direction = {"hh_hl": "buy", "lh_ll": "sell"}.get(m5_pattern)
    transition_expired = (
        transition_age_minutes is not None
        and transition_age_minutes >= TRANSITION_MAX_MINUTES
    )

    def stable_from_current() -> str:
        if aligned:
            if same_direction and ((atr_ratio or 0) >= 1.1 or (body_atr or 0) >= 1.0):
                return "trend_strong"
            if same_direction:
                return "trend_channel"
            return "trending_range"
        if hint == "range":
            if (atr_ratio or 0) < 0.75 or (
                range_info and range_info["width_atr"] <= 3.0
            ):
                return "tight_range"
            return "range"
        return "unknown"

    # A reversal is a multi-cycle transition, not a pattern label.  The first
    # mixed M5 structure after a trend arms observation only.  Confirmation
    # requires a new opposite M5 swing sequence, structural displacement, and
    # M15 no longer maintaining the old sequence.  This makes the previously
    # dead reversal_confirmed policy reachable without allowing one double
    # top/bottom or wick to flip the market state.
    if prev_regime_state == "reversal_attempt":
        opposite_structure = (
            current_direction is not None
            and prev_trend_direction in {"buy", "sell"}
            and current_direction != prev_trend_direction
        )
        m15_old_pattern = {
            "buy": "hh_hl",
            "sell": "lh_ll",
        }.get(prev_trend_direction)
        structural_break = (
            displacement_through is True and (body_atr or 0.0) >= 0.8
        )
        if opposite_structure and structural_break and m15_pattern != m15_old_pattern:
            return "reversal_confirmed"
        if opposite_structure and transition_expired:
            return "reversal_confirmed"
        if current_direction == prev_trend_direction:
            return stable_from_current()
        if m5_pattern == "mixed" and transition_expired:
            return "range" if (atr_ratio or 0) >= 0.75 else "tight_range"
        if m5_pattern == "mixed" or opposite_structure:
            return "reversal_attempt"

    if prev_regime_state == "climax_exhaustion" and transition_expired:
        return stable_from_current()
    if hint == "breakout":
        return "breakout_confirmed"
    if hint == "exhaustion":
        return "climax_exhaustion"

    if prev_regime_state in TREND_STATES:
        opposite_structure = (
            current_direction is not None
            and prev_trend_direction in {"buy", "sell"}
            and current_direction != prev_trend_direction
        )
        if opposite_structure:
            m15_old_pattern = {
                "buy": "hh_hl",
                "sell": "lh_ll",
            }.get(prev_trend_direction)
            structural_break = (
                displacement_through is True and (body_atr or 0.0) >= 0.8
            )
            if (
                structural_break and m15_pattern != m15_old_pattern
            ) or transition_expired:
                return "reversal_confirmed"
            return "reversal_attempt"
        if m5_pattern == "mixed":
            if transition_expired:
                return "range" if (atr_ratio or 0) >= 0.75 else "tight_range"
            # A mixed local leg inside an established trend is the normal
            # pullback state. Keep the owning trend tradable while Qwen waits
            # for the mapped with-trend response.
            return prev_regime_state

    if prev_regime_state == "breakout_attempt" and transition_expired:
        return stable_from_current()
    if prev_regime in ("trend", "breakout") and m5_pattern == "mixed":
        return "trend_channel"
    if displacement_through is True and prev_regime == "range":
        return "breakout_attempt"
    if aligned:
        if same_direction and ((atr_ratio or 0) >= 1.1 or (body_atr or 0) >= 1.0):
            return "trend_strong"
        if same_direction:
            return "trend_channel"
        return "trending_range"
    if hint == "range":
        if (atr_ratio or 0) < 0.75 or (range_info and range_info["width_atr"] <= 3.0):
            return "tight_range"
        return "range"
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
    prev_regime_state: str | None = None,
    prev_trend_direction: str | None = None,
    transition_age_minutes: float | None = None,
    price_digits: int = 3,
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
    state = _regime_state(
        hint, atr_ratio, m5_body_atr, m5_pattern, m15_pattern,
        range_info, disp_through, prev_regime,
        prev_regime_state, prev_trend_direction, transition_age_minutes,
    )
    local_direction = {"hh_hl": "buy", "lh_ll": "sell"}.get(m5_pattern)
    pullback_active = (
        (
            prev_regime_state in TREND_STATES
            or (
                prev_regime_state is None
                and prev_regime in {"trend", "breakout"}
                and prev_trend_direction in {"buy", "sell"}
            )
        )
        and state in TREND_STATES
        and m5_pattern == "mixed"
    )
    effective_direction = (
        prev_trend_direction if pullback_active else local_direction
    )
    transition_expired = (
        transition_age_minutes is not None
        and transition_age_minutes >= TRANSITION_MAX_MINUTES
    )
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
        regime_state=state,
        volatility_state=_volatility_state(atr_ratio, prev_atr_ratio),
        trend_direction=effective_direction,
        local_swing_direction=local_direction,
        prior_trend_direction=prev_trend_direction,
        pullback_active=pullback_active,
        transition_age_minutes=(
            round(transition_age_minutes, 2)
            if transition_age_minutes is not None
            else None
        ),
        transition_expired=transition_expired,
        current_price=round(float(current_price), price_digits),
        prev_regime_hint=prev_regime,
        prev_regime_state=prev_regime_state,
        regime_transition=transition,
    )


def snapshot_regime(
    symbol: str,
    current_price: float,
    levels: dict[str, float],
    prev_regime: str | None = None,
    prev_atr_ratio: float | None = None,
    prev_regime_state: str | None = None,
    prev_trend_direction: str | None = None,
    transition_started_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build a loggable regime packet from cached bars. Never raises."""
    from market_context_cache import get_cached_completed_bars

    m1_bars = get_cached_completed_bars(symbol, "M1", 120)
    m5_bars = get_cached_completed_bars(symbol, "M5", 96)
    m15_bars = get_cached_completed_bars(symbol, "M15", 96)
    atr = snapshot_atr_from_cache(m1_bars, symbol) if m1_bars else {}
    m5_candle = m5_bars[-1] if m5_bars else None
    observation_time = _bar_close_time(m1_bars[-1] if m1_bars else None)
    transition_started = _parse_utc(transition_started_at_utc)
    transition_age_minutes = None
    if observation_time is not None and transition_started is not None:
        transition_age_minutes = max(
            0.0,
            (observation_time - transition_started).total_seconds() / 60.0,
        )
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
        prev_regime_state=prev_regime_state,
        prev_trend_direction=prev_trend_direction,
        transition_age_minutes=transition_age_minutes,
        price_digits=instrument_for(symbol).digits,
    )
    packet = ctx.to_dict()
    packet["observation_time_utc"] = (
        observation_time.isoformat().replace("+00:00", "Z")
        if observation_time is not None
        else None
    )
    packet["atr_ok"] = bool(atr.get("ok"))
    packet["atr_error"] = atr.get("error")
    packet["atr_source"] = atr.get("source")
    packet["m1_bars"] = len(m1_bars)
    packet["m5_bars"] = len(m5_bars)
    return packet


def update_regime_memory(
    memory: dict[str, float | str | None],
    context: dict,
) -> None:
    """Persist classifier continuity while preserving a reversal's anchor.

    An opposite M5 sequence can appear before the required structural
    displacement.  While state remains ``reversal_attempt``, keep the prior
    trend direction so another cycle cannot relabel that unconfirmed sequence
    as an ordinary trend merely because memory forgot what is being reversed.
    """
    memory["hint"] = context.get("regime_hint")
    memory["atr_ratio"] = context.get("atr_ratio_3_51")
    memory["state"] = context.get("regime_state")
    memory["pullback_active"] = bool(context.get("pullback_active"))
    state = context.get("regime_state")
    transition_active = bool(context.get("pullback_active")) or state in TRANSITION_STATES
    if transition_active:
        if not memory.get("transition_started_at_utc"):
            memory["transition_started_at_utc"] = context.get("observation_time_utc")
    else:
        memory["transition_started_at_utc"] = None
    current_direction = context.get("trend_direction")
    if (
        current_direction in {"buy", "sell"}
        and context.get("regime_state") != "reversal_attempt"
    ):
        memory["trend_direction"] = current_direction


def _parse_utc(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _bar_close_time(row: dict | None) -> datetime | None:
    if not isinstance(row, dict):
        return None
    for key in ("close_time_utc", "event_time_utc", "time_utc", "time"):
        value = row.get(key)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                continue
        parsed = _parse_utc(value)
        if parsed is not None:
            return parsed
    return None


def suggested_target_mode(hint: str | None) -> str | None:
    """Python suggestion for entry target_mode. Qwen may override."""
    return {
        "range": "scalp",
        "exhaustion": "scalp",
        "trend": "scalp",
        "breakout": "scalp",
    }.get(str(hint or "").strip().lower())
