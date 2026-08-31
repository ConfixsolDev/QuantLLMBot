import pytest

from vnext.execution.broker import BrokerSubmissionError, IdempotentBrokerAdapter
from vnext.execution.mt5 import MT5BrokerClient


class FakeClient:
    def __init__(self): self.calls = []
    def order_send(self, request): self.calls.append(dict(request)); return {"retcode": "accepted"}


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


class FakeMT5:
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 2
    ORDER_TYPE_SELL = 3
    ORDER_TIME_GTC = 4
    ORDER_FILLING_IOC = 5
    class Tick: bid = 10.0; ask = 10.2
    def symbol_info_tick(self, symbol): return self.Tick()
    def order_send(self, request): self.request = request; return {"retcode": 10009}


def test_mt5_transport_builds_validated_bracket_request():
    mt5 = FakeMT5()
    result = MT5BrokerClient(mt5, magic=7).order_send({"pair": "XAUUSDr", "direction": "buy",
        "volume": 0.1, "stop": 9.0, "target": 12.0})
    assert result["retcode"] == 10009
    assert mt5.request["price"] == 10.2 and mt5.request["magic"] == 7
