"""Stage 0: decision points, structure features and outcome labels.

    python -m research_lab.dataset --m1 <M1 folder> --out lab_runs/real

Decision points = every normal CLOSE of a ``decision_timeframe`` candle (H1
by default). At each one we store the structure features (features.py) — the
"without Kronos" information set — and, from the FUTURE M1 bars, the labels
the models are scored on:

    dir_1h        did price close higher 60 minutes later?          (1 / 0)
    dir_4h        ... 240 minutes later?                             (1 / 0)
    barrier_4h    within 240 minutes, did price touch
                  +barrier_atr x ATR(H1) BEFORE -barrier_atr x ATR(H1)?
                  (1 / 0; None when neither or both inside one minute)
    spike_rev_60  only at close spikes: 60 minutes later, is price back
                  beyond the spike's start?                          (1 / 0)

Each label records when it becomes known (decision time + horizon). The
comparison only trains on labels already known at the moment it predicts —
no look-ahead in the learning either.
"""

from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path

from structure_engine.config import load_config as load_structure_config
from structure_engine.engine import StructureEngine
from structure_engine.feeds import RecordedFeed

from .config import load_lab_config
from .features import FeatureBuilder


def build_decisions(m1_bars, scfg, lab) -> list[dict]:
    """Replay the engine once; capture features at every decision close."""
    engine = StructureEngine(scfg)
    fb = FeatureBuilder(engine)
    dtf = lab["decision_timeframe"]
    rows = []
    for bar in m1_bars:
        events = engine.push(bar)
        fb.on_events(bar, events)
        closed = engine.closed_now.get(dtf, [])
        if not closed or closed[-1].close_time != engine.now or closed[-1].m1_count < closed[-1].minutes:
            continue                                      # only normal, complete closes
        f = fb.build()
        if f is None:
            continue
        row = {"t": engine.now, "price": bar.close, "atr_h1": engine.atr["H1"].value, "features": f}
        sp = [e for e in events if e.kind == "close_spike"]
        if sp:
            d = sp[-1].data
            row["spike"] = {"direction": d["direction"], "ref": d["ref"], "extreme": d["extreme"], "move": d["move"]}
        rows.append(row)
    return rows


def add_labels(rows: list[dict], m1_bars, lab) -> None:
    """Fill ``labels`` and ``label_known_at`` from future M1 bars (offline)."""
    times = [b.close_time for b in m1_bars]
    tol = lab["label_tolerance_minutes"] * 60
    k = lab["barrier_atr"]
    for r in rows:
        t, p = r["t"], r["price"]
        labels, known = {}, {}
        for name, minutes in (("dir_1h", 60), ("dir_4h", 240)):
            i = bisect.bisect_left(times, t + minutes * 60)
            ok = i < len(times) and times[i] - (t + minutes * 60) <= tol
            labels[name] = (1 if m1_bars[i].close > p else 0) if ok else None
            known[name] = t + minutes * 60
        # first-touch barrier
        up, dn = p + k * r["atr_h1"], p - k * r["atr_h1"]
        i = bisect.bisect_right(times, t)
        hit = None
        while i < len(times) and times[i] <= t + 240 * 60:
            b = m1_bars[i]
            if b.high >= up and b.low <= dn:
                break                                     # both in one minute: ambiguous
            if b.high >= up:
                hit = 1
                break
            if b.low <= dn:
                hit = 0
                break
            i += 1
        labels["barrier_4h"] = hit
        known["barrier_4h"] = t + 240 * 60
        if "spike" in r:
            s = r["spike"]
            i = bisect.bisect_left(times, t + 3600)
            if i < len(times) and times[i] - (t + 3600) <= tol:
                c = m1_bars[i].close
                labels["spike_rev_60"] = 1 if ((c <= s["ref"]) if s["direction"] == "up" else (c >= s["ref"])) else 0
            else:
                labels["spike_rev_60"] = None
            known["spike_rev_60"] = t + 3600
        r["labels"], r["label_known_at"] = labels, known


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="+", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lab-config", default=None)
    ap.add_argument("--structure-config", default=None)
    args = ap.parse_args()
    lab = load_lab_config(args.lab_config)
    scfg = load_structure_config(args.structure_config)
    bars = list(RecordedFeed(args.m1))
    rows = build_decisions(bars, scfg, lab)
    add_labels(rows, bars, lab)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "decisions.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({**r, "structure_config_hash": scfg.config_hash}) + "\n")
    print(f"{len(rows)} decision points -> {out / 'decisions.jsonl'}")


if __name__ == "__main__":
    main()
