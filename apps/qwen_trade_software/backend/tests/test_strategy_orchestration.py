from __future__ import annotations

import pytest

from llm_arbitration import validate_response
from strategy_scheduler import EvaluationSchedule, cadence
from strategy_statistics import summarize
from test_strategy_contract import candidate


def test_strategy_statistics_are_scoped_and_non_predictive():
    stats = summarize("XAUUSD_SCALP_V1", [{"r": 1, "mfe_r": 2, "mae_r": 0.5}, {"r": -1, "mfe_r": 0.3, "mae_r": 1.2}])
    assert stats.sample_size == 2
    assert stats.expected_r == 0
    assert stats.as_dict()["strategy_id"] == "XAUUSD_SCALP_V1"


def test_scheduler_prioritizes_state_change_then_trigger():
    schedule = EvaluationSchedule("XAUUSD_SCALP_V1", 300, 60, 5)
    assert cadence(schedule, near_actionable_zone=True, trigger_pending=True, state_changed=True)["reason"] == "state_changed"
    assert cadence(schedule, near_actionable_zone=True, trigger_pending=True, state_changed=False)["reason"] == "critical_entry"


def test_llm_can_only_approve_supplied_candidate():
    c = candidate()
    result = validate_response({"decision": "APPROVE", "candidate_id": c.candidate_id, "state_hash": c.state_hash, "reason": "candidate evidence is coherent"}, c)
    assert result.decision == "APPROVE"
    with pytest.raises(ValueError, match="must cite"):
        validate_response({"decision": "APPROVE", "candidate_id": "invented", "reason": "x"}, c)
