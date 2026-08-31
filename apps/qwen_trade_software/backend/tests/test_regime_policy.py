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


def test_coarse_range_math_does_not_veto_a_mapped_level_response():
    regime = {"range_support": 100.0, "range_resistance": 110.0}
    for side, price in (("buy", 102.0), ("sell", 108.0), ("buy", 105.0), ("sell", 102.0)):
        assert range_entry_allowed(side, price, regime) is None


def test_range_hint_without_detected_boundaries_does_not_invent_middle():
    """A missing range cannot prove that an entry is at the wrong edge."""
    regime = {
        "regime_state": "range",
        "range_detected": False,
        "range_support": None,
        "range_resistance": None,
    }
    assert range_entry_allowed("sell", 4492.0, regime) is None


def test_every_recognized_regime_can_offer_a_reduced_risk_scalp():
    for state in (
        "trend_strong", "trend_channel", "trending_range", "range",
        "tight_range", "breakout_attempt", "breakout_confirmed",
        "reversal_attempt", "reversal_confirmed", "climax_exhaustion",
    ):
        settings = execution_settings(state)
        assert settings["allow_new_entry"] is True
        assert settings["target_mode"] == "scalp"
        assert 0 < settings["risk_budget"] <= execution_settings("trend_strong")["risk_budget"]
    assert not execution_settings("unknown")["allow_new_entry"]
