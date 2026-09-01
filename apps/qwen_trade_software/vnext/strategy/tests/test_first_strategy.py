from datetime import datetime, timezone

from vnext.strategy.xau_m15_m1_structure_scalper import (
    DEFINITION, SPEC, candidate_inputs, entry_session_at,
)


def test_first_strategy_has_independent_identity_and_excludes_m5():
    assert DEFINITION.strategy_id == "XAU_M15_M1_STRUCTURE_SCALPER_50PT_V1"
    assert DEFINITION.magic_number == 3101
    assert DEFINITION.execution_comment == "QVN:XAU:M15M1:50"
    assert SPEC.narrator_request["explicitly_exclude"] == ("M5",)
    assert SPEC.model_contract["focus"]["execution_timeframes"] == ("M1",)
    assert SPEC.model_contract["focus"]["excluded_timeframes"] == ("M5",)


def test_first_strategy_fails_closed_without_complete_shared_episode_evidence():
    assert candidate_inputs({"zones": [], "structural_events": []}) is None


def test_first_strategy_rejects_m5_evidence():
    evidence = {"strategy_id": DEFINITION.strategy_id, "timeframes_used": "M5"}
    assert candidate_inputs({"strategy_evidence": evidence}) is None


def test_legacy_utc_entry_sessions_are_preserved_at_every_boundary():
    cases = ((0, "asia", True), (6, "asia", True), (7, "off_session", False),
             (8, "london", True), (12, "london", True), (13, "overlap", True),
             (15, "overlap", True), (16, "new_york", True),
             (20, "new_york", True), (21, "off_session", False),
             (23, "off_session", False))
    for hour, name, permitted in cases:
        session = entry_session_at(datetime(2026, 1, 5, hour, tzinfo=timezone.utc))
        assert session["session"] == name
        assert session["trade_permitted"] is permitted
