"""Phase 3: M1 entry gate, regime target_mode, qualified levels."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live_mapped_levels as lml  # noqa: E402
from paper_executor import pre_fill_zone_cancellation  # noqa: E402
import paper_executor as pe  # noqa: E402
import qualified_levels as ql  # noqa: E402
import regime_engine as re  # noqa: E402
import reviewer  # noqa: E402


def test_m1_failure_for_buy_support():
    zone_fail = {"open": 101.2, "high": 101.4, "low": 99.8, "close": 100.4}
    zone_through = {"open": 100.2, "high": 100.4, "low": 99.1, "close": 99.4}
    assert lml.m1_failure_for_entry("buy", 100, 102, zone_fail)
    assert not lml.m1_failure_for_entry("buy", 100, 102, zone_through)


def test_suggested_target_mode_by_regime():
    assert re.suggested_target_mode("range") == "scalp"
    assert re.suggested_target_mode("breakout") == "starter_basket"
    assert re.suggested_target_mode("unknown") is None


def test_stamp_regime_fills_missing_target_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(ql, "QUALIFIED_LEVELS_PATH", tmp_path / "qualified-levels.json")
    review = {
        "execution_plan": {
            "status": "ready",
            "side": "sell",
            "entry_low_id": "M5_PREVIOUS_HIGH",
            "entry_high_id": "M15_PREVIOUS_HIGH",
            "stop_level_id": "M15_PREVIOUS_HIGH",
            "target_level_id": "M5_PREVIOUS_LOW",
        }
    }
    facts = {
        "regime_context": {"regime_hint": "range"},
        "suggested_target_mode": "scalp",
    }
    reviewer._stamp_regime_target_mode(review, facts)
    assert review["execution_plan"]["target_mode"] == "scalp"
    assert review["execution_plan"]["suggested_target_mode"] == "scalp"
    assert "M5_PREVIOUS_HIGH" in ql.load_qualified_level_ids()


def test_stamp_keeps_qwen_target_mode(monkeypatch, tmp_path):
    monkeypatch.setattr(ql, "QUALIFIED_LEVELS_PATH", tmp_path / "qualified-levels.json")
    review = {
        "execution_plan": {
            "status": "ready",
            "target_mode": "directional_basket",
            "entry_low_id": "H1_PREVIOUS_LOW",
        }
    }
    reviewer._stamp_regime_target_mode(
        review,
        {"regime_context": {"regime_hint": "trend"}, "suggested_target_mode": "starter_basket"},
    )
    assert review["execution_plan"]["target_mode"] == "directional_basket"


def test_range_without_bounds_keeps_mapped_zone_ready(monkeypatch, tmp_path):
    """Regression for the missed 02:41 close / 02:42 double-top scalp."""
    monkeypatch.setattr(ql, "QUALIFIED_LEVELS_PATH", tmp_path / "qualified-levels.json")
    review = {
        "execution_plan": {
            "status": "ready",
            "side": "sell",
            "entry_low": 4491.489,
            "entry_high": 4492.853,
            "optimal_entry_price": 4492.853,
            "entry_low_id": "M1_PREVIOUS_LOW",
            "entry_high_id": "M1_PREVIOUS_HIGH",
            "target_mode": "scalp",
        }
    }
    facts = {
        "regime_context": {
            "regime_hint": "range",
            "regime_state": "range",
            "range_detected": False,
            "range_support": None,
            "range_resistance": None,
            "current_price": 4490.961,
        }
    }
    reviewer._stamp_regime_target_mode(review, facts)
    assert review["execution_plan"]["status"] == "ready"
    assert review["execution_plan"]["range_edge_check"] == "unavailable"


def test_entry_fill_ready_waits_without_m1_failure():
    ready, gate = pe.entry_fill_ready(
        "sell", 101, 100, 102, 105,
        {"open": 100.5, "high": 102.4, "low": 100.4, "close": 102.3},
    )
    assert not ready
    assert gate == "inside_zone_waiting_m1_failure"


def test_zone_wait_survives_time_but_cancels_on_structure_not_clock():
    rejection = {"open": 101.5, "high": 102.4, "low": 100.8, "close": 101.4}
    assert pre_fill_zone_cancellation("sell", 101.5, 100, 102, 104, 95, rejection) is None
    accepted = {"open": 101.5, "high": 103.0, "low": 101.0, "close": 102.5}
    assert pre_fill_zone_cancellation("sell", 102.2, 100, 102, 104, 95, accepted) == (
        "zone_accepted_through_on_m1"
    )


def test_zone_wait_cancels_if_invalidation_or_target_already_traded():
    assert pre_fill_zone_cancellation("sell", 104, 100, 102, 104, 95, None) == (
        "zone_invalidated_at_stop"
    )
    assert pre_fill_zone_cancellation("sell", 95, 100, 102, 104, 95, None) == (
        "target_reached_without_fill"
    )


def test_levels_for_ui_marks_qualified(monkeypatch, tmp_path):
    path = tmp_path / "qualified-levels.json"
    monkeypatch.setattr(ql, "QUALIFIED_LEVELS_PATH", path)
    ql.remember_qualified_level_ids(["M5_PREVIOUS_LOW"])
    import trade_management as tm

    monkeypatch.setattr(tm, "historical_respect_counts", lambda *a, **k: {})
    grouped = tm.levels_for_ui(
        {"M5_PREVIOUS_LOW": 4393.0, "H1_PREVIOUS_HIGH": 4404.0},
        symbol=None,
    )
    by_id = {row["id"]: row for rows in grouped.values() for row in rows}
    assert by_id["M5_PREVIOUS_LOW"]["qualified"] is True
    assert by_id["H1_PREVIOUS_HIGH"]["display"] == "candidate"
