from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from instrument_config import InstrumentConfig, XAUUSD, instrument_for  # noqa: E402
import market_structure  # noqa: E402
from market_runtime import MarketRuntimeRegistry  # noqa: E402
import reviewer  # noqa: E402
import runtime_config  # noqa: E402
import trade_geometry  # noqa: E402


def _config(key: str, symbol: str, scale: float) -> InstrumentConfig:
    return InstrumentConfig(
        key=key,
        broker_symbol=symbol,
        digits=5,
        point_size=scale / 100,
        fvg_min_width=scale,
        ote_min_impulse=scale * 10,
        equal_level_tolerance=scale * 2,
        sweep_overshoot_max=scale * 4,
        order_block_touch_tolerance=scale / 2,
        displacement_min_body=scale * 3,
        mapped_level_max_distance=scale * 50,
    )


def test_gold_aliases_resolve_to_one_instrument_profile():
    assert instrument_for("XAUUSD") is XAUUSD
    assert instrument_for("XAUUSDr") is XAUUSD
    assert instrument_for("GOLD") is XAUUSD


def test_market_engines_are_isolated_by_instrument():
    market_structure.reset()
    a = market_structure.engine_for("AAA", config=_config("AAA", "AAAr", 0.1))
    b = market_structure.engine_for("BBB", config=_config("BBB", "BBBr", 0.001))
    assert a is not b
    assert a.tracker is not b.tracker
    assert a.fvg_detector is not b.fvg_detector
    assert a.fvg_detector.min_width == 0.1
    assert b.fvg_detector.min_width == 0.001
    assert a.ote_calculator.min_impulse_points == 1.0
    assert b.ote_calculator.min_impulse_points == 0.01


def test_reset_one_instrument_does_not_reset_another():
    market_structure.reset()
    a = market_structure.engine_for("AAA", config=_config("AAA", "AAAr", 0.1))
    b = market_structure.engine_for("BBB", config=_config("BBB", "BBBr", 0.01))
    market_structure.reset("AAA")
    a2 = market_structure.engine_for("AAA", config=_config("AAA", "AAAr", 0.1))
    assert a2 is not a
    assert market_structure.engine_for(
        "BBB", config=_config("BBB", "BBBr", 0.01)
    ) is b


def test_entry_prompt_has_generic_and_instrument_specific_portions():
    prompt = reviewer.build_entry_prompt({"symbol": "XAUUSDr"})
    assert "GENERIC MARKET ANALYSIS CONTRACT:" in prompt
    assert "REGIME-SPECIFIC PLAYBOOK [TREND qwen_entry_trend:1.2]" in prompt
    assert "INSTRUMENT-SPECIFIC CONTRACT:" in prompt
    assert "The supplied instrument is XAUUSD" in prompt
    assert prompt.index("GENERIC MARKET ANALYSIS CONTRACT:") < prompt.index(
        "REGIME-SPECIFIC PLAYBOOK"
    ) < prompt.index(
        "INSTRUMENT-SPECIFIC CONTRACT:"
    )


def test_entry_prompt_routes_each_regime_to_only_its_own_playbook():
    cases = {
        "trend_channel": ("TREND", "Trend playbook"),
        "range": ("RANGE", "Range playbook"),
        "reversal_confirmed": ("REVERSAL", "Reversal playbook"),
    }
    for state, (family, marker) in cases.items():
        prompt = reviewer.build_entry_prompt({
            "symbol": "XAUUSDr",
            "regime_context": {"regime_state": state},
        })
        assert f"REGIME-SPECIFIC PLAYBOOK [{family} " in prompt
        assert marker in prompt
        other_markers = {
            "Trend playbook", "Range playbook", "Reversal playbook"
        } - {marker}
        assert not any(other in prompt for other in other_markers)


def test_unknown_instrument_gets_generic_overlay_without_gold_assumptions():
    prompt = reviewer.build_entry_prompt({"symbol": "EURUSDr"})
    specific = prompt.split("INSTRUMENT-SPECIFIC CONTRACT:", 1)[1].split(
        "ENTRY FACTS:", 1
    )[0]
    assert "EURUSDR" in specific
    assert "Gold remains authoritative" not in specific


def test_runtime_registry_isolates_lifecycle_approach_and_regime():
    registry = MarketRuntimeRegistry()
    gold = registry.get("XAUUSDr")
    other = registry.get("EURUSDr")
    gold.idea_manager.create_idea("GOLD_ZONE", "buy", 100, 101, "gold")
    gold.regime_memory["hint"] = "trend"
    assert other.idea_manager.has_active is False
    assert other.regime_memory["hint"] is None
    assert gold.approach_tracker is not other.approach_tracker


