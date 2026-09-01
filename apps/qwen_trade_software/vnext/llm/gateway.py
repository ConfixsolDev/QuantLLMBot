"""Single strategy-facing gateway for constrained Qwen interactions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from vnext.llm.arbitrator import Arbitration
from vnext.llm.client import QwenClient, request_arbitration
from vnext.market.state import PairMarketState
from vnext.strategy.contracts import TradeCandidate


@dataclass(frozen=True, slots=True)
class StrategyQwenGateway:
    """Route every strategy's supplied candidate through one Qwen boundary.

    Strategies remain responsible for deterministic candidate construction.
    Qwen only arbitrates that candidate against the bounded state package.
    """

    client: QwenClient

    def arbitrate(self, state: PairMarketState, candidate: TradeCandidate,
                  story: Mapping[str, Any]) -> Arbitration:
        return request_arbitration(self.client, state, candidate, story)
