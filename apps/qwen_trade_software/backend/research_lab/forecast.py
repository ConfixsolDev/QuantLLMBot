"""Stage 1: forecasts at every decision point (the expensive part).

    # on the trading PC, AMD GPU through DirectML:
    python -m research_lab.forecast --m1 <M1 folder> --decisions lab_runs/real/decisions.jsonl \\
        --forecaster kronos --device dml --kronos-repo C:\\Kronos --out lab_runs/real/forecasts_kronos.jsonl
    # anywhere, the no-skill yardstick:
    python -m research_lab.forecast --m1 <M1 folder> --decisions lab_runs/real/decisions.jsonl \\
        --forecaster bootstrap --out lab_runs/real/forecasts_bootstrap.jsonl

For each decision and each forecast timeframe (M1, M30, H1, H4 by default)
the forecaster gets that timeframe's CLOSED candles up to the decision
(rebuilt exactly as the structure engine builds them, New York H4 included)
and returns N paths. Only summaries are stored:

    p_up            share of paths whose final close is above the last close
    p_up_1          same after the first candle
    q10/q50/q90     final close change, in H1 ATR
    p_barrier_up    share of paths touching +barrier x ATR(H1) before
                    -barrier x ATR(H1) (H1 paths; ties count half; neither = no vote)
    p_spike_rev     at close spikes: share of paths whose final close is back
                    beyond the spike's start

The run is RESUMABLE: decisions already in the output file are skipped, so a
long Kronos run can be stopped and restarted.
"""

from __future__ import annotations

import argparse
import bisect
import json
import statistics
import time
from pathlib import Path

from structure_engine.config import load_config as load_structure_config
from structure_engine.engine import closed_bars_by_timeframe
from structure_engine.feeds import RecordedFeed

from .config import load_lab_config
from .forecasters import BootstrapForecaster, KronosForecaster


def summarize(paths, last_close: float, atr: float, barrier: float, spike: dict | None) -> dict:
    finals = [p[-1][3] for p in paths]
    firsts = [p[0][3] for p in paths]
    rets = sorted((f - last_close) / atr for f in finals)
    q = lambda x: rets[min(len(rets) - 1, int(x * len(rets)))]  # noqa: E731
    out = {"p_up": sum(f > last_close for f in finals) / len(finals),
           "p_up_1": sum(f > last_close for f in firsts) / len(firsts),
           "q10": q(0.1), "q50": statistics.median(rets), "q90": q(0.9)}
    up, dn = last_close + barrier * atr, last_close - barrier * atr
    votes = []
    for p in paths:
        for _o, h, l, _c in p:
            if h >= up and l <= dn:
                votes.append(0.5)
                break
            if h >= up:
                votes.append(1.0)
                break
            if l <= dn:
                votes.append(0.0)
                break
    out["p_barrier_up"] = sum(votes) / len(votes) if votes else None
    out["barrier_votes"] = len(votes) / len(paths)
    if spike:
        rev = [(f <= spike["ref"]) if spike["direction"] == "up" else (f >= spike["ref"]) for f in finals]
        out["p_spike_rev"] = sum(rev) / len(rev)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="+", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--forecaster", choices=("kronos", "bootstrap"), required=True)
    ap.add_argument("--device", default="cpu", help="cpu | dml (AMD on Windows) | cuda:0")
    ap.add_argument("--kronos-repo", default="C:\\Kronos")
    ap.add_argument("--lab-config", default=None)
    ap.add_argument("--structure-config", default=None)
    ap.add_argument("--limit", type=int, default=0, help="only the first N decisions (quick test)")
    args = ap.parse_args()

    lab = load_lab_config(args.lab_config)
    fc = lab["forecast"]
    rows = [json.loads(x) for x in open(args.decisions, encoding="utf-8")]
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out)
    done = set()
    if out.exists():
        done = {json.loads(x)["t"] for x in out.open(encoding="utf-8")}
    todo = [r for r in rows if r["t"] not in done]
    print(f"{len(rows)} decisions, {len(done)} already forecast, {len(todo)} to go")
    if not todo:
        return
    if args.forecaster == "kronos":
        model = KronosForecaster(args.kronos_repo, fc["kronos_model"], fc["kronos_tokenizer"], args.device,
                                 fc["max_context"], fc["temperature"], fc["top_p"])
    else:
        model = BootstrapForecaster()
    by_tf = closed_bars_by_timeframe(RecordedFeed(args.m1), load_structure_config(args.structure_config))
    close_times = {tf: [b.close_time for b in bars] for tf, bars in by_tf.items()}
    started = time.time()
    with out.open("a", encoding="utf-8") as fh:
        for n, r in enumerate(todo, 1):
            rec = {"t": r["t"], "forecaster": model.name, "lab_hash": lab["_hash"], "tf": {}}
            for tf, spec in fc["timeframes"].items():
                i = bisect.bisect_right(close_times[tf], r["t"])
                ctx = by_tf[tf][max(0, i - spec["lookback"]): i]
                if len(ctx) < max(32, spec["lookback"] // 2):
                    continue                                  # not enough history yet
                step = ctx[-1].minutes * 60
                future = [ctx[-1].time + step * (k + 1) for k in range(spec["horizon"])]
                paths = model.sample(ctx, future, fc["paths"], fc["seed"] + r["t"] % 1_000_003)
                rec["tf"][tf] = summarize(paths, ctx[-1].close, r["atr_h1"], lab["barrier_atr"], r.get("spike"))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if n % 25 == 0 or n == len(todo):
                rate = (time.time() - started) / n
                print(f"  {n}/{len(todo)}  {rate:.1f}s per decision, ~{rate * (len(todo) - n) / 60:.0f} min left")


if __name__ == "__main__":
    main()