def test_runtime_registry_migrates_legacy_single_market_state():
    source = MarketRuntimeRegistry()
    gold = source.get("XAUUSDr")
    gold.idea_manager.create_idea("LEGACY", "buy", 100, 101, "legacy")
    legacy = {
        "idea_manager": gold.idea_manager.to_state(),
        "approach_tracker": gold.approach_tracker.to_state(),
    }
    restored = MarketRuntimeRegistry.from_state(legacy)
    assert restored.get("XAUUSD").idea_manager.active_idea.zone_id == "LEGACY"


def test_runtime_registry_roundtrip_keeps_markets_separate():
    source = MarketRuntimeRegistry()
    source.get("XAUUSDr").regime_memory["hint"] = "trend"
    source.get("XAUUSDr").regime_memory["state"] = "trend_channel"
    source.get("XAUUSDr").regime_memory["trend_direction"] = "buy"
    source.get("XAUUSDr").regime_memory["transition_started_at_utc"] = (
        "2026-08-25T01:00:00Z"
    )
    source.get("XAUUSDr").regime_memory["pullback_active"] = True
    source.get("EURUSDr").regime_memory["hint"] = "range"
    restored = MarketRuntimeRegistry.from_state(source.to_state())
    assert restored.get("XAUUSD").regime_memory["hint"] == "trend"
    assert restored.get("XAUUSD").regime_memory["state"] == "trend_channel"
    assert restored.get("XAUUSD").regime_memory["trend_direction"] == "buy"
    assert restored.get("XAUUSD").regime_memory["transition_started_at_utc"] == (
        "2026-08-25T01:00:00Z"
    )
    assert restored.get("XAUUSD").regime_memory["pullback_active"] is True
    assert restored.get("EURUSDr").regime_memory["hint"] == "range"


def test_dashboard_regime_prefers_live_context_and_exposes_family():
    runtime = MarketRuntimeRegistry().get("XAUUSDr")
    runtime.regime_memory.update({
        "state": "trend_channel", "hint": "trend", "trend_direction": "buy"
    })
    result = reviewer.dashboard_regime_context(
        {
            "regime_context": {
                "regime_state": "reversal_attempt",
                "regime_hint": "range",
                "trend_direction": None,
                "volatility_state": "high",
                "regime_transition": True,
                "pullback_active": False,
                "transition_age_minutes": 7.0,
            }
        },
        {"qwen": {"execution_plan": {"regime_state": "range"}}},
        runtime,
    )
    assert result == {
        "regime_state": "reversal_attempt",
        "regime_hint": "range",
        "regime_family": "reversal",
        "trend_direction": None,
        "volatility_state": "high",
        "regime_transition": True,
        "pullback_active": False,
        "transition_age_minutes": 7.0,
        "source": "live_management",
    }


def test_dashboard_regime_falls_back_to_latest_entry_decision():
    runtime = MarketRuntimeRegistry().get("XAUUSDr")
    runtime.regime_memory["trend_direction"] = "sell"
    result = reviewer.dashboard_regime_context(
        {},
        {
            "qwen": {
                "execution_plan": {
                    "regime_state": "trending_range",
                    "regime_hint": "range",
                    "volatility_state": "normal",
                }
            }
        },
        runtime,
    )
    assert result["regime_state"] == "trending_range"
    assert result["regime_family"] == "range"
    assert result["source"] == "latest_entry_decision"


def test_only_explicitly_authorized_instruments_can_trade():
    assert instrument_for("XAUUSDr").trade_enabled is True
    generic = instrument_for("EURUSDr")
    assert generic.trade_enabled is False
    assert generic.context_only is True


def test_generic_contract_value_changes_risk_sizing():
    gold_size = trade_geometry.size_for_risk(3.0, 150.0, 100.0)
    other_size = trade_geometry.size_for_risk(3.0, 150.0, 10.0)
    assert other_size > gold_size


def test_qwen_models_are_selected_by_independent_roles():
    roles = runtime_config.ModelRoles(
        entry="entry-v1", management="manager-v2",
        planner="planner-v3", context="context-v4",
    )
    assert len({roles.entry, roles.management, roles.planner, roles.context}) == 4
    assert runtime_config.model_for_role("entry") == runtime_config.MODEL_ROLES.entry


def test_provider_shadow_publishes_closed_bar_without_execution_authority(tmp_path, monkeypatch):
    bars = []
    close = 100.0
    for index in range(20):
        close += 1.0 if index % 2 == 0 else -0.4
        bars.append({
            "time": index,
            "open": close - 0.2, "high": close + 0.5,
            "low": close - 0.5, "close": close,
        })
    monkeypatch.setattr("market_structure_shadow.LOG_DIR", tmp_path)
    shadow = market_structure._publish_shadow_input(
        "XAUUSDr", {"M5": bars},
        {"htf_bias": "bullish", "trends": {"M5": "bearish"}, "alignment": "mixed"},
    )
    assert shadow["status"] == "published"
    assert shadow["native_direction"] == "bullish"
    assert shadow["execution_authority"] is False
