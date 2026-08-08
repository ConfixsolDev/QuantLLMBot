"""Entry decision: the "should we open a trade" half of the Qwen paper-trading system.

2026-08-06 split: this file used to also run trade management (the ongoing
in-trade review loop). That moved to trade_management.py as its own process
-- see that file's module docstring for the rationale. This file now owns
only: asking Qwen for a new setup when no Qwen position is open, recording
the resulting proposal, and serving the dashboard HTTP API the frontend
polls. It has no MT5 connection of its own; all live broker data (price,
positions, today's stats) comes from trade_management.py's
management-dashboard-state.json, which this process only ever reads.
"""

import json
import logging.handlers
import os
import socket
import threading
import time
import uuid
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from market_context_cache import (
    latest_entry_context,
    load_prompt_section,
)
from review_shared import (
    DEFAULT_ENTRY_QWEN_STATE,
    DEFAULT_MANAGEMENT_STATE,
    ENTRY_STATE_FILE,
    LOG_DIR,
    MANAGEMENT_STATE_FILE,
    PLANNER_STATE_FILE,
    STORE_ROOT,
    _dated_log_files,
    _dated_log_path,
    load_review_tickets,
    normalize_confidence,
    normalize_invalidation,
    normalize_text,
    ollama_generate,
    read_json_safe,
    save_review_tickets,
    warm_model,
    write_json_atomic,
)
from session_planner import DEFAULT_PLANNER_STATE, load_plan_history, read_chart_candles
from tick_data_archive import append_qwen_decision, append_tick_record


# 2026-08-06: kept separate from trade_management.py's
# QWEN_REVIEW_INTERVAL_SECONDS on purpose -- "how often to check for a new
# setup when flat" and "how often to review an open trade" are different
# concerns now that they're different processes, and may end up tuned to
# different values once real numbers are in from the faster GPU machine.
# Defaults to the same 30s starting point either way.
INTERVAL_SECONDS = int(os.environ.get("QWEN_ENTRY_INTERVAL_SECONDS", "30"))
DAILY_PAPER_CAP = 100
MIN_ENTRY_CONFIDENCE = 51
QWEN_PLAN_GATING = os.environ.get("QWEN_PLAN_GATING", "0") == "1"
QWEN_DECISION_LOCK = threading.Lock()


def latest_paper_execution():
    for path in _dated_log_files("paper-executions"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def append_paper_proposal(
    snapshot: dict,
    review: dict,
    raw_response: str,
    decision_wall_seconds: float | None = None,
    decision_duration_ns: int | None = None,
    prompt_text: str | None = None,
    planner_context: dict | None = None,
) -> dict:
    """Append an immutable research record for later chart replay and feedback.

    decision_wall_seconds / decision_duration_ns capture how long the Qwen
    entry-decision call itself took (None when no call was made, e.g. the
    cache-not-ready or off-session branches). This is the latency between
    the market snapshot Qwen reasoned about and the moment the proposal is
    even written — a gap that previously wasn't logged anywhere, even
    though everything downstream of it (the proposal's own 60s TTL,
    execution) is timed from *after* this gap already happened.
    """
    created_at = datetime.now(timezone.utc)
    proposal = {
        "schema_version": 1,
        "proposal_id": f"paper-{created_at:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
        "created_at_utc": created_at.isoformat(),
        "mode": "paper-research",
        "source": "dashboard-deal-sheet",
        "symbol": snapshot.get("symbol"),
        "timeframe": snapshot.get("timeframe"),
        "market": {
            "price": snapshot.get("price"),
            "connected": snapshot.get("connected"),
            "levels": snapshot.get("decision_levels", snapshot.get("levels", {})),
            "market_context": snapshot.get("market_context", {}),
            "cache_context": snapshot.get("entry_cache", {}),
            "positions_visible": snapshot.get("positions", []),
            "today": snapshot.get("today", {}),
        },
        "qwen": {
            "model": snapshot.get("model"),
            "bias": review.get("bias", "Conditional"),
            "confidence_raw": review.get("confidence"),
            "confidence": normalize_confidence(review.get("confidence"), 0),
            "summary": review.get("summary", "No summary returned."),
            "invalidation": review.get(
                "invalidation", "No invalidation returned."
            ),
            "execution_plan": review.get(
                "execution_plan",
                {"status": "wait", "reason": "No paper execution plan."},
            ),
            "decision_wall_seconds": decision_wall_seconds,
            "decision_duration_ns": decision_duration_ns,
            "raw_response": raw_response,
            "prompt_text": prompt_text,
        },
        "human_feedback": None,
        "paper_execution": None,
    }
    if planner_context:
        proposal["day_plan_id"] = planner_context.get("day_plan_id")
        proposal["session_plan_id"] = planner_context.get("session_plan_id")
    append_tick_record("paper-proposals", proposal)
    logging.info("Paper proposal recorded: %s", proposal["proposal_id"])
    return proposal


_LOG_HANDLER = logging.handlers.TimedRotatingFileHandler(
    filename=LOG_DIR / "reviewer.log", when="midnight", encoding="utf-8"
)
_LOG_HANDLER.suffix = "%Y-%m-%d"
_LOG_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_LOG_HANDLER])


