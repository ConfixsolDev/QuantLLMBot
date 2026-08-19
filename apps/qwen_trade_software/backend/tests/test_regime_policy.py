from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from regime_policy import execution_settings, range_entry_allowed  # noqa: E402


def test_range_is_faster_but_never_higher_cash_risk():
    trend = execution_settings("trend_strong")
    range_settings = execution_settings("range")
    assert range_settings["signal_ttl_seconds"] < trend["signal_ttl_seconds"]
    assert range_settings["risk_budget"] <= trend["risk_budget"]
    assert range_settings["target_mode"] == "scalp"


def test_range_entries_only_at_correct_outer_edge():
    regime = {"range_support": 100.0, "range_resistance": 110.0}
    assert range_entry_allowed("buy", 102.0, regime)
    assert range_entry_allowed("sell", 108.0, regime)
    assert not range_entry_allowed("buy", 105.0, regime)
    assert not range_entry_allowed("sell", 102.0, regime)


def test_unconfirmed_transition_states_do_not_trade():
    assert not execution_settings("breakout_attempt")["allow_new_entry"]
    assert not execution_settings("reversal_attempt")["allow_new_entry"]
    assert not execution_settings("tight_range")["allow_new_entry"]
