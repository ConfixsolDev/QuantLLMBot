"""Shared two-layer prompt assembly for every market-facing AI role."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from instrument_config import InstrumentConfig, instrument_for


def instrument_knowledge(
    symbol: str,
    store_root: Path,
    section_loader: Callable[[str, Path], str],
) -> str:
    """Return doctrine that is valid only for the requested instrument.

    ``core_skill.md`` is presently the distilled Gold skill.  It must never be
    leaked into an unknown/new market merely because that market shares the
    same analysis engine.
    """
    profile = instrument_for(symbol)
    parts: list[str] = []
    if profile.key == "XAUUSD":
        parts.append((store_root / "core_skill.md").read_text(encoding="utf-8"))
    if profile.prompt_section:
        parts.append(section_loader(profile.prompt_section, store_root))
    return "\n\n".join(part.strip() for part in parts if part.strip())


def compose_market_prompt(
    *,
    generic_contract: str,
    symbol: str,
    facts_label: str,
    facts: Any,
    instrument_contract: str = "",
) -> str:
    """Build the invariant generic + instrument overlay prompt shape."""
    profile: InstrumentConfig = instrument_for(symbol)
    specific = instrument_contract.strip() or (
        f"No instrument doctrine is registered for {profile.key}. "
        "Use generic analysis only; do not infer Gold-specific price scales, "
        "session behavior, costs, or execution permission."
    )
    payload = json.dumps(facts, separators=(",", ":"), ensure_ascii=False)
    return (
        "GENERIC MARKET ROLE CONTRACT:\n"
        + generic_contract.strip()
        + "\n\nINSTRUMENT-SPECIFIC CONTRACT ["
        + profile.key
        + "]:\n"
        + specific
        + f"\n\n{facts_label}:\n"
        + payload
    )
