"""Build the Qwen test dataset: every prompt the live system WOULD send, plus hidden outcomes.

    python -m strategy.dataset --m1 <files/folders> --from 2026-05-01 --to 2026-08-08 --out <dir>
    python -m strategy.dataset --db --from 2026-08-01 --to 2026-11-01 --out ..\\data\\qwen_dataset

Output folder:

  system.txt       the system message (identical for every prompt of this strategy version)
  prompts.jsonl    one line per decision point: id, time, strategy, bytes, the exact USER
                   message, candidate_map (C1 -> key), evidence_map (E1 -> engine event id)
  labels.jsonl     one line per prompt id: what happened to each candidate if it had been
                   taken. NEVER part of a prompt — this is the answer key:
                     r            result in R (stop/target/stalled close/time-out, spread paid)
                     exit         stop | target | stalled | timeout
                     mfe_atr / mae_atr   best / worst excursion in ATR(M15) within 60 M1 bars
                     followthrough       moved | stalled (engine event 3 bars after the rejection)
                     level_outcome       held | broken | open (that test of the level)
  summary.json     counts, prompt sizes, take-every-candidate result, per month

Prompts are built by exactly the code the live pipeline uses (strategy/runner.py
+ strategy/template.py), at exactly the moment it would ask. Candidates are
labelled independently (no "one position at a time" interference), so every
prompt has an answer key.
"""

from __future__ import annotations

import argparse
import calendar
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from . import load, template  # noqa: E402
from .runner import StrategyRunner  # noqa: E402

MAX_HOLD_BARS = 480            # time-out: 8 hours
EXCURSION_BARS = 60


class Labeller:
    """Follows each offered candidate forward on M1 bars until its simulated trade ends."""

    def __init__(self, spread: float) -> None:
        self.spread = spread
        self.open: list[dict] = []
        self.done: dict[str, dict] = {}            # prompt id -> {label: outcome}

    def start(self, pid: str, label: str, key: str, intent, atr: float, now: int) -> None:
        s = 1 if intent.side == "buy" else -1
        ref = intent.meta["rejection_candle"]["close"]
        entry = ref + (self.spread if s > 0 else 0.0)           # buys pay the spread at entry
        self.open.append({"pid": pid, "label": label, "key": key, "s": s, "entry": entry, "stop": intent.stop,
                          "target": intent.target, "atr": atr, "risk": abs(entry - intent.stop), "bars": 0,
                          "mfe": 0.0, "mae": 0.0, "opened": now, "out": None, "ft": None, "lvl": "open"})

    def on_bar(self, bar, events) -> None:
        ft = {}
        lvl = {}
        for e in events:
            d = e.data
            if e.kind == "level_followthrough":
                ft[f"{d['level']['id']}:{d['test_no']}"] = d["result"]
            elif e.kind == "level_held":
                lvl[f"{d['level']['id']}:{d['test_no']}"] = "held"
            elif e.kind == "level_broken" and d.get("during_test"):
                lvl[f"{d['level']['id']}:{d['during_test']}"] = "broken"
        for t in self.open:
            if t["key"] in ft and t["ft"] is None:
                t["ft"] = ft[t["key"]]
            if t["key"] in lvl:
                t["lvl"] = lvl[t["key"]]
            if t["out"] is not None:
                continue
            t["bars"] += 1
            s = t["s"]
            hi, lo = bar.high + (self.spread if s < 0 else 0), bar.low + (self.spread if s < 0 else 0)
            fav = (hi - t["entry"]) if s > 0 else (t["entry"] - lo)
            adv = (t["entry"] - lo) if s > 0 else (hi - t["entry"])
            if t["bars"] <= EXCURSION_BARS:
                t["mfe"], t["mae"] = max(t["mfe"], fav), max(t["mae"], adv)
            if (s > 0 and lo <= t["stop"]) or (s < 0 and hi >= t["stop"]):
                t["out"] = ("stop", t["stop"])
            elif (s > 0 and hi >= t["target"]) or (s < 0 and lo <= t["target"]):
                t["out"] = ("target", t["target"])
            elif t["ft"] == "stalled":
                t["out"] = ("stalled", bar.close + (self.spread if s < 0 else 0))
            elif t["bars"] >= MAX_HOLD_BARS:
                t["out"] = ("timeout", bar.close + (self.spread if s < 0 else 0))
        keep = []
        for t in self.open:
            finished = t["out"] is not None and t["bars"] >= EXCURSION_BARS and t["lvl"] != "open"
            if finished or t["bars"] >= MAX_HOLD_BARS:
                self._finish(t)
            else:
                keep.append(t)
        self.open = keep

    def _finish(self, t: dict) -> None:
        exit_kind, price = t["out"] or ("timeout", t["entry"])
        r = t["s"] * (price - t["entry"]) / t["risk"] if t["risk"] else 0.0
        self.done.setdefault(t["pid"], {})[t["label"]] = {
            "key": t["key"], "r": round(r, 3), "exit": exit_kind, "mfe_atr": round(t["mfe"] / t["atr"], 2),
            "mae_atr": round(t["mae"] / t["atr"], 2), "followthrough": t["ft"], "level_outcome": t["lvl"]}

    def flush(self) -> None:
        for t in self.open:
            self._finish(t)
        self.open = []


