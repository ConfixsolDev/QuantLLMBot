import pytest

from vnext.execution.broker import BrokerSubmissionError, IdempotentBrokerAdapter
from vnext.execution.mt5 import MT5BrokerClient


class FakeClient:
    def __init__(self): self.calls = []
    def order_send(self, request): self.calls.append(dict(request)); return {"retcode": "accepted"}


class RejectingClient:
    def order_send(self, request): return {"retcode": 10004}


def test_duplicate_order_is_submitted_once_and_not_filled():
    client = FakeClient()
    adapter = IdempotentBrokerAdapter(client)
    order = {"order_id": "o1", "candidate_id": "c1", "volume": 1}
    first = adapter.submit(order)
    second = adapter.submit(order)
    assert first == second
    assert first["state"] == "SUBMITTED"
    assert first["filled_volume"] == 0.0
    assert len(client.calls) == 1


def test_reused_order_id_with_changed_request_is_rejected():
    adapter = IdempotentBrokerAdapter(FakeClient())
    adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 1})
    with pytest.raises(BrokerSubmissionError):
        adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 2})


def test_broker_rejection_is_not_recorded_as_submitted():
    adapter = IdempotentBrokerAdapter(RejectingClient())
    with pytest.raises(BrokerSubmissionError):
        adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 1})


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 2
    ORDER_TYPE_SELL = 3
    ORDER_TIME_GTC = 4
    ORDER_FILLING_IOC = 5
    class Tick: bid = 10.0; ask = 10.2
    def symbol_info_tick(self, symbol): return self.Tick()
    def order_send(self, request): self.request = request; return {"retcode": 10009}
    def positions_get(self, symbol=None):
        return [type("Position", (), {"ticket": 12, "symbol": symbol or "XAUUSDr", "type": 0,
                                       "volume": .1, "magic": 7})()]


class SnapshotMT5:
    def account_info(self): return type("Account", (), {"login": 7, "trade_allowed": True})()
    def terminal_info(self): return type("Terminal", (), {"connected": True})()
    def positions_get(self):
        return [
            type("Position", (), {"ticket": 1, "symbol": "XAUUSDr", "type": 0, "volume": 0.1, "magic": 0})(),
            type("Position", (), {"ticket": 2, "symbol": "XAUUSDr", "type": 1, "volume": 0.1, "magic": 3101})(),
        ]


def test_snapshot_excludes_positions_owned_by_another_magic_namespace():
    snapshot = MT5BrokerClient(SnapshotMT5(), magic=3101).snapshot()
    assert [row["position_id"] for row in snapshot["positions"]] == ["2"]


def test_snapshot_excludes_position_without_a_magic_namespace():
    class UnnamespacedSnapshotMT5(SnapshotMT5):
        def positions_get(self):
            return (type("Position", (), {"ticket": 3, "symbol": "XAUUSDr", "type": 0, "volume": 0.1})(),)

    assert MT5BrokerClient(UnnamespacedSnapshotMT5(), magic=3101).snapshot()["positions"] == ()


def test_mt5_transport_builds_validated_bracket_request():
    mt5 = FakeMT5()
    result = MT5BrokerClient(mt5, magic=7).order_send({"pair": "XAUUSDr", "direction": "buy",
        "entry_price": 10.2, "volume": 0.1, "stop": 9.0, "target": 12.0})
    assert result["retcode"] == 10009
    assert mt5.request["price"] == 10.2 and mt5.request["magic"] == 7


def test_mt5_transport_has_explicit_modify_and_close_position_boundaries():
    mt5 = FakeMT5()
    client = MT5BrokerClient(mt5, magic=7)
    client.modify_position(position_id=12, pair="XAUUSDr", stop=9.5, target=12)
    assert mt5.request["action"] == mt5.TRADE_ACTION_SLTP and mt5.request["position"] == 12
    client.close_position(position_id=12, pair="XAUUSDr", direction="buy", volume=.1)
    assert mt5.request["action"] == mt5.TRADE_ACTION_DEAL
    assert mt5.request["type"] == mt5.ORDER_TYPE_SELL and mt5.request["price"] == 10.0


def test_management_transport_refuses_a_position_from_another_magic_namespace():
    mt5 = FakeMT5()
    mt5.positions_get = lambda symbol=None: [type("Position", (), {"ticket": 12, "symbol": "XAUUSDr",
        "type": 0, "volume": .1, "magic": 99})()]
    with pytest.raises(RuntimeError, match="magic number"):
        MT5BrokerClient(mt5, magic=7).close_position(position_id=12, pair="XAUUSDr", direction="buy", volume=.1)
