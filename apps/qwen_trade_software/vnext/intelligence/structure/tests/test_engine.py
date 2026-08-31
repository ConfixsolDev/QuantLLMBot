from datetime import datetime, timedelta, timezone

from vnext.data.bars import Bar
from vnext.intelligence.structure.engine import StructureEngine


def bar(i, o, h, l, c):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
    return Bar("XAUUSD", "M1", start, start + timedelta(minutes=1), o, h, l, c)


def test_swing_is_confirmed_only_after_later_reversal_bar():
    events = StructureEngine().detect_swings([bar(0, 10, 11, 9, 10), bar(1, 10, 15, 10, 14), bar(2, 14, 14, 8, 9)])
    assert len(events) == 1
    assert events[0].event_type == "SWING_HIGH_CONFIRMED"
    assert events[0].observed_at_utc > events[0].source_bar_start_utc


def test_event_identity_is_deterministic():
    rows = [bar(0, 10, 11, 9, 10), bar(1, 10, 15, 10, 14), bar(2, 14, 14, 8, 9)]
    assert StructureEngine().detect_swings(rows)[0].event_id == StructureEngine().detect_swings(rows)[0].event_id
