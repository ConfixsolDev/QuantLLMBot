"""Run the vNext strategy pipeline with broker submission forcibly disabled."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from vnext.llm.client import QwenClient
from vnext.data.news_calendar import DailyNewsCalendar
from vnext.platform.events import EventEnvelope
from vnext.runtime.lease import LeaseHeartbeat, VNextLease
from vnext.runtime.live_cycle import LiveVNextCycle, MT5ClosedBarSource
from vnext.runtime.service import ServiceResult, VNextService
from vnext.storage.persistence import from_environment
from vnext.strategy.xau_m15_m1_structure_scalper import (
    SPEC,
    build_strategy_evidence,
    candidate_blockers,
    candidate_inputs,
)
from vnext.strategy.timeframe_audit import TimeframeExpectationAuditor


def diagnostic_payload(result: ServiceResult, *, cycle_number: int, model: str,
                       entry_gate_reason: str | None = None) -> dict[str, Any]:
    state = result.state.as_dict()
    blockers = list(candidate_blockers(state))
    evaluation = result.evaluation
    story = evaluation.story if evaluation else {}
    story_facts = story.get("facts", {}) if isinstance(story, dict) else {}
    feedback = (evaluation.candidate.metadata.get("qwen_feedback", {})
                if evaluation and evaluation.candidate else {})
    return {
        "mode": "DEBUG_NO_ORDERS",
        "execution_enabled": False,
        "cycle_number": cycle_number,
        "strategy_id": SPEC.definition.strategy_id,
        "strategy_version": SPEC.definition.version,
        "model": model,
        "frontier_utc": result.state.time_frontier_utc.isoformat(),
        "state_hash": result.state.state_hash,
        "completed_m1_bars": result.state.data_quality.get("completed_bars", 0),
        "zone_count": len(result.state.zones),
        "structure_event_count": len(result.state.structural_events),
        "strategy_evidence_present": bool(state.get("strategy_evidence") or build_strategy_evidence(state)),
        "story_schema": story.get("schema_version") if isinstance(story, dict) else None,
        "story_timeframes": sorted(story_facts.get("timeframes", {})) if isinstance(story_facts, dict) else [],
        "strategy_feedback_schema": feedback.get("schema_version") if isinstance(feedback, dict) else None,
        "candidate_blockers": blockers,
        "entry_gate_reason": entry_gate_reason,
        "candidate_id": evaluation.candidate.candidate_id if evaluation and evaluation.candidate else None,
        "qwen_decision": evaluation.arbitration.decision if evaluation and evaluation.arbitration else None,
        "qwen_reason": evaluation.arbitration.reason if evaluation and evaluation.arbitration else None,
        "qwen_violations": list(evaluation.arbitration.violations)
        if evaluation and evaluation.arbitration else [],
        "risk_approved": evaluation.risk.approved if evaluation and evaluation.risk else None,
        "order_submitted": False,
    }


def debug_event(pair: str, payload: dict[str, Any], event_type: str = "VNEXT_DEBUG_CYCLE") -> EventEnvelope:
    observed = datetime.now(timezone.utc)
    raw = json.dumps(payload, sort_keys=True, default=str)
    event_id = hashlib.sha256(f"{event_type}|{observed.isoformat()}|{raw}".encode()).hexdigest()[:24]
    return EventEnvelope(event_id, event_type, pair, observed, payload, "vnext_debug_service")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", default=os.environ.get("QWEN_VNEXT_PAIR", SPEC.definition.pair))
    parser.add_argument("--model", default=os.environ.get("QWEN_VNEXT_MODEL", "qwen-trading-v005:latest"))
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--qwen-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--lookback", type=int, default=300)
    parser.add_argument("--max-cycles", type=int, default=0,
                        help="Zero runs until interrupted; positive values are useful for verification.")
    args = parser.parse_args()
    if (args.interval_seconds <= 0 or args.qwen_timeout_seconds <= 0
            or args.lookback < 3 or args.max_cycles < 0):
        raise ValueError("invalid debug service timing")

    dsn = os.environ.get("QWEN_TIMESCALE_DSN", "")
    redis_url = os.environ.get("QWEN_REDIS_URL", "")
    neo4j_uri = os.environ.get("QWEN_NEO4J_URI", "bolt://127.0.0.1:7687")
    neo4j_user = os.environ.get("QWEN_NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("QWEN_NEO4J_PASSWORD", "")

    import MetaTrader5 as mt5

    persistence = from_environment(dsn=dsn, redis_url=redis_url, neo4j_uri=neo4j_uri,
                                   neo4j_user=neo4j_user, neo4j_password=neo4j_password)
    lease = VNextLease(persistence.working_memory.client,
                       name="qwen:vnext:debug-service:lease", ttl_seconds=180)
    if not lease.acquire():
        persistence.close()
        raise RuntimeError("another vNext debug service owns the lease")
    heartbeat = LeaseHeartbeat(lease)
    heartbeat.start()

    initialized = False
    try:
        persistence.ensure_ready()
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        initialized = True
        source = MT5ClosedBarSource(mt5)
        cycle = LiveVNextCycle(pair=args.pair, source=source,
                               persistence=persistence, lookback=args.lookback)
        calendar = DailyNewsCalendar(persistence.working_memory, durable_store=persistence)
        calendar_refresh_day: str | None = None
        entry_gate = {"reason": "calendar_missing"}

        def refresh_calendar_once(now: datetime) -> None:
            nonlocal calendar_refresh_day
            day = now.astimezone(timezone.utc).date().isoformat()
            if calendar_refresh_day == day:
                return
            calendar_refresh_day = day
            try:
                payload = calendar.refresh(now=now)
                persistence.append_events([debug_event(args.pair, {
                    "day_utc": day, "event_count": len(payload.get("events", ()),),
                    "status": "CALENDAR_REFRESHED",
                }, "VNEXT_CALENDAR_REFRESHED")])
            except Exception as exc:
                persistence.append_events([debug_event(args.pair, {
                    "day_utc": day, "status": "CALENDAR_REFRESH_FAILED",
                    "error": str(exc)[:300],
                }, "VNEXT_CALENDAR_REFRESH_FAILED")])

        def gated_candidate_provider(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
            frontier = datetime.fromisoformat(str(state["time_frontier_utc"]).replace("Z", "+00:00"))
            refresh_calendar_once(frontier)
            gate = calendar.gate(now=frontier)
            entry_gate["reason"] = gate.reason
            return candidate_inputs(state) if gate.allowed else None

        service = VNextService(
            cycle=cycle,
            strategy=SPEC,
            candidate_provider=gated_candidate_provider,
            qwen_client=QwenClient(model=args.model, timeout_seconds=args.qwen_timeout_seconds),
            risk_provider=None,
            order_provider=None,
            broker=None,
            timeframe_auditor=TimeframeExpectationAuditor(persistence),
        )
        persistence.append_events([debug_event(args.pair, {
            "mode": "DEBUG_NO_ORDERS", "execution_enabled": False,
            "strategy_id": SPEC.definition.strategy_id, "model": args.model,
            "status": "STARTED",
        }, "VNEXT_DEBUG_SERVICE_STARTED")])

        cycle_number = 0
        while args.max_cycles == 0 or cycle_number < args.max_cycles:
            heartbeat.ensure_owned()
            cycle_number += 1
            try:
                result = service.run_once()
                payload = diagnostic_payload(result, cycle_number=cycle_number, model=args.model,
                                             entry_gate_reason=entry_gate["reason"])
                persistence.append_events([debug_event(args.pair, payload)])
                print(json.dumps(payload, sort_keys=True), flush=True)
            except Exception as exc:
                payload = {
                    "mode": "DEBUG_NO_ORDERS", "execution_enabled": False,
                    "cycle_number": cycle_number, "strategy_id": SPEC.definition.strategy_id,
                    "error_type": type(exc).__name__, "error": str(exc)[:500],
                }
                persistence.append_events([debug_event(args.pair, payload, "VNEXT_DEBUG_CYCLE_FAILED")])
                print(json.dumps(payload, sort_keys=True), flush=True)
            heartbeat.ensure_owned()
            if args.max_cycles == 0 or cycle_number < args.max_cycles:
                time.sleep(args.interval_seconds)
        return 0
    finally:
        heartbeat.stop()
        if initialized:
            mt5.shutdown()
        lease.release()
        persistence.close()


if __name__ == "__main__":
    raise SystemExit(main())
