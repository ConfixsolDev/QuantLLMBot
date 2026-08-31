from strategy_contract import StrategyDefinition
from vnext.llm.arbitrator import arbitrate
from vnext.strategy.definition import StrategySpec, create_candidate


def candidate():
    spec = StrategySpec(StrategyDefinition("XAUUSD", "SCALP_V1", "1", 1001, "SCALP"), trigger="reclaim", invalidation_policy="break", target_zone_policy="next")
    return create_candidate(spec, candidate_id="c1", direction="buy", zone_id="z1", invalidation="z1-low", target_zone_ids=("z2",), state_hash="hash", created_at_utc="2026-01-01T00:00:00Z")


def test_approve_must_cite_supplied_candidate():
    result = arbitrate({"decision": "APPROVE", "candidate_id": "other"}, candidate())
    assert result.decision == "NO_TRADE"
    assert "approve_must_cite_candidate" in result.violations


def test_valid_wait_is_preserved():
    result = arbitrate({"decision": "WAIT", "reason": "not triggered", "state_hash": "hash"}, candidate())
    assert result.decision == "WAIT"
