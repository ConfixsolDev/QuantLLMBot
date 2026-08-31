"""Strategy-scoped statistics with sample-aware shrinkage."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable


@dataclass(frozen=True, slots=True)
class StrategyStats:
    strategy_id: str
    sample_size: int
    wins: int
    losses: int
    expected_r: float | None
    mean_mfe_r: float | None
    mean_mae_r: float | None
    stability: float | None
    shrunk_expected_r: float | None
    evidence_quality: str

    def as_dict(self) -> dict:
        return {"strategy_id": self.strategy_id, "sample_size": self.sample_size,
                "wins": self.wins, "losses": self.losses, "expected_r": self.expected_r,
                "mean_mfe_r": self.mean_mfe_r, "mean_mae_r": self.mean_mae_r,
                "stability": self.stability, "shrunk_expected_r": self.shrunk_expected_r,
                "evidence_quality": self.evidence_quality}


def summarize(strategy_id: str, outcomes: Iterable[dict], *, prior_r: float = 0.0,
              prior_weight: int = 20) -> StrategyStats:
    rows = list(outcomes)
    returns = [float(row["r"]) for row in rows if row.get("r") is not None]
    mfe = [float(row["mfe_r"]) for row in rows if row.get("mfe_r") is not None]
    mae = [float(row["mae_r"]) for row in rows if row.get("mae_r") is not None]
    wins = sum(value > 0 for value in returns)
    losses = sum(value <= 0 for value in returns)
    mean = sum(returns) / len(returns) if returns else None
    deviation = sqrt(sum((value - mean) ** 2 for value in returns) / len(returns)) if returns and mean is not None else None
    shrunk = ((mean * len(returns)) + (prior_r * prior_weight)) / (len(returns) + prior_weight) if mean is not None else prior_r
    quality = "none" if not returns else "low" if len(returns) < 20 else "usable" if len(returns) < 100 else "strong"
    return StrategyStats(strategy_id, len(rows), wins, losses, mean,
                         sum(mfe) / len(mfe) if mfe else None,
                         sum(mae) / len(mae) if mae else None,
                         (mean / deviation if deviation else None), shrunk, quality)
