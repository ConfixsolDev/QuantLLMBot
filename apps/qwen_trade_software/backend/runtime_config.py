"""Single source of truth for live trading runtime identity.

Upgrade or roll back Qwen by changing ``DEFAULT_QWEN_MODEL`` here. Every live
worker imports ``ACTIVE_QWEN_MODEL``; ``QWEN_MODEL`` remains an intentional
deployment override for qualification and controlled comparisons.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Change this one constant when promoting the next trained model.
DEFAULT_QWEN_MODEL = "qwen-trading-v005:latest"
PRIMARY_MARKET_SYMBOL = os.environ.get("QWEN_PRIMARY_SYMBOL", "XAUUSDr")
NEO4J_ENABLED = os.environ.get("QWEN_NEO4J_ENABLED", "").strip().lower() in {
    "1", "true", "yes", "on"
}

# All processes resolve the override identically at startup.
ACTIVE_QWEN_MODEL = os.environ.get("QWEN_MODEL", DEFAULT_QWEN_MODEL)


@dataclass(frozen=True, slots=True)
class ModelRoles:
    entry: str
    management: str
    planner: str
    context: str


MODEL_ROLES = ModelRoles(
    entry=os.environ.get("QWEN_ENTRY_MODEL", ACTIVE_QWEN_MODEL),
    management=os.environ.get("QWEN_MANAGEMENT_MODEL", ACTIVE_QWEN_MODEL),
    planner=os.environ.get("QWEN_PLANNER_MODEL", ACTIVE_QWEN_MODEL),
    context=os.environ.get("QWEN_CONTEXT_MODEL", ACTIVE_QWEN_MODEL),
)


def model_for_role(role: str) -> str:
    try:
        return str(getattr(MODEL_ROLES, role))
    except AttributeError as exc:
        raise ValueError(f"unknown Qwen model role: {role}") from exc


def configured_models() -> tuple[str, ...]:
    """Unique models used by active roles, preserving role order."""
    return tuple(dict.fromkeys((
        MODEL_ROLES.entry,
        MODEL_ROLES.management,
        MODEL_ROLES.planner,
        MODEL_ROLES.context,
    )))
