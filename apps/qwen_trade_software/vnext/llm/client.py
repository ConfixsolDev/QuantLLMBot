"""Native constrained Qwen transport and prompt boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import request

from vnext.llm.arbitrator import Arbitration, arbitrate
from vnext.market.state import PairMarketState
from vnext.strategy.contracts import TradeCandidate


@dataclass(frozen=True, slots=True)
class QwenClient:
    endpoint: str = "http://127.0.0.1:11434/api/generate"
    model: str = "qwen"
    timeout_seconds: float = 30.0
    opener: Callable[..., Any] = request.urlopen

    def generate(self, prompt: str) -> Mapping[str, Any]:
        if not prompt or self.timeout_seconds <= 0:
            raise ValueError("Qwen request requires a prompt and positive timeout")
        body = json.dumps({"model": self.model, "prompt": prompt,
                           "stream": False, "format": "json"}).encode()
        req = request.Request(self.endpoint, data=body,
                              headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener(req, timeout=self.timeout_seconds) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError("Qwen transport failed") from exc
        raw = envelope.get("response") if isinstance(envelope, dict) else None
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise ValueError("Qwen response has no JSON content")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Qwen response is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Qwen response must be a JSON object")
        return parsed


def build_arbitration_prompt(state: PairMarketState, candidate: TradeCandidate,
                             story: Mapping[str, Any]) -> str:
    packet = {"task": "arbitrate_one_candidate", "allowed_decisions": ["APPROVE", "WAIT", "VETO", "NO_TRADE"],
              "state_hash": state.state_hash, "state": state.as_dict(),
              "candidate": candidate.as_dict(), "story": dict(story),
              "constraints": ["cite candidate_id for APPROVE", "do not invent geometry",
                              "do not size risk", "do not submit orders", "return JSON only"]}
    return json.dumps(packet, sort_keys=True, separators=(",", ":"))


def request_arbitration(client: QwenClient, state: PairMarketState,
                        candidate: TradeCandidate, story: Mapping[str, Any]) -> Arbitration:
    """Transport failure is represented as NO_TRADE rather than an exception."""
    try:
        response = client.generate(build_arbitration_prompt(state, candidate, story))
        return arbitrate(response, candidate)
    except (RuntimeError, ValueError) as exc:
        return Arbitration("NO_TRADE", None, str(exc), candidate.state_hash,
                           ("qwen_transport_or_parse_failure",))
