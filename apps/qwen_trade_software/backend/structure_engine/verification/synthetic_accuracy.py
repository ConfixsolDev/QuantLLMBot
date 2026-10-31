"""Accuracy report on synthetic ground truth.

Run (from apps/qwen_trade_software/backend)::

    python -m structure_engine.verification.synthetic_accuracy --seeds 5
    python -m structure_engine.verification.synthetic_accuracy --seeds 5 --json report.json

What each line means
--------------------
swings   streaming detector vs the independent offline reference on random
         walks, every timeframe. Must be exactly 100% / 100%.
zones    planted base+departure zones per timeframe. "neg rejected" counts
         planted WEAK-departure look-alikes that were correctly NOT reported.
patterns planted double/triple tops & bottoms (confirmed by neckline close).
         "neg rejected" counts shallow-neckline and mismatched-peak
         look-alikes correctly NOT reported.
causality no-repaint over random cut points + determinism + invariants.

Synthetic accuracy proves the code does what the DEFINITIONS say. Whether
the definitions are useful on real gold is a separate question, answered by
point-in-time review on real XAUUSD (XAUUSD_SYSTEM_ARCHITECTURE_V3.md, Part B §B4).
"""

from __future__ import annotations

import argparse
import json

from ..engine import closed_bars_by_timeframe
from ..config import StructureConfig, load_config
from .causality import determinism, invariants, no_repaint, run
from .matching import Score, match
from .reference import reference_swings
from .synthetic import pattern_series, random_walk_m1, zone_series


def evaluate_swings(cfg: StructureConfig, seed: int) -> dict[str, Score]:
    bars = random_walk_m1(seed)
    events = [e for e in run(bars, cfg) if e.kind == "swing"]
    by_tf = closed_bars_by_timeframe(bars, cfg)      # incl. the New York H4 grid
    out = {}
    for tf in cfg.tf_minutes:
        tf_bars = by_tf[tf]
        truth = [{"kind": k, "time": t, "price": p}
                 for k, t, p in reference_swings(tf_bars, cfg["swings"]["strength"][tf])]
        det = [{"kind": e.data["kind"], "time": e.time, "price": e.data["price"]}
               for e in events if e.tf == tf]
        out[tf] = match(det, truth, time_tol=0, same=lambda d, t: d["kind"] == t["kind"]
                        and d["price"] == t["price"], price=lambda x: x["price"])
    return out


def evaluate_zones(cfg: StructureConfig, seed: int) -> dict[str, tuple[Score, int, int]]:
    out = {}
    for tf in cfg["zones"]["timeframes"]:
        minutes = cfg.tf_minutes[tf]
        syn = zone_series(seed, tf, minutes)
        det = [{"side": e.data["side"], "time": e.time, "mid": (e.data["low"] + e.data["high"]) / 2}
               for e in run(syn.m1, cfg) if e.kind == "zone_created" and e.tf == tf]
        truth = [{**t, "mid": (t["low"] + t["high"]) / 2} for t in syn.truth]
        tol = minutes * 60
        same = lambda d, t: d["side"] == t["side"]  # noqa: E731
        score = match(det, truth, time_tol=tol, same=same, price=lambda x: x["mid"])
        rejected = sum(1 for n in syn.negatives
                       if not any(same(d, n) and abs(d["time"] - n["time"]) <= tol for d in det))
        out[tf] = (score, rejected, len(syn.negatives))
    return out


def evaluate_patterns(cfg: StructureConfig, seed: int) -> tuple[Score, int, int]:
    syn = pattern_series(seed)
    det = [{"kind": e.data["kind"], "time": e.data["peaks"][0]["time"]}
           for e in run(syn.m1, cfg) if e.kind == "pattern_confirmed"]
    truth = [{"kind": t["kind"], "time": t["peak_times"][0]} for t in syn.truth]
    tol = 2 * 60
    score = match(det, truth, time_tol=tol, same=lambda d, t: d["kind"] == t["kind"])
    side = lambda k: k.split("_")[1]  # noqa: E731
    rejected = sum(1 for n in syn.negatives
                   if not any(side(d["kind"]) == side(n["kind"]) and abs(d["time"] - n["peak_times"][0]) <= tol
                              for d in det))
    return score, rejected, len(syn.negatives)


