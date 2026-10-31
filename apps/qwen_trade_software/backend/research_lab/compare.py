"""Stage 2: compare WITHOUT Kronos, WITH Kronos, and XGBoost on top — fairly.

    python -m research_lab.compare --decisions lab_runs/real/decisions.jsonl \\
        --forecasts kronos=lab_runs/real/forecasts_kronos.jsonl \\
        --forecasts bootstrap=lab_runs/real/forecasts_bootstrap.jsonl \\
        --out lab_runs/real/report.json

Contenders, all predicting the same labels on the same decision points
---------------------------------------------------------------------
base_rate              how often the label was 1 so far (no information)
<fc>_raw               the forecaster's own probability (share of its paths)
xgb_structure          XGBoost on the deterministic structure features only
                       (= the system WITHOUT Kronos)
xgb_structure+<fc>     XGBoost on structure + that forecaster's features
                       (= the system WITH Kronos, or with the bootstrap control)

Why the bootstrap control matters: if "structure + bootstrap" improves as much
as "structure + Kronos", the gain came from giving XGBoost more volatility
numbers, not from Kronos knowing anything.

Walk-forward, no look-ahead
---------------------------
Decisions are processed in time order. The first ``initial_train_fraction``
is training-only. After that, every ``retrain_every`` decisions the models
are refit on all EARLIER decisions whose label was already known at that
moment (label_known_at <= now). Each test decision is predicted once, by a
model that never saw its future.

Scores (lower Brier / log-loss is better; AUC 0.5 = coin flip)
-------------------------------------------------------------
brier, logloss, auc, acc (at 0.5), skill = 1 - brier / brier(base_rate), and a
paired bootstrap of the Brier difference against xgb_structure: "better?" is
"yes" only when the 90 % interval lies entirely below zero.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from .config import load_lab_config

TARGETS = ("dir_1h", "dir_4h", "barrier_4h", "spike_rev_60")
# which forecast summary gives a forecaster's own probability for each target
RAW = {"dir_1h": ("H1", "p_up_1"), "dir_4h": ("H1", "p_up"), "barrier_4h": ("H1", "p_barrier_up"),
       "spike_rev_60": ("H1", "p_spike_rev")}
FC_STATS = ("p_up", "p_up_1", "q10", "q50", "q90", "p_barrier_up", "p_spike_rev")


# ---------------------------------------------------------------- metrics
def brier(p, y):
    return sum((a - b) ** 2 for a, b in zip(p, y)) / len(y)


def logloss(p, y):
    e = 1e-6
    return -sum(b * math.log(min(1 - e, max(e, a))) + (1 - b) * math.log(min(1 - e, max(e, 1 - a)))
                for a, b in zip(p, y)) / len(y)


def auc(p, y):
    pos = [a for a, b in zip(p, y) if b == 1]
    neg = [a for a, b in zip(p, y) if b == 0]
    if not pos or not neg:
        return None
    order = sorted(p)
    rank = {}
    i = 0
    while i < len(order):                       # average ranks for ties
        j = i
        while j + 1 < len(order) and order[j + 1] == order[i]:
            j += 1
        rank[order[i]] = (i + j) / 2 + 1
        i = j + 1
    s = sum(rank[a] for a in pos)
    return (s - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def paired_ci(pa, pb, y, n=400, seed=1):
    """90 % bootstrap interval of brier(a) - brier(b)."""
    rng = random.Random(seed)
    idx = list(range(len(y)))
    diffs = []
    for _ in range(n):
        s = [idx[rng.randrange(len(idx))] for _ in idx]
        diffs.append(sum((pa[i] - y[i]) ** 2 - (pb[i] - y[i]) ** 2 for i in s) / len(s))
    diffs.sort()
    return diffs[int(0.05 * n)], diffs[int(0.95 * n) - 1]


# ---------------------------------------------------------------- models
def make_model(xcfg):
    """XGBoost if available (and enabled), else scikit-learn's gradient boosting."""
    if xcfg["use_xgboost"]:
        try:
            import xgboost as xgb
            return xgb.XGBClassifier(
                n_estimators=xcfg["n_estimators"], max_depth=xcfg["max_depth"],
                learning_rate=xcfg["learning_rate"], subsample=xcfg["subsample"],
                colsample_bytree=xcfg["colsample_bytree"], min_child_weight=xcfg["min_child_weight"],
                reg_lambda=xcfg["reg_lambda"], eval_metric="logloss", n_jobs=2, verbosity=0)
        except ImportError:
            pass
    from sklearn.ensemble import HistGradientBoostingClassifier
    return HistGradientBoostingClassifier(max_depth=xcfg["max_depth"], learning_rate=xcfg["learning_rate"],
                                          max_iter=xcfg["n_estimators"])


