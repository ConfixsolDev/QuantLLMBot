"""Operator-mapped H4/M15 shelves stay in the entry ladder."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_context_cache import MAPPED_TRADE_LEVELS_PATH  # noqa: E402
from reviewer import _execution_level_ladder  # noqa: E402


def test_mapped_trade_levels_file_has_chart_marks():
    payload = json.loads(MAPPED_TRADE_LEVELS_PATH.read_text(encoding="utf-8"))
    ids = {row["level_id"] for row in payload["levels"]}
    assert "M15_MAPPED_4369" in ids
    assert "M15_MAPPED_4364" in ids
    assert "M15_MAPPED_4354" in ids
    assert "H4_MAPPED_4382" in ids
    assert "H4_MAPPED_4376" in ids


def test_execution_ladder_pins_mapped_levels():
    decision = {
        "M1": [
            {
                "id": "M1_PREVIOUS_HIGH",
                "price": 4371.0,
                "zone_high": 4371.0,
                "role": "previous_high",
            }
        ],
        "M15": [
            {
                "id": "M15_MAPPED_4354",
                "price": 4354.964,
                "zone_high": 4354.964,
                "role": "mapped_important",
            },
            {
                "id": "M15_MAPPED_4369",
                "price": 4369.276,
                "zone_high": 4369.276,
                "role": "mapped_important",
            },
        ],
        "H4": [
            {
                "id": "H4_MAPPED_4382",
                "price": 4382.0,
                "zone_high": 4383.848,
                "role": "mapped_important",
            }
        ],
    }
    ladder = _execution_level_ladder(decision, mid_price=4370.0, each_side=1)
    ids = {row["id"] for row in ladder}
    assert "M15_MAPPED_4354" in ids
    assert "M15_MAPPED_4369" in ids
    assert "H4_MAPPED_4382" in ids
