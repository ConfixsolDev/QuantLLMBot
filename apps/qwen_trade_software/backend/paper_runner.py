"""Continuously runs validated Qwen proposals through the demo executor."""

import json
import logging
import logging.handlers
import msvcrt
import time
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5

import build_manifest
import process_logging
import paper_executor
import trade_geometry
from market_context_cache import latest_entry_context


APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "paper-runner.log"
DAILY_PAPER_CAP = 100
MIN_ENTRY_CONFIDENCE = 51
MAX_PROPOSAL_AGE_SECONDS = 60
PROPOSAL_POLL_SECONDS = 0.25
# Cool down after EVERY completed trade, win or loss.
#
# 2026-08-11 -- why a win now cools down too
# ------------------------------------------
# Only losses paused the runner. Measured over the trades that opened within
# half an hour of a previous close:
#
#     after a WINNING close   n=23  net  -353.40  avg  -15.37  win 52%
#     after a LOSING close    n=34  net  -954.85  avg  -28.08  win 26%
#
# The post-loss group is worse, which is why that pause exists. But the
# post-win group also loses money: a 52% win rate at -15.37 a trade means the
# winners are smaller than the losers. Re-entering straight after taking profit
# is entering on a level that has just been reached and reacted to, which is
# rarely the same setup the plan was built on.
#
# 2026-08-13 -- loss cooldown lengthened; exceptional bypass only
# --------------------------------------------------------------
# Three same-thesis M5 pin fades lost ~$516 in ~45 minutes after the old 120s
# loss pause. 30 minutes covers that re-fire window. During a loss cooldown the
# runner still polls: a fresh ready proposal may enter only when model
# confidence is very high AND structural reward:risk is very high. Win
# cooldown stays short and hard (no bypass).
LOSS_COOLDOWN_SECONDS = 1800
WIN_COOLDOWN_SECONDS = 120
LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE = 82
# Above normal geometry floor (~0.9) and above the fixed $3/$5 bracket (~1.67).
LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK = 2.5
BEST_PRICE_OBSERVATION_SECONDS = 2.0
BEST_PRICE_RETRACE = 0.10
RUNNER_LOCK_FILE = APP_DIR / "paper-runner.lock"
BROKER_TRUTH_REFRESH_SECONDS = 2.0
_BROKER_COUNT_CACHE = {"checked": 0.0, "count": 0}
# Active post-trade pause. Cleared on expiry or a qualifying loss-cooldown bypass.
_COOLDOWN_STATE = {"until_monotonic": 0.0, "label": ""}

_LOG_HANDLER = process_logging.configure(LOG_FILE, owner="paper_runner")
# Announce the build and alarm if it has drifted from the declared freeze.
build_manifest.log_identity("paper_runner")


def _dated_log_path(base_name: str) -> Path:
    """Today's log file, e.g. paper-proposals-2026-08-06.jsonl.

    Computed fresh on every call (never cached) so a process that stays
    running across midnight rolls over to a new file automatically, the
    same way reviewer.py already rotates reviews-*.jsonl by date.
    """
    return LOG_DIR / f"{base_name}-{datetime.now():%Y-%m-%d}.jsonl"


def _dated_log_files(base_name: str, days_back: int = 1) -> list[Path]:
    """Existing dated files for `base_name`, today first then earlier days.

    A proposal or position from just before midnight can still be looked
    up just after it, so lookups need to see yesterday's file too, not
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


def processed_ids() -> set:
    ids = set()
    for path in _dated_log_files("paper-executions"):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") in (
                "simulation_started", "mt5_execution_started", "mt5_execution_skipped"
            ):
                ids.add(event.get("proposal_id"))
    return ids


def broker_filled_today() -> int:
    """Count today's Qwen positions from authoritative MT5 deal history."""
    now_monotonic = time.monotonic()
    if now_monotonic - _BROKER_COUNT_CACHE["checked"] < BROKER_TRUTH_REFRESH_SECONDS:
        return int(_BROKER_COUNT_CACHE["count"])
    if not mt5.initialize(path=paper_executor.DEFAULT_TERMINAL):
        raise RuntimeError(f"MT5 broker truth unavailable: {mt5.last_error()}")
    try:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(start, now)
        if deals is None:
            raise RuntimeError(f"MT5 deal history unavailable: {mt5.last_error()}")
        position_ids = {
            int(deal.position_id)
            for deal in deals
            if deal.magic == paper_executor.QWEN_MAGIC
            and deal.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
            and deal.entry in (mt5.DEAL_ENTRY_IN, mt5.DEAL_ENTRY_INOUT)
        }
        _BROKER_COUNT_CACHE.update(
            {"checked": now_monotonic, "count": len(position_ids)}
        )
        return len(position_ids)
    finally:
        mt5.shutdown()


