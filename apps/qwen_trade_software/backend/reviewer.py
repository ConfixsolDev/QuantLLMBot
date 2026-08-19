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
import live_mapped_levels
import plan_ladder
from execution_funnel import build_funnel
from decision_liveness import (
    DecisionEvent,
    DecisionLivenessMonitor,
    format_alarm,
)
import build_manifest
import news_blackout
import process_logging
from trade_step_log import log_step
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
    gpu_residency,
    sync_model_residency,
    unload_stale_models,
    write_json_atomic,
)
from session_planner import (
    build_branch_view,
    refresh_idea_states,
    DEFAULT_PLANNER_STATE,
    live_mid_from_facts,
    live_sanity_snapshot,
    load_plan_history,
    planner_facts,
    read_chart_candles,
)
from tick_data_archive import append_qwen_decision, append_tick_record
from trade_geometry import TF_MIN_STOP, TF_MIN_TARGET, min_stop_for, min_target_for
from approach_tracker import ApproachTracker
from idea_lifecycle import IdeaManager
from zone_scorer import score_zones, compact_score_log, ScoringConfig
from market_structure import compute_structure_context


# 2026-08-06: kept separate from trade_management.py's
# QWEN_REVIEW_INTERVAL_SECONDS on purpose -- "how often to check for a new
# setup when flat" and "how often to review an open trade" are different
# concerns now that they're different processes, and may end up tuned to
# different values once real numbers are in from the faster GPU machine.
# Defaults to the same 30s starting point either way.
INTERVAL_SECONDS = int(os.environ.get("QWEN_ENTRY_INTERVAL_SECONDS", "30"))
DAILY_PAPER_CAP = 100
ENTRY_REGIME_MEMORY = {"hint": None, "atr_ratio": None}
MIN_ENTRY_CONFIDENCE = 51
QWEN_PLAN_GATING = os.environ.get("QWEN_PLAN_GATING", "0") == "1"
QWEN_DECISION_LOCK = threading.Lock()
# Rolling health view of the decision stream. Holds the invariants that were
# missing on 2026-08-10, when the system produced no ready proposal for 2h20m
# with the market open, the cache ready and Qwen answering normally -- and
# nothing alarmed.
LIVENESS = DecisionLivenessMonitor()

# ---------------------------------------------------------------------------
# Trade idea lifecycle — persistent across cycles
# ---------------------------------------------------------------------------
from pathlib import Path as _Path

LIFECYCLE_STATE_FILE = _Path(__file__).resolve().parent / "lifecycle-state.json"
XAUUSD_SCORING_CONFIG = ScoringConfig()  # default tuning for gold

_IDEA_MANAGER = IdeaManager()
_APPROACH_TRACKER = ApproachTracker()
LEGACY_DUAL_ASSESSMENT = "dual-direction assessment"


