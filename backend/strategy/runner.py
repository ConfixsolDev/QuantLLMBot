"""StrategyRunner: follows the engine's event stream for ONE strategy.

Feed it every bar's events (live or replay — same code). Each call returns:

  asks     candidates that need a Qwen decision now (a plan was armed)
  intents  TradeIntents ready for the executor (approved plan + M1 rejection)
  closes   (candidate key, reason) — an open trade's idea failed and must be
           closed, e.g. the rejection STALLED (no 0.5 ATR move in 3 M1 bars)
  ended    candidates whose test finished without a trade (for the journal)

Qwen answers asynchronously: call ``approve`` / ``refuse`` when it does. If
the M1 rejection already happened while Qwen was thinking, ``approve`` returns
the intent at once — as long as the entry window is still open.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from trading.intent import TradeIntent

from . import candidates as cands
from .outlook import EVIDENCE_KINDS, brief


@dataclass
class Step:
    asks: list = field(default_factory=list)
    intents: list = field(default_factory=list)
    closes: list = field(default_factory=list)
    ended: list = field(default_factory=list)
    skipped: list = field(default_factory=list)          # (level test id, reason) — why no candidate


class StrategyRunner:
    def __init__(self, strategy, session_of: Callable[[int], str | None], history: int = 400) -> None:
        self.s = strategy
        self.session_of = session_of
        self.recent: deque[tuple[str, str, int]] = deque(maxlen=history)   # (event id, text, time)
        self.texts: dict[str, str] = {}
        self.by_level: dict[str, list[str]] = {}       # level id -> its evidence event ids
        self.active: dict[str, cands.Candidate] = {}   # key -> candidate
        self.traded: dict[str, cands.Candidate] = {}   # key -> candidate with an intent (until closed)

    # ------------------------------------------------------------------ events
    def observe(self, events: list, snapshot_fn: Callable[[], dict], now: int) -> Step:
        step, snap = Step(), None
        for ev in events:
            e = ev if isinstance(ev, dict) else ev.as_dict()
            k, d = e["kind"], e["data"]
            if k in EVIDENCE_KINDS:
                txt = brief(e)
                if txt:
                    self.recent.append((e["id"], txt, e["available_at"]))
                    self.texts[e["id"]] = txt
                    if k.startswith("level_"):
                        self.by_level.setdefault(d["level"]["id"], []).append(e["id"])
            if k == "level_test":
                snap = snap or snapshot_fn()
                c, why = cands.plan(self.s, e, snap, self.session_of(e["time"]))
                if c is None:
                    step.skipped.append((e["id"], why))
                    continue
                c.evidence = list(self.by_level.get(d["level"]["id"], []))[-4:]
                self.active[c.key] = c
                step.asks.append(c)
            elif k == "level_rejection":
                c = self.active.get(f"{d['level']['id']}:{d['test_no']}")
                if c is None:
                    continue
                c.rejection = e
                if c.status == "approved":
                    self._fire(c, e["available_at"], step)
            elif k == "level_followthrough":
                key = f"{d['level']['id']}:{d['test_no']}"
                if key in self.traded and d["result"] == "stalled" and self.s.rules["close_on_stalled_followthrough"]:
                    step.closes.append((key, "rejection stalled: no 0.5 ATR move in 3 M1 bars"))
            elif k in ("level_held", "level_broken", "level_expired"):
                key = f"{d['level']['id']}:{d.get('test_no') or d.get('during_test')}"
                c = self.active.pop(key, None)
                if c is not None and c.status != "triggered":
                    step.ended.append(c)
        for key, c in list(self.active.items()):                 # time runs out
            if c.status != "triggered" and now >= c.expires_at:
                step.ended.append(self.active.pop(key))
        return step

    # ------------------------------------------------------------------ decisions
    def approve(self, key: str, decision_id: str, now: int) -> TradeIntent | None:
        c = self.active.get(key)
        if c is None or c.status not in ("new", "asked"):
            return None
        c.status, c.decision_id = "approved", decision_id
        if c.rejection is not None:                               # rejection came while Qwen thought
            step = Step()
            self._fire(c, now, step)
            return step.intents[0] if step.intents else None
        return None

    def refuse(self, key: str, decision_id: str) -> None:
        c = self.active.get(key)
        if c is not None and c.status in ("new", "asked"):
            c.status, c.decision_id = "refused", decision_id

    def mark_asked(self, keys: list[str]) -> None:
        for k in keys:
            if k in self.active and self.active[k].status == "new":
                self.active[k].status = "asked"

    def trade_closed(self, key: str) -> None:
        self.traded.pop(key, None)

    def _fire(self, c: cands.Candidate, now: int, step: Step) -> None:
        intent, why = cands.trigger(self.s, c, c.rejection, now)
        if intent is None or now > intent.expires_at:
            c.status = "expired"
            step.skipped.append((c.key, why if intent is None else "entry window passed"))
            return
        c.status = "triggered"
        self.traded[c.key] = c
        step.intents.append(intent)

    # ------------------------------------------------------------------ evidence for the prompt
    def evidence(self, asks: list[cands.Candidate], limit: int) -> list[tuple[str, str]]:
        """Candidate-specific events first, then the most recent market events."""
        out, seen = [], set()
        for c in asks:
            for eid in c.evidence:
                if eid not in seen and eid in self.texts:
                    out.append((eid, self.texts[eid]))
                    seen.add(eid)
        for eid, txt, _ in reversed(self.recent):
            if len(out) >= limit:
                break
            if eid not in seen:
                out.append((eid, txt))
                seen.add(eid)
        return out[:limit]