def adaptive_stop_distance(snapshot: dict) -> float:
    """Size gold breathing room from recent closed M1/M5 ranges, capped at 3-5."""
    def median_range(timeframe: str) -> float:
        values = sorted(
            max(0.0, float(row["high"]) - float(row["low"]))
            for row in snapshot.get("market_context", {}).get(timeframe, [])
            if row.get("high") is not None and row.get("low") is not None
        )
        if not values:
            return 0.0
        middle = len(values) // 2
        return (
            values[middle]
            if len(values) % 2
            else (values[middle - 1] + values[middle]) / 2
        )

    m1_range = median_range("M1")
    m5_range = median_range("M5")
    return round(max(3.0, min(5.0, max(m1_range * 2, m5_range * 0.75))), 3)


def cache_levels_for_decision(entry_cache: dict) -> dict:
    """Group cache-owned levels into the compact entry-decision map."""
    grouped: dict[str, list[dict]] = {}
    for row in entry_cache.get("levels", []):
        grouped.setdefault(str(row["timeframe"]), []).append(
            {
                "id": str(row["level_id"]),
                "price": float(row["zone_low"]),
                "zone_high": float(row["zone_high"]),
                "role": row.get("role"),
                "source_candle_ids": row.get("source_candle_ids", []),
            }
        )
    for rows in grouped.values():
        rows.sort(key=lambda row: row["price"])
    return grouped


def entry_decision_schema(entry_cache: dict, decision_levels: dict) -> dict:
    level_ids = sorted(
        row["id"] for rows in decision_levels.values() for row in rows
    )
    epochs = entry_cache["epochs"]
    return {
        "type": "object",
        "properties": {
            "bias": {"type": "string", "enum": ["buy", "sell", "conditional"]},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary": {"type": "string", "maxLength": 120},
            "acknowledged_epochs": {
                "type": "object",
                "properties": {
                    key: {"type": "string", "const": value}
                    for key, value in epochs.items()
                },
                "required": sorted(epochs),
                "additionalProperties": False,
            },
            "evidence_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": entry_cache["known_evidence_ids"],
                },
                "minItems": 1,
                "maxItems": 6,
            },
            "execution_plan": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["ready", "wait"]},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "entry_low_id": {"type": "string", "enum": level_ids},
                    "entry_high_id": {"type": "string", "enum": level_ids},
                    "stop_level_id": {"type": "string", "enum": level_ids},
                    "target_level_id": {"type": "string", "enum": level_ids},
                    "volume_each": {"type": "number", "const": 0.5},
                    "reason": {"type": "string", "maxLength": 120},
                },
                "required": ["status", "reason"],
                "additionalProperties": False,
            },
        },
        "required": [
            "bias", "confidence", "summary", "acknowledged_epochs",
            "evidence_ids", "execution_plan",
        ],
        "additionalProperties": False,
    }


def validate_entry_provenance(review: dict, entry_cache: dict) -> list[str]:
    failures = []
    if review.get("acknowledged_epochs") != entry_cache.get("epochs"):
        failures.append("entry:cache_epoch_mismatch")
    cited = review.get("evidence_ids")
    known = set(entry_cache.get("known_evidence_ids", []))
    if not isinstance(cited, list) or not cited:
        failures.append("entry:cache_evidence_missing")
    elif not set(cited).issubset(known):
        failures.append("entry:invented_cache_evidence")
    return failures


