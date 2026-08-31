"""Best-effort compact execution lifecycle events for episode memory."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from storage_factory import create_intelligence_store

log = logging.getLogger(__name__)
_lock = threading.Lock()
_store: Any = None
GRAPH_EXECUTION_EVENTS = {
    "mt5_execution_started", "mt5_fill", "mt5_execution_closed", "mt5_execution_skipped"
}


def _intelligence_store() -> IntelligenceStore:
    global _store
    with _lock:
        if _store is None:
            path = Path(__file__).resolve().parents[1] / "cache" / "market-intelligence.sqlite3"
            _store = create_intelligence_store(path)
        return _store


def append_execution_event(record: dict) -> bool:
    """Append a bounded lifecycle event without ever raising into execution."""
    if os.environ.get("QWEN_DISABLE_FILE_LOGGING") == "1":
        return False
    try:
        name = str(record.get("event") or "")
        symbol = record.get("symbol") or (record.get("plan") or {}).get("symbol")
        proposal_id = record.get("proposal_id")
        if name not in GRAPH_EXECUTION_EVENTS or not symbol or not proposal_id:
            return False
        identity = {
            "event": name,
            "execution_id": record.get("execution_id"),
            "proposal_id": proposal_id,
            "created_at_utc": record.get("created_at_utc"),
        }
        suffix = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        fill = record.get("fill") or {}
        plan = record.get("plan") or {}
        event = {
            "event_id": f"execution:{name}:{suffix}",
            "symbol": str(symbol),
            "timeframe": str(plan.get("signal_timeframe") or "M1").upper(),
            "event_type": "execution_event",
            "event_time_utc": record["created_at_utc"],
            "evidence_id": proposal_id,
            "payload": {
                "episode_id": proposal_id,
                "execution_id": record.get("execution_id"),
                "event_name": name,
                "reason": record.get("reason"),
                "side": plan.get("side") or record.get("side"),
                "entry_price": fill.get("price") or record.get("average_entry"),
                "exit_price": record.get("exit_price"),
                "net_pnl": record.get("net_pnl"),
                "gross_pnl": record.get("gross_pnl"),
                "mfe": record.get("peak_favorable_price_move"),
                "mae": record.get("adverse_price_move"),
                "duration_seconds": record.get("position_holding_seconds"),
            },
        }
        inserted = _intelligence_store().append_event(event)
        if name == "mt5_execution_closed" and record.get("fills"):
            from .trade_journal import journal_closed_trade
            journal_closed_trade(record)
        return inserted
    except Exception:
        log.warning("execution graph event append failed", exc_info=True)
        return False
