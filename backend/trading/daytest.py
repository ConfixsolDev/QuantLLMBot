"""Day-by-day PLATFORM test: run the whole trading system one trading day at a time.

    python -m trading.daytest --db --from 2026-10-01 --to 2026-11-01            (the model, Start-LLM.bat)
    python -m trading.daytest --db --from 2026-10-01 --to 2026-11-01 --lane stub (no model: platform only)
    python -m trading.daytest --m1 <bars> --from ... --to ... [--pause] [--day 2026-10-07]

Days are gold TRADING days (17:00 New York to 17:00 New York, named by the
day they end), so a Sunday evening opens Monday. Exactly the live pipeline (structure engine -> strategy runner -> prompt ->
decider -> answer contract -> executor -> paper broker -> journal), fed with
the stored M1 bars. The engine warms up on the 10 days before ``--from`` and
then runs CONTINUOUSLY, like live; after each trading day the day is checked
and reported before the next one starts (``--pause`` waits for Enter).

Lanes (the decider):
  llm    the real model (config/llm.json) — latency is SIMULATED into the
         clock: an answer that takes 40 s is executed 40 s after the bar
  stub   no model: takes every candidate after a fixed 2 s "answer" —
         tests the platform without the GPU
  all    take every candidate instantly (the strategy baseline)

Platform checks per day (the strategy's results are reported, not judged):
  DATA     bars stored for the day, gaps > 5 min outside the daily break,
           clock (gold's daily break at 17:00 New York)
  CRASH    any exception inside the pipeline (caught per bar, counted, first
           traceback kept) — the platform must never stop on a bad bar
  MODEL    answers valid %, the reasons for invalid ones (unreachable, out of
           tokens, contract), latency p50 / p95 / max
  WINDOW   approvals that arrived after the entry window closed (the model was
           too slow for the trade), and how much window was left
  PROMPT   largest prompt vs the byte budget, prompts that had to be trimmed
  RULES    trading/verify.py on the day's decisions and trades
  EXEC     executor refusals by reason; intents that are neither filled nor refused
  BOOK     positions still open at the end of the day

Output: ``runs/daytest/<stamp>/`` — ``day-YYYY-MM-DD.json`` per day,
``summary.md`` (one line per day + every issue found), ``decisions.jsonl``
(every decision with the model's raw answer). The folder is not in git.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
import time
import traceback
from collections import Counter
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))            # backend/

from structure_engine.config import load_config  # noqa: E402
from structure_engine.engine import StructureEngine  # noqa: E402

from strategy import load as load_strategy  # noqa: E402
from trading.broker import PaperBroker  # noqa: E402
from trading.executor import Executor  # noqa: E402
from trading.journal import MemoryJournal  # noqa: E402
from trading.pipeline import Pipeline  # noqa: E402
from trading.risk import XAUUSD_DEFAULT  # noqa: E402
from trading.settings import load_settings  # noqa: E402
from trading.verify import verify  # noqa: E402

DAY = 86400
REPO = Path(__file__).resolve().parents[2]


def stub_decider(latency_ms: int = 2000):
    """Platform test without a model: take the first candidate, 'answer' after latency_ms."""
    from llm.contract import Verdict
    from llm.decider import Decision

    def decide(prompt, strategy):
        label = next(iter(prompt.candidate_map))
        v = Verdict("take", label, prompt.candidate_map[label], 75, (f"{label}.rejection",), (), "stub")
        return Decision(v, "stub", "stub", latency_ms, json.dumps({"decision": label}))
    return decide


def day_of(t: int) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(t))


def trading_day(t: int) -> str:
    """Gold's trading day: 17:00 New York to 17:00 New York, named by the day it ENDS
    (Sunday-evening bars belong to Monday, as on every trading platform)."""
    from structure_engine.clock import anchored_day
    return day_of(anchored_day(t, "America/New_York", 17)[1] - 1)


def _pct(v: list, q: float):
    if not v:
        return None
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * q))]


class DayTest:
    def __init__(self, lane: str, out: Path, balance: float = 10_000.0, spread: float = 0.2) -> None:
        self.settings = load_settings()
        self.strategy = load_strategy(self.settings.strategy, self.settings.strategy_version)
        self.engine = StructureEngine(load_config())
        self.broker = PaperBroker(XAUUSD_DEFAULT, balance=balance, spread=spread)
        self.journal = MemoryJournal()
        self.executor = Executor(self.broker, replace(self.settings, mode="paper"), "XAUUSD", self.journal)
        if lane == "llm":
            from llm.decider import LLMDecider
            decider = LLMDecider()
        elif lane == "stub":
            decider = stub_decider()
        else:
            from llm.decider import take_all
            decider = take_all
        self.lane = lane
        self.pipe = Pipeline(self.strategy, self.engine, decider, self.executor, self.journal,
                             mode=f"daytest-{lane}", simulate_latency=lane != "all")
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.days: list[dict] = []
        self._decision_file = (out / "decisions.jsonl").open("w", encoding="utf-8")

    # ------------------------------------------------------------------ one day
    def run_day(self, date: str, bars: list) -> dict:
        n_dec, n_diag = len(self.journal.decisions), len(self.pipe.diagnostics)
        n_ref, trades_before = len(self.journal.refusals), set(self.journal.trades)
        stats_before = dict(self.pipe.stats)
        crashes, first_tb = 0, None
        for bar in bars:
            events = self.engine.push(bar)
            self.broker.on_bar(bar)
            try:
                self.pipe.on_bar(bar, events, self.engine.now)
            except Exception:                                   # the platform must survive any bar
                crashes += 1
                first_tb = first_tb or traceback.format_exc()
        decisions = self.journal.decisions[n_dec:]
        diags = self.pipe.diagnostics[n_diag:]
        refusals = self.journal.refusals[n_ref:]
        new_trades = [t for k, t in self.journal.trades.items() if k not in trades_before]
        delta = {k: self.pipe.stats[k] - stats_before.get(k, 0) for k in self.pipe.stats
                 if isinstance(self.pipe.stats[k], int) and k != "max_prompt_bytes"}
        for d in decisions:
            self._decision_file.write(json.dumps({k: d.get(k) for k in (
                "id", "time", "action", "label", "candidate_key", "confidence", "cites", "why", "errors",
                "latency_ms", "prompt_bytes", "model", "model_digest", "raw_answer")}) + "\n")
        self._decision_file.flush()

        issues: list[str] = []
        # DATA
        times = [b.time for b in bars]
        gaps = []
        from quantllm.replay import clock_check
        clock = clock_check(times)
        breaks = {x["utc"] for x in clock["breaks"]}
        for a, b in zip(times, times[1:]):
            if b - a > 300 and (a + 60) not in breaks:
                gaps.append((day_of(a) + time.strftime(" %H:%M", time.gmtime(a + 60)), (b - a) // 60 - 1))
        if len(bars) < 600:
            issues.append(f"DATA only {len(bars)} M1 bars stored for the day")
        if gaps:
            issues.append(f"DATA {len(gaps)} gap(s) > 5 min, e.g. {gaps[0][0]} ({gaps[0][1]} min missing)")
        if not clock["ok"]:
            issues.append("DATA bar times not UTC: daily break at "
                          + ", ".join(x["ny"] for x in clock["breaks"] if not x["ok"]) + " New York")
        # CRASH
        if crashes:
            issues.append(f"CRASH {crashes} bar(s) raised inside the pipeline: "
                          + first_tb.strip().splitlines()[-1])
        # MODEL
        lat = [x["latency_s"] for x in diags if x["latency_s"] is not None]
        invalid = [d for d in decisions if d["action"] == "invalid"]
        reasons = Counter(e.split(":")[0][:80] for d in invalid for e in d.get("errors") or ["?"])
        if decisions and invalid:
            issues.append(f"MODEL {len(invalid)}/{len(decisions)} invalid answers: "
                          + "; ".join(f"{r} x{n}" for r, n in reasons.most_common(3)))
        # WINDOW
        late = [x for x in diags if x["window_left_s"] is not None and x["window_left_s"] < 0]
        if late:
            issues.append(f"WINDOW {len(late)} approval(s) arrived after the entry window closed "
                          f"(latency up to {max(x['latency_s'] for x in late):.0f} s)")
        # PROMPT
        max_bytes = max((x["prompt_bytes"] for x in diags), default=0)
        trimmed = sum(1 for x in diags if any(x["trimmed"].values()))
        if max_bytes > self.strategy.prompt["max_bytes"]:
            issues.append(f"PROMPT {max_bytes} bytes > budget {self.strategy.prompt['max_bytes']}")
        if delta.get("too_large"):
            issues.append(f"PROMPT {delta['too_large']} prompt(s) too large even after trimming")
        # RULES (on this day's records only)
        day_journal = MemoryJournal()
        day_journal.decisions = decisions
        day_journal.trades = {t["id"]: t for t in new_trades}
        for f in verify(self.strategy, self.settings, day_journal):
            if not f.startswith("T6"):                     # T6 needs the whole book: checked at the end
                issues.append(f"RULES {f}")
        # EXEC
        ref_reasons = Counter(r["reason"].split(" (")[0][:60] for r in refusals)
        accounted = delta.get("filled", 0) + delta.get("refused", 0)
        if accounted != delta.get("intents", 0):
            issues.append(f"EXEC {delta.get('intents', 0)} intents but {accounted} filled + refused")
        errors = [r for r in refusals if r["status"] == "error"]
        if errors:
            issues.append(f"EXEC {len(errors)} broker error(s): {errors[0]['reason'][:80]}")
        # BOOK
        open_now = self.broker.positions("XAUUSD", self.settings.magic)
        closed = [t for t in new_trades if t.get("r_multiple") is not None]
        rep = {
            "date": date, "lane": self.lane, "bars": len(bars),
            "prompts": delta.get("prompts", 0), "take": delta.get("take", 0), "wait": delta.get("wait", 0),
            "invalid": delta.get("invalid", 0), "intents": delta.get("intents", 0),
            "filled": delta.get("filled", 0), "refused": delta.get("refused", 0),
            "refusal_reasons": dict(ref_reasons), "late_approvals": len(late),
            "latency_s": {"p50": _pct(lat, 0.5), "p95": _pct(lat, 0.95), "max": max(lat, default=None)},
            "window_left_s_min": min((x["window_left_s"] for x in diags if x["window_left_s"] is not None),
                                     default=None),
            "max_prompt_bytes": max_bytes, "trimmed_prompts": trimmed, "crashes": crashes,
            "first_traceback": first_tb, "open_positions_end": len(open_now),
            "trades_opened": len(new_trades), "trades_closed": len(closed),
            "r_today": round(sum(t["r_multiple"] for t in closed), 2) if closed else 0.0,
            "balance": round(self.broker.balance, 2), "issues": issues,
        }
        (self.out / f"day-{date}.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
        self.days.append(rep)
        return rep

    def finish(self) -> Path:
        self._decision_file.close()
        book = [f for f in verify(self.strategy, self.settings, self.journal) if f.startswith("T6")]
        lines = [f"# Day-by-day platform test — lane `{self.lane}`, strategy `{self.strategy.ref}`", "",
                 "| day | bars | prompts | take/wait/invalid | latency p50/p95/max s | late | filled/refused "
                 "| trades | R | issues |", "|---|---|---|---|---|---|---|---|---|---|"]
        for d in self.days:
            lt = d["latency_s"]
            fmt = lambda x: "-" if x is None else f"{x:.1f}"                     # noqa: E731
            lines.append(f"| {d['date']} | {d['bars']} | {d['prompts']} | {d['take']}/{d['wait']}/{d['invalid']} "
                         f"| {fmt(lt['p50'])}/{fmt(lt['p95'])}/{fmt(lt['max'])} | {d['late_approvals']} "
                         f"| {d['filled']}/{d['refused']} | {d['trades_closed']} | {d['r_today']:+.2f} "
                         f"| {len(d['issues'])} |")
        all_issues = [(d["date"], i) for d in self.days for i in d["issues"]] + [("whole run", f"RULES {f}")
                                                                                  for f in book]
        kinds = Counter(i.split(" ")[0] for _, i in all_issues)
        lines += ["", f"## Issues: {len(all_issues)} ({', '.join(f'{k} {n}' for k, n in kinds.most_common()) or 'none'})",
                  ""] + [f"- **{day}** {i}" for day, i in all_issues]
        trades = [t for t in self.journal.trades.values() if t.get("r_multiple") is not None]
        lines += ["", "## Strategy (information only — the platform comes first)", "",
                  f"- trades {len(trades)}, total {sum(t['r_multiple'] for t in trades):+.2f} R, "
                  f"paper balance 10,000 -> {self.broker.balance:,.2f}",
                  f"- decisions {len(self.journal.decisions)}: " + ", ".join(
                      f"{k} {v}" for k, v in Counter(d['action'] for d in self.journal.decisions).items())]
        path = self.out / "summary.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path


def trading_days(bars, start: int, end: int):
    """Yield (trading day, [bars]) for bars in [start, end); bars before start come first as warm-up."""
    warm, cur, buf = [], None, []
    for b in bars:
        if b.time < start:
            warm.append(b)
            continue
        if b.time >= end:
            break
        d = trading_day(b.time)
        if warm:
            yield "warm-up", warm
            warm = []
        if cur is not None and d != cur:
            yield cur, buf
            buf = []
        cur = d
        buf.append(b)
    if warm:
        yield "warm-up", warm
    if buf:
        yield cur, buf


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m trading.daytest", description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="*")
    ap.add_argument("--db", action="store_true")
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True, help="exclusive")
    ap.add_argument("--lane", choices=("llm", "stub", "all"), default="llm")
    ap.add_argument("--day", help="report only this day (the run still warms up and runs up to it)")
    ap.add_argument("--pause", action="store_true", help="wait for Enter after each day")
    ap.add_argument("--out")
    a = ap.parse_args()
    from structure_engine.clock import anchored_day
    noon = lambda d: calendar.timegm(time.strptime(d, "%Y-%m-%d")) + 12 * 3600       # noqa: E731
    start = anchored_day(noon(a.start), "America/New_York", 17)[0]    # 17:00 NY the evening before
    end = anchored_day(noon(a.end), "America/New_York", 17)[0]
    warm = start - 10 * DAY
    if a.db:
        from quantllm import mt5_connection
        from quantllm.database import Database
        from quantllm.settings import load_settings as app_settings
        st = app_settings()
        bars = Database(st.db_dsn, st.db_schema).iter_candles(mt5_connection.settings().broker_symbol, warm)
    elif a.m1:
        from structure_engine.feeds import RecordedFeed
        bars = (b for b in RecordedFeed(a.m1) if b.time >= warm)
    else:
        sys.exit("give --db or --m1 <files/folders>")
    if a.lane == "llm":
        from llm import LLMClient, LLMError
        try:
            info = LLMClient().ping()
            print(f"model: {info.get('identity') or info['model']} at {info['url']}, "
                  f"reasoning {info['reasoning_effort']}")
        except LLMError as exc:
            sys.exit(f"model server not reachable ({exc}). Start Start-LLM.bat, or use --lane stub.")
    out = Path(a.out) if a.out else REPO / "runs" / "daytest" / time.strftime("%Y%m%d-%H%M%S")
    dt = DayTest(a.lane, out)
    print(f"reports -> {out}")
    for date, day_bars in trading_days(bars, start, end):
        if date == "warm-up":
            for b in day_bars:
                ev = dt.engine.push(b)
                dt.broker.on_bar(b)
                dt.pipe.runner.observe(ev, dt.engine.snapshot, dt.engine.now)   # level history, no trading
            print(f"warm-up: {len(day_bars)} bars")
            continue
        r = dt.run_day(date, day_bars)
        if a.day and date != a.day:
            continue
        lt = r["latency_s"]
        print(f"{date}  bars {r['bars']:>4}  prompts {r['prompts']:>3}  take/wait/invalid "
              f"{r['take']}/{r['wait']}/{r['invalid']}  latency p95 {lt['p95'] or '-'} s  "
              f"filled {r['filled']} refused {r['refused']}  R {r['r_today']:+.2f}  "
              f"issues {len(r['issues'])}")
        for i in r["issues"]:
            print(f"    - {i}")
        if a.pause:
            input("    Enter for the next day... ")
    print(f"\nsummary: {dt.finish()}")


if __name__ == "__main__":
    main()
