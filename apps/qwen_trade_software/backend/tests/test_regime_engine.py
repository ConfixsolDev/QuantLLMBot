"""Regime engine: ATR + displacement + swings + range. Computation only."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import regime_engine as re  # noqa: E402


def _swing(kind: str, price: float, index: int) -> dict:
    return {"kind": kind, "price": price, "index": index}


def _mixed_range_swings() -> list[dict]:
    return [
        _swing("high", 4398.0, 0),
        _swing("low", 4392.8, 1),
        _swing("high", 4397.4, 2),
        _swing("low", 4393.2, 3),
        _swing("high", 4398.2, 4),
        _swing("low", 4392.9, 5),
    ]


def _hh_hl_swings() -> list[dict]:
    return [
        _swing("high", 4398.0, 0),
        _swing("low", 4392.0, 1),
        _swing("high", 4401.0, 2),
        _swing("low", 4394.0, 3),
        _swing("high", 4404.0, 4),
        _swing("low", 4397.0, 5),
    ]


def _lh_ll_swings() -> list[dict]:
    return [
        _swing("high", 4405.0, 0),
        _swing("low", 4400.0, 1),
        _swing("high", 4403.0, 2),
        _swing("low", 4397.0, 3),
        _swing("high", 4401.0, 4),
        _swing("low", 4394.0, 5),
    ]


def test_mapped_level_distance_filter():
    assert re.mapped_level_within_distance(4395.0, 4398.0)
    assert not re.mapped_level_within_distance(4349.0, 4398.0)
    assert re.mapped_level_within_distance(4349.0, None)


def test_range_hint_on_mixed_swings_inside_band():
    swings = _mixed_range_swings()
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=0.96,
        m5_candle={"open": 4395.0, "high": 4395.6, "low": 4394.4, "close": 4395.2},
        m5_swings=swings,
        m15_swings=swings,
        current_price=4395.0,
        levels={"M5_PREVIOUS_HIGH": 4398.0, "M5_PREVIOUS_LOW": 4392.8},
    )
    assert ctx.range_detected is True
    assert ctx.m5_swing_pattern == "mixed"
    assert ctx.regime_hint == "range"
    assert ctx.regime_state == "range"
    assert ctx.volatility_state == "low"


def test_trend_hint_on_hh_hl_with_expanding_atr():
    swings = _hh_hl_swings()
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.56,
        m5_candle={"open": 4396.0, "high": 4400.2, "low": 4395.8, "close": 4400.1},
        m5_swings=swings,
        m15_swings=swings,
        current_price=4400.0,
        levels={"M5_PREVIOUS_HIGH": 4398.0},
    )
    assert ctx.m5_swing_pattern == "hh_hl"
    assert ctx.regime_hint == "trend"
    assert ctx.regime_state == "trend_strong"


def test_breakout_when_compressed_then_displacement_through():
    swings = _hh_hl_swings()
    candle = {"open": 4396.0, "high": 4400.2, "low": 4395.8, "close": 4400.1}
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.56,
        m5_candle=candle,
        m5_swings=swings,
        m15_swings=swings,
        current_price=4400.0,
        levels={"M5_PREVIOUS_HIGH": 4398.0},
        prev_regime="range",
        prev_atr_ratio=0.7,
    )
    assert ctx.displacement_through is True
    assert ctx.regime_hint == "breakout"
    assert ctx.regime_state == "breakout_confirmed"
    assert ctx.regime_transition is True


def test_unknown_without_atr():
    ctx = re.compute_regime(
        atr_m1_51=None,
        atr_m1_3=None,
        m5_candle=None,
        m5_swings=[],
        m15_swings=[],
        current_price=4395.0,
        levels={},
    )
    assert ctx.regime_hint == "unknown"
    assert ctx.regime_state == "unknown"


def test_mixed_structure_after_trend_is_a_tradable_pullback():
    swings = _mixed_range_swings()
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.2,
        m5_candle={"open": 4395.0, "high": 4395.6, "low": 4394.4, "close": 4395.2},
        m5_swings=swings,
        m15_swings=_hh_hl_swings(),
        current_price=4395.0,
        levels={"M5_PREVIOUS_LOW": 4394.5},
        prev_regime="trend",
        prev_regime_state="trend_channel",
        prev_trend_direction="buy",
    )
    assert ctx.regime_state == "trend_channel"
    assert ctx.pullback_active is True
    assert ctx.trend_direction == "buy"
    assert ctx.local_swing_direction is None
    assert ctx.prior_trend_direction == "buy"


def test_unresolved_pullback_becomes_range_at_fifteen_minutes():
    swings = _mixed_range_swings()
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.2,
        m5_candle={"open": 4395.0, "high": 4395.6, "low": 4394.4, "close": 4395.2},
        m5_swings=swings,
        m15_swings=_hh_hl_swings(),
        current_price=4395.0,
        levels={"M5_PREVIOUS_LOW": 4394.5},
        prev_regime="trend",
        prev_regime_state="trend_channel",
        prev_trend_direction="buy",
        transition_age_minutes=15.0,
    )
    assert ctx.regime_state == "range"
    assert ctx.pullback_active is False
    assert ctx.transition_expired is True


def test_reversal_attempt_confirms_only_after_opposite_displacement():
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.32,
        m5_candle={"open": 4399.7, "high": 4400.0, "low": 4397.8, "close": 4398.0},
        m5_swings=_lh_ll_swings(),
        m15_swings=_mixed_range_swings(),
        current_price=4398.0,
        levels={"M5_BREAK_LEVEL": 4398.5},
        prev_regime="range",
        prev_atr_ratio=1.0,
        prev_regime_state="reversal_attempt",
        prev_trend_direction="buy",
    )
    assert ctx.displacement_through is True
    assert ctx.trend_direction == "sell"
    assert ctx.regime_state == "reversal_confirmed"


def test_opposite_pattern_without_structural_displacement_stays_attempt():
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.2,
        m5_candle={"open": 4399.0, "high": 4399.4, "low": 4398.5, "close": 4398.8},
        m5_swings=_lh_ll_swings(),
        m15_swings=_mixed_range_swings(),
        current_price=4398.8,
        levels={"M5_BREAK_LEVEL": 4398.7},
        prev_regime="range",
        prev_regime_state="reversal_attempt",
        prev_trend_direction="buy",
    )
    assert ctx.displacement_through is None
    assert ctx.regime_state == "reversal_attempt"


def test_sustained_opposite_structure_confirms_by_fifteen_minutes():
    ctx = re.compute_regime(
        atr_m1_51=1.2,
        atr_m1_3=1.2,
        m5_candle={"open": 4399.0, "high": 4399.4, "low": 4398.5, "close": 4398.8},
        m5_swings=_lh_ll_swings(),
        m15_swings=_mixed_range_swings(),
        current_price=4398.8,
        levels={"M5_BREAK_LEVEL": 4398.7},
        prev_regime="trend",
        prev_regime_state="reversal_attempt",
        prev_trend_direction="buy",
        transition_age_minutes=15.0,
    )
    assert ctx.regime_state == "reversal_confirmed"
    assert ctx.trend_direction == "sell"
    assert ctx.transition_expired is True


def test_reversal_attempt_memory_preserves_prior_trend_anchor():
    memory = {
        "hint": "range",
        "atr_ratio": 1.0,
        "state": "reversal_attempt",
        "trend_direction": "buy",
        "transition_started_at_utc": None,
    }
    re.update_regime_memory(memory, {
        "regime_hint": "trend",
        "atr_ratio_3_51": 1.0,
        "regime_state": "reversal_attempt",
        "trend_direction": "sell",
        "observation_time_utc": "2026-08-25T01:00:00Z",
    })
    assert memory["state"] == "reversal_attempt"
    assert memory["trend_direction"] == "buy"
    assert memory["transition_started_at_utc"] == "2026-08-25T01:00:00Z"

    re.update_regime_memory(memory, {
        "regime_hint": "trend",
        "atr_ratio_3_51": 1.1,
        "regime_state": "reversal_confirmed",
        "trend_direction": "sell",
        "observation_time_utc": "2026-08-25T01:15:00Z",
    })
    assert memory["trend_direction"] == "sell"
    assert memory["transition_started_at_utc"] is None
