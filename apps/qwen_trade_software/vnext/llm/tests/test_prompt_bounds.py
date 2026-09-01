from vnext.llm.client import build_arbitration_prompt
from vnext.market.state import PairMarketState
from vnext.narrator.story import NarratorRequest, StoryNarrator
from vnext.platform.time_frontier import TimeFrontier
from vnext.strategy.contracts import StrategyDefinition, TradeCandidate


def test_arbitration_prompt_is_bounded():
    state = PairMarketState("XAUUSD", TimeFrontier.from_value("2026-01-01T00:00:00Z").as_of_utc, {},
                            {"M1": [{"i": i} for i in range(100)]},
                            structural_events=tuple({"i": i} for i in range(100)))
    definition = StrategyDefinition("XAUUSD", "S1", "1", 1, "SCALP")
    candidate = TradeCandidate("c1", "XAUUSD", definition, "buy", "reclaim", "z1", "low", ("z2",),
                               "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00", state.state_hash,
                               metadata={"qwen_feedback": {"schema_version": "S1_QWEN_V1", "focus": {
                                   "context_timeframes": ("M1",), "setup_timeframes": (), "execution_timeframes": (),
                                   "excluded_timeframes": (), "focus_tags": ()}}})
    import json
    story = StoryNarrator().narrate(state, NarratorRequest("XAUUSD", ("M1",), (), (),
                                                            max_bars_per_timeframe=32,
                                                            max_structure_events=16))
    packet = json.loads(build_arbitration_prompt(state, candidate, story))
    assert len(packet["strategy_package"]["story"]["facts"]["timeframes"]["M1"]) == 32
    assert len(packet["strategy_package"]["story"]["facts"]["structural_events"]) == 16
    assert "state" not in packet
