"""StrategyRunner: follows the engine's event stream for ONE strategy.

Feed it every bar's events (live or replay — same code). Each call returns:

  asks     candidates that need a Qwen decision NOW
  intents  TradeIntents ready for the executor
  closes   (candidate key, reason) — an open trade's idea failed, e.g. the
           rejection STALLED (no 0.5 ATR move in 3 M1 bars)
  ended    candidates whose test finished without a trade
  skipped  (event id, reason) — why a level test did not become a candidate

When Qwen is asked depends on ``rules.decision_point``:

  "rejection" (v2)  a level test arms a candidate silently; Qwen is asked when
                    the M1 rejection happens, sees that candle, and an approval
                    becomes an intent at once (entry window: a few M1 bars)
  "test"            Qwen is asked when price reaches the level; an approval
                    waits for the rejection (v1 behaviour)

The runner also keeps what the prompt needs: each level's history (earlier
tests: rejected? moved or stalled? held?) and a curated set of recent events
(``evidence``) — structure breaks per timeframe, liquidity near price,
patterns, VWAP band rejects of the day/week VWAP.
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
    skipped: list = field(default_factory=list)


@dataclass
class Ev:
    id: str
    kind: str
    tf: str
    time: int                 # available_at
    text: str
    price: float | None       # a price the event is about (for "near price" selection)
    level_id: str | None = None


def _price_of(e: dict) -> float | None:
    d = e["data"]
    if e["kind"] in ("bos", "choch"):
        return d["level"]
    if "levels" in d and d["levels"]:
        return d["levels"][0]["price"]
    if "level" in d and isinstance(d["level"], dict):
        return d["level"]["price"]
    if "neckline" in d:
        return d["neckline"]
    return None


class StrategyRunner:
    def __init__(self, strategy, session_of: Callable[[int], str | None], history: int = 600) -> None:
        self.s = strategy
        self.session_of = session_of
        self.at_rejection = strategy.rules["decision_point"] == "rejection"
        self.recent: deque[Ev] = deque(maxlen=history)
        self.level_tests: dict[str, dict[int, dict]] = {}   # level id -> test no -> {time, rej, ft, held, broken}
        self.active: dict[str, cands.Candidate] = {}
        self.traded: dict[str, cands.Candidate] = {}

    # ------------------------------------------------------------------ events
    def observe(self, events: list, snapshot_fn: Callable[[], dict], now: int) -> Step:
        step, snap = Step(), None
        for ev in events:
            e = ev if isinstance(ev, dict) else ev.as_dict()
            k, d = e["kind"], e["data"]
            if k in EVIDENCE_KINDS:
                txt = brief(e)
                if txt:
                    lid = d["level"]["id"] if k.startswith("level_") else None
                    self.recent.append(Ev(e["id"], k, e["tf"], e["available_at"], txt, _price_of(e), lid))
            self._history(e)
            if k == "level_test":
                snap = snap or snapshot_fn()
                c, why = cands.plan(self.s, e, snap, self.session_of(e["time"]))
                if c is None:
                    step.skipped.append((e["id"], why))
                    continue
                c.test_event = e
                self.active[c.key] = c
                if not self.at_rejection:
                    step.asks.append(c)
            elif k == "level_rejection":
                c = self.active.get(f"{d['level']['id']}:{d['test_no']}")
                if c is None or c.rejection is not None:
                    continue
                c.rejection = e
                if c.status == "approved":
                    self._fire(c, e["available_at"], step)
                elif self.at_rejection and c.status == "new":
                    step.asks.append(c)
            elif k == "level_followthrough":
                key = f"{d['level']['id']}:{d['test_no']}"
                if key in self.traded and d["result"] == "stalled" and self.s.rules["close_on_stalled_followthrough"]:
                    step.closes.append((key, "rejection stalled: no 0.5 ATR move in 3 M1 bars"))
            elif k in ("level_held", "level_broken", "level_expired"):
                key = f"{d['level']['id']}:{d.get('test_no') or d.get('during_test')}"
                c = self.active.pop(key, None)
                if c is not None and c.status != "triggered":
                    step.ended.append(c)
        for key, c in list(self.active.items()):
            if c.status != "triggered" and now >= c.expires_at:
                step.ended.append(self.active.pop(key))
        return step

    def _history(self, e: dict) -> None:
        k, d = e["kind"], e["data"]
        if not k.startswith("level_") or k in ("level_created", "level_pattern", "level_expired"):
            return
        tests = self.level_tests.setdefault(d["level"]["id"], {})
        if k == "level_test":
            tests[d["test_no"]] = {"time": e["time"]}
        elif k == "level_rejection" and d["test_no"] in tests:
            tests[d["test_no"]]["rej"] = d["pierce_atr"]
        elif k == "level_followthrough" and d["test_no"] in tests:
            tests[d["test_no"]]["ft"] = d["result"]
        elif k == "level_held" and d["test_no"] in tests:
            tests[d["test_no"]]["held"] = True
        elif k == "level_broken" and d.get("during_test") in tests:
            tests[d["during_test"]]["held"] = False

    def history(self, level_id: str, before_test: int, now: int) -> list[str]:
        """Earlier tests of a level in words, e.g. 't1 95m ago: rejected (poke 0.21), moved, held'."""
        out = []
        for n, t in sorted(self.level_tests.get(level_id, {}).items()):
            if n >= before_test:
                break
            parts = [f"rejected (poke {t['rej']})" if "rej" in t else "no rejection"]
            if "ft" in t:
                parts.append(t["ft"])
            parts.append({True: "held", False: "broke"}.get(t.get("held"), "unresolved"))
            out.append(f"t{n} {age(now - t['time'])} ago: {', '.join(parts)}")
        return out

    # ------------------------------------------------------------------ decisions
    def approve(self, key: str, decision_id: str, now: int) -> TradeIntent | None:
        c = self.active.get(key)
        if c is None or c.status not in ("new", "asked"):
            return None
        c.status, c.decision_id = "approved", decision_id
        if c.rejection is not None:
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
    def evidence(self, asks: list, price: float, atr: float, now: int, limit: int) -> list[tuple[str, str]]:
        """Curated evidence, most useful first, each line prefixed with its age.

        1. M1 patterns that formed AT the candidate's level (its tests and
           rejections are already in the candidate itself, not repeated here)
        2. the latest BOS/CHoCH on H4, H1, M30, M15 (one each) and on M5 (two)
        3. liquidity events (sweeps, false breaks, taken) within 3 ATR of price, last 3 h
        4. M1 patterns / patterns at a level, last hour; day/week VWAP band rejects, last 30 min
        5. anything else recent, to fill the budget
        """
        picked: list[Ev] = []
        seen: set[str] = set()

        texts: set[str] = set()

        def add(ev: Ev) -> None:
            body = ev.text.split(" ", 1)[1]
            if ev.id not in seen and body not in texts:   # same fact twice (e.g. a pattern) = once
                picked.append(ev)
                seen.add(ev.id)
                texts.add(body)
        levels = {c.level["id"] for c in asks}
        for ev in self.recent:
            if ev.level_id in levels and ev.kind == "level_pattern" and ev.time >= now - 3600:
                add(ev)
        rec = list(self.recent)[::-1]
        need = {"H4": 1, "H1": 1, "M30": 1, "M15": 1, "M5": 2}
        for ev in rec:
            if ev.kind in ("bos", "choch") and need.get(ev.tf, 0) > 0:
                need[ev.tf] -= 1
                add(ev)
        for ev in rec:
            if ev.kind in ("liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken") \
                    and ev.time >= now - 3 * 3600 and ev.price is not None and abs(ev.price - price) <= 3 * atr:
                add(ev)
        for ev in rec:
            if ev.kind in ("pattern_confirmed", "level_pattern") and ev.time >= now - 3600:
                add(ev)
            if ev.kind == "vwap_band_reject" and ev.time >= now - 1800 and ("VWAP day" in ev.text or "VWAP week" in ev.text):
                add(ev)
        for ev in rec:
            if len(picked) >= limit:
                break
            if ev.kind not in ("vwap_band_reject", "level_test") and ev.level_id not in levels \
                    and ev.time >= now - 6 * 3600:
                add(ev)
        return [(ev.id, f"[{age(now - ev.time)} ago] {ev.text.split(' ', 1)[1]}") for ev in picked[:limit]]


def age(seconds: int) -> str:
    """Readable age: 7m, 3h, 4d (huge minute counts are hard for a model to compare)."""
    m = max(0, seconds) // 60
    return f"{m}m" if m < 120 else f"{m // 60}h" if m < 72 * 60 else f"{m // 1440}d"
