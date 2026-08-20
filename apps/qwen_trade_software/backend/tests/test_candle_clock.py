from datetime import datetime, timezone

from candle_clock import candle_clock


def test_last_trade_clock_exposes_m15_and_h1_close_risk():
    clock = candle_clock(datetime(2026, 8, 20, 5, 58, 35, tzinfo=timezone.utc))
    assert clock["frames"]["M15"]["remaining_seconds"] == 85
    assert clock["frames"]["M30"]["remaining_seconds"] == 85
    assert clock["frames"]["H1"]["remaining_seconds"] == 85
    assert clock["frames"]["M15"]["phase"] == "closing_transition"
    assert clock["frames"]["H1"]["phase"] == "closing_transition"
    assert clock["frames"]["M30"]["phase"] == "closing_transition"
    assert clock["frames"]["H4"]["remaining_seconds"] == 7285
    assert clock["frames"]["H4"]["phase"] == "middle"


def test_management_clock_marks_rollover_since_entry():
    clock = candle_clock(
        datetime(2026, 8, 20, 6, 1, 0, tzinfo=timezone.utc),
        entry_time=datetime(2026, 8, 20, 5, 58, 35, tzinfo=timezone.utc),
    )
    assert clock["frames"]["M15"]["rolled_since_entry"] is True
    assert clock["frames"]["M30"]["rolled_since_entry"] is True
    assert clock["frames"]["H1"]["rolled_since_entry"] is True
    assert clock["frames"]["H4"]["rolled_since_entry"] is False
    assert clock["frames"]["H1"]["entry_seconds_before_close"] == 85


def test_clock_exposes_nested_boundary_frames_without_double_counting():
    clock = candle_clock(datetime(2026, 8, 20, 5, 58, 35, tzinfo=timezone.utc))
    assert clock["next_boundary_frames"] == ["M15", "M30", "H1"]
    assert clock["close_hierarchy"] == (
        "M15 builds M30; M30 builds H1; H1 builds H4"
    )
