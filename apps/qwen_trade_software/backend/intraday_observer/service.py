"""Dedicated Qwen reflection service for the completed intraday tape."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from datetime import datetime, timezone

import build_manifest
import process_logging
from market_context_cache import (
    get_cached_completed_bars,
    latest_observer_facts,
    load_prompt_section,
)
from review_shared import LOG_DIR, STORE_ROOT, gold_market_open, ollama_generate, sync_model_residency
from runtime_config import PRIMARY_MARKET_SYMBOL, model_for_role
from tick_data_archive import append_qwen_decision

from .contracts import CONTRACT_VERSION, read_state, write_state
from .deterministic import build_snapshot
from .scheduler import review_due


SYMBOL = PRIMARY_MARKET_SYMBOL
MODEL = model_for_role("context")
# Ten seconds guarantees an eligible check near every M1 boundary regardless
# of the worker's startup second; a 20-second phase could permanently miss it.
POLL_SECONDS = max(5, int(os.environ.get("QWEN_INTRADAY_OBSERVER_POLL_SECONDS", "10")))
EVENT_REVIEW_COOLDOWN_SECONDS = max(
    60, int(os.environ.get("QWEN_INTRADAY_OBSERVER_EVENT_COOLDOWN_SECONDS", "300"))
)
MODEL_TIMEOUT_SECONDS = min(
    30, max(5, int(os.environ.get("QWEN_INTRADAY_OBSERVER_TIMEOUT_SECONDS", "30")))
)
MIN_SECONDS_BEFORE_M1_CLOSE = MODEL_TIMEOUT_SECONDS + 5
SINGLETON_PORT = 48636

_LOG_HANDLER = process_logging.configure(
    LOG_DIR / "intraday-observer.log", owner="intraday_observer"
)
build_manifest.log_identity("intraday_observer")


def observer_schema(level_ids: list[str], episode_id: str) -> dict:
    ids = sorted(set(level_ids)) or ["__no_level__"]
    return {
        "type": "object",
        "properties": {
            "episode_id": {"type": "string", "const": episode_id},
            "market_story": {"type": "string", "maxLength": 220},
            "structure_read": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "enum": ["bullish", "bearish", "range", "transition", "unclear"],
                    },
                    "sequence_explanation": {"type": "string", "maxLength": 140},
                    "drivers_so_far": {"type": "string", "maxLength": 140},
                    "contradicting_evidence": {"type": "string", "maxLength": 100},
                },
                "required": [
                    "state", "sequence_explanation", "drivers_so_far", "contradicting_evidence"
                ],
                "additionalProperties": False,
            },
            "level_reads": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "level_id": {"type": "string", "enum": ids},
                        "quality": {
                            "type": "string",
                            "enum": ["clear", "developing", "mixed", "failed", "untested"],
                        },
                        "price_story": {"type": "string", "maxLength": 100},
                        "next_verification": {"type": "string", "maxLength": 90},
                    },
                    "required": ["level_id", "quality", "price_story", "next_verification"],
                    "additionalProperties": False,
                },
                "maxItems": 3,
            },
            "prior_view_review": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["confirmed", "weakened", "invalidated", "unresolved", "none"],
                    },
                    "reason": {"type": "string", "maxLength": 100},
                },
                "required": ["status", "reason"],
                "additionalProperties": False,
            },
            "next_focus": {"type": "string", "maxLength": 100},
        },
        "required": [
            "episode_id", "market_story", "structure_read", "level_reads",
            "prior_view_review", "next_focus",
        ],
        "additionalProperties": False,
    }


def build_prompt(snapshot: dict) -> str:
    contract = load_prompt_section("qwen_intraday_observer", STORE_ROOT)
    return (
        contract
        + "\n\nINTRADAY OBSERVER FACTS:\n"
        + json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False)
    )


def run_once(now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    market = gold_market_open(now)
    sync_model_residency(market)
    if not market.get("open"):
        return {"status": "skipped", "reason": f"market_closed:{market.get('reason')}"}

    cache = latest_observer_facts(SYMBOL, now=now)
    if cache.get("status") != "ready":
        return {"status": "skipped", "reason": f"cache:{cache.get('status')}"}
    previous = read_state()
    snapshot = build_snapshot(
        symbol=SYMBOL,
        level_rows=cache.get("levels") or [],
        bar_provider=get_cached_completed_bars,
        now=now,
        prior_analysis=previous.get("qwen_analysis") or {},
        session=cache.get("session") or {},
    )
    due, reason = review_due(
        snapshot, previous, now,
        event_cooldown_seconds=EVENT_REVIEW_COOLDOWN_SECONDS,
    )
    if not due:
        return {"status": "skipped", "reason": reason}
    # A reflection may not start unless its hard timeout fits before the next
    # M1 boundary.  Together with the non-waiting model lock this prevents the
    # background notebook from queuing ahead of the next candle decision.
    seconds_to_next_m1 = 60 - now.second
    if seconds_to_next_m1 < MIN_SECONDS_BEFORE_M1_CLOSE:
        return {"status": "deferred", "reason": "insufficient_m1_quiet_window"}
    prompt = build_prompt(snapshot)
    schema = observer_schema(
        [row.get("level_id") for row in snapshot.get("levels") or [] if row.get("level_id")],
        snapshot["episode_id"],
    )
    try:
        result = ollama_generate(
            prompt,
            timeout=MODEL_TIMEOUT_SECONDS,
            num_predict=320,
            num_ctx=8192,
            format_schema=schema,
            model=MODEL,
            # Background reflection never waits behind entry or management.
            lock_timeout=0.05,
        )
    except TimeoutError as error:
        reason = (
            "live_qwen_generation_active"
            if "lock" in str(error).lower()
            else "qwen_generation_timeout"
        )
        return {"status": "deferred", "reason": reason}
    raw = result.get("response", "{}")
    analysis = json.loads(raw)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state = {
        "contract_version": CONTRACT_VERSION,
        "symbol": SYMBOL,
        "generated_at_utc": generated_at,
        "trigger": reason,
        "execution_authority": False,
        "deterministic": snapshot,
        "qwen_analysis": analysis,
        "model": MODEL,
    }
    write_state(state)
    append_qwen_decision(
        decision_type="intraday_observer",
        symbol=SYMBOL,
        price=(snapshot.get("today_tape") or {}).get("close"),
        prompt_text=prompt,
        raw_response=raw,
        parsed=analysis,
        model=MODEL,
        duration_ns=result.get("total_duration"),
        atr=result.get("market_atr"),
        context={
            "contract_version": CONTRACT_VERSION,
            "episode_id": snapshot.get("episode_id"),
            "fingerprint": snapshot.get("fingerprint"),
            "trigger": reason,
            "execution_authority": False,
            # Bounded graph projection input. Full prompt/response stays in the
            # immutable Qwen log; SQLite/outbox owns replay into Neo4j.
            "observer_snapshot": {
                "today_tape": snapshot.get("today_tape") or {},
                "session": snapshot.get("session") or {},
                "structure": snapshot.get("structure") or {},
                "levels": (snapshot.get("levels") or [])[:12],
                "notable_closed_moves": (snapshot.get("notable_closed_moves") or [])[-8:],
            },
        },
    )
    logging.info(
        "Intraday story updated episode=%s trigger=%s levels=%d",
        snapshot.get("episode_id"), reason, len(snapshot.get("levels") or []),
    )
    return state


def main() -> None:
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", SINGLETON_PORT))
        singleton.listen(1)
    except OSError as error:
        process_logging.structured_event(
            "worker_singleton_conflict",
            level=logging.ERROR,
            worker="intraday_observer",
            port=SINGLETON_PORT,
            error=str(error),
        )
        return
    logging.info("Qwen intraday observer starting; poll=%ds", POLL_SECONDS)
    process_logging.structured_event(
        "worker_started",
        worker="intraday_observer",
        poll_seconds=POLL_SECONDS,
        port=SINGLETON_PORT,
        model=MODEL,
    )
    while True:
        started = time.monotonic()
        try:
            result = run_once()
            if result.get("status") in {"deferred", "skipped"}:
                logging.info("Intraday observer %s: %s", result["status"], result.get("reason"))
            process_logging.structured_event(
                "observer_cycle",
                status=result.get("status", "story_updated"),
                reason=result.get("reason"),
                episode_id=result.get("episode_id")
                or (result.get("qwen_analysis") or {}).get("episode_id"),
                trigger=result.get("trigger"),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
        except Exception as error:
            logging.exception("Intraday observer cycle failed")
            process_logging.structured_event(
                "observer_cycle",
                level=logging.ERROR,
                status="error",
                error_type=type(error).__name__,
                error=str(error),
                duration_ms=round((time.monotonic() - started) * 1000, 2),
            )
        elapsed = time.monotonic() - started
        time.sleep(max(1, POLL_SECONDS - elapsed))
