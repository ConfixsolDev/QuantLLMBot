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


def _intraday_story_event(record: dict, parsed: dict, context: dict) -> dict:
    """Build a replay-safe, bounded graph event for Qwen's market notebook."""
    snapshot = context.get("observer_snapshot") or {}
    structure = snapshot.get("structure") or {}
    sequence = (structure.get("sequence") or [])[-12:]
    deterministic_levels = (snapshot.get("levels") or [])[:12]
    qwen_by_level = {
        str(row.get("level_id")): row
        for row in (parsed.get("level_reads") or [])[:6]
        if row.get("level_id")
    }
    level_reads = []
    for row in deterministic_levels:
        level_id = str(row.get("level_id") or "")
        if not level_id:
            continue
        interpretation = qwen_by_level.get(level_id) or {}
        level_reads.append({
            "level_id": level_id,
            "timeframe": row.get("timeframe"),
            "role": row.get("role"),
            "price": row.get("price"),
            "zone_low": row.get("zone_low"),
            "zone_high": row.get("zone_high"),
            "touch_episodes_today": row.get("touch_episodes_today"),
            "last_touch_utc": row.get("last_touch_utc"),
            "latest_closed_response": row.get("latest_closed_response"),
            "current_relation": row.get("current_relation"),
            "qwen_quality": interpretation.get("quality"),
            "qwen_price_story": str(interpretation.get("price_story") or "")[:500],
            "next_verification": str(interpretation.get("next_verification") or "")[:500],
        })

    evidence_ids = list(dict.fromkeys(
        str(value)
        for value in (
            [(snapshot.get("today_tape") or {}).get("latest_evidence_id")]
            + [row.get("evidence_id") for row in sequence]
            + [row.get("evidence_id") for row in (snapshot.get("notable_closed_moves") or [])]
        )
        if value
    ))[:24]
    episode_id = str(context.get("episode_id") or parsed.get("episode_id") or "unknown")
    fingerprint = str(context.get("fingerprint") or "unknown")
    symbol = str(record.get("symbol") or "UNKNOWN")
    structure_read = parsed.get("structure_read") or {}
    prior = parsed.get("prior_view_review") or {}
    tape = snapshot.get("today_tape") or {}
    event_id = f"intraday-story:{symbol}:{episode_id}:{fingerprint}"
    return {
        "event_id": event_id,
        "symbol": symbol,
        "timeframe": "M5",
        "event_type": "intraday_story",
        "event_time_utc": record["recorded_at_utc"],
        "evidence_id": evidence_ids[-1] if evidence_ids else None,
        "payload": {
            "episode_id": episode_id,
            "decision_type": "intraday_observer",
            "decision_state": str(structure_read.get("state") or "unclear"),
            "state": str(structure_read.get("state") or "unclear"),
            "summary": str(parsed.get("market_story") or "")[:1000],
            "market_story": str(parsed.get("market_story") or "")[:2000],
            "sequence_explanation": str(structure_read.get("sequence_explanation") or "")[:1200],
            "drivers_so_far": str(structure_read.get("drivers_so_far") or "")[:1200],
            "contradicting_evidence": str(structure_read.get("contradicting_evidence") or "")[:1000],
            "prior_view_status": prior.get("status"),
            "prior_view_reason": str(prior.get("reason") or "")[:1000],
            "next_focus": str(parsed.get("next_focus") or "")[:1000],
            "model": record.get("model"),
            "mode": "shadow_only",
            "execution_authority": False,
            "eligible_for_live_context": False,
            "observer_contract_version": context.get("contract_version"),
            "observer_fingerprint": fingerprint,
            "trigger": context.get("trigger"),
            "day_open": tape.get("open"),
            "day_high": tape.get("high"),
            "day_low": tape.get("low"),
            "day_close": tape.get("close"),
            "day_net_move": tape.get("net_move"),
            "day_range": tape.get("range"),
            "structure_method": structure.get("method"),
            "deterministic_structure_state": structure.get("state"),
            "structure_sequence": sequence,
            "level_reads": level_reads,
            "notable_closed_moves": (snapshot.get("notable_closed_moves") or [])[-8:],
            "session": snapshot.get("session") or {},
            "evidence_ids": evidence_ids,
            "prompt_hash": hashlib.sha256(
                str(record.get("prompt_text") or "").encode("utf-8")
            ).hexdigest()[:20] if record.get("prompt_text") else None,
            "response_hash": hashlib.sha256(
                str(record.get("raw_response") or "").encode("utf-8")
            ).hexdigest()[:20],
        },
    }


def append_decision_event(record: dict) -> bool:
    """Append a bounded graph-ready decision event; never raise into trading."""
    if os.environ.get("QWEN_DISABLE_FILE_LOGGING") == "1":
        return False
    try:
        parsed = record.get("parsed") or {}
        context = record.get("context") or {}
        plan = parsed.get("execution_plan") or {}
        decision_type = str(record.get("decision_type") or "unknown")
        if decision_type == "intraday_observer":
            return _intelligence_store().append_event(
                _intraday_story_event(record, parsed, context)
            )
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
