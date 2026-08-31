"""Dependency-injected MT5 broker adapter with idempotent submit semantics."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Protocol


class BrokerClient(Protocol):
    def order_send(self, request: Mapping[str, Any]) -> Any: ...


class BrokerSubmissionError(RuntimeError):
    pass


class IdempotentBrokerAdapter:
    """Submit each logical order once; broker response is not treated as fill."""

    def __init__(self, client: BrokerClient) -> None:
        self.client = client
        self._submissions: dict[str, dict[str, Any]] = {}

    def submit(self, order: Mapping[str, Any]) -> dict[str, Any]:
        if not order.get("order_id") or not order.get("candidate_id"):
            raise BrokerSubmissionError("order_id and candidate_id are required")
        fingerprint = hashlib.sha256(json.dumps(dict(order), sort_keys=True, default=str).encode()).hexdigest()
        previous = self._submissions.get(str(order["order_id"]))
        if previous is not None:
            if previous["fingerprint"] != fingerprint:
                raise BrokerSubmissionError("order ID reused with different request")
            return dict(previous["result"])
        result = self.client.order_send(dict(order))
        if result is None:
            raise BrokerSubmissionError("broker returned no response")
        response = dict(result) if isinstance(result, Mapping) else {"raw": result}
        normalized = {"state": "SUBMITTED", "broker_response": response,
                      "order_id": str(order["order_id"]), "filled_volume": 0.0}
        self._submissions[str(order["order_id"])] = {"fingerprint": fingerprint, "result": normalized}
        return dict(normalized)
