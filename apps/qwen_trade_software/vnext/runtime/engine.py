"""End-to-end composition of the clean-room V2 modules.

This engine owns orchestration only. Market facts are deterministic, the
strategy supplies candidates, the LLM only arbitrates a supplied candidate,
risk gates the result, and the broker adapter owns transport.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from vnext.data.bars import Bar, TimeframeBuilder
from vnext.intelligence.indicators.evidence import indicator_evidence
from vnext.intelligence.mtf.relationships import classify_relationship
from vnext.intelligence.structure.engine import StructureEngine
from vnext.intelligence.zones.engine import ZoneEngine
from vnext.llm.arbitrator import Arbitration, arbitrate
from vnext.llm.client import QwenClient, request_arbitration
from vnext.market.state import PairMarketState
from vnext.narrator.story import NarratorRequest, StoryNarrator
from vnext.platform.events import EventEnvelope
from vnext.platform.time_frontier import TimeFrontier
from vnext.recovery.reconcile import RecoveryPlan, reconcile
from vnext.risk.engine import RiskDecision, evaluate_risk
from vnext.strategy.definition import StrategySpec, create_candidate


class EventLedger(Protocol):
    def append(self, event: EventEnvelope, *, frontier: TimeFrontier | None = None) -> bool: ...


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
                 broker: BrokerAdapter | None = None,
                 ledger: EventLedger | None = None,
                 event_sink: Callable[[list[EventEnvelope]], int] | None = None,
                 qwen_client: QwenClient | None = None) -> None:
        self.pair = pair
        self.frontier = frontier
        self.broker = broker
        self.ledger = ledger
        self.event_sink = event_sink
        self.qwen_client = qwen_client
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
        if structure_events:
            latest_structure = structure_events[-1]
            structure["direction"] = ("sell" if latest_structure.event_type == "SWING_HIGH_CONFIRMED"
                                       else "buy" if latest_structure.event_type == "SWING_LOW_CONFIRMED"
                                       else "neutral")
            structure["state"] = "confirmed_swing"
            structure["last_event_id"] = latest_structure.event_id
        timeframe_rows = {
            timeframe: {"direction": ("buy" if rows and rows[-1]["close"] > rows[-1]["open"]
                                       else "sell" if rows and rows[-1]["close"] < rows[-1]["open"]
                                       else "neutral"),
                        "state": "confirmed_bar" if rows else "unknown"}
            for timeframe, rows in timeframes.items()
        }
        relationships = tuple(
            {"parent_timeframe": parent, "child_timeframe": child,
             **classify_relationship(timeframe_rows[parent], timeframe_rows[child])}
            for parent, child in zip(("D1", "H4", "H1", "M30", "M15", "M5"),
                                     ("H4", "H1", "M30", "M15", "M5", "M1"))
        )
        state = PairMarketState(
            self.pair, self.frontier.as_of_utc, {"status": "ready" if confirmed else "unavailable",
            "completed_bars": len(confirmed)}, timeframes,
            zones=tuple(zone.as_dict() for zone in zones), structure=structure,
            structural_events=tuple(event.as_dict() for event in structure_events),
            mtf_relationships=relationships, temporal_state={}, statistics=statistics or {},
            indicators=indicators,
        )
        self._record("PAIR_MARKET_STATE_COMPOSED", {"state_hash": state.state_hash,
                     "timefrontier": self.frontier.as_of_utc.isoformat(),
                     "completed_bars": len(confirmed)})
        return state

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
        arbitration_result = None
        if candidate:
            if response is not None:
                arbitration_result = arbitrate(response, candidate)
            elif self.qwen_client is not None:
                arbitration_result = request_arbitration(self.qwen_client, state, candidate, story)
            else:
                arbitration_result = arbitrate({"decision": "WAIT", "state_hash": state.state_hash}, candidate)
            self._record("QWEN_ARBITRATION", {
                "candidate_id": candidate.candidate_id,
                "decision": arbitration_result.decision,
                "state_hash": arbitration_result.state_hash,
                "violations": list(arbitration_result.violations),
                "reason": arbitration_result.reason[:512],
            })
        risk_result = None
        if candidate and arbitration_result and arbitration_result.decision == "APPROVE" and risk_inputs:
            risk_result = evaluate_risk(**dict(risk_inputs))
        evaluation = Evaluation(state, story, candidate, arbitration_result, risk_result)
        self._record("STRATEGY_EVALUATION", {
            "state_hash": state.state_hash,
            "candidate_id": candidate.candidate_id if candidate else None,
            "decision": arbitration_result.decision if arbitration_result else None,
            "risk_approved": risk_result.approved if risk_result else None,
        })
        return evaluation

    def submit(self, evaluation: Evaluation, *, order: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.broker is None:
            raise RuntimeError("broker adapter is required for submission")
        if evaluation.candidate is None or evaluation.arbitration is None or evaluation.arbitration.decision != "APPROVE":
            raise RuntimeError("order requires an approved candidate")
        if evaluation.risk is None or not evaluation.risk.approved:
            raise RuntimeError("order requires approved risk")
        candidate = evaluation.candidate
        owned_order = dict(order)
        supplied_magic = owned_order.get("magic_number", owned_order.get("magic"))
        if supplied_magic is not None and int(supplied_magic) != candidate.strategy.magic_number:
            raise RuntimeError("order magic number does not belong to strategy")
        supplied_strategy = owned_order.get("strategy_id")
        if supplied_strategy is not None and str(supplied_strategy) != candidate.strategy.strategy_id:
            raise RuntimeError("order strategy identity does not match candidate")
        owned_order.update({"strategy_id": candidate.strategy.strategy_id,
                            "strategy_version": candidate.strategy.version,
                            "magic_number": candidate.strategy.magic_number,
                            "comment": candidate.strategy.execution_comment})
        result = self.broker.submit(owned_order)
        self._record("ORDER_SUBMITTED", {"candidate_id": candidate.candidate_id,
                     "strategy_id": candidate.strategy.strategy_id,
                     "magic_number": candidate.strategy.magic_number,
                     "comment": candidate.strategy.execution_comment,
                     "order": owned_order, "broker_result": dict(result)})
        return result

    def _record(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.ledger is None and self.event_sink is None:
            return
        raw = f"{self.pair}|{event_type}|{self.frontier.as_of_utc.isoformat()}|{payload}"
        event = EventEnvelope(hashlib.sha256(raw.encode()).hexdigest()[:24], event_type,
                              self.pair, self.frontier.as_of_utc, payload, "vnext_runtime")
        if self.event_sink is not None:
            self.event_sink([event])
        else:
            assert self.ledger is not None
            self.ledger.append(event, frontier=self.frontier)

    @staticmethod
    def recover(*, broker_positions: list[Mapping[str, Any]], ledger_positions: list[Mapping[str, Any]],
                broker_healthy: bool, data_healthy: bool, timescale_healthy: bool,
                redis_rebuilt: bool, neo4j_status: str = "ready") -> RecoveryPlan:
        return reconcile(broker_positions=broker_positions, ledger_positions=ledger_positions,
                         broker_healthy=broker_healthy, data_healthy=data_healthy,
                         timescale_healthy=timescale_healthy, redis_rebuilt=redis_rebuilt,
                         neo4j_status=neo4j_status)
