"""Hard risk checks; no discretionary market interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    risk_amount: float
    stop_distance: float

    def as_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "reasons": list(self.reasons),
                "risk_amount": self.risk_amount, "stop_distance": self.stop_distance}


def evaluate_risk(*, account_equity: float, risk_fraction: float,
                  entry: float, stop: float, point_value: float,
                  daily_pnl: float = 0.0, daily_loss_cap: float | None = None,
                  open_exposure: float = 0.0, exposure_cap: float | None = None,
                  broker_healthy: bool = True, data_healthy: bool = True) -> RiskDecision:
    reasons: list[str] = []
    distance = abs(float(entry) - float(stop))
    risk_amount = max(0.0, float(account_equity) * float(risk_fraction))
    if account_equity <= 0 or risk_fraction <= 0 or point_value <= 0:
        reasons.append("invalid_risk_configuration")
    if distance <= 0:
        reasons.append("stop_distance_invalid")
    if daily_loss_cap is not None and daily_pnl <= daily_loss_cap:
        reasons.append("daily_loss_cap_reached")
    if exposure_cap is not None and open_exposure >= exposure_cap:
        reasons.append("exposure_cap_reached")
    if not broker_healthy:
        reasons.append("broker_unhealthy")
    if not data_healthy:
        reasons.append("data_unhealthy")
    return RiskDecision(not reasons, tuple(reasons), risk_amount, distance)
