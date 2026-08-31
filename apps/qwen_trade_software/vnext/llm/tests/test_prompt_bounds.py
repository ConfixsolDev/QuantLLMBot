from vnext.llm.client import build_arbitration_prompt
from vnext.market.state import PairMarketState
from vnext.platform.time_frontier import TimeFrontier
from vnext.strategy.contracts import StrategyDefinition, TradeCandidate


def test_arbitration_prompt_is_bounded():
    state = PairMarketState("XAUUSD", TimeFrontier.from_value("2026-01-01T00:00:00Z").as_of_utc, {},
                            {"M1": [{"i": i} for i in range(100)]},
                            structural_events=tuple({"i": i} for i in range(100)))
    definition = StrategyDefinition("XAUUSD", "S1", "1", 1, "SCALP")
    candidate = TradeCandidate("c1", "XAUUSD", definition, "buy", "reclaim", "z1", "low", ("z2",),
                               "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00", state.state_hash)
    import json
    packet = json.loads(build_arbitration_prompt(state, candidate, {}))
    assert len(packet["state"]["timeframes"]["M1"]) == 32
    assert len(packet["state"]["structural_events"]) == 16
