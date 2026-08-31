import pytest

from vnext.execution.broker import BrokerSubmissionError, IdempotentBrokerAdapter


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
