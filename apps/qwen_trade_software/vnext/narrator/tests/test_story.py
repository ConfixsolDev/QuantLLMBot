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
