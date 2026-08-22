"""Single-position MT5 demo entry executor with an enforced demo-account lock."""

import argparse
import json
import logging
import msvcrt
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5

import build_manifest
import live_mapped_levels
import trade_geometry
from instrument_config import XAUUSD, instrument_for
from runtime_config import PRIMARY_MARKET_SYMBOL
from trade_step_log import log_step
from tick_data_archive import append_tick_record


APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"
QWEN_MAGIC = 26072401
QWEN_COMMENT_PREFIX = "QWEN"
EXECUTION_LOCK_FILE = APP_DIR / "paper-executor.lock"
MONITOR_INTERVAL_SECONDS = 1.0
# No longer used to gate entry timing (see BestPriceRangeTracker docstring,
# 2026-08-06) -- kept only so nothing else in this file breaks if it's
# still referenced by a stale caller or an old log-replay tool.
BEST_PRICE_MINIMUM_OBSERVATION_SECONDS = 0.25
MIN_ENTRY_CONFIDENCE = 51
# Legacy fixed broker bracket. Retained as the fallback path and as the
# reference the entry guard validates against -- see broker_bracket_from_plan.
INITIAL_STOP_DISTANCE = 3.0
INITIAL_TAKE_PROFIT_DISTANCE = 5.0

# ── Optimal entry price gate ────────────────────────────────────────────
# Instead of filling anywhere inside the zone, wait for price to reach
# within OPTIMAL_ENTRY_TOLERANCE_PTS of the optimal zone edge.
# Buy → optimal = zone low, fill only when price <= optimal + tolerance.
# Sell → optimal = zone high, fill only when price >= optimal - tolerance.
# This ensures we buy at the bottom and sell at the top of the zone.
OPTIMAL_ENTRY_TOLERANCE_PTS = 0.5  # allow 0.5pt slippage from optimal edge
# A mapped zone is slower-lived than its M1 trigger.  The executor may wait for
# price to revisit structure, but never indefinitely: a bounded window prevents
# an old synchronous execution from hiding a newer Qwen plan.
ZONE_ARMED_MAX_SECONDS = max(
    60, int(os.environ.get("QWEN_ZONE_ARMED_MAX_SECONDS", "900"))
)

# Stage 3: place the stop beyond the structural invalidation and let size absorb
# the distance. Set QWEN_STRUCTURAL_BRACKET=0 to fall back to the flat $3/$5.
STRUCTURAL_BRACKET_ENABLED = os.environ.get("QWEN_STRUCTURAL_BRACKET", "1") != "0"

# RESEARCH POLICY (2026-08-20): keep the protected fallback enabled by default
# during the next few months of research.  A structural path can lose because
# it is wrong in a different way; retaining the fixed bracket gives us a safe,
# comparable control sample instead of prematurely optimizing around one loss
# direction.  This is research behaviour, not proof of positive expectancy.
# Set QWEN_ENFORCE_HTF_MICRO_BRACKET=1 when the collected evidence supports
# enforcing the stricter HTF-only rule.
ENFORCE_HTF_MICRO_BRACKET = (
    os.environ.get("QWEN_ENFORCE_HTF_MICRO_BRACKET", "0") == "1"
)

# Geometry verdicts that *can* refuse entry rather than degrading to $3/$5.
#
# 2026-08-11: default OFF for a two-day observation window. Level-distance /
# reward:risk rejects were skipping most ready ideas (HTF min TP, R:R < 1.2,
# wrong-side target). We need live fills to learn what to block; set
# QWEN_SKIP_ON_GEOMETRY=1 to restore the hard skip list.
_GEOMETRY_SKIP_CANDIDATES = frozenset({
    trade_geometry.GeometryReason.REWARD_RISK_TOO_LOW,
    trade_geometry.GeometryReason.STOP_TOO_WIDE,
    trade_geometry.GeometryReason.INVALIDATION_WRONG_SIDE,
    trade_geometry.GeometryReason.TARGET_WRONG_SIDE,
    trade_geometry.GeometryReason.SIZE_BELOW_MINIMUM,
})
SKIP_ON_GEOMETRY_REJECTION = (
    _GEOMETRY_SKIP_CANDIDATES
    if os.environ.get("QWEN_SKIP_ON_GEOMETRY", "0") == "1"
    else frozenset()
)


GEOMETRY_OBSERVATION_LOG = "geometry-observations"


def record_geometry_observation(args, bracket, order_price: float) -> None:
    """Record an entry geometry would have refused, for later scoring.

    Written during the observation window (QWEN_SKIP_ON_GEOMETRY=0) so that the
    decision to enforce or relax the gate can be made on realised P&L. Keyed by
    proposal_id so it joins to the close in paper-runner.log.

    Deliberately non-fatal: an observation that fails to write must never stop a
    trade.
    """
    try:
        append_event(
            {
                "event": "geometry_observation",
                "proposal_id": getattr(args, "proposal_id", None),
                "created_at_utc": utc_now(),
                "would_refuse": True,
                "reason_code": bracket.reason_code,
                "detail": bracket.detail,
                "side": getattr(args, "side", None),
                "order_price": round(float(order_price), 3),
                "structural_stop": getattr(args, "management_reference_sl", None),
                "structural_target": getattr(args, "management_reference_tp", None),
                "frame": getattr(args, "structure_timeframe", None),
                "would_be_stop_distance": bracket.stop_distance or None,
                "would_be_reward_risk": bracket.reward_risk or None,
                "taken_on": "fixed_3_5",
            }
        )
    except Exception:
        logging.exception("geometry:observation_record_failed")


