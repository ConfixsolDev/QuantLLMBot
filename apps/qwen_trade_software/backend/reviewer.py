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

import entry_policy
from decision_liveness import (
    DecisionEvent,
    DecisionLivenessMonitor,
    format_alarm,
)
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
    MODEL,
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
    gold_market_open,
    sync_model_residency,
    unload_stale_models,
    write_json_atomic,
)
from session_planner import (
    build_branch_view,
    DEFAULT_PLANNER_STATE,
    live_mid_from_facts,
    live_sanity_snapshot,
    load_plan_history,
    planner_facts,
    read_chart_candles,
)
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
# Rolling health view of the decision stream. Holds the invariants that were
# missing on 2026-08-10, when the system produced no ready proposal for 2h20m
# with the market open, the cache ready and Qwen answering normally -- and
# nothing alarmed.
LIVENESS = DecisionLivenessMonitor()
# Set QWEN_POLICY_V2=1 to route entry decisions through entry_policy.py, where
# the model returns dual-side observations and the code owns the verdict.
# Defaults off so this branch is a no-op for the running stack until enabled.
QWEN_POLICY_V2 = os.environ.get("QWEN_POLICY_V2", "0") == "1"
# Broker entry bracket is fixed; structure S/R is for the model zone + management.
FIXED_STOP_DISTANCE = 3.0
FIXED_TARGET_DISTANCE = 5.0
MIN_STOP_DISTANCE = FIXED_STOP_DISTANCE
MIN_TARGET_DISTANCE = FIXED_TARGET_DISTANCE
MAX_STRUCTURE_DISTANCE = 40.0
STRUCTURE_TIMEFRAMES = ("H4", "H1", "M15", "M30", "D1")


