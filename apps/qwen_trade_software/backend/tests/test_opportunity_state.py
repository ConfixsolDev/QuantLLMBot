from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import opportunity_state as state  # noqa: E402


LEVELS = [
    {
        "level_id": "H1_PREVIOUS_LOW",
        "timeframe": "H1",
        "zone_low": 4598.0,
        "zone_high": 4600.0,
        "role": "support",
        "structure_proven": True,
        "evidence_ids": ["swing-low-1"],
    },
    {
        "level_id": "H1_PREVIOUS_LOW_DUPLICATE",
        "timeframe": "H1",
        "zone_low": 4599.0,
        "zone_high": 4601.0,
        "role": "support",
    },
    {
        "level_id": "H1_PREVIOUS_HIGH",
        "timeframe": "H1",
        "zone_low": 4610.0,
        "zone_high": 4612.0,
        "role": "resistance",
    },
]


def test_registry_is_bounded_and_collapses_overlapping_same_owner_zones():
    registry = state.build_active_zone_registry(LEVELS, live_price=4600.5)
    assert registry["execution_authority"] is False
    assert registry["raw_zone_count"] == 3
    assert registry["deduplicated_zone_count"] == 2
    assert registry["selected_zone_count"] == 2
    assert registry["zones"][0]["zone_id"] == "H1_PREVIOUS_LOW"
    assert registry["zones"][0]["structure_proven"] is True


def test_live_quote_can_locate_but_cannot_trigger_a_branch():
    packet = state.build_opportunity_shadow(
        LEVELS, live_price=4599.5, committed_side="buy",
    )
    assert packet["branches"]["buy"]["state"] == state.ARMED
    assert packet["shadow_triggered_side"] is None
    assert packet["decision"] == "wait"


def test_closed_proof_only_triggers_the_single_qwen_committed_side():
    proof = [{
        "side": "buy",
        "zone_id": "H1_PREVIOUS_LOW",
        "timeframe": "H1",
        "closed_candle": True,
        "status": "confirmed",
        "evidence_ids": ["candle:h1:100"],
    }]
    packet = state.build_opportunity_shadow(
        LEVELS,
        live_price=4599.5,
        committed_side="buy",
        closed_prices_by_timeframe={"H1": 4599.5},
        confirmations=proof,
    )
    assert packet["branches"]["buy"]["state"] == state.TRIGGERED
    assert packet["branches"]["sell"]["state"] != state.TRIGGERED
    assert packet["shadow_triggered_side"] == "buy"
    assert packet["execution_authority"] is False


def test_same_proof_cannot_originate_direction_without_qwen_commitment():
    proof = [{
        "side": "buy",
        "zone_id": "H1_PREVIOUS_LOW",
        "timeframe": "H1",
        "closed_candle": True,
        "status": "confirmed",
    }]
    packet = state.build_opportunity_shadow(
        LEVELS, live_price=4599.5, confirmations=proof,
    )
    assert packet["committed_side"] == "wait"
    assert packet["branches"]["buy"]["state"] == state.INSIDE_ZONE
    assert packet["decision"] == "wait"


def test_owner_timeframe_close_invalidates_but_live_wick_cannot():
    live_only = state.build_opportunity_shadow(
        LEVELS, live_price=4597.0, committed_side="buy",
    )
    assert live_only["branches"]["buy"]["state"] != state.INVALIDATED

    closed_break = state.build_opportunity_shadow(
        LEVELS,
        live_price=4597.0,
        committed_side="buy",
        closed_prices_by_timeframe={"H1": 4597.0},
    )
    assert closed_break["branches"]["buy"]["state"] == state.INVALIDATED


def test_m1_close_cannot_invalidate_an_h1_zone():
    packet = state.build_opportunity_shadow(
        LEVELS,
        live_price=4597.0,
        committed_side="buy",
        closed_prices_by_timeframe={"M1": 4597.0},
    )
    assert packet["branches"]["buy"]["state"] != state.INVALIDATED


def test_bidirectional_location_still_has_one_or_zero_committed_side():
    packet = state.build_opportunity_shadow(
        LEVELS, live_price=4605.0, committed_side="sell",
    )
    assert set(packet["branches"]) == {"buy", "sell"}
    assert packet["branches"]["buy"]["committed"] is False
    assert packet["branches"]["sell"]["committed"] is True
    assert packet["decision"] == "wait"


def test_qwen_commitment_is_read_not_invented_and_prefers_latest_layer():
    planner = {
        "trade_idea_stack": {
            "h4": {"side": "buy", "status": "active", "thesis": "H4 rejection"},
            "m15": {"side": "sell", "status": "active", "thesis": "M15 accepted below support"},
        }
    }
    assert state.qwen_committed_side(planner) == "sell"
    assert state.qwen_committed_side({"trade_idea_stack": {}}) is None


def test_placeholder_or_terminal_qwen_idea_does_not_become_commitment():
    placeholder = {"trade_idea_stack": {"h4": {"side": "buy", "thesis": "none"}}}
    terminal = {
        "trade_idea_stack": {
            "m15": {"side": "sell", "status": "invalidated", "thesis": "old break"},
        }
    }
    assert state.qwen_committed_side(placeholder) is None
    assert state.qwen_committed_side(terminal) is None
