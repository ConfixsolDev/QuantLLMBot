from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_structure_shadow import build_summary, native_decision, realised_direction  # noqa: E402


def test_native_decision_freezes_htf_before_m5_fallback():
    assert native_decision({"htf_bias": "bullish", "trends": {"M5": "bearish"}}) == "bullish"
    assert native_decision({"htf_bias": "mixed", "trends": {"M5": "bearish"}}) == "bearish"


def test_realised_direction_uses_preregistered_atr_deadband():
    assert realised_direction(100, 100.3, 2.0) == "bullish"
    assert realised_direction(100, 99.7, 2.0) == "bearish"
    assert realised_direction(100, 100.1, 2.0) == "mixed"


def test_summary_compares_native_consensus_and_individual_providers():
    resolutions = [{
        "sample_id": "one", "realised_direction": "bullish",
        "native_direction": "bullish", "external_direction": "bearish",
        "provider_directions": {"scipy_peaks": "bullish"},
    }]
    summary = build_summary([{"sample_id": "one"}], resolutions)
    assert summary["actors"]["native"]["accuracy"] == 1.0
    assert summary["actors"]["external_consensus"]["accuracy"] == 0.0
    assert summary["actors"]["scipy_peaks"]["accuracy"] == 1.0
    assert summary["execution_authority"] is False