def report(seeds: int, cfg: StructureConfig | None = None) -> dict:
    cfg = cfg or load_config()
    swings: dict[str, Score] = {}
    zones: dict[str, list] = {}
    pat_score, pat_rej, pat_neg = None, 0, 0
    for seed in range(seeds):
        for tf, sc in evaluate_swings(cfg, seed).items():
            swings[tf] = sc if tf not in swings else swings[tf].merge(sc)
        for tf, (sc, rej, neg) in evaluate_zones(cfg, seed).items():
            if tf in zones:
                zones[tf] = [zones[tf][0].merge(sc), zones[tf][1] + rej, zones[tf][2] + neg]
            else:
                zones[tf] = [sc, rej, neg]
        sc, rej, neg = evaluate_patterns(cfg, seed)
        pat_score = sc if pat_score is None else pat_score.merge(sc)
        pat_rej += rej
        pat_neg += neg
    # causality on one mixed series (zones + patterns)
    bars = pattern_series(99).m1[:4000]
    repaint = no_repaint(bars, cfg, cuts=6)
    inv = invariants(run(zone_series(99, "M30", 30).m1, cfg), cfg) + invariants(run(bars, cfg), cfg)
    return {
        "config_id": cfg["config_id"], "config_hash": cfg.config_hash, "seeds": seeds,
        "swings": {tf: s.as_dict() for tf, s in swings.items()},
        "zones": {tf: {**v[0].as_dict(), "negatives_rejected": f"{v[1]}/{v[2]}"} for tf, v in zones.items()},
        "patterns": {**pat_score.as_dict(), "negatives_rejected": f"{pat_rej}/{pat_neg}"},
        "causality": {"no_repaint_failures": repaint, "deterministic": determinism(bars, cfg),
                      "invariant_violations": inv[:20]},
    }


def _print(rep: dict) -> None:
    print(f"Structure engine synthetic accuracy  config={rep['config_id']} hash={rep['config_hash']} seeds={rep['seeds']}")
    print(f"{'detector':<22}{'precision':>10}{'recall':>9}{'F1':>8}{'tp':>6}{'fp':>5}{'fn':>5}  extra")
    for tf, s in rep["swings"].items():
        print(f"{'swings ' + tf:<22}{s['precision']:>10.1%}{s['recall']:>9.1%}{s['f1']:>8.3f}{s['tp']:>6}{s['fp']:>5}{s['fn']:>5}")
    for tf, s in rep["zones"].items():
        print(f"{'zones ' + tf:<22}{s['precision']:>10.1%}{s['recall']:>9.1%}{s['f1']:>8.3f}{s['tp']:>6}{s['fp']:>5}{s['fn']:>5}"
              f"  neg rejected {s['negatives_rejected']}, mid err {s['price_err']}")
    s = rep["patterns"]
    print(f"{'patterns (M1)':<22}{s['precision']:>10.1%}{s['recall']:>9.1%}{s['f1']:>8.3f}{s['tp']:>6}{s['fp']:>5}{s['fn']:>5}"
          f"  neg rejected {s['negatives_rejected']}, time err {s['time_err_s']}s")
    c = rep["causality"]
    print(f"no-repaint: {'PASS' if not c['no_repaint_failures'] else 'FAIL ' + str(c['no_repaint_failures'])}"
          f" | deterministic: {'PASS' if c['deterministic'] else 'FAIL'}"
          f" | invariants: {'PASS' if not c['invariant_violations'] else 'FAIL ' + str(c['invariant_violations'][:3])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--config", default=None, help="alternative config JSON")
    ap.add_argument("--json", default=None, help="also write the report here")
    args = ap.parse_args()
    rep = report(args.seeds, load_config(args.config) if args.config else None)
    _print(rep)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=2)


if __name__ == "__main__":
    main()
