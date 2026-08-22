"""Best-effort compact decision events for temporal graph memory.

Full prompts and raw responses remain in the immutable JSONL audit. This module
adds only bounded decision metadata and provenance to the SQLite intelligence
ledger, where the graph outbox can project it asynchronously.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from pathlib import Path

from .store import IntelligenceStore

log = logging.getLogger(__name__)
_lock = threading.Lock()
_store: IntelligenceStore | None = None


def _intelligence_store() -> IntelligenceStore:
    global _store
    with _lock:
        if _store is None:
            path = Path(__file__).resolve().parents[1] / "cache" / "market-intelligence.sqlite3"
            _store = IntelligenceStore(path, busy_timeout_ms=50)
        return _store


def _decision_id(record: dict) -> str:
    identity = {
        "recorded_at_utc": record.get("recorded_at_utc"),
        "decision_type": record.get("decision_type"),
        "proposal_id": record.get("proposal_id"),
        "position_id": record.get("mt5_position_id"),
        "model": record.get("model"),
    }
    suffix = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"decision:{record.get('decision_type') or 'unknown'}:{suffix}"


def append_decision_event(record: dict) -> bool:
    """Append a bounded graph-ready decision event; never raise into trading."""
    if os.environ.get("QWEN_DISABLE_FILE_LOGGING") == "1":
        return False
    try:
        parsed = record.get("parsed") or {}
        context = record.get("context") or {}
        plan = parsed.get("execution_plan") or {}
        decision_type = str(record.get("decision_type") or "unknown")
        episode_id = (
            record.get("proposal_id")
            or context.get("entry_proposal_id")
            or (f"position:{record.get('mt5_position_id')}" if record.get("mt5_position_id") else None)
        )
        state = (
            parsed.get("bias") if decision_type == "entry"
            else parsed.get("action") or parsed.get("plan_status") or "unknown"
        )
        evidence_ids = list(dict.fromkeys(
            str(value) for value in (parsed.get("evidence_ids") or []) if value
        ))[:24]
        event = {
            "event_id": _decision_id(record),
            "symbol": str(record.get("symbol") or "UNKNOWN"),
            "timeframe": str(plan.get("signal_timeframe") or "M1").upper(),
            "event_type": "qwen_decision",
            "event_time_utc": record["recorded_at_utc"],
            "evidence_id": evidence_ids[-1] if evidence_ids else None,
            "payload": {
                "episode_id": episode_id,
                "decision_type": decision_type,
                "decision_state": str(state or "unknown").lower(),
                "confidence": parsed.get("confidence"),
                "summary": str(parsed.get("summary") or parsed.get("note") or "")[:1000],
                "model": record.get("model"),
                "proposal_id": record.get("proposal_id"),
                "position_id": record.get("mt5_position_id"),
                "evidence_ids": evidence_ids,
                "acknowledged_epochs": parsed.get("acknowledged_epochs") or {},
                "prompt_hash": hashlib.sha256(
                    str(record.get("prompt_text") or "").encode("utf-8")
                ).hexdigest()[:20] if record.get("prompt_text") else None,
                "response_hash": hashlib.sha256(
                    str(record.get("raw_response") or "").encode("utf-8")
                ).hexdigest()[:20],
            },
        }
        return _intelligence_store().append_event(event)
    except Exception:
        log.warning("decision graph event append failed", exc_info=True)
        return False
