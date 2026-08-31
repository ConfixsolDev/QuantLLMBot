from strategy_contract import StrategyDefinition
from vnext.strategy.definition import StrategySpec, create_candidate
from vnext.strategy.statistics import summarize


def spec():
    return StrategySpec(StrategyDefinition("XAUUSD", "SCALP_V1", "1", 1001, "SCALP"),
                        trigger="M1_RECLAIM", invalidation_policy="zone_break", target_zone_policy="next_zone")


def test_candidate_is_expiring_and_strategy_scoped():
    candidate = create_candidate(spec(), candidate_id="c1", direction="buy", zone_id="z1", invalidation="z1_low", target_zone_ids=("z2",), state_hash="h", created_at_utc="2026-01-01T00:00:00Z")
    assert candidate.strategy.strategy_id == "SCALP_V1"
    assert candidate.expires_at_utc > candidate.created_at_utc


def test_statistics_shrink_small_samples_toward_prior():
    result = summarize("SCALP_V1", [{"r": 1.0}, {"r": -1.0}], prior_r=0.2, prior_weight=20)
    assert result.sample_size == 2
    assert result.shrunk_expected_r == 0.18181818181818182
    assert result.evidence_quality == "low"
