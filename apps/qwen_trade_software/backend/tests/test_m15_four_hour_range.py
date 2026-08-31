from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewer  # noqa: E402


def _bars(count: int = 16) -> list[dict]:
    rows = []
    for index in range(count):
        open_ = 100.0 + (index % 2)
        close = 101.0 if index % 2 == 0 else 100.0
        rows.append({
            "evidence_id": f"candle:M15:{index}",
            "open": open_,
            "high": 103.0 if index == 5 else max(open_, close) + 0.5,
            "low": 98.0 if index == 7 else min(open_, close) - 0.5,
            "close": close,
            "tick_volume": 100 + index,
        })
    return rows


def test_four_hour_range_uses_sixteen_completed_m15_bars():
    result = reviewer.m15_four_hour_range(_bars(), 102.0)
    assert result["status"] == "ready"
    assert result["execution_authority"] is False
    assert result["bars_used"] == 16
    assert result["outer_low"] == 98.0
    assert result["outer_high"] == 103.0
    assert result["midpoint"] == 100.5
    assert result["price_region"] == "upper_third"
    assert result["latest_closed_m15"]["id"] == "candle:M15:15"
    assert result["direction_changes"] >= 10


def test_four_hour_range_fails_neutrally_when_history_is_short():
    result = reviewer.m15_four_hour_range(_bars(15), 100.0)
    assert result == {
        "status": "insufficient_history",
        "execution_authority": False,
        "required_bars": 16,
        "available_bars": 15,
    }


def test_four_hour_range_does_not_mutate_or_select_a_side():
    rows = _bars()
    before = [dict(row) for row in rows]
    result = reviewer.m15_four_hour_range(rows, 99.0)
    assert rows == before
    assert "side" not in result
    assert "regime_state" not in result
