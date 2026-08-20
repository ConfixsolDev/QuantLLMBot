from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_structure_providers import (  # noqa: E402
    CapabilityProvider, ProviderResult, StructureEvent, provider_inventory,
    run_shadow_providers,
)


class FakeProvider:
    package = "fake"
    offline_only = False

    def __init__(self, name: str, directions: list[str]):
        self.name, self.directions = name, directions

    def detect(self, bars, timeframe, atr):
        return ProviderResult(self.name, True, "ok", tuple(
            StructureEvent(self.name, "swing", direction, timeframe, i, 100 + i)
            for i, direction in enumerate(self.directions)
        ))


def test_shadow_consensus_is_pair_agnostic_and_non_authoritative():
    result = run_shadow_providers([], "M5", 2.0, (
        FakeProvider("a", ["bearish", "bearish"]),
        FakeProvider("b", ["bullish"]),
    ))
    assert result["mode"] == "shadow_only"
    assert result["direction"] == "bearish"
    assert result["agreement"] == 0.667
    assert result["status"] == "ok"
    assert result["provider_decisions"][0]["direction"] == "bearish"
    assert result["execution_authority"] is False


def test_offline_providers_never_run_in_live_shadow_path():
    offline = CapabilityProvider("zigzag", "definitely_missing", repaint_risk=True)
    result = run_shadow_providers([], "M1", 1.0, (offline,))
    assert result["event_count"] == 0
    assert result["providers_missing"] == []
    assert result["status"] == "no_providers_available"


def test_inventory_declares_no_execution_authority():
    inventory = provider_inventory()
    assert len(inventory) == 9
    assert all(row["execution_authority"] is False for row in inventory)
    assert any(row["offline_only"] for row in inventory)


def test_inventory_distinguishes_installed_distribution_from_importable_module():
    inventory = provider_inventory((
        CapabilityProvider("missing", "definitely_missing", distribution_name="definitely-missing"),
    ))
    assert inventory[0]["installed"] is False
    assert inventory[0]["importable"] is False
