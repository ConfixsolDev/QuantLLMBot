"""Scalp strategy tests: m1_probe_failure (python -m pytest strategy/tests -q, from backend/)."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm.contract import answer_schema, check  # noqa: E402
from strategy import StrategyError, load  # noqa: E402
from strategy import scalp  # noqa: E402
from strategy import template  # noqa: E402
from strategy.model import parse  # noqa: E402
from structure_engine.bars import Bar  # noqa: E402

S = load("m1_probe_failure_scalp")
T0 = 1_785_000_000 - 1_785_000_000 % 60
ATR1 = 2.0
LEVEL = {"id": "Vres", "price": 2000.0, "side": "high", "sources": ["M15 swing high", "LONDON high"],
         "time": T0 - 7200, "created_at": T0 - 3600, "tests": 2, "held": 1}
SNAP = {"htf_levels": [LEVEL, {"id": "Vsup", "price": 1990.0, "side": "low", "sources": ["ASIA low"], "tests": 0}],
        "atr": {"M1": ATR1, "M15": 5.0, "H1": 9.0},
        "trend": {"H4": {"state": "down", "protected": 2030.0}, "H1": {"state": "down", "protected": 2010.0},
                  "M30": {"state": "up", "protected": 1985.0}, "M15": {"state": "up", "protected": 1988.0}},
        "vwap": {"day": {"vwap": 1995.0, "sd": 2.5}}, "as_of": T0, "swings": {"M15": [{"kind": "low", "price": 1997.0}]},
        "ranges": {}, "forming": {"day": {"high": 2001.0, "low": 1985.0}}}
# the probe candle: high 2001.2 beyond the 2000 resistance, closes back at 1999.0, long upper wick, red body
CANDLE = {"time": T0, "open": 1999.6, "high": 2001.2, "low": 1998.8, "close": 1999.0, "volume": 900.0}


def ev(kind, data, eid=None, t=T0):
    return {"id": eid or f"{kind}{t}", "kind": kind, "tf": "M1", "time": t, "available_at": t + 60, "data": data}


def m1_history(n=40, vol=200.0, start=1975.0, step=0.6):
    """M1 bars rising into the level (price ran up: a sell fade is 'stretched')."""
    return [Bar(T0 - 60 * (n - i), start + step * i, start + step * i + 0.5, start + step * i - 0.3,
                start + step * i + 0.3, vol) for i in range(n)] + [Bar(T0, 1999.6, 2001.2, 1998.8, 1999.0, 900.0)]


def runner(bars=None, session="LONDON", strategy=S):
    bars = bars if bars is not None else m1_history()
    return scalp.ScalpRunner(strategy, lambda t: session, lambda: bars)


def triggers():
    rej = ev("level_rejection", {"level": LEVEL, "test_no": 3, "pierce_atr": 0.24, "bars_after_touch": 1,
                                 "candle": CANDLE}, "Erej")
    sweep = ev("liquidity_sweep", {"side": "high", "candle": CANDLE, "extreme": 2001.2, "pierce_atr": 0.6,
                                   "close_vs_level_atr": 0.5, "break_time": None,
                                   "levels": [{"id": "Lp", "kind": "equal_highs", "side": "high", "price": 2000.4,
                                               "source_tf": "M15", "time": T0 - 5000, "active_from": T0 - 4000}]},
               "Esweep")
    return [rej, sweep]


def test_strategy_file_is_strict_and_hashed():
    assert S.rules["kind"] == "m1_probe_failure" and S.ref.startswith("m1_probe_failure_scalp@v1#")
    assert S.rules["atr_timeframe"] == "M1" and S.rules["min_stop_atr"] == 1.2 and S.rules["target_r"] == 1.0
    assert S.rules["max_hold_bars"] == 30 and S.prompt["max_bytes"] == 6000
    raw = json.loads(next(Path(__file__).resolve().parents[1].joinpath("library")
                          .glob("m1_probe_failure_scalp.v1.json")).read_text(encoding="utf-8"))
    assert parse(raw).hash == S.hash
    with pytest.raises(StrategyError, match="unknown"):
        parse({**raw, "rules": {**raw["rules"], "decision_point": "rejection"}})     # a level-strategy key
    with pytest.raises(StrategyError, match="triggers"):
        parse({**raw, "rules": {**raw["rules"], "triggers": ["level_test"]}})
    doctrine = " ".join(S.doctrine)
    assert "M5 is not used" in doctrine and "costs nothing" not in doctrine and "Never answer 0" in doctrine


def test_one_bar_one_side_is_one_candidate_with_all_locations_and_checks():
    r = runner()
    step = r.observe(triggers(), lambda: SNAP, T0 + 60)
    assert len(step.asks) == 1
    c = step.asks[0]
    assert c.key == "Erej" and c.side == "sell" and [a["what"] for a in c.at] == ["level rejection", "liquidity sweep"]
    assert c.atr == ATR1 and c.test_no == 3
    # wick (2001.2-1999.6)/2.4 = 0.67, red body (sell), volume 900/200 = 4.5x, ran 4.5 ATR into it, 2 triggers
    assert c.checks == {"confluence": True, "wick": True, "close_against_probe": True, "volume": True,
                        "stretched": True}
    assert c.passed == 5 and c.facts["vol_x"] == 4.5 and c.facts["triggers_in_window"] == 2


def test_filters_min_checks_sessions_and_oversized_candle():
    quiet = [Bar(b.time, b.open, b.high, b.low, b.close, 2000.0)
             for b in m1_history(start=1999.0, step=0.0)]                          # flat and loud: no stretch
    lone = triggers()[1:]                                                         # one trigger only
    weak = {**CANDLE, "open": 1999.0, "close": 2000.3, "high": 2000.6}            # small wick, green body
    lone[0]["data"]["candle"] = weak
    quiet[-1] = Bar(T0, 1999.0, 2000.6, 1998.8, 2000.3, 900.0)
    step = runner(quiet).observe(lone, lambda: SNAP, T0 + 60)
    assert not step.asks and "min_checks" in step.skipped[0][1]
    strat = replace(S, rules={**S.rules, "sessions": ["LONDON"]})
    step = runner(session="NEW_YORK", strategy=strat).observe(triggers(), lambda: SNAP, T0 + 60)
    assert not step.asks and "session NEW_YORK" in step.skipped[0][1]
    huge = {**CANDLE, "high": 2012.0}                                             # stop would be > 4 ATR(M1)
    big = triggers()
    for e in big:
        e["data"]["candle"] = huge
    step = runner().observe(big, lambda: SNAP, T0 + 60)
    assert not step.asks and "too big" in step.skipped[0][1]


def test_trigger_prices_stop_target_window():
    c = runner().observe(triggers(), lambda: SNAP, T0 + 60).asks[0]
    it, why = scalp.trigger(S, c, T0 + 70)
    assert why == "ok" and it.side == "sell"
    # beyond the candle: 2001.2 + 0.1 x 2 = 2001.4 -> 2.4 from 1999.0 >= 1.2 ATR (2.4): equal here
    assert it.stop == pytest.approx(2001.4) and it.target == pytest.approx(1999.0 - 2.4)
    assert it.entry_low == pytest.approx(1998.0) and it.entry_high == pytest.approx(2000.0)
    assert it.expires_at == T0 + 60 * 3 and it.atr == ATR1 and it.meta["checks_passed"] == 5
    small = {**CANDLE, "high": 1999.9, "open": 1999.5}                            # tiny probe: the 1.2 ATR floor
    c2 = replace(c, candle=small)
    it2, _ = scalp.trigger(S, c2, T0 + 70)
    assert it2.stop == pytest.approx(1999.0 + 1.2 * ATR1) and it2.target == pytest.approx(1999.0 - 1.2 * ATR1)


def test_approval_fires_once_and_the_time_cap_closes_it():
    r = runner()
    c = r.observe(triggers(), lambda: SNAP, T0 + 60).asks[0]
    r.mark_asked([c.key])
    it = r.approve(c.key, "d1", T0 + 70)
    assert it is not None and it.decision_id == "d1" and r.approve(c.key, "d2", T0 + 71) is None
    assert r.observe([], lambda: SNAP, T0 + 70 + 29 * 60).closes == []
    st = r.observe([], lambda: SNAP, T0 + 70 + 30 * 60)
    assert st.closes == [(c.key, "time cap: 30 M1 bars")]
    assert r.observe([], lambda: SNAP, T0 + 70 + 31 * 60).closes == []          # asked once
    r.trade_closed(c.key)
    assert c.key not in r.traded


def test_expired_candidate_is_not_fired():
    r = runner()
    c = r.observe(triggers(), lambda: SNAP, T0 + 60).asks[0]
    assert r.approve(c.key, "d1", T0 + 60 * 5) is None and c.status == "expired"


class FakeEngine:
    _last_close = 1999.0
    config_hash = "h"

    class sessions:
        @staticmethod
        def _window_of(t):
            return ("LONDON", t - 3600, t + 3600)

    def snapshot(self):
        return SNAP


def test_prompt_budget_thesis_checks_and_answer_contract():
    r = runner()
    c = r.observe(triggers(), lambda: SNAP, T0 + 60).asks[0]
    p = template.build(S, FakeEngine(), r, [c], T0 + 60)
    assert p.bytes <= S.prompt["max_bytes"] and p.candidate_map == {"C1": "Erej"}
    assert "M5" not in p.user
    u = json.loads(p.user)
    assert u["market"]["thesis"] == {"bias": "sell", "why": "H4 and H1 down; M15 up = pullback against it"}
    assert set(u["market"]["trend"]) == {"H4", "H1", "M30", "M15"} and u["market"]["atr"]["M1"] == ATR1
    v = u["candidates"][0]
    assert v["checks"]["passed"] == 5 and v["trade"]["rr"] == 1.0 and v["trade"]["max_hold_min"] == 30
    assert v["at"][0]["history"] and v["trade"]["risk_usd"] == 2.4
    sch = answer_schema(p)
    assert "C1.checks" in sch["properties"]["cites"]["items"]["enum"]
    assert sch["properties"]["confidence"]["minimum"] == 1
    ok = check(json.dumps({"decision": "C1", "confidence": 68, "cites": ["C1.checks", "C1.at"], "why": "5/5"}),
               p, S.rules["min_confidence"])
    assert ok.action == "take" and ok.candidate_key == "Erej"
    low = check(json.dumps({"decision": "C1", "confidence": 45, "cites": ["C1.checks"], "why": "x"}), p, 51)
    assert low.action == "invalid"


def test_verify_accepts_the_time_cap_and_rejects_other_early_closes():
    from trading.journal import MemoryJournal
    from trading.settings import TradingSettings
    from trading.verify import verify
    r = runner()
    c = r.observe(triggers(), lambda: SNAP, T0 + 60).asks[0]
    it = r.approve(c.key, "d1", T0 + 70)
    j = MemoryJournal()
    j.decisions = [{"id": "d1", "prompt_bytes": 5000, "action": "take", "label": "C1", "candidates": {"C1": c.key}}]
    base = {"id": "t1", "decision_id": "d1", "side": "sell", "stop": it.stop, "target": it.target, "atr": ATR1,
            "risk_money": 100.0, "balance_before": 10_000, "opened_at": T0 + 70, "meta": it.meta,
            "intent_created_at": it.created_at, "pnl_complete": True, "r_multiple": 0.3,
            "close_reason": "strategy_close", "exit_price": 1998.3}
    j.trades = {"t1": {**base, "closed_at": T0 + 70 + 30 * 60}}
    assert verify(S, TradingSettings(), j) == []
    j.trades = {"t1": {**base, "closed_at": T0 + 70 + 5 * 60}}
    assert any(f.startswith("T9") for f in verify(S, TradingSettings(), j))
