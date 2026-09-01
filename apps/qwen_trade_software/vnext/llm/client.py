"""Native constrained Qwen transport and prompt boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import request

from vnext.llm.arbitrator import Arbitration, arbitrate
from vnext.market.state import PairMarketState
from vnext.strategy.contracts import TradeCandidate


ARBITRATION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["APPROVE", "WAIT", "VETO", "NO_TRADE"]},
        "candidate_id": {"type": "string"},
        "reason": {"type": "string"},
        "state_hash": {"type": "string"},
    },
    "required": ["decision", "candidate_id", "reason", "state_hash"],
    "additionalProperties": False,
}


def arbitration_response_schema(candidate: TradeCandidate) -> dict[str, Any]:
    """Bind transport output to the immutable candidate identity it arbitrates."""
    return {
        **ARBITRATION_RESPONSE_SCHEMA,
        "properties": {
            **ARBITRATION_RESPONSE_SCHEMA["properties"],
            "candidate_id": {"type": "string", "const": candidate.candidate_id},
            "state_hash": {"type": "string", "const": candidate.state_hash},
        },
    }


@dataclass(frozen=True, slots=True)
class QwenClient:
    endpoint: str = "http://127.0.0.1:11434/api/generate"
    model: str = "qwen"
    timeout_seconds: float = 30.0
    context_window: int = 8192
    opener: Callable[..., Any] = request.urlopen

    def generate(self, prompt: str, *, response_schema: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if not prompt or self.timeout_seconds <= 0 or self.context_window <= 0:
            raise ValueError("Qwen request requires a prompt and positive timeout")
        body = json.dumps({"model": self.model, "prompt": prompt,
                           "stream": False, "format": dict(response_schema or ARBITRATION_RESPONSE_SCHEMA),
                           "options": {"num_ctx": self.context_window}}).encode()
        req = request.Request(self.endpoint, data=body,
                              headers={"Content-Type": "application/json"}, method="POST")
        try:
            with self.opener(req, timeout=self.timeout_seconds) as response:
                envelope = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Qwen transport failed ({type(exc).__name__})") from exc
        raw = envelope.get("response") if isinstance(envelope, dict) else None
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise ValueError("Qwen response has no JSON content")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            head = " ".join(raw[:160].split())
            tail = " ".join(raw[-80:].split()) if len(raw) > 160 else ""
            raise ValueError(
                f"Qwen response is not valid JSON (length={len(raw)}, head={head!r}, tail={tail!r})"
            ) from exc
        if not isinstance(parsed, dict):
            raise ValueError("Qwen response must be a JSON object")
        return parsed


def build_arbitration_prompt(state: PairMarketState, candidate: TradeCandidate,
                             story: Mapping[str, Any]) -> str:
    if story.get("schema_version") != "STORY_V1":
        raise ValueError("Qwen arbitration requires a bounded STORY_V1 packet")
    feedback = candidate.metadata.get("qwen_feedback")
    if not isinstance(feedback, Mapping) or not feedback:
        raise ValueError("Qwen arbitration requires strategy-owned feedback")
    _validate_strategy_packet(story, feedback)
    packet = {"task": "arbitrate_one_candidate",
              "instruction": "Return exactly the output_contract JSON fields. Do not return a task, command, question, data, metadata, or wrapper object.",
              "allowed_decisions": ["APPROVE", "WAIT", "VETO", "NO_TRADE"],
              "state_integrity": {"pair": state.pair, "time_frontier_utc": state.time_frontier_utc.isoformat(),
                                  "state_hash": state.state_hash},
              "candidate": candidate.as_dict(),
              "strategy_package": {"story": dict(story), "feedback": dict(feedback)},
              "output_contract": {"decision": "APPROVE|WAIT|VETO|NO_TRADE",
                                  "candidate_id": candidate.candidate_id,
                                  "reason": "short evidence-based reason",
                                  "state_hash": state.state_hash},
              "constraints": ["cite candidate_id for APPROVE", "do not invent geometry",
                              "do not size risk", "do not submit orders", "return JSON only"]}
    return json.dumps(packet, sort_keys=True, separators=(",", ":"))


def _validate_strategy_packet(story: Mapping[str, Any], feedback: Mapping[str, Any]) -> None:
    """Reject a packet whose declared strategy focus does not match its story."""
    focus = feedback.get("focus")
    request = story.get("request")
    if not isinstance(focus, Mapping) or not isinstance(request, Mapping):
        raise ValueError("Qwen arbitration requires strategy focus and story request")
    for name in ("context_timeframes", "setup_timeframes", "execution_timeframes", "excluded_timeframes", "focus_tags"):
        if tuple(focus.get(name, ())) != tuple(request.get(name, ())):
            raise ValueError(f"strategy feedback and story disagree on {name}")
    facts = story.get("facts")
    timeframes = facts.get("timeframes", {}) if isinstance(facts, Mapping) else {}
    excluded = set(str(value) for value in focus.get("excluded_timeframes", ()))
    if not isinstance(timeframes, Mapping) or excluded.intersection(timeframes):
        raise ValueError("story contains a strategy-excluded timeframe")


def request_arbitration(client: QwenClient, state: PairMarketState,
                        candidate: TradeCandidate, story: Mapping[str, Any]) -> Arbitration:
    """Transport failure is represented as NO_TRADE rather than an exception."""
    try:
        response = client.generate(
            build_arbitration_prompt(state, candidate, story),
            response_schema=arbitration_response_schema(candidate),
        )
        return arbitrate(response, candidate)
    except (RuntimeError, ValueError) as exc:
        return Arbitration("NO_TRADE", None, str(exc), candidate.state_hash,
                           ("qwen_transport_or_parse_failure",))
