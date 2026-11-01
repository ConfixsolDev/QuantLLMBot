"""Replay the whole pipeline on stored M1 bars with the paper broker.

    python -m trading.backtest --m1 <files/folders> [--lane all|llm] [--from D] [--to D]
    python -m trading.backtest --db --from 2026-09-01 --lane llm

Lanes (V3 Part F — "the model must beat a baseline before it trades"):
  all   take EVERY candidate the strategy produces (deterministic baseline)
  llm   take only what the model approves (needs the model server: Start-LLM.bat, config/llm.json)

Same engine, same strategy, same paper broker, same days: the only
difference between the lanes is the decider. Results are reported in R
(net / money risked), so the risk % does not change the comparison.

The paper broker fills at the close of the bar that triggered (+ spread for
buys) and assumes the stop is hit first when one bar touches both stop and
target — conservative, never flattering.
"""

from __future__ import annotations

import argparse
import calendar
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))       # backend/

from structure_engine.config import load_config  # noqa: E402
from structure_engine.engine import StructureEngine  # noqa: E402

from strategy import load as load_strategy  # noqa: E402
from trading.broker import PaperBroker  # noqa: E402
from trading.executor import Executor  # noqa: E402
from trading.journal import MemoryJournal  # noqa: E402
from trading.pipeline import Pipeline  # noqa: E402
from trading.risk import XAUUSD_DEFAULT as XAU  # noqa: E402
from trading.settings import load_settings  # noqa: E402


def run(bars, lane: str = "all", balance: float = 10_000.0, spread: float = 0.2,
        risk_pct: float | None = None, start: int | None = None, decider=None) -> dict:
    from llm.decider import LLMDecider, take_all
    settings = load_settings()
    if risk_pct is not None:
        from dataclasses import replace
        settings = replace(settings, risk_pct=risk_pct)
    strat = load_strategy(settings.strategy, settings.strategy_version)
    engine = StructureEngine(load_config())
    broker = PaperBroker(XAU, balance=balance, spread=spread)
    journal = MemoryJournal()
    ex = Executor(broker, settings, "XAUUSD", journal)
    decide = decider or (take_all if lane == "all" else LLMDecider())
    pipe = Pipeline(strat, engine, decide, ex, journal, mode=f"backtest-{lane}")
    for bar in bars:
        events = engine.push(bar)
        broker.on_bar(bar)
        if start is not None and bar.time < start:      # warm-up: engine only
            continue
        pipe.on_bar(bar, events, engine.now)
    from trading.verify import verify
    return {"strategy": strat.ref, "lane": lane, "pipeline": pipe.stats, "journal": journal,
            "balance": round(broker.balance, 2), "start_balance": balance,
            "verify": verify(strat, settings, journal)}


def report(res: dict) -> str:
    trades = [t for t in res["journal"].trades.values() if t.get("r_multiple") is not None]
    fails = res.get("verify", [])
    lines = [f"strategy {res['strategy']}  lane {res['lane']}",
             f"pipeline {res['pipeline']}",
             "system checks (trading/verify.py): " + ("ALL PASS" if not fails else f"{len(fails)} FAILURES")]
    lines += [f"  {f}" for f in fails[:20]]
    if not trades:
        return "\n".join(lines + ["no closed trades"])
    rs = [t["r_multiple"] for t in trades]
    eq, peak, dd = 0.0, 0.0, 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    wins = sum(r > 0 for r in rs)
    lines += [f"trades {len(rs)}  win {wins / len(rs):.1%}  avg {statistics.mean(rs):+.3f} R  "
              f"total {sum(rs):+.2f} R  max drawdown {dd:.2f} R",
              f"balance {res['start_balance']} -> {res['balance']} (paper, risk {load_settings().risk_pct}% per trade)"]
    by = defaultdict(list)
    for t in trades:
        by[t["close_reason"] + (f" ({t['close_note'][:20]})" if t.get("close_note") else "")].append(t["r_multiple"])
    stop_atr = [abs(t["meta"]["rejection_candle"]["close"] - t["stop"]) / t["atr"] for t in trades]
    lines.append(f"  stop distance: min {min(stop_atr):.2f}  median {statistics.median(stop_atr):.2f}  "
                 f"max {max(stop_atr):.2f} ATR(M15)")
    for k, v in sorted(by.items()):
        lines.append(f"  closed by {k:<40} n={len(v):4d}  avg {statistics.mean(v):+.2f} R")
    bt = defaultdict(list)
    for t in trades:
        bt[min(t["meta"].get("test_no", 0), 3)].append(t["r_multiple"])
    for k, v in sorted(bt.items()):
        lines.append(f"  test {k}{'+' if k == 3 else ' '} n={len(v):4d}  avg {statistics.mean(v):+.2f} R  "
                     f"win {sum(r > 0 for r in v) / len(v):.0%}")
    refusals = Counter(r["reason"].split(" ")[0] for r in res["journal"].refusals)
    if refusals:
        lines.append(f"  refusals {dict(refusals)}")
    return "\n".join(lines)


def _day(s: str | None) -> int | None:
    return calendar.timegm(time.strptime(s, "%Y-%m-%d")) if s else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trading.backtest", description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="*", help="M1 CSV files or folders")
    ap.add_argument("--db", action="store_true", help="read M1 bars from the database")
    ap.add_argument("--from", dest="start", help="first traded day YYYY-MM-DD (10 days before = warm-up)")
    ap.add_argument("--to", dest="end", help="last day (exclusive) YYYY-MM-DD")
    ap.add_argument("--lane", choices=("all", "llm"), default="all")
    ap.add_argument("--balance", type=float, default=10_000.0)
    ap.add_argument("--spread", type=float, default=0.2)
    ap.add_argument("--risk", type=float, help="override risk_pct")
    a = ap.parse_args()
    start, end = _day(a.start), _day(a.end)
    warm = start - 10 * 86400 if start else None
    if a.db:
        from quantllm import mt5_connection
        from quantllm.database import Database
        from quantllm.settings import load_settings as app_settings
        st = app_settings()
        bars = Database(st.db_dsn, st.db_schema).iter_candles(mt5_connection.settings().broker_symbol, warm)
    elif a.m1:
        from structure_engine.feeds import RecordedFeed
        bars = (b for b in RecordedFeed(a.m1) if warm is None or b.time >= warm)
    else:
        sys.exit("give --m1 <files/folders> or --db")
    if end:
        bars = (b for b in bars if b.time < end)
    print(report(run(bars, a.lane, a.balance, a.spread, a.risk, start)))


if __name__ == "__main__":
    main()
