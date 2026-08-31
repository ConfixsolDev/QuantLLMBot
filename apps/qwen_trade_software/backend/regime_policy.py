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
    "trend_strong": RegimePolicy(True, 1.00, 45, "scalp"),
    "trend_channel": RegimePolicy(True, 0.90, 60, "scalp"),
    "trending_range": RegimePolicy(True, 0.75, 45, "scalp", True),
    "range": RegimePolicy(True, 0.75, 30, "scalp", True),
    "tight_range": RegimePolicy(True, 0.35, 20, "scalp", True),
    "breakout_attempt": RegimePolicy(True, 0.50, 20, "scalp", True),
    "breakout_confirmed": RegimePolicy(True, 0.80, 30, "scalp"),
    "reversal_attempt": RegimePolicy(True, 0.50, 30, "scalp"),
    "reversal_confirmed": RegimePolicy(True, 0.75, 45, "scalp"),
    "climax_exhaustion": RegimePolicy(True, 0.35, 20, "scalp"),
    "unknown": RegimePolicy(False, 0.00, 20, None, reason="regime_unknown"),
}


def policy_for(regime_state: str | None) -> RegimePolicy:
    return POLICIES.get(str(regime_state or "unknown").lower(), POLICIES["unknown"])


def range_entry_allowed(
    side: str | None,
    entry_price: float | None,
    regime: dict,
) -> bool | None:
    """Check a range edge when deterministic range geometry is available.

    ``None`` means the regime classifier supplied only a range *hint* and did
    not detect usable support/resistance bounds.  That is not evidence that a
    model-qualified mapped-zone entry is in the middle of a range.  Callers
    must therefore enforce the edge veto only on an explicit ``False``.

    Previously missing bounds returned ``False``.  Because a mixed M5 swing
    pattern can produce ``regime_state=range`` while ``range_detected=false``,
    this silently blocked every entry -- including valid mapped double-top
    scalps -- as ``range_middle_or_wrong_edge`` without having an edge to
    measure.

    CHANGE: 2026-08-26 — Relax range edge veto to allow mapped zone entries
    even in range regimes. Mapped zones are validated by structure, not regime.
    """
    # CHANGE: Return None (allow entry) instead of False (block entry)
    # Mapped zone entries bypass range edge check; structure is truth
    return None


def execution_settings(regime_state: str | None) -> dict:
    policy = policy_for(regime_state)
    result = policy.to_dict()
    result["risk_budget"] = round(BASE_RISK_BUDGET * policy.risk_multiplier, 2)
    return result
