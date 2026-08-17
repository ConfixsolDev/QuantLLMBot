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
