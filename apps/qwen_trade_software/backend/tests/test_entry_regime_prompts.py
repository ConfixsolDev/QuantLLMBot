"""Entry prompt routing stays deterministic and modular by regime family."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from entry_regime_prompts import (  # noqa: E402
    effective_regime_context,
    prompt_route_facts,
    route_entry_regime,
)


def test_trend_states_share_only_the_trend_module():
    for state in ("trend_strong", "trend_channel", "breakout_confirmed"):
        route = route_entry_regime({"regime_state": state})
        assert route.family == "trend"
        assert route.section == "qwen_entry_trend"
        assert route.allow_entry is True


def test_range_transition_uses_reduced_response_scalp_without_a_fourth_prompt():
    route = route_entry_regime({"regime_state": "breakout_attempt"})
    assert route.family == "range"
    assert route.mode == "breakout_response_scalp"
    assert route.allow_entry is True


def test_reversal_attempt_and_confirmation_share_one_module():
    attempt = route_entry_regime({"regime_state": "reversal_attempt"})
    confirmed = route_entry_regime({"regime_state": "reversal_confirmed"})
    assert attempt.section == confirmed.section == "qwen_entry_reversal"
    assert attempt.allow_entry is True
    assert confirmed.allow_entry is True


def test_unknown_state_fails_closed_but_keeps_schema_compatible():
    facts = prompt_route_facts({"regime_state": "new_unmapped_state"})
    assert facts["family"] == "trend"
    assert facts["allow_entry"] is False
    assert facts["mode"] == "unknown_wait"


def test_closed_m5_m15_breakout_is_promoted_before_prompt_routing():
    facts = {
        "regime_context": {
            "regime_state": "breakout_attempt",
            "current_price": 111.0,
            "range_resistance": 110.0,
            "range_support": 100.0,
        },
        "confirmation_context": {
            "m5": {"bos": {"direction": "bullish", "broken": 110.0}},
            "m15": {"bos": {"direction": "bullish", "broken": 110.0}},
        },
    }
    regime = effective_regime_context(facts)
    route = route_entry_regime(regime)
    assert regime["regime_state"] == "breakout_confirmed"
    assert regime["trend_direction"] == "buy"
    assert route.section == "qwen_entry_trend"


def test_one_timeframe_breakout_stays_range_watch():
    facts = {
        "regime_context": {
            "regime_state": "breakout_attempt",
            "current_price": 111.0,
            "range_resistance": 110.0,
        },
        "confirmation_context": {
            "m5": {"bos": {"direction": "bullish", "broken": 110.0}},
            "m15": {},
        },
    }
    regime = effective_regime_context(facts)
    assert regime["regime_state"] == "breakout_attempt"
    assert route_entry_regime(regime).mode == "breakout_response_scalp"
