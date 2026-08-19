"""Fast, deterministic MFE/ATR profit-protection policy.

Qwen supervises structure and may tighten a stop further.  This policy owns the
latency-sensitive minimum protection floor and can never widen broker risk.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict


ARM_R = 0.50
ARM_ATR = 1.00
TRAIL_ATR = 0.80
GIVEBACK_MFE = 0.45
COST_SPREADS = 3.0
SECURE_COSTS_R = 0.65
LOCK_1R = 0.30
LOCK_1_5R = 0.45


@dataclass(frozen=True)
class ProtectionDecision:
    state: str
    armed: bool
    should_modify: bool
    crossed: bool
    candidate_stop: float | None
    mfe: float
    current_move: float
    giveback: float
    initial_risk: float
    progress_r: float
    atr: float
    arm_distance: float
    trail_distance: float
    locked_move: float
    costs_buffer: float

    def record(self) -> dict:
        return asdict(self)


def evaluate(*, side: str, entry: float, current: float, peak: float,
             broker_sl: float, atr: float, spread: float,
             point: float = 0.001,
             initial_risk: float | None = None) -> ProtectionDecision:
    """Return a monotonic protection decision using price distances only."""
    is_buy = side == "buy"
    initial_risk = (
        float(initial_risk) if initial_risk is not None
        else abs(entry - broker_sl) if broker_sl else 0.0
    )
    mfe = max(0.0, peak - entry if is_buy else entry - peak)
    current_move = current - entry if is_buy else entry - current
    giveback = max(0.0, mfe - current_move)
    costs_buffer = max(spread * COST_SPREADS, point * 2)
    arm_distance = max(initial_risk * ARM_R, atr * ARM_ATR, costs_buffer)
    armed = initial_risk > 0 and atr > 0 and mfe >= arm_distance
    progress_r = mfe / initial_risk if initial_risk else 0.0
    trail_distance = max(atr * TRAIL_ATR, mfe * GIVEBACK_MFE)
    candidate = None
    locked_move = 0.0
    if armed:
        candidate = peak - trail_distance if is_buy else peak + trail_distance
        if progress_r >= SECURE_COSTS_R:
            floor = entry + costs_buffer if is_buy else entry - costs_buffer
            candidate = max(candidate, floor) if is_buy else min(candidate, floor)
        if progress_r >= 1.5:
            floor = entry + mfe * LOCK_1_5R if is_buy else entry - mfe * LOCK_1_5R
            candidate = max(candidate, floor) if is_buy else min(candidate, floor)
        elif progress_r >= 1.0:
            floor = entry + mfe * LOCK_1R if is_buy else entry - mfe * LOCK_1R
            candidate = max(candidate, floor) if is_buy else min(candidate, floor)
        locked_move = max(0.0, candidate - entry if is_buy else entry - candidate)

    minimum_change = max(point * 2, spread * 0.10)
    tighter = bool(candidate is not None and (
        (is_buy and candidate > broker_sl + minimum_change)
        or (not is_buy and candidate < broker_sl - minimum_change)
    ))
    crossed = bool(candidate is not None and (
        current <= candidate if is_buy else current >= candidate
    ))
    state = "structural_risk"
    if armed:
        state = "costs_secured" if locked_move >= costs_buffer else "protection_armed"
        if progress_r >= 1.0:
            state = "profit_secured"
        if crossed:
            state = "protection_crossed"
    return ProtectionDecision(
        state, armed, tighter, crossed, candidate, mfe, current_move, giveback,
        initial_risk, progress_r, atr, arm_distance, trail_distance,
        locked_move, costs_buffer,
    )
