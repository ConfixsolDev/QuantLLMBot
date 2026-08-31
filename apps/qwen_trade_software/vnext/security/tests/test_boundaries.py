from vnext.llm.arbitrator import arbitrate
from vnext.market.state import PairMarketState
from vnext.narrator.story import NarratorRequest, StoryNarrator
from vnext.platform.time_frontier import TimeFrontier
from vnext.strategy.definition import StrategySpec, create_candidate
from vnext.strategy.contracts import StrategyDefinition


def candidate():
    spec = StrategySpec(StrategyDefinition("XAUUSD", "SCALP", "1", 1001, "SCALP"), trigger="reclaim", invalidation_policy="break", target_zone_policy="next")
    return create_candidate(spec, candidate_id="c1", direction="buy", zone_id="z1", invalidation="z1-low", target_zone_ids=("z2",), state_hash="known", created_at_utc="2026-01-01T00:00:00Z")


def test_tampered_state_hash_cannot_approve():
    result = arbitrate({"decision": "APPROVE", "candidate_id": "c1", "state_hash": "tampered"}, candidate())
    assert result.decision == "NO_TRADE"


def test_narrator_rejects_cross_pair_context():
    state = PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {}, {})
    try:
        StoryNarrator().narrate(state, NarratorRequest("DXY", (), (), ()))
    except ValueError:
        return
    raise AssertionError("cross-pair context must be rejected")


def test_frontier_rejects_future_event():
    assert not TimeFrontier.from_value("2026-01-01T00:00:00Z").permits("2026-01-01T00:00:01Z")
