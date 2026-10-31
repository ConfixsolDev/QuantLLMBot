"""Forecasters: produce N sampled future candle paths from closed history.

Both share one interface::

    paths = forecaster.sample(context, future_times, n_paths, seed)
    # context: list of closed Bars (oldest first)
    # returns: list of n_paths paths, each a list of (open, high, low, close)

KronosForecaster   the foundation model (github.com/shiyu-coder/Kronos).
                   Runs on CPU, an NVIDIA GPU ("cuda:0") or an AMD/Intel GPU on
                   Windows through DirectML ("dml"). Distinct paths come from
                   ``predict_batch`` on N copies of the context with
                   ``sample_count=1`` — Kronos' own ``sample_count`` AVERAGES
                   samples into one path, which would hide the spread.
BootstrapForecaster  the no-skill yardstick: future candles are re-drawn from
                   this context's own recent candles (moves, bodies and wicks),
                   so it knows the current volatility but nothing about
                   direction. Kronos is only interesting if it beats this.

Every path is sanitised so high >= max(open, close) and low <= min(open, close).
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timezone


def _clean(o: float, h: float, l: float, c: float) -> tuple[float, float, float, float]:
    return o, max(o, h, l, c), min(o, h, l, c), c


class BootstrapForecaster:
    name = "bootstrap"

    def sample(self, context, future_times, n_paths: int, seed: int):
        rng = random.Random(seed)
        pool = context[-200:]
        steps = []
        for prev, b in zip(pool, pool[1:]):
            steps.append((b.open - prev.close, b.close - b.open,
                          b.high - max(b.open, b.close), min(b.open, b.close) - b.low))
        last = context[-1].close
        paths = []
        for _ in range(n_paths):
            c, path = last, []
            for _t in future_times:
                gap, body, up_w, dn_w = steps[rng.randrange(len(steps))]
                o = c + gap
                c2 = o + body
                path.append(_clean(o, max(o, c2) + up_w, min(o, c2) - dn_w, c2))
                c = c2
            paths.append(path)
        return paths


class KronosForecaster:
    name = "kronos"

    def __init__(self, repo: str, model_id: str, tokenizer_id: str, device: str = "cpu",
                 max_context: int = 512, temperature: float = 1.0, top_p: float = 0.9,
                 predictor=None) -> None:
        self.temperature, self.top_p = temperature, top_p
        self.device_name = device
        if predictor is not None:                    # tests inject a fake
            self.predictor = predictor
            return
        sys.path.insert(0, repo)
        import importlib
        importlib.import_module("torch")       # fail early, clearly, if PyTorch is missing
        from model import Kronos, KronosPredictor, KronosTokenizer
        dev = device
        if device == "dml":
            import torch_directml
            dev = torch_directml.device()
        tok = KronosTokenizer.from_pretrained(tokenizer_id)
        mdl = Kronos.from_pretrained(model_id)
        self.predictor = KronosPredictor(mdl, tok, device=dev, max_context=max_context)

    def sample(self, context, future_times, n_paths: int, seed: int):
        import pandas as pd
        try:
            import torch
            torch.manual_seed(seed)
        except ImportError:
            pass
        df = pd.DataFrame({"open": [b.open for b in context], "high": [b.high for b in context],
                           "low": [b.low for b in context], "close": [b.close for b in context],
                           "volume": [b.volume for b in context]})
        to_ts = lambda ts: pd.Series(pd.to_datetime([datetime.fromtimestamp(t, tz=timezone.utc).replace(tzinfo=None)  # noqa: E731
                                                     for t in ts]))
        x_ts, y_ts = to_ts([b.time for b in context]), to_ts(future_times)
        preds = self.predictor.predict_batch(
            df_list=[df] * n_paths, x_timestamp_list=[x_ts] * n_paths, y_timestamp_list=[y_ts] * n_paths,
            pred_len=len(future_times), T=self.temperature, top_p=self.top_p, sample_count=1, verbose=False)
        return [[_clean(float(r.open), float(r.high), float(r.low), float(r.close))
                 for r in p.itertuples()] for p in preds]
