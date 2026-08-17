"""Displacement vs ATR on closed candles."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import displacement  # noqa: E402


def test_commitment_body_is_displacement():
    candle = {"open": 4396.0, "high": 4400.2, "low": 4395.8, "close": 4400.1}
    atr = 1.2
    disp = displacement.candle_displacement(candle, atr)
    assert disp["is_displacement"] is True
    assert disp["direction"] == "up"
    assert disp["body_pct"] > 0.65
    assert disp["body_atr_ratio"] > 0.8


def test_doji_is_not_displacement():
    candle = {"open": 4396.0, "high": 4398.0, "low": 4394.0, "close": 4396.1}
    disp = displacement.candle_displacement(candle, 1.2)
    assert disp["is_displacement"] is False


def test_displacement_through_level():
    candle = {"open": 4396.0, "high": 4400.2, "low": 4395.8, "close": 4400.1}
    hit = displacement.displacement_at_level(
        candle, {"M5_PREVIOUS_HIGH": 4398.0}, 1.2
    )
    assert hit is not None
    assert hit["through"] is True
    assert hit["level_id"] == "M5_PREVIOUS_HIGH"


def test_displacement_rejected_at_level():
    candle = {"open": 4394.2, "high": 4399.0, "low": 4394.1, "close": 4397.6}
    hit = displacement.displacement_at_level(
        candle, {"M5_PREVIOUS_HIGH": 4398.0}, 1.2
    )
    assert hit is not None
    assert hit["direction"] == "up"
    assert hit["through"] is False
