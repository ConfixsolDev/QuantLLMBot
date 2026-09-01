"""Read MT5 positions owned by one magic number and run V2 management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any, Mapping

from vnext.execution.mt5 import MT5BrokerClient
from vnext.runtime.position_management import ManagedPosition, PositionManagementResult, PositionManagementService


class MT5PositionMonitor:
    """Per-tick adapter. It never sees or touches another magic namespace."""

    def __init__(self, *, mt5: Any, broker: MT5BrokerClient,
                 manager: PositionManagementService, strategy_id: str) -> None:
        if not strategy_id:
            raise ValueError("magic-owned monitor requires a strategy identity")
        self.mt5, self.broker, self.manager, self.strategy_id = mt5, broker, manager, strategy_id
        self._peaks: dict[str, float] = {}

    def run_once(self, *, now: datetime | None = None) -> dict[str, PositionManagementResult]:
        observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        results: dict[str, PositionManagementResult] = {}
        for row in self.broker.owned_position_rows():
            position = self._managed_position(row, observed)
            results[position.position_id] = self.manager.on_tick(position, now=observed)
        active = set(results)
        self._peaks = {position_id: peak for position_id, peak in self._peaks.items() if position_id in active}
        return results

    def _managed_position(self, row: Mapping[str, Any], now: datetime) -> ManagedPosition:
        pair, side = str(row["symbol"]), _direction(row)
        position_id = str(row.get("ticket", row.get("position_id")))
        m1, m5 = self._completed_candles(pair)
        current = float(row.get("price_current") or _quote(self.mt5, pair, side))
        entry = float(row.get("price_open"))
        broker_stop, broker_target = float(row.get("sl") or 0.0), float(row.get("tp") or 0.0)
        if broker_stop <= 0 or broker_target <= 0:
            raise RuntimeError("owned position lacks broker stop or target protection")
        prior_peak = self._peaks.get(position_id, entry)
        peak = max(prior_peak, current) if side == "buy" else min(prior_peak, current)
        self._peaks[position_id] = peak
        ranges = [float(item["high"]) - float(item["low"]) for item in m1]
        atr = max(mean(ranges[-14:]), 1e-9)
        point = float(getattr(self.mt5.symbol_info(pair), "point", 0.0) or 0.0)
        if point <= 0:
            raise RuntimeError("MT5 symbol point unavailable")
        opened = datetime.fromtimestamp(float(row.get("time")), timezone.utc)
        latest_m1, latest_m5 = m1[-1], m5[-1]
        return ManagedPosition(
            position_id=position_id, strategy_id=self.strategy_id, pair=pair, direction=side,
            volume=float(row["volume"]), entry=entry, current=current, peak=peak, opened_at=opened,
            broker_stop=broker_stop, broker_target=broker_target,
            atr=atr, spread=float(getattr(self.mt5.symbol_info_tick(pair), "ask", current)
                              - getattr(self.mt5.symbol_info_tick(pair), "bid", current)), point=point,
            latest_m1=latest_m1, latest_m5=latest_m5,
            latest_m1_id=str(latest_m1["bar_id"]), latest_m5_id=str(latest_m5["bar_id"]),
        )

    def _completed_candles(self, pair: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        m1_rows = self.mt5.copy_rates_from_pos(pair, self.mt5.TIMEFRAME_M1, 1, 20)
        m5_rows = self.mt5.copy_rates_from_pos(pair, self.mt5.TIMEFRAME_M5, 1, 2)
        m1_rows = () if m1_rows is None else m1_rows
        m5_rows = () if m5_rows is None else m5_rows
        m1 = [_candle(row, "M1") for row in m1_rows]
        m5 = [_candle(row, "M5") for row in m5_rows]
        if len(m1) < 14 or not m5:
            raise RuntimeError("insufficient completed candles for position management")
        return m1, m5


def _candle(row: Any, timeframe: str) -> dict[str, Any]:
    get = row.get if isinstance(row, Mapping) else lambda key, default=None: row[key]
    stamp = int(get("time"))
    return {"bar_id": f"{timeframe}:{stamp}", "time": stamp, "open": float(get("open")),
            "high": float(get("high")), "low": float(get("low")), "close": float(get("close"))}


def _direction(row: Mapping[str, Any]) -> str:
    value = row.get("type")
    if value in (0, "0", "buy", "BUY"):
        return "buy"
    if value in (1, "1", "sell", "SELL"):
        return "sell"
    raise RuntimeError("MT5 position direction unavailable")


def _quote(mt5: Any, pair: str, side: str) -> float:
    tick = mt5.symbol_info_tick(pair)
    if tick is None:
        raise RuntimeError("MT5 quote unavailable")
    return float(getattr(tick, "bid" if side == "buy" else "ask"))
