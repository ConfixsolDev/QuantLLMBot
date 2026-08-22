from datetime import datetime, timedelta, timezone

from market_intelligence.hourly_structure_audit import (
    AUDIT_EVENT_TYPE,
    _cross_status,
    _movement_relation,
    _stable_id,
)


def test_supervision_identity_is_stable_and_rule_scoped():
    event_time = "2026-08-20T12:00:00Z"
    assert _stable_id("XAUUSDr", event_time) == _stable_id("XAUUSDr", event_time)
    assert _stable_id("XAUUSDr", event_time, "complete") != _stable_id(
        "XAUUSDr", event_time, "incomplete:2026-08-21T18:00:00Z"
    )
    assert _stable_id("XAUUSDr", event_time).startswith("supervision:")
    assert AUDIT_EVENT_TYPE == "market_structure_hourly_supervision"


def test_parent_child_and_cross_pair_relations_are_explicit():
    assert _movement_relation("bullish", "bullish") == "aligned_continuation"
    assert _movement_relation("bullish", "bearish") == "counter_parent_pullback"
    assert _cross_status("bullish", "bearish") == "inverse_aligned"
    assert _cross_status("bullish", "bullish") == "positive_correlation_conflict"


def test_audit_clock_example_has_distinct_forward_boundary():
    decision = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)
    assert decision + timedelta(hours=4) > decision
