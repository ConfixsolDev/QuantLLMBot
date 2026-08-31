"""Deterministic routing for independently versioned entry playbooks.

The shared Qwen wire contract remains in ``prompt:qwen_cached_entry``.  This
module selects one small strategy overlay from Python's deterministic regime
state, so changing range doctrine cannot silently change trend or reversal
behaviour (or the response schema).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryRegimePrompt:
    family: str
    section: str
    version: str
    mode: str
    allow_entry: bool


_ROUTES = {
    "trend_strong": EntryRegimePrompt(
        "trend", "qwen_entry_trend", "1.2", "pullback", True
    ),
    "trend_channel": EntryRegimePrompt(
        "trend", "qwen_entry_trend", "1.2", "pullback", True
    ),
    "breakout_confirmed": EntryRegimePrompt(
        "trend", "qwen_entry_trend", "1.2", "breakout_pullback", True
    ),
    "range": EntryRegimePrompt(
        "range", "qwen_entry_range", "1.2", "outer_edge", True
    ),
    "trending_range": EntryRegimePrompt(
        "range", "qwen_entry_range", "1.2", "trending_range_edge", True
    ),
    "tight_range": EntryRegimePrompt(
        "range", "qwen_entry_range", "1.2", "tight_range_edge_scalp", True
    ),
    "breakout_attempt": EntryRegimePrompt(
        "range", "qwen_entry_range", "1.2", "breakout_response_scalp", True
    ),
    "reversal_attempt": EntryRegimePrompt(
        "reversal", "qwen_entry_reversal", "1.3", "attempt_response_scalp", True
    ),
    "reversal_confirmed": EntryRegimePrompt(
        "reversal", "qwen_entry_reversal", "1.3", "confirmed_entry", True
    ),
    "climax_exhaustion": EntryRegimePrompt(
        "reversal", "qwen_entry_reversal", "1.3", "exhaustion_response_scalp", True
    ),
}

_UNKNOWN = EntryRegimePrompt(
    "trend", "qwen_entry_trend", "1.2", "unknown_wait", False
)


def route_entry_regime(regime_context: dict | None) -> EntryRegimePrompt:
    """Return the contextual playbook matching the deterministic regime label."""
    context = regime_context if isinstance(regime_context, dict) else {}
    state = str(context.get("regime_state") or "unknown").strip().lower()
    return _ROUTES.get(state, _UNKNOWN)


def effective_regime_context(facts: dict | None) -> dict:
    """Return the deterministic entry-time regime, including closed BO proof.

    ``regime_engine`` supplies the normal M1-cycle classification.  Entry facts
    can additionally contain closed M5 and M15 structure confirming that an
    earlier range breakout attempt is now holding.  Resolve that promotion
    here so the prompt router and post-model policy consume the same state.
    """
    source = facts if isinstance(facts, dict) else {}
    regime = dict(source.get("regime_context") or {})
    state = str(regime.get("regime_state") or "unknown").lower()
    if state not in {"range", "trending_range", "breakout_attempt"}:
        return regime

    confirmation = source.get("confirmation_context") or {}

    def _event(frame: dict) -> dict:
        return frame.get("mss") or frame.get("choch") or frame.get("bos") or {}

    m5_event = _event(confirmation.get("m5") or {})
    m15_event = _event(confirmation.get("m15") or {})
    m5_direction = str(m5_event.get("direction") or m5_event.get("dir") or "").lower()
    m15_direction = str(m15_event.get("direction") or m15_event.get("dir") or "").lower()

    def _number(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    current_price = _number(regime.get("current_price"))
    resistance = _number(regime.get("range_resistance"))
    support = _number(regime.get("range_support"))
    bullish_boundary = max(
        _number(m5_event.get("broken")),
        _number(m15_event.get("broken")),
        resistance,
    )
    bearish_candidates = [
        value for value in (
            _number(m5_event.get("broken")),
            _number(m15_event.get("broken")),
            support,
        ) if value > 0
    ]
    bearish_boundary = min(bearish_candidates) if bearish_candidates else 0.0
    breakout_side = None
    if m5_direction == m15_direction == "bullish" and bullish_boundary:
        if current_price > bullish_boundary:
            breakout_side = "buy"
    elif m5_direction == m15_direction == "bearish" and bearish_boundary:
        if current_price < bearish_boundary:
            breakout_side = "sell"

    if breakout_side:
        regime["regime_state"] = "breakout_confirmed"
        regime["trend_direction"] = breakout_side
        regime["entry_promotion_reason"] = "m5_m15_closed_structure"
    return regime


def prompt_route_facts(regime_context: dict | None) -> dict:
    """Compact, non-directional route metadata supplied to Qwen and logs."""
    context = regime_context if isinstance(regime_context, dict) else {}
    route = route_entry_regime(context)
    return {
        "family": route.family,
        "state": str(context.get("regime_state") or "unknown").lower(),
        "mode": route.mode,
        "allow_entry": route.allow_entry,
        "direction_authority": "qwen_from_mapped_level_response",
        "playbook_version": f"{route.section}:{route.version}",
    }
