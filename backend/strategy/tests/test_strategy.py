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
from strategy.runner import StrategyRunner, age  # noqa: E402
from structure_engine.verification.synthetic import random_walk_m1  # noqa: E402

S = load("htf_level_m1_rejection")
T0 = 1_785_000_000 - 1_785_000_000 % 60
LEVEL = {"id": "Vabc", "price": 2000.0, "side": "high", "sources": ["H1 swing high", "LONDON high"],
         "time": T0 - 7200, "created_at": T0 - 3600, "tests": 2, "held": 1}
SNAP = {"htf_levels": [LEVEL, {"id": "Vsup", "price": 1990.0, "side": "low", "sources": ["ASIA low"], "tests": 0}],
        "atr": {"M15": 5.0, "H1": 9.0}, "trend": {"H1": {"state": "up", "protected": 1980.0}},
        "vwap": {"day": {"vwap": 1995.0, "sd": 2.5}}, "as_of": T0, "swings": {"M15": [{"kind": "low", "price": 1996.0}]},
        "ranges": {}, "forming": {"day": {"high": 2001.0, "low": 1985.0}}}


def ev(kind, t, data, eid=None):
    return {"id": eid or f"{kind}{t}", "kind": kind, "tf": "M1", "time": t, "available_at": t + 60, "data": data}


def level_test(test_no=2, t=T0):
    return ev("level_test", t, {"level": {**LEVEL, "tests": test_no}, "test_no": test_no, "atr": 5.0,
                                "approach": "drift", "stretch_h1_atr": 3.1, "trend": {"H1": "up"},
                                "approach_detail": {"net_atr": 1.23, "efficiency": 0.4, "pressing_bars": 3},
                                "candle": {"time": t, "open": 1999, "high": 2000.1, "low": 1998.5, "close": 1999.2}})


def rejection(t=T0 + 60, high=2001.0, close=1999.0, test_no=2):
    return ev("level_rejection", t, {"level": LEVEL, "test_no": test_no, "pierce_atr": 0.2, "bars_after_touch": 1,
                                     "candle": {"time": t, "open": 1999.5, "high": high, "low": 1998.8,
                                                "close": close, "volume": 300.0}})


class FakeEngine:
    """Just what template.build reads from the engine."""
    _last_close = 1999.0
    config_hash = "h"

    class sessions:
        @staticmethod
        def _window_of(t):
            return ("LONDON", t - 3600, t + 3600)

    def __init__(self):
        from structure_engine.bars import Bar
        self.hist = {"M15": [(Bar(T0 - 900 * i, 1998, 2000, 1996, 1999, 100), None) for i in range(4)]}

        class levels:                                   # the last closed M1 bars (average volume 200)
            m1 = [Bar(T0 - 60 * i, 1998, 2000, 1996, 1999, 200) for i in range(60, 0, -1)]
        self.levels = levels

    def snapshot(self):
        return SNAP


def test_strategy_file_is_strict_and_hashed():
    assert S.version == 3 and S.rules["decision_point"] == "rejection" and S.ref.startswith("htf_level_m1_rejection@v3#")
    assert S.rules["min_stop_atr"] == 1.2 and S.rules["target"] == "r_multiple" and S.rules["target_r"] == 1.5
    assert S.rules["close_on_stalled_followthrough"] is False
    raw = json.loads(next(Path(__file__).resolve().parents[1].joinpath("library").glob("*.v3.json")).read_text())
    assert parse(raw).hash == S.hash
    with pytest.raises(StrategyError, match="unknown"):
        parse({**raw, "rules": {**raw["rules"], "min_rrr": 1}})
    with pytest.raises(StrategyError, match="decision_point"):
        parse({**raw, "rules": {**raw["rules"], "decision_point": "whenever"}})
    assert parse({**raw, "doctrine": raw["doctrine"] + ["one more rule"]}).hash != S.hash


