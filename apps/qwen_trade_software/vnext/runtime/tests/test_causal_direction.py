from datetime import datetime, timedelta, timezone

from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine


def test_structure_direction_uses_confirmed_swing_not_last_body():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [Bar("XAUUSD", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i+1),
                 10, high, low, close, 1) for i, (high, low, close) in enumerate(
                     ((12, 9, 11), (14, 10, 13), (11, 8, 9)))]
    state = VNextEngine(pair="XAUUSD", frontier=TimeFrontier.from_value(start + timedelta(minutes=3))).compose_state(bars)
    assert state.structure["state"] == "confirmed_swing"
    assert state.structure["direction"] == "sell"
