"""Explicit order lifecycle independent from broker adapter implementation."""

from __future__ import annotations

from dataclasses import dataclass, replace


ORDER_STATES = frozenset({"PENDING_SUBMIT", "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "CANCELLED", "REPLACE_PENDING", "REJECTED", "EXPIRED", "FAILED"})
TRANSITIONS = {
    "PENDING_SUBMIT": {"SUBMITTED", "FAILED", "EXPIRED"},
    "SUBMITTED": {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "REJECTED", "FAILED"},
    "ACKNOWLEDGED": {"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "REPLACE_PENDING", "FAILED"},
    "PARTIALLY_FILLED": {"PARTIALLY_FILLED", "FILLED", "CANCEL_PENDING", "FAILED"},
    "CANCEL_PENDING": {"CANCELLED", "PARTIALLY_FILLED", "FILLED", "FAILED"},
    "REPLACE_PENDING": {"ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "REJECTED", "FAILED"},
}


@dataclass(frozen=True, slots=True)
class Order:
    order_id: str
    candidate_id: str
    pair: str
    strategy_id: str
    state: str = "PENDING_SUBMIT"
    broker_order_id: str | None = None
    filled_volume: float = 0.0
    requested_volume: float = 0.0

    def transition(self, state: str, *, broker_order_id: str | None = None,
                   filled_volume: float | None = None) -> "Order":
        if state not in ORDER_STATES:
            raise ValueError(f"unknown order state: {state}")
        if state not in TRANSITIONS.get(self.state, set()):
            raise ValueError(f"invalid order transition {self.state}->{state}")
        return replace(self, state=state,
                       broker_order_id=broker_order_id or self.broker_order_id,
                       filled_volume=self.filled_volume if filled_volume is None else filled_volume)
