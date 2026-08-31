from vnext.strategy.xau_m15_m1_structure_scalper import DEFINITION, SPEC, candidate_inputs


def test_first_strategy_has_independent_identity_and_excludes_m5():
    assert DEFINITION.strategy_id == "XAU_M15_M1_STRUCTURE_SCALPER_50PT_V1"
    assert DEFINITION.magic_number == 3101
    assert DEFINITION.execution_comment == "QVN:XAU:M15M1:50"
    assert SPEC.narrator_request["explicitly_exclude"] == ("M5",)


def test_first_strategy_fails_closed_without_complete_shared_episode_evidence():
    assert candidate_inputs({"zones": [], "structural_events": []}) is None


def test_first_strategy_rejects_m5_evidence():
    evidence = {"strategy_id": DEFINITION.strategy_id, "timeframes_used": "M5"}
    assert candidate_inputs({"strategy_evidence": evidence}) is None