class GeometryRejection(RuntimeError):
    """Raised when structure says this entry is not worth taking."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"{reason_code}: {detail}")
        self.reason_code = reason_code
        self.detail = detail
INITIAL_SAFETY_DISTANCE = INITIAL_TAKE_PROFIT_DISTANCE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dated_log_path(base_name: str) -> Path:
    """Today's log file, e.g. paper-executions-2026-08-06.jsonl.

    Computed fresh on every call (never cached) so a process that stays
    running across midnight rolls over to a new file automatically, the
    same way reviewer.py already rotates reviews-*.jsonl by date.
    """
    return LOG_DIR / f"{base_name}-{datetime.now():%Y-%m-%d}.jsonl"


def _dated_log_files(base_name: str, days_back: int = 1) -> list[Path]:
    """Existing dated files for `base_name`, today first then earlier days.

    A proposal or position from just before midnight can still be looked
    up just after it, so id-lookups need to see yesterday's file too, not
    only today's.
    """
    today = datetime.now().date()
    paths = []
    for offset in range(days_back + 1):
        day = today - timedelta(days=offset)
        path = LOG_DIR / f"{base_name}-{day:%Y-%m-%d}.jsonl"
        if path.exists():
            paths.append(path)
    return paths


# Per-tick heartbeat rows go to their own family.
#
# 2026-08-11: mt5_execution_monitor was 52,986 of 54,809 execution rows (96.7%)
# and 36.1 MB of 37.4 MB. Every analysis, report and training script paid a 30x
# parsing cost to reach the 3.3% of rows that record a decision, and the logs
# had grown to 346 MB with no retention.
#
# The tick path is NOT discarded -- trade management needs MFE, MAE, giveback
# and time-to-peak. It is simply not interleaved with the decisions.
PATH_EVENTS = frozenset({"mt5_execution_monitor"})
PATH_LOG = "paper-path"
EXECUTION_LOG = "paper-executions"
_EXECUTION_SYMBOLS: dict[str, str] = {}


def append_event(event: dict) -> None:
    """Route one execution event to the decision log or the path log.

    2026-08-11 -- why this cannot raise
    -----------------------------------
    This is called once per second from the monitor loop that watches a LIVE
    position. On 2026-08-11 an unregistered log family made it raise KeyError
    on every tick; the exception left the monitor loop, aborted the run, and
    five positions were left open with no close record while the runner blocked
    every new proposal on a position it thought was still there.

    The trade-off is deliberate and one-sided. A failed write costs one row --
    and the row usually survives anyway, because the runtime log is written
    before the archive. A raised exception costs an unmanaged position with
    real money against it. Recording a trade is never more important than
    managing one.

    Failures are logged with a full traceback, so this hides nothing; it only
    refuses to let bookkeeping kill trading.
    """
    event = dict(event)
    execution_id = event.get("execution_id")
    symbol = event.get("symbol") or (event.get("plan") or {}).get("symbol")
    if execution_id and symbol:
        _EXECUTION_SYMBOLS[str(execution_id)] = str(symbol)
    elif execution_id:
        symbol = _EXECUTION_SYMBOLS.get(str(execution_id))
    if symbol:
        event["symbol"] = symbol
    base = PATH_LOG if event.get("event") in PATH_EVENTS else EXECUTION_LOG
    try:
        append_tick_record(base, event)
    except Exception:
        logging.exception(
            "execution event write FAILED (base=%s event=%s execution_id=%s). "
            "Trading continues; this record is lost.",
            base, event.get("event"), event.get("execution_id"),
        )
    if base == EXECUTION_LOG:
        try:
            from market_intelligence.execution_events import append_execution_event
            append_execution_event(event)
        except Exception:
            logging.warning("execution graph memory unavailable", exc_info=True)
    if execution_id and event.get("event") in {"mt5_execution_closed", "mt5_execution_skipped"}:
        _EXECUTION_SYMBOLS.pop(str(execution_id), None)


def load_proposal(proposal_id: str) -> dict:
    files = _dated_log_files("paper-proposals")
    if not files:
        raise RuntimeError("No paper proposal log exists.")
    for path in files:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            proposal = json.loads(line)
            if proposal.get("proposal_id") == proposal_id:
                return proposal
    raise RuntimeError(f"Unknown proposal ID: {proposal_id}")


def validate_plan(args, proposal: dict) -> None:
    if proposal.get("mode") != "paper-research":
        raise RuntimeError("Proposal is not marked paper-research.")
    if not proposal.get("market", {}).get("connected"):
        raise RuntimeError("Proposal was recorded while MT5 was disconnected.")
    qwen = proposal.get("qwen")
    qwen = qwen if isinstance(qwen, dict) else {}
    plan = qwen.get("execution_plan")
    plan = plan if isinstance(plan, dict) else {}
    try:
        confidence = float(qwen.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_ENTRY_CONFIDENCE:
        raise RuntimeError(
            f"Qwen confidence must be at least {MIN_ENTRY_CONFIDENCE}."
        )
    if plan.get("decision_confidence") != round(confidence):
        raise RuntimeError("Plan confidence provenance does not match Qwen output.")
    if plan.get("side") != args.side:
        raise RuntimeError("Plan side does not match executor arguments.")
    if args.entry_low > args.entry_high:
        raise RuntimeError("entry-low must be less than or equal to entry-high.")
    if args.side == "buy":
        if not args.stop_loss < args.entry_low:
            raise RuntimeError("Buy stop-loss must be below the entry zone.")
        if not args.take_profit > args.entry_high:
            raise RuntimeError("Buy take-profit must be above the entry zone.")
    else:
        if not args.stop_loss > args.entry_high:
            raise RuntimeError("Sell stop-loss must be above the entry zone.")
        if not args.take_profit < args.entry_low:
            raise RuntimeError("Sell take-profit must be below the entry zone.")
    if args.buckets != 1:
        raise RuntimeError("Single-position mode requires exactly one entry.")
    if args.volume <= 0:
        raise RuntimeError("volume must be positive.")
    if args.signal_timeframe not in ("M1", "M5"):
        raise RuntimeError("Demo entries must be generated from M1 or M5.")
    if abs(float(args.stop_price_distance) - INITIAL_STOP_DISTANCE) > 1e-9:
        raise RuntimeError(
            f"stop-price-distance must be the fixed {INITIAL_STOP_DISTANCE} entry bracket."
        )


def fill_price(tick, side: str) -> float:
    return float(tick.ask if side == "buy" else tick.bid)


def close_price(tick, side: str) -> float:
    return float(tick.bid if side == "buy" else tick.ask)


def inside_entry_zone(price: float, low: float, high: float) -> bool:
    return low <= price <= high


def entry_location(
    side: str,
    price: float,
    low: float,
    high: float,
    stop_loss: float | None = None,
) -> str:
    """Classify live quote vs the approved S/R entry band.

    - inside_zone: within [low, high]
    - favorable_outside: still on the approach side of the zone (buy above high
      waiting to tag support; sell below low waiting to tag resistance)
    - past_stop: already through invalidation — never enter
    - unfavorable_outside: accepted through the zone (buy below support, sell
      above resistance) — do not fade acceptance
    """
    if side == "buy":
        if stop_loss is not None and price <= float(stop_loss):
            return "past_stop"
        if price < low:
            return "unfavorable_outside"
        if price > high:
            return "favorable_outside"
        return "inside_zone"
    if stop_loss is not None and price >= float(stop_loss):
        return "past_stop"
    if price > high:
        return "unfavorable_outside"
    if price < low:
        return "favorable_outside"
    return "inside_zone"


def entry_price_allowed(
    side: str,
    price: float,
    low: float,
    high: float,
    stop_loss: float | None = None,
) -> bool:
    """True only when price is inside the approved hunt/entry band.

    2026-08-13 — Context → Hunt → Arm: filling on ``favorable_outside`` let
    sells fire below a resistance hunt zone (structure-low fills while the
    plan's band was higher). Approach side is still classified for logs, but
    execution waits until price is actually in-band (learning teaches the same
    wait via missing_fact=at_entry_location).
    """
    return entry_location(side, price, low, high, stop_loss) == "inside_zone"


def latest_closed_m1_bar(symbol: str) -> dict | None:
    """Last completed M1 timing bar from MT5.

    Direction, zone, target and invalidation are already fixed upstream. M1
    therefore decides only the execution moment; it never rewrites structure.
    Waiting for an M5 close here routinely enters after the zone response is
    exhausted.
    """
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, 1)
    if rates is None or len(rates) < 1:
        return None
    rate = rates[-1]
    return {
        "open": float(rate["open"]),
        "high": float(rate["high"]),
        "low": float(rate["low"]),
        "close": float(rate["close"]),
    }


def latest_closed_m5_bar(symbol: str) -> dict | None:
    """Compatibility helper for callers that explicitly need M5 context."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 1, 1)
    if rates is None or len(rates) < 1:
        return None
    rate = rates[-1]
    return {
        "open": float(rate["open"]),
        "high": float(rate["high"]),
        "low": float(rate["low"]),
        "close": float(rate["close"]),
    }


def entry_fill_ready(
    side: str,
    price: float,
    low: float,
    high: float,
    stop_loss: float | None,
    closed_m1: dict | None,
    optimal_entry_price: float | None = None,
) -> tuple[bool, str]:
    """Inside the hunt band, near its optimal edge, after a closed M1 failure.

    M1 is permitted only because upstream has already committed direction,
    mapped the zone, and supplied structural invalidation/target. It times that
    plan; it does not promote an M1 move into higher-timeframe structure.

    2026-08-18: added optimal entry price gate. Instead of filling
    anywhere inside the zone, wait for price to reach within tolerance
    of the zone edge (buy at the bottom, sell at the top). This is the
    core quality-of-entry improvement — a human trader waits for price
    to reach the level, not the middle of the range.
    """
    location = entry_location(side, price, low, high, stop_loss)
    if location != "inside_zone":
        return False, location
    if not live_mapped_levels.m1_failure_for_entry(side, low, high, closed_m1):
        return False, "inside_zone_waiting_m1_failure"

    # ── Optimal price gate ───────────────────────────────────────────
    # Brooks: after a valid closed failure at the edge, enter while the signal
    # remains actionable; demanding the exact extreme can miss the response.
    # Restrict fills to the favorable outer half of the zone.
    if optimal_entry_price is not None:
        tol = OPTIMAL_ENTRY_TOLERANCE_PTS
        midpoint = (low + high) / 2.0
        buy_limit = max(optimal_entry_price + tol, midpoint)
        sell_limit = min(optimal_entry_price - tol, midpoint)
        if side == "buy" and price > buy_limit:
            return False, "inside_zone_waiting_optimal_buy_low"
        if side == "sell" and price < sell_limit:
            return False, "inside_zone_waiting_optimal_sell_high"

    return True, "armed_m1_failure_at_optimal"


def pre_fill_zone_cancellation(
    side: str,
    price: float,
    low: float,
    high: float,
    stop_loss: float,
    take_profit: float,
    closed_m1: dict | None,
) -> str | None:
    """Return why a persistent zone is no longer tradeable.

    Zone lifetime and trigger lifetime are intentionally separate.  A later
    revisit is allowed, but it must not enter after the thesis invalidated, its
    target already traded, or a completed M1 candle accepted through the zone.
    """
    if side == "buy":
        if price <= stop_loss:
            return "zone_invalidated_at_stop"
        if price >= take_profit:
            return "target_reached_without_fill"
        if closed_m1 is not None and float(closed_m1["close"]) < low:
            return "zone_accepted_through_on_m1"
    else:
        if price >= stop_loss:
            return "zone_invalidated_at_stop"
        if price <= take_profit:
            return "target_reached_without_fill"
        if closed_m1 is not None and float(closed_m1["close"]) > high:
            return "zone_accepted_through_on_m1"
    return None


def remaining_signal_seconds(created_at: datetime, now: datetime, ttl: float) -> float:
    return ttl - (now - created_at).total_seconds()


def average_fill_price(fills: list[dict]) -> float:
    total_volume = sum(float(fill["volume"]) for fill in fills)
    return (
        sum(float(fill["price"]) * float(fill["volume"]) for fill in fills)
        / total_volume
    )


def favorable_price_move(mark: float, average_entry: float, side: str) -> float:
    return mark - average_entry if side == "buy" else average_entry - mark


class BestPriceRangeTracker:
    """Enter immediately on the first fresh allowed tick.

    Allowed means inside Qwen's approved hunt/entry band only.
    Favorable approach (buy above support / sell below resistance) waits
    until price tags the band — hunt step. Through the zone or past stop
    never enters.

    2026-08-06 change: this used to wait up to `observation_seconds` (2s)
    hunting for a small retrace before entering, and if nothing retraced it
    would accept whatever price was live once that timer ran out -- with no
    check on how far that price had drifted from the best one seen. On a
    fast tape that meant paying deep into the bad end of Qwen's approved
    range (e.g. approved 82-91, filled at 89) purely because the clock ran
    out, not because 89 was actually the best available. `observation_seconds`
    and `retrace_distance` are kept as constructor/CLI arguments -- and are
    still recorded in the logged proposal `plan` for audit continuity -- but
    no longer gate the entry decision. The first fresh allowed tick fires
    immediately. `best_seen` is still tracked and reported purely for
    observability (how the actual fill compared to the best price available
    in the brief window before entry), not as a trigger condition.
    """

    def __init__(
        self,
        side: str,
        observation_seconds: float,
        retrace_distance: float,
    ) -> None:
        self.side = side
        self.observation_seconds = max(0.0, float(observation_seconds))
        self.retrace_distance = max(0.0, float(retrace_distance))
        self.first_seen: float | None = None
        self.best_seen: float | None = None
        self.best_seen_at: float | None = None
        self.observations = 0

    def observe(
        self,
        price: float,
        now_monotonic: float,
        *,
        inside_range: bool,
        signal_seconds_left: float,
        poll_seconds: float,
        location: str = "inside_zone",
    ) -> dict:
        if not inside_range:
            return {
                "enter": False,
                "reason": (
                    "past_stop"
                    if location == "past_stop"
                    else "outside_entry_range"
                ),
                "location": location,
            }
        self.observations += 1
        if self.first_seen is None:
            self.first_seen = now_monotonic
            self.best_seen = float(price)
            self.best_seen_at = now_monotonic
        improved = (
            price < self.best_seen
            if self.side == "buy"
            else price > self.best_seen
        )
        if improved:
            self.best_seen = float(price)
            self.best_seen_at = now_monotonic
        elapsed = now_monotonic - self.first_seen
        retrace = (
            float(price) - float(self.best_seen)
            if self.side == "buy"
            else float(self.best_seen) - float(price)
        )
        reason = (
            "favorable_outside_zone_entry"
            if location == "favorable_outside"
            else "immediate_zone_entry"
        )
        return {
            "enter": True,
            "reason": reason,
            "location": location,
            "best_price": self.best_seen,
            "current_price": float(price),
            "retrace_distance": round(retrace, 6),
            "observation_seconds": round(elapsed, 3),
            "observations": self.observations,
        }


def execution_comment(execution_id: str) -> str:
    return f"{QWEN_COMMENT_PREFIX}_{execution_id[-8:]}"


def owned_positions(symbol: str, execution_id: str):
    expected_comment = execution_comment(execution_id)
    positions = mt5.positions_get(symbol=symbol) or ()
    return tuple(
        position
        for position in positions
        if position.magic == QWEN_MAGIC
        and str(position.comment) == expected_comment
    )


# A position vanishes from positions_get the instant the broker accepts the
# close, but the closing DEAL lands in history a moment later. Read history in
# that gap and you see only the entry deal.
EXIT_SETTLE_TIMEOUT_SECONDS = 5.0
EXIT_SETTLE_POLL_SECONDS = 0.25


def manager_closed_position(position_ids: set[int]) -> dict | None:
    """The manager's own close decision for this position, if it made one.

    Attribution must not depend on the broker preserving our order comment.
    The manager writes every close decision to qwen-decisions-*.jsonl with the
    position id; that record is ours, it cannot be stripped in transit, and it
    carries the reasoning. Comments are the fast path, this is the truth.
    """
    for path in _dated_log_files("qwen-decisions"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("mt5_position_id") not in position_ids:
                continue
            parsed = record.get("parsed") or {}
            if str(parsed.get("action", "")).lower() in ("close", "exit"):
                return record
    return None


def realized_execution_outcome(fills: list[dict], since: datetime) -> dict:
    """Read authoritative MT5 deal P&L after the managed position disappears.

    2026-08-11 -- why this waits, and why it consults the manager
    ------------------------------------------------------------
    Seven closes were recorded as `external_position_close` with gross_pnl
    exactly 0.00 and costs exactly -3.50. That pattern is not a trade that
    earned nothing: it is the ENTRY deal's commission and nothing else. The
    position had left positions_get but its closing deal had not yet reached
    history, so this function summed a single deal and reported the result as
    final. The recorded P&L for those trades was wrong -- not merely
    mislabelled -- and the manager could learn nothing from them.

    Two fixes:

      1. Wait for the exit deal to settle instead of reading the gap.
      2. Attribute the close from the manager's own decision record when the
         broker did not preserve our comment. A close the manager performed is
         the manager's close; calling it external hides the manager's own work
         from the record it is supposed to learn from.

    If the exit deal never appears, say so with a distinct reason rather than
    reporting a confident zero. A trade with unknown P&L must be visible as
    unknown, because a false zero silently drags every average toward nothing.
    """
    position_ids = {int(fill["order"]) for fill in fills}

    deadline = time.monotonic() + EXIT_SETTLE_TIMEOUT_SECONDS
    while True:
        deals = mt5.history_deals_get(since, datetime.now(timezone.utc)) or ()
        matched = [deal for deal in deals if int(deal.position_id) in position_ids]
        exits = [deal for deal in matched if deal.entry != mt5.DEAL_ENTRY_IN]
        if exits or time.monotonic() >= deadline:
            break
        time.sleep(EXIT_SETTLE_POLL_SECONDS)

    comments = [str(deal.comment) for deal in exits]
    manager_decision = None
    if not exits:
        # Nothing settled inside the window. Report the gap honestly.
        reason = "exit_deals_unsettled"
        logging.error(
            "exit deals never settled for positions %s within %.1fs; "
            "P&L for this trade is INCOMPLETE and must not be treated as zero",
            sorted(position_ids),
            EXIT_SETTLE_TIMEOUT_SECONDS,
        )
    elif any("QWEN_MGR_CLOSE" in comment for comment in comments):
        reason = "qwen_confirmed_close"
    elif any(comment.startswith("[sl") for comment in comments):
        reason = "managed_or_safety_sl"
    elif any(comment.startswith("[tp") for comment in comments):
        reason = "managed_or_safety_tp"
    elif any(comment.startswith("[so") for comment in comments):
        reason = "broker_stopout"
    else:
        manager_decision = manager_closed_position(position_ids)
        if manager_decision is not None:
            reason = "qwen_confirmed_close"
            logging.info(
                "close attributed to trade management from its decision record "
                "(broker did not preserve the order comment); positions %s",
                sorted(position_ids),
            )
        else:
            reason = "external_position_close"
    exit_volume = sum(float(deal.volume) for deal in exits)
    exit_price = (
        sum(float(deal.price) * float(deal.volume) for deal in exits) / exit_volume
        if exit_volume
        else None
    )
    gross = sum(float(deal.profit) for deal in matched)
    costs = sum(
        float(deal.commission) + float(deal.swap) + float(deal.fee)
        for deal in matched
    )
    return {
        "reason": reason,
        "exit_price": exit_price,
        "gross_pnl": gross,
        "costs": costs,
        "net_pnl": gross + costs,
        "close_comments": comments,
        # False means the numbers above are missing the exit deal. Anything
        # that averages, totals, or trains on P&L must skip these rows rather
        # than read them as a flat zero.
        "pnl_is_complete": bool(exits),
        "exit_deal_count": len(exits),
        # How we know who closed it: "broker_comment", "manager_decision_log",
        # or None when nobody claimed it.
        "attribution_source": (
            "manager_decision_log"
            if manager_decision is not None
            else ("broker_comment" if comments else None)
        ),
        "manager_close_decision": _manager_close_summary(manager_decision),
    }


def _manager_close_summary(record: dict | None) -> dict | None:
    """The manager's reasoning for the close, kept with the outcome.

    Stored alongside P&L so the decision and its result live in one row. A
    close reason that is only in the decision log has to be joined by hand
    before anyone can ask "did closing early actually help".
    """
    if not record:
        return None
    parsed = record.get("parsed") or {}
    return {
        "decision_id": record.get("decision_id"),
        "created_at_utc": record.get("created_at_utc"),
        "action": parsed.get("action"),
        "confidence": parsed.get("confidence"),
        "reason": parsed.get("reason") or parsed.get("rationale"),
        "criterion": parsed.get("criterion") or parsed.get("exit_criterion"),
        "model": record.get("model"),
    }


def initial_safety_bracket(
    side: str, order_price: float, digits: int, instrument=XAUUSD
) -> tuple[float, float]:
    """Fixed $3 stop / $5 target from the fill price."""
    if side == "buy":
        stop_loss = order_price - instrument.fallback_stop_distance
        take_profit = order_price + instrument.fallback_target_distance
    else:
        stop_loss = order_price + instrument.fallback_stop_distance
        take_profit = order_price - instrument.fallback_target_distance
    return round(stop_loss, digits), round(take_profit, digits)


# H1+ theses resolve over dollars measured in ATR×structure, not a $3 scalp
# pad. Fixed micro brackets on those frames are the measured Asia failure mode
# (2026-08-13: −147 then −162 — both H4 + $3 stop). Cooldown cannot fix that.
HTF_MICRO_BRACKET_FRAMES = frozenset({"H1", "H4", "D1"})


def _refuse_htf_micro_bracket(args, *, detail: str) -> None:
    frame = str(getattr(args, "structure_timeframe", "") or "").strip().upper()
    if frame not in HTF_MICRO_BRACKET_FRAMES:
        return
    if not ENFORCE_HTF_MICRO_BRACKET:
        logging.warning(
            "HTF micro-bracket observation override: proposal=%s frame=%s "
            "using protected $%s/$%s fallback; would_refuse=%s",
            getattr(args, "proposal_id", None),
            frame,
            INITIAL_STOP_DISTANCE,
            INITIAL_TAKE_PROFIT_DISTANCE,
            detail,
        )
        return
    raise GeometryRejection(
        "htf_thesis_micro_bracket",
        (
            f"structure_timeframe={frame} cannot use fixed "
            f"${INITIAL_STOP_DISTANCE}/${INITIAL_TAKE_PROFIT_DISTANCE} brackets; "
            f"{detail}"
        ),
    )


def broker_bracket_from_plan(
    args, order_price: float, digits: int, *, include_volume: bool = False
):
    """Place the entry bracket. Structural when possible, fixed $3/$5 otherwise.

    2026-08-10 -- why this changed
    -----------------------------
    The bracket used to be a flat $3 stop / $5 target from the fill regardless of
    structure. Measured across the last seven closed trades, the only column that
    separated winners from losers was how far the live stop sat INSIDE the
    structural invalidation:

        +246.50  stop BEYOND structure (-2.99)   -> ran to target
        +249.15  0.26 inside                      -> ran to target
        -153.50  4.13 inside                      -> stopped out
        -153.50  8.46 inside, thesis never tested -> stopped in 81s

    Across all 27 closed trades winners averaged 1.71 inside and losers 3.76. A
    stop inside the invalidation converts "my idea was wrong" into "noise removed
    me" -- the trade is closed before the thesis can resolve.

    trade_geometry places the stop BEYOND the named invalidation and lets
    position size absorb the extra distance, so a wider stop is a smaller
    position rather than a larger loss.

    Fallback is deliberate for M15/M30: if the plan carries no usable structural
    levels, or geometry rejects the setup, we return the legacy bracket rather
    than leaving a position unprotected. H1/H4/D1 theses never take that
    fallback -- a micro stop on an HTF idea is the overfit we already measured.

    Set QWEN_STRUCTURAL_BRACKET=0 to force the legacy path (still HTF-blocked).
    """
    instrument = instrument_for(getattr(args, "symbol", PRIMARY_MARKET_SYMBOL))
    safety_sl, safety_tp = initial_safety_bracket(
        args.side, order_price, digits, instrument
    )
    risk_budget = float(
        getattr(args, "risk_budget", trade_geometry.DEFAULT_RISK_BUDGET)
    )
    fallback_volume = trade_geometry.size_for_risk(
        abs(order_price - safety_sl), risk_budget,
        instrument.contract_value_per_price_unit_lot,
    )

    def result(sl: float, tp: float, source: str, volume: float):
        values = (sl, tp, source, volume)
        return values if include_volume else values[:3]

    if not STRUCTURAL_BRACKET_ENABLED:
        _refuse_htf_micro_bracket(
            args, detail="structural brackets disabled; refuse HTF micro pad"
        )
        return result(safety_sl, safety_tp, "fixed_3_5", fallback_volume)

    invalidation = getattr(args, "management_reference_sl", None)
    target = getattr(args, "management_reference_tp", None)
    if invalidation is None or target is None:
        _refuse_htf_micro_bracket(
            args, detail="no structural invalidation/target on the plan"
        )
        return result(
            safety_sl, safety_tp, "fixed_3_5_no_structure", fallback_volume
        )

    bracket = trade_geometry.build_bracket(
        side=args.side,
        entry_price=order_price,
        invalidation_price=float(invalidation),
        target_price=float(target),
        frame=getattr(args, "structure_timeframe", None),
        invalidation_id=getattr(args, "stop_level_id", None),
        target_id=getattr(args, "target_level_id", None),
        risk_budget=risk_budget,
        allow_fallback=False,
        instrument=instrument,
    )
    if not bracket.ok:
        # 2026-08-11 observation window: do not refuse on level/R:R geometry for
        # M15/M30. Log the structural verdict, then place with the fixed $3/$5
        # bracket so those ideas still execute. H1/H4/D1 never fall through to
        # the micro pad — that was the Asia sudden-loss pattern.
        if bracket.reason_code in SKIP_ON_GEOMETRY_REJECTION:
            raise GeometryRejection(bracket.reason_code, bracket.detail)
        _refuse_htf_micro_bracket(
            args,
            detail=(
                f"geometry={bracket.reason_code}; refuse fixed micro pad on HTF thesis"
            ),
        )
        # Observation window for sub-H1. Geometry disliked this entry but is
        # not enforcing, so record WHAT it would have refused -- keyed by
        # proposal_id -- and take the trade anyway. Report:
        # tools/geometry_observation_report.py
        record_geometry_observation(args, bracket, order_price)
        logging.info(
            "structural bracket unavailable (%s: %s); using fixed %s/%s (level geometry does not block entry)",
            bracket.reason_code,
            bracket.detail,
            INITIAL_STOP_DISTANCE,
            INITIAL_TAKE_PROFIT_DISTANCE,
        )
        return result(
            safety_sl,
            safety_tp,
            f"fixed_3_5_after_{bracket.reason_code}",
            fallback_volume,
        )

    logging.info(
        "structural bracket: stop %.3f (beyond %s) target %.3f, distance %.2f, "
        "size %.2f lots, risk %.2f",
        bracket.stop_loss, bracket.invalidation_id, bracket.take_profit,
        bracket.stop_distance, bracket.volume, bracket.expected_risk,
    )
    return result(
        round(bracket.stop_loss, digits),
        round(bracket.take_profit, digits),
        bracket.geometry_source,
        bracket.volume,
    )


def submit_single_position(args, execution_id: str, tick):
    instrument = instrument_for(args.symbol)
    is_buy = args.side == "buy"
    order_price = float(tick.ask if is_buy else tick.bid)
    symbol_info = mt5.symbol_info(args.symbol)
    digits = int(symbol_info.digits) if symbol_info else 3
    # GeometryRejection propagates to _run, which owns the skip record. This
    # function's contract is a 4-tuple; returning anything else here breaks the
    # caller's unpacking.
    safety_sl, safety_tp, bracket_source, effective_volume = broker_bracket_from_plan(
        args, order_price, digits, include_volume=True
    )
    # The plan's invalidation is a hard live-price boundary, not a level that
    # waits for candle confirmation. Put it on the broker order itself so the
    # first tradable quote through it exits even if the manager or executor is
    # delayed. The wider structural stop remains a management reference only.
    planned_invalidation = round(float(args.stop_loss), digits)
    invalidation_is_valid = (
        planned_invalidation < order_price
        if is_buy
        else planned_invalidation > order_price
    )
    if not invalidation_is_valid:
        raise GeometryRejection(
            "geometry:invalidation_already_crossed",
            f"{args.side} entry {order_price:.3f} is already beyond "
            f"planned invalidation {planned_invalidation:.3f}",
        )
    safety_sl = planned_invalidation
    # The observation override may accept geometry that fell back to a nominal
    # $3 bracket, while the broker stop is the plan's actual invalidation.
    # Re-size against that real distance so loosening entry frequency never
    # silently increases the configured dollar risk.
    effective_volume = min(
        effective_volume,
        trade_geometry.size_for_risk(
            abs(order_price - safety_sl),
            float(getattr(args, "risk_budget", trade_geometry.DEFAULT_RISK_BUDGET)),
            instrument.contract_value_per_price_unit_lot,
        ),
    )
    bracket_source = f"planned_invalidation_live+{bracket_source}"
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": args.symbol,
        "volume": effective_volume,
        "type": mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL,
        "price": order_price,
        "sl": safety_sl,
        "tp": safety_tp,
        "deviation": 30,
        "magic": QWEN_MAGIC,
        "comment": execution_comment(execution_id),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result is None or result.retcode not in (
        mt5.TRADE_RETCODE_DONE,
        mt5.TRADE_RETCODE_DONE_PARTIAL,
    ):
        detail = result.comment if result else str(mt5.last_error())
        raise RuntimeError(f"MT5 demo order rejected: {detail}")
    return result, safety_sl, safety_tp, bracket_source


def _run(args) -> dict:
    instrument = instrument_for(args.symbol)
    if not instrument.trade_enabled or instrument.context_only:
        raise RuntimeError(
            f"Execution disabled for context-only instrument {instrument.key}"
        )
    proposal = load_proposal(args.proposal_id)
    validate_plan(args, proposal)
    proposal_created_at = datetime.fromisoformat(proposal["created_at_utc"])
    zone_validity_seconds = max(
        float(args.signal_ttl_seconds),
        float(getattr(args, "zone_validity_seconds", ZONE_ARMED_MAX_SECONDS)),
    )
    signal_seconds_left = remaining_signal_seconds(
        proposal_created_at,
        datetime.now(timezone.utc),
        zone_validity_seconds,
    )
    if signal_seconds_left <= 0:
        result = {
            "schema_version": 1,
            "event": "mt5_execution_skipped",
            "proposal_id": args.proposal_id,
            "created_at_utc": utc_now(),
            "reason": "zone_wait_expired",
            "signal_ttl_seconds": args.signal_ttl_seconds,
            "zone_validity_seconds": zone_validity_seconds,
        }
        append_event(result)
        return result
    if not mt5.initialize(path=args.terminal):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"MT5 account unavailable: {mt5.last_error()}")
        if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
            raise RuntimeError("Paper executor refuses non-demo MT5 accounts.")
        if proposal["symbol"] != args.symbol:
            raise RuntimeError("Plan symbol does not match the recorded proposal.")
        if not mt5.symbol_select(args.symbol, True):
            raise RuntimeError(f"Unable to select {args.symbol}.")

        execution_id = f"demo-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        fills = []
        minimum_pnl = 0.0
        peak_pnl = 0.0
        peak_price_move = 0.0
        first_fill_monotonic = None
        last_monitor_monotonic = None
        started = time.monotonic()
        signal_deadline = started + signal_seconds_left
        entry_tracker = BestPriceRangeTracker(
            args.side,
            args.best_price_observation_seconds,
            args.best_price_retrace,
        )
        append_event(
            {
                "schema_version": 1,
                "event": "mt5_execution_started",
                "execution_id": execution_id,
                "proposal_id": args.proposal_id,
                "created_at_utc": utc_now(),
                "mode": "mt5-demo",
                "account": {"login": account.login, "server": account.server, "trade_mode": "DEMO"},
                "plan": {
                    "symbol": args.symbol,
                    "side": args.side,
                    "entry_low": args.entry_low,
                    "entry_high": args.entry_high,
                    "position_count": 1,
                    "volume": args.volume,
                    "signal_timeframe": args.signal_timeframe,
                    "stop_price_distance": args.stop_price_distance,
                    "qwen_reference_sl": getattr(
                        args, "management_reference_sl", args.stop_loss
                    ),
                    "qwen_reference_target": getattr(
                        args, "management_reference_tp", args.take_profit
                    ),
                    "broker_sl_tp": (
                        "structure support/resistance from plan; "
                        "trade_management may extend TP after break or cut early"
                    ),
                    "initial_stop_distance": INITIAL_STOP_DISTANCE,
                    "initial_take_profit_distance": INITIAL_TAKE_PROFIT_DISTANCE,
                    "initial_safety_distance": INITIAL_SAFETY_DISTANCE,
                    "management_owner": "qwen_trade_management",
                    "signal_ttl_seconds": args.signal_ttl_seconds,
                    "zone_validity_seconds": zone_validity_seconds,
                    "optimal_entry_price": getattr(args, "optimal_entry_price", None),
                    "optimal_entry_tolerance_pts": OPTIMAL_ENTRY_TOLERANCE_PTS,
                    "entry_price_policy": (
                        "optimal_zone_edge_fill;"
                        "buy_at_zone_low_sell_at_zone_high;"
                        "tolerance_0.5pts_from_optimal"
                    ),
                    "best_price_observation_seconds": args.best_price_observation_seconds,
                    "best_price_retrace": args.best_price_retrace,
                },
            }
        )

        # Visibility for the two distinct ways the pre-fill wait can stall:
        # MT5 not handing us a fresh tick at all, versus price still on the
        # unfavorable / chasing side of Qwen's zone. Logged (not gated) so we
        # can tell the two apart from paper-runner.log instead of having to
        # reconstruct it after the fact from execution records, as happened
        # with today's 2026-08-06 review. Neither log line changes behavior;
        # the signal_deadline check above is still the only hard stop.
        STALL_LOG_THRESHOLD_SECONDS = 2.0
        stale_tick_since = None
        outside_zone_since = None
        outside_zone_gate = None

        while True:
            if not fills and time.monotonic() >= signal_deadline:
                result = {
                    "schema_version": 1,
                    "event": "mt5_execution_closed",
                    "execution_id": execution_id,
                    "proposal_id": args.proposal_id,
                    "created_at_utc": utc_now(),
                    "reason": "zone_wait_expired",
                    "exit_price": None,
                    "fills": [],
                    "unfilled_positions": 1,
                    "gross_pnl": 0,
                    "peak_pnl": 0.0,
                    "maximum_drawdown": 0.0,
                    "holding_seconds": round(time.monotonic() - started, 3),
                    "position_holding_seconds": 0.0,
                    "close_results": [],
                }
                append_event(result)
                return result
            tick = mt5.symbol_info_tick(args.symbol)
            if tick is None or tick.time_msc <= 0:
                if not fills:
                    now = time.monotonic()
                    if stale_tick_since is None:
                        stale_tick_since = now
                    elif now - stale_tick_since >= STALL_LOG_THRESHOLD_SECONDS:
                        logging.warning(
                            "paper_executor %s: no tick from MT5 for %s (symbol=%s)",
                            execution_id, args.symbol, "%.1fs" % (now - stale_tick_since),
                        )
                        stale_tick_since = now
                time.sleep(args.poll_ms / 1000)
                continue
            age_ms = int(time.time() * 1000) - int(tick.time_msc)
            if age_ms > args.maximum_tick_age_ms:
                if not fills:
                    now = time.monotonic()
                    if stale_tick_since is None:
                        stale_tick_since = now
                        log_step(
                            "quote_freshness", "stale", proposal_id=args.proposal_id,
                            execution_id=execution_id, symbol=args.symbol,
                            price=float(tick.bid), quote_age_ms=age_ms,
                            detail="entry blocked pending fresh MT5 quote",
                        )
                    elif now - stale_tick_since >= STALL_LOG_THRESHOLD_SECONDS:
                        logging.warning(
                            "paper_executor %s: MT5 tick is %dms stale, stuck for %.1fs (symbol=%s)",
                            execution_id, age_ms, now - stale_tick_since, args.symbol,
                        )
                        stale_tick_since = now
                time.sleep(args.poll_ms / 1000)
                continue
            if stale_tick_since is not None:
                log_step(
                    "quote_freshness", "recovered", proposal_id=args.proposal_id,
                    execution_id=execution_id, symbol=args.symbol,
                    price=float(tick.bid), quote_age_ms=max(0, age_ms),
                )
            stale_tick_since = None

            entry_quote = fill_price(tick, args.side)
            mark = close_price(tick, args.side)
            closed_m1 = latest_closed_m1_bar(args.symbol)
            cancellation = pre_fill_zone_cancellation(
                args.side,
                entry_quote,
                args.entry_low,
                args.entry_high,
                args.stop_loss,
                args.take_profit,
                closed_m1,
            ) if not fills else None
            if cancellation:
                result = {
                    "schema_version": 1,
                    "event": "mt5_execution_closed",
                    "execution_id": execution_id,
                    "proposal_id": args.proposal_id,
                    "created_at_utc": utc_now(),
                    "reason": cancellation,
                    "exit_price": None,
                    "fills": [],
                    "unfilled_positions": 1,
                    "gross_pnl": 0,
                    "peak_pnl": 0.0,
                    "maximum_drawdown": 0.0,
                    "holding_seconds": round(time.monotonic() - started, 3),
                    "position_holding_seconds": 0.0,
                    "close_results": [],
                }
                append_event(result)
                log_step(
                    "zone_lifecycle", "cancelled", proposal_id=args.proposal_id,
                    execution_id=execution_id, symbol=args.symbol,
                    price=entry_quote, quote_age_ms=max(0, age_ms),
                    detail=cancellation,
                )
                return result
            location = entry_location(
                args.side,
                entry_quote,
                args.entry_low,
                args.entry_high,
                args.stop_loss,
            )
            currently_allowed, gate = entry_fill_ready(
                args.side,
                entry_quote,
                args.entry_low,
                args.entry_high,
                args.stop_loss,
                closed_m1,
                optimal_entry_price=getattr(args, "optimal_entry_price", None),
            )
            currently_allowed = not fills and currently_allowed
            if not fills and not currently_allowed:
                now = time.monotonic()
                if outside_zone_since is None or gate != outside_zone_gate:
                    outside_zone_since = now
                    outside_zone_gate = gate
                    log_step(
                        "execution_gate", "waiting", proposal_id=args.proposal_id,
                        execution_id=execution_id, symbol=args.symbol,
                        price=entry_quote, quote_age_ms=max(0, age_ms), detail=gate,
                        entry_low=args.entry_low, entry_high=args.entry_high,
                    )
                elif now - outside_zone_since >= STALL_LOG_THRESHOLD_SECONDS:
                    # Emit one diagnostic per unchanged gate state. Repeating
                    # this every two seconds hid actionable warnings.
                    logging.info(
                        "paper_executor %s: price %.3f %s vs zone [%.3f, %.3f] stop %.3f after %.1fs",
                        execution_id,
                        entry_quote,
                        gate,
                        args.entry_low,
                        args.entry_high,
                        args.stop_loss,
                        now - outside_zone_since,
                    )
                    outside_zone_since = float("inf")
            else:
                outside_zone_since = None
                outside_zone_gate = None
            tracker_state = entry_tracker.observe(
                entry_quote,
                time.monotonic(),
                inside_range=currently_allowed,
                signal_seconds_left=max(0.0, signal_deadline - time.monotonic()),
                poll_seconds=args.poll_ms / 1000,
                location=location,
            )
            if not fills and tracker_state.get("enter"):
                phase = "single_entry"
                log_step(
                    "m1_trigger", "passed", proposal_id=args.proposal_id,
                    execution_id=execution_id, symbol=args.symbol,
                    price=entry_quote, quote_age_ms=max(0, age_ms), detail=gate,
                )
                logging.info(
                    "paper_executor %s: entry_gate=%s filling at %.3f "
                    "optimal=%.3f zone=[%.3f, %.3f]",
                    execution_id,
                    gate,
                    entry_quote,
                    getattr(args, "optimal_entry_price", 0.0) or 0.0,
                    args.entry_low,
                    args.entry_high,
                )
                try:
                    order_result, safety_sl, safety_tp, bracket_source = (
                        submit_single_position(args, execution_id, tick)
                    )
                except GeometryRejection as rejection:
                    # Structure says this entry is not worth taking. A refused
                    # entry is a decision, not a fault: record a clean skip and
                    # end the run without opening a position.
                    logging.info(
                        "entry refused by structural geometry: %s (%s)",
                        rejection.reason_code,
                        rejection.detail,
                    )
                    skipped = {
                        "event": "mt5_execution_skipped",
                        "execution_id": execution_id,
                        "proposal_id": args.proposal_id,
                        "created_at_utc": utc_now(),
                        "reason": rejection.reason_code,
                        "detail": rejection.detail,
                    }
                    append_event(skipped)
                    return skipped
                actual_fill = float(order_result.price or entry_quote)
                log_step(
                    "position_open", "filled", proposal_id=args.proposal_id,
                    execution_id=execution_id, symbol=args.symbol,
                    price=actual_fill, side=args.side,
                )
                actual_volume = float(
                    getattr(order_result, "volume", 0.0) or args.volume
                )
                best_observed = float(tracker_state["best_price"])
                fill = {
                    "position_number": 1,
                    "phase": phase,
                    "price": actual_fill,
                    "best_observed_entry_price": best_observed,
                    "price_from_best": round(
                        actual_fill - best_observed
                        if args.side == "buy"
                        else best_observed - actual_fill,
                        6,
                    ),
                    "entry_selection_reason": tracker_state["reason"],
                    "entry_gate": gate,
                    "entry_observation_seconds": tracker_state["observation_seconds"],
                    "entry_observations": tracker_state["observations"],
                    "improvement_from_previous": None,
                    "volume": actual_volume,
                    "filled_at_utc": utc_now(),
                    "tick_time_msc": tick.time_msc,
                    "deal": int(order_result.deal),
                    "order": int(order_result.order),
                    "retcode": int(order_result.retcode),
                    "stop_loss": safety_sl,
                    "take_profit": safety_tp,
                    "sl_source": bracket_source,
                    "tp_source": bracket_source,
                    "management_reference_sl": getattr(
                        args, "management_reference_sl", args.stop_loss
                    ),
                    "management_reference_tp": getattr(
                        args, "management_reference_tp", args.take_profit
                    ),
                }
                fills.append(fill)
                if first_fill_monotonic is None:
                    first_fill_monotonic = time.monotonic()
                append_event(
                    {
                        "schema_version": 1,
                        "event": "mt5_fill",
                        "execution_id": execution_id,
                        "proposal_id": args.proposal_id,
                        "created_at_utc": utc_now(),
                        "fill": fill,
                    }
                )

            if fills:
                live_positions = owned_positions(args.symbol, execution_id)
                pnl = sum(float(position.profit) for position in live_positions)
                minimum_pnl = min(minimum_pnl, pnl)
                peak_pnl = max(peak_pnl, pnl)
                position_holding_seconds = (
                    time.monotonic() - first_fill_monotonic
                    if first_fill_monotonic is not None
                    else 0.0
                )
                average_entry = average_fill_price(fills)
                price_move = favorable_price_move(mark, average_entry, args.side)
                peak_price_move = max(peak_price_move, price_move)
                structural_tp = getattr(
                    args, "management_reference_tp", args.take_profit
                )
                structural_sl = getattr(
                    args, "management_reference_sl", args.stop_loss
                )
                structural_target_distance = favorable_price_move(
                    structural_tp, average_entry, args.side
                )
                giveback = peak_price_move - price_move
                adverse_price_move = max(0.0, -price_move)
                active_stop_distance = abs(average_entry - float(structural_sl))

                now_monotonic = time.monotonic()
                if (
                    last_monitor_monotonic is None
                    or now_monotonic - last_monitor_monotonic >= MONITOR_INTERVAL_SECONDS
                ):
                    append_event(
                        {
                            "schema_version": 1,
                            "event": "mt5_execution_monitor",
                            "execution_id": execution_id,
                            "proposal_id": args.proposal_id,
                            "created_at_utc": utc_now(),
                            "side": args.side,
                            "mark": mark,
                            "average_entry": average_entry,
                            "favorable_price_move": round(price_move, 3),
                            "peak_favorable_price_move": round(peak_price_move, 3),
                            "price_giveback": round(giveback, 3),
                            "adverse_price_move": round(adverse_price_move, 3),
                            "stop_price_distance": round(active_stop_distance, 3),
                            "stop_progress_pct": round(
                                100 * adverse_price_move / max(active_stop_distance, 0.001),
                                1,
                            ),
                            "structural_target": structural_tp,
                            "structural_target_distance": round(
                                structural_target_distance, 3
                            ),
                            "structural_progress_pct": (
                                round(
                                    100 * price_move / structural_target_distance,
                                    1,
                                )
                                if structural_target_distance > 0
                                else None
                            ),
                            "management_owner": "qwen_trade_management",
                            "target_is_review_level": True,
                            "gross_pnl": pnl,
                            "peak_pnl": peak_pnl,
                            "maximum_drawdown": minimum_pnl,
                            "holding_seconds": round(position_holding_seconds, 3),
                        }
                    )
                    last_monitor_monotonic = now_monotonic
                # MT5 enforces Qwen's named-level SL/TP. The separate Qwen
                # manager may later replace either level after validation.
                if not live_positions:
                    outcome = realized_execution_outcome(fills, proposal_created_at)
                    reason = outcome["reason"]
                    pnl = outcome["gross_pnl"]
                    if outcome["exit_price"] is not None:
                        mark = float(outcome["exit_price"])
                        price_move = favorable_price_move(
                            mark, average_entry, args.side
                        )
                        giveback = peak_price_move - price_move
                        adverse_price_move = max(0.0, -price_move)
                    close_results = []
                    result = {
                        "schema_version": 1,
                        "event": "mt5_execution_closed",
                        "execution_id": execution_id,
                        "proposal_id": args.proposal_id,
                        "created_at_utc": utc_now(),
                        "reason": reason,
                        "exit_price": mark,
                        "fills": fills,
                        "gross_pnl": pnl,
                        "costs": outcome["costs"],
                        "net_pnl": outcome["net_pnl"],
                        "average_entry": average_entry,
                        "favorable_price_move": round(price_move, 3),
                        "peak_favorable_price_move": round(peak_price_move, 3),
                        "price_giveback": round(giveback, 3),
                        "adverse_price_move": round(adverse_price_move, 3),
                        "stop_price_distance": round(active_stop_distance, 3),
                        "structural_target": args.take_profit,
                        "structural_target_distance": round(
                            structural_target_distance, 3
                        ),
                        "management_owner": "qwen_trade_management",
                        "peak_pnl": peak_pnl,
                        "maximum_drawdown": minimum_pnl,
                        "holding_seconds": round(time.monotonic() - started, 3),
                        "position_holding_seconds": round(position_holding_seconds, 3),
                        "entry_wait_seconds": round(
                            first_fill_monotonic - started, 3
                        ) if first_fill_monotonic is not None else None,
                        "close_results": close_results,
                        "close_comments": outcome["close_comments"],
                        # Attribution and completeness travel WITH the outcome.
                        # Without these the manager's own closes were being
                        # filed as "external" and a missing exit deal was
                        # indistinguishable from a genuine zero-P&L trade.
                        "pnl_is_complete": outcome["pnl_is_complete"],
                        "exit_deal_count": outcome["exit_deal_count"],
                        "attribution_source": outcome["attribution_source"],
                        "manager_close_decision": outcome["manager_close_decision"],
                        # Which version of the system produced this result.
                        # Without it, four days of different behaviour get
                        # pooled into one dataset and cancel out.
                        **build_manifest.stamp(),
                    }
                    append_event(result)
                    return result
            time.sleep(args.poll_ms / 1000)

    finally:
        mt5.shutdown()


def run(args) -> dict:
    """Run one exclusive position so concurrent runners cannot overlap tickets."""
    lock = EXECUTION_LOCK_FILE.open("a+b")
    if lock.tell() == 0:
        lock.write(b"\0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        result = {
            "schema_version": 1,
            "event": "mt5_execution_skipped",
            "proposal_id": args.proposal_id,
            "created_at_utc": utc_now(),
            "reason": "executor_busy",
        }
        append_event(result)
        return result
    try:
        return _run(args)
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


def self_test() -> None:
    assert inside_entry_zone(101, 100, 102)
    assert not inside_entry_zone(103, 100, 102)
    assert entry_location("buy", 101, 100, 102, 97) == "inside_zone"
    assert entry_location("buy", 103, 100, 102, 97) == "favorable_outside"
    assert entry_location("buy", 99, 100, 102, 97) == "unfavorable_outside"
    assert entry_location("buy", 97, 100, 102, 97) == "past_stop"
    assert entry_location("sell", 101, 100, 102, 105) == "inside_zone"
    assert entry_location("sell", 99, 100, 102, 105) == "favorable_outside"
    assert entry_location("sell", 103, 100, 102, 105) == "unfavorable_outside"
    assert entry_location("sell", 105, 100, 102, 105) == "past_stop"
    assert entry_price_allowed("buy", 101, 100, 102, 97)
    assert entry_price_allowed("sell", 101, 100, 102, 105)
    assert not entry_price_allowed("buy", 103, 100, 102, 97)  # approach: wait for hunt tag
    assert not entry_price_allowed("sell", 99, 100, 102, 105)  # approach: wait for hunt tag
    assert not entry_price_allowed("buy", 99, 100, 102, 97)
    assert not entry_price_allowed("sell", 103, 100, 102, 105)
    assert not entry_price_allowed("buy", 97, 100, 102, 97)
    fail_m1 = {"open": 101.2, "high": 101.4, "low": 99.8, "close": 100.4}
    through_m1 = {"open": 100.2, "high": 99.6, "low": 99.1, "close": 99.4}
    # No optimal price → fills anywhere in zone (backward compat)
    ready, gate = entry_fill_ready("buy", 101, 100, 102, 97, fail_m1)
    assert ready and gate == "armed_m1_failure_at_optimal"
    waiting, wait_gate = entry_fill_ready("buy", 101, 100, 102, 97, through_m1)
    assert not waiting and wait_gate == "inside_zone_waiting_m1_failure"
    outside, outside_gate = entry_fill_ready("buy", 103, 100, 102, 97, fail_m1)
    assert not outside and outside_gate == "favorable_outside"
    # Optimal price gate: buy at zone low (100), sell at zone high (102)
    # Buy at 100.3 with optimal=100, tolerance=0.5 → within tolerance → fill
    buy_opt, buy_opt_gate = entry_fill_ready("buy", 100.3, 100, 102, 97, fail_m1, 100.0)
    assert buy_opt and buy_opt_gate == "armed_m1_failure_at_optimal"
    # Buy at 101.5 with optimal=100, tolerance=0.5 → too far from optimal → wait
    buy_far, buy_far_gate = entry_fill_ready("buy", 101.5, 100, 102, 97, fail_m1, 100.0)
    assert not buy_far and buy_far_gate == "inside_zone_waiting_optimal_buy_low"
    # Sell at 101.8 with optimal=102, tolerance=0.5 → within tolerance → fill
    sell_opt, sell_opt_gate = entry_fill_ready("sell", 101.8, 100, 102, 105, fail_m1, 102.0)
    assert sell_opt and sell_opt_gate == "armed_m1_failure_at_optimal"
    # Sell at 100.5 with optimal=102, tolerance=0.5 → too far from optimal → wait
    sell_far, sell_far_gate = entry_fill_ready("sell", 100.5, 100, 102, 105, fail_m1, 102.0)
    assert not sell_far and sell_far_gate == "inside_zone_waiting_optimal_sell_high"
    assert average_fill_price([{"price": 101, "volume": 0.5}]) == 101
    assert favorable_price_move(104, 101, "buy") == 3
    assert favorable_price_move(98, 101, "sell") == 3
    assert MIN_ENTRY_CONFIDENCE == 51
    assert initial_safety_bracket("buy", 4233.553, 3) == (4228.553, 4238.553)
    assert initial_safety_bracket("sell", 4233.553, 3) == (4238.553, 4228.553)
    created = datetime(2026, 7, 30, tzinfo=timezone.utc)
    assert remaining_signal_seconds(
        created, created + timedelta(seconds=59), 60
    ) == 1
    assert remaining_signal_seconds(
        created, created + timedelta(seconds=60), 60
    ) == 0
    # First fresh allowed tick fires immediately only when in-zone (hunt tag).
    buy_tracker = BestPriceRangeTracker("buy", 2.0, 0.1)
    first = buy_tracker.observe(
        101.0,
        0.0,
        inside_range=True,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="inside_zone",
    )
    assert first["enter"] and first["reason"] == "immediate_zone_entry"
    assert first["best_price"] == 101.0
    assert first["observations"] == 1
    buy_approach = BestPriceRangeTracker("buy", 2.0, 0.1).observe(
        103.0,
        0.0,
        inside_range=False,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="favorable_outside",
    )
    assert not buy_approach["enter"] and buy_approach["reason"] == "outside_entry_range"
    outside = BestPriceRangeTracker("buy", 2.0, 0.1).observe(
        99.0,
        0.0,
        inside_range=False,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="unfavorable_outside",
    )
    assert not outside["enter"] and outside["reason"] == "outside_entry_range"
    sell_tracker = BestPriceRangeTracker("sell", 1.0, 0.1)
    immediate = sell_tracker.observe(
        100.0,
        0.0,
        inside_range=True,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="inside_zone",
    )
    assert immediate["enter"] and immediate["best_price"] == 100.0
    sell_approach = BestPriceRangeTracker("sell", 1.0, 0.1).observe(
        99.0,
        0.0,
        inside_range=False,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="favorable_outside",
    )
    assert not sell_approach["enter"] and sell_approach["reason"] == "outside_entry_range"
    improved = sell_tracker.observe(
        100.2,
        1.0,
        inside_range=True,
        signal_seconds_left=9,
        poll_seconds=0.25,
        location="inside_zone",
    )
    # sell side: a higher price is the favorable direction, so best_price
    # tracking should move up even though entry already fired on the first tick.
    assert improved["enter"] and improved["best_price"] == 100.2
    print("paper_executor self-test passed")


def parse_args():
    parser = argparse.ArgumentParser(description="MT5 single-position paper executor")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--proposal-id")
    parser.add_argument("--symbol", default=PRIMARY_MARKET_SYMBOL)
    parser.add_argument("--side", choices=("buy", "sell"))
    parser.add_argument("--entry-low", type=float)
    parser.add_argument("--entry-high", type=float)
    parser.add_argument("--stop-loss", type=float)
    parser.add_argument("--take-profit", type=float)
    parser.add_argument("--buckets", type=int, default=1)
    parser.add_argument("--volume", type=float, default=0.5)
    parser.add_argument("--signal-ttl-seconds", type=float, default=60)
    parser.add_argument("--maximum-tick-age-ms", type=int, default=3000)
    parser.add_argument("--poll-ms", type=int, default=250)
    parser.add_argument("--signal-timeframe", choices=("M1", "M5"), default="M1")
    parser.add_argument("--stop-price-distance", type=float, default=3.0)
    parser.add_argument("--best-price-observation-seconds", type=float, default=2.0)
    parser.add_argument("--best-price-retrace", type=float, default=0.10)
    parser.add_argument("--terminal", default=DEFAULT_TERMINAL)
    args = parser.parse_args()
    if not args.self_test:
        required = (
            "proposal_id",
            "side",
            "entry_low",
            "entry_high",
            "stop_loss",
            "take_profit",
        )
        missing = [name for name in required if getattr(args, name) is None]
        if missing:
            parser.error("missing required arguments: " + ", ".join(missing))
    return args


if __name__ == "__main__":
    arguments = parse_args()
    if arguments.self_test:
        self_test()
    else:
        print(json.dumps(run(arguments), indent=2))