def latest_ready_proposal():
    files = _dated_log_files("paper-proposals")
    if not files:
        return None
    done = processed_ids()
    for path in files:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                proposal = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                created_at = datetime.fromisoformat(proposal["created_at_utc"])
            except (KeyError, TypeError, ValueError):
                continue
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age_seconds < 0 or age_seconds > MAX_PROPOSAL_AGE_SECONDS:
                # Proposals are read newest-first within a file; once one is
                # too old, everything earlier in this file is too, but a
                # second (older) file may still hold nothing usable either,
                # so just move on rather than stopping the whole search.
                continue
            plan = proposal.get("qwen", {}).get("execution_plan", {})
            if plan.get("status") == "ready" and proposal.get("proposal_id") not in done:
                return proposal
    return None


def arguments_for(proposal: dict) -> Namespace:
    plan = proposal["qwen"]["execution_plan"]
    # Broker uses fixed $3/$5 from the plan. Structure S/R prices are management
    # references only — never used to reject the entry.
    manage_sl = plan.get("structural_stop_loss")
    manage_tp = plan.get("structural_take_profit")
    try:
        manage_sl = float(manage_sl) if manage_sl is not None else float(plan["stop_loss"])
    except (TypeError, ValueError):
        manage_sl = float(plan["stop_loss"])
    try:
        manage_tp = (
            float(manage_tp) if manage_tp is not None else float(plan["take_profit"])
        )
    except (TypeError, ValueError):
        manage_tp = float(plan["take_profit"])
    return Namespace(
        proposal_id=proposal["proposal_id"],
        symbol=proposal["symbol"],
        side=plan["side"],
        entry_low=float(plan["entry_low"]),
        entry_high=float(plan["entry_high"]),
        stop_loss=float(plan["stop_loss"]),
        take_profit=float(plan["take_profit"]),
        management_reference_sl=manage_sl,
        management_reference_tp=manage_tp,
        buckets=1,
        volume=float(plan["volume_each"]),
        signal_ttl_seconds=MAX_PROPOSAL_AGE_SECONDS,
        maximum_tick_age_ms=3000,
        poll_ms=250,
        stop_price_distance=float(plan.get("stop_price_distance") or 3.0),
        # Stage 3 inputs. The executor uses these to place the stop beyond the
        # named invalidation instead of at a flat $3 from the fill; see
        # paper_executor.broker_bracket_from_plan for the measured rationale.
        structure_timeframe=plan.get("structure_timeframe"),
        stop_level_id=plan.get("stop_level_id"),
        target_level_id=plan.get("target_level_id"),
        best_price_observation_seconds=BEST_PRICE_OBSERVATION_SECONDS,
        best_price_retrace=BEST_PRICE_RETRACE,
        signal_timeframe=proposal.get("timeframe", "M1"),
        terminal=paper_executor.DEFAULT_TERMINAL,
    )


