"""Trade geometry study: which stop / target / management turns the candidates into the best trades?

    python -m studies.trade_geometry --dataset <qwen dataset dir> --m1 <bars>
    python -m studies.trade_geometry --dataset ..\\data\\qwen_dataset\\<dir> --db

Takes EVERY candidate of a dataset built by ``python -m strategy.dataset``
(entry = close of the rejection candle, side, level, nearby levels from the
prompt itself — exactly what the live system knew) and replays the following
M1 bars under each variant:

  stop    atr1.0 / atr1.2      at least k x ATR(M15) from entry, never tighter than the rejection candle
          next-level           just beyond the next level of the same side (<= 3 ATR away), floor 1.2 ATR
          higher-level         same, but only H4 / day / week levels count ("one timeframe up")
  target  1R / 1.5R / 2R       multiples of the real risk
  manage  plain                stop or target only (8 h time-out)
          stalled              also close when the rejection stalled after 3 bars (v2 rule)
          breakeven            stop to entry + 0.05 R after +1 R

Reports per variant: trades, average R, win rate, total R, max drawdown (R),
the two halves of the period separately (a variant that only works in one half
is noise), and the average R of trades whose level HELD vs BROKE — the gap
between those two is what a good selector (Qwen) can capture.

Research only. Spread 0.2 is paid on every trade; no commission.
"""

from __future__ import annotations

import argparse
import bisect
import itertools
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HIGHER = ("H4", "DAY", "WEEK")
STOPS = ("atr1.0", "atr1.2", "next-level", "higher-level")
TARGETS = (1.0, 1.5, 2.0)
MANAGE = ("plain", "stalled", "breakeven")


def stop_price(u: dict, mode: str, spread: float) -> tuple[float, float, float, int]:
    c = u["candidates"][0]
    atr = u["market"]["atr"]["M15"]
    s = 1 if c["side"] == "buy" else -1
    entry = c["trade"]["entry"] + (spread if s > 0 else 0.0)
    struct = c["trade"]["stop"]                                     # beyond the rejection candle
    k = 1.0 if mode == "atr1.0" else 1.2
    base = entry - s * k * atr
    base = min(base, struct) if s > 0 else max(base, struct)
    if mode.startswith("atr"):
        return entry, base, atr, s
    want = "S" if s > 0 else "R"
    beyond = [lv["price"] for lv in u["market"]["levels"]
              if lv["side"] == want and not lv.get("beyond") and s * (entry - lv["price"]) > 0
              and abs(entry - lv["price"]) <= 3 * atr
              and (mode == "next-level" or any(h in lv["src"] for h in HIGHER))]
    if not beyond:
        return entry, base, atr, s
    lvl = max(beyond) if s > 0 else min(beyond)                     # the nearest one beyond
    st = lvl - s * 0.2 * atr
    return entry, (st if s * (entry - st) >= 1.2 * atr else base), atr, s


def simulate(prompt: dict, label: dict, bars, times, stop_mode: str, target_r: float, manage: str,
             spread: float) -> float:
    u = json.loads(prompt["user"])
    entry, stop, atr, s = stop_price(u, stop_mode, spread)
    risk = abs(entry - stop)
    target = entry + s * target_r * risk
    i = bisect.bisect_right(times, prompt["time"] - 60)
    cur = stop
    for j in range(i, min(len(bars), i + 480)):
        b = bars[j]
        hi, lo = b.high + (spread if s < 0 else 0), b.low + (spread if s < 0 else 0)
        if (s > 0 and lo <= cur) or (s < 0 and hi >= cur):
            return s * (cur - entry) / risk
        if (s > 0 and hi >= target) or (s < 0 and lo <= target):
            return target_r
        if manage == "breakeven" and s * ((hi if s > 0 else lo) - entry) >= risk:
            cur = entry + s * 0.05 * risk
        if manage == "stalled" and j - i == 2 and label["followthrough"] == "stalled":
            return s * (b.close + (spread if s < 0 else 0) - entry) / risk
    last = bars[min(len(bars) - 1, i + 479)]
    return s * (last.close + (spread if s < 0 else 0) - entry) / risk


def run(dataset: Path, bars, spread: float = 0.2) -> list[dict]:
    prompts = [json.loads(x) for x in (dataset / "prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = {json.loads(x)["id"]: json.loads(x)["candidates"]["C1"]
              for x in (dataset / "labels.jsonl").read_text(encoding="utf-8").splitlines()}
    prompts = [p for p in prompts if p["id"] in labels]
    times = [b.time for b in bars]
    mid = prompts[len(prompts) // 2]["time"] if prompts else 0
    out = []
    for stop_mode, tr, manage in itertools.product(STOPS, TARGETS, MANAGE):
        rows = [(p["time"], simulate(p, labels[p["id"]], bars, times, stop_mode, tr, manage, spread),
                 labels[p["id"]]["level_outcome"]) for p in prompts]
        rs = [r for _, r, _ in rows]
        eq = peak = dd = 0.0
        for r in rs:
            eq += r
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
        part = lambda f: [r for t, r, _ in rows if f(t)]                     # noqa: E731
        by = lambda o: [r for _, r, x in rows if x == o]                     # noqa: E731
        mean = lambda v: round(statistics.mean(v), 3) if v else None        # noqa: E731
        out.append({"stop": stop_mode, "target_r": tr, "manage": manage, "n": len(rs), "avg_r": mean(rs),
                    "win": round(sum(r > 0 for r in rs) / len(rs), 2), "total_r": round(sum(rs), 1),
                    "max_dd_r": round(dd, 1), "first_half": mean(part(lambda t: t < mid)),
                    "second_half": mean(part(lambda t: t >= mid)), "held": mean(by("held")),
                    "broken": mean(by("broken"))})
    return sorted(out, key=lambda r: -(r["avg_r"] or -9))


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m studies.trade_geometry")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--m1", nargs="*")
    ap.add_argument("--db", action="store_true")
    ap.add_argument("--spread", type=float, default=0.2)
    a = ap.parse_args()
    ds = Path(a.dataset)
    first = json.loads((ds / "prompts.jsonl").open(encoding="utf-8").readline())["time"]
    if a.db:
        from quantllm import mt5_connection
        from quantllm.database import Database
        from quantllm.settings import load_settings
        st = load_settings()
        bars = list(Database(st.db_dsn, st.db_schema).iter_candles(mt5_connection.settings().broker_symbol, first - 3600))
    else:
        from structure_engine.feeds import RecordedFeed
        bars = [b for b in RecordedFeed(a.m1) if b.time >= first - 3600]
    print(f"{'stop':<13}{'target':>6} {'manage':<10}{'n':>5}{'avgR':>8}{'win':>6}{'totalR':>8}{'maxDD':>7}"
          f"{'1st½':>8}{'2nd½':>8}{'held':>7}{'broken':>8}")
    for r in run(ds, bars, a.spread):
        print(f"{r['stop']:<13}{r['target_r']:>6} {r['manage']:<10}{r['n']:>5}{r['avg_r']:>+8.3f}{r['win']:>6.2f}"
              f"{r['total_r']:>+8.1f}{r['max_dd_r']:>7.1f}{r['first_half']:>+8.3f}{r['second_half']:>+8.3f}"
              f"{(r['held'] or 0):>+7.2f}{(r['broken'] or 0):>+8.2f}")


if __name__ == "__main__":
    main()
