"""Production vNext service boundary with explicit strategy and order providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import Evaluation, VNextEngine
from vnext.runtime.live_cycle import LiveVNextCycle
from vnext.llm.gateway import StrategyQwenGateway
from vnext.strategy.definition import StrategySpec
from vnext.strategy.dsl import StrategyProgram
from vnext.strategy.timeframe_audit import TimeframeExpectationAuditor


CandidateProvider = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]
RiskProvider = Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any] | None]
OrderProvider = Callable[[Evaluation], Mapping[str, Any] | None]


@dataclass(frozen=True, slots=True)
class ServiceResult:
    state: Any
    evaluation: Evaluation | None
    submitted: Mapping[str, Any] | None


class VNextService:
    """Run one active cycle; absent providers mean an auditable no-trade cycle."""

    def __init__(self, *, cycle: LiveVNextCycle, strategy: StrategySpec,
                 candidate_provider: CandidateProvider | None = None,
                 strategy_program: StrategyProgram | None = None,
                 risk_provider: RiskProvider | None = None,
                 order_provider: OrderProvider | None = None,
                 qwen_client: Any = None, qwen_gateway: StrategyQwenGateway | None = None,
                 broker: Any = None,
                 timeframe_auditor: TimeframeExpectationAuditor | None = None) -> None:
        if not isinstance(strategy, StrategySpec):
            raise TypeError("V2 service requires an explicit StrategySpec")
        self.cycle, self.strategy = cycle, strategy
        self.candidate_provider = candidate_provider
        self.strategy_program = strategy_program
        self.risk_provider = risk_provider
        self.order_provider = order_provider
        self.qwen_client, self.qwen_gateway, self.broker = qwen_client, qwen_gateway, broker
        self.timeframe_auditor = timeframe_auditor
        self.timeframe_audit_error: str | None = None
        if self.qwen_gateway is None and self.qwen_client is not None:
            self.qwen_gateway = StrategyQwenGateway(self.qwen_client)

    def run_once(self) -> ServiceResult:
        state = self.cycle.run_once()
        if self.timeframe_auditor is not None:
            try:
                self.timeframe_auditor.record(state, self.strategy)
                self.timeframe_audit_error = None
            except Exception as exc:
                # Observability must never alter candidate, risk, or order behavior.
                self.timeframe_audit_error = f"{type(exc).__name__}: {str(exc)[:240]}"
        if self.candidate_provider:
            candidate_inputs = self.candidate_provider(state.as_dict())
        elif self.strategy_program:
            intent = self.strategy_program.propose({**state.as_dict(), "state_hash": state.state_hash})
            candidate_inputs = ({"candidate_id": intent.candidate_id, "direction": intent.direction,
                                 "zone_id": intent.zone_id, "invalidation": intent.invalidation,
                                 "target_zone_ids": intent.target_zone_ids} if intent else None)
        else:
            candidate_inputs = None
        if not candidate_inputs:
            return ServiceResult(state, None, None)
        risk_inputs = self.risk_provider(state.as_dict(), candidate_inputs) if self.risk_provider else None
        engine = VNextEngine(
            pair=state.pair,
            frontier=TimeFrontier.from_value(state.time_frontier_utc),
            broker=self.broker,
            event_sink=self.cycle.persistence.append_events,
            qwen_gateway=self.qwen_gateway,
        )
        evaluation = engine.evaluate(state, self.strategy,
                                     candidate_inputs=candidate_inputs,
                                     risk_inputs=risk_inputs)
        submitted = None
        if evaluation.risk is not None and evaluation.risk.approved and self.order_provider:
            order = self.order_provider(evaluation)
            if order is not None:
                submitted = engine.submit(evaluation, order=order)
        return ServiceResult(state, evaluation, submitted)
