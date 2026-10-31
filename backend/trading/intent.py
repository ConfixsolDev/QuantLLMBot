"""The one object that crosses from decision to execution: a TradeIntent.

Strategy code (deterministic) builds it from engine facts after Qwen approved
the plan; the executor turns it into an order or refuses it. Nothing else
about the decision reaches the broker. Prices here come from code, never
from model text (V3 Part E1: "MT5 facts and code-owned levels are
authoritative over model text").
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TradeIntent:
    intent_id: str            # deterministic: strategy + candidate + trigger candle
    strategy_ref: str         # id@vN#hash
    decision_id: str          # the Qwen decision that approved the plan
    candidate_id: str         # stable candidate key (level id : test number)
    side: str                 # "buy" | "sell"
    entry_low: float          # the live price must be inside [entry_low, entry_high]
    entry_high: float
    stop: float               # structural invalidation = broker stop (always sent with the order)
    target: float             # next higher-timeframe level = broker take-profit
    created_at: int           # UTC epoch: close of the trigger candle
    expires_at: int           # UTC epoch: no fill after this
    atr: float                # ATR(M15) at the trigger, for reference
    meta: dict = field(default_factory=dict)   # level, test number, rejection candle ...

    def as_dict(self) -> dict:
        return asdict(self)

    def risk_per_unit(self, price: float) -> float:
        """Price distance from ``price`` to the stop."""
        return abs(price - self.stop)