def build(bars, out: Path, start: int | None, end: int | None, strategy_id: str = "htf_level_m1_rejection",
          spread: float = 0.2) -> dict:
    from structure_engine.config import load_config
    from structure_engine.engine import StructureEngine
    s = load(strategy_id)
    engine = StructureEngine(load_config())
    runner = StrategyRunner(s, engine._session_name)
    lab = Labeller(spread)
    out.mkdir(parents=True, exist_ok=True)
    (out / "system.txt").write_text(template.system_message(s), encoding="utf-8")
    sizes, months, n = [], Counter(), 0
    with (out / "prompts.jsonl").open("w", encoding="utf-8") as pf:
        for bar in bars:
            if end is not None and bar.time >= end:
                break
            events = engine.push(bar)
            lab.on_bar(bar, events)
            step = runner.observe(events, engine.snapshot, engine.now)
            if not step.asks:
                continue
            if start is not None and bar.time < start:
                for c in step.asks:
                    runner.refuse(c.key, "warm-up")
                continue
            try:
                p = template.build(s, engine, runner, step.asks, engine.now)
            except (template.NothingToAsk, template.PromptTooLarge):
                for c in step.asks:
                    runner.refuse(c.key, "dataset")
                continue
            for c in step.asks:
                runner.refuse(c.key, "dataset")          # labels are simulated independently
            n += 1
            pid = f"{s.id}-v{s.version}-{engine.now}-{p.sha[:6]}"
            pf.write(json.dumps({"id": pid, "time": engine.now, "strategy": s.ref, "bytes": p.bytes,
                                 "user": p.user, "candidate_map": p.candidate_map,
                                 "evidence_map": p.evidence_map}, ensure_ascii=False) + "\n")
            sizes.append(p.bytes)
            months[time.strftime("%Y-%m", time.gmtime(engine.now))] += 1
            for label, key in p.candidate_map.items():
                cand = next(c for c in step.asks if c.key == key)
                lab.start(pid, label, key, p.previews[label], cand.atr, engine.now)
    lab.flush()
    with (out / "labels.jsonl").open("w", encoding="utf-8") as lf:
        for pid, cands in lab.done.items():
            lf.write(json.dumps({"id": pid, "candidates": cands}) + "\n")
    rs = [c["r"] for v in lab.done.values() for c in v.values()]
    by_exit = defaultdict(list)
    for v in lab.done.values():
        for c in v.values():
            by_exit[c["exit"]].append(c["r"])
    summary = {
        "strategy": s.ref, "prompts": n, "candidates_labelled": len(rs), "per_month": dict(months),
        "prompt_bytes": {"median": statistics.median(sizes) if sizes else None, "max": max(sizes, default=None),
                         "limit": s.prompt["max_bytes"]},
        "take_every_candidate": {"n": len(rs), "avg_r": round(statistics.mean(rs), 3) if rs else None,
                                 "win": round(sum(r > 0 for r in rs) / len(rs), 3) if rs else None,
                                 "total_r": round(sum(rs), 1)},
        "by_exit": {k: {"n": len(v), "avg_r": round(statistics.mean(v), 2)} for k, v in by_exit.items()},
        "spread": spread}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _day(s: str | None) -> int | None:
    return calendar.timegm(time.strptime(s, "%Y-%m-%d")) if s else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m strategy.dataset", description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="*")
    ap.add_argument("--db", action="store_true")
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end")
    ap.add_argument("--out", required=True)
    ap.add_argument("--spread", type=float, default=0.2)
    a = ap.parse_args()
    start, end = _day(a.start), _day(a.end)
    warm = start - 10 * 86400
    if a.db:
        from quantllm import mt5_connection
        from quantllm.database import Database
        from quantllm.settings import load_settings
        st = load_settings()
        bars = Database(st.db_dsn, st.db_schema).iter_candles(mt5_connection.settings().broker_symbol, warm)
    elif a.m1:
        from structure_engine.feeds import RecordedFeed
        bars = (b for b in RecordedFeed(a.m1) if b.time >= warm)
    else:
        sys.exit("give --m1 <files/folders> or --db")
    print(json.dumps(build(bars, Path(a.out), start, end, spread=a.spread), indent=2))


if __name__ == "__main__":
    main()
