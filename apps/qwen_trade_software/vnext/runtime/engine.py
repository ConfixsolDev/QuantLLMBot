"""End-to-end composition of the clean-room V2 modules.

This engine owns orchestration only. Market facts are deterministic, the
strategy supplies candidates, the LLM only arbitrates a supplied candidate,
risk gates the result, and the broker adapter owns transport.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from vnext.data.bars import Bar, TimeframeBuilder
from vnext.intelligence.indicators.evidence import indicator_evidence
from vnext.intelligence.mtf.relationships import classify_relationship
from vnext.intelligence.structure.engine import StructureEngine
from vnext.intelligence.zones.engine import ZoneEngine
from vnext.llm.arbitrator import Arbitration, arbitrate
from vnext.market.state import PairMarketState
from vnext.narrator.story import NarratorRequest, StoryNarrator
from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier
from vnext.recovery.reconcile import RecoveryPlan, reconcile
from vnext.risk.engine import RiskDecision, evaluate_risk
from vnext.strategy.definition import StrategySpec, create_candidate


class BrokerAdapter(Protocol):
    def submit(self, order: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Evaluation:
    state: PairMarketState
    story: dict[str, Any]
    candidate: Any | None
    arbitration: Arbitration | None
    risk: RiskDecision | None


class VNextEngine:
    def __init__(self, *, pair: str, frontier: TimeFrontier,
                 broker: BrokerAdapter | None = None) -> None:
        self.pair = pair
        self.frontier = frontier
        self.broker = broker
        self.zone_engine = ZoneEngine()
        self.structure_engine = StructureEngine()
        self.narrator = StoryNarrator()

    def compose_state(self, m1_bars: list[Bar], *, statistics: dict | None = None) -> PairMarketState:
        builder = TimeframeBuilder(self.pair, frontier=self.frontier)
        timeframes: dict[str, Any] = {"M1": [bar.as_dict() for bar in builder.build(m1_bars, "M1")]}
        for timeframe in ("M5", "M15", "M30", "H1", "H4", "D1"):
            timeframes[timeframe] = [bar.as_dict() for bar in builder.build(m1_bars, timeframe)]
        confirmed = [bar for bar in m1_bars if bar.pair == self.pair and self.frontier.permits(bar.end_utc)]
        zones = self.zone_engine.discover(confirmed, pair=self.pair, timeframe="M1")
        structure_events = self.structure_engine.detect_swings(confirmed)
        latest = confirmed[-1] if confirmed else None
        indicators = indicator_evidence(confirmed)
        structure = {"state": "unknown", "direction": "neutral",
                     "confirmed_event_count": len(structure_events)}
        if latest is not None:
            structure["direction"] = "buy" if latest.close >= latest.open else "sell"
        return PairMarketState(
            self.pair, self.frontier.as_of_utc, {"status": "ready" if confirmed else "unavailable",
            "completed_bars": len(confirmed)}, timeframes,
            zones=tuple(zone.as_dict() for zone in zones), structure=structure,
            structural_events=tuple(event.as_dict() for event in structure_events),
            mtf_relationships=(), temporal_state={}, statistics=statistics or {},
            indicators=indicators,
        )

    def evaluate(self, state: PairMarketState, spec: StrategySpec, *, response: Mapping[str, Any] | None = None,
                 candidate_inputs: Mapping[str, Any] | None = None, risk_inputs: Mapping[str, Any] | None = None) -> Evaluation:
        request = NarratorRequest(
            pair=state.pair,
            context_timeframes=tuple(spec.narrator_request.get("context_timeframes", ("M15", "H1"))),
            setup_timeframes=tuple(spec.narrator_request.get("setup_timeframes", ("M5",))),
            execution_timeframes=tuple(spec.narrator_request.get("execution_timeframes", ("M1",))),
            purpose="ENTRY", depth="STANDARD", include_statistics=True,
        )
        story = self.narrator.narrate(state, request)
        candidate = None
        if candidate_inputs:
            candidate = create_candidate(spec, state_hash=state.state_hash, **dict(candidate_inputs))
        arbitration_result = arbitrate(response or {"decision": "WAIT", "state_hash": state.state_hash}, candidate) if candidate else None
        risk_result = None
        if candidate and arbitration_result and arbitration_result.decision == "APPROVE" and risk_inputs:
            risk_result = evaluate_risk(**dict(risk_inputs))
        return Evaluation(state, story, candidate, arbitration_result, risk_result)

    def submit(self, evaluation: Evaluation, *, order: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.broker is None:
            raise RuntimeError("broker adapter is required for submission")
        if evaluation.candidate is None or evaluation.arbitration is None or evaluation.arbitration.decision != "APPROVE":
            raise RuntimeError("order requires an approved candidate")
        if evaluation.risk is None or not evaluation.risk.approved:
            raise RuntimeError("order requires approved risk")
        return self.broker.submit(dict(order))

    @staticmethod
    def recover(*, broker_positions: list[Mapping[str, Any]], ledger_positions: list[Mapping[str, Any]],
                broker_healthy: bool, data_healthy: bool, timescale_healthy: bool,
                redis_rebuilt: bool, neo4j_status: str = "ready") -> RecoveryPlan:
        return reconcile(broker_positions=broker_positions, ledger_positions=ledger_positions,
                         broker_healthy=broker_healthy, data_healthy=data_healthy,
                         timescale_healthy=timescale_healthy, redis_rebuilt=redis_rebuilt,
                         neo4j_status=neo4j_status)
