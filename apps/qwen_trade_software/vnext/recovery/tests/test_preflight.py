from types import SimpleNamespace

from vnext.execution.mt5 import MT5BrokerClient
from vnext.recovery.preflight import run_preflight


class FakeMT5:
    def account_info(self): return SimpleNamespace(login=7, trade_allowed=True)
    def terminal_info(self): return SimpleNamespace(connected=True)
    def positions_get(self): return [SimpleNamespace(ticket=12, symbol="XAUUSDr", type=0, volume=0.1)]


class Persistence:
    def ensure_ready(self): return SimpleNamespace(timescale=True, neo4j=True, redis=True, ready=True)


def test_mt5_snapshot_is_read_only_and_normalized():
    snapshot = MT5BrokerClient(FakeMT5(), magic=7).snapshot()
    assert snapshot["healthy"] is True
    assert snapshot["positions"] == ({"position_id": "12", "pair": "XAUUSDr", "direction": "buy", "volume": 0.1},)


def test_preflight_fails_closed_on_position_mismatch():
    result = run_preflight(persistence=Persistence(), broker=MT5BrokerClient(FakeMT5(), magic=7),
                           ledger_positions=[], redis_rebuilt=True)
    assert result.allowed is False
    assert "broker_ledger_position_mismatch" in result.plan.reasons
