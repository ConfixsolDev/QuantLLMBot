from vnext.execution.broker import IdempotentBrokerAdapter, BrokerSubmissionError


class Client:
    def __init__(self): self.calls = 0
    def order_send(self, request): self.calls += 1; return {"broker_order_id": "b1"}


class Store:
    def __init__(self): self.rows = {}
    def get(self, order_id): return self.rows.get(order_id)
    def put(self, order_id, fingerprint, result): self.rows[order_id] = {"fingerprint": fingerprint, "result": result}


class ClaimStore(Store):
    def claim(self, order_id, fingerprint):
        if order_id in self.rows:
            return self.rows[order_id]
        self.rows[order_id] = {"fingerprint": fingerprint, "result": {}, "status": "RESERVED"}
        return self.rows[order_id]
    def complete(self, order_id, fingerprint, result):
        self.rows[order_id] = {"fingerprint": fingerprint, "result": result, "status": "SUBMITTED"}
    def release(self, order_id, fingerprint): self.rows.pop(order_id, None)


class AcquiredClaimStore(ClaimStore):
    def claim(self, order_id, fingerprint):
        if order_id in self.rows:
            return self.rows[order_id]
        self.rows[order_id] = {
            "fingerprint": fingerprint, "result": {}, "status": "RESERVED", "claimed": True,
        }
        return self.rows[order_id]


def test_durable_submission_store_prevents_restart_duplicate():
    client, store = Client(), Store()
    order = {"order_id": "o1", "candidate_id": "c1", "volume": 1}
    assert IdempotentBrokerAdapter(client, submission_store=store).submit(order)["state"] == "SUBMITTED"
    assert IdempotentBrokerAdapter(client, submission_store=store).submit(order)["state"] == "SUBMITTED"
    assert client.calls == 1


def test_durable_submission_store_rejects_collision():
    client, store = Client(), Store()
    adapter = IdempotentBrokerAdapter(client, submission_store=store)
    adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 1})
    try:
        adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 2})
    except BrokerSubmissionError:
        return
    raise AssertionError("order ID collision must be rejected")


def test_claim_store_fails_closed_when_submission_is_already_reserved():
    client, store = Client(), ClaimStore()
    adapter = IdempotentBrokerAdapter(client, submission_store=store)
    try:
        adapter.submit({"order_id": "o1", "candidate_id": "c1", "volume": 1})
    except BrokerSubmissionError:
        pass
    else:
        raise AssertionError("a reserved order must not be submitted without reconciliation")
    assert client.calls == 0


def test_newly_acquired_durable_claim_submits_once_and_caches_result():
    client, store = Client(), AcquiredClaimStore()
    order = {"order_id": "o1", "candidate_id": "c1", "volume": 1}
    assert IdempotentBrokerAdapter(client, submission_store=store).submit(order)["state"] == "SUBMITTED"
    assert IdempotentBrokerAdapter(client, submission_store=store).submit(order)["state"] == "SUBMITTED"
    assert client.calls == 1