def proposal_runtime_failures(proposal: dict) -> list[str]:
    """Recheck confidence + session/cache before entry. No TP/SL geometry veto."""
    failures = []
    qwen = proposal.get("qwen")
    qwen = qwen if isinstance(qwen, dict) else {}
    plan = qwen.get("execution_plan")
    plan = plan if isinstance(plan, dict) else {}
    try:
        confidence = float(qwen.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < MIN_ENTRY_CONFIDENCE:
        failures.append(f"confidence_below_{MIN_ENTRY_CONFIDENCE}")
    if plan.get("side") not in ("buy", "sell"):
        failures.append("side_missing")
    if plan.get("decision_confidence") != round(confidence):
        failures.append("confidence_provenance_mismatch")

    symbol = str(proposal.get("symbol") or "XAUUSDr")
    current = latest_entry_context(symbol)
    if current.get("status") != "ready":
        failures.append("current_cache_not_ready")
        return failures
    current_session = current.get("session", {})
    if not current_session.get("trade_permitted", False):
        failures.append("current_session_not_permitted")
    original_session = (
        proposal.get("market", {}).get("cache_context", {}).get("session", {})
    )
    for field in ("trading_date_utc", "session"):
        if original_session.get(field) != current_session.get(field):
            failures.append(f"current_session_{field}_changed")
    # Cache epochs rotate every minute; requiring an exact structural/playbook
    # match vetoed fresh ready proposals before MT5 could place them. Keep the
    # model digest check only — session/date checks above still apply.
    if (
        plan.get("cache_model_digest")
        and current.get("model_digest")
        and plan.get("cache_model_digest") != current.get("model_digest")
    ):
        failures.append("current_model_digest_changed")
    return failures


def has_open_qwen_position() -> bool:
    """Block every new entry while any Qwen-owned position remains open."""
    if not mt5.initialize(path=paper_executor.DEFAULT_TERMINAL):
        raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
    try:
        positions = mt5.positions_get() or ()
        return any(
            position.magic == paper_executor.QWEN_MAGIC
            and str(position.comment).startswith("QWEN_")
            for position in positions
        )
    finally:
        mt5.shutdown()


def cooldown_for(result: dict) -> tuple[int, str]:
    """How long to pause after a completed run, and what to call it.

    Only a trade that actually reached the market earns a cooldown. A proposal
    that expired unfilled, or was skipped, never took a position -- pausing on
    those would throttle the system for something that never happened.

    The signal that a real trade completed is a settled P&L. `pnl_is_complete`
    is False when the closing deal never reached MT5 history, in which case
    net_pnl is the entry commission and its sign means nothing.
    """
    if result.get("pnl_is_complete") is False:
        return 0, ""
    net = result.get("net_pnl")
    if net is None:
        return 0, ""          # signal_expired and friends: no position was held
    try:
        net = float(net)
    except (TypeError, ValueError):
        return 0, ""
    if net < 0:
        return LOSS_COOLDOWN_SECONDS, "Loss"
    if net > 0:
        return WIN_COOLDOWN_SECONDS, "Win"
    return 0, ""              # exactly flat: nothing to step back from


def start_cooldown(seconds: int, label: str) -> None:
    """Arm the post-trade pause. Loss pauses stay interruptible; see bypass."""
    if seconds <= 0:
        _COOLDOWN_STATE.update({"until_monotonic": 0.0, "label": ""})
        return
    _COOLDOWN_STATE.update(
        {
            "until_monotonic": time.monotonic() + float(seconds),
            "label": label,
        }
    )


def clear_cooldown() -> None:
    _COOLDOWN_STATE.update({"until_monotonic": 0.0, "label": ""})


def cooldown_remaining_seconds() -> float:
    remaining = float(_COOLDOWN_STATE.get("until_monotonic") or 0.0) - time.monotonic()
    return remaining if remaining > 0 else 0.0


def active_cooldown_label() -> str:
    if cooldown_remaining_seconds() <= 0:
        return ""
    return str(_COOLDOWN_STATE.get("label") or "")


def proposal_confidence(proposal: dict) -> float:
    qwen = proposal.get("qwen")
    qwen = qwen if isinstance(qwen, dict) else {}
    try:
        return float(qwen.get("confidence"))
    except (TypeError, ValueError):
        return 0.0


def proposal_reward_risk(proposal: dict) -> float | None:
    """Structural thesis R:R when available; else plan stop/target R:R.

    Uses the same cost haircut as trade_geometry so "very high" is comparable
    to the live geometry floor, not a raw price-distance ratio.
    """
    qwen = proposal.get("qwen")
    qwen = qwen if isinstance(qwen, dict) else {}
    plan = qwen.get("execution_plan")
    plan = plan if isinstance(plan, dict) else {}
    side = str(plan.get("side") or "").lower()
    try:
        entry_low = float(plan["entry_low"])
        entry_high = float(plan["entry_high"])
    except (KeyError, TypeError, ValueError):
        return None
    entry_mid = (entry_low + entry_high) / 2.0

    def _float(key_primary: str, key_fallback: str) -> float | None:
        for key in (key_primary, key_fallback):
            raw = plan.get(key)
            if raw is None:
                continue
            try:
                return float(raw)
            except (TypeError, ValueError):
                continue
        return None

    stop = _float("structural_stop_loss", "stop_loss")
    target = _float("structural_take_profit", "take_profit")
    if stop is None or target is None:
        return None
    if side == "buy":
        risk = entry_mid - stop
        reward = target - entry_mid
    elif side == "sell":
        risk = stop - entry_mid
        reward = entry_mid - target
    else:
        return None
    if risk <= 0 or reward <= 0:
        return None
    return (reward - trade_geometry.ROUND_TRIP_COST) / risk


def loss_cooldown_bypass_ok(proposal: dict) -> tuple[bool, dict]:
    """True only during a Loss cooldown when confidence and R:R both clear."""
    confidence = proposal_confidence(proposal)
    reward_risk = proposal_reward_risk(proposal)
    detail = {
        "confidence": confidence,
        "reward_risk": None if reward_risk is None else round(reward_risk, 3),
        "min_confidence": LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE,
        "min_reward_risk": LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK,
    }
    if confidence + 1e-9 < LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE:
        return False, detail
    if reward_risk is None or reward_risk + 1e-9 < LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK:
        return False, detail
    return True, detail


def skip_proposal(proposal_id: str, reason: str, **extra) -> None:
    paper_executor.append_event(
        {
            "schema_version": 1,
            "event": "mt5_execution_skipped",
            "proposal_id": proposal_id,
            "created_at_utc": paper_executor.utc_now(),
            "reason": reason,
            **extra,
        }
    )


def run_loop() -> None:
    logging.info("MT5 demo runner started (hard demo-account lock enabled)")
    while True:
        try:
            daily_completed = broker_filled_today()
        except Exception:
            logging.exception("MT5 broker-truth count failed; new entries blocked")
            time.sleep(3)
            continue
        if daily_completed >= DAILY_PAPER_CAP:
            logging.info(
                "Daily paper cap reached: %d/%d",
                daily_completed,
                DAILY_PAPER_CAP,
            )
            time.sleep(60)
            continue
        proposal = latest_ready_proposal()
        if proposal is None:
            time.sleep(PROPOSAL_POLL_SECONDS)
            continue
        runtime_failures = proposal_runtime_failures(proposal)
        if runtime_failures:
            proposal_id = proposal["proposal_id"]
            skip_proposal(
                proposal_id,
                "entry_runtime_validation_failed",
                failures=runtime_failures,
            )
            logging.info(
                "Skipped proposal %s runtime_failures=%s",
                proposal_id,
                runtime_failures,
            )
            time.sleep(PROPOSAL_POLL_SECONDS)
            continue
        if has_open_qwen_position():
            logging.info("Single-position gate blocked a new proposal")
            time.sleep(1)
            continue

        remaining = cooldown_remaining_seconds()
        label = active_cooldown_label()
        if remaining > 0:
            proposal_id = proposal["proposal_id"]
            if label == "Loss":
                ok, bypass_detail = loss_cooldown_bypass_ok(proposal)
                if ok:
                    logging.info(
                        "Loss cooldown bypassed for %s remaining=%.0fs detail=%s",
                        proposal_id,
                        remaining,
                        bypass_detail,
                    )
                    clear_cooldown()
                else:
                    skip_proposal(
                        proposal_id,
                        "loss_cooldown_active",
                        remaining_seconds=round(remaining, 1),
                        bypass=bypass_detail,
                    )
                    logging.info(
                        "Loss cooldown blocked %s remaining=%.0fs bypass=%s",
                        proposal_id,
                        remaining,
                        bypass_detail,
                    )
                    time.sleep(PROPOSAL_POLL_SECONDS)
                    continue
            else:
                skip_proposal(
                    proposal_id,
                    "win_cooldown_active",
                    remaining_seconds=round(remaining, 1),
                )
                logging.info(
                    "Win cooldown blocked %s remaining=%.0fs",
                    proposal_id,
                    remaining,
                )
                time.sleep(PROPOSAL_POLL_SECONDS)
                continue

        proposal_id = proposal["proposal_id"]
        logging.info("Starting validated proposal %s", proposal_id)
        try:
            result = paper_executor.run(arguments_for(proposal))
            logging.info(
                "Completed %s reason=%s net_pnl=%s",
                proposal_id,
                result.get("reason"),
                result.get("net_pnl"),
            )
            seconds, cool_label = cooldown_for(result)
            if seconds:
                start_cooldown(seconds, cool_label)
                logging.info(
                    "%s cooldown started for %ds after %s (net_pnl=%s)",
                    cool_label, seconds, proposal_id, result.get("net_pnl"),
                )
        except Exception:
            logging.exception("Paper proposal failed: %s", proposal_id)
            time.sleep(3)


def main() -> None:
    lock = RUNNER_LOCK_FILE.open("a+b")
    if lock.tell() == 0:
        lock.write(b"\0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        logging.error("Paper runner refused duplicate process")
        lock.close()
        return
    try:
        run_loop()
    finally:
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


if __name__ == "__main__":
    main()
