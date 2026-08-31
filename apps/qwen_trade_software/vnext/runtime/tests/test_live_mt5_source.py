from datetime import datetime, timezone

import pytest

from vnext.runtime.live_cycle import MT5ClosedBarSource


class FakeMT5:
    TIMEFRAME_M1 = 1

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
