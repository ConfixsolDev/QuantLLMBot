from datetime import datetime, timezone

from entry_safety import candle_boundary_entry_block


def utc(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 8, 21, hour, minute, second, tzinfo=timezone.utc)


def test_blocks_first_loss_inside_pre_close_window():
    block = candle_boundary_entry_block(utc(1, 27, 26))
    assert block is not None
    assert block["reason"] == "candle_boundary_blackout"
    assert "M15" in block["frames"]
    assert "M30" in block["frames"]


def test_blocks_second_loss_six_seconds_before_m15_close():
    block = candle_boundary_entry_block(utc(1, 44, 54))
    assert block is not None
    assert "M15" in block["frames"]
    assert block["nearest_boundary_seconds"] == 6


def test_blocks_opening_minute_after_rollover():
    block = candle_boundary_entry_block(utc(2, 0, 30))
    assert block is not None
    assert block["frames"] == ["M15", "M30", "H1"]


def test_allows_entry_outside_boundary_window():
    assert candle_boundary_entry_block(utc(1, 35, 0)) is None


def test_exact_end_of_opening_window_is_allowed():
    assert candle_boundary_entry_block(utc(1, 31, 0)) is None
