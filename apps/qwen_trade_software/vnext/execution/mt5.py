"""Validated MT5 transport for the V2 idempotent broker adapter."""

from __future__ import annotations

from typing import Any, Mapping

from vnext.execution.broker import IdempotentBrokerAdapter


class MT5BrokerClient:
    """Translate only validated V2 order fields into an MT5 market request."""

    def __init__(self, mt5_client: Any, *, magic: int, deviation: int = 20) -> None:
        if magic <= 0 or deviation < 0:
            raise ValueError("invalid MT5 broker configuration")
        self.mt5, self.magic, self.deviation = mt5_client, magic, deviation

    def snapshot(self) -> dict[str, Any]:
        """Return a read-only broker snapshot for restart reconciliation.

        The adapter deliberately normalizes only fields needed by recovery. It
        never places, modifies, or closes an order while taking a snapshot.
        """
        account = self.mt5.account_info()
        terminal = self.mt5.terminal_info()
        positions = self.mt5.positions_get()
        if account is None or terminal is None or positions is None:
            raise RuntimeError("MT5 snapshot unavailable")
        normalized = []
        for position in positions:
            row = _as_mapping(position)
            position_id = row.get("ticket", row.get("position_id"))
            if position_id is None:
                raise RuntimeError("MT5 position has no stable ticket")
            normalized.append({
                "position_id": str(position_id),
                "pair": str(row.get("symbol", "")),
                "direction": _position_direction(row),
                "volume": float(row.get("volume", 0.0)),
            })
        return {
            "healthy": bool(_field(terminal, "connected", True))
            and bool(_field(account, "trade_allowed", True)),
            "positions": tuple(normalized),
            "account_login": str(_field(account, "login", "")),
        }

    def order_send(self, order: Mapping[str, Any]) -> Any:
        direction = str(order.get("direction", "")).lower()
        if direction not in {"buy", "sell"}:
            raise ValueError("MT5 order direction must be buy or sell")
        symbol, volume = str(order.get("pair", "")), float(order.get("volume", 0))
        if not symbol or volume <= 0:
            raise ValueError("MT5 order requires pair and positive volume")
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("MT5 tick unavailable")
        is_buy = direction == "buy"
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": symbol,
            "volume": volume,
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": float(tick.ask if is_buy else tick.bid),
            "sl": float(order["stop"]), "tp": float(order["target"]),
            "deviation": self.deviation, "magic": self.magic,
            "comment": str(order.get("comment", "QuantLLM-vNext"))[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        return self.mt5.order_send(request)


class MT5IdempotentBroker:
    """Production composition: MT5 transport plus durable/idempotent adapter."""

    def __init__(self, mt5_client: Any, *, magic: int, submission_store: Any = None) -> None:
        self.adapter = IdempotentBrokerAdapter(
            MT5BrokerClient(mt5_client, magic=magic), submission_store=submission_store)

    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]:
        return self.adapter.submit(order)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {name: getattr(value, name) for name in dir(value)
            if not name.startswith("_") and not callable(getattr(value, name))}


def _field(value: Any, name: str, default: Any) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def _position_direction(row: Mapping[str, Any]) -> str:
    position_type = row.get("type")
    if position_type in (0, "0", "buy", "BUY"):
        return "buy"
    if position_type in (1, "1", "sell", "SELL"):
        return "sell"
    raise RuntimeError("MT5 position has unknown direction")
