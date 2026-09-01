from datetime import datetime, timedelta, timezone

from vnext.execution.mt5 import MT5BrokerClient
from vnext.runtime.mt5_position_monitor import MT5PositionMonitor
from vnext.runtime.position_management import ManagementProfile, PositionManagementService
from vnext.strategy.management import ScalpManagementParameters


class MT5:
    TIMEFRAME_M1 = 1; TIMEFRAME_M5 = 5
    TRADE_ACTION_DEAL = 1; TRADE_ACTION_SLTP = 2; ORDER_TYPE_BUY = 0; ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0; ORDER_FILLING_IOC = 0
    def __init__(self): self.requests = []
    def positions_get(self, symbol=None):
        return [type("Position", (), {"ticket": 12, "symbol": "XAUUSDr", "type": 0, "volume": .1,
            "magic": 3101, "price_open": 100., "price_current": 100., "time": 1767225600,
            "sl": 97., "tp": 105.})()]
    def copy_rates_from_pos(self, pair, timeframe, start, count):
        seconds = 60 if timeframe == self.TIMEFRAME_M1 else 300
        return [{"time": 1767225600 + seconds * i, "open": 100., "high": 100.5,
                 "low": 99.5, "close": 100.} for i in range(count)]
    def symbol_info(self, pair): return type("Symbol", (), {"point": .01})()
    def symbol_info_tick(self, pair): return type("Tick", (), {"bid": 100., "ask": 100.1})()
    def order_send(self, request): self.requests.append(request); return {"retcode": 10009}


def test_magic_position_monitor_manages_only_owned_position_on_tick():
    mt5 = MT5()
    transport = MT5BrokerClient(mt5, magic=3101)
    manager = PositionManagementService(
        profiles={"S": ManagementProfile("S", ScalpManagementParameters())}, broker=transport)
    monitor = MT5PositionMonitor(mt5=mt5, broker=transport, manager=manager, strategy_id="S")
    result = monitor.run_once(now=datetime.fromtimestamp(1767225600, timezone.utc) + timedelta(minutes=10))
    assert result["12"].applied_action == "close"
    assert mt5.requests[-1]["position"] == 12
