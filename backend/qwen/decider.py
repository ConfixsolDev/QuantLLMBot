"""Deciders: who answers "take C1 / wait" for a prompt.

    QwenDecider   asks the local Qwen and checks the answer with contract.check
    take_all      lane A of the comparison: approve the best candidate every time
                  (the yardstick Qwen has to beat — V3 Part F, "Qwen earns its place")

A decider is called as ``decider(prompt, strategy) -> Decision`` and never
raises for a bad answer: an unreachable server or a broken answer is a
Decision with action "invalid" and the reason, so nothing trades on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import QwenClient, QwenError
from .contract import Verdict, check


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    model: str
    model_digest: str | None = None
    latency_ms: int | None = None
    raw: str = ""
    meta: dict = field(default_factory=dict)


class QwenDecider:
    def __init__(self, client: QwenClient | None = None) -> None:
        self.client = client or QwenClient()

    def __call__(self, prompt, strategy) -> Decision:
        try:
            reply = self.client.ask(prompt.system, prompt.user)
        except QwenError as exc:
            v = Verdict("invalid", None, None, 0, (), (), "", (f"Qwen unreachable: {exc}",))
            return Decision(v, self.client.s.model)
        v = check(reply.text, prompt, strategy.rules["min_confidence"])
        return Decision(v, reply.model, reply.model_digest, reply.latency_ms, reply.text,
                        {"prompt_tokens": reply.prompt_tokens, "output_tokens": reply.output_tokens})


def take_all(prompt, strategy) -> Decision:
    """Lane A: always take the first (code-ranked) candidate."""
    label = next(iter(prompt.candidate_map))
    v = Verdict("take", label, prompt.candidate_map[label], 100, (), (), "lane A: take every candidate")
    return Decision(v, "take-all")
