"""Closed-candle CHoCH / BOS / FVG / sweep labels."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import confirmation_engine as ce  # noqa: E402


def _bar(o, h, l, c, eid=None):
    return {
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "evidence_id": eid,
    }


def test_bullish_fvg_unfilled():
    rows = [
        _bar(10, 11, 9.5, 10.5),
        _bar(10.6, 12, 10.4, 11.8),
        _bar(12.5, 13, 12.4, 12.8),
    ]
    fvgs = ce.detect_fvg(rows)
    assert len(fvgs) == 1
    assert fvgs[0]["side"] == "bullish"
    assert fvgs[0]["filled"] is False
    assert fvgs[0]["gap_low"] == 11.0
    assert fvgs[0]["gap_high"] == 12.4


def test_bearish_fvg_fills_when_later_bar_covers():
    rows = [
        _bar(13, 13.2, 12.0, 12.2),
        _bar(12.1, 12.3, 11.8, 11.9),
        _bar(11.0, 11.1, 10.5, 10.8),
        _bar(10.9, 12.5, 10.8, 12.2),
    ]
    fvgs = ce.detect_fvg(rows)
    assert fvgs == []


def test_liquidity_sweep_high_closes_back():
    swings = [{"kind": "high", "price": 100.0, "index": 0}]
    rows = [_bar(99.0, 101.2, 98.8, 99.4)]
    sweep = ce.detect_liquidity_sweep(rows, swings)
    assert sweep is not None
    assert sweep["kind"] == "sweep_high"
    assert sweep["level"] == 100.0


def test_bos_with_trend_hh_hl():
    swings = [
        {"kind": "high", "price": 10, "index": 0},
        {"kind": "low", "price": 5, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 7, "index": 3},
        {"kind": "high", "price": 14, "index": 4},
        {"kind": "low", "price": 8, "index": 5},
    ]
    rows = [_bar(13, 15.2, 12.8, 15.0)]
    event = ce.last_structure_event(rows, swings)
    assert event["swing_pattern"] == "hh_hl"
    assert event["bos"]["direction"] == "bullish"
    assert event["choch"] is None


def test_choch_against_hh_hl():
    swings = [
        {"kind": "high", "price": 10, "index": 0},
        {"kind": "low", "price": 5, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 7, "index": 3},
        {"kind": "high", "price": 14, "index": 4},
        {"kind": "low", "price": 8, "index": 5},
    ]
    rows = [_bar(9, 9.5, 7.2, 7.4)]
    event = ce.last_structure_event(rows, swings)
    assert event["choch"]["direction"] == "bearish"
    assert event["bos"] is None


def test_sweep_and_bos_are_exclusive_on_last_swing():
    swings = [
        {"kind": "high", "price": 10, "index": 0},
        {"kind": "low", "price": 5, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 7, "index": 3},
        {"kind": "high", "price": 14, "index": 4},
        {"kind": "low", "price": 8, "index": 5},
    ]
    sweep_bar = [_bar(13.2, 14.4, 12.9, 13.5)]
    bos_bar = [_bar(13.2, 15.1, 13.0, 14.8)]
    assert ce.detect_liquidity_sweep(sweep_bar, swings)["kind"] == "sweep_high"
    assert ce.last_structure_event(sweep_bar, swings)["bos"] is None
    assert ce.detect_liquidity_sweep(bos_bar, swings) is None
    assert ce.last_structure_event(bos_bar, swings)["bos"]["direction"] == "bullish"


def test_compact_confirmation_log():
    packet = {
        "m5": {
            "bos": None,
            "choch": {"direction": "bearish"},
            "liquidity_sweep": {"kind": "sweep_high"},
            "fvg": [{"side": "bearish"}],
        },
        "m15": {"bos": None, "choch": None, "liquidity_sweep": None, "fvg": []},
    }
    line = ce.compact_confirmation_log(packet)
    assert "m5_choch=bearish" in line
    assert "m5_sweep=sweep_high" in line
    assert "m5_fvg=1" in line
    assert ce.compact_confirmation_log({}) == "none"