def cache_fallback_geometry(
    side: str, decision_levels: dict, quote: float
) -> dict | None:
    """Map a clear Qwen side onto nearby cache-owned execution levels."""
    level_rows = [
        (str(row["id"]), float(row["price"]), timeframe)
        for timeframe, rows in decision_levels.items()
        for row in rows
    ]
    if len(level_rows) < 4:
        return None

    entry_points = None
    for timeframe in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        rows = sorted(
            {
                (str(row["id"]), float(row["price"]))
                for row in decision_levels.get(timeframe, [])
            },
            key=lambda item: item[1],
        )
        if len(rows) < 2:
            continue
        pairs = list(zip(rows, rows[1:]))
        entry_points = min(
            pairs,
            key=lambda pair: (
                0.0
                if pair[0][1] <= quote <= pair[1][1]
                else min(abs(quote - pair[0][1]), abs(quote - pair[1][1])),
                pair[1][1] - pair[0][1],
            ),
        )
        break
    if entry_points is None:
        return None

    (entry_low_id, entry_low), (entry_high_id, entry_high) = entry_points
    lower = sorted(
        (row for row in level_rows if row[1] < entry_low),
        key=lambda row: row[1],
        reverse=True,
    )
    upper = sorted(
        (row for row in level_rows if row[1] > entry_high),
        key=lambda row: row[1],
    )
    if not lower or not upper:
        return None
    stop_level_id, stop_loss, _ = lower[0] if side == "buy" else upper[0]
    target_level_id, take_profit, _ = upper[0] if side == "buy" else lower[0]
    return {
        "entry_low_id": entry_low_id,
        "entry_high_id": entry_high_id,
        "stop_level_id": stop_level_id,
        "target_level_id": target_level_id,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }


def load_active_planner_context() -> dict:
    planner = read_json_safe(PLANNER_STATE_FILE, DEFAULT_PLANNER_STATE)
    day_plan = planner.get("day_plan")
    session_plan = planner.get("session_plan")
    return {
        "planner_status": planner.get("planner_status"),
        "clock": planner.get("clock", {}),
        "day_plan_id": day_plan.get("day_plan_id") if day_plan else None,
        "session_plan_id": session_plan.get("session_plan_id") if session_plan else None,
        "day_plan_summary": {
            "tradeable": day_plan.get("tradeable") if day_plan else False,
            "key_levels": day_plan.get("key_levels", []) if day_plan else [],
            "expected_session_behaviour": day_plan.get("expected_session_behaviour", {})
            if day_plan
            else {},
        },
        "session_plan_summary": {
            "tradeable": session_plan.get("tradeable") if session_plan else False,
            "active_scenario": session_plan.get("active_scenario") if session_plan else None,
            "entry_zones": session_plan.get("entry_zones", []) if session_plan else [],
            "confidence": session_plan.get("confidence") if session_plan else 0,
        },
    }


def validate_entry_against_plan(execution_plan: dict, planner_context: dict) -> list[str]:
    if not QWEN_PLAN_GATING:
        return []
    failures = []
    session_summary = planner_context.get("session_plan_summary", {})
    if not session_summary.get("tradeable"):
        failures.append("entry:session_plan_not_tradeable")
        return failures
    side = str(execution_plan.get("side", "")).lower()
    entry_low = float(execution_plan.get("entry_low", 0))
    entry_high = float(execution_plan.get("entry_high", 0))
    zones = session_summary.get("entry_zones", [])
    if not zones:
        failures.append("entry:no_session_entry_zones")
        return failures
    matched = False
    for zone in zones:
        if str(zone.get("side", "")).lower() != side:
            continue
        zone_bounds = zone.get("zone") or []
        if len(zone_bounds) != 2:
            continue
        lo, hi = sorted(float(v) for v in zone_bounds)
        if entry_low >= lo and entry_high <= hi:
            matched = True
            break
    if not matched:
        failures.append("entry:outside_session_plan_zone")
    return failures


