"""Read-only MT5 snapshot adapter for strategy-declared risk policies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def live_risk_inputs(mt5: Any, state: Mapping[str, Any], candidate_inputs: Mapping[str, Any],
                     *, magic_number: int) -> dict[str, Any] | None:
    """Resolve declared market-entry geometry and broker metadata without trading."""
    metadata = candidate_inputs.get("metadata")
    policy = metadata.get("risk_policy") if isinstance(metadata, Mapping) else None
    if not isinstance(policy, Mapping) or policy.get("entry_mode") != "MARKET":
        return None
    pair = str(state.get("pair") or "")
    direction = str(candidate_inputs.get("direction") or "").lower()
    account, terminal = mt5.account_info(), mt5.terminal_info()
    symbol, tick = mt5.symbol_info(pair), mt5.symbol_info_tick(pair)
    if not pair or direction not in {"buy", "sell"} or not all((account, terminal, symbol, tick)):
        return None
    entry = float(tick.ask if direction == "buy" else tick.bid)
    stop_distance, target_distance = float(policy["stop_distance_price"]), float(policy["target_distance_price"])
    stop = entry - stop_distance if direction == "buy" else entry + stop_distance
    target = entry + target_distance if direction == "buy" else entry - target_distance
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(day_start, now) or ()
    daily_pnl = sum(_deal_pnl(deal) for deal in deals if _field(deal, "magic", None) == magic_number)
    positions = mt5.positions_get(symbol=pair) or ()
    owned_positions = [row for row in positions if _field(row, "magic", None) == magic_number]
    demo_mode = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    broker_healthy = bool(_field(terminal, "connected", False) and _field(account, "trade_allowed", False)
                          and _field(account, "trade_expert", False))
    return {
        "account_equity": float(_field(account, "equity", 0.0)),
        "max_cash_loss": float(policy["max_cash_loss"]),
        "entry": entry, "stop": stop, "target": target, "direction": direction,
        "point_value": float(_field(symbol, "trade_tick_value", 0.0)),
        "tick_size": float(_field(symbol, "trade_tick_size", 0.0)),
        "tick_value": float(_field(symbol, "trade_tick_value", 0.0)),
        "volume_min": float(_field(symbol, "volume_min", 0.0)),
        "volume_max": float(_field(symbol, "volume_max", 0.0)),
        "volume_step": float(_field(symbol, "volume_step", 0.0)),
        "daily_pnl": daily_pnl, "daily_loss_cap": float(policy["daily_loss_cap"]),
        "open_positions": len(owned_positions), "max_open_positions": int(policy["max_open_positions"]),
        "broker_healthy": broker_healthy,
        "data_healthy": str(state.get("data_quality", {}).get("status", "")) == "ready",
        "demo_account": _field(account, "trade_mode", None) == demo_mode,
    }


def _deal_pnl(deal: Any) -> float:
    return sum(float(_field(deal, name, 0.0) or 0.0) for name in ("profit", "swap", "commission", "fee"))


def _field(value: Any, name: str, default: Any) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
