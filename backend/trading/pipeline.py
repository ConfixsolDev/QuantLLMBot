"""The decision pipeline, bar by bar — the same code for replay and the live demo.

For every closed M1 bar, after the structure engine has processed it::

    events --> StrategyRunner.observe --+--> asks: build outlook + prompt (<= 6 KB)
                                        |          --> decider (Qwen or take-all)
                                        |          --> journal the decision (always)
                                        |          --> approve / refuse candidates
                                        +--> intents (approved plan + M1 rejection) --> Executor.execute
                                        +--> closes  (e.g. rejection stalled)       --> Executor.close
    Executor.sync --> finished trades: result in R, journal, runner forgets them

The decider is passed in, so this file depends on neither Qwen nor MT5:
``qwen.decider.QwenDecider()`` for lane B, ``qwen.decider.take_all`` for lane A.
"""

from __future__ import annotations

import hashlib

from strategy import outlook as outlook_mod
from strategy import template
from strategy.runner import StrategyRunner


class Pipeline:
    def __init__(self, strategy, engine, decider, executor, journal, mode: str = "paper") -> None:
        self.s, self.engine, self.decide, self.ex, self.journal, self.mode = \
            strategy, engine, decider, executor, journal, mode
        self.runner = StrategyRunner(strategy, engine._session_name)
        self.stats = {"bars": 0, "prompts": 0, "take": 0, "wait": 0, "invalid": 0, "intents": 0,
                      "filled": 0, "refused": 0, "closes": 0, "max_prompt_bytes": 0, "too_large": 0}

    def on_bar(self, bar, events, now: int) -> None:
        self.stats["bars"] += 1
        step = self.runner.observe(events, self.engine.snapshot, now)
        intents = list(step.intents)
        if step.asks:
            intents += self._ask(step.asks, bar, now)
        for intent in intents:
            self.stats["intents"] += 1
            out = self.ex.execute(intent, now)
            self.stats["filled" if out.status == "filled" else "refused"] += 1
        for key, reason in step.closes:
            if self.ex.close(key, reason, now):
                self.stats["closes"] += 1
        for t in self.ex.sync(now):
            self.runner.trade_closed(t["candidate_key"])

    def _ask(self, asks, bar, now: int) -> list:
        s = self.s
        snap = self.engine.snapshot()
        ol = outlook_mod.build(snap, bar.close, self.engine._session_name(bar.time), s.prompt["max_levels"])
        try:
            prompt = template.build(s, ol, asks, self.runner.evidence(asks, s.prompt["max_evidence"]))
        except template.PromptTooLarge:
            self.stats["too_large"] += 1
            return []
        self.runner.mark_asked([c.key for c in asks])
        self.stats["prompts"] += 1
        self.stats["max_prompt_bytes"] = max(self.stats["max_prompt_bytes"], prompt.bytes)
        d = self.decide(prompt, s)
        v = d.verdict
        self.stats[v.action] += 1
        did = hashlib.sha1(f"{s.ref}|{prompt.sha}|{now}".encode()).hexdigest()[:16]
        self.journal.decision({
            "id": did, "time": now, "strategy_ref": s.ref, "prompt_sha": prompt.sha, "prompt_bytes": prompt.bytes,
            "candidates": {lbl: key for lbl, key in prompt.candidate_map.items()}, "evidence_map": prompt.evidence_map,
            "model": d.model, "model_digest": d.model_digest, "latency_ms": d.latency_ms, "raw_answer": d.raw,
            "action": v.action, "label": v.label, "candidate_key": v.candidate_key, "confidence": v.confidence,
            "cites": list(v.cites), "why": v.why, "errors": list(v.errors),
            "engine_config_hash": self.engine.config_hash, "mode": self.mode})
        intents = []
        for c in asks:
            if v.action == "take" and c.key == v.candidate_key:
                it = self.runner.approve(c.key, did, now)
                if it is not None:
                    intents.append(it)
            else:
                self.runner.refuse(c.key, did)
        return intents