def test_plan_and_trigger_prices():
    c, why = cands.plan(S, level_test(), SNAP, "LONDON")
    # v3: planned stop 1.2 ATR beyond the level, target 1.5 R
    assert why == "ok" and c.side == "sell" and c.plan_stop == pytest.approx(2006.0)
    assert c.target == pytest.approx(2000.0 - 1.5 * 6.0) and c.rr == pytest.approx(1.5)
    assert cands.plan(S, level_test(test_no=9), SNAP, "LONDON")[0] is None
    c.decision_id = "D1"
    it, why = cands.trigger(S, c, rejection(), T0 + 120)
    # the rejection extreme + 0.1 ATR (2001.5) is closer than 1.2 ATR: the stop goes to 1999 + 6 = 2005
    assert why == "ok" and it.stop == pytest.approx(2005.0) and it.entry_high < it.stop
    assert it.target == pytest.approx(1999.0 - 1.5 * 6.0) and it.meta["rr"] == pytest.approx(1.5)
    wide, _ = cands.trigger(S, c, rejection(high=2008.0, close=1999.0), T0 + 120)
    assert wide.stop == pytest.approx(2008.5)                  # structure wider than 1.2 ATR wins


def test_runner_asks_at_the_rejection_and_fires_on_approval():
    r = StrategyRunner(S, lambda t: "LONDON")
    assert r.observe([level_test()], lambda: SNAP, T0 + 60).asks == []        # armed silently
    st = r.observe([rejection()], lambda: SNAP, T0 + 120)
    assert len(st.asks) == 1 and st.asks[0].rejection is not None
    key = st.asks[0].key
    it = r.approve(key, "D9", T0 + 125)
    assert it is not None and it.decision_id == "D9" and it.side == "sell"
    stalled = ev("level_followthrough", T0 + 240, {"level": LEVEL, "test_no": 2, "result": "stalled",
                                                   "move_atr": 0.1, "rejection_time": T0 + 60})
    assert r.observe([stalled], lambda: SNAP, T0 + 300).closes == []        # v3: no early exit
    v2 = load("htf_level_m1_rejection", 2)
    r3 = StrategyRunner(v2, lambda t: "LONDON")
    r3.observe([level_test()], lambda: SNAP, T0 + 60)
    k3 = r3.observe([rejection()], lambda: SNAP, T0 + 120).asks[0].key
    r3.approve(k3, "D", T0 + 125)
    assert r3.observe([stalled], lambda: SNAP, T0 + 300).closes[0][0] == k3  # v2 closed stalled trades
    r2 = StrategyRunner(S, lambda t: "LONDON")
    r2.observe([level_test()], lambda: SNAP, T0 + 60)
    k2 = r2.observe([rejection()], lambda: SNAP, T0 + 120).asks[0].key
    r2.refuse(k2, "D1")
    assert r2.approve(k2, "D2", T0 + 130) is None                            # a refusal is final


def test_level_history_and_ages():
    r = StrategyRunner(S, lambda t: "LONDON")
    t1 = level_test(test_no=1, t=T0 - 3600)
    r.observe([t1, rejection(t=T0 - 3540, test_no=1)], lambda: SNAP, T0 - 3480)
    r.observe([ev("level_followthrough", T0 - 3360, {"level": LEVEL, "test_no": 1, "result": "moved", "move_atr": 1.0,
                                                     "rejection_time": 0}),
               ev("level_held", T0 - 3300, {"level": LEVEL, "test_no": 1, "bars": 5, "rejected": True})],
              lambda: SNAP, T0 - 3240)
    assert r.history("Vabc", 2, T0) == ["t1 60m ago: rejected (poke 0.2), moved, held"]
    assert (age(59 * 60), age(5 * 3600), age(4 * 86400)) == ("59m", "5h", "4d")


def test_template_v2_named_fields_budget_and_dedupe():
    r = StrategyRunner(S, lambda t: "LONDON")
    r.observe([level_test()], lambda: SNAP, T0 + 60)
    asks = r.observe([rejection()], lambda: SNAP, T0 + 120).asks
    p = template.build(S, FakeEngine(), r, asks, T0 + 120)
    u = json.loads(p.user)
    assert set(u) == {"market", "candidates", "evidence"} and p.bytes <= S.prompt["max_bytes"]
    c = u["candidates"][0]
    assert c["id"] == "C1" and c["level"]["test"] == 2 and c["rejection"]["vol_x"] == pytest.approx(1.5)
    assert c["trade"]["stop"] == pytest.approx(2005.0) and c["trade"]["rr"] == pytest.approx(1.5)
    assert c["obstacles"][0]["what"] in ("M15 swing low", "VWAP day")
    assert u["market"]["trend"]["H1"] == {"dir": "up", "protected": 1980.0}
    assert "FIELDS:" in p.system and p.previews["C1"] is not None
    # two levels hit by the same candle give the same trade: offered once
    lv2 = {**LEVEL, "id": "Vxyz", "price": 2000.3}
    r2 = StrategyRunner(S, lambda t: "LONDON")
    t2 = level_test()
    t2b = {**level_test(), "id": "t2b", "data": {**level_test()["data"], "level": {**lv2, "tests": 2}}}
    r2.observe([t2, t2b], lambda: SNAP, T0 + 60)
    rj2 = {**rejection(), "id": "r2b", "data": {**rejection()["data"], "level": lv2}}
    asks2 = r2.observe([rejection(), rj2], lambda: SNAP, T0 + 120).asks
    assert len(asks2) == 2 and len(template.build(S, FakeEngine(), r2, asks2, T0 + 120).candidate_map) == 1


