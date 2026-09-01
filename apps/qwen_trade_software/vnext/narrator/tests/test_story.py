from vnext.market.state import PairMarketState
from vnext.narrator.story import NarratorRequest, StoryNarrator


def test_narrator_only_reports_supplied_facts():
    state = PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {"ok": True}, {"M1": {"close": 10}}, structure={"state": "trend", "direction": "buy"}, zones=({"zone_id": "z1"},))
    request = NarratorRequest("XAUUSD", ("M1",), (), ())
    result = StoryNarrator().narrate(state, request)
    assert result["facts"]["zones"] == [{"zone_id": "z1"}]
    assert result["authority"] == "facts_only_no_signal_generation"


def test_narrator_rejects_cross_pair_state():
    state = PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {}, {})
    request = NarratorRequest("DXY", (), (), ())
    try:
        StoryNarrator().narrate(state, request)
    except ValueError:
        return
    raise AssertionError("cross-pair narration must be rejected")


def test_narrator_applies_strategy_bounds_to_story_facts():
    state = PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {},
                            {"M1": [{"i": index} for index in range(5)], "M5": [{"i": index} for index in range(5)]},
                            zones=tuple({"zone_id": str(index)} for index in range(5)),
                            structural_events=tuple({"event_id": str(index)} for index in range(5)))
    result = StoryNarrator().narrate(state, NarratorRequest("XAUUSD", ("M1",), (), (),
                                                            max_bars_per_timeframe=2,
                                                            max_structure_events=3, max_zones=2))
    assert result["facts"]["timeframes"] == {"M1": [{"i": 3}, {"i": 4}]}
    assert "M5" not in result["facts"]["timeframes"]
    assert len(result["facts"]["structural_events"]) == 3
    assert len(result["facts"]["zones"]) == 2
