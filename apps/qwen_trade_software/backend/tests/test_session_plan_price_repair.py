"""Invented M15 idea prices must not keep the planner in generating."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_planner import (  # noqa: E402
    apply_live_price_sanity,
    plan_needs_price_repair,
)


def test_m15_hallucination_is_stripped_not_regenerated():
    live = 4401.6
    plan = {
        "reference_price": live,
        "session_plan_id": "sp-20260818-asia",
        "bullish_scenario": {
            "trigger": "accept",
            "targets": [4415.0],
            "invalidation": 4388.0,
            "evidence": ["H4_1"],
        },
        "bearish_scenario": {
            "trigger": "reject",
            "targets": [4380.0],
            "invalidation": 4418.0,
            "evidence": ["H1_1"],
        },
        "key_levels": [{"price": 4400.0, "label": "pivot", "role": "two_sided"}],
        "trade_idea_m15": {
            "side": "sell",
            "pullback_zone": [261.5, 260.5],
            "invalidation": 262.5,
            "target": 259.5,
        },
        "price_sanity": {
            "ok": False,
            "failures": [
                "trade_idea_m15.pullback_lo:261.500 vs live:4401.665",
                "trade_idea_m15.pullback_hi:260.500 vs live:4401.665",
            ],
        },
        "tradeable": False,
    }
    assert plan_needs_price_repair(plan, live) is False
    sanity = apply_live_price_sanity(plan, live, source="test")
    assert sanity["ok"] is True
    assert plan["trade_idea_m15"] is None
    assert plan_needs_price_repair(plan, live) is False


def test_core_geometry_still_requests_repair():
    live = 4401.6
    plan = {
        "reference_price": live,
        "price_repair_attempts": 0,
        "bullish_scenario": {
            "trigger": "accept",
            "targets": [3550.0],
            "invalidation": 3530.0,
            "evidence": ["H4_1"],
        },
        "price_sanity": {
            "ok": False,
            "failures": ["bullish_scenario.targets[0]:3550.000 vs live:4401.600"],
        },
    }
    assert plan_needs_price_repair(plan, live) is True
    plan["price_repair_attempts"] = 1
    assert plan_needs_price_repair(plan, live) is False
