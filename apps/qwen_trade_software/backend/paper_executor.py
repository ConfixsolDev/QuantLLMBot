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

import trade_geometry
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
# Stage 3: place the stop beyond the structural invalidation and let size absorb
# the distance. Set QWEN_STRUCTURAL_BRACKET=0 to fall back to the flat $3/$5.
STRUCTURAL_BRACKET_ENABLED = os.environ.get("QWEN_STRUCTURAL_BRACKET", "1") != "0"

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


def append_event(event: dict) -> None:
    append_tick_record("paper-executions", event)


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
    """True when price is in-zone or favorably outside it (not chasing, not past stop)."""
    return entry_location(side, price, low, high, stop_loss) in (
        "inside_zone",
        "favorable_outside",
    )


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

    Allowed means inside Qwen's approved zone, or favorably outside it:
    buy below the zone low, sell above the zone high. Chasing the wrong
    side of the zone still waits. Price already through the structural
    stop never enters.

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


def initial_safety_bracket(side: str, order_price: float, digits: int) -> tuple[float, float]:
    """Fixed $3 stop / $5 target from the fill price."""
    if side == "buy":
        stop_loss = order_price - INITIAL_STOP_DISTANCE
        take_profit = order_price + INITIAL_TAKE_PROFIT_DISTANCE
    else:
        stop_loss = order_price + INITIAL_STOP_DISTANCE
        take_profit = order_price - INITIAL_TAKE_PROFIT_DISTANCE
    return round(stop_loss, digits), round(take_profit, digits)


