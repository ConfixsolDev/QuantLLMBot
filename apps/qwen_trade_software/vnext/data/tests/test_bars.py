from datetime import datetime, timezone, timedelta

import pytest

from vnext.data.bars import Bar, TimeframeBuilder
from vnext.market.state import PairMarketState
from vnext.platform.time_frontier import TimeFrontier


def m1(index: int, close: float = 10.0) -> Bar:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index)
    return Bar("XAUUSD", "M1", start, start + timedelta(minutes=1), close, close + 1, close - 1, close, 2)


def test_builder_requires_all_children_and_tracks_slots():
    frontier = TimeFrontier.from_value("2026-01-01T00:05:00Z")
    built = TimeframeBuilder("XAUUSD", frontier=frontier).build([m1(i) for i in range(5)], "M5")
    assert len(built) == 1
    assert built[0].child_slots == (1, 2, 3, 4, 5)
    assert built[0].child_count == 5


def test_builder_skips_partial_or_future_bucket():
    frontier = TimeFrontier.from_value("2026-01-01T00:05:00Z")
    assert TimeframeBuilder("XAUUSD", frontier=frontier).build([m1(i) for i in range(4)], "M5") == []
    assert TimeframeBuilder("XAUUSD", frontier=frontier).build([m1(0)], "M5") == []


def test_pair_state_hash_is_stable():
    state = PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {"ok": True}, {"M1": {"close": 10}})
    assert state.state_hash == PairMarketState("XAUUSD", "2026-01-01T00:05:00Z", {"ok": True}, {"M1": {"close": 10}}).state_hash