def test_dataset_builder_writes_prompts_and_hidden_labels(tmp_path):
    from strategy.dataset import build
    bars = random_walk_m1(4, 8 * 1440)
    summary = build(iter(bars), tmp_path, start=bars[0].time + 2 * 86400, end=None)
    prompts = [json.loads(x) for x in (tmp_path / "prompts.jsonl").read_text().splitlines()]
    labels = {json.loads(x)["id"]: json.loads(x) for x in (tmp_path / "labels.jsonl").read_text().splitlines()}
    assert summary["prompts"] == len(prompts) > 0 and (tmp_path / "system.txt").read_text().startswith("STRATEGY")
    for p in prompts:
        assert p["bytes"] <= 6000 and "r" not in json.loads(p["user"])           # no answer key inside
        assert set(labels[p["id"]]["candidates"]) == set(p["candidate_map"])


def test_stop_beyond_the_next_higher_level_option():
    """Owner's alternative: trade an H1 level, put the stop just beyond the next H4/day/week level."""
    import dataclasses
    h4 = {"id": "Vh4", "price": 2004.0, "side": "high", "sources": ["H4 swing high"], "tests": 0}
    far = {"id": "Vfar", "price": 2030.0, "side": "high", "sources": ["WEEK high"], "tests": 0}
    snap = {**SNAP, "htf_levels": SNAP["htf_levels"] + [h4, far]}
    s2 = dataclasses.replace(S, rules={**S.rules, "stop_mode": "beyond_higher_level"})
    c, _ = cands.plan(s2, level_test(), snap, "LONDON")
    assert c.higher_beyond == [2004.0, 2030.0]                  # H4/day/week levels beyond, nearest first
    it, _ = cands.trigger(s2, c, rejection(), T0 + 120)
    # 1.2 ATR from 1999 = 2005 is already beyond 2004 + 0.5: the wider of the two wins -> 2005 (atr)
    assert it.stop == pytest.approx(2005.0) and it.meta["stop_source"] == "atr"
    h4b = {**h4, "price": 2007.0}
    c2, _ = cands.plan(s2, level_test(), {**SNAP, "htf_levels": SNAP["htf_levels"] + [h4b, far]}, "LONDON")
    it2, _ = cands.trigger(s2, c2, rejection(), T0 + 120)
    assert it2.stop == pytest.approx(2007.5) and it2.meta["stop_source"] == "beyond higher level"
    assert it2.target == pytest.approx(1999.0 - 1.5 * 8.5)       # 1.5 R of the wider stop
    # the WEEK high at 2030 is 6 ATR away (> max_stop_atr 3): never used
    c3, _ = cands.plan(s2, level_test(), {**SNAP, "htf_levels": SNAP["htf_levels"] + [far]}, "LONDON")
    assert cands.trigger(s2, c3, rejection(), T0 + 120)[0].meta["stop_source"] == "atr"


def test_stop_beyond_the_next_level_of_any_timeframe():
    import dataclasses
    h1 = {"id": "Vh1", "price": 2007.0, "side": "high", "sources": ["H1 swing high"], "tests": 0}
    s2 = dataclasses.replace(S, rules={**S.rules, "stop_mode": "beyond_next_level"})
    c, _ = cands.plan(s2, level_test(), {**SNAP, "htf_levels": SNAP["htf_levels"] + [h1]}, "LONDON")
    assert c.next_beyond == [2007.0] and c.higher_beyond == []
    it, _ = cands.trigger(s2, c, rejection(), T0 + 120)
    assert it.stop == pytest.approx(2007.5) and it.meta["stop_source"] == "beyond next level"
