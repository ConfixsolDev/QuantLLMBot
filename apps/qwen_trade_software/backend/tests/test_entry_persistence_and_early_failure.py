from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paper_executor as pe  # noqa: E402
import reviewer  # noqa: E402
import trade_manager as tm  # noqa: E402


def _tick_msc(stamp: str) -> int:
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def test_next_m1_first_15_seconds_must_persist_in_trade_direction():
    trigger = {
        "evidence_id": "candle:XAUUSDr:M1:10:00",
        "close_time_utc": "2026-08-27T10:01:00Z",
    }
    forming = {"open": 4500.0, "open_time_utc": "2026-08-27T10:01:00Z"}
    state = {}
    ready, reason = pe.m1_persistence_ready(
        "buy", 4500.2, 0.05, _tick_msc("2026-08-27T10:01:15Z"),
        trigger, forming, state, atr_m1_51=2.0,
    )
    assert ready is True
    assert reason == "m1_persistence_passed"


def test_failed_second_15_sample_cannot_recover_inside_same_m1():
    trigger = {
        "evidence_id": "candle:XAUUSDr:M1:10:00",
        "close_time_utc": "2026-08-27T10:01:00Z",
    }
    forming = {"open": 4500.0, "open_time_utc": "2026-08-27T10:01:00Z"}
    state = {}
    ready, _ = pe.m1_persistence_ready(
        "sell", 4500.1, 0.05, _tick_msc("2026-08-27T10:01:15Z"),
        trigger, forming, state, atr_m1_51=2.0,
    )
    assert ready is False
    recovered, reason = pe.m1_persistence_ready(
        "sell", 4499.0, 0.05, _tick_msc("2026-08-27T10:01:30Z"),
        trigger, forming, state, atr_m1_51=2.0,
    )
    assert recovered is False
    assert reason == "m1_persistence_failed_waiting_close"


def test_failed_sample_can_rearm_only_after_that_candle_closes_valid():
    old_trigger = {
        "evidence_id": "candle:XAUUSDr:M1:10:00",
        "open_time_utc": "2026-08-27T10:00:00Z",
        "close_time_utc": "2026-08-27T10:01:00Z",
    }
    failed_bar = {"open": 4500.0, "open_time_utc": "2026-08-27T10:01:00Z"}
    state = {}
    pe.m1_persistence_ready(
        "sell", 4500.1, 0.05, _tick_msc("2026-08-27T10:01:15Z"),
        old_trigger, failed_bar, state, atr_m1_51=2.0,
    )
    revalidated_trigger = {
        "evidence_id": "candle:XAUUSDr:M1:10:01",
        "open_time_utc": "2026-08-27T10:01:00Z",
        "close_time_utc": "2026-08-27T10:02:00Z",
    }
    next_bar = {"open": 4499.8, "open_time_utc": "2026-08-27T10:02:00Z"}
    ready, reason = pe.m1_persistence_ready(
        "sell", 4499.8, 0.05, _tick_msc("2026-08-27T10:02:00Z"),
        revalidated_trigger, next_bar, state, atr_m1_51=2.0,
    )
    assert ready is True
    assert reason == "m1_persistence_revalidated_on_close"


def test_direction_context_preserves_both_structural_responses_for_qwen():
    facts = {
        "regime_context": {
            "regime_state": "breakout_confirmed",
            "regime_hint": "breakout",
            "trend_direction": "buy",
        },
        "entry_geometry_menu": [
            {"geometry_row_id": "G1", "side": "sell"},
            {"geometry_row_id": "G2", "side": "buy"},
        ],
    }
    contract = reviewer.apply_entry_direction_contract(facts)
    assert contract["authoritative_side"] is None
    assert contract["parent_auction_side"] == "buy"
    assert [row["geometry_row_id"] for row in facts["entry_geometry_menu"]] == ["G1", "G2"]


