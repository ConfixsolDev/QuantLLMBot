from datetime import datetime, timezone

import pytest

from vnext.runtime.live_cycle import MT5ClosedBarSource


class FakeMT5:
    TIMEFRAME_M1 = 1
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 60
    TIMEFRAME_H4 = 240
    TIMEFRAME_D1 = 1440

    def copy_rates_from_pos(self, pair, timeframe, start, count):
        assert (pair, timeframe, start) == ("XAUUSD", 1, 1)
        return [{"time": datetime(2026, 1, 1, tzinfo=timezone.utc), "open": 1,
                 "high": 2, "low": 0.5, "close": 1.5, "tick_volume": 4}]

    def last_error(self):
        return (1, "failed")


def test_mt5_source_requests_completed_bars_only():
    rows = list(MT5ClosedBarSource(FakeMT5()).closed_m1("XAUUSD", 10))
    assert rows[0]["tick_volume"] == 4


def test_mt5_source_rejects_short_causal_window():
    with pytest.raises(ValueError):
        list(MT5ClosedBarSource(FakeMT5()).closed_m1("XAUUSD", 2))


def test_mt5_source_keeps_forming_bars_display_only(monkeypatch):
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)

    class FormingMT5(FakeMT5):
        def copy_rates_from_pos(self, pair, timeframe, start, count):
            if start == 1:
                return super().copy_rates_from_pos(pair, timeframe, start, count)
            seconds = {15: 900, 30: 1800, 60: 3600, 240: 14400, 1440: 86400}[timeframe]
            opened = int(now.timestamp()) // seconds * seconds
            return [{"time": opened, "open": 10, "high": 12, "low": 9,
                     "close": 11, "tick_volume": 4, "spread": 2}]

    rows = MT5ClosedBarSource(FormingMT5()).forming_timeframes("XAUUSD")
    assert [row["timeframe"] for row in rows] == ["D1", "H4", "H1", "M30", "M15"]
    assert all(row["is_forming"] and row["source"] == "mt5_display_only" for row in rows)
    assert "M1" not in {row["timeframe"] for row in rows}
