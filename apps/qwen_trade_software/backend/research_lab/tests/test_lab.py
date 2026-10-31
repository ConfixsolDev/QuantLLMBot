"""research_lab: dataset causality, forecasters, walk-forward comparison.

    python -m pytest research_lab/tests -q      (from apps/qwen_trade_software/backend)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research_lab.compare import auc, brier, compare, logloss  # noqa: E402
from research_lab.config import load_lab_config  # noqa: E402
from research_lab.dataset import add_labels, build_decisions  # noqa: E402
from research_lab.forecast import summarize  # noqa: E402
from research_lab.forecasters import BootstrapForecaster, KronosForecaster  # noqa: E402
from structure_engine import load_config  # noqa: E402
from structure_engine.verification.synthetic import random_walk_m1  # noqa: E402

LAB = load_lab_config()


@pytest.fixture(scope="module")
def rows():
    bars = random_walk_m1(3, 14 * 1440)            # two weeks of M1
    r = build_decisions(bars, load_config(), LAB)
    add_labels(r, bars, LAB)
    return r


def test_decisions_are_causal(rows):
    assert len(rows) > 200
    for r in rows:
        assert r["t"] % 3600 == 0                   # H1 closes
        for k, when in r["label_known_at"].items():
            assert when > r["t"]                    # a label is always known later
        assert set(r["labels"]) >= {"dir_1h", "dir_4h", "barrier_4h"}


def test_bootstrap_paths_are_valid_and_seeded():
    from structure_engine import Bar
    ctx = [Bar(60 * i, 100 + i % 5, 101 + i % 5, 99 + i % 5, 100.5 + i % 5) for i in range(300)]
    a = BootstrapForecaster().sample(ctx, [1, 2, 3], 8, seed=1)
    b = BootstrapForecaster().sample(ctx, [1, 2, 3], 8, seed=1)
    assert a == b and len(a) == 8 and all(len(p) == 3 for p in a)
    assert all(h >= max(o, c) and l <= min(o, c) for p in a for o, h, l, c in p)
    s = summarize(a, ctx[-1].close, 1.0, 1.0, {"direction": "up", "ref": 100.0})
    assert 0 <= s["p_up"] <= 1 and s["q10"] <= s["q50"] <= s["q90"] and "p_spike_rev" in s


def test_kronos_wrapper_builds_distinct_paths_from_predict_batch():
    pd = pytest.importorskip("pandas")
    from structure_engine import Bar

    class FakePredictor:
        def predict_batch(self, df_list, x_timestamp_list, y_timestamp_list, pred_len, T, top_p, sample_count, verbose):
            assert sample_count == 1 and len(df_list) == 4 and len(y_timestamp_list[0]) == pred_len
            return [pd.DataFrame({"open": [100 + i] * pred_len, "high": [99 + i] * pred_len,
                                  "low": [101 + i] * pred_len, "close": [100.5 + i] * pred_len,
                                  "volume": [1] * pred_len}) for i in range(len(df_list))]

    k = KronosForecaster("", "", "", predictor=FakePredictor())
    ctx = [Bar(60 * i, 100, 101, 99, 100.5, 5) for i in range(50)]
    paths = k.sample(ctx, [3000, 3060], 4, seed=0)
    assert len(paths) == 4 and len({p[0][3] for p in paths}) == 4
    assert all(h >= max(o, c) and l <= min(o, c) for p in paths for o, h, l, c in p)   # sanitised


def test_metrics():
    y = [0, 0, 1, 1]
    assert brier([0, 0, 1, 1], y) == 0 and auc([0.1, 0.2, 0.8, 0.9], y) == 1.0
    assert logloss([0.5] * 4, y) == pytest.approx(0.6931, abs=1e-3)


def test_walk_forward_comparison_runs_without_lookahead(rows, tmp_path):
    from research_lab.config import DEFAULT
    raw = json.loads(DEFAULT.read_text())
    raw["walk_forward"] = {"initial_train_fraction": 0.5, "retrain_every": 20, "min_train": 60}
    raw["xgboost"]["n_estimators"] = 30
    p = tmp_path / "lab.json"
    p.write_text(json.dumps(raw))
    lab = load_lab_config(p)
    bars = random_walk_m1(3, 14 * 1440)
    from research_lab.forecast import summarize as summ
    from structure_engine.engine import closed_bars_by_timeframe
    import bisect
    by_tf = closed_bars_by_timeframe(bars, load_config())
    ct = [b.close_time for b in by_tf["H1"]]
    fc = {}
    for r in rows:
        i = bisect.bisect_right(ct, r["t"])
        ctx = by_tf["H1"][max(0, i - 200):i]
        if len(ctx) >= 50:
            paths = BootstrapForecaster().sample(ctx, [0, 1, 2, 3], 16, seed=r["t"])
            fc[r["t"]] = {"H1": summ(paths, ctx[-1].close, r["atr_h1"], 1.0, None)}
    rep = compare(rows, {"bootstrap": fc}, lab)
    res = rep["targets"]["dir_4h"]
    assert res["n"] > 20
    for name in ("base_rate", "bootstrap_raw", "xgb_structure", "xgb_structure+bootstrap"):
        assert 0 <= res[name]["brier"] <= 1
