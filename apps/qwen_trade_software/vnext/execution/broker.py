"""Dependency-injected MT5 broker adapter with idempotent submit semantics."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Protocol


class BrokerClient(Protocol):
    def order_send(self, request: Mapping[str, Any]) -> Any: ...


class SubmissionStore(Protocol):
    def get(self, order_id: str) -> dict[str, Any] | None: ...
    def put(self, order_id: str, fingerprint: str, result: dict[str, Any]) -> None: ...


class BrokerSubmissionError(RuntimeError):
    pass


class IdempotentBrokerAdapter:
    """Submit each logical order once; broker response is not treated as fill."""

    def __init__(self, client: BrokerClient, *, submission_store: SubmissionStore | None = None) -> None:
        self.client = client
        self.submission_store = submission_store
        self._submissions: dict[str, dict[str, Any]] = {}

    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]:
        if not order.get("order_id") or not order.get("candidate_id"):
            raise BrokerSubmissionError("order_id and candidate_id are required")
        fingerprint = hashlib.sha256(json.dumps(dict(order), sort_keys=True, default=str).encode()).hexdigest()
        order_id = str(order["order_id"])
        previous = self.submission_store.get(order_id) if self.submission_store else self._submissions.get(order_id)
        claimed = False
        if self.submission_store and hasattr(self.submission_store, "claim"):
            previous = self.submission_store.claim(order_id, fingerprint)
            claimed = previous is not None and previous.get("status") == "RESERVED" and not previous.get("result")
        if previous is not None:
            if previous["fingerprint"] != fingerprint:
                raise BrokerSubmissionError("order ID reused with different request")
            if claimed:
                raise BrokerSubmissionError("order submission is reserved; broker reconciliation required")
            return dict(previous["result"])
        result = self.client.order_send(dict(order))
        if result is None:
            raise BrokerSubmissionError("broker returned no response")
        response = dict(result) if isinstance(result, Mapping) else {"raw": result}
        retcode = response.get("retcode")
        if isinstance(retcode, int) and retcode not in {10008, 10009, 10010}:
            if self.submission_store and hasattr(self.submission_store, "release"):
                self.submission_store.release(order_id, fingerprint)
            raise BrokerSubmissionError(f"broker rejected order: retcode={retcode}")
        normalized = {"state": "SUBMITTED", "broker_response": response,
                      "order_id": str(order["order_id"]), "filled_volume": 0.0}
        record = {"fingerprint": fingerprint, "result": normalized}
        if self.submission_store:
            if hasattr(self.submission_store, "complete"):
                self.submission_store.complete(order_id, fingerprint, normalized)
            else:
                self.submission_store.put(order_id, fingerprint, normalized)
        else:
            self._submissions[order_id] = record
        return dict(normalized)
