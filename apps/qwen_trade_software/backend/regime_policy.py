"""Brooks-derived execution policy for each market regime.

The policy changes opportunity selection and trade shape, never the account's
maximum cash risk. A smaller structural stop may produce more units, but the
risk budget remains capped.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


BASE_RISK_BUDGET = 150.0


@dataclass(frozen=True)
class RegimePolicy:
    allow_new_entry: bool
    risk_multiplier: float
    signal_ttl_seconds: int
    target_mode: str | None
    edge_only: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


POLICIES = {
    "trend_strong": RegimePolicy(True, 1.00, 45, "starter_basket"),
    "trend_channel": RegimePolicy(True, 0.90, 60, "starter_basket"),
    "trending_range": RegimePolicy(True, 0.75, 45, "scalp", True),
    "range": RegimePolicy(True, 0.75, 30, "scalp", True),
    "tight_range": RegimePolicy(False, 0.00, 20, None, reason="tight_range_no_edge"),
    "breakout_attempt": RegimePolicy(False, 0.00, 20, None, reason="await_breakout_follow_through"),
    "breakout_confirmed": RegimePolicy(True, 0.80, 30, "starter_basket"),
    "reversal_attempt": RegimePolicy(False, 0.00, 30, None, reason="await_reversal_confirmation"),
    "reversal_confirmed": RegimePolicy(True, 0.75, 45, "scalp"),
    "climax_exhaustion": RegimePolicy(False, 0.00, 20, None, reason="do_not_chase_climax"),
    "unknown": RegimePolicy(False, 0.00, 20, None, reason="regime_unknown"),
}


def policy_for(regime_state: str | None) -> RegimePolicy:
    return POLICIES.get(str(regime_state or "unknown").lower(), POLICIES["unknown"])


def range_entry_allowed(side: str | None, entry_price: float | None, regime: dict) -> bool:
    """Permit range trades only in the outer 30%, directed back into balance."""
    try:
        support = float(regime["range_support"])
        resistance = float(regime["range_resistance"])
        entry = float(entry_price)
    except (KeyError, TypeError, ValueError):
        return False
    if resistance <= support:
        return False
    position = (entry - support) / (resistance - support)
    return (side == "buy" and position <= 0.30) or (side == "sell" and position >= 0.70)


def execution_settings(regime_state: str | None) -> dict:
    policy = policy_for(regime_state)
    result = policy.to_dict()
    result["risk_budget"] = round(BASE_RISK_BUDGET * policy.risk_multiplier, 2)
    return result
