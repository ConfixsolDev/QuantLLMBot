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
        for row in self.owned_position_rows(positions):
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

    def owned_position_rows(self, positions: Any = None) -> list[Mapping[str, Any]]:
        """Read broker positions owned by this strategy magic; no mutation."""
        source = self.mt5.positions_get() if positions is None else positions
        if source is None:
            raise RuntimeError("MT5 positions unavailable")
        owned: list[Mapping[str, Any]] = []
        for position in source:
            row = _as_mapping(position)
            position_magic = row.get("magic")
            # Never adopt an unnamespaced row: test doubles must model the
            # same broker ownership invariant as a live MT5 position.
            if position_magic is None or int(position_magic) != self.magic:
                continue
            owned.append(row)
        return owned

    def order_send(self, order: Mapping[str, Any]) -> Any:
        direction = str(order.get("direction", "")).lower()
        if direction not in {"buy", "sell"}:
            raise ValueError("MT5 order direction must be buy or sell")
        symbol, volume = str(order.get("pair", "")), float(order.get("volume", 0))
        if not symbol or volume <= 0:
            raise ValueError("MT5 order requires pair and positive volume")
        is_buy = direction == "buy"
        if "entry_price" not in order:
            raise ValueError("MT5 order requires a risk-bound entry_price")
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL, "symbol": symbol,
            "volume": volume,
            "type": self.mt5.ORDER_TYPE_BUY if is_buy else self.mt5.ORDER_TYPE_SELL,
            "price": float(order["entry_price"]),
            "sl": float(order["stop"]), "tp": float(order["target"]),
            "deviation": self.deviation, "magic": self.magic,
            "comment": str(order.get("comment", "QuantLLM-vNext"))[:31],
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        return self.mt5.order_send(request)

    def modify_position(self, *, position_id: str | int, pair: str, stop: float,
                        target: float, comment: str = "QuantLLM-vNext") -> Any:
        """Tighten an already-owned position's protection; caller validates intent."""
        if not str(position_id) or not pair or stop <= 0 or target <= 0:
            raise ValueError("position modification requires identity and positive protection")
        self._require_owned_position(position_id=position_id, pair=pair)
        request = {
            "action": self.mt5.TRADE_ACTION_SLTP, "position": int(position_id),
            "symbol": pair, "sl": float(stop), "tp": float(target),
            "magic": self.magic, "comment": str(comment)[:31],
        }
        return self.mt5.order_send(request)

    def close_position(self, *, position_id: str | int, pair: str, direction: str,
                       volume: float, comment: str = "QuantLLM-vNext") -> Any:
        """Close an owned position at the current opposite executable quote."""
        if direction not in {"buy", "sell"} or not str(position_id) or not pair or volume <= 0:
            raise ValueError("position close requires identity, direction, and positive volume")
        self._require_owned_position(position_id=position_id, pair=pair)
        tick = self.mt5.symbol_info_tick(pair)
        if tick is None:
            raise RuntimeError("MT5 close quote unavailable")
        is_buy_position = direction == "buy"
        request = {
            "action": self.mt5.TRADE_ACTION_DEAL, "position": int(position_id), "symbol": pair,
            "volume": float(volume),
            "type": self.mt5.ORDER_TYPE_SELL if is_buy_position else self.mt5.ORDER_TYPE_BUY,
            "price": float(_field(tick, "bid" if is_buy_position else "ask", 0.0)),
            "deviation": self.deviation, "magic": self.magic, "comment": str(comment)[:31],
            "type_time": self.mt5.ORDER_TIME_GTC, "type_filling": self.mt5.ORDER_FILLING_IOC,
        }
        if request["price"] <= 0:
            raise RuntimeError("MT5 close quote invalid")
        return self.mt5.order_send(request)

    def _require_owned_position(self, *, position_id: str | int, pair: str) -> None:
        """Enforce magic-number ownership again at the mutation boundary."""
        positions = self.mt5.positions_get(symbol=pair)
        if positions is None:
            raise RuntimeError("MT5 position ownership check unavailable")
        wanted = str(position_id)
        for position in positions:
            row = _as_mapping(position)
            if str(row.get("ticket", row.get("position_id", ""))) == wanted:
                if int(row.get("magic", -1)) == self.magic:
                    return
                break
        raise RuntimeError("position is not owned by this V2 magic number")


class MT5IdempotentBroker:
    """Production composition: MT5 transport plus durable/idempotent adapter."""

    def __init__(self, mt5_client: Any, *, magic: int, submission_store: Any = None) -> None:
        self.transport = MT5BrokerClient(mt5_client, magic=magic)
        self.adapter = IdempotentBrokerAdapter(self.transport, submission_store=submission_store)

    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]:
        return self.adapter.submit(order)

    def snapshot(self) -> dict[str, Any]:
        return self.transport.snapshot()

    def modify_position(self, **kwargs: Any) -> Any:
        return self.transport.modify_position(**kwargs)

    def close_position(self, **kwargs: Any) -> Any:
        return self.transport.close_position(**kwargs)


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
