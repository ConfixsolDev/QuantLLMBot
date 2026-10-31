"""Position size from a % of the balance and the stop distance.

    risk money   = balance x risk_pct / 100
    distance     = |entry - stop| + spread + slippage allowance   (price units)
    value / unit = tick_value / tick_size     (money per 1.0 price move per lot, from MT5)
    lots         = risk money / (distance x value per unit)
                   rounded DOWN to volume_step, clamped to [volume_min, volume_max]

Rounding down means the real risk is never above the budget. If even
volume_min would risk more than the budget, there is NO trade (the stop is
never moved closer to make a size fit — the stop is the structure).

For XAUUSD most brokers quote tick_size 0.01 and tick_value 1.0 per lot
(= 100 oz: $100 per $1 move), but the numbers are always read from the
broker, never assumed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolSpec:
    symbol: str
    tick_value: float          # money per tick per 1.0 lot
    tick_size: float           # price units per tick
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int

    @property
    def value_per_unit(self) -> float:
        return self.tick_value / self.tick_size


@dataclass(frozen=True)
class Size:
    lots: float
    risk_money: float          # money lost at the stop with these lots (incl. spread + slippage allowance)
    distance: float            # price units used for the calculation
    reason: str = "ok"


def position_size(balance: float, risk_pct: float, entry: float, stop: float, spec: SymbolSpec,
                  spread: float = 0.0, slippage: float = 0.0) -> Size:
    distance = abs(entry - stop) + max(spread, 0.0) + max(slippage, 0.0)
    if balance <= 0 or risk_pct <= 0:
        return Size(0.0, 0.0, distance, "no balance or no risk set")
    if distance <= 0:
        return Size(0.0, 0.0, distance, "stop distance is zero")
    budget = balance * risk_pct / 100.0
    per_lot = distance * spec.value_per_unit
    raw = budget / per_lot
    steps = math.floor(raw / spec.volume_step + 1e-9)
    lots = round(steps * spec.volume_step, 8)
    if lots < spec.volume_min:
        min_risk = spec.volume_min * per_lot
        return Size(0.0, 0.0, distance,
                    f"minimum lot {spec.volume_min} would risk {min_risk:.2f} > budget {budget:.2f}")
    lots = min(lots, spec.volume_max)
    return Size(lots, round(lots * per_lot, 2), distance)


#: Typical XAUUSD contract (100 oz: $100 per $1 move per lot). Used ONLY by the
#: paper broker when MT5 is not connected; live sizing always reads the broker.
XAUUSD_DEFAULT = SymbolSpec("XAUUSD", tick_value=1.0, tick_size=0.01, volume_min=0.01,
                            volume_max=100.0, volume_step=0.01, digits=2)