def broker_bracket_from_plan(args, order_price: float, digits: int) -> tuple[float, float, str]:
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

    Fallback is deliberate: if the plan carries no usable structural levels, or
    geometry rejects the setup, we return the exact legacy bracket rather than
    leaving a position unprotected. Worst case is today's behaviour.

    Set QWEN_STRUCTURAL_BRACKET=0 to force the legacy path.
    """
    safety_sl, safety_tp = initial_safety_bracket(args.side, order_price, digits)
    if not STRUCTURAL_BRACKET_ENABLED:
        return safety_sl, safety_tp, "fixed_3_5"

    invalidation = getattr(args, "management_reference_sl", None)
    target = getattr(args, "management_reference_tp", None)
    if invalidation is None or target is None:
        return safety_sl, safety_tp, "fixed_3_5_no_structure"

    bracket = trade_geometry.build_bracket(
        side=args.side,
        entry_price=order_price,
        invalidation_price=float(invalidation),
        target_price=float(target),
        frame=getattr(args, "structure_timeframe", None),
        invalidation_id=getattr(args, "stop_level_id", None),
        target_id=getattr(args, "target_level_id", None),
        risk_budget=float(getattr(args, "risk_budget", trade_geometry.DEFAULT_RISK_BUDGET)),
        allow_fallback=False,
    )
    if not bracket.ok:
        # 2026-08-11 observation window: do not refuse on level/R:R geometry.
        # Log the structural verdict, then place with the fixed $3/$5 bracket
        # so ready ideas still execute. Re-enable hard skips with
        # QWEN_SKIP_ON_GEOMETRY=1 after we have enough live evidence.
        if bracket.reason_code in SKIP_ON_GEOMETRY_REJECTION:
            raise GeometryRejection(bracket.reason_code, bracket.detail)
        # Observation window. Geometry disliked this entry but is not enforcing,
        # so record WHAT it would have refused -- keyed by proposal_id -- and
        # take the trade anyway. Refusing a trade tells you nothing about
        # whether refusing it was right; letting it run and keeping the
        # counterfactual is what makes the decision measurable in a day or two.
        # Report: tools/geometry_observation_report.py
        record_geometry_observation(args, bracket, order_price)
        logging.info(
            "structural bracket unavailable (%s: %s); using fixed %s/%s (level geometry does not block entry)",
            bracket.reason_code,
            bracket.detail,
            INITIAL_STOP_DISTANCE,
            INITIAL_TAKE_PROFIT_DISTANCE,
        )
        return safety_sl, safety_tp, f"fixed_3_5_after_{bracket.reason_code}"

    logging.info(
        "structural bracket: stop %.3f (beyond %s) target %.3f, distance %.2f, "
        "size %.2f lots, risk %.2f",
        bracket.stop_loss, bracket.invalidation_id, bracket.take_profit,
        bracket.stop_distance, bracket.volume, bracket.expected_risk,
    )
    return (
        round(bracket.stop_loss, digits),
        round(bracket.take_profit, digits),
        bracket.geometry_source,
    )


def submit_single_position(args, execution_id: str, tick):
    is_buy = args.side == "buy"
    order_price = float(tick.ask if is_buy else tick.bid)
    symbol_info = mt5.symbol_info(args.symbol)
    digits = int(symbol_info.digits) if symbol_info else 3
    # GeometryRejection propagates to _run, which owns the skip record. This
    # function's contract is a 4-tuple; returning anything else here breaks the
    # caller's unpacking.
    safety_sl, safety_tp, bracket_source = broker_bracket_from_plan(
        args, order_price, digits
    )
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": args.symbol,
        "volume": args.volume,
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
    proposal = load_proposal(args.proposal_id)
    validate_plan(args, proposal)
    proposal_created_at = datetime.fromisoformat(proposal["created_at_utc"])
    signal_seconds_left = remaining_signal_seconds(
        proposal_created_at,
        datetime.now(timezone.utc),
        args.signal_ttl_seconds,
    )
    if signal_seconds_left <= 0:
        result = {
            "schema_version": 1,
            "event": "mt5_execution_skipped",
            "proposal_id": args.proposal_id,
            "created_at_utc": utc_now(),
            "reason": "signal_expired",
            "signal_ttl_seconds": args.signal_ttl_seconds,
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
                    "entry_price_policy": (
                        "in_zone_or_favorable_outside;"
                        "buy_below_low_and_sell_above_high_allowed;"
                        "unfavorable_chase_waits"
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

        while True:
            if not fills and time.monotonic() >= signal_deadline:
                result = {
                    "schema_version": 1,
                    "event": "mt5_execution_closed",
                    "execution_id": execution_id,
                    "proposal_id": args.proposal_id,
                    "created_at_utc": utc_now(),
                    "reason": "signal_expired",
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
                    elif now - stale_tick_since >= STALL_LOG_THRESHOLD_SECONDS:
                        logging.warning(
                            "paper_executor %s: MT5 tick is %dms stale, stuck for %.1fs (symbol=%s)",
                            execution_id, age_ms, now - stale_tick_since, args.symbol,
                        )
                        stale_tick_since = now
                time.sleep(args.poll_ms / 1000)
                continue
            stale_tick_since = None

            entry_quote = fill_price(tick, args.side)
            mark = close_price(tick, args.side)
            location = entry_location(
                args.side,
                entry_quote,
                args.entry_low,
                args.entry_high,
                args.stop_loss,
            )
            currently_allowed = not fills and entry_price_allowed(
                args.side,
                entry_quote,
                args.entry_low,
                args.entry_high,
                args.stop_loss,
            )
            if not fills and not currently_allowed:
                now = time.monotonic()
                if outside_zone_since is None:
                    outside_zone_since = now
                elif now - outside_zone_since >= STALL_LOG_THRESHOLD_SECONDS:
                    logging.warning(
                        "paper_executor %s: price %.3f %s vs zone [%.3f, %.3f] stop %.3f after %.1fs",
                        execution_id,
                        entry_quote,
                        location,
                        args.entry_low,
                        args.entry_high,
                        args.stop_loss,
                        now - outside_zone_since,
                    )
                    outside_zone_since = now
            else:
                outside_zone_since = None
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
                    "entry_observation_seconds": tracker_state["observation_seconds"],
                    "entry_observations": tracker_state["observations"],
                    "improvement_from_previous": None,
                    "volume": args.volume,
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
    assert entry_price_allowed("buy", 103, 100, 102, 97)
    assert entry_price_allowed("sell", 99, 100, 102, 105)
    assert not entry_price_allowed("buy", 99, 100, 102, 97)
    assert not entry_price_allowed("sell", 103, 100, 102, 105)
    assert not entry_price_allowed("buy", 97, 100, 102, 97)
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
    # First fresh allowed tick fires immediately (in-zone or favorable outside).
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
    buy_better = BestPriceRangeTracker("buy", 2.0, 0.1).observe(
        103.0,
        0.0,
        inside_range=True,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="favorable_outside",
    )
    assert buy_better["enter"] and buy_better["reason"] == "favorable_outside_zone_entry"
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
    sell_better = BestPriceRangeTracker("sell", 1.0, 0.1).observe(
        99.0,
        0.0,
        inside_range=True,
        signal_seconds_left=10,
        poll_seconds=0.25,
        location="favorable_outside",
    )
    assert sell_better["enter"] and sell_better["reason"] == "favorable_outside_zone_entry"
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
    parser.add_argument("--symbol", default="XAUUSDr")
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
