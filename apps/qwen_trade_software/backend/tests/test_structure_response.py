from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from structure_response import evaluate_nearby_responses, evaluate_zone_response  # noqa: E402


def test_missed_20260819_double_top_is_confirmed_sell_response():
    level = {
        "id": "H1_LIVE_H_4499_1400", "tf": "H1",
        "lo": 4498.867, "hi": 4498.867, "pattern": "first_test_high",
    }
    candle = {
        "id": "candle:XAUUSDr:M1:2026-08-19T16:16:00Z",
        "o": 4498.007, "h": 4499.392, "l": 4496.865, "c": 4497.674,
    }
    response = evaluate_zone_response(
        level, candle, atr=2.73764, point_size=0.001
    )
    assert response is not None
    assert response["state"] == "sweep_rejection"
    assert response["direction"] == "sell"
    assert response["confirmed"] is True


def test_same_normalized_zone_structure_works_on_fx_scale():
    level = {
        "id": "EURUSD_H1_LIVE_HIGH", "tf": "H1",
        "lo": 1.10000, "hi": 1.10020, "pattern": "mapped_high",
    }
    candle = {
        "id": "candle:EURUSD:M1:test",
        "open": 1.10010, "high": 1.10045, "low": 1.09970, "close": 1.09990,
    }
    response = evaluate_zone_response(
        level, candle, atr=0.00080, point_size=0.00001
    )
    assert response is not None
    assert response["state"] == "sweep_rejection"
    assert response["direction"] == "sell"
    assert 0 < response["probe_depth_atr"] < 1


def test_acceptance_is_not_mislabeled_as_rejection():
    level = {
        "id": "M15_PREVIOUS_HIGH", "tf": "M15",
        "lo": 100.0, "hi": 101.0, "role": "previous_high",
    }
    candle = {"open": 100.5, "high": 102.5, "low": 100.2, "close": 102.0}
    response = evaluate_zone_response(level, candle, atr=2.0, point_size=0.01)
    assert response is not None
    assert response["state"] == "acceptance"
    assert response["direction"] == "buy"
    assert response["confirmed"] is False


def test_nearby_responses_rank_rejection_before_acceptance():
    levels = [
        {"id": "LOW", "lo": 95, "hi": 96, "role": "previous_low"},
        {"id": "HIGH", "lo": 100, "hi": 101, "role": "previous_high"},
    ]
    candle = {"open": 100, "high": 102, "low": 95, "close": 100}
    rows = evaluate_nearby_responses(levels, candle, atr=5, point_size=0.01)
    assert rows[0]["level_id"] == "HIGH"
    assert rows[0]["state"] == "sweep_rejection"
