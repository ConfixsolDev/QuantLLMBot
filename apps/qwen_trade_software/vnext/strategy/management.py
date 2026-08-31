"""Deterministic, strategy-owned early-failure and profit-protection policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ScalpManagementParameters:
    initial_check_seconds: int = 10
    next_m1_check_seconds: int = 15
    failed_check_wait_minutes: int = 1
    break_even_atr_trigger: float = 1.0
    break_even_offset_atr: float = 0.05
    maximum_early_adverse_atr: float = 0.25
    spread_cost_multiple: float = 3.0
    minimum_point_buffer: float = 2.0

    def __post_init__(self) -> None:
        if self.initial_check_seconds <= 0 or self.next_m1_check_seconds <= 0 or self.failed_check_wait_minutes <= 0:
            raise ValueError("scalp management time parameters must be positive")
        if self.break_even_atr_trigger <= 0 or self.break_even_offset_atr < 0 or self.maximum_early_adverse_atr <= 0:
            raise ValueError("scalp management ATR parameters are invalid")
        if self.spread_cost_multiple < 0 or self.minimum_point_buffer < 0:
            raise ValueError("scalp management cost parameters are invalid")


@dataclass(frozen=True, slots=True)
class ManagementDecision:
    action: str
    phase: str
    reason: str
    favorable_move: float
    adverse_move: float
    mfe_atr: float
    candidate_stop: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"action": self.action, "phase": self.phase, "reason": self.reason,
                "favorable_move": self.favorable_move, "adverse_move": self.adverse_move,
                "mfe_atr": self.mfe_atr, "candidate_stop": self.candidate_stop}


def manage_scalp(*, side: str, entry: float, current: float, peak: float,
                 opened_at: datetime, now: datetime, atr: float, broker_stop: float,
                 spread: float, point: float, parameters: ScalpManagementParameters) -> ManagementDecision:
    """Evaluate one position snapshot without I/O or broker side effects.

    The first two checks govern early entry failure. Once the trade earns the
    configured ATR threshold, the manager proposes only a tighter
    break-even-plus stop; it never widens an accepted broker stop.
    """
    if side not in {"buy", "sell"} or atr <= 0 or point <= 0 or spread < 0:
        raise ValueError("invalid scalp management snapshot")
    opened = _utc(opened_at)
    observed = _utc(now)
    if observed < opened:
        raise ValueError("management observation cannot precede entry")
    favorable = current - entry if side == "buy" else entry - current
    adverse = max(0.0, -favorable)
    mfe = max(0.0, peak - entry if side == "buy" else entry - peak)
    mfe_atr = mfe / atr
    costs = max(spread * parameters.spread_cost_multiple, point * parameters.minimum_point_buffer)
    favorable_threshold = costs
    age = (observed - opened).total_seconds()
    early_adverse_limit = parameters.maximum_early_adverse_atr * atr
    if age < parameters.initial_check_seconds:
        phase = "INITIAL_CHECK"
    else:
        next_open = opened.replace(second=0, microsecond=0) + timedelta(minutes=1)
        next_age = (observed - next_open).total_seconds()
        if 0 <= next_age <= parameters.next_m1_check_seconds:
            phase = "NEXT_M1_CHECK"
        elif observed < next_open + timedelta(minutes=parameters.failed_check_wait_minutes):
            phase = "FAILED_CHECK_WAIT"
        else:
            phase = "EXPIRED"
    if phase in {"INITIAL_CHECK", "NEXT_M1_CHECK", "FAILED_CHECK_WAIT"} and adverse >= early_adverse_limit:
        return ManagementDecision("CLOSE", phase, "early_adverse_move", favorable, adverse, mfe_atr)
    if phase == "INITIAL_CHECK":
        return ManagementDecision("HOLD" if favorable >= favorable_threshold else "WAIT", phase,
                                  "initial_favorable_move" if favorable >= favorable_threshold else "await_initial_confirmation",
                                  favorable, adverse, mfe_atr)
    if phase == "NEXT_M1_CHECK":
        return ManagementDecision("HOLD" if favorable >= favorable_threshold else "WAIT", phase,
                                  "next_m1_favorable_move" if favorable >= favorable_threshold else "await_next_m1_confirmation",
                                  favorable, adverse, mfe_atr)
    if phase == "FAILED_CHECK_WAIT":
        return ManagementDecision("HOLD" if favorable >= favorable_threshold else "WAIT", phase,
                                  "late_favorable_recovery" if favorable >= favorable_threshold else "await_failure_deadline",
                                  favorable, adverse, mfe_atr)
    if phase == "EXPIRED" and favorable < favorable_threshold:
        return ManagementDecision("CLOSE", phase, "scalp_confirmation_expired", favorable, adverse, mfe_atr)
    if mfe_atr >= parameters.break_even_atr_trigger:
        stop = entry + parameters.break_even_offset_atr * atr + costs if side == "buy" else entry - parameters.break_even_offset_atr * atr - costs
        tighter = (side == "buy" and stop > broker_stop + point) or (side == "sell" and stop < broker_stop - point)
        if tighter:
            return ManagementDecision("MOVE_STOP", "PROFIT_PROTECTION", "atr_break_even_plus", favorable, adverse, mfe_atr, stop)
    return ManagementDecision("HOLD", "PROTECTED" if mfe_atr >= parameters.break_even_atr_trigger else "ACTIVE",
                              "no_management_change", favorable, adverse, mfe_atr)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