def latest_paper_execution():
    for path in _dated_log_files("paper-executions"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def wait_decision_signature(review: dict, entry_cache: dict) -> str:
    """Stable identity for a non-model wait so identical blocks are not re-logged."""
    plan = review.get("execution_plan") if isinstance(review.get("execution_plan"), dict) else {}
    if plan.get("status") != "wait":
        return ""
    session = entry_cache.get("session") if isinstance(entry_cache.get("session"), dict) else {}
    return json.dumps(
        {
            "reason": plan.get("reason"),
            "failures": sorted(review.get("entry_validation_failures") or []),
            "cache_status": entry_cache.get("status"),
            "cache_reason": entry_cache.get("reason"),
            "session": session.get("session"),
            "trade_permitted": session.get("trade_permitted"),
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def latest_wait_decision_signature() -> str | None:
    """Return wait signature of the newest paper proposal, if it was a wait."""
    for path in _dated_log_files("paper-proposals"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                proposal = json.loads(line)
            except json.JSONDecodeError:
                continue
            qwen = proposal.get("qwen") if isinstance(proposal.get("qwen"), dict) else {}
            plan = (
                qwen.get("execution_plan")
                if isinstance(qwen.get("execution_plan"), dict)
                else {}
            )
            if plan.get("status") != "wait":
                return None
            cache = (
                proposal.get("market", {}).get("cache_context")
                if isinstance(proposal.get("market"), dict)
                else {}
            )
            review = {
                "execution_plan": plan,
                "entry_validation_failures": (
                    qwen.get("entry_validation_failures")
                    or (cache or {}).get("failures")
                    or []
                ),
            }
            return wait_decision_signature(review, cache or {})
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
            "entry_validation_failures": review.get(
                "entry_validation_failures", []
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


def _slim_candle(row: dict) -> dict:
    return {
        "id": row.get("evidence_id"),
        "o": row.get("open"),
        "h": row.get("high"),
        "l": row.get("low"),
        "c": row.get("close"),
        "v": row.get("tick_volume"),
    }


def _execution_level_ladder(
    decision_levels: dict, mid_price: float, each_side: int = 6
) -> list[dict]:
    """Nearest named levels above and below price for geometry only."""
    rows = [
        {
            "id": str(row["id"]),
            "tf": timeframe,
            "lo": float(row["price"]),
            "hi": float(row["zone_high"]),
            "role": row.get("role"),
        }
        for timeframe, level_rows in decision_levels.items()
        for row in level_rows
    ]
    rows.sort(key=lambda item: item["lo"])
    below = [row for row in rows if row["hi"] <= mid_price][-each_side:]
    above = [row for row in rows if row["lo"] > mid_price][:each_side]
    return below + above


def compact_entry_facts(
    entry_cache: dict,
    decision_levels: dict,
    planner_context: dict,
    symbol: str,
) -> dict:
    """Compress validated cache into trade-quality facts only.

    Research-aligned assembly: static contract stays short; runtime injects
    only decision-relevant cache fields (location, response, participation,
    geometry, session, thin planner). Drops full core_skill and duplicated
    minute/structure/level dumps that previously bloated entry to ~14KB+.
    """
    minute = entry_cache.get("minute") or {}
    quote = minute.get("quote") or {}
    mid = float(quote.get("bid") or quote.get("ask") or 0.0)
    structure = entry_cache.get("structure") or {}
    location = {}
    for timeframe, value in (structure.get("timeframe_location") or {}).items():
        if not isinstance(value, dict):
            continue
        latest = value.get("latest_completed") or {}
        location[timeframe] = {
            "location": value.get("location"),
            "auction": value.get("auction_state"),
            "close": latest.get("close"),
            "evidence_ids": value.get("evidence_ids") or [],
        }

    def zone_ref(zone: dict | None) -> dict | None:
        if not isinstance(zone, dict):
            return None
        return {
            "id": zone.get("level_id"),
            "lo": zone.get("zone_low"),
            "hi": zone.get("zone_high"),
            "role": zone.get("role"),
        }

    playbooks = []
    for row in (entry_cache.get("playbooks") or [])[:3]:
        playbooks.append(
            {
                "id": row.get("playbook_id"),
                "level_id": row.get("level_id"),
                "buy": row.get("buy_condition"),
                "sell": row.get("sell_condition"),
                "missing": row.get("missing_evidence"),
                "evidence_ids": row.get("evidence_ids") or [],
            }
        )

    recent = {}
    for timeframe, keep in (("M1", 3), ("M5", 3), ("M15", 2), ("M30", 2)):
        rows = (entry_cache.get("recent_closed") or {}).get(timeframe) or []
        recent[timeframe] = [_slim_candle(row) for row in rows[-keep:]]

    forming = minute.get("forming") or {}
    forming_slim = {
        timeframe: {
            "id": row.get("id"),
            "o": row.get("open"),
            "h": row.get("high"),
            "l": row.get("low"),
            "cur": row.get("current"),
        }
        for timeframe, row in forming.items()
        if timeframe in ("M1", "M5") and isinstance(row, dict)
    }

    closed_m1 = minute.get("closed_m1") or {}
    execution_levels = _execution_level_ladder(decision_levels, mid)
    session = entry_cache.get("session") or {}
    session_plan = (planner_context or {}).get("session_plan_summary") or {}
    planner = {
        "status": (planner_context or {}).get("planner_status"),
        "day_plan_id": (planner_context or {}).get("day_plan_id"),
        "session_plan_id": (planner_context or {}).get("session_plan_id"),
        "tradeable": bool(session_plan.get("tradeable")),
        "active_scenario": session_plan.get("active_scenario"),
        "confidence": session_plan.get("confidence"),
        "entry_zones": session_plan.get("entry_zones") or [],
    }

    known = set(entry_cache.get("known_evidence_ids") or [])
    citeable: list[str] = []
    seen: set[str] = set()

    def _add_cite(value: str | None) -> None:
        if not value or value in seen or value not in known:
            return
        seen.add(value)
        citeable.append(value)

    for value in location.values():
        for evidence_id in value.get("evidence_ids") or []:
            _add_cite(evidence_id)
    for playbook in playbooks:
        _add_cite(playbook.get("level_id"))
        for evidence_id in playbook.get("evidence_ids") or []:
            _add_cite(evidence_id)
    _add_cite(closed_m1.get("id"))
    for rows in recent.values():
        for row in rows:
            _add_cite(row.get("id"))
    for row in execution_levels:
        _add_cite(row.get("id"))
    for row in minute.get("nearby_levels") or []:
        _add_cite(row.get("id"))

    return {
        "symbol": symbol,
        "quote": {
            "bid": quote.get("bid"),
            "ask": quote.get("ask"),
            "spread": quote.get("spread"),
            "age_ms": quote.get("age_ms"),
        },
        "validated_at_utc": entry_cache.get("validated_at_utc"),
        "decision_time_utc": entry_cache.get("decision_time_utc"),
        "epochs": entry_cache.get("epochs"),
        "session": {
            "session": session.get("session"),
            "trade_permitted": session.get("trade_permitted"),
            "asia_high": session.get("asia_high"),
            "asia_low": session.get("asia_low"),
            "asia_relation": session.get("asia_relation"),
        },
        "location": location,
        "h4_state": structure.get("current_h4_state"),
        "nearest_lower_zone": zone_ref(structure.get("nearest_lower_zone")),
        "nearest_upper_zone": zone_ref(structure.get("nearest_upper_zone")),
        "playbooks": playbooks,
        "closed_m1": {
            "id": closed_m1.get("id"),
            "o": closed_m1.get("open"),
            "h": closed_m1.get("high"),
            "l": closed_m1.get("low"),
            "c": closed_m1.get("close"),
            "v": closed_m1.get("tick_volume"),
        },
        "forming": forming_slim,
        "volume": minute.get("volume") or {},
        "nearby_levels": minute.get("nearby_levels") or [],
        "recent_closed": recent,
        "execution_levels": execution_levels,
        "planner": planner,
        "citeable_evidence_ids": citeable,
    }


def entry_contract_version() -> str:
    """Version stamp of the live entry contract, e.g. "1.10".

    Recorded on every decision so a distribution shift can be attributed to the
    exact contract that caused it. On 2026-08-10 the v1.8 -> v1.9 edit halted
    trading for 2h20m and nothing tied the two facts together.
    """
    try:
        contract = load_prompt_section(
            "qwen_cached_entry", STORE_ROOT, keep_comments=True
        )
    except Exception:
        return "unknown"
    for line in contract.splitlines():
        marker = "<!-- version:"
        if line.strip().startswith(marker):
            return line.split(marker, 1)[1].split("|", 1)[0].strip()
    return "unversioned"


def build_entry_prompt(facts: dict) -> str:
    """Compact entry prompt: short trade-quality contract + compressed facts."""
    contract = load_prompt_section("qwen_cached_entry", STORE_ROOT)
    return contract + "\n\nENTRY FACTS:\n" + json.dumps(facts, separators=(",", ":"))


def entry_decision_schema(entry_cache: dict, decision_levels: dict, facts: dict | None = None) -> dict:
    if facts and facts.get("execution_levels"):
        level_ids = sorted({row["id"] for row in facts["execution_levels"]})
    else:
        level_ids = sorted(
            row["id"] for rows in decision_levels.values() for row in rows
        )
    if not level_ids:
        level_ids = ["__no_level__"]
    evidence_enum = list(facts.get("citeable_evidence_ids") or []) if facts else []
    if not evidence_enum:
        evidence_enum = list(entry_cache.get("known_evidence_ids") or [])
    if not evidence_enum:
        evidence_enum = ["__no_evidence__"]
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
                    "enum": evidence_enum,
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


def dual_side_observation_schema(
    entry_cache: dict, decision_levels: dict, facts: dict | None = None
) -> dict:
    """Schema for prompt:qwen_dual_side_entry (contract v2.0).

    The model returns observations only -- no status, no overall confidence, no
    side selection. Both ``long`` and ``short`` are ``required``, which is what
    makes the 2026-08-10 one-sided drift (44 sell / 1 buy) a schema violation
    rather than a silent omission. Confidence is composed in entry_policy.py
    from the component scores below, so a "confidence 0 alongside a bullish
    read" contradiction cannot be expressed at all.

    Note there is deliberately no ``conditional`` value anywhere: on 2026-08-10
    the model returned ``bias: "conditional"`` in 71% of decisions despite the
    contract forbidding it in prose. Prose does not constrain output; enums do.
    """
    if facts and facts.get("execution_levels"):
        level_ids = sorted({row["id"] for row in facts["execution_levels"]})
    else:
        level_ids = sorted(
            row["id"] for rows in decision_levels.values() for row in rows
        )
    if not level_ids:
        level_ids = ["__no_level__"]
    evidence_enum = list(facts.get("citeable_evidence_ids") or []) if facts else []
    if not evidence_enum:
        evidence_enum = list(entry_cache.get("known_evidence_ids") or [])
    if not evidence_enum:
        evidence_enum = ["__no_evidence__"]
    epochs = entry_cache["epochs"]

    score_block = {
        "type": "object",
        "properties": {
            component: {"type": "integer", "minimum": 0, "maximum": 10}
            for component in entry_policy.SCORE_COMPONENTS
        },
        "required": list(entry_policy.SCORE_COMPONENTS),
        "additionalProperties": False,
    }
    side_block = {
        "type": "object",
        "properties": {
            "zone_id": {"type": "string", "enum": level_ids},
            "invalidation_id": {"type": "string", "enum": level_ids},
            "trigger_tf": {
                "type": "string",
                "enum": list(entry_policy.TIMEFRAME_ORDER),
            },
            "response_observed": {"type": "boolean"},
            "traps_triggered": {
                "type": "array",
                "items": {"type": "string", "enum": sorted(entry_policy.KNOWN_TRAPS)},
                "maxItems": len(entry_policy.KNOWN_TRAPS),
            },
            "scores": score_block,
        },
        "required": [
            "zone_id", "invalidation_id", "trigger_tf",
            "response_observed", "traps_triggered", "scores",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "read": {
                "type": "object",
                "properties": {
                    "htf_auction": {"type": "string", "maxLength": 40},
                    "htf_timeframe": {
                        "type": "string",
                        "enum": list(entry_policy.TIMEFRAME_ORDER),
                    },
                    "location": {"type": "string", "maxLength": 60},
                    "acceptance": {"type": "string", "maxLength": 40},
                },
                "required": ["htf_auction", "htf_timeframe", "location", "acceptance"],
                "additionalProperties": False,
            },
            "long": side_block,
            "short": side_block,
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
                "items": {"type": "string", "enum": evidence_enum},
                "minItems": 1,
                "maxItems": 6,
            },
        },
        # Both sides required: the model cannot omit the direction it dislikes.
        "required": ["read", "long", "short", "acknowledged_epochs", "evidence_ids"],
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
    structure_tf = infer_structure_timeframe(
        entry_low_id, entry_high_id, "", ""
    )
    stop_pick, target_pick = pick_structure_stop_target(
        side,
        entry_low,
        entry_high,
        decision_levels,
        structure_tf,
        None,
        None,
        {},
    )
    if stop_pick is None or target_pick is None:
        return None
    return {
        "entry_low_id": entry_low_id,
        "entry_high_id": entry_high_id,
        "stop_level_id": stop_pick[0],
        "target_level_id": target_pick[0],
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop_loss": stop_pick[1],
        "take_profit": target_pick[1],
        "structure_timeframe": structure_tf,
    }


def _level_timeframe(level_id: str) -> str | None:
    text = str(level_id or "")
    for timeframe in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        if text.startswith(f"{timeframe}_") or text.startswith(f"{timeframe}-"):
            return timeframe
    return None


def infer_structure_timeframe(
    entry_low_id: str,
    entry_high_id: str,
    stop_level_id: str,
    target_level_id: str,
) -> str:
    """Choose SL/TP ladder from the trade's structure TF (H4 → H1 → M15)."""
    votes: list[str] = []
    for level_id in (stop_level_id, target_level_id, entry_low_id, entry_high_id):
        timeframe = _level_timeframe(level_id)
        if timeframe in STRUCTURE_TIMEFRAMES:
            votes.append(timeframe)
    for timeframe in ("H4", "H1", "M15", "M30", "D1"):
        if timeframe in votes:
            return timeframe
    return "H1"


def _collect_structure_levels(
    decision_levels: dict, structure_tf: str
) -> list[tuple[str, float, str]]:
    """Levels for the structure TF, then wider parents if the ladder is thin."""
    order = list(STRUCTURE_TIMEFRAMES)
    try:
        start = order.index(structure_tf)
    except ValueError:
        start = order.index("H1")
    # Prefer own TF first, then higher parents (H1→H4→D1), then lower M15/M30.
    preferred = order[start:] + list(reversed(order[:start]))
    collected: list[tuple[str, float, str]] = []
    seen: set[str] = set()
    for timeframe in preferred:
        for row in decision_levels.get(timeframe, []) or []:
            level_id = str(row.get("id") or "")
            if not level_id or level_id in seen:
                continue
            try:
                price = float(row["price"])
            except (KeyError, TypeError, ValueError):
                continue
            seen.add(level_id)
            collected.append((level_id, price, timeframe))
    return collected


def pick_structure_stop_target(
    side: str,
    entry_low: float,
    entry_high: float,
    decision_levels: dict,
    structure_tf: str,
    qwen_stop_id: str | None,
    qwen_target_id: str | None,
    level_map: dict,
) -> tuple[tuple[str, float] | None, tuple[str, float] | None]:
    """Next support/resistance beyond the entry zone with Gold-scale room."""
    levels = _collect_structure_levels(decision_levels, structure_tf)
    below = sorted(
        ((level_id, price) for level_id, price, _ in levels if price < entry_low - 1e-9),
        key=lambda item: item[1],
        reverse=True,
    )
    above = sorted(
        ((level_id, price) for level_id, price, _ in levels if price > entry_high + 1e-9),
        key=lambda item: item[1],
    )

    def accept_stop(level_id: str | None, price: float | None) -> tuple[str, float] | None:
        if not level_id or price is None:
            return None
        if side == "buy":
            distance = entry_low - price
            if distance < MIN_STOP_DISTANCE or distance > MAX_STRUCTURE_DISTANCE:
                return None
        else:
            distance = price - entry_high
            if distance < MIN_STOP_DISTANCE or distance > MAX_STRUCTURE_DISTANCE:
                return None
        return level_id, float(price)

    def accept_target(level_id: str | None, price: float | None) -> tuple[str, float] | None:
        if not level_id or price is None:
            return None
        if side == "buy":
            distance = price - entry_high
            if distance < MIN_TARGET_DISTANCE or distance > MAX_STRUCTURE_DISTANCE:
                return None
        else:
            distance = entry_low - price
            if distance < MIN_TARGET_DISTANCE or distance > MAX_STRUCTURE_DISTANCE:
                return None
        return level_id, float(price)

    stop_pick = accept_stop(
        qwen_stop_id, level_map.get(qwen_stop_id) if qwen_stop_id else None
    )
    target_pick = accept_target(
        qwen_target_id, level_map.get(qwen_target_id) if qwen_target_id else None
    )

    if stop_pick is None:
        candidates = below if side == "buy" else above
        for level_id, price in candidates:
            stop_pick = accept_stop(level_id, price)
            if stop_pick is not None:
                break

    if target_pick is None:
        candidates = above if side == "buy" else below
        # Prefer the nearest level that clears MIN_TARGET_DISTANCE (often $5–$20).
        for level_id, price in candidates:
            target_pick = accept_target(level_id, price)
            if target_pick is not None:
                break

    # Last resort: nearest level on the correct side (even beyond MAX), padded
    # to Gold-scale mins — keeps a clear Qwen ready from becoming wait.
    if stop_pick is None:
        candidates = below if side == "buy" else above
        if candidates:
            level_id, price = candidates[0]
            if side == "buy":
                price = min(price, entry_low - MIN_STOP_DISTANCE)
            else:
                price = max(price, entry_high + MIN_STOP_DISTANCE)
            stop_pick = (level_id, float(price))
        else:
            synth = (
                entry_low - MIN_STOP_DISTANCE
                if side == "buy"
                else entry_high + MIN_STOP_DISTANCE
            )
            stop_pick = (f"SYNTH_STOP_{structure_tf}", round(synth, 3))

    if target_pick is None:
        candidates = above if side == "buy" else below
        if candidates:
            # Prefer farthest-within-MAX, else nearest padded to min room.
            usable = []
            for level_id, price in candidates:
                distance = (
                    price - entry_high if side == "buy" else entry_low - price
                )
                if distance <= MAX_STRUCTURE_DISTANCE:
                    usable.append((level_id, price, distance))
            if usable:
                # Nearest that already has min room, else nearest padded.
                with_room = [row for row in usable if row[2] >= MIN_TARGET_DISTANCE]
                if with_room:
                    level_id, price, _ = with_room[0]
                    target_pick = (level_id, float(price))
                else:
                    level_id, price, _ = usable[0]
                    if side == "buy":
                        price = max(price, entry_high + MIN_TARGET_DISTANCE)
                    else:
                        price = min(price, entry_low - MIN_TARGET_DISTANCE)
                    target_pick = (level_id, float(price))
            else:
                level_id, price = candidates[0]
                if side == "buy":
                    price = max(price, entry_high + MIN_TARGET_DISTANCE)
                else:
                    price = min(price, entry_low - MIN_TARGET_DISTANCE)
                target_pick = (level_id, float(price))
        else:
            synth = (
                entry_high + MIN_TARGET_DISTANCE
                if side == "buy"
                else entry_low - MIN_TARGET_DISTANCE
            )
            target_pick = (f"SYNTH_TARGET_{structure_tf}", round(synth, 3))

    return stop_pick, target_pick


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


def _ollama_runtime_status(model: str = MODEL) -> dict:
    """Return residency + GPU/CPU placement from Ollama /api/ps."""
    import urllib.request

    status = {
        "model": model,
        "model_installed": False,
        "model_resident": False,
        "model_device": "unloaded",
        "size_vram": 0,
        "size": 0,
    }
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=3) as response:
            tags = json.loads(response.read().decode("utf-8")).get("models", [])
        status["model_installed"] = any(
            row.get("name") == model or str(row.get("name") or "").startswith(model.split(":")[0])
            for row in tags
        )
    except Exception:
        logging.debug("Ollama tags lookup failed", exc_info=True)
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as response:
            running = json.loads(response.read().decode("utf-8")).get("models", [])
        resident = next(
            (
                row
                for row in running
                if row.get("name") == model
                or str(row.get("name") or "").startswith(model.split(":")[0])
            ),
            None,
        )
        if resident:
            size = int(resident.get("size") or 0)
            vram = int(resident.get("size_vram") or 0)
            status["model_resident"] = True
            status["size"] = size
            status["size_vram"] = vram
            if vram <= 0:
                status["model_device"] = "CPU"
            elif size > 0 and vram >= size * 0.9:
                status["model_device"] = "GPU"
            else:
                status["model_device"] = "MIXED"
    except Exception:
        logging.debug("Ollama ps lookup failed", exc_info=True)
    return status


def build_plan_snapshot() -> dict:
    planner = read_json_safe(PLANNER_STATE_FILE, DEFAULT_PLANNER_STATE)
    planner["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    planner["planner_alive"] = _planner_process_alive()
    try:
        facts = planner_facts(str(planner.get("symbol") or "XAUUSDr"))
        live_price = live_mid_from_facts(facts)
    except Exception:
        logging.exception("Plan snapshot live price lookup failed")
        live_price = None
    planner["live_price"] = live_price
    # Re-evaluate the two day-plan branches against the LIVE price rather than
    # serving whatever was current when the planner last saved. The screen's
    # headline ("BUY confirmed" / "no entry yet") is only useful if it reflects
    # where price is now.
    try:
        if live_price:
            planner.setdefault("live", {})["mid"] = live_price
        planner["day_branches"] = build_branch_view(planner)
    except Exception:
        logging.exception("plan:branch_view_failed")
    planner["day_plan_live_sanity"] = live_sanity_snapshot(
        planner.get("day_plan"), live_price
    )
    planner["session_plan_live_sanity"] = live_sanity_snapshot(
        planner.get("session_plan"), live_price
    )
    management = read_json_safe(MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE)
    runtime = _ollama_runtime_status(str(management.get("model") or MODEL))
    planner["model"] = runtime["model"]
    planner["model_installed"] = runtime["model_installed"]
    planner["model_resident"] = runtime["model_resident"]
    planner["model_device"] = runtime["model_device"]
    planner["model_size_vram"] = runtime["size_vram"]
    planner["mt5_connected"] = bool(management.get("connected"))
    planner["runtime_status"] = {
        "model": runtime["model"],
        "model_installed": runtime["model_installed"],
        "model_resident": runtime["model_resident"],
        "model_device": runtime["model_device"],
        "mt5_connected": bool(management.get("connected")),
        "planner_alive": planner["planner_alive"],
    }
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
    """Ready gate = confidence + named S/R entry zone; broker SL/TP = $3/$5.

    Qwen names support/resistance zones and side. Runtime places a fixed $3
    stop and $5 target from the zone. Next structure S/R prices are kept only
    as management references for trade_management to improve after fill.
    """
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
    declared_side = str(value.get("side") or "").strip().lower()
    # Ready plan side is authoritative if bias was left conditional.
    if normalized_bias not in ("buy", "sell"):
        if declared_side in ("buy", "sell"):
            normalized_bias = declared_side
        else:
            return wait("Qwen must provide a clear buy or sell bias.")
    if declared_side and declared_side != normalized_bias:
        return wait("Qwen plan side contradicts its declared bias.")
    side = declared_side or normalized_bias
    decision_levels = snapshot.get("decision_levels", {})
    level_map = {
        str(level["id"]): float(level["price"])
        for levels in decision_levels.values()
        for level in levels
    }
    quote = float(
        entry_cache.get("minute", {}).get("quote", {}).get(
            "ask" if side == "buy" else "bid",
            snapshot.get("price", 0.0),
        )
        or 0.0
    )

    entry_low_id = str(value.get("entry_low_id") or value.get("entry_id") or "")
    entry_high_id = str(value.get("entry_high_id") or entry_low_id or "")
    qwen_stop_id = str(value.get("stop_level_id") or "")
    qwen_target_id = str(value.get("target_level_id") or "")
    geometry_source = "qwen_sr_zone_fixed_3_5"

    if entry_low_id in level_map and entry_high_id in level_map:
        entry_points = sorted(
            (
                (entry_low_id, level_map[entry_low_id]),
                (entry_high_id, level_map[entry_high_id]),
            ),
            key=lambda item: item[1],
        )
        entry_low_id, entry_low = entry_points[0]
        entry_high_id, entry_high = entry_points[1]
        if entry_low_id == entry_high_id or abs(entry_low - entry_high) < 1e-9:
            band = 0.4
            entry_low = round(entry_low - band, 3)
            entry_high = round(entry_high + band, 3)
    else:
        fallback = cache_fallback_geometry(side, decision_levels, quote)
        if fallback is None:
            return wait("Validated cache cannot map a Qwen entry zone.")
        geometry_source = "cache_sr_zone_fixed_3_5"
        entry_low_id = fallback["entry_low_id"]
        entry_high_id = fallback["entry_high_id"]
        entry_low = fallback["entry_low"]
        entry_high = fallback["entry_high"]
        if not qwen_stop_id:
            qwen_stop_id = fallback["stop_level_id"]
        if not qwen_target_id:
            qwen_target_id = fallback["target_level_id"]

    structure_tf = infer_structure_timeframe(
        entry_low_id, entry_high_id, qwen_stop_id, qwen_target_id
    )
    # Management references only — never used to reject or replace the entry.
    stop_pick, target_pick = pick_structure_stop_target(
        side,
        entry_low,
        entry_high,
        decision_levels,
        structure_tf,
        qwen_stop_id or None,
        qwen_target_id or None,
        level_map,
    )
    if stop_pick is None:
        stop_pick = (
            qwen_stop_id or f"MGMT_STOP_{structure_tf}",
            round(
                entry_low - FIXED_STOP_DISTANCE
                if side == "buy"
                else entry_high + FIXED_STOP_DISTANCE,
                3,
            ),
        )
    if target_pick is None:
        target_pick = (
            qwen_target_id or f"MGMT_TARGET_{structure_tf}",
            round(
                entry_high + FIXED_TARGET_DISTANCE
                if side == "buy"
                else entry_low - FIXED_TARGET_DISTANCE,
                3,
            ),
        )
    stop_level_id, structural_stop = stop_pick
    target_level_id, structural_target = target_pick

    if side == "buy":
        stop_loss = round(entry_low - FIXED_STOP_DISTANCE, 3)
        take_profit = round(entry_high + FIXED_TARGET_DISTANCE, 3)
    else:
        stop_loss = round(entry_high + FIXED_STOP_DISTANCE, 3)
        take_profit = round(entry_low - FIXED_TARGET_DISTANCE, 3)

    # Sibling traps to the 2026-08-10 sell-into-buy failure (see sop
    # qwen_cached_entry hard traps). Runtime enforces the ones that are
    # unambiguous from quote + named levels.
    acceptance_pad = 1.0
    if quote > 0:
        if side == "sell" and quote > entry_high + acceptance_pad:
            return wait(
                "Live price already accepted above the sell resistance zone; "
                "do not fade the bullish auction."
            )
        if side == "buy" and quote < entry_low - acceptance_pad:
            return wait(
                "Live price already accepted below the buy support zone; "
                "do not fade the bearish auction."
            )

    # Buy zone entirely above live price = buying into resistance.
    # Sell zone entirely below live price = selling into support.
    if quote > 0:
        if side == "buy" and entry_low > quote + 0.5:
            return wait(
                "Do not buy into resistance above live price; "
                "wait for pullback support or break-and-retest."
            )
        if side == "sell" and entry_high < quote - 0.5:
            return wait(
                "Do not sell into support below live price; "
                "wait for bounce to resistance or failed support hold."
            )

    planner_scenario = str(
        snapshot.get("planner_context", {}).get("session_plan_summary", {}).get(
            "active_scenario", ""
        )
        or ""
    ).strip().lower()
    if planner_scenario == "bullish" and side == "sell" and quote > entry_high:
        return wait(
            "Planner active_scenario is bullish; do not ready a counter-trend "
            "sell above the mapped resistance."
        )
    if planner_scenario == "bearish" and side == "buy" and quote < entry_low:
        return wait(
            "Planner active_scenario is bearish; do not ready a counter-trend "
            "buy below the mapped support."
        )

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
        "structure_timeframe": structure_tf,
        "stop_distance": FIXED_STOP_DISTANCE,
        "target_distance": FIXED_TARGET_DISTANCE,
        "structural_stop_loss": float(structural_stop),
        "structural_take_profit": float(structural_target),
        "stop_price_distance": FIXED_STOP_DISTANCE,
        "buckets": 1,
        "volume_each": 0.5,
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
    market = gold_market_open()

    if not market.get("open"):
        review = {
            "bias": "conditional",
            "confidence": 0,
            "summary": "Gold market closed; Qwen is unloaded until quotes resume.",
            "acknowledged_epochs": {},
            "evidence_ids": [],
            "execution_plan": {
                "status": "wait",
                "reason": f"market_closed:{market.get('reason')}",
            },
            "entry_validation_failures": [
                f"entry:market_closed:{market.get('reason')}"
            ],
        }
        raw_response = json.dumps(review, separators=(",", ":"))
    elif entry_cache.get("status") != "ready":
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
        facts = compact_entry_facts(
            entry_cache, decision_levels, planner_context, symbol
        )
        prompt = build_entry_prompt(facts)
        prompt_text = prompt
        prompt_bytes = len(prompt.encode("utf-8"))
        decision_started = time.monotonic()
        result = ollama_generate(
            prompt,
            timeout=None,
            # 2026-08-10: was 320, which truncated the response mid-string and
            # surfaced as "dealsheet:generation_failed :: JSONDecodeError:
            # Unterminated string". The failing char offset matched
            # response_chars exactly (529/530/536/537), i.e. generation stopped
            # at the token cap rather than producing bad JSON.
            #
            # The entry schema requires acknowledged_epochs copied verbatim --
            # five ~35-char epoch hashes -- plus up to six evidence_ids and four
            # level IDs. Hash-dense JSON tokenises at ~1.65-1.85 chars/token, so
            # 320 tokens ran out around 530-600 chars. Prose-heavier responses
            # tokenise nearer 2.1 chars/token, which is why some 681-char
            # responses still parsed and the failure looked intermittent.
            #
            # 768 leaves roughly 2x headroom over the largest observed valid
            # response. The context challenge already uses 1024 for the same
            # reason. This is an upper bound, not a target: well-formed answers
            # stop early on their own.
            num_predict=768,
            num_ctx=4096,
            format_schema=entry_decision_schema(
                entry_cache, decision_levels, facts
            ),
        )
        decision_wall_seconds = round(time.monotonic() - decision_started, 3)
        decision_duration_ns = result.get("total_duration")
        logging.info(
            "Qwen entry decision took %.2fs prompt_bytes=%d (model total_duration=%sns)",
            decision_wall_seconds,
            prompt_bytes,
            decision_duration_ns,
        )
        raw_response = result.get("response", "{}")
        review = json.loads(raw_response)
        provenance_failures = validate_entry_provenance(review, entry_cache)
        snapshot["qwen_evidence_ids"] = list(review.get("evidence_ids") or [])

        # 2026-08-10 guard: contract v1.9 made the model emit status="ready"
        # alongside confidence=0 and a directional bias. That contradiction
        # occurred 72 times in two hours and nothing detected it -- the plan was
        # silently downgraded to a wait and trading simply stopped. Surface it
        # loudly with a stable code so a contract regression cannot hide again.
        contradiction = entry_policy.check_legacy_contradiction(review)
        if contradiction:
            logging.error(
                "%s :: model returned status=ready with confidence=%s (bias=%s); "
                "suspect entry-contract regression",
                contradiction,
                review.get("confidence"),
                review.get("bias"),
            )
            provenance_failures.append(contradiction)

        if provenance_failures:
            # Report the actual cause. Folding every failure into a single
            # "Cache provenance validation failed." string is how the v1.9
            # contradiction stayed invisible: the wait reason named the wrong
            # subsystem, so the logs pointed at the cache while the real fault
            # was the entry contract.
            review["execution_plan"] = {
                "status": "wait",
                "reason": (
                    "Model returned ready with sub-threshold confidence "
                    "(suspect entry-contract regression)."
                    if contradiction
                    else "Cache provenance validation failed."
                ),
                "reason_code": (
                    contradiction if contradiction else "entry:provenance_failed"
                ),
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
    if (
        review["execution_plan"].get("status") == "ready"
        and review.get("invalidation") is None
    ):
        plan = review["execution_plan"]
        review["invalidation"] = {
            "level_id": plan["stop_level_id"],
            "price": plan.get("structural_stop_loss", plan["stop_loss"]),
        }

    # Feed the decision stream to the liveness monitor before any dedup, so a
    # regression that produces endless identical waits is still visible.
    try:
        _plan = review.get("execution_plan") or {}
        for _alarm in LIVENESS.record(
            DecisionEvent(
                at=time.time(),
                confidence=int(review.get("confidence") or 0),
                status=str(_plan.get("status") or "wait"),
                side=_plan.get("side"),
                trade_permitted=bool(entry_cache.get("status") == "ready"),
                cache_ready=bool(entry_cache.get("status") == "ready"),
                has_open_position=False,
                latency_seconds=review.get("decision_wall_seconds"),
                contract_version=entry_contract_version(),
            )
        ):
            logging.error(format_alarm(_alarm))
    except Exception:
        logging.exception("liveness:record_failed")

    # No-model wait churn: identical cache/session blocks used to rewrite a
    # fresh proposal every 30s. Keep UI state fresh; only audit when the wait
    # signature changes or Qwen actually ran.
    model_called = prompt_text is not None
    wait_signature = wait_decision_signature(review, entry_cache)
    skip_wait_audit = (
        not model_called
        and bool(wait_signature)
        and wait_signature == latest_wait_decision_signature()
    )
    entry_state = read_json_safe(
        ENTRY_STATE_FILE, {"qwen": dict(DEFAULT_ENTRY_QWEN_STATE)}
    )
    if skip_wait_audit:
        proposal_id = entry_state.get("qwen", {}).get("proposal_id") or "wait-deduped"
        logging.info(
            "Skipped identical wait proposal audit signature=%s",
            wait_signature,
        )
    else:
        append_qwen_decision(
            decision_type="entry",
            symbol=symbol,
            price=snapshot.get("price"),
            prompt_text=prompt_text,
            raw_response=raw_response,
            parsed=review,
            model=snapshot.get("model") or MODEL,
            duration_ns=decision_duration_ns,
            context={
                "cache_status": entry_cache.get("status"),
                "session": entry_cache.get("session"),
                "execution_plan": review.get("execution_plan"),
                "prompt_bytes": len(prompt_text.encode("utf-8")) if prompt_text else 0,
                "entry_prompt_mode": "compact_trade_quality_v1",
                "wait_signature": wait_signature or None,
            },
        )
        proposal = append_paper_proposal(
            snapshot,
            review,
            raw_response,
            decision_wall_seconds,
            decision_duration_ns,
            prompt_text,
            planner_context,
        )
        proposal_id = proposal["proposal_id"]
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
        "proposal_id": proposal_id,
        "proposal_price": snapshot.get("price"),
        "execution_plan": review["execution_plan"],
        "wait_deduped": skip_wait_audit,
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
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
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
    except Exception as exc:
        # 2026-08-10: this used to log the bare string "Automatic deal-sheet
        # generation failed" with no exception attached, which cannot be
        # counted, grouped or alerted on. Carry a stable code plus the actual
        # error type so failures become measurable.
        logging.exception(
            "dealsheet:generation_failed :: %s: %s",
            type(exc).__name__,
            exc,
        )
    finally:
        QWEN_DECISION_LOCK.release()


def self_test_entry_prompt() -> None:
    """Verify compact entry prompt stays far below the old ~14KB+ core_skill dump."""
    entry_cache = {
        "status": "ready",
        "validated_at_utc": "2026-08-09T00:00:00Z",
        "decision_time_utc": "2026-08-09T00:00:00Z",
        "epochs": {
            "structural": "s1",
            "levels": "l1",
            "session": "ss1",
            "playbooks": "p1",
            "minute": "m1",
        },
        "structure": {
            "current_h4_state": "forming_active",
            "nearest_lower_zone": {
                "level_id": "H1_SUP_1",
                "zone_low": 3300.0,
                "zone_high": 3301.0,
                "role": "support",
            },
            "nearest_upper_zone": {
                "level_id": "H1_RES_1",
                "zone_low": 3310.0,
                "zone_high": 3311.0,
                "role": "resistance",
            },
            "timeframe_location": {
                "H4": {
                    "location": "inside_prior",
                    "auction_state": "balance",
                    "latest_completed": {"close": 3305.0},
                    "evidence_ids": ["H4_1", "H4_2"],
                },
                "H1": {
                    "location": "above_prior",
                    "auction_state": "acceptance",
                    "latest_completed": {"close": 3306.0},
                    "evidence_ids": ["H1_1", "H1_2"],
                },
            },
        },
        "session": {
            "session": "london",
            "trade_permitted": True,
            "asia_high": 3312.0,
            "asia_low": 3298.0,
            "asia_relation": "inside",
        },
        "playbooks": [
            {
                "playbook_id": "pb1",
                "level_id": "H1_RES_1",
                "buy_condition": "M5 close reclaim above H1_RES_1",
                "sell_condition": "M1 fail close below H1_RES_1",
                "missing_evidence": None,
                "evidence_ids": ["H1_1"],
            }
        ],
        "minute": {
            "quote": {"bid": 3305.5, "ask": 3305.7, "spread": 0.2, "age_ms": 40},
            "closed_m1": {
                "id": "M1_1",
                "open": 3305.0,
                "high": 3306.0,
                "low": 3304.5,
                "close": 3305.4,
                "tick_volume": 120,
            },
            "forming": {
                "M1": {"id": "M1f", "open": 3305.4, "high": 3305.8, "low": 3305.2, "current": 3305.6},
                "H4": {"id": "H4f", "open": 1, "high": 2, "low": 0, "current": 1},
            },
            "volume": {"M1_ratio": 1.2, "M5_ratio": 0.9},
            "nearby_levels": [{"id": "H1_RES_1", "price": 3310.0, "distance": 4.5}],
        },
        "recent_closed": {
            "M1": [
                {
                    "evidence_id": f"M1_{index}",
                    "open": 3300 + index,
                    "high": 3301 + index,
                    "low": 3299 + index,
                    "close": 3300.5 + index,
                    "tick_volume": 100 + index,
                }
                for index in range(5)
            ],
            "M5": [],
            "M15": [],
            "M30": [],
        },
        "levels": [
            {
                "level_id": "H1_SUP_1",
                "timeframe": "H1",
                "zone_low": 3300.0,
                "zone_high": 3301.0,
                "role": "support",
            },
            {
                "level_id": "H1_RES_1",
                "timeframe": "H1",
                "zone_low": 3310.0,
                "zone_high": 3311.0,
                "role": "resistance",
            },
        ],
        "known_evidence_ids": [
            "H4_1", "H4_2", "H1_1", "H1_2", "M1_0", "M1_1", "M1_2", "M1_3", "M1_4",
            "H1_SUP_1", "H1_RES_1",
        ],
    }
    decision_levels = cache_levels_for_decision(entry_cache)
    facts = compact_entry_facts(entry_cache, decision_levels, {}, "XAUUSDr")
    prompt = build_entry_prompt(facts)
    prompt_bytes = len(prompt.encode("utf-8"))
    assert "core_skill" not in prompt
    assert "ENTRY FACTS" in prompt
    assert "execution_levels" in facts
    assert "forming" in facts and "H4" not in facts["forming"]
    assert prompt_bytes < 6000, prompt_bytes
    schema = entry_decision_schema(entry_cache, decision_levels, facts)
    assert "H1_RES_1" in schema["properties"]["execution_plan"]["properties"]["entry_low_id"]["enum"]
    wait_review = {
        "execution_plan": {"status": "wait", "reason": "Entry cache blocked."},
        "entry_validation_failures": ["entry_cache:minute:expired"],
    }
    blocked_cache = {
        "status": "blocked",
        "reason": "cache_provenance_invalid",
        "session": {},
    }
    sig_a = wait_decision_signature(wait_review, blocked_cache)
    sig_b = wait_decision_signature(wait_review, blocked_cache)
    assert sig_a and sig_a == sig_b
    assert wait_decision_signature(
        {"execution_plan": {"status": "ready", "reason": "ok"}}, blocked_cache
    ) == ""
    print(f"reviewer entry-prompt self-test passed prompt_bytes={prompt_bytes}")


def main() -> None:
    # A localhost listener prevents duplicate entry-decision instances.
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", 48631))
        singleton.listen(1)
    except OSError:
        return

    logging.info("Qwen entry-decision process starting; interval=%ds", INTERVAL_SECONDS)
    # Evict any previous qwen-trading-* left pinned in VRAM. warm_model() pins
    # with keep_alive=-1, so a model switch otherwise leaves BOTH resident and
    # Ollama starts returning HTTP 500 on every call (2026-08-10 incident).
    try:
        evicted = unload_stale_models()
        if evicted:
            logging.info("freed VRAM by evicting: %s", ", ".join(evicted))
    except Exception:
        logging.exception("model:stale_eviction_failed")
    start_dashboard_server()
    while True:
        started = time.monotonic()
        try:
            market = gold_market_open()
            sync_model_residency(market)
            if not market.get("open"):
                logging.info(
                    "Market closed (%s); Qwen unloaded/idle — skip entry cycle",
                    market.get("reason"),
                )
            else:
                generate_automatic_deal_sheet()

            # Time-based liveness must run every cycle, including cycles that
            # produce nothing. The 2026-08-10 outage was invisible precisely
            # because the absence of decisions emitted no signal.
            management_state = read_json_safe(
                MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE
            )
            for alarm in LIVENESS.check_time_based(
                time.time(),
                trade_permitted=bool(market.get("open")),
                cache_ready=bool(
                    (management_state.get("context_cache") or {}).get("status") == "ready"
                ),
                has_open_position=any(
                    position.get("qwen_owned")
                    for position in management_state.get("positions", [])
                ),
            ):
                logging.error(format_alarm(alarm))
        except Exception:
            logging.exception("entry:cycle_failed")
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test_entry_prompt()
    else:
        main()
