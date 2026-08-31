"""Adapter around the existing closed-candle regime implementation."""

from __future__ import annotations

from typing import Any

from regime_engine import compute_regime


def build_regime_facts(**inputs: Any) -> dict[str, Any]:
    """Build factual regime context while preserving Qwen decision authority."""
    result = compute_regime(**inputs)
    if hasattr(result, "as_dict"):
        return result.as_dict()
    if isinstance(result, dict):
        return dict(result)
    raise TypeError(f"unexpected regime result: {type(result).__name__}")