def _has_legacy_dual_assessment(value) -> bool:
    """Detect the retired dual-direction wording in persisted/model state."""
    if isinstance(value, dict):
        return any(_has_legacy_dual_assessment(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_legacy_dual_assessment(item) for item in value)
    return LEGACY_DUAL_ASSESSMENT in str(value or "").lower()


def _load_lifecycle_state() -> None:
    """Restore IdeaManager and ApproachTracker from disk on startup."""
    global _IDEA_MANAGER, _APPROACH_TRACKER
    state = read_json_safe(LIFECYCLE_STATE_FILE, {})
    if _has_legacy_dual_assessment(state.get("idea_manager")):
        # The retired response was persisted as the active thesis and then fed
        # back to Qwen on every call. Start a fresh directional observation;
        # broker/trade logs remain untouched.
        logging.warning("lifecycle:discarded_legacy_dual_assessment_state")
        _IDEA_MANAGER = IdeaManager()
        _APPROACH_TRACKER = ApproachTracker()
        _save_lifecycle_state()
        return
    if state.get("idea_manager"):
        try:
            _IDEA_MANAGER = IdeaManager.from_state(state["idea_manager"])
        except Exception:
            logging.exception("lifecycle:idea_manager_restore_failed")
            _IDEA_MANAGER = IdeaManager()
    if state.get("approach_tracker"):
        try:
            _APPROACH_TRACKER = ApproachTracker.from_state(state["approach_tracker"])
        except Exception:
            logging.exception("lifecycle:approach_tracker_restore_failed")
            _APPROACH_TRACKER = ApproachTracker()


def _save_lifecycle_state() -> None:
    """Persist IdeaManager and ApproachTracker to disk after each cycle."""
    state = {
        "idea_manager": _IDEA_MANAGER.to_state(),
        "approach_tracker": _APPROACH_TRACKER.to_state(),
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json_atomic(LIFECYCLE_STATE_FILE, state)


# NOTE (2026-08-11): there was a QWEN_POLICY_V2 flag here. It was defined and
# never read, so setting it to 1 did nothing at all while appearing to promise a
# behaviour change. entry_policy.py stays -- its guards and MIN_ENTRY_CONFIDENCE
# are live -- but its dual-side decide() path is not wired, and a study of 71
# closed trades found its two testable mechanisms either already delivered by the
# existing funnel or inert on every trade on record. See
# docs/research/dual_side_policy_study.md before reviving it.
# Broker entry bracket is fixed; structure S/R is for the model zone + management.
FIXED_STOP_DISTANCE = 3.0
FIXED_TARGET_DISTANCE = 5.0
MIN_STOP_DISTANCE = FIXED_STOP_DISTANCE
MIN_TARGET_DISTANCE = FIXED_TARGET_DISTANCE
MAX_STRUCTURE_DISTANCE = 40.0
STRUCTURE_TIMEFRAMES = ("H4", "H1", "M15", "M30", "D1")

# A slow local-model response is still usable when price remains in the same
# local auction. Beyond this ATR-aware displacement it is a stale snapshot and
# must be reviewed again instead of becoming a late entry.
MIN_DECISION_DRIFT_POINTS = 2.0
MAX_DECISION_DRIFT_ATR_FRACTION = 0.75


def decision_snapshot_freshness(
    source_facts: dict,
    current_cache: dict,
) -> dict:
    """Compare the Qwen prompt snapshot with market state after generation."""
    source_quote = source_facts.get("quote") or {}
    current_quote = ((current_cache.get("minute") or {}).get("quote") or {})
    try:
        source_price = float(source_quote.get("bid") or source_quote.get("ask"))
        current_price = float(current_quote.get("bid") or current_quote.get("ask"))
    except (TypeError, ValueError):
        return {"fresh": False, "reason": "quote_unavailable_after_qwen"}
    try:
        atr = float((source_facts.get("regime_context") or {}).get("atr_m1_51") or 0)
    except (TypeError, ValueError):
        atr = 0.0
    threshold = max(
        MIN_DECISION_DRIFT_POINTS,
        atr * MAX_DECISION_DRIFT_ATR_FRACTION,
    )
    drift = abs(current_price - source_price)
    source_m1 = (source_facts.get("closed_m1") or {}).get("id")
    current_m1 = ((current_cache.get("minute") or {}).get("closed_m1") or {}).get("id")
    return {
        "fresh": drift <= threshold,
        "reason": None if drift <= threshold else "decision_snapshot_price_drift",
        "source_price": source_price,
        "current_price": current_price,
        "price_drift": round(drift, 3),
        "maximum_drift": round(threshold, 3),
        "source_closed_m1": source_m1,
        "current_closed_m1": current_m1,
        "closed_m1_changed": bool(source_m1 and current_m1 and source_m1 != current_m1),
    }


def latest_paper_execution():
    for path in _dated_log_files("paper-executions"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _execution_outcome_index(days_back: int = 2) -> dict[str, dict]:
    """Best execution outcome per proposal_id (skip/close preferred over monitors)."""
    priority = {
        "mt5_execution_closed": 50,
        "mt5_execution_skipped": 40,
        "mt5_fill": 30,
        "mt5_execution_started": 20,
        # Monitor rows moved to paper-path on 2026-08-11 and no longer appear
        # in this file. The entry is kept so an older log replayed through this
        # function still ranks correctly.
        "mt5_execution_monitor": 10,
    }
    by_id: dict[str, tuple[int, dict]] = {}
    for path in _dated_log_files("paper-executions", days_back=days_back):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            proposal_id = event.get("proposal_id")
            if not proposal_id:
                continue
            rank = priority.get(str(event.get("event")), 0)
            if rank <= 0:
                continue
            row = {
                "event": event.get("event"),
                "reason": event.get("reason"),
                "detail": event.get("detail"),
                "side": event.get("side"),
                "average_entry": event.get("average_entry"),
                "net_pnl": event.get("net_pnl"),
                "created_at_utc": event.get("created_at_utc"),
            }
            prior = by_id.get(proposal_id)
            if prior is None or rank > prior[0] or (
                rank == prior[0] and rank in (10, 50)
            ):
                by_id[proposal_id] = (rank, row)
    return {key: value[1] for key, value in by_id.items()}


def _geometry_metrics(plan: dict) -> dict:
    """Stop/target distances and R:R from the proposal execution plan."""
    side = str(plan.get("side") or "").lower()
    try:
        entry_low = float(plan.get("entry_low") or 0)
        entry_high = float(plan.get("entry_high") or 0)
    except (TypeError, ValueError):
        entry_low = entry_high = 0.0
    entry_mid = (
        (entry_low + entry_high) / 2.0
        if entry_low and entry_high
        else entry_low or entry_high or 0.0
    )

    def _dist(a, b) -> float | None:
        try:
            if a is None or b is None:
                return None
            return round(abs(float(a) - float(b)), 3)
        except (TypeError, ValueError):
            return None

    stop = plan.get("stop_loss")
    target = plan.get("take_profit")
    structural_stop = plan.get("structural_stop_loss")
    structural_target = plan.get("structural_take_profit")
    stop_distance = plan.get("stop_distance")
    target_distance = plan.get("target_distance")
    try:
        stop_distance = float(stop_distance) if stop_distance is not None else _dist(entry_mid, stop)
    except (TypeError, ValueError):
        stop_distance = _dist(entry_mid, stop)
    try:
        target_distance = (
            float(target_distance) if target_distance is not None else _dist(entry_mid, target)
        )
    except (TypeError, ValueError):
        target_distance = _dist(entry_mid, target)

    structural_stop_distance = _dist(entry_mid, structural_stop)
    structural_target_distance = _dist(entry_mid, structural_target)
    frame = str(plan.get("structure_timeframe") or "").upper() or None
    min_stop = min_stop_for(frame) if frame else None
    min_target = min_target_for(frame) if frame else None

    def _rr(reward, risk):
        if not reward or not risk or risk <= 0:
            return None
        return round(float(reward) / float(risk), 3)

    plan_rr = _rr(target_distance, stop_distance)
    structural_rr = _rr(structural_target_distance, structural_stop_distance)

    rr_issue = None
    check_target = structural_target_distance if structural_target_distance is not None else target_distance
    check_stop = structural_stop_distance if structural_stop_distance is not None else stop_distance
    if frame and check_target is not None and min_target is not None and check_target + 1e-9 < min_target:
        rr_issue = (
            f"target {check_target:.2f} below the {frame} minimum {min_target:.1f}"
        )
    elif frame and check_stop is not None and min_stop is not None and check_stop + 1e-9 < min_stop:
        rr_issue = (
            f"stop {check_stop:.2f} below the {frame} minimum {min_stop:.1f}"
        )
    elif structural_rr is not None and structural_rr + 1e-9 < 1.2:
        rr_issue = f"structural reward:risk {structural_rr:.2f} below 1.2"
    elif plan_rr is not None and plan_rr + 1e-9 < 1.2 and structural_rr is None:
        rr_issue = f"plan reward:risk {plan_rr:.2f} below 1.2"

    return {
        "side": side or None,
        "entry_low": entry_low or None,
        "entry_high": entry_high or None,
        "entry_mid": round(entry_mid, 3) if entry_mid else None,
        "stop_loss": stop,
        "take_profit": target,
        "stop_distance": stop_distance,
        "target_distance": target_distance,
        "plan_reward_risk": plan_rr,
        "structural_stop_loss": structural_stop,
        "structural_take_profit": structural_target,
        "structural_stop_distance": structural_stop_distance,
        "structural_target_distance": structural_target_distance,
        "structural_reward_risk": structural_rr,
        "structure_timeframe": frame,
        "frame_min_stop": min_stop,
        "frame_min_target": min_target,
        "geometry_source": plan.get("geometry_source"),
        "rr_issue": rr_issue,
    }


def list_trade_ideas(
    *,
    min_confidence: float = 50.0,
    days_back: int = 2,
    ready_only: bool = False,
    limit: int = 300,
) -> dict:
    """Trade ideas with confidence above the floor, plus R:R / execution outcome.

    Used by Plan View /ideas so operators can see geometry skips
    (reward_risk_too_low / target below HTF minimum) on high-confidence ideas.
    """
    outcomes = _execution_outcome_index(days_back=days_back)
    ideas: list[dict] = []
    for path in _dated_log_files("paper-proposals", days_back=days_back):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
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
            try:
                confidence = float(qwen.get("confidence") or 0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence <= float(min_confidence):
                continue
            status = str(plan.get("status") or "").lower()
            if ready_only and status != "ready":
                continue
            proposal_id = proposal.get("proposal_id")
            geometry = _geometry_metrics(plan)
            outcome = outcomes.get(proposal_id) if proposal_id else None
            outcome_reason = (outcome or {}).get("reason")
            outcome_detail = (outcome or {}).get("detail")
            reason_l = str(outcome_reason or "").lower()
            blocked_by_rr = bool(outcome_reason) and (
                "reward_risk" in reason_l or reason_l.startswith("geometry:")
            )
            ideas.append(
                {
                    "proposal_id": proposal_id,
                    "created_at_utc": proposal.get("created_at_utc"),
                    "symbol": proposal.get("symbol"),
                    "price": (proposal.get("market") or {}).get("price"),
                    "bias": qwen.get("bias"),
                    "confidence": confidence,
                    "summary": qwen.get("summary"),
                    "status": status or None,
                    "plan_reason": plan.get("reason"),
                    "side": plan.get("side") or geometry.get("side"),
                    "entry_low_id": plan.get("entry_low_id"),
                    "entry_high_id": plan.get("entry_high_id"),
                    "stop_level_id": plan.get("stop_level_id"),
                    "target_level_id": plan.get("target_level_id"),
                    "geometry": geometry,
                    "outcome": outcome,
                    "blocked_by_geometry": blocked_by_rr,
                    "geometry_block_detail": outcome_detail
                    or geometry.get("rr_issue"),
                }
            )
    ideas.sort(key=lambda row: row.get("created_at_utc") or "", reverse=True)
    if limit > 0:
        ideas = ideas[: int(limit)]
    blocked = sum(1 for row in ideas if row.get("blocked_by_geometry"))
    ready = sum(1 for row in ideas if row.get("status") == "ready")
    return {
        "min_confidence": float(min_confidence),
        "days_back": int(days_back),
        "count": len(ideas),
        "ready_count": ready,
        "geometry_blocked_count": blocked,
        "frame_min_targets": dict(TF_MIN_TARGET),
        "frame_min_stops": dict(TF_MIN_STOP),
        "ideas": ideas,
    }


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


def new_proposal_id(created_at: datetime | None = None) -> str:
    """Mint the id that ties one entry decision to everything that follows.

    2026-08-11 -- why this is a separate function
    ---------------------------------------------
    The id used to be minted inside append_paper_proposal(), which runs AFTER
    append_qwen_decision(). So the decision record -- the only place the prompt
    and the raw model response are stored -- carried proposal_id=None on all
    3,703 entry decisions ever written. The field existed and was always empty.

    The consequence: not one closed trade could be joined back to the prompt
    that produced it, so live trading has never been able to feed model
    training. Minting the id first, before the model is called, makes
    prompt -> decision -> proposal -> fill -> outcome a single joinable chain.
    """
    created_at = created_at or datetime.now(timezone.utc)
    return f"paper-{created_at:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"


def append_paper_proposal(
    snapshot: dict,
    review: dict,
    raw_response: str,
    decision_wall_seconds: float | None = None,
    decision_duration_ns: int | None = None,
    prompt_text: str | None = None,
    planner_context: dict | None = None,
    proposal_id: str | None = None,
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
        # Supplied by the caller so the decision record written BEFORE this
        # point carries the same id. Minting one here is the fallback path.
        "proposal_id": proposal_id or new_proposal_id(created_at),
        **build_manifest.stamp(),
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
    plan = proposal["qwen"].get("execution_plan") or {}
    quote = (snapshot.get("entry_cache", {}).get("minute", {}).get("quote", {}))
    log_step(
        "proposal_ready", plan.get("status", "wait"),
        proposal_id=proposal["proposal_id"], symbol=proposal.get("symbol"),
        price=quote.get("bid"), quote_age_ms=quote.get("age_ms"),
        bias=proposal["qwen"].get("bias"), confidence=proposal["qwen"].get("confidence"),
        side=plan.get("side"), entry_low=plan.get("entry_low"),
        entry_high=plan.get("entry_high"), optimal_entry_price=plan.get("optimal_entry_price"),
        detail=plan.get("reason"),
    )
    logging.info("Paper proposal recorded: %s", proposal["proposal_id"])
    return proposal


# Claims the root logger for THIS process. Must use process_logging.configure
# (force=True), not bare basicConfig: reviewer imports session_planner above,
# whose module-level setup would otherwise have already claimed the root logger
# and silently swallowed this call, sending every reviewer line to
# session-planner.log. See process_logging.py.
_LOG_HANDLER = process_logging.configure(LOG_DIR / "reviewer.log", owner="reviewer")
# Announce the build and alarm if it has drifted from the declared freeze.
build_manifest.log_identity("reviewer")


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
                "pattern": row.get("pattern"),
                "test_count": row.get("test_count"),
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
    """Nearest named levels above and below price for geometry only.

    Live and operator-mapped shelves inside PIN_BAND, or an active double
    top/bottom, stay selectable so the model can name the zone it actually sees.
    Distant yesterday shelves are not pinned into the enum.
    """
    rows = [
        {
            "id": str(row["id"]),
            "tf": timeframe,
            "lo": float(row["price"]),
            "hi": float(row["zone_high"]),
            "role": row.get("role"),
            "pattern": row.get("pattern"),
            "test_count": row.get("test_count"),
        }
        for timeframe, level_rows in decision_levels.items()
        for row in level_rows
    ]
    rows.sort(key=lambda item: item["lo"])
    below = [row for row in rows if row["hi"] <= mid_price][-each_side:]
    above = [row for row in rows if row["lo"] > mid_price][:each_side]
    pinned = [row for row in rows if live_mapped_levels.should_pin(row, mid_price)]
    merged: list[dict] = []
    seen: set[str] = set()
    for row in below + above + pinned:
        level_id = row["id"]
        if level_id in seen:
            continue
        seen.add(level_id)
        merged.append(row)
    merged.sort(key=lambda item: item["lo"])
    return merged


def compact_entry_facts(
    entry_cache: dict,
    decision_levels: dict,
    planner_context: dict,
    symbol: str,
    *,
    idea_manager: IdeaManager | None = None,
    approach_tracker: ApproachTracker | None = None,
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
    live_map = minute.get("live_map") or {}
    for row in live_map.get("near") or []:
        _add_cite(row.get("id"))
    for key in ("double_top", "double_bottom"):
        if isinstance(live_map.get(key), dict):
            _add_cite(live_map[key].get("id"))

    packet = {
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
        "live_map": live_map,
        "recent_closed": recent,
        "execution_levels": execution_levels,
        "planner": planner,
        "citeable_evidence_ids": citeable,
        "regime_context": {},
        "confirmation_context": {},
        "suggested_target_mode": None,
        "prior_idea_context": {},
        "active_idea_context": {},
        "zone_scores": [],
        "approach_context": {},
        "zone_edge_context": {},
        "market_structure": {},
    }

    # -- Lifecycle context injection --
    mgr = idea_manager or _IDEA_MANAGER
    trk = approach_tracker or _APPROACH_TRACKER
    # A closed M1 beyond the wrong side of the watched zone invalidates the
    # directional idea before Qwen sees the packet. Previously the stale sell
    # at 4347 remained active while M5 had already changed bullish, repeatedly
    # anchoring the model to confidence=50 waits. Forming price/wicks never
    # trigger this rule.
    invalidated = mgr.invalidate_on_closed_acceptance(
        closed_m1.get("close"),
        closed_m1.get("id"),
    )
    if invalidated is not None:
        trk.reset()
        logging.info(
            "lifecycle:closed_acceptance_invalidated idea=%s side=%s zone=[%.3f-%.3f] close=%s",
            invalidated.idea_id,
            invalidated.side,
            invalidated.zone_low,
            invalidated.zone_high,
            closed_m1.get("close"),
        )
    current_level_ids = {
        str(row.get("id")) for row in execution_levels if row.get("id")
    }
    recovered = mgr.recover_stale(
        closed_m1.get("close"),
        current_level_ids=current_level_ids,
    )
    if recovered is not None:
        trk.reset()
        logging.warning(
            "STALE_RECOVERY component=active_idea action=resolved "
            "idea=%s zone=%s side=%s outcome=%s reason=%s",
            recovered.idea_id,
            recovered.zone_id,
            recovered.side,
            recovered.outcome,
            recovered.resolution_reason,
        )
        log_step(
            "freshness_recovery", "recovered", symbol=symbol,
            price=closed_m1.get("close"), detail=recovered.resolution_reason,
            active_idea=recovered.zone_id,
        )
    packet["prior_idea_context"] = mgr.prior_idea_context()
    packet["active_idea_context"] = mgr.active_idea_for_facts()
    packet["freshness"] = {
        "quote_age_ms": quote.get("age_ms"),
        "validated_at_utc": entry_cache.get("validated_at_utc"),
        "decision_time_utc": entry_cache.get("decision_time_utc"),
        "active_idea_recovered": recovered is not None,
        "recovery_reason": (
            recovered.resolution_reason if recovered is not None else None
        ),
    }

    # Zone scoring: score nearby levels as zones using recent M15 bars.
    # nearby_levels use "pattern" (not "kind") and test_count may be None.
    # recent_closed bars are in slim format {o,h,l,c} — expand for scorer.
    try:
        nearby = minute.get("nearby_levels") or []
        raw_m15 = (entry_cache.get("recent_closed") or {}).get("M15") or []
        # Expand slim bars to full-key format the scorer expects
        full_m15 = []
        for b in raw_m15:
            full_m15.append({
                "open": b.get("open") or b.get("o"),
                "high": b.get("high") or b.get("h"),
                "low": b.get("low") or b.get("l"),
                "close": b.get("close") or b.get("c"),
                "evidence_id": b.get("evidence_id") or b.get("id"),
            })
        if nearby and full_m15:
            zone_dicts = []
            for lvl in nearby[:15]:
                price = float(lvl.get("price", 0))
                half = float(lvl.get("zone_width", 1.5)) / 2.0
                tc = lvl.get("test_count")
                zone_dicts.append({
                    "level_id": lvl.get("id", ""),
                    "zone_low": price - half,
                    "zone_high": price + half,
                    "kind": lvl.get("pattern") or lvl.get("kind") or "",
                    "test_count": int(tc) if tc is not None else 0,
                })
            scored = score_zones(
                zone_dicts, full_m15,
                live_price=mid, config=XAUUSD_SCORING_CONFIG,
                min_grade="C",
            )
            packet["zone_scores"] = [s.to_dict() for s in scored[:5]]
    except Exception:
        logging.debug("lifecycle:zone_scoring_failed", exc_info=True)

    # Approach tracking: update if there's an active idea.
    # Expand slim M5 bars {o,h,l,c} to full keys for the tracker.
    if mgr.has_active and mid > 0:
        active = mgr.active_idea
        raw_m5 = (entry_cache.get("recent_closed") or {}).get("M5") or []
        full_m5 = []
        for b in raw_m5:
            full_m5.append({
                "open": b.get("open") or b.get("o"),
                "high": b.get("high") or b.get("h"),
                "low": b.get("low") or b.get("l"),
                "close": b.get("close") or b.get("c"),
            })
        try:
            snap = trk.observe(
                target_zone_id=active.zone_id,
                target_zone_low=active.zone_low,
                target_zone_high=active.zone_high,
                target_side=active.side,
                live_price=mid,
                recent_bars=full_m5[-10:],
                confirmations=packet.get("confirmation_context"),
                timestamp=time.time(),
            )
            packet["approach_context"] = snap.to_dict()
            mgr.update_approach(active.idea_id, snap.to_dict())
        except Exception:
            logging.debug("lifecycle:approach_tracking_failed", exc_info=True)

        # Zone-edge entry context: optimal fill price and structural SL.
        # Buy → enter at zone_low (lowest possible), SL just below.
        # Sell → enter at zone_high (highest possible), SL just above.
        # Structural SL buffer: spread + noise margin beyond zone boundary.
        SL_BUFFER = 1.5  # points beyond zone edge (XAUUSD spread ~0.3 + slippage + noise)
        if active.side == "buy":
            optimal_entry = active.zone_low
            structural_sl = active.zone_low - SL_BUFFER
            sl_distance = optimal_entry - structural_sl
        else:
            optimal_entry = active.zone_high
            structural_sl = active.zone_high + SL_BUFFER
            sl_distance = structural_sl - optimal_entry

        # Distance from current price to the optimal entry
        distance_to_optimal = abs(mid - optimal_entry)

        packet["zone_edge_context"] = {
            "optimal_entry_price": round(optimal_entry, 3),
            "structural_sl_price": round(structural_sl, 3),
            "structural_sl_distance": round(sl_distance, 3),
            "distance_to_optimal": round(distance_to_optimal, 3),
            "zone_width": round(active.zone_high - active.zone_low, 3),
            "side": active.side,
            "note": (
                f"{'Buy' if active.side == 'buy' else 'Sell'} at zone edge "
                f"{optimal_entry:.1f}, SL {structural_sl:.1f} "
                f"(risk {sl_distance:.1f}pts)"
            ),
        }

    # -- Market structure context (ICT/SMC) --
    try:
        ms = compute_structure_context(symbol, mid)
        if ms.get("status") == "ok":
            packet["market_structure"] = ms
            # Phase 2 must not depend on Qwen already saying "ready".  That
            # created a circular deadlock: without a remembered zone there was
            # no approach/response context, and without that context Qwen could
            # never select a zone.  Seed one directional candidate when M5 and
            # H1 agree; Qwen still owns the final entry decision.
            trends = ms.get("trends") or {}
            m5_trend = trends.get("M5")
            h1_trend = trends.get("H1")
            seed_side = (
                "sell" if m5_trend == h1_trend == "bearish" else
                "buy" if m5_trend == h1_trend == "bullish" else None
            )
            if not mgr.has_active and seed_side and mid > 0:
                candidates = []
                for level in execution_levels:
                    lo = float(level.get("lo") or 0)
                    hi = float(level.get("hi") or lo)
                    if lo <= 0:
                        continue
                    correct_side = lo >= mid if seed_side == "sell" else hi <= mid
                    if not correct_side:
                        continue
                    distance = lo - mid if seed_side == "sell" else mid - hi
                    tf_rank = {"M15": 0, "M5": 1, "M1": 2, "H1": 3}.get(
                        str(level.get("tf")), 4
                    )
                    candidates.append((distance, tf_rank, level))
                if candidates:
                    _, _, target = min(candidates, key=lambda row: (row[0], row[1]))
                    zone_id = str(target["id"])
                    lo = float(target.get("lo") or 0)
                    hi = float(target.get("hi") or lo)
                    if abs(hi - lo) < 1e-9:
                        lo, hi = _zone_bounds_from_data(
                            zone_id, lo, seed_side, packet
                        )
                    idea = mgr.create_idea(
                        zone_id=zone_id,
                        side=seed_side,
                        zone_low=min(lo, hi),
                        zone_high=max(lo, hi),
                        thesis=(
                            f"Deterministic {m5_trend} M5/H1 directional bias; "
                            f"stalk nearest mapped {seed_side} zone"
                        ),
                    )
                    packet["active_idea_context"] = mgr.active_idea_for_facts()
                    logging.info(
                        "lifecycle:idea_seeded_directional :: %s [%.3f-%.3f] "
                        "side=%s idea=%s",
                        zone_id, min(lo, hi), max(lo, hi), seed_side, idea.idea_id,
                    )
    except Exception:
        logging.debug("lifecycle:market_structure_failed", exc_info=True)

    try:
        from regime_engine import snapshot_regime, suggested_target_mode

        level_prices = {}
        for row in execution_levels:
            level_id = row.get("id")
            if not level_id:
                continue
            try:
                lo = float(row.get("lo") or row.get("price") or 0)
                hi = float(row.get("hi") or lo)
            except (TypeError, ValueError):
                continue
            level_prices[str(level_id)] = (lo + hi) / 2.0
        if mid > 0:
            packet["regime_context"] = snapshot_regime(
                symbol,
                mid,
                level_prices,
                prev_regime=ENTRY_REGIME_MEMORY.get("hint"),
                prev_atr_ratio=ENTRY_REGIME_MEMORY.get("atr_ratio"),
            )
            ENTRY_REGIME_MEMORY["hint"] = packet["regime_context"].get("regime_hint")
            ENTRY_REGIME_MEMORY["atr_ratio"] = packet["regime_context"].get("atr_ratio_3_51")
        packet["suggested_target_mode"] = suggested_target_mode(
            packet["regime_context"].get("regime_hint")
        )
        packet["regime_context"]["suggested_target_mode"] = packet[
            "suggested_target_mode"
        ]
    except Exception:
        pass
    try:
        from confirmation_engine import snapshot_confirmations

        packet["confirmation_context"] = snapshot_confirmations(symbol)
    except Exception:
        pass
    return packet


# Re-probe residency at most this often, and re-alarm at most this often. The
# entry loop runs every 30s; probing Ollama and shouting on every pass would
# bury the alarm in its own repetition.
GPU_PROBE_INTERVAL_SECONDS = 60.0
GPU_ALARM_INTERVAL_SECONDS = 300.0
_GPU_GATE_STATE = {"checked_at": 0.0, "ok": True, "alarmed_at": 0.0}

# Set QWEN_REQUIRE_GPU=0 to trade on CPU anyway. Present so an operator who
# understands the cost can override, not because CPU is a supported mode --
# decisions arrive after their proposal has expired, which is why this defaults
# to on.
REQUIRE_GPU = os.environ.get("QWEN_REQUIRE_GPU", "1") != "0"

# The window a decision has to beat, quoted in the alarm so the number is in
# front of whoever reads it. Mirrors paper_runner.MAX_PROPOSAL_AGE_SECONDS,
# which owns the real TTL -- duplicated rather than imported because reviewer
# does not otherwise depend on the runner, and a wrong number in a log message
# is cheaper than a new import cycle.
PROPOSAL_TTL_SECONDS_FOR_ALARM = 60


# Re-announce an ongoing blackout at most this often. The entry loop runs every
# 30s; a 30-minute window would otherwise produce 60 identical lines.
NEWS_LOG_INTERVAL_SECONDS = 300.0
_NEWS_GATE_STATE: dict = {"logged_at": 0.0, "event_key": None}


def news_blackout_active() -> bool:
    """True while a high-impact release makes a new entry unwise.

    ENTRIES ONLY. This is never consulted by trade_management, and that
    asymmetry is deliberate: an open position has money at risk and needs
    looking after through the release more than at any other time. Closing or
    abandoning a live trade because a calendar entry exists would be a worse
    decision than the one being avoided.

    Fails OPEN. Every failure path in news_blackout returns None, so a missing,
    stale or unreachable calendar lets trading continue and says so loudly.
    """
    try:
        event = news_blackout.active_event()
    except Exception:
        logging.exception("news:gate_failed — failing open")
        return False
    if not event:
        _NEWS_GATE_STATE["event_key"] = None
        return False

    key = f"{event['title']}@{event['event_time_utc']}"
    now = time.monotonic()
    if (
        key != _NEWS_GATE_STATE["event_key"]
        or now - float(_NEWS_GATE_STATE["logged_at"]) >= NEWS_LOG_INTERVAL_SECONDS
    ):
        _NEWS_GATE_STATE.update({"event_key": key, "logged_at": now})
        logging.info(
            "news blackout: no new entries — %s %s (%s) at %s, window %s to %s "
            "(%.0f min away). Open positions continue to be managed.",
            event["country"], event["title"], event["impact"],
            event["event_time_utc"][11:16],
            event["window_start_utc"][11:16], event["window_end_utc"][11:16],
            event["minutes_to_event"],
        )
        news_blackout.record_block(event)
    return True


def gpu_ready_for_entry() -> bool:
    """True when the model is on the GPU and an entry decision can beat its TTL.

    Cached briefly: residency only changes on a load or an eviction, and this
    is called every cycle.

    Fails OPEN on an unreadable probe. If Ollama cannot be reached the entry
    call will fail on its own with a clear error -- refusing to trade because a
    diagnostic endpoint timed out would be a worse failure than the one being
    guarded against.
    """
    now = time.monotonic()
    if not REQUIRE_GPU:
        return True
    if now - _GPU_GATE_STATE["checked_at"] < GPU_PROBE_INTERVAL_SECONDS:
        return bool(_GPU_GATE_STATE["ok"])

    residency = gpu_residency()
    state = residency["state"]
    # "unloaded" is normal before the first warm and between market sessions;
    # "unknown" means the probe failed, not that placement is wrong.
    ok = state in ("gpu", "unloaded", "unknown")
    _GPU_GATE_STATE["checked_at"] = now
    _GPU_GATE_STATE["ok"] = ok

    if not ok and now - _GPU_GATE_STATE["alarmed_at"] >= GPU_ALARM_INTERVAL_SECONDS:
        _GPU_GATE_STATE["alarmed_at"] = now
        logging.error(
            "ALARM CRITICAL model:not_on_gpu :: %s is on %s (%s) — entry cycles "
            "are being SKIPPED. A decision takes 190-455s on CPU against a %ds "
            "proposal TTL, so every proposal would expire before its answer "
            "arrived. Free VRAM (`ollama ps` shows what is resident) and "
            "restart; set QWEN_REQUIRE_GPU=0 to trade anyway.",
            MODEL, state, residency["detail"], PROPOSAL_TTL_SECONDS_FOR_ALARM,
        )
    return ok


def _stamp_regime_target_mode(review: dict, facts: dict) -> None:
    """Apply deterministic Brooks regime permissions and execution profile."""
    from regime_engine import suggested_target_mode
    from regime_policy import execution_settings, range_entry_allowed
    from qualified_levels import remember_qualified_level_ids

    regime = (facts or {}).get("regime_context") or {}
    hint = regime.get("regime_hint")
    explicit_state = bool(regime.get("regime_state"))
    state = regime.get("regime_state") or regime.get("regime_hint") or "unknown"
    # A BOS label alone is only a breakout attempt. Promote only when closed
    # M5 and M15 structure agree and price is holding beyond the old range.
    confirmation = (facts or {}).get("confirmation_context") or {}
    m5 = confirmation.get("m5") or {}
    m15 = confirmation.get("m15") or {}

    def _event(frame: dict) -> dict:
        return frame.get("mss") or frame.get("choch") or frame.get("bos") or {}

    m5_event = _event(m5)
    m15_event = _event(m15)
    m5_direction = str(m5_event.get("direction") or m5_event.get("dir") or "").lower()
    m15_direction = str(m15_event.get("direction") or m15_event.get("dir") or "").lower()
    def _number(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    current_price = _number(regime.get("current_price"))
    resistance = _number(regime.get("range_resistance"))
    support = _number(regime.get("range_support"))
    breakout_side = None
    try:
        bullish_boundary = max(
            float(m5_event.get("broken") or 0),
            float(m15_event.get("broken") or 0),
            resistance,
        )
        bearish_boundary = min(
            value for value in (
                float(m5_event.get("broken") or 0),
                float(m15_event.get("broken") or 0),
                support,
            ) if value > 0
        )
    except (TypeError, ValueError):
        bullish_boundary = bearish_boundary = 0.0
    if m5_direction == m15_direction == "bullish" and bullish_boundary and current_price > bullish_boundary:
        breakout_side = "buy"
    elif m5_direction == m15_direction == "bearish" and bearish_boundary and current_price < bearish_boundary:
        breakout_side = "sell"
    if breakout_side and state in {"range", "trending_range", "breakout_attempt"}:
        state = "breakout_confirmed"
        regime["regime_state"] = state
        regime["trend_direction"] = breakout_side
        logging.info(
            "entry_regime_promoted state=breakout_confirmed side=%s evidence=m5+m15_closed_structure",
            breakout_side,
        )
    settings = execution_settings(state)
    suggested = settings.get("target_mode") or (facts or {}).get("suggested_target_mode") or suggested_target_mode(hint)
    plan = review.get("execution_plan")
    if not isinstance(plan, dict):
        plan = {}
        review["execution_plan"] = plan
    plan["regime_hint"] = hint
    plan["regime_state"] = state
    plan["volatility_state"] = regime.get("volatility_state")
    plan["regime_policy"] = settings
    plan["signal_ttl_seconds"] = settings["signal_ttl_seconds"]
    plan["risk_budget"] = settings["risk_budget"]
    plan["suggested_target_mode"] = suggested
    if plan.get("status") == "ready" and suggested and (explicit_state or not plan.get("target_mode")):
        plan["target_mode"] = suggested
    blocked_reason = settings.get("reason") if explicit_state and not settings.get("allow_new_entry") else None
    if plan.get("status") == "ready" and explicit_state and settings.get("edge_only"):
        try:
            entry = float(plan.get("optimal_entry_price"))
        except (TypeError, ValueError):
            try:
                entry = (float(plan["entry_low"]) + float(plan["entry_high"])) / 2.0
            except (KeyError, TypeError, ValueError):
                entry = None
        if not range_entry_allowed(plan.get("side"), entry, regime):
            blocked_reason = "range_middle_or_wrong_edge"
    expected_side = regime.get("trend_direction")
    if (
        plan.get("status") == "ready"
        and state in {"trend_strong", "trend_channel", "breakout_confirmed"}
        and expected_side in ("buy", "sell")
        and plan.get("side") != expected_side
    ):
        blocked_reason = f"plan_side_opposes_{state}_{expected_side}"
    if plan.get("status") == "ready" and blocked_reason:
        plan["status"] = "wait"
        plan["reason"] = f"Regime policy blocked entry: {blocked_reason}."
        logging.info("entry_regime_block state=%s reason=%s", state, blocked_reason)
    logging.info(
        "entry_regime hint=%s state=%s volatility=%s risk_budget=%s ttl=%s suggested_target_mode=%s qwen_target_mode=%s",
        hint, state, regime.get("volatility_state"), settings["risk_budget"], settings["signal_ttl_seconds"],
        suggested,
        plan.get("target_mode"),
    )
    try:
        from confirmation_engine import compact_confirmation_log

        logging.info(
            "entry_confirm %s",
            compact_confirmation_log((facts or {}).get("confirmation_context")),
        )
    except Exception:
        pass
    if plan.get("status") == "ready":
        remembered = remember_qualified_level_ids(
            [
                plan.get("entry_low_id"),
                plan.get("entry_high_id"),
                plan.get("stop_level_id"),
                plan.get("target_level_id"),
            ]
        )
        logging.info("qualified_levels count=%d", len(remembered))


def wait_reason_for(contradiction: str | None, review: dict) -> str:
    """Plain-language wait reason naming the actual cause.

    Folding every failure into one "Cache provenance validation failed." string
    is how the v1.9 contradiction stayed invisible for two hours: the wait
    reason named the wrong subsystem, so the logs pointed at the cache while
    the fault was the entry contract. Each cause gets its own sentence.
    """
    codes = entry_policy.ReasonCode
    if contradiction == codes.INVARIANT_READY_ZERO_CONFIDENCE:
        return (
            "Model returned ready with confidence 0; waiting until it has "
            "conviction."
        )
    if contradiction == codes.READY_CONTRADICTS_OWN_REASON:
        plan_reason = (review.get("execution_plan") or {}).get("reason") or "unstated"
        return (
            f"Model returned ready but its own reason says the setup has not "
            f"triggered ({plan_reason})."
        )
    if contradiction == codes.READY_BELOW_CONFIDENCE_THRESHOLD:
        return (
            f"Confidence below the {entry_policy.MIN_ENTRY_CONFIDENCE} entry "
            "threshold; waiting for a stronger read."
        )
    return "Cache provenance validation failed."


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


def qwen_contract_correction_reason(review: dict) -> str | None:
    """Return why one bounded model retry is required; never invent scores."""
    plan = review.get("execution_plan") or {}
    bias = str(review.get("bias") or "").lower()
    try:
        confidence = int(review.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if bias in ("buy", "sell") and confidence == 0:
        return "directional_bias_with_zero_confidence"
    if str(plan.get("status") or "").lower() == "ready":
        # Geometry omissions are repaired from validated mapped levels by
        # normalize_execution_plan. Retrying Qwen made otherwise valid M1
        # facts 20-35 seconds older without adding semantic judgment.
        declared_side = str(plan.get("side") or "").lower()
        if declared_side and bias in ("buy", "sell") and declared_side != bias:
            return "ready_side_contradicts_bias"
    return None


def build_qwen_correction_prompt(facts: dict, review: dict, reason: str) -> str:
    """Small retry packet: preserve evidence without re-sending ~20KB."""
    compact = {
        "quote": facts.get("quote"),
        "session": facts.get("session"),
        "epochs": facts.get("epochs"),
        "active_idea": facts.get("active_idea_context"),
        "approach": facts.get("approach_context"),
        "zone_edge": facts.get("zone_edge_context"),
        "closed_m1": facts.get("closed_m1"),
        "recent_m1": (facts.get("recent_closed") or {}).get("M1"),
        "confirmation": facts.get("confirmation_context"),
        "structure": facts.get("market_structure"),
        "execution_levels": (facts.get("execution_levels") or [])[:20],
        "citeable_evidence_ids": (facts.get("citeable_evidence_ids") or [])[:30],
        "previous_invalid_response": review,
    }
    return (
        f"Correct one XAUUSD entry JSON contract violation: {reason}. "
        "Return JSON only. Never claim the model is disabled. Confidence is "
        "1-100 and must be calibrated even for wait. Ready requires bias and "
        "side buy|sell plus entry_low_id, entry_high_id, stop_level_id, and "
        "target_level_id copied from execution_levels. If the M1 trigger or "
        "target is incomplete, return wait with the actual 1-50 confidence. "
        "Copy epochs exactly and cite only supplied evidence IDs.\nCORRECTION FACTS:\n"
        + json.dumps(compact, separators=(",", ":"))
    )


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
            "bias": {"type": "string", "enum": ["buy", "sell", "wait"]},
            # Every assessment must be calibrated. A value of 1 represents
            # effectively no conviction; zero caused v004 to emit a learned
            # disabled-mode placeholder instead of assessing supplied facts.
            "confidence": {"type": "integer", "minimum": 1, "maximum": 100},
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
                    "target_mode": {
                        "type": "string",
                        "enum": ["scalp", "starter_basket", "directional_basket"],
                    },
                    "volume_each": {"type": "number", "const": 0.5},
                    "reason": {"type": "string", "maxLength": 120},
                },
                # Wait must not fabricate a side or geometry. Ready geometry is
                # validated deterministically after the model response.
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
    facts: dict = {}
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
        # Keep the trade-idea stack on the same clock as the branch panel.
        # Without this the stack stays on its last HOURLY evaluation and the
        # screen contradicts itself -- Day Plan showing TARGET REACHED beside
        # H4/H1/M15 INVALIDATED (2026-08-11).
        planner["trade_idea_stack"] = refresh_idea_states(planner, live_price)
    except Exception:
        logging.exception("plan:branch_view_failed")
    # Why the system is or is not trading. Previously only discoverable by
    # reading paper-runner.log by hand.
    try:
        planner["execution_funnel"] = build_funnel(LOG_DIR).as_dict()
        # Pass the cache's per-timeframe levels so each frame's two branches are
        # built from its OWN structure rather than copying the day plan.
        planner["timeframe_ladder"] = plan_ladder.build_ladder_from_state(
            planner, live_price, (facts or {}).get("levels")
        )
    except Exception:
        logging.exception("plan:funnel_failed")
        planner["execution_funnel"] = None
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
    zone_edge_context: dict | None = None,
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
    level_bounds = {
        str(level["id"]): (
            min(float(level["price"]), float(level.get("zone_high", level["price"]))),
            max(float(level["price"]), float(level.get("zone_high", level["price"]))),
        )
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

    if entry_low_id in level_bounds and entry_high_id in level_bounds:
        selected = (level_bounds[entry_low_id], level_bounds[entry_high_id])
        entry_low = min(bound[0] for bound in selected)
        entry_high = max(bound[1] for bound in selected)
        if abs(entry_low - entry_high) < 1e-9:
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
    # qwen_cached_entry hard traps). Softened for a two-day observation
    # window: log the condition but do not block ready->execution. Set
    # QWEN_LEVEL_ENTRY_GATES=1 to restore hard waits.
    # Safety gates are fail-closed in live operation. Explicitly setting 0 is
    # retained only for controlled research replays.
    level_gates_on = os.environ.get("QWEN_LEVEL_ENTRY_GATES", "1") != "0"
    acceptance_pad = 1.0
    if quote > 0:
        if side == "sell" and quote > entry_high + acceptance_pad:
            msg = (
                "Live price already accepted above the sell resistance zone; "
                "do not fade the bullish auction."
            )
            if level_gates_on:
                return wait(msg)
            logging.info("level gate soft-pass (not blocking): %s", msg)
        if side == "buy" and quote < entry_low - acceptance_pad:
            msg = (
                "Live price already accepted below the buy support zone; "
                "do not fade the bearish auction."
            )
            if level_gates_on:
                return wait(msg)
            logging.info("level gate soft-pass (not blocking): %s", msg)

    # Buy zone entirely above live price = buying into resistance.
    # Sell zone entirely below live price = selling into support.
    if quote > 0:
        if side == "buy" and entry_low > quote + 0.5:
            msg = (
                "Do not buy into resistance above live price; "
                "wait for pullback support or break-and-retest."
            )
            if level_gates_on:
                return wait(msg)
            logging.info("level gate soft-pass (not blocking): %s", msg)
        if side == "sell" and entry_high < quote - 0.5:
            msg = (
                "Do not sell into support below live price; "
                "wait for bounce to resistance or failed support hold."
            )
            if level_gates_on:
                return wait(msg)
            logging.info("level gate soft-pass (not blocking): %s", msg)

    planner_scenario = str(
        snapshot.get("planner_context", {}).get("session_plan_summary", {}).get(
            "active_scenario", ""
        )
        or ""
    ).strip().lower()
    if planner_scenario == "bullish" and side == "sell" and quote > entry_high:
        msg = (
            "Planner active_scenario is bullish; do not ready a counter-trend "
            "sell above the mapped resistance."
        )
        if level_gates_on:
            return wait(msg)
        logging.info("level gate soft-pass (not blocking): %s", msg)
    if planner_scenario == "bearish" and side == "buy" and quote < entry_low:
        msg = (
            "Planner active_scenario is bearish; do not ready a counter-trend "
            "buy below the mapped support."
        )
        if level_gates_on:
            return wait(msg)
        logging.info("level gate soft-pass (not blocking): %s", msg)

    # ── Optimal entry price from zone-edge analysis ────────────────────
    # Buy → enter at zone low (lowest possible price).
    # Sell → enter at zone high (highest possible price).
    # Falls back to zone edge if lifecycle modules didn't compute it.
    zec = zone_edge_context or {}
    optimal_entry = zec.get("optimal_entry_price")
    if optimal_entry is None:
        # Fallback: use the zone edge for the side.
        optimal_entry = entry_low if side == "buy" else entry_high
    optimal_entry = float(optimal_entry)
    if not entry_low <= optimal_entry <= entry_high:
        supplied = optimal_entry
        optimal_entry = entry_low if side == "buy" else entry_high
        logging.warning(
            "zone geometry repaired: optimal %.3f outside [%.3f, %.3f]; using %.3f",
            supplied, entry_low, entry_high, optimal_entry,
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
        "optimal_entry_price": optimal_entry,
        "zone_edge_context": zec,
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


# ---------------------------------------------------------------------------
# Idea lifecycle state machine — driven by Qwen response
# ---------------------------------------------------------------------------

# Minimum zone half-width when no data is available (XAUUSD default).
_FALLBACK_ZONE_HALF = 1.5


def _zone_bounds_from_data(
    zone_id: str,
    center: float,
    side: str,
    facts: dict,
) -> tuple[float, float]:
    """Derive zone lo/hi from real market data.

    Priority:
        1. execution_levels — fractal cluster zones already have zone_low /
           zone_high computed from the candles that formed the level.
        2. Average wick of candles that touched the level area — the wick
           tells you how far price pokes past a level before reversing.
           Only candles at that area count, not all candles.
        3. Fixed ±1.5 fallback.

    For sell (resistance): zone is centered at the level, expanded by the
    average upper wick of candles that reached up to that area.
    For buy (support): expanded by the average lower wick of candles that
    reached down to that area.
    """
    # 1. Try execution_levels — they carry real cluster bounds
    for lvl in facts.get("execution_levels") or []:
        if lvl.get("id") == zone_id:
            try:
                z_lo = float(lvl.get("lo") or lvl.get("zone_low") or 0)
                z_hi = float(lvl.get("hi") or lvl.get("zone_high") or 0)
                if z_hi - z_lo >= 0.5:
                    # Real zone width from fractal clustering
                    return z_lo, z_hi
            except (TypeError, ValueError):
                pass
            break

    # 2. Compute from candle wicks at the level area.
    #    Extract the timeframe from zone_id prefix (e.g. "H4_LIVE_H_..." → H4)
    tf_prefix = zone_id.split("_")[0] if "_" in zone_id else ""
    # Map level TF to the bars we have in recent_closed (slim format)
    tf_bar_key = {
        "M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30",
        "H1": "M15", "H4": "M15",  # for HTF levels, use M15 bars
        "D1": "M15",
    }.get(tf_prefix, "M5")
    bars = (facts.get("recent_closed") or {}).get(tf_bar_key) or []

    if bars:
        TOUCH_PROXIMITY = 5.0  # candle must come within 5pts of the level
        wicks: list[float] = []
        for bar in bars:
            h = float(bar.get("h") or bar.get("high") or 0)
            l = float(bar.get("l") or bar.get("low") or 0)
            o = float(bar.get("o") or bar.get("open") or 0)
            c = float(bar.get("c") or bar.get("close") or 0)
            if h == 0 or l == 0:
                continue

            if side == "sell":
                # Resistance zone: candles that reached up near the level
                if h >= center - TOUCH_PROXIMITY:
                    upper_wick = h - max(o, c)
                    if upper_wick > 0:
                        wicks.append(upper_wick)
            else:
                # Support zone: candles that reached down near the level
                if l <= center + TOUCH_PROXIMITY:
                    lower_wick = min(o, c) - l
                    if lower_wick > 0:
                        wicks.append(lower_wick)

        if wicks:
            avg_wick = sum(wicks) / len(wicks)
            # Zone extends by average wick on the rejection side,
            # small buffer on the other side
            half = max(avg_wick, 0.5)
            return center - half, center + half

    # 3. Fixed fallback
    return center - _FALLBACK_ZONE_HALF, center + _FALLBACK_ZONE_HALF


def _update_idea_lifecycle(review: dict, facts: dict) -> None:
    """Update trade idea state machine based on the Qwen entry response.

    Called after every model-produced entry decision. Drives the lifecycle
    through STALKING → AT_ZONE → ARMED → RESOLVED based on the model's
    execution_plan and the approach tracker's assessment.

    Rules:
        - status="ready" with a zone → create or transition idea to ARMED
        - status="wait" with identified zones → STALKING (approach tracking)
        - Active idea invalidated by model (price broke zone) → RESOLVED
        - Active idea superseded by new zone target → auto-resolved

    All mutations are on the module-level _IDEA_MANAGER / _APPROACH_TRACKER.
    """
    plan = review.get("execution_plan") or {}
    status = str(plan.get("status", "wait")).strip().lower()
    side = plan.get("side")
    confidence = int(review.get("confidence") or 0)

    # Extract the *target zone* from Qwen's response — NOT the full bracket.
    # For a sell the model is targeting resistance (entry_high level).
    # For a buy the model is targeting support (entry_low level).
    # The entry bracket (entry_low to entry_high) spans the whole range and
    # is too wide for approach tracking (often 30-40 pts on XAUUSD).
    entry_low_price = plan.get("entry_low") or plan.get("entry_low_price")
    entry_high_price = plan.get("entry_high") or plan.get("entry_high_price")
    entry_low_id = plan.get("entry_low_id", "")
    entry_high_id = plan.get("entry_high_id", "")

    # Pick the side-appropriate level as the tight target zone.
    # For sell → resistance level (entry_high). For buy → support (entry_low).
    if side == "sell" and entry_high_id:
        zone_id = entry_high_id
        try:
            center = float(entry_high_price or 0)
        except (TypeError, ValueError):
            center = 0.0
    elif side == "buy" and entry_low_id:
        zone_id = entry_low_id
        try:
            center = float(entry_low_price or 0)
        except (TypeError, ValueError):
            center = 0.0
    else:
        zone_id = ""
        center = 0.0

    # Get approach assessment from facts
    approach = facts.get("approach_context") or {}
    zone_scores = facts.get("zone_scores") or []

    if status == "ready" and side and zone_id and center > 0:
        # Derive zone bounds from real data:
        # 1. execution_levels already carry zone_low/zone_high from fractal
        #    clustering — use those when the level has real width.
        # 2. For point levels (width=0), compute average wick of candles
        #    that touched that area — the wick IS the rejection zone.
        lo, hi = _zone_bounds_from_data(
            zone_id, center, side, facts,
        )

        # Find zone score for this zone if available
        matched_score = {}
        for zs in zone_scores:
            if zs.get("zone_id") in (zone_id, entry_low_id, entry_high_id):
                matched_score = zs
                break

        active = _IDEA_MANAGER.active_idea
        if active and active.zone_id == zone_id and active.state.value != "armed":
            # Same zone, transition forward
            _IDEA_MANAGER.transition(
                active.idea_id, "armed",
                reason=f"model_ready_conf={confidence}",
            )
            logging.info(
                "lifecycle:idea_armed :: %s [%.1f-%.1f] side=%s conf=%d",
                zone_id, lo, hi, side, confidence,
            )
        elif not active or active.zone_id != zone_id:
            # New zone — create new idea (auto-supersedes old)
            idea = _IDEA_MANAGER.create_idea(
                zone_id=zone_id, side=side,
                zone_low=lo, zone_high=hi,
                # Lead with runtime-owned geometry. Qwen sometimes repeats an
                # older price in its summary; that prose must never make a new
                # mapped zone look like a position at the stale price.
                thesis=(
                    f"{side.title()} watch {zone_id} [{lo:.3f}-{hi:.3f}]. "
                    f"{str(review.get('summary', ''))[:100]}"
                ),
                zone_score=matched_score,
            )
            # Jump straight to ARMED since model said ready
            _IDEA_MANAGER.transition(
                idea.idea_id, "at_zone",
                reason="model_identified_zone",
            )
            _IDEA_MANAGER.transition(
                idea.idea_id, "armed",
                reason=f"model_ready_conf={confidence}",
            )
            logging.info(
                "lifecycle:idea_created_armed :: %s [%.1f-%.1f] side=%s conf=%d",
                zone_id, lo, hi, side, confidence,
            )

    elif status == "wait" and _IDEA_MANAGER.has_active:
        # Model says wait — check if we should maintain or invalidate idea
        active = _IDEA_MANAGER.active_idea
        reason_text = str(plan.get("reason", "")).lower()

        if "broke" in reason_text or "invalidat" in reason_text:
            # Zone broke — resolve the idea
            _IDEA_MANAGER.resolve(
                active.idea_id,
                outcome="invalidated",
                reason=f"model_wait:{reason_text[:80]}",
            )
            _APPROACH_TRACKER.reset()
            logging.info(
                "lifecycle:idea_invalidated :: %s reason=%s",
                active.zone_id, reason_text[:60],
            )
        elif approach.get("distance_trend") == "retreating" and approach.get("observation_count", 0) >= 3:
            # Price retreating from zone for multiple observations — expire
            _IDEA_MANAGER.resolve(
                active.idea_id,
                outcome="expired",
                reason="price_retreating_from_zone",
            )
            _APPROACH_TRACKER.reset()
            logging.info(
                "lifecycle:idea_expired :: %s retreating",
                active.zone_id,
            )
        else:
            # Still tracking — approach data was already updated in compact_entry_facts
            if active.state.value == "armed":
                # Was armed but model now says wait — downgrade back to at_zone
                _IDEA_MANAGER.transition(
                    active.idea_id, "at_zone",
                    reason=f"model_wait:{reason_text[:40]}",
                )
            logging.debug(
                "lifecycle:idea_stalking :: %s approach=%s",
                active.zone_id,
                approach.get("assessment", "unknown"),
            )

    elif status == "wait" and not _IDEA_MANAGER.has_active:
        # No active idea and model says wait — check if planner has zones to stalk
        planner_zones = (facts.get("planner") or {}).get("entry_zones") or []
        # side may be None on a wait plan — fall back to bias
        stalk_side = side or (
            review.get("bias") if review.get("bias") in ("buy", "sell") else None
        )
        if planner_zones and stalk_side:
            zone = planner_zones[0]
            try:
                lo = float(zone.get("lo") or zone.get("low") or zone.get("entry_low") or 0)
                hi = float(zone.get("hi") or zone.get("high") or zone.get("entry_high") or 0)
                z_id = str(zone.get("id") or zone.get("zone_id") or f"plan_{entry_low_id}")
            except (TypeError, ValueError):
                lo, hi, z_id = 0.0, 0.0, ""
            if lo > 0 and hi > 0 and z_id:
                _IDEA_MANAGER.create_idea(
                    zone_id=z_id, side=stalk_side,
                    zone_low=lo, zone_high=hi,
                    thesis=f"Session plan zone: {z_id}",
                )
                logging.info("lifecycle:idea_stalking_plan_zone :: %s", z_id)


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
    market_atr = None
    facts: dict = {}
    market = gold_market_open()

    if not market.get("open"):
        review = {
            "bias": "wait",
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
            "bias": "wait",
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
            "bias": "wait",
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
            entry_cache, decision_levels, planner_context, symbol,
            idea_manager=_IDEA_MANAGER,
            approach_tracker=_APPROACH_TRACKER,
        )
        log_step(
            "context_ready", "passed", symbol=symbol,
            price=(facts.get("quote") or {}).get("bid"),
            quote_age_ms=(facts.get("quote") or {}).get("age_ms"),
            cache_epochs=facts.get("epochs"),
            active_idea=(facts.get("active_idea_context") or {}).get("watching_zone"),
            approach=(facts.get("approach_context") or {}).get("assessment"),
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
            # ENTRY FACTS are ~20KB. 4096 tokens can truncate the contract at
            # the beginning, which produced confidence=0 / malformed ready
            # responses because Qwen never saw the governing instructions.
            num_ctx=8192,
            format_schema=entry_decision_schema(
                entry_cache, decision_levels, facts
            ),
        )
        decision_wall_seconds = round(time.monotonic() - decision_started, 3)
        decision_duration_ns = result.get("total_duration")
        market_atr = result.get("market_atr")
        logging.info(
            "Qwen entry decision took %.2fs prompt_bytes=%d (model total_duration=%sns)",
            decision_wall_seconds,
            prompt_bytes,
            decision_duration_ns,
        )
        raw_response = result.get("response", "{}")
        review = json.loads(raw_response)
        correction_reason = qwen_contract_correction_reason(review)
        if correction_reason:
            correction_prompt = build_qwen_correction_prompt(
                facts, review, correction_reason
            )
            logging.warning("Qwen contract correction requested: %s", correction_reason)
            correction = ollama_generate(
                correction_prompt, timeout=None, num_predict=768, num_ctx=4096,
                format_schema=entry_decision_schema(entry_cache, decision_levels, facts),
            )
            decision_duration_ns = int(decision_duration_ns or 0) + int(
                correction.get("total_duration") or 0
            )
            prompt_text = correction_prompt
            raw_response = correction.get("response", "{}")
            review = json.loads(raw_response)
            log_step(
                "qwen_contract_correction", "completed", symbol=symbol,
                price=(facts.get("quote") or {}).get("bid"),
                quote_age_ms=(facts.get("quote") or {}).get("age_ms"),
                detail=correction_reason, bias=review.get("bias"),
                confidence=review.get("confidence"),
                plan_status=(review.get("execution_plan") or {}).get("status"),
            )
        log_step(
            "qwen_response", "received", symbol=symbol,
            price=(facts.get("quote") or {}).get("bid"),
            quote_age_ms=(facts.get("quote") or {}).get("age_ms"),
            bias=review.get("bias"), confidence=review.get("confidence"),
            plan_status=(review.get("execution_plan") or {}).get("status"),
            detail=(review.get("execution_plan") or {}).get("reason"),
        )
        if _has_legacy_dual_assessment(review.get("summary")):
            # v004 may reproduce wording learned by an older contract. Never
            # persist or recycle it as a thesis under the directional contract.
            review["summary"] = "Directional bias unresolved."
        provenance_failures = validate_entry_provenance(review, entry_cache)
        snapshot["qwen_evidence_ids"] = list(review.get("evidence_ids") or [])

        # Confidence is an observed model output, not permission that runtime
        # may manufacture. Keep the raw value: the contradiction guard below
        # turns ready+zero into a wait instead of promoting it into a trade.

        # 2026-08-10 guard: contract v1.9 made the model emit status="ready"
        # alongside confidence=0 and a directional bias. That contradiction
        # occurred 72 times in two hours and nothing detected it -- the plan was
        # silently downgraded to a wait and trading simply stopped. Surface it
        # loudly with a stable code so a contract regression cannot hide again.
        contradiction = entry_policy.check_legacy_contradiction(review)
        # Checked even when confidence is fine: the two claims are independent.
        # A ready plan whose own reason reads "entry_trigger_missing" at
        # confidence 62 passes every confidence gate there is.
        if not contradiction:
            contradiction = entry_policy.check_ready_reason_contradiction(review)
        if contradiction:
            # Alarm only on the codes that mean something reached, or could
            # reach, the broker wrongly. Sub-threshold confidence is the model
            # doing its job -- it is trained for high-conviction entries and is
            # saying it has none. Logged at ERROR that came to 394 lines in one
            # day, which is how the real regression gets scrolled past.
            try:
                _conf = float(review.get("confidence") or 0)
            except (TypeError, ValueError):
                _conf = 0.0
            log = (
                logging.error
                if entry_policy.is_contract_regression(contradiction, _conf)
                else logging.info
            )
            log(
                "%s :: status=ready, confidence=%s, bias=%s, plan_reason=%r",
                contradiction,
                review.get("confidence"),
                review.get("bias"),
                (review.get("execution_plan") or {}).get("reason"),
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
                "reason": wait_reason_for(contradiction, review),
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
                zone_edge_context=facts.get("zone_edge_context"),
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
        # Qwen can take more than a minute locally. Re-read the cache after the
        # answer and prevent a READY decision from trading a materially moved
        # market. WAIT assessments remain useful observations and are not
        # rewritten merely because another M1 candle closed.
        post_qwen_cache = latest_entry_context(symbol)
        snapshot_freshness = decision_snapshot_freshness(facts, post_qwen_cache)
        review["decision_freshness"] = snapshot_freshness
        if (
            review["execution_plan"].get("status") == "ready"
            and not snapshot_freshness.get("fresh", False)
        ):
            stale_ready = dict(review["execution_plan"])
            review["execution_plan"] = {
                "status": "wait",
                "reason": "stale_decision_snapshot; refresh current zone and response",
                "reason_code": "entry:stale_decision_snapshot",
            }
            provenance_failures.append("entry:stale_decision_snapshot")
            logging.warning(
                "STALE_RECOVERY component=qwen_decision action=ready_to_wait "
                "side=%s drift=%s max=%s source_m1=%s current_m1=%s",
                stale_ready.get("side"),
                snapshot_freshness.get("price_drift"),
                snapshot_freshness.get("maximum_drift"),
                snapshot_freshness.get("source_closed_m1"),
                snapshot_freshness.get("current_closed_m1"),
            )
            log_step(
                "freshness_recovery", "recovered", symbol=symbol,
                price=snapshot_freshness.get("current_price"),
                detail="entry:stale_decision_snapshot",
                source_price=snapshot_freshness.get("source_price"),
                price_drift=snapshot_freshness.get("price_drift"),
            )
        review["entry_validation_failures"] = provenance_failures
        _stamp_regime_target_mode(review, facts)

        # -- Trade idea lifecycle update from Qwen response --
        try:
            _update_idea_lifecycle(review, facts)
        except Exception:
            logging.debug("lifecycle:update_failed", exc_info=True)

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
        # Minted BEFORE the decision is written, and handed to both writes.
        # This single line is what makes a trade traceable back to the prompt
        # that produced it; without it, proposal_id was None on every one of
        # the 3,703 entry decisions on record and no training pair could ever
        # be built from live trading. See new_proposal_id().
        proposal_id = new_proposal_id()
        append_qwen_decision(
            decision_type="entry",
            symbol=symbol,
            price=snapshot.get("price"),
            prompt_text=prompt_text,
            raw_response=raw_response,
            parsed=review,
            model=snapshot.get("model") or MODEL,
            duration_ns=decision_duration_ns,
            proposal_id=proposal_id,
            atr=market_atr,
            context={
                "cache_status": entry_cache.get("status"),
                "session": entry_cache.get("session"),
                "execution_plan": review.get("execution_plan"),
                "prompt_bytes": len(prompt_text.encode("utf-8")) if prompt_text else 0,
                "entry_prompt_mode": "compact_trade_quality_v1",
                "wait_signature": wait_signature or None,
                "model_called": model_called,
                **build_manifest.stamp(),
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
            proposal_id=proposal_id,
        )
        assert proposal["proposal_id"] == proposal_id, (
            "decision and proposal must share one id or the chain is broken"
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
        "proposal_id": proposal_id,
        "proposal_price": snapshot.get("price"),
        "execution_plan": review["execution_plan"],
        "wait_deduped": skip_wait_audit,
    }
    write_json_atomic(ENTRY_STATE_FILE, entry_state)
    try:
        _save_lifecycle_state()
    except Exception:
        logging.debug("lifecycle:save_failed", exc_info=True)
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
        if path == "/trade-ideas":
            query = parse_qs(parsed.query)
            try:
                min_confidence = float(query.get("min_confidence", ["50"])[0])
            except ValueError:
                min_confidence = 50.0
            try:
                days_back = int(query.get("days", ["2"])[0])
            except ValueError:
                days_back = 2
            try:
                limit = int(query.get("limit", ["300"])[0])
            except ValueError:
                limit = 300
            ready_only = str(query.get("ready_only", ["0"])[0]).lower() in {
                "1",
                "true",
                "yes",
            }
            payload = json.dumps(
                list_trade_ideas(
                    min_confidence=min_confidence,
                    days_back=max(0, min(days_back, 14)),
                    ready_only=ready_only,
                    limit=max(1, min(limit, 1000)),
                )
            ).encode("utf-8")
            self._headers()
            self.wfile.write(payload)
            return
        if path == "/lifecycle":
            payload = json.dumps({
                "active_idea": _IDEA_MANAGER.active_idea_for_facts(),
                "prior_context": _IDEA_MANAGER.prior_idea_context(),
                "history": [h.to_dict() for h in _IDEA_MANAGER.history[-5:]],
                "approach": (
                    _APPROACH_TRACKER.snapshot().to_dict()
                    if _APPROACH_TRACKER.active else {}
                ),
            }).encode("utf-8")
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
    # Lifecycle fields (prior_idea_context, zone_scores, approach_context)
    # add ~1600 bytes worst case. num_ctx=4096 tokens ≈ 8KB at 2 chars/token.
    assert prompt_bytes < 8000, prompt_bytes
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
    # Restore trade idea lifecycle state from disk
    try:
        _load_lifecycle_state()
        if _IDEA_MANAGER.has_active:
            logging.info(
                "lifecycle:restored active_idea=%s state=%s",
                _IDEA_MANAGER.active_idea.zone_id,
                _IDEA_MANAGER.active_idea.state,
            )
        logging.info("lifecycle:restored history_count=%d", len(_IDEA_MANAGER.history))
    except Exception:
        logging.exception("lifecycle:restore_failed")
    # Evict any previous qwen-trading-* left pinned in VRAM. warm_model() pins
    # with keep_alive=-1, so a model switch otherwise leaves BOTH resident and
    # Ollama starts returning HTTP 500 on every call (2026-08-10 incident).
    try:
        evicted = unload_stale_models()
        if evicted:
            logging.info("freed VRAM by evicting: %s", ", ".join(evicted))
    except Exception:
        logging.exception("model:stale_eviction_failed")
    # Calendar refresh runs on its own clock, off the decision path. A network
    # call inside the entry loop would be a new way for entries to stall, and
    # entry latency is already the binding constraint on this system.
    news_refreshed_at = 0.0
    NEWS_REFRESH_SECONDS = 3600.0
    try:
        news_blackout.refresh_calendar()
        news_refreshed_at = time.monotonic()
        for event in news_blackout.upcoming(3):
            logging.info(
                "upcoming blackout: %s %s %s at %s (%d min)",
                event["country"], event["impact"], event["title"],
                event["event_time_utc"][11:16], event["minutes_away"],
            )
    except Exception:
        logging.exception("news:initial_refresh_failed")

    start_dashboard_server()
    while True:
        started = time.monotonic()
        try:
            if started - news_refreshed_at >= NEWS_REFRESH_SECONDS:
                news_blackout.refresh_calendar()
                news_refreshed_at = started
            market = gold_market_open()
            sync_model_residency(market)
            if not market.get("open"):
                logging.info(
                    "Market closed (%s); Qwen unloaded/idle — skip entry cycle",
                    market.get("reason"),
                )
            elif news_blackout_active():
                # Entries only. A position already open keeps being managed
                # through the release -- see the note in news_blackout_active().
                pass
            elif not gpu_ready_for_entry():
                # Deliberately skip the cycle rather than call the model.
                #
                # On CPU an entry decision takes 190-455s against a 60s
                # proposal TTL, so the answer is guaranteed to arrive after the
                # proposal it belongs to has expired. Making the call anyway
                # burns five minutes, writes a proposal nobody can act on, and
                # blocks the next cycle behind the model lock -- which is how
                # 106 proposals produced 4 fills without a single error.
                #
                # Skipping keeps the process alive, the alarm visible, and the
                # logs honest about why nothing is trading.
                pass
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
