"""Strategy-scoped outcome statistics; no trade decision authority."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable


@dataclass(frozen=True, slots=True)
class StrategyStatistics:
    strategy_id: str
    sample_size: int
    wins: int
    losses: int
    expected_r: float | None
    mean_mfe_r: float | None
    mean_mae_r: float | None
    stability: float | None

    def as_dict(self) -> dict:
        return {"strategy_id": self.strategy_id, "sample_size": self.sample_size,
                "wins": self.wins, "losses": self.losses, "expected_r": self.expected_r,
                "mean_mfe_r": self.mean_mfe_r, "mean_mae_r": self.mean_mae_r,
                "stability": self.stability}


def summarize(strategy_id: str, outcomes: Iterable[dict]) -> StrategyStatistics:
    rows = list(outcomes)
    returns = [float(row["r"]) for row in rows if row.get("r") is not None]
    mfe = [float(row["mfe_r"]) for row in rows if row.get("mfe_r") is not None]
    mae = [float(row["mae_r"]) for row in rows if row.get("mae_r") is not None]
    wins = sum(value > 0 for value in returns)
    losses = sum(value <= 0 for value in returns)
    mean = sum(returns) / len(returns) if returns else None
    deviation = sqrt(sum((value - mean) ** 2 for value in returns) / len(returns)) if returns and mean is not None else None
    return StrategyStatistics(strategy_id, len(rows), wins, losses, mean,
                              sum(mfe) / len(mfe) if mfe else None,
                              sum(mae) / len(mae) if mae else None,
                              (mean / deviation if deviation else None))
