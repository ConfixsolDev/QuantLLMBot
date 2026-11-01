"""The decision pipeline, bar by bar — the same code for replay and the live demo.

For every closed M1 bar, after the structure engine has processed it::

    events --> StrategyRunner.observe --+--> asks: build outlook + prompt (<= 6 KB)
                                        |          --> decider (the model or take-all)
                                        |          --> journal the decision (always)
                                        |          --> approve / refuse candidates
                                        +--> intents (approved plan + M1 rejection) --> Executor.execute
                                        +--> closes  (time cap, rejection stalled)  --> Executor.close
    Executor.sync --> finished trades: result in R, journal, runner forgets them

The decider is passed in, so this file depends on neither the model nor MT5:
``llm.decider.LLMDecider()`` for lane B, ``llm.decider.take_all`` for lane A.

Time while the model thinks. The bar closed at ``now``; the answer arrives
``latency`` seconds later, and the entry window of the intent keeps running.
The executor is therefore called with the DECISION time, not the bar time:

  live        ``clock=time.time`` — the real wall clock after the answer
  replay      ``simulate_latency=True`` — bar time + the model's measured
              latency, so a slow model expires intents exactly as it would live
  baseline    neither (take-all has no latency)

``diagnostics`` keeps one row per decision (latency, entry window left at the
moment of the answer, outcome) for the day-by-day platform test.
"""

from __future__ import annotations

import hashlib
import time as _time

from strategy import template
from strategy.runner import make_runner


class Pipeline:
    def __init__(self, strategy, engine, decider, executor, journal, mode: str = "paper",
                 clock=None, simulate_latency: bool = False) -> None:
        self.s, self.engine, self.decide, self.ex, self.journal, self.mode = \
            strategy, engine, decider, executor, journal, mode
        self.clock, self.simulate_latency = clock, simulate_latency
        self.diagnostics: list[dict] = []
        self.runner = make_runner(strategy, engine)
        self.stats = {"bars": 0, "prompts": 0, "take": 0, "wait": 0, "invalid": 0, "intents": 0,
                      "filled": 0, "refused": 0, "closes": 0, "max_prompt_bytes": 0, "too_large": 0}

    def on_bar(self, bar, events, now: int) -> None:
        self.stats["bars"] += 1
        step = self.runner.observe(events, self.engine.snapshot, now)
        work = [(it, now) for it in step.intents]
        if step.asks:
            work += self._ask(step.asks, bar, now)
        for intent, t in work:
            self.stats["intents"] += 1
            out = self.ex.execute(intent, t)
            self.stats["filled" if out.status == "filled" else "refused"] += 1
        for key, reason in step.closes:
            if self.ex.close(key, reason, now):
                self.stats["closes"] += 1
        for t in self.ex.sync(now):
            self.runner.trade_closed(t["candidate_key"])

    def _ask(self, asks, bar, now: int) -> list:
        s = self.s
        try:
            prompt = template.build(s, self.engine, self.runner, asks, now)
        except template.NothingToAsk:
            for c in asks:
                self.runner.refuse(c.key, "no-candidate")
            return []
        except template.PromptTooLarge:
            self.stats["too_large"] += 1
            return []
        self.runner.mark_asked([c.key for c in asks])
        self.stats["prompts"] += 1
        self.stats["max_prompt_bytes"] = max(self.stats["max_prompt_bytes"], prompt.bytes)
        t0 = _time.monotonic()
        try:
            d = self.decide(prompt, s)
        except Exception as exc:                            # a decider bug must not stop trading/journaling
            from llm.contract import Verdict
            from llm.decider import Decision
            d = Decision(Verdict("invalid", None, None, 0, (), (), "", (f"decider error: {exc!r}",)), "error")
        v = d.verdict
        latency_s = d.latency_ms / 1000 if d.latency_ms is not None else _time.monotonic() - t0
        if self.clock is not None:
            decided = int(self.clock())                    # live: the real time of the answer
        elif self.simulate_latency:
            decided = now + int(round(latency_s))           # replay: bar time + model latency
        else:
            decided = now
        self.stats[v.action] += 1
        did = hashlib.sha1(f"{s.ref}|{prompt.sha}|{now}".encode()).hexdigest()[:16]
        self.journal.decision({
            "id": did, "time": now, "strategy_ref": s.ref, "prompt_sha": prompt.sha, "prompt_bytes": prompt.bytes,
            "candidates": {lbl: key for lbl, key in prompt.candidate_map.items()}, "evidence_map": prompt.evidence_map,
            "model": d.model, "model_digest": d.model_digest, "latency_ms": d.latency_ms, "raw_answer": d.raw,
            "action": v.action, "label": v.label, "candidate_key": v.candidate_key, "confidence": v.confidence,
            "cites": list(v.cites), "why": v.why, "errors": list(v.errors),
            "engine_config_hash": self.engine.config_hash, "mode": self.mode,
            "checks": {lbl: c.passed for lbl, key in prompt.candidate_map.items()
                       for c in asks if c.key == key and hasattr(c, "passed")}})
        intents = []
        window_left = None
        for c in asks:
            if v.action == "take" and c.key == v.candidate_key and c.key in prompt.candidate_map.values():
                preview = prompt.previews.get(v.label)
                if preview is not None:
                    window_left = preview.expires_at - decided
                it = self.runner.approve(c.key, did, decided)
                if it is not None:
                    intents.append((it, decided))
            else:
                self.runner.refuse(c.key, did)
        self.diagnostics.append({"id": did, "time": now, "action": v.action, "label": v.label,
                                 "latency_s": round(latency_s, 2), "errors": list(v.errors),
                                 "prompt_bytes": prompt.bytes, "trimmed": prompt.trimmed,
                                 "window_left_s": window_left, "intent": bool(intents)})
        return intents
