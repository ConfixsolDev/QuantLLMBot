"""Match detections to ground truth and compute accuracy metrics.

A detection MATCHES a truth item when ``same(d, t)`` is true (same kind /
side / timeframe) and their anchor times are within ``time_tol`` seconds.
Matching is one-to-one and greedy by smallest time error, so one detection
can never claim two truths (and vice versa).

    precision = matched detections / all detections   (how often it is right)
    recall    = matched truths / all truths           (how much it finds)
    F1        = harmonic mean of the two

Localisation error = mean |time difference| (seconds) and, when both sides
carry prices, mean |price difference| over matched pairs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Score:
    tp: int
    fp: int
    fn: int
    time_err: float          # mean abs time error of matches (seconds)
    price_err: float | None  # mean abs price error of matches

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def merge(self, other: "Score") -> "Score":
        n1, n2 = self.tp, other.tp
        te = (self.time_err * n1 + other.time_err * n2) / (n1 + n2) if n1 + n2 else 0.0
        pe = None
        if self.price_err is not None or other.price_err is not None:
            a, b = self.price_err or 0.0, other.price_err or 0.0
            pe = (a * n1 + b * n2) / (n1 + n2) if n1 + n2 else 0.0
        return Score(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn, te, pe)

    def as_dict(self) -> dict:
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn,
                "precision": round(self.precision, 4), "recall": round(self.recall, 4),
                "f1": round(self.f1, 4), "time_err_s": round(self.time_err, 1),
                "price_err": None if self.price_err is None else round(self.price_err, 4)}


def match(detections: list[dict], truths: list[dict], *, time_key: str = "time",
          time_tol: float, same: Callable[[dict, dict], bool] = lambda d, t: True,
          price: Callable[[dict], float] | None = None) -> Score:
    pairs = []
    for i, d in enumerate(detections):
        for j, t in enumerate(truths):
            if same(d, t):
                dt = abs(d[time_key] - t[time_key])
                if dt <= time_tol:
                    pairs.append((dt, i, j))
    pairs.sort()
    used_d, used_t, matched = set(), set(), []
    for dt, i, j in pairs:
        if i in used_d or j in used_t:
            continue
        used_d.add(i)
        used_t.add(j)
        matched.append((dt, i, j))
    tp = len(matched)
    time_err = sum(m[0] for m in matched) / tp if tp else 0.0
    price_err = None
    if price and tp:
        price_err = sum(abs(price(detections[i]) - price(truths[j])) for _, i, j in matched) / tp
    return Score(tp, len(detections) - tp, len(truths) - tp, time_err, price_err)