def test_trending_range_keeps_parent_direction_as_context_only():
    facts = {
        "regime_context": {
            "regime_state": "trending_range", "trend_direction": "buy",
        },
        "entry_geometry_menu": [
            {"geometry_row_id": "G1", "side": "sell"},
            {"geometry_row_id": "G2", "side": "buy"},
        ],
    }

    contract = reviewer.apply_entry_direction_contract(facts)

    assert contract["authoritative_side"] is None
    assert contract["parent_auction_side"] == "buy"
    assert [row["geometry_row_id"] for row in facts["entry_geometry_menu"]] == ["G1", "G2"]


def test_post_qwen_breakout_level_response_is_not_directionally_overridden():
    facts = {
        "regime_context": {
            "regime_state": "breakout_confirmed",
            "regime_hint": "breakout",
            "trend_direction": "buy",
        }
    }
    review = {
        "execution_plan": {
            "status": "ready",
            "side": "sell",
            "optimal_entry_price": 4500.0,
        }
    }
    reviewer._stamp_regime_target_mode(review, facts)
    assert review["execution_plan"]["status"] == "ready"
    assert review["execution_plan"]["side"] == "sell"


def test_post_qwen_trending_range_level_response_is_not_directionally_overridden():
    facts = {
        "regime_context": {
            "regime_state": "trending_range",
            "regime_hint": "range",
            "trend_direction": "buy",
        }
    }
    review = {
        "execution_plan": {
            "status": "ready", "side": "sell", "optimal_entry_price": 4500.0,
        }
    }

    reviewer._stamp_regime_target_mode(review, facts)

    assert review["execution_plan"]["status"] == "ready"
    assert review["execution_plan"]["side"] == "sell"


def _early_facts(candle: dict) -> dict:
    return {
        "latest_completed_m1": candle["evidence_id"],
        "latest_completed_m5": None,
        "completed_candles": [candle],
        "position": {
            "side": "buy",
            "entry": 4500.0,
            "opened_at": "2026-08-27T10:00:20+00:00",
        },
        "level_references": {
            "entry_failure_boundary": {"level_id": "ENTRY_PRICE", "price": 4500.0},
        },
        "trade_path": {"reached_favorable_level_refs": []},
    }


def test_research_detector_identifies_first_opposite_m1_close_through_entry():
    candle = {
        "evidence_id": "candle:M1:10:01",
        "timeframe": "M1",
        "closed_at_utc": "2026-08-27T10:01:00+00:00",
        "open": 4500.2,
        "high": 4500.3,
        "low": 4499.4,
        "close": 4499.6,
        "direction": "down",
    }
    facts = _early_facts(candle)
    decision = tm.early_entry_failure_guard(facts)
    assert decision is not None
    parsed, failures = tm.validate_management_decision(decision, facts)
    assert failures == []
    assert parsed["action"] == "close"


def test_research_early_failure_detector_has_no_live_safety_authority():
    candle = {
        "evidence_id": "candle:M1:10:01",
        "timeframe": "M1",
        "closed_at_utc": "2026-08-27T10:01:00+00:00",
        "open": 4500.2,
        "high": 4500.3,
        "low": 4499.4,
        "close": 4499.6,
        "direction": "down",
    }
    assert tm.early_entry_failure_guard(_early_facts(candle)) is not None
    assert tm.safety_guard(_early_facts(candle)) is None


def test_fifteen_second_persistence_is_not_a_live_entry_gate():
    assert pe.M1_PERSISTENCE_ENFORCED is False


def test_opposite_candle_that_holds_entry_is_not_an_early_failure():
    candle = {
        "evidence_id": "candle:M1:10:01",
        "timeframe": "M1",
        "closed_at_utc": "2026-08-27T10:01:00+00:00",
        "open": 4500.4,
        "high": 4500.5,
        "low": 4500.05,
        "close": 4500.1,
        "direction": "down",
    }
    assert tm.early_entry_failure_guard(_early_facts(candle)) is None


def test_later_opposite_m1_is_left_to_normal_management():
    candle = {
        "evidence_id": "candle:M1:10:02",
        "timeframe": "M1",
        "closed_at_utc": "2026-08-27T10:02:00+00:00",
        "open": 4500.2,
        "high": 4500.3,
        "low": 4499.0,
        "close": 4499.2,
        "direction": "down",
    }
    assert tm.early_entry_failure_guard(_early_facts(candle)) is None
