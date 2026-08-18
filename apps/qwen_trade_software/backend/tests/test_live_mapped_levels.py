"""Live mapped zones commit on closed M1; double tops need a second live test."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live_mapped_levels as lml  # noqa: E402


def _bar(i: int, open_: float, high: float, low: float, close: float, tf: str = "M1"):
    opened = datetime(2026, 8, 14, 1, 0, tzinfo=timezone.utc) + timedelta(minutes=i)
    closed = opened + timedelta(minutes=1 if tf == "M1" else 5)
    return {
        "evidence_id": f"candle:XAUUSDr:{tf}:{opened.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        "open_time_utc": opened.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "close_time_utc": closed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "tick_volume": 100,
    }


def _up_then_high(start: int, peak: float, base: float, count_before: int = 8):
    rows = []
    price = base
    for i in range(count_before):
        rows.append(_bar(start + i, price, price + 0.4, price - 0.3, price + 0.2))
        price += 0.2
    # peak bar
    rows.append(_bar(start + count_before, price, peak, price - 0.4, price - 0.2))
    # drop away from the zone
    price = peak - 2.0
    for i in range(1, 6):
        rows.append(
            _bar(
                start + count_before + i,
                price,
                price + 0.3,
                price - 0.8,
                price - 0.5,
            )
        )
        price -= 0.6
    return rows


def test_first_high_maps_only_after_closed_wing():
    rows = _up_then_high(0, 4323.4, 4318.0)
    # Last two closed bars are the wing; peak is confirmed.
    swings = lml.fractal_swings(rows, 2, "high")
    assert swings
    assert max(item["price"] for item in swings) == 4323.4
    # Truncate so the peak has no right wing: must not map.
    incomplete = rows[: rows.index(next(r for r in rows if r["high"] == 4323.4)) + 1]
    assert lml.fractal_swings(incomplete, 2, "high") == []


def test_leave_and_return_closed_m1_is_double_top():
    first = _up_then_high(0, 4323.4, 4318.0)
    # Return: climb back and print a second probe that fails to close above.
    t = len(first)
    return_rows = [
        _bar(t, 4318.0, 4319.0, 4317.5, 4318.8),
        _bar(t + 1, 4318.8, 4321.0, 4318.6, 4320.5),
        _bar(t + 2, 4320.5, 4323.5, 4320.2, 4322.1),  # probe, close back inside
    ]
    rows = first + return_rows
    closed_m1 = rows[-1]
    levels = lml.build_from_completed({"M1": rows}, closed_m1, 4322.1)
    highs = [row for row in levels if row["timeframe"] == "M1" and "H" in row["level_id"]]
    assert highs
    assert any(row["pattern"] == "double_top" for row in highs)
    assert any(row["test_count"] >= 2 for row in highs)


def test_nearby_prefers_live_map_not_last_bar():
    live = {
        "level_id": "M5_LIVE_H_4323_0110",
        "timeframe": "M5",
        "zone_low": 4322.8,
        "zone_high": 4323.5,
        "role": "mapped_important",
        "pattern": "double_top",
        "test_count": 2,
        "calculation_method": "live_closed_swing",
    }
    last_bar = {
        "level_id": "M1_PREVIOUS_HIGH",
        "timeframe": "M1",
        "zone_low": 4322.05,
        "zone_high": 4322.05,
        "role": "previous_high",
        "calculation_method": "latest_completed_candle",
    }
    stale = {
        "level_id": "M15_MAPPED_4369",
        "timeframe": "M15",
        "zone_low": 4369.276,
        "zone_high": 4369.276,
        "role": "mapped_important",
        "calculation_method": "operator_mapped",
    }
    nearby = lml.select_nearby([live, last_bar, stale], 4322.1, limit=3)
    ids = [row["level_id"] for row in nearby]
    assert "M5_LIVE_H_4323_0110" in ids
    assert ids[0] == "M5_LIVE_H_4323_0110"


def test_execution_ladder_pins_live_near_price_not_distant_shelf():
    from reviewer import _execution_level_ladder
    decision = {
        "M5": [
            {
                "id": "M5_LIVE_H_4323_0110",
                "price": 4322.8,
                "zone_high": 4323.5,
                "role": "mapped_important",
                "pattern": "double_top",
                "test_count": 2,
            }
        ],
        "M15": [
            {
                "id": "M15_MAPPED_4369",
                "price": 4369.276,
                "zone_high": 4369.276,
                "role": "mapped_important",
            }
        ],
        "M1": [
            {
                "id": "M1_PREVIOUS_LOW",
                "price": 4319.9,
                "zone_high": 4319.9,
                "role": "previous_low",
            }
        ],
    }
    ladder = _execution_level_ladder(decision, mid_price=4322.0, each_side=1)
    ids = {row["id"] for row in ladder}
    assert "M5_LIVE_H_4323_0110" in ids
    assert "M15_MAPPED_4369" not in ids


def test_compact_facts_expose_live_map_ids():
    from reviewer import compact_entry_facts
    entry_cache = {
        "validated_at_utc": "2026-08-14T01:47:00Z",
        "decision_time_utc": "2026-08-14T01:47:00Z",
        "epochs": {"structural": "s", "levels": "l", "session": "se", "playbooks": "p", "minute": "m"},
        "known_evidence_ids": ["M5_LIVE_H_4323_0110", "candle:XAUUSDr:M1:2026-08-14T01:46:00Z"],
        "levels": [
            {
                "level_id": "M5_LIVE_H_4323_0110",
                "timeframe": "M5",
                "zone_low": 4322.8,
                "zone_high": 4323.5,
                "role": "mapped_important",
                "pattern": "double_top",
                "test_count": 2,
            }
        ],
        "structure": {},
        "session": {"session": "asia", "trade_permitted": True},
        "playbooks": [],
        "recent_closed": {},
        "minute": {
            "quote": {"bid": 4322.1, "ask": 4322.2, "spread": 0.1, "age_ms": 0},
            "closed_m1": {
                "id": "candle:XAUUSDr:M1:2026-08-14T01:46:00Z",
                "open": 4320.5,
                "high": 4323.5,
                "low": 4320.2,
                "close": 4322.1,
                "tick_volume": 200,
            },
            "nearby_levels": [
                {
                    "id": "M5_LIVE_H_4323_0110",
                    "price": 4323.15,
                    "distance": 1.05,
                    "pattern": "double_top",
                    "test_count": 2,
                }
            ],
            "live_map": {
                "near": [
                    {
                        "id": "M5_LIVE_H_4323_0110",
                        "tf": "M5",
                        "lo": 4322.8,
                        "hi": 4323.5,
                        "tests": 2,
                        "pattern": "double_top",
                        "dist": 1.05,
                    }
                ],
                "double_top": {
                    "id": "M5_LIVE_H_4323_0110",
                    "tf": "M5",
                    "lo": 4322.8,
                    "hi": 4323.5,
                    "tests": 2,
                    "pattern": "double_top",
                    "dist": 1.05,
                },
                "double_bottom": None,
            },
        },
    }
    decision = {
        "M5": [
            {
                "id": "M5_LIVE_H_4323_0110",
                "price": 4322.8,
                "zone_high": 4323.5,
                "role": "mapped_important",
                "pattern": "double_top",
                "test_count": 2,
            }
        ]
    }
    facts = compact_entry_facts(entry_cache, decision, {}, "XAUUSDr")
    assert "confirmation_context" in facts
    assert facts["live_map"]["double_top"]["id"] == "M5_LIVE_H_4323_0110"
    assert "M5_LIVE_H_4323_0110" in {row["id"] for row in facts["execution_levels"]}
    assert "M5_LIVE_H_4323_0110" in facts["citeable_evidence_ids"]


def test_classify_swing_sequence_hh_hl_lh_ll_mixed():
    hh_hl = [
        {"kind": "high", "price": 10, "index": 0},
        {"kind": "low", "price": 5, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 7, "index": 3},
        {"kind": "high", "price": 14, "index": 4},
        {"kind": "low", "price": 8, "index": 5},
    ]
    assert lml.classify_swing_sequence(hh_hl) == "hh_hl"
    lh_ll = [
        {"kind": "high", "price": 14, "index": 0},
        {"kind": "low", "price": 8, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 6, "index": 3},
        {"kind": "high", "price": 11, "index": 4},
        {"kind": "low", "price": 5, "index": 5},
    ]
    assert lml.classify_swing_sequence(lh_ll) == "lh_ll"
    mixed = [
        {"kind": "high", "price": 14, "index": 0},
        {"kind": "low", "price": 5, "index": 1},
        {"kind": "high", "price": 12, "index": 2},
        {"kind": "low", "price": 8, "index": 3},
        {"kind": "high", "price": 13, "index": 4},
        {"kind": "low", "price": 6, "index": 5},
    ]
    assert lml.classify_swing_sequence(mixed) == "mixed"
    assert lml.classify_swing_sequence(hh_hl[:2]) == "insufficient"


if __name__ == "__main__":
    test_first_high_maps_only_after_closed_wing()
    test_leave_and_return_closed_m1_is_double_top()
    test_nearby_prefers_live_map_not_last_bar()
    print("live_mapped_levels unit tests passed")