def feature_matrix(rows, forecasts: dict[str, dict], use: list[str]):
    """Columns: structure features (+ forecaster summaries); NaN when missing."""
    cols = sorted(rows[0]["features"])
    fc_cols = [(name, tf, st) for name in use for tf in ("M1", "M30", "H1", "H4") for st in FC_STATS]
    X = []
    for r in rows:
        x = [float(r["features"][c]) for c in cols]
        for name, tf, st in fc_cols:
            v = forecasts[name].get(r["t"], {}).get(tf, {}).get(st)
            x.append(float("nan") if v is None else float(v))
        X.append(x)
    return X, cols + [f"{n}_{tf}_{st}" for n, tf, st in fc_cols]


def walk_forward(rows, target, X, wf, xcfg):
    """Return {test_index: probability}, refitting on known labels only."""
    n0 = int(len(rows) * wf["initial_train_fraction"])
    preds, model, since = {}, None, wf["retrain_every"]
    for i in range(n0, len(rows)):
        now = rows[i]["t"]
        if since >= wf["retrain_every"]:
            tr = [j for j in range(i) if rows[j]["labels"].get(target) is not None
                  and rows[j]["label_known_at"][target] <= now]
            ys = [rows[j]["labels"][target] for j in tr]
            model = None
            if len(tr) >= wf["min_train"] and 0 < sum(ys) < len(ys):
                model = make_model(xcfg)
                model.fit([X[j] for j in tr], ys)
            since = 0
        since += 1
        if model is not None and rows[i]["labels"].get(target) is not None:
            preds[i] = float(model.predict_proba([X[i]])[0][1])
    return preds


def running_base(rows, target, start):
    out, ones, n = {}, 0, 0
    known = sorted((r["label_known_at"][target], r["labels"][target]) for r in rows
                   if r["labels"].get(target) is not None)
    k = 0
    for i in range(start, len(rows)):
        now = rows[i]["t"]
        while k < len(known) and known[k][0] <= now:
            ones += known[k][1]
            n += 1
            k += 1
        if rows[i]["labels"].get(target) is not None:
            out[i] = ones / n if n else 0.5
    return out


