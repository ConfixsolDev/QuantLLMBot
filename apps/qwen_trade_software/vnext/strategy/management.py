"""Deterministic, strategy-owned early-failure and profit-protection policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


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
    maximum_position_seconds: int = 600
    qwen_review_seconds: int = 300

    def __post_init__(self) -> None:
        if (self.initial_check_seconds <= 0 or self.next_m1_check_seconds <= 0
                or self.failed_check_wait_minutes <= 0 or self.maximum_position_seconds <= 0
                or self.qwen_review_seconds <= 0):
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


@dataclass(frozen=True, slots=True)
class ManagementReview:
    """Validated, bounded management instruction for one open strategy position."""
    action: str
    reason: str
    evidence_ids: tuple[str, ...]
    candidate_stop: float | None = None
    candidate_target: float | None = None


def emergency_close_required(*, side: str, invalidation_price: float,
                             latest_m1: Mapping[str, Any], latest_m5: Mapping[str, Any]) -> bool:
    """Require exit only when both completed candles cross the invalidation.

    This is the approved legacy M1+M5 emergency rule.  It is deliberately
    based on completed bars, never a transient tick or unrealized P&L.
    """
    if side not in {"buy", "sell"}:
        raise ValueError("unknown position side")
    try:
        m1, m5 = float(latest_m1["close"]), float(latest_m5["close"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("emergency close requires completed M1 and M5 closes") from exc
    return m1 < invalidation_price and m5 < invalidation_price if side == "buy" else m1 > invalidation_price and m5 > invalidation_price


def validate_qwen_management_review(*, response: Mapping[str, Any], side: str,
                                    current_stop: float, current_target: float,
                                    latest_m1_id: str, latest_m5_id: str) -> tuple[ManagementReview, tuple[str, ...]]:
    """Constrain Qwen to approved close/protect/hold management actions.

    A close needs both latest completed-candle citations.  Protection can only
    tighten the stop.  A target change additionally needs explicit verified
    deterioration and must remain ahead of the current market (the latter is
    checked at the broker-application boundary).
    """
    action = str(response.get("action", "hold")).lower()
    evidence = tuple(str(item) for item in response.get("evidence_ids", ()) if str(item))
    failures: list[str] = []
    if action not in {"hold", "protect", "close"}:
        failures.append("management:unknown_action")
        action = "hold"
    if action == "close":
        if response.get("close_confirmed") is not True:
            failures.append("management:close_not_confirmed")
        if latest_m1_id not in evidence or latest_m5_id not in evidence:
            failures.append("management:close_missing_completed_candle_evidence")
    stop = _optional_price(response.get("candidate_stop"), "candidate_stop", failures)
    target = _optional_price(response.get("candidate_target"), "candidate_target", failures)
    if action == "protect":
        if latest_m1_id not in evidence or latest_m5_id not in evidence:
            failures.append("management:protect_missing_completed_candle_evidence")
        tighter = stop is not None and ((side == "buy" and stop > current_stop) or (side == "sell" and stop < current_stop))
        if stop is not None and not tighter:
            failures.append("management:stop_not_tighter")
        if target is not None:
            if response.get("deterioration_confirmed") is not True:
                failures.append("management:target_change_without_deterioration")
            if latest_m1_id not in evidence or latest_m5_id not in evidence:
                failures.append("management:target_change_missing_completed_candle_evidence")
    if action == "hold" and (stop is not None or target is not None):
        failures.append("management:hold_cannot_change_protection")
    if failures:
        return ManagementReview("hold", "management_response_rejected", evidence), tuple(sorted(set(failures)))
    return ManagementReview(action, str(response.get("reason", ""))[:180], evidence, stop, target), ()


def _optional_price(value: Any, name: str, failures: list[str]) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        failures.append(f"management:invalid_{name}")
        return None


def qwen_review_due(*, opened_at: datetime, now: datetime,
                    last_review_at: datetime | None, parameters: ScalpManagementParameters) -> bool:
    """Whether an open scalp may request its bounded five-minute Qwen review."""
    opened, observed = _utc(opened_at), _utc(now)
    if observed < opened:
        raise ValueError("management observation cannot precede entry")
    previous = opened if last_review_at is None else _utc(last_review_at)
    return observed >= previous + timedelta(seconds=parameters.qwen_review_seconds)


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
    if age >= parameters.maximum_position_seconds:
        return ManagementDecision("CLOSE", "MAX_DURATION", "max_scalp_duration",
                                  favorable, adverse, mfe_atr)
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
