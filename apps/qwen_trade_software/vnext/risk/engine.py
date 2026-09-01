"""Hard, broker-normalized risk checks with no market interpretation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    reasons: tuple[str, ...]
    risk_amount: float
    stop_distance: float
    normalized_volume: float | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    request_hash: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"approved": self.approved, "reasons": list(self.reasons),
                "risk_amount": self.risk_amount, "stop_distance": self.stop_distance,
                "normalized_volume": self.normalized_volume, "entry_price": self.entry_price,
                "stop_price": self.stop_price, "target_price": self.target_price,
                "request_hash": self.request_hash}


def evaluate_risk(*, account_equity: float, entry: float, stop: float,
                  point_value: float, risk_fraction: float | None = None,
                  max_cash_loss: float | None = None, target: float | None = None,
                  direction: str | None = None, tick_size: float | None = None,
                  tick_value: float | None = None, volume_min: float | None = None,
                  volume_max: float | None = None, volume_step: float | None = None,
                  daily_pnl: float = 0.0, daily_loss_cap: float | None = None,
                  open_exposure: float = 0.0, exposure_cap: float | None = None,
                  open_positions: int = 0, max_open_positions: int | None = None,
                  broker_healthy: bool = True, data_healthy: bool = True,
                  demo_account: bool = True) -> RiskDecision:
    """Veto unsafe geometry and derive broker-valid volume when metadata exists.

    `max_cash_loss` is strategy-owned. This common component enforces it against
    broker economics and volume constraints; it never chooses direction or prices.
    """
    reasons: list[str] = []
    entry_value, stop_value = float(entry), float(stop)
    distance = abs(entry_value - stop_value)
    risk_amount = (float(max_cash_loss) if max_cash_loss is not None
                   else max(0.0, float(account_equity) * float(risk_fraction or 0.0)))
    if account_equity <= 0 or point_value <= 0 or risk_amount <= 0:
        reasons.append("invalid_risk_configuration")
    if distance <= 0:
        reasons.append("stop_distance_invalid")
    if risk_amount > account_equity:
        reasons.append("risk_exceeds_equity")
    if direction is not None and direction not in {"buy", "sell"}:
        reasons.append("invalid_direction")
    target_value = float(target) if target is not None else None
    if target_value is not None:
        if direction == "buy" and not (stop_value < entry_value < target_value):
            reasons.append("buy_geometry_invalid")
        elif direction == "sell" and not (target_value < entry_value < stop_value):
            reasons.append("sell_geometry_invalid")
        elif direction is None:
            reasons.append("target_requires_direction")
    if daily_loss_cap is not None and daily_pnl <= -abs(float(daily_loss_cap)):
        reasons.append("daily_loss_cap_reached")
    if exposure_cap is not None and open_exposure >= exposure_cap:
        reasons.append("exposure_cap_reached")
    if max_open_positions is not None and open_positions >= max_open_positions:
        reasons.append("position_cap_reached")
    if not broker_healthy:
        reasons.append("broker_unhealthy")
    if not data_healthy:
        reasons.append("data_unhealthy")
    if not demo_account:
        reasons.append("non_demo_account")

    normalized_volume = None
    broker_volume_fields = (tick_size, tick_value, volume_min, volume_max, volume_step)
    if any(value is not None for value in broker_volume_fields):
        if not all(value is not None and float(value) > 0 for value in broker_volume_fields):
            reasons.append("broker_volume_metadata_invalid")
        elif distance > 0:
            per_lot_loss = distance / float(tick_size) * float(tick_value)
            raw_volume = risk_amount / per_lot_loss if per_lot_loss > 0 else 0.0
            normalized_volume = _round_down(raw_volume, float(volume_step))
            if normalized_volume < float(volume_min):
                reasons.append("risk_below_broker_minimum_volume")
            elif normalized_volume > float(volume_max):
                reasons.append("risk_above_broker_maximum_volume")
            elif normalized_volume <= 0:
                reasons.append("normalized_volume_invalid")

    request_hash = hashlib.sha256(json.dumps({
        "account_equity": account_equity, "risk_amount": risk_amount, "entry": entry_value,
        "stop": stop_value, "target": target_value, "direction": direction,
        "tick_size": tick_size, "tick_value": tick_value, "volume_min": volume_min,
        "volume_max": volume_max, "volume_step": volume_step, "daily_pnl": daily_pnl,
        "daily_loss_cap": daily_loss_cap, "open_exposure": open_exposure,
        "exposure_cap": exposure_cap, "open_positions": open_positions,
        "max_open_positions": max_open_positions, "demo_account": demo_account,
    }, sort_keys=True, default=str).encode()).hexdigest()
    return RiskDecision(not reasons, tuple(reasons), risk_amount, distance, normalized_volume,
                        entry_value, stop_value, target_value, request_hash)


def _round_down(value: float, step: float) -> float:
    if value <= 0 or step <= 0:
        return 0.0
    return round(math.floor((value + 1e-12) / step) * step, 8)
