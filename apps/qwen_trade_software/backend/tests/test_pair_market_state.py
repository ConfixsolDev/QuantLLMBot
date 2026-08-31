from __future__ import annotations

import pytest

from pair_market_state import SCHEMA_VERSION, build_pair_market_state


def test_state_is_versioned_and_replayable_without_mutable_aliases():
    source = [{"event_time_utc": "2026-08-31T08:00:00Z", "kind": "swing"}]
    state = build_pair_market_state(
        "XAUUSDr", "2026-08-31T08:05:00Z", structural_events=source,
        versions={"structure_engine_version": "shadow-v1"},
    )
    source[0]["kind"] = "changed-after-build"

    assert state.as_dict()["schema_version"] == SCHEMA_VERSION
    assert state.as_dict()["structural_events"][0]["kind"] == "swing"
    with pytest.raises(TypeError):
        state.data_quality["unsafe"] = True


def test_future_evidence_is_rejected_at_the_frontier():
    with pytest.raises(ValueError, match="future evidence"):
        build_pair_market_state(
            "XAUUSDr", "2026-08-31T08:00:00Z",
            structure=[{"observed_at": "2026-08-31T08:00:01Z"}],
        )


def test_state_does_not_invent_or_select_a_direction():
    state = build_pair_market_state("XAUUSDr", "2026-08-31T08:00:00Z")
    payload = state.as_dict()
    assert payload["zones"] == []
    assert payload["structure"] == []
    assert "direction" not in payload
    assert "execution" not in payload
