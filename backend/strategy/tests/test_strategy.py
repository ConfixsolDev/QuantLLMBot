"""Strategy package tests (python -m pytest strategy/tests -q, from backend/)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from strategy import StrategyError, load  # noqa: E402
from strategy import candidates as cands  # noqa: E402
from strategy import template  # noqa: E402
from strategy.model import parse  # noqa: E402
from strategy.runner import StrategyRunner  # noqa: E402

S = load("htf_level_m1_rejection")
T0 = 1_785_000_000 - 1_785_000_000 % 60
LEVEL = {"id": "Vabc", "price": 2000.0, "side": "high", "sources": ["H1 swing high", "LONDON high"],
         "time": T0 - 7200, "created_at": T0 - 3600, "tests": 2, "held": 1}
SNAP = {"htf_levels": [LEVEL, {"id": "Vsup", "price": 1990.0, "side": "low", "sources": ["ASIA low"],
                               "tests": 0}],
        "atr": {"M15": 5.0, "H1": 9.0}, "trend": {}, "vwap": {}, "as_of": T0}


def ev(kind, t, data, eid=None):
    return {"id": eid or f"{kind}{t}", "kind": kind, "tf": "M1", "time": t, "available_at": t + 60, "data": data}


def level_test_event(test_no=2, t=T0):
    return ev("level_test", t, {"level": {**LEVEL, "tests": test_no}, "test_no": test_no, "atr": 5.0,
                                "approach": "drift", "stretch_h1_atr": 3.1, "trend": {"H1": "up"},
                                "candle": {"time": t, "open": 1999, "high": 2000.1, "low": 1998.5, "close": 1999.2}})


def rejection(t=T0 + 60, high=2001.0, close=1999.0, test_no=2):
    return ev("level_rejection", t, {"level": LEVEL, "test_no": test_no, "pierce_atr": 0.2, "bars_after_touch": 1,
                                     "candle": {"time": t, "open": 1999.5, "high": high, "low": 1998.8,
                                                "close": close}})


def test_strategy_file_is_strict_and_hashed():
    assert S.ref.startswith("htf_level_m1_rejection@v1#") and len(S.hash) == 10
    raw = json.loads(next(Path(__file__).resolve().parents[1].joinpath("library").glob("*.v1.json")).read_text())
    assert parse(raw).hash == S.hash
    with pytest.raises(StrategyError, match="unknown"):
        parse({**raw, "rules": {**raw["rules"], "min_rrr": 1}})
    with pytest.raises(StrategyError):
        parse({**raw, "rules": {**raw["rules"], "kind": "magic"}})
    changed = parse({**raw, "doctrine": raw["doctrine"] + ["one more rule"]})
    assert changed.hash != S.hash                     # any edit is visible in the journal


def test_plan_sell_at_resistance_targets_next_support():
    c, why = cands.plan(S, level_test_event(), SNAP, "LONDON")
    assert why == "ok" and c.side == "sell" and c.target == 1990.0 and c.target_source == "ASIA low"
    assert c.plan_stop == pytest.approx(2000.0 + 0.4 * 5.0)
    assert c.rr == pytest.approx(10.0 / 2.0)
    assert c.expires_at == T0 + 60 * (10 + 3 + 1)
    view = c.prompt_view("C1")
    assert view["id"] == "C1" and view["test"] == 2 and "below" in view["trigger"]


def test_plan_refusals():
    assert cands.plan(S, level_test_event(test_no=9), SNAP, "LONDON")[0] is None
    near = {**SNAP, "htf_levels": [LEVEL, {"id": "x", "price": 1999.5, "side": "low", "sources": ["s"], "tests": 0}]}
    c, _ = cands.plan(S, level_test_event(), near, "LONDON")
    assert c.target_source.startswith("2.0R")         # support too close -> fallback 2R target


def test_trigger_prices_from_the_rejection_candle():
    c, _ = cands.plan(S, level_test_event(), SNAP, "LONDON")
    c.decision_id = "D1"
    it, why = cands.trigger(S, c, rejection(), T0 + 120)
    assert why == "ok" and it.side == "sell" and it.decision_id == "D1"
    assert it.stop == pytest.approx(2001.0 + 0.1 * 5.0)            # extreme + buffer
    assert it.entry_high < it.stop and it.entry_low == pytest.approx(1999.0 - 1.5)
    assert it.target == 1990.0 and it.meta["rr"] >= 1.0
    tiny, _ = cands.trigger(S, c, rejection(high=2000.05, close=2000.0), T0 + 120)
    assert tiny.stop - 2000.0 == pytest.approx(0.3 * 5.0)           # min stop distance


def test_runner_approve_after_rejection_and_stalled_close():
    r = StrategyRunner(S, lambda t: "LONDON")
    step = r.observe([level_test_event()], lambda: SNAP, T0 + 60)
    assert len(step.asks) == 1
    key = step.asks[0].key
    r.mark_asked([key])
    r.observe([rejection()], lambda: SNAP, T0 + 120)                 # rejection while Qwen thinks
    it = r.approve(key, "D9", T0 + 150)
    assert it is not None and it.decision_id == "D9"
    stalled = ev("level_followthrough", T0 + 240, {"level": LEVEL, "test_no": 2, "result": "stalled",
                                                   "move_atr": 0.1, "rejection_time": T0 + 60})
    st = r.observe([stalled], lambda: SNAP, T0 + 300)
    assert st.closes and st.closes[0][0] == key
    r2 = StrategyRunner(S, lambda t: "LONDON")
    k2 = r2.observe([level_test_event()], lambda: SNAP, T0 + 60).asks[0].key
    r2.refuse(k2, "D1")
    assert not r2.observe([rejection()], lambda: SNAP, T0 + 120).intents      # refused: no trade


def test_template_budget_and_trimming():
    r = StrategyRunner(S, lambda t: "LONDON")
    c = r.observe([level_test_event()], lambda: SNAP, T0 + 60).asks
    ev_list = [(f"e{i}", f"12:{i:02d} M5 BOS dn close beyond 1999.{i:02d} and some padding text") for i in range(40)]
    outlook = {"t": "x", "px": 1999.0, "levels": [["R", 2000.0, "a", 1, 0.2]] * 4}
    p = template.build(S, outlook, c, ev_list)
    assert p.bytes <= S.prompt["max_bytes"] and p.candidate_map == {"C1": c[0].key}
    assert set(p.evidence_map) == {f"E{i + 1}" for i in range(len(p.evidence_map))}
    small = load("htf_level_m1_rejection")
    small = type(small)(**{**small.__dict__, "prompt": {**small.prompt, "max_bytes": 3000}})
    p2 = template.build(small, outlook, c, ev_list)
    assert p2.bytes <= 3000 and p2.trimmed["evidence"] > 0
    tiny = type(small)(**{**small.__dict__, "prompt": {**small.prompt, "max_bytes": 500}})
    with pytest.raises(template.PromptTooLarge):
        template.build(tiny, outlook, c, ev_list)
