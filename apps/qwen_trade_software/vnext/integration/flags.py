"""Explicit opt-in activation flags; default behavior remains unchanged."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class ModularFlags:
    enabled: bool = False
    market_facts: bool = False
    strategy_lifecycle: bool = False
    execution_adapter: bool = False

    @classmethod
    def from_env(cls) -> "ModularFlags":
        enabled = _on("QWEN_VNEXT_MODULAR_ENABLED")
        return cls(
            enabled=enabled,
            market_facts=enabled and _on("QWEN_VNEXT_MARKET_FACTS"),
            strategy_lifecycle=enabled and _on("QWEN_VNEXT_STRATEGY_LIFECYCLE"),
            execution_adapter=enabled and _on("QWEN_VNEXT_EXECUTION_ADAPTER"),
        )

    def active(self) -> bool:
        return self.enabled and any((self.market_facts, self.strategy_lifecycle, self.execution_adapter))
