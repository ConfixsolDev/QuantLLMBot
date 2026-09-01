"""Strategy-owned evidence integration tests."""

from datetime import datetime, timedelta, timezone

from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine
from vnext.strategy.xau_m15_m1_structure_scalper import build_strategy_evidence, candidate_inputs


def _state() -> dict:
    return {
        "state_hash": "state-1", "timeframes": {"M1": [{"close": 100.0}]},
        "zones": [
            {"timeframe": "M15", "zone_id": "support", "lower": 99.0, "upper": 100.0,
            "lifecycle_state": "FRESH", "algorithm_version": "ZONE_V1",
             "created_at_utc": "2026-01-01T09:00:00+00:00"},
            {"timeframe": "M15", "zone_id": "resistance", "lower": 105.0, "upper": 106.0,
            "lifecycle_state": "FRESH", "algorithm_version": "ZONE_V1",
             "created_at_utc": "2026-01-01T09:00:00+00:00"},
            {"timeframe": "M1", "zone_id": "ignored-m1", "lower": 99.5, "upper": 100.5,
             "lifecycle_state": "FRESH"},
        ],
        "structural_events": [
            {"timeframe": "M1", "event_id": "high", "event_type": "SWING_HIGH_CONFIRMED",
             "observed_at_utc": "2026-01-01T10:01:00+00:00", "price": 105.5},
            {"timeframe": "M1", "event_id": "low", "event_type": "SWING_LOW_CONFIRMED",
             "observed_at_utc": "2026-01-01T10:02:00+00:00", "price": 99.5},
            {"timeframe": "M5", "event_id": "ignored-m5", "event_type": "SWING_HIGH_CONFIRMED",
             "observed_at_utc": "2026-01-01T10:03:00+00:00"},
        ],
        "temporal_state": {"entry_session": {"trade_permitted": True}},
    }


def test_strategy_selects_m15_level_and_m1_trigger_only():
    evidence = build_strategy_evidence(_state())
    assert evidence is not None
    assert evidence["level_id"] == "support"
    assert evidence["target_zone_id"] == "resistance"
    assert evidence["direction"] == "buy"
    assert evidence["timeframes_used"] == "M15,M1"


def test_strategy_evidence_creates_its_own_candidate_packet():
    candidate = candidate_inputs(_state())
    assert candidate is not None
    assert candidate["zone_id"] == "support"
    assert candidate["invalidation"] == "low"
    assert candidate["metadata"]["evidence_state_hash"] == "state-1"


def test_strategy_uses_approved_fixed_five_price_target_without_second_m15_zone():
    state = _state()
    state["zones"] = [state["zones"][0]]
    evidence = build_strategy_evidence(state)
    assert evidence is not None
    assert evidence["target_zone_id"] == "FIXED_TP_5_PRICE"
    assert evidence["target_space_points"] == 5.0


def test_common_state_composition_publishes_facts_not_strategy_evidence():
    start = datetime(2026, 8, 31, 10, tzinfo=timezone.utc)
    bars = [Bar("XAUUSDr", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i + 1),
                100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(50)]
    state = VNextEngine(pair="XAUUSDr", frontier=TimeFrontier.from_value(bars[-1].end_utc)).compose_state(bars)
    assert state.strategy_evidence == {}
    assert any(zone["timeframe"] == "M15" for zone in state.zones)
