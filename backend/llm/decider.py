"""Deciders: who answers "take C1 / wait" for a prompt.

    LLMDecider    asks the local model (Bonsai 2 27B on llama-server, client.py),
                  grammar-constrained to the answer contract, then checks the
                  answer with contract.check
    take_all      lane A of the comparison: take every candidate (the yardstick
                  the model has to beat — V3 Part F, "the model earns its place")

A decider is called as ``decider(prompt, strategy) -> Decision`` and never
raises: an unreachable server or a broken answer is a Decision with action
"invalid" and the reason, so nothing trades on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .client import LLMClient, LLMError
from .contract import Verdict, answer_schema, check


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    model: str
    model_digest: str | None = None
    latency_ms: int | None = None
    raw: str = ""
    meta: dict = field(default_factory=dict)


class LLMDecider:
    def __init__(self, client: LLMClient | None = None) -> None:
        self.client = client or LLMClient()

    def __call__(self, prompt, strategy) -> Decision:
        try:
            reply = self.client.ask(prompt.system, prompt.user, answer_schema(prompt))
        except LLMError as exc:
            v = Verdict("invalid", None, None, 0, (), (), "", (f"model unreachable / no answer: {exc}",))
            return Decision(v, self.client.s.model)
        v = check(reply.text, prompt, strategy.rules["min_confidence"])
        return Decision(v, reply.model, reply.model_digest, reply.latency_ms, reply.text,
                        {"prompt_tokens": reply.prompt_tokens, "output_tokens": reply.output_tokens,
                         "reasoning_chars": len(reply.reasoning)})


def take_all(prompt, strategy) -> Decision:
    """Lane A: always take the first (code-ranked) candidate."""
    label = next(iter(prompt.candidate_map))
    v = Verdict("take", label, prompt.candidate_map[label], 100, (), (), "lane A: take every candidate")
    return Decision(v, "take-all")