def compare(rows, forecasts, lab) -> dict:
    rows = sorted(rows, key=lambda r: r["t"])
    wf, xcfg = lab["walk_forward"], lab["xgboost"]
    start = int(len(rows) * wf["initial_train_fraction"])
    report = {"decisions": len(rows), "test_from": rows[start]["t"] if rows else None,
              "forecasters": sorted(forecasts), "targets": {}}
    matrices = {"xgb_structure": feature_matrix(rows, forecasts, [])}
    for name in forecasts:
        matrices[f"xgb_structure+{name}"] = feature_matrix(rows, forecasts, [name])
    importances = {}
    for target in TARGETS:
        if not any(r["labels"].get(target) is not None for r in rows):
            continue
        contenders = {"base_rate": running_base(rows, target, start)}
        for name, fmap in forecasts.items():
            tf, st = RAW[target]
            contenders[f"{name}_raw"] = {i: fmap[rows[i]["t"]][tf][st] for i in range(start, len(rows))
                                         if rows[i]["labels"].get(target) is not None
                                         and fmap.get(rows[i]["t"], {}).get(tf, {}).get(st) is not None}
        for mname, (X, cols) in matrices.items():
            contenders[mname] = walk_forward(rows, target, X, wf, xcfg)
        # score every contender on the decisions they ALL predicted
        common = set.intersection(*(set(p) for p in contenders.values() if p)) if contenders else set()
        common = sorted(common)
        res = {"n": len(common)}
        if len(common) < 20:
            res["note"] = "too few scored decisions"
            report["targets"][target] = res
            continue
        y = [rows[i]["labels"][target] for i in common]
        ref = [contenders["xgb_structure"][i] for i in common] if contenders.get("xgb_structure") else None
        b0 = brier([contenders["base_rate"][i] for i in common], y)
        res["base_rate_of_1"] = round(sum(y) / len(y), 4)
        for cname, pmap in contenders.items():
            if not pmap:
                continue
            p = [pmap[i] for i in common]
            r = {"brier": round(brier(p, y), 5), "logloss": round(logloss(p, y), 5),
                 "auc": None if auc(p, y) is None else round(auc(p, y), 4),
                 "acc": round(sum((a >= 0.5) == (b == 1) for a, b in zip(p, y)) / len(y), 4),
                 "skill_vs_base": round(1 - brier(p, y) / b0, 4) if b0 else None}
            if ref is not None and cname != "xgb_structure":
                lo, hi = paired_ci(p, ref, y)
                r["brier_minus_structure_90ci"] = [round(lo, 5), round(hi, 5)]
                r["better_than_structure"] = "yes" if hi < 0 else ("worse" if lo > 0 else "no clear difference")
            res[cname] = r
        report["targets"][target] = res
    # feature importance of the richest model on dir_4h (what XGBoost relies on)
    try:
        name = max(matrices, key=lambda k: len(matrices[k][1]))
        X, cols = matrices[name]
        tr = [j for j, r in enumerate(rows) if r["labels"].get("dir_4h") is not None]
        if len(tr) >= wf["min_train"]:
            m = make_model(xcfg)
            m.fit([X[j] for j in tr], [rows[j]["labels"]["dir_4h"] for j in tr])
            if hasattr(m, "feature_importances_"):
                imp = sorted(zip(cols, m.feature_importances_), key=lambda t: -t[1])[:15]
                importances = {name: [[c, round(float(v), 4)] for c, v in imp]}
    except Exception as exc:                       # informative only
        importances = {"error": str(exc)}
    report["feature_importance_dir_4h"] = importances
    return report


def print_report(rep: dict) -> None:
    print(f"decisions {rep['decisions']}  forecasters {rep['forecasters']}")
    for target, res in rep["targets"].items():
        print(f"\n== {target}   scored n={res['n']}   share of 1s={res.get('base_rate_of_1')}")
        if "note" in res:
            print("   " + res["note"])
            continue
        print(f"   {'contender':<28}{'brier':>8}{'logloss':>9}{'auc':>7}{'acc':>7}{'skill':>8}   vs structure-only")
        for name, r in res.items():
            if not isinstance(r, dict):
                continue
            auc_s = "-" if r["auc"] is None else f"{r['auc']:.3f}"
            print(f"   {name:<28}{r['brier']:>8.4f}{r['logloss']:>9.4f}{auc_s:>7}{r['acc']:>7.3f}"
                  f"{r['skill_vs_base']:>8.3f}   {r.get('better_than_structure', '')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--forecasts", action="append", default=[], help="name=path (repeatable)")
    ap.add_argument("--lab-config", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    lab = load_lab_config(args.lab_config)
    rows = [json.loads(x) for x in open(args.decisions, encoding="utf-8")]
    forecasts = {}
    for spec in args.forecasts:
        name, path = spec.split("=", 1)
        forecasts[name] = {}
        for x in open(path, encoding="utf-8"):
            rec = json.loads(x)
            forecasts[name][rec["t"]] = rec["tf"]
    rep = compare(rows, forecasts, lab)
    print_report(rep)
    if args.out:
        Path(args.out).write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