def build_plan_snapshot() -> dict:
    planner = read_json_safe(PLANNER_STATE_FILE, DEFAULT_PLANNER_STATE)
    planner["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    planner["planner_alive"] = _planner_process_alive()
    return planner


def _planner_process_alive() -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.connect(("127.0.0.1", 48634))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def normalize_execution_plan(
    value,
    snapshot: dict,
    entry_cache: dict,
    bias: str | None = None,
    confidence=None,
) -> dict:
    """Accept clear intent while keeping geometry inside the validated cache."""
    def wait(reason):
        return {"status": "wait", "reason": reason}

    if not isinstance(value, dict):
        return wait("Qwen did not return a structured execution plan.")
    if str(value.get("status", "")).strip().lower() != "ready":
        return wait(normalize_text(value.get("reason"), "No paper setup is ready."))

    confidence_score = normalize_confidence(confidence, 0)
    if confidence_score < MIN_ENTRY_CONFIDENCE:
        return wait(
            f"Qwen confidence {confidence_score} is below "
            f"the {MIN_ENTRY_CONFIDENCE} entry minimum."
        )
    normalized_bias = str(bias or "").strip().lower()
    if normalized_bias not in ("buy", "sell"):
        return wait("Qwen must provide a clear buy or sell bias.")
    declared_side = str(value.get("side") or "").strip().lower()
    if declared_side and declared_side != normalized_bias:
        return wait("Qwen plan side contradicts its declared bias.")
    side = declared_side or normalized_bias
    level_map = {
        str(level["id"]): float(level["price"])
        for levels in snapshot.get("decision_levels", {}).values()
        for level in levels
    }
    geometry_source = "qwen_named_levels"
    try:
        entry_low_id = str(
            value.get("entry_low_id") or value.get("entry_id")
        )
        if entry_low_id not in level_map:
            raise KeyError(entry_low_id)
        entry_high_value = value.get("entry_high_id")
        entry_high_id = str(entry_high_value) if entry_high_value else entry_low_id
        stop_level_id = str(value.get("stop_level_id") or "")
        target_level_id = str(value.get("target_level_id") or "")
        if entry_high_id not in level_map or entry_high_id == entry_low_id:
            raise KeyError(entry_high_id)
        if stop_level_id not in level_map or target_level_id not in level_map:
            raise KeyError("stop_or_target")
        entry_points = sorted(
            ((entry_low_id, level_map[entry_low_id]),
             (entry_high_id, level_map[entry_high_id])),
            key=lambda item: item[1],
        )
        entry_low_id, entry_low = entry_points[0]
        entry_high_id, entry_high = entry_points[1]
        stop_loss = level_map[stop_level_id]
        take_profit = level_map[target_level_id]
        volume_each = 0.5
    except (KeyError, TypeError, ValueError):
        fallback = cache_fallback_geometry(
            side,
            snapshot.get("decision_levels", {}),
            float(
                entry_cache.get("minute", {}).get("quote", {}).get(
                    "ask" if side == "buy" else "bid",
                    snapshot.get("price", 0.0),
                )
            ),
        )
        if fallback is None:
            return wait("Validated cache cannot map complete entry geometry.")
        geometry_source = "cache_nearest_levels_fallback"
        entry_low_id = fallback["entry_low_id"]
        entry_high_id = fallback["entry_high_id"]
        stop_level_id = fallback["stop_level_id"]
        target_level_id = fallback["target_level_id"]
        entry_low = fallback["entry_low"]
        entry_high = fallback["entry_high"]
        stop_loss = fallback["stop_loss"]
        take_profit = fallback["take_profit"]
        volume_each = 0.5

    if side == "buy" and not (stop_loss < entry_low <= entry_high < take_profit):
        return wait("Mapped buy geometry has no valid stop or target room.")
    if side == "sell" and not (take_profit < entry_low <= entry_high < stop_loss):
        return wait("Mapped sell geometry has no valid stop or target room.")
    return {
        "status": "ready",
        "side": side,
        "entry_low_id": entry_low_id,
        "entry_high_id": entry_high_id,
        "stop_level_id": stop_level_id,
        "target_level_id": target_level_id,
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "stop_price_distance": adaptive_stop_distance(snapshot),
        "buckets": 1,
        "volume_each": volume_each,
        "decision_confidence": confidence_score,
        "cache_epochs": dict(entry_cache["epochs"]),
        "cache_model_digest": entry_cache.get("model_digest"),
        "cache_evidence_ids": list(snapshot.get("qwen_evidence_ids", [])),
        "cache_decision_time_utc": entry_cache.get("decision_time_utc"),
        "geometry_source": geometry_source,
        "reason": normalize_text(value.get("reason"), "Validated named-level setup."),
    }


def build_snapshot() -> dict:
    """Merge the two processes' dashboard-state files into the one /snapshot
    shape the frontend already expects.

    Live broker data (price, positions, today's stats, chart levels) always
    comes from trade_management.py's file, since only that process holds a
    live MT5 connection. The "qwen" field is whichever side is currently
    relevant: management's in-trade commentary while a Qwen position is
    open, otherwise entry's most recent thesis -- the same mutual
    exclusivity the single-process version had by construction (entry never
    generated a new deal sheet while a Qwen position was open).
    """
    management_state = read_json_safe(MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE)
    entry_state = read_json_safe(
        ENTRY_STATE_FILE, {"qwen": dict(DEFAULT_ENTRY_QWEN_STATE)}
    )
    snapshot = dict(management_state)
    qwen_owned_open = any(
        position.get("qwen_owned") for position in management_state.get("positions", [])
    )
    if qwen_owned_open and "qwen_management" in management_state:
        snapshot["qwen"] = management_state["qwen_management"]
    else:
        snapshot["qwen"] = entry_state.get("qwen", dict(DEFAULT_ENTRY_QWEN_STATE))
    snapshot.pop("qwen_management", None)
    return snapshot


def generate_dashboard_deal_sheet() -> dict:
    snapshot = read_json_safe(MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE)
    symbol = str(snapshot.get("symbol") or "XAUUSDr")
    entry_cache = latest_entry_context(symbol)
    snapshot["entry_cache"] = entry_cache
    decision_levels = (
        cache_levels_for_decision(entry_cache)
        if entry_cache.get("status") == "ready"
        else {}
    )
    snapshot["decision_levels"] = decision_levels
    planner_context = load_active_planner_context()
    snapshot["planner_context"] = planner_context
    # Only the branch below that actually calls Qwen sets these; the
    # wait/off-session branches never called the model, so None correctly
    # says "no decision latency to measure" rather than implying a 0s call.
    decision_wall_seconds = None
    decision_duration_ns = None
    prompt_text = None

    if entry_cache.get("status") != "ready":
        review = {
            "bias": "conditional",
            "confidence": 0,
            "summary": "Validated entry cache is unavailable.",
            "acknowledged_epochs": {},
            "evidence_ids": [],
            "execution_plan": {
                "status": "wait",
                "reason": entry_cache.get("reason", "Entry cache blocked."),
            },
            "entry_validation_failures": entry_cache.get("failures", []),
        }
        raw_response = json.dumps(review, separators=(",", ":"))
    elif not entry_cache.get("session", {}).get("trade_permitted", False):
        review = {
            "bias": "conditional",
            "confidence": 0,
            "summary": "Current session prohibits a new entry.",
            "acknowledged_epochs": dict(entry_cache["epochs"]),
            "evidence_ids": [],
            "execution_plan": {"status": "wait", "reason": "off_session"},
            "entry_validation_failures": ["entry:off_session"],
        }
        raw_response = json.dumps(review, separators=(",", ":"))
    else:
        core_skill = (STORE_ROOT / "core_skill.md").read_text(
            encoding="utf-8"
        )
        contract = load_prompt_section("qwen_cached_entry", STORE_ROOT)
        prompt = (
            core_skill
            + "\n\n"
            + contract
            + "\n\nENTRY FACTS:\n"
            + json.dumps(
                {
                    "symbol": symbol,
                    "price": entry_cache["minute"]["quote"],
                    "validated_at_utc": entry_cache["validated_at_utc"],
                    "decision_time_utc": entry_cache["decision_time_utc"],
                    "epochs": entry_cache["epochs"],
                    "structure": entry_cache["structure"],
                    "session": entry_cache["session"],
                    "playbooks": entry_cache["playbooks"],
                    "minute": entry_cache["minute"],
                    "recent_closed": entry_cache["recent_closed"],
                    "levels_by_timeframe": decision_levels,
                    "allowed_evidence_ids": entry_cache["known_evidence_ids"],
                    "planner_context": planner_context,
                },
                separators=(",", ":"),
            )
        )
        prompt_text = prompt
        decision_started = time.monotonic()
        result = ollama_generate(
            prompt,
            timeout=None,
            num_predict=512,
            num_ctx=8192,
            format_schema=entry_decision_schema(entry_cache, decision_levels),
        )
        decision_wall_seconds = round(time.monotonic() - decision_started, 3)
        decision_duration_ns = result.get("total_duration")
        logging.info(
            "Qwen entry decision took %.2fs (model total_duration=%sns)",
            decision_wall_seconds,
            decision_duration_ns,
        )
        raw_response = result.get("response", "{}")
        review = json.loads(raw_response)
        provenance_failures = validate_entry_provenance(review, entry_cache)
        snapshot["qwen_evidence_ids"] = list(review.get("evidence_ids") or [])
        if provenance_failures:
            review["execution_plan"] = {
                "status": "wait",
                "reason": "Cache provenance validation failed.",
            }
        else:
            review["execution_plan"] = normalize_execution_plan(
                review.get("execution_plan"),
                snapshot,
                entry_cache,
                bias=review.get("bias"),
                confidence=review.get("confidence"),
            )
            plan_failures = validate_entry_against_plan(
                review["execution_plan"], planner_context
            )
            if plan_failures and review["execution_plan"].get("status") == "ready":
                review["execution_plan"] = {
                    "status": "wait",
                    "reason": "Session plan gating rejected entry geometry.",
                }
                provenance_failures.extend(plan_failures)
        review["entry_validation_failures"] = provenance_failures
    append_qwen_decision(
        decision_type="entry",
        symbol=symbol,
        price=snapshot.get("price"),
        prompt_text=prompt_text,
        raw_response=raw_response,
        parsed=review,
        model=snapshot.get("model") or "qwen-trading-v002:latest",
        duration_ns=decision_duration_ns,
        context={
            "cache_status": entry_cache.get("status"),
            "session": entry_cache.get("session"),
            "execution_plan": review.get("execution_plan"),
        },
    )
    if (
        review["execution_plan"].get("status") == "ready"
        and review.get("invalidation") is None
    ):
        review["invalidation"] = {
            "level_id": review["execution_plan"]["stop_level_id"],
            "price": review["execution_plan"]["stop_loss"],
        }
    proposal = append_paper_proposal(
        snapshot,
        review,
        raw_response,
        decision_wall_seconds,
        decision_duration_ns,
        prompt_text,
        planner_context,
    )
    entry_state = read_json_safe(
        ENTRY_STATE_FILE, {"qwen": dict(DEFAULT_ENTRY_QWEN_STATE)}
    )
    entry_state["qwen"] = {
        "bias": review.get("bias", "Conditional"),
        "confidence": normalize_confidence(review.get("confidence"), 0),
        "summary": normalize_text(
            review.get("summary"), "No summary returned."
        ),
        "invalidation": normalize_invalidation(
            review.get("invalidation"), review["execution_plan"]
        ),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "proposal_id": proposal["proposal_id"],
        "proposal_price": snapshot.get("price"),
        "execution_plan": review["execution_plan"],
    }
    write_json_atomic(ENTRY_STATE_FILE, entry_state)
    return build_snapshot()


class DashboardHandler(BaseHTTPRequestHandler):
    def _headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin", "")
        allowed_origins = {
            "http://localhost",
            "http://127.0.0.1",
            "http://localhost:3000",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:8088",
            "http://127.0.0.1:8088",
        }
        if origin in allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/snapshot":
            snapshot = build_snapshot()
            snapshot["paper_execution"] = latest_paper_execution()
            payload = json.dumps(snapshot).encode("utf-8")
            self._headers()
            self.wfile.write(payload)
            return
        if path == "/plan":
            payload = json.dumps(build_plan_snapshot()).encode("utf-8")
            self._headers()
            self.wfile.write(payload)
            return
        if path == "/candles":
            query = parse_qs(parsed.query)
            timeframe = str(query.get("tf", ["M15"])[0]).upper()
            count = int(query.get("count", ["200"])[0])
            try:
                candles = read_chart_candles(timeframe=timeframe, count=count)
                payload = json.dumps(
                    {"timeframe": timeframe, "count": len(candles), "candles": candles}
                ).encode("utf-8")
                self._headers()
                self.wfile.write(payload)
            except ValueError as error:
                self._headers(400)
                self.wfile.write(json.dumps({"error": str(error)}).encode("utf-8"))
            return
        if path == "/plan/history":
            query = parse_qs(parsed.query)
            day_text = query.get("date", [date.today().isoformat()])[0]
            try:
                trading_date = date.fromisoformat(day_text)
            except ValueError:
                self._headers(400)
                self.wfile.write(json.dumps({"error": "invalid date"}).encode("utf-8"))
                return
            payload = json.dumps(load_plan_history(trading_date)).encode("utf-8")
            self._headers()
            self.wfile.write(payload)
            return
        self._headers(404)
        self.wfile.write(b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/review-tickets":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length).decode("utf-8"))
                ticket = int(request["ticket"])
                tickets = load_review_tickets()
                if request.get("action") == "remove":
                    tickets.discard(ticket)
                else:
                    tickets.add(ticket)
                save_review_tickets(tickets)
                snapshot = build_snapshot()
                for position in snapshot.get("positions", []):
                    position["under_review"] = position.get("ticket") in tickets
                payload = json.dumps(snapshot).encode("utf-8")
                self._headers()
                self.wfile.write(payload)
            except Exception as error:
                self._headers(400)
                self.wfile.write(json.dumps({"error": str(error)}).encode("utf-8"))
            return
        if self.path != "/deal-sheet":
            self._headers(404)
            self.wfile.write(b'{"error":"not found"}')
            return
        if not QWEN_DECISION_LOCK.acquire(blocking=False):
            payload = json.dumps(
                {
                    **build_snapshot(),
                    "decision_in_progress": True,
                }
            ).encode("utf-8")
            self._headers(202)
            self.wfile.write(payload)
            return
        try:
            payload = json.dumps(generate_dashboard_deal_sheet()).encode("utf-8")
            self._headers()
            self.wfile.write(payload)
        except Exception as error:
            logging.exception("Dashboard deal-sheet generation failed")
            self._headers(503)
            self.wfile.write(json.dumps({"error": str(error)}).encode("utf-8"))
        finally:
            QWEN_DECISION_LOCK.release()

    def log_message(self, format, *args):
        return


def start_dashboard_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 48632), DashboardHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info("Dashboard API listening on http://127.0.0.1:48632")


def generate_automatic_deal_sheet() -> None:
    """Generate the next proposal without depending on an open web browser."""
    management_state = read_json_safe(MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE)
    broker_positions_today = int(management_state.get("today", {}).get("baskets", 0))
    qwen_position_open = any(
        position.get("qwen_owned") for position in management_state.get("positions", [])
    )
    if broker_positions_today >= DAILY_PAPER_CAP:
        logging.info(
            "MT5 broker filled-position cap reached: %d/%d",
            broker_positions_today,
            DAILY_PAPER_CAP,
        )
        return
    if qwen_position_open:
        return
    if not QWEN_DECISION_LOCK.acquire(blocking=False):
        return
    try:
        generate_dashboard_deal_sheet()
    except Exception:
        logging.exception("Automatic deal-sheet generation failed")
    finally:
        QWEN_DECISION_LOCK.release()


def main() -> None:
    # A localhost listener prevents duplicate entry-decision instances.
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", 48631))
        singleton.listen(1)
    except OSError:
        return

    logging.info("Qwen entry-decision process starting; interval=%ds", INTERVAL_SECONDS)
    start_dashboard_server()
    while True:
        started = time.monotonic()
        try:
            warm_model()
            generate_automatic_deal_sheet()
        except Exception:
            logging.exception("Entry-decision cycle failed")
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
