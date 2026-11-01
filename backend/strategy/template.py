"""The prompt the model receives (template v2): system + user, <= strategy.prompt.max_bytes.

  system  STRATEGY line, doctrine, FIELDS legend, answer format. Identical for
          every call of one strategy version, so the model server can keep it
          cached (only the user message is new each time).
  user    one JSON object:
            {"market":     outlook.market(...)        — now, session, ATR, trend per TF, ranges,
                                                         VWAPs, nearby levels,
             "candidates": [outlook.candidate(...)]   — C1, C2: level + history, approach,
                                                         rejection quality, exact trade, obstacles,
             "evidence":   {"E1": "[3m ago] H1 CHOCH up close beyond 4080.81", ...}}

Evidence ids map back to engine event ids (``Prompt.evidence_map``); the model may
only cite those (llm/contract.py), so every reason points at a stored fact.

Budget: when over ``max_bytes``, the least important evidence goes first,
then the farthest market levels; if it still does not fit, PromptTooLarge —
nothing is silently cut and no call is made.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from . import candidates as cands
from . import outlook


class PromptTooLarge(ValueError):
    pass


class NothingToAsk(ValueError):
    """Every candidate dropped out (e.g. R:R no longer acceptable at the rejection)."""


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    bytes: int
    sha: str                          # hash of both messages (journal: prompt identity)
    candidate_map: dict               # "C1" -> candidate key
    evidence_map: dict                # "E1" -> engine event id
    trimmed: dict                     # what was dropped to fit
    previews: dict                    # "C1" -> TradeIntent preview (exact prices) or None
    cite_fields: tuple = ("rejection", "level", "level.history", "approach", "trade", "obstacles",
                          "stretch_h1atr")         # candidate facts the model may cite (C1.<field>)


def system_message(strategy) -> str:
    return "\n".join([f"STRATEGY {strategy.id} v{strategy.version}: {strategy.name}", *strategy.doctrine,
                      "FIELDS:", *strategy.legend,
                      "Reply with ONE JSON object and nothing else:",
                      json.dumps(strategy.answer, separators=(",", ":"))])


def _avg_m1_volume(engine) -> float | None:
    """Average volume of the last 60 closed M1 bars (v1 used 12 M5 bars; config v2 has no M5)."""
    bars = list(engine.levels.m1)[-60:]
    vol = sum(b.volume for b in bars)
    return vol / len(bars) if bars and vol > 0 else None


def build(strategy, engine, runner, asks: list, now: int) -> Prompt:
    """Everything the model needs for the candidates in ``asks``, as of ``now``."""
    if strategy.rules["kind"] == "m1_probe_failure":
        from .scalp import build_prompt
        return build_prompt(strategy, engine, runner, asks, now)
    snap = engine.snapshot()
    price = engine._last_close
    atr = snap["atr"].get("M15") or 1.0
    views, cmap, previews = [], {}, {}
    avg_vol = _avg_m1_volume(engine)
    seen_trades = set()
    for c in asks:
        if len(cmap) >= strategy.rules["max_candidates"]:
            break
        intent = None
        if c.rejection is not None:
            intent, why = cands.trigger(strategy, c, c.rejection, now)
            if intent is None:                         # R:R no longer acceptable: not offered
                continue
            same = (c.side, intent.stop, intent.target)
            if same in seen_trades:                    # two levels, one candle, one identical trade
                continue
            seen_trades.add(same)
        label = f"C{len(cmap) + 1}"
        cmap[label], previews[label] = c.key, intent
        views.append(outlook.candidate(c, label, runner.history(c.level["id"], c.test_no, now), intent,
                                       snap, avg_vol))
    if not cmap:
        raise NothingToAsk("no candidate left to offer")
    market = outlook.market(engine, snap, price, now, {c.level["id"] for c in asks}, strategy.prompt["max_levels"])
    ev = runner.evidence(asks, price, atr, now, strategy.prompt["max_evidence"])
    system = system_message(strategy)
    trimmed = {"evidence": 0, "levels": 0}
    while True:
        user = json.dumps({"market": market, "candidates": views,
                           "evidence": {f"E{i + 1}": txt for i, (_, txt) in enumerate(ev)}},
                          separators=(",", ":"), ensure_ascii=False)
        size = len(system.encode()) + len(user.encode())
        if size <= strategy.prompt["max_bytes"]:
            break
        if len(ev) > 3:
            ev.pop()
            trimmed["evidence"] += 1
        elif len(market.get("levels", [])) > 1:
            market["levels"] = market["levels"][:-1]
            trimmed["levels"] += 1
        else:
            raise PromptTooLarge(f"prompt is {size} bytes > {strategy.prompt['max_bytes']} after trimming")
    emap = {f"E{i + 1}": eid for i, (eid, _) in enumerate(ev)}
    sha = hashlib.sha1((system + "\n" + user).encode()).hexdigest()[:16]
    return Prompt(system, user, size, sha, cmap, emap, trimmed, previews)
