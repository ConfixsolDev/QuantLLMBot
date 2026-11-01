"""Trading package tests: sizing, executor checks, paper broker, journal, backtest smoke."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from structure_engine.bars import Bar  # noqa: E402
from structure_engine.verification.synthetic import random_walk_m1  # noqa: E402
from trading.broker import PaperBroker  # noqa: E402
from trading.executor import Executor  # noqa: E402
from trading.intent import TradeIntent  # noqa: E402
from trading.journal import MemoryJournal  # noqa: E402
from trading.risk import XAUUSD_DEFAULT as XAU  # noqa: E402
from trading.risk import position_size  # noqa: E402
from trading.settings import TradingSettings, load_settings  # noqa: E402

T0 = 1_785_000_000 - 1_785_000_000 % 60


def test_position_size_percent_of_balance_per_stop_distance():
    s = position_size(10_000, 10, 4000.0, 3995.0, XAU, spread=0.2, slippage=0.2)
    # budget 1000; distance 5.4; $100 per $1 per lot -> 540 per lot -> 1.851 -> 1.85 lots (rounded DOWN)
    assert s.lots == 1.85 and s.risk_money == pytest.approx(999.0) and s.risk_money <= 1000
    tiny = position_size(100, 1, 4000.0, 3900.0, XAU)          # 1 USD budget, 100$ stop
    assert tiny.lots == 0 and "minimum lot" in tiny.reason
    huge = position_size(10_000_000, 50, 4000.0, 3999.9, XAU)
    assert huge.lots == XAU.volume_max


def test_settings_refuse_live_accounts(tmp_path):
    f = tmp_path / "t.json"
    f.write_text('{"require_demo": false}')
    with pytest.raises(ValueError, match="demo"):
        load_settings(f)
    f.write_text('{"risk_pct": 12.5, "mode": "paper"}')
    assert load_settings(f).risk_pct == 12.5


def make(side="sell", stop=2002.0, target=1990.0, lo=1998.5, hi=2001.0, expires=T0 + 300):
    return TradeIntent("i1", "s@v1#h", "d1", "Vabc:2", side, lo, hi, stop, target, T0, expires, 5.0, {"test_no": 2})


def setup(price=1999.0, **kw):
    b = PaperBroker(XAU, balance=10_000, spread=0.2)
    b.on_bar(Bar(T0, price, price + 0.5, price - 0.5, price, 10))
    j = MemoryJournal()
    ex = Executor(b, replace(TradingSettings(), risk_pct=kw.get("risk", 10.0), slippage_allowance=0.0), "XAUUSD", j)
    return b, ex, j


def test_fill_then_stop_is_about_minus_one_r():
    b, ex, j = setup()
    out = ex.execute(make(), T0 + 60)
    assert out.status == "filled" and out.trade["entry"] == 1999.0
    assert out.trade["risk_money"] <= 1000
    b.on_bar(Bar(T0 + 60, 1999.0, 2002.5, 1998.9, 2002.2, 10))      # spikes through the stop
    t = ex.sync(T0 + 120)[0]
    assert t["close_reason"] == "stop" and t["r_multiple"] == pytest.approx(-1.0, abs=0.08)
    assert j.trades["i1"]["r_multiple"] == t["r_multiple"]


def test_target_and_strategy_close():
    b, ex, _ = setup()
    ex.execute(make(), T0 + 60)
    b.on_bar(Bar(T0 + 60, 1999.0, 1999.1, 1989.5, 1990.5, 10))
    t = ex.sync(T0 + 120)[0]
    assert t["close_reason"] == "target" and t["r_multiple"] > 2.5
    b, ex, _ = setup()
    ex.execute(make(), T0 + 60)
    b.on_bar(Bar(T0 + 60, 1999.0, 1999.5, 1998.6, 1999.2, 10))
    assert ex.close("Vabc:2", "rejection stalled", T0 + 120)
    t = ex.sync(T0 + 120)[0]
    assert t["close_reason"] == "strategy_close" and t["close_note"] == "rejection stalled"


def test_executor_refusals():
    cases = [
        (make(expires=T0), "expired"),
        (make(lo=1990.0, hi=1995.0), "outside entry range"),
        (make(stop=1998.0), "stop"),
        (make(target=2005.0), "target"),
    ]
    for intent, why in cases:
        _, ex, j = setup()
        out = ex.execute(intent, T0 + 60)
        assert out.status == "refused" and why in out.reason, (why, out.reason)
        assert j.refusals and j.refusals[-1]["reason"] == out.reason
    b, ex, _ = setup()
    ex.execute(make(), T0 + 60)
    assert "already open" in ex.execute(replace(make(), intent_id="i2"), T0 + 60).reason
    b, ex, _ = setup()
    b.demo = False
    assert "NOT a demo" in ex.execute(make(), T0 + 60).reason


def test_backtest_take_all_smoke():
    from trading.backtest import report, run
    res = run(random_walk_m1(3, 6 * 1440), lane="all")
    assert res["verify"] == []                          # every system rule held on every trade
    st = res["pipeline"]
    assert st["bars"] == 6 * 1440 and st["too_large"] == 0 and st["max_prompt_bytes"] <= 6000
    assert st["prompts"] == st["take"] and st["filled"] + st["refused"] == st["intents"]
    assert "lane all" in report(res)


def test_db_journal_writes_decisions_trades_refusals(tmp_path_factory):
    import os
    if os.environ.get("QUANTLLM_TEST_DSN"):
        dsn = os.environ["QUANTLLM_TEST_DSN"]
    else:
        pgserver = pytest.importorskip("pgserver")
        dsn = pgserver.get_server(str(tmp_path_factory.mktemp("pgj")), cleanup_mode="stop").get_uri()
    psycopg = pytest.importorskip("psycopg")
    from trading.journal import DbJournal
    conn = psycopg.connect(dsn, autocommit=True)
    conn.execute("CREATE SCHEMA IF NOT EXISTS journal_test")
    conn.execute("SET search_path TO journal_test")
    for t in ("decisions", "trades", "refusals"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    j = DbJournal(conn)
    j.decision({"id": "d1", "time": T0, "strategy_ref": "s@v1#h", "prompt_sha": "p", "prompt_bytes": 3000,
                "candidates": {"C1": "Vabc:2"}, "evidence_map": {"E1": "ev"}, "action": "take", "label": "C1",
                "candidate_key": "Vabc:2", "confidence": 70, "cites": ["E1"], "why": "ok", "errors": []})
    b = PaperBroker(XAU, balance=10_000, spread=0.2)
    b.on_bar(Bar(T0, 1999.0, 1999.5, 1998.5, 1999.0, 10))
    ex = Executor(b, TradingSettings(), "XAUUSD", j)
    assert ex.execute(make(), T0 + 60).status == "filled"
    ex.execute(replace(make(), intent_id="i2"), T0 + 60)                     # refused: one position
    b.on_bar(Bar(T0 + 60, 1999.0, 1999.1, 1989.0, 1990.0, 10))
    ex.sync(T0 + 120)
    row = conn.execute("SELECT close_reason, r_multiple, pnl_complete FROM trades WHERE id='i1'").fetchone()
    assert row[0] == "target" and row[1] > 2 and row[2] is True
    assert conn.execute("SELECT count(*) FROM decisions").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM refusals").fetchone()[0] == 1
    assert j.net_today(T0 + 120) > 0
    conn.close()


def test_mt5_broker_request_fields_and_exit_reasons():
    """MT5Broker against a fake MetaTrader5 module: order fields, IOC, magic, settle + reasons."""
    from types import SimpleNamespace as NS
    from trading.broker import MT5Broker
    sent = []

    class FakeMT5:
        ACCOUNT_TRADE_MODE_DEMO, TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1, 0, 1
        ORDER_TIME_GTC, ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 0, 1, 2
        TRADE_RETCODE_DONE, TRADE_RETCODE_DONE_PARTIAL, POSITION_TYPE_BUY, DEAL_ENTRY_IN = 10009, 10010, 0, 0

        def account_info(self):
            return NS(balance=5000.0, equity=5000.0, currency="USD", login=1, trade_mode=0)

        def symbol_info(self, s):
            return NS(trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01, volume_max=50.0,
                      volume_step=0.01, digits=2, filling_mode=3)

        def symbol_info_tick(self, s):
            return NS(bid=1999.0, ask=1999.2, time=T0)

        def order_send(self, req):
            sent.append(req)
            return NS(retcode=10009, order=77, price=req["price"], volume=req["volume"], comment="done")

        def history_deals_get(self, a, b):
            return [NS(position_id=77, entry=0, profit=0.0, commission=-1.0, swap=0.0, fee=0.0, comment="QL x",
                       volume=1.0, price=1999.0, time=T0),
                    NS(position_id=77, entry=1, profit=-200.0, commission=-1.0, swap=0.0, fee=0.0,
                       comment="[sl 2001.00]", volume=1.0, price=2001.0, time=T0 + 600)]

        def last_error(self):
            return (0, "")

    b = MT5Broker(FakeMT5(), lambda t: t)
    assert b.account()["demo"] and b.spec("XAUUSD").value_per_unit == 100.0
    f = b.open("XAUUSD", "sell", 1.0, 2001.0, 1990.0, 26110101, "QL i1", 30)
    req = sent[-1]
    assert f.position_id == 77 and req["price"] == 1999.0 and req["sl"] == 2001.0 and req["tp"] == 1990.0
    assert req["magic"] == 26110101 and req["type_filling"] == FakeMT5.ORDER_FILLING_IOC
    ex = b.exit_summary(77, T0)
    assert ex.reason == "stop" and ex.complete and ex.net == pytest.approx(-202.0) and ex.exit_price == 2001.0


def test_verify_catches_rule_breaks():
    from types import SimpleNamespace
    from strategy import load
    from trading.verify import verify
    s = load("htf_level_m1_rejection")
    j = MemoryJournal()
    j.decision({"id": "d1", "prompt_bytes": 9000, "action": "take", "label": "C1", "candidates": {"C1": "k"}})
    j.trade_opened({"id": "t1", "decision_id": "d1", "side": "sell", "stop": 2001.0, "target": 1990.0,
                    "risk_money": 2000.0, "balance_before": 10_000.0, "opened_at": T0 + 60, "atr": 5.0,
                    "intent_created_at": T0, "meta": {"rejection_candle": {"time": T0, "close": 1999.0}}})
    j.trade_opened({"id": "t2", "decision_id": "dX", "side": "sell", "stop": 2006.0, "target": 1988.5,
                    "risk_money": 100.0, "balance_before": 10_000.0, "opened_at": T0 + 120, "atr": 5.0,
                    "intent_created_at": T0, "meta": {"rejection_candle": {"time": T0, "close": 1999.0}}})
    codes = {f.split(" ")[0] for f in verify(s, SimpleNamespace(risk_pct=10.0, max_open_positions=1), j)}
    assert {"D1", "T1", "T2", "T3", "T4", "T6"} <= codes


def _daytest(tmp_path, decider):
    from trading.daytest import DayTest, trading_days
    bars = random_walk_m1(9, 9 * 1440)
    dt = DayTest("stub", tmp_path)
    dt.pipe.decide = decider
    start = bars[0].time + 3 * 86400
    reps = []
    for date, day_bars in trading_days(iter(bars), start - start % 86400, bars[-1].time):
        if date == "warm-up":
            for b in day_bars:
                dt.engine.push(b)
                dt.broker.on_bar(b)
            continue
        reps.append(dt.run_day(date, day_bars))
    return dt, reps


def test_daytest_runs_day_by_day_and_reports(tmp_path):
    from trading.daytest import stub_decider
    dt, reps = _daytest(tmp_path, stub_decider(2000))
    assert reps and sum(r["prompts"] for r in reps) > 0
    assert all(r["crashes"] == 0 and not [i for i in r["issues"] if not i.startswith("DATA")] for r in reps)
    assert (tmp_path / f"day-{reps[0]['date']}.json").exists()
    assert "Day-by-day platform test" in dt.finish().read_text()


def test_daytest_flags_a_slow_model_and_a_crashing_decider(tmp_path):
    from trading.daytest import stub_decider
    _, reps = _daytest(tmp_path / "slow", stub_decider(400_000))           # 400 s: window is ~3 min
    assert any(i.startswith("WINDOW") for r in reps for i in r["issues"])
    assert sum(r["filled"] for r in reps) == 0

    def boom(prompt, strategy):
        raise RuntimeError("decider exploded")
    _, reps2 = _daytest(tmp_path / "boom", boom)
    model = [i for r in reps2 for i in r["issues"] if i.startswith("MODEL")]
    assert model and "decider error" in model[0] and len(reps2) == len(reps)      # journaled, run went on
    assert not [i for r in reps2 for i in r["issues"] if i.startswith("CRASH")]
