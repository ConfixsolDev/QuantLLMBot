from datetime import datetime, timezone

from entry_safety import temporal_protection_window


def utc(hour: int, minute: int, second: int) -> datetime:
    return datetime(2026, 8, 21, hour, minute, second, tzinfo=timezone.utc)


def test_m30_and_h1_final_ten_minutes_are_protected():
    window = temporal_protection_window(utc(1, 53, 0))
    assert window is not None
    assert window["frames"] == ["M30", "H1"]


def test_h4_final_fifteen_minutes_are_protected():
    window = temporal_protection_window(utc(3, 46, 0))
    assert window is not None
    assert "H4" in window["frames"]


def test_rollover_itself_starts_normal_new_candle_period():
    assert temporal_protection_window(utc(2, 0, 30)) is None


def test_normal_period_has_no_temporal_protection():
    assert temporal_protection_window(utc(1, 35, 0)) is None
