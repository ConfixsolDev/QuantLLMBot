"""Order-enabled V2 demo worker. Explicit opt-in only; never use for live accounts."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from vnext.data.news_calendar import DailyNewsCalendar
from vnext.execution.boundary import build_order_intent
from vnext.execution.mt5 import MT5IdempotentBroker
from vnext.llm.client import QwenClient
from vnext.recovery.magic_reconciler import MagicPositionReconciler
from vnext.risk.mt5 import live_risk_inputs
from vnext.runtime.live_cycle import LiveVNextCycle, MT5ClosedBarSource
from vnext.runtime.mt5_position_monitor import MT5PositionMonitor
from vnext.runtime.position_management import ManagementProfile, PositionManagementService
from vnext.runtime.qwen_management import QwenManagementReviewer
from vnext.runtime.service import VNextService
from vnext.runtime.lease import LeaseHeartbeat, VNextLease
from vnext.storage.persistence import from_environment
from vnext.strategy.xau_m15_m1_structure_scalper import DEFINITION, MANAGEMENT, SPEC, candidate_inputs
from vnext.strategy.timeframe_audit import TimeframeExpectationAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-demo-submissions", action="store_true")
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--lookback", type=int, default=300)
    parser.add_argument("--max-cycles", type=int, default=0)
    args = parser.parse_args()
    if not args.enable_demo_submissions or os.environ.get("QWEN_VNEXT_DEMO_SUBMISSIONS") != "1":
        raise RuntimeError("demo submissions require --enable-demo-submissions and QWEN_VNEXT_DEMO_SUBMISSIONS=1")
    if args.interval_seconds <= 0 or args.lookback < 300 or args.max_cycles < 0:
        raise ValueError("invalid demo worker parameters")
    import MetaTrader5 as mt5
    persistence = None
    lease = None
    heartbeat = None
    try:
        persistence = from_environment(dsn=os.environ.get("QWEN_TIMESCALE_DSN", ""),
                                       redis_url=os.environ.get("QWEN_REDIS_URL", ""),
                                       neo4j_uri=os.environ.get("QWEN_NEO4J_URI", "bolt://127.0.0.1:7687"),
                                       neo4j_user=os.environ.get("QWEN_NEO4J_USER", "neo4j"),
                                       neo4j_password=os.environ.get("QWEN_NEO4J_PASSWORD", ""))
        if not persistence.ensure_ready().ready:
            raise RuntimeError("V2 durable stores are not ready")
        lease = VNextLease(persistence.working_memory.client,
                           name="qwen:vnext:demo-service:lease", ttl_seconds=180)
        if not lease.acquire():
            raise RuntimeError("another vNext demo service owns the lease")
        heartbeat = LeaseHeartbeat(lease)
        heartbeat.start()
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        account = mt5.account_info()
        if account is None or getattr(account, "trade_mode", None) != getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0):
            raise RuntimeError("V2 demo worker refuses a non-demo account")
        transport = MT5IdempotentBroker(mt5, magic=DEFINITION.magic_number, submission_store=persistence.submissions)
        qwen = QwenClient(model=os.environ.get("QWEN_VNEXT_MODEL", "qwen-trading-v005:latest"))
        manager = PositionManagementService(
            profiles={DEFINITION.strategy_id: ManagementProfile(DEFINITION.strategy_id, MANAGEMENT)},
            broker=transport, reviewer=QwenManagementReviewer(qwen))
        monitor = MT5PositionMonitor(mt5=mt5, broker=transport.transport, manager=manager,
                                     strategy_id=DEFINITION.strategy_id)
        cycle = LiveVNextCycle(pair=DEFINITION.pair, source=MT5ClosedBarSource(mt5),
                               persistence=persistence, lookback=args.lookback)
        calendar = DailyNewsCalendar(persistence.working_memory, durable_store=persistence)
        refreshed_day: str | None = None

        def gated_candidate(state: Mapping[str, Any]) -> Mapping[str, Any] | None:
            nonlocal refreshed_day
            frontier = datetime.fromisoformat(str(state["time_frontier_utc"]).replace("Z", "+00:00"))
            day = frontier.astimezone(timezone.utc).date().isoformat()
            if refreshed_day != day:
                refreshed_day = day
                try:
                    calendar.refresh(now=frontier)
                except Exception:
                    pass
            return candidate_inputs(state) if calendar.gate(now=frontier).allowed else None

        service = VNextService(cycle=cycle, strategy=SPEC, candidate_provider=gated_candidate,
                               qwen_client=qwen, broker=transport,
                               timeframe_auditor=TimeframeExpectationAuditor(persistence),
                               risk_provider=lambda state, candidate: live_risk_inputs(mt5, state, candidate,
                                                                                         magic_number=DEFINITION.magic_number),
                               order_provider=lambda evaluation: build_order_intent(evaluation.candidate, evaluation.risk))
        reconciler = MagicPositionReconciler(magic_number=DEFINITION.magic_number, store=persistence)
        count = 0
        while args.max_cycles == 0 or count < args.max_cycles:
            heartbeat.ensure_owned()
            count += 1
            recovery = reconciler.run(transport, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
            monitor.run_once()
            if recovery.new_trade_creation_allowed:
                service.run_once()
            if args.max_cycles == 0 or count < args.max_cycles:
                time.sleep(args.interval_seconds)
        return 0
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        if lease is not None:
            lease.release()
        mt5.shutdown()
        if persistence is not None:
            persistence.close()


if __name__ == "__main__":
    raise SystemExit(main())
