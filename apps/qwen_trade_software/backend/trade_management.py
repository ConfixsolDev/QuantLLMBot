"""Trade management: the ongoing, in-trade half of the Qwen paper-trading system.

2026-08-06 split: this file used to be part of reviewer.py. It is now a
separate process because entry-decision and trade-management are, per the
user, "a different game" -- they will need separate knowledge bases and
eventually separate trained skills/models, so keeping them in one file made
that future work harder than it needed to be.

This process owns everything that happens AFTER a Qwen position is already
open: reading live positions/deals from MT5, building the deterministic
management facts (trade path, structural levels, execution-monitor state),
asking Qwen whether to hold, protect, or close. A safety guard still closes on
hard invalidation. If Qwen is down for several cycles, a timeout guard is the
last-resort mechanical close. This process owns everything that happens AFTER a
Qwen position is already open: reading live positions/deals from MT5, building
the deterministic management facts (trade path, structural levels, execution-monitor state),
and applying that decision to the live position's SL/TP.
protect, or close, and applying that decision to the live position's SL/TP.
It runs on its own interval (QWEN_REVIEW_INTERVAL_SECONDS, default 30s) and
writes its own dashboard-state file (management-dashboard-state.json) that
reviewer.py reads and merges into the /snapshot endpoint the frontend
already expects.

It does NOT talk to Qwen about new entries -- that stays entirely in
reviewer.py. The two processes currently still share one Qwen/Ollama model
instance (see review_shared.model_generation_lock) -- splitting the code is
not the same as splitting the model; that is future hardware-dependent work.
"""

import json
import logging
import logging.handlers
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5

import build_manifest
import live_mapped_levels
import process_logging
import management_policy
import trade_geometry
from instrument_config import instrument_for
from market_context_cache import latest_entry_context, latest_readiness
from review_shared import (
    DEFAULT_MANAGEMENT_STATE,
    LOG_DIR,
    MANAGEMENT_STATE_FILE,
    PROTECTION_STATE_FILE,
    MODEL,
    QWEN_MAGIC,
    STORE_ROOT,
    _dated_log_files,
    _dated_log_path,
    connect_mt5,
    is_qwen_owned,
    load_review_tickets,
    normalize_confidence,
    normalize_invalidation,
    normalize_text,
    ollama_generate,
    read_json_safe,
    gold_market_open,
    require_gpu,
    sync_model_residency,
    write_json_atomic,
)
from runtime_config import PRIMARY_MARKET_SYMBOL, model_for_role
from intraday_observer.contracts import (
    CONTRACT_VERSION as INTRADAY_OBSERVER_CONTRACT,
    read_for_trader as read_intraday_observer,
)

MANAGEMENT_MODEL = model_for_role("management")
from tick_data_archive import append_qwen_decision, append_tick_record
from trade_manager import (
    GUARD_TIMEOUT_CYCLES,
    build_management_facts,
    build_management_prompt,
    decision_is_currently_applicable,
    management_schema,
    safety_guard,
    timeout_guard,
    unavailable_hold,
    validate_management_decision,
)


# Same env var reviewer.py's entry loop reads a separate one for -- kept
# distinct on purpose (QWEN_REVIEW_INTERVAL_SECONDS here vs.
# QWEN_ENTRY_INTERVAL_SECONDS in reviewer.py) so the two cadences can be
# tuned independently once real hardware numbers are in from the faster GPU
# machine, without conflating "how often to check for a new setup" with
# "how often to review a live trade".
import os

INTERVAL_SECONDS = int(os.environ.get("QWEN_REVIEW_INTERVAL_SECONDS", "30"))
INTRADAY_OBSERVER_PROMOTED = os.environ.get("QWEN_INTRADAY_OBSERVER_LIVE", "0") == "1"
# The executor installs a generic +/-5.0-price symmetric safety bracket at
# entry, not Qwen's own reference SL/TP (considered and explicitly rejected
# on 2026-08-06 -- Qwen's own levels are often too tight to use as the
# immediate entry-time bracket). This process is the intended path for those
# levels to actually take effect over the life of the trade: it may tighten
# the SL and/or replace the TP with a validated named level once the
# completed-candle management contract confirms it.
AUTO_MANAGE_QWEN_OWNED = True

LAST_MANAGED_M1_BY_TICKET: dict[int, str] = {}
LAST_REGIME_HINT: dict[str, float | str | None] = {"hint": None, "atr_ratio": None}
CONSECUTIVE_QWEN_FAILURES: dict[int, int] = {}
ENTRY_CONTEXT_BY_TICKET: dict[int, dict] = {}
EXECUTION_MONITOR_BY_ID: dict[str, dict] = {}
# Tracks (file, byte offset) for the incremental executions tail below. The
# file changes at midnight, which naturally resets the offset to 0 for the
# new day's file.
PAPER_EXECUTION_TAIL_STATE = {"path": None, "offset": 0}

# Trade-path state used by the completed-M1 Qwen management review. Fast
# broker protection is owned independently by profit_protection.py at tick
# cadence; this process must not duplicate or race that stop ladder.

# Peak favorable price move tracked per ticket across management cycles.
# Cleared by reconcile_position_state when the position closes.

_LOG_HANDLER = process_logging.configure(
    LOG_DIR / "trade-management.log", owner="trade_management"
)
# Announce the build and alarm if it has drifted from the declared freeze.
build_manifest.log_identity("trade_management")


def _model_status_label(model: str = MODEL) -> str:
    """Live Ollama residency label: Loaded on GPU|CPU|MIXED, or Unloaded."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=2) as response:
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
        if not resident:
            return "Unloaded"
        size = int(resident.get("size") or 0)
        vram = int(resident.get("size_vram") or 0)
        if vram <= 0:
            return "Loaded on CPU"
        if size > 0 and vram >= size * 0.9:
            return "Loaded on GPU"
        return "Loaded MIXED"
    except Exception:
        return "Status unknown"


def position_to_dict(position) -> dict:
    return {
        "ticket": position.ticket,
        "symbol": position.symbol,
        "side": "buy" if position.type == mt5.POSITION_TYPE_BUY else "sell",
        "volume": position.volume,
        "open_price": position.price_open,
        "current_price": position.price_current,
        "stop_loss": position.sl,
        "take_profit": position.tp,
        "profit": position.profit,
        "swap": position.swap,
        "magic": position.magic,
        "comment": position.comment,
        "opened_at": datetime.fromtimestamp(position.time, timezone.utc).isoformat(),
    }


def deal_to_dict(deal) -> dict:
    return {
        "ticket": deal.ticket,
        "order": deal.order,
        "position_id": deal.position_id,
        "symbol": deal.symbol,
        "side": "buy" if deal.type == mt5.DEAL_TYPE_BUY else "sell",
        "entry": deal.entry,
        "volume": deal.volume,
        "price": deal.price,
        "profit": deal.profit,
        "commission": deal.commission,
        "swap": deal.swap,
        "magic": deal.magic,
        "comment": deal.comment,
        "executed_at": datetime.fromtimestamp(deal.time, timezone.utc).isoformat(),
    }


def _mapped_trade_level_prices(symbol: str, current_price: float | None = None) -> dict:
    """Operator / history-mapped shelves for management ladder + UI."""
    from regime_engine import mapped_level_within_distance

    path = Path(__file__).resolve().parent / "mapped_trade_levels.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not instrument_for(symbol).accepts(
        str(payload.get("symbol") or symbol)
    ):
        return {}
    out = {}
    for row in payload.get("levels") or []:
        level_id = str(row.get("level_id") or "").strip()
        if not level_id:
            continue
        try:
            lo = float(row["zone_low"])
            hi = float(row.get("zone_high", lo))
        except (KeyError, TypeError, ValueError):
            continue
        mid = (lo + hi) / 2.0
        if not mapped_level_within_distance(mid, current_price):
            continue
        out[level_id] = mid
    return out


def _live_mapped_chart_prices(symbol: str) -> dict:
    """Same live swing map the entry model sees, for the management UI."""
    cache_levels = {}
    try:
        entry = latest_entry_context(symbol)
    except Exception:
        entry = {}
    if str(entry.get("status") or "") == "ready":
        for row in entry.get("levels") or []:
            if str(row.get("calculation_method") or "") != "live_closed_swing":
                continue
            level_id = str(row.get("level_id") or "")
            if not level_id:
                continue
            try:
                cache_levels[level_id] = (
                    float(row["zone_low"]) + float(row.get("zone_high", row["zone_low"]))
                ) / 2.0
            except (KeyError, TypeError, ValueError):
                continue
        if cache_levels:
            return cache_levels
    timeframes = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
    }
    seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400}
    completed = {}
    closed_m1 = None
    for tag, timeframe in timeframes.items():
        rates = mt5.copy_rates_from_pos(
            symbol, timeframe, 1, live_mapped_levels.LOOKBACK[tag]
        )
        if rates is None:
            continue
        rows = []
        for rate in sorted(rates, key=lambda item: int(item["time"])):
            opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
            closed = opened + timedelta(seconds=seconds[tag])
            row = {
                "evidence_id": f"candle:{symbol}:{tag}:{opened.strftime('%Y-%m-%dT%H:%M:%SZ')}",
                "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
                "close_time_utc": closed.isoformat().replace("+00:00", "Z"),
                "open": float(rate["open"]),
                "high": float(rate["high"]),
                "low": float(rate["low"]),
                "close": float(rate["close"]),
                "tick_volume": int(rate["tick_volume"]),
            }
            rows.append(row)
        completed[tag] = rows
        if tag == "M1" and rows:
            closed_m1 = rows[-1]
    tick = mt5.symbol_info_tick(symbol)
    price = float(tick.bid) if tick else 0.0
    out = {}
    for row in live_mapped_levels.build_from_completed(completed, closed_m1, price):
        out[row["level_id"]] = (row["zone_low"] + row["zone_high"]) / 2.0
    return out


def chart_levels(symbol: str) -> dict:
    levels = {}
    timeframes = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
    }
    for tag, timeframe in timeframes.items():
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 2)
        if rates is None or len(rates) < 2:
            continue
        ordered = sorted(rates, key=lambda rate: int(rate["time"]))
        previous, current = ordered[-2], ordered[-1]
        levels[f"{tag}_CURRENT_OPEN"] = float(current["open"])
        levels[f"{tag}_PREVIOUS_HIGH"] = float(previous["high"])
        levels[f"{tag}_PREVIOUS_LOW"] = float(previous["low"])

    daily = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 2)
    if daily is not None and len(daily) >= 2:
        ordered = sorted(daily, key=lambda rate: int(rate["time"]))
        previous, current = ordered[-2], ordered[-1]
        high, low, close = (
            float(previous["high"]),
            float(previous["low"]),
            float(previous["close"]),
        )
        pivot = (high + low + close) / 3.0
        levels.update(
            {
                "D1_CURRENT_OPEN": float(current["open"]),
                "D1_CURRENT_HIGH": float(current["high"]),
                "D1_CURRENT_LOW": float(current["low"]),
                "D1_PREVIOUS_HIGH": high,
                "D1_PREVIOUS_LOW": low,
                "D1_PIVOT": pivot,
                "D1_R1": 2.0 * pivot - low,
                "D1_S1": 2.0 * pivot - high,
            }
        )
    tick = mt5.symbol_info_tick(symbol)
    current_price = float(tick.bid) if tick else None
    levels.update(_mapped_trade_level_prices(symbol, current_price=current_price))
    levels.update(_live_mapped_chart_prices(symbol))
    return levels


def historical_respect_counts(symbol: str, flat_levels: dict) -> dict:
    """Count distinct 15-day reactions around each M30/H1/H4 named level."""
    counts = {}
    timeframe_map = {
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
    }
    bars_per_day = {"M30": 48, "H1": 24, "H4": 6}
    for tag, timeframe in timeframe_map.items():
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, bars_per_day[tag] * 15)
        if rates is None:
            continue
        tag_levels = {
            level_id: float(price)
            for level_id, price in flat_levels.items()
            if level_id.startswith(f"{tag}_")
        }
        for level_id, level in tag_levels.items():
            tolerance = max(0.35, level * 0.00010)
            respected = 0
            touching_previous = False
            for rate in sorted(rates, key=lambda item: int(item["time"])):
                high = float(rate["high"])
                low = float(rate["low"])
                opened = float(rate["open"])
                closed = float(rate["close"])
                touched = low - tolerance <= level <= high + tolerance
                rejected = touched and (
                    (low <= level + tolerance and closed > level and closed >= opened)
                    or (high >= level - tolerance and closed < level and closed <= opened)
                )
                if rejected and not touching_previous:
                    respected += 1
                touching_previous = touched
            counts[level_id] = respected
    return counts


def levels_for_ui(flat_levels: dict, symbol: str = None) -> dict:
    grouped = {}
    respect_counts = historical_respect_counts(symbol, flat_levels) if symbol else {}
    from qualified_levels import load_qualified_level_ids

    qualified_ids = load_qualified_level_ids()
    for level_id, price in flat_levels.items():
        timeframe = level_id.split("_", 1)[0]
        role = level_id.replace(f"{timeframe}_", "").replace("_", " ").title()
        cited = level_id in qualified_ids
        grouped.setdefault(timeframe, []).append(
            {
                "id": level_id,
                "price": price,
                "role": role,
                "respect_count": respect_counts.get(level_id, 0),
                "qualified": cited,
                "display": "qualified" if cited else "candidate",
            }
        )
    for timeframe in grouped:
        grouped[timeframe].sort(key=lambda item: item["price"], reverse=True)
    return grouped


def recent_candle_context(symbol: str) -> dict:
    """Capture closed candles so Qwen can see reactions, wicks, and oscillation."""
    output = {}
    for tag, timeframe in (("M1", mt5.TIMEFRAME_M1), ("M5", mt5.TIMEFRAME_M5)):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 1, 5)
        rows = []
        if rates is not None:
            for rate in sorted(rates, key=lambda item: int(item["time"])):
                closed_at = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
                opened = float(rate["open"])
                high = float(rate["high"])
                low = float(rate["low"])
                closed = float(rate["close"])
                rows.append(
                    {
                        "time_utc": closed_at.strftime("%H:%M"),
                        "closed_at_utc": closed_at.isoformat(),
                        "evidence_id": f"candle:{tag}:{closed_at.isoformat()}",
                        "open": opened,
                        "high": high,
                        "low": low,
                        "close": closed,
                        "direction": (
                            "up" if closed > opened else "down" if closed < opened else "flat"
                        ),
                        "body": round(abs(closed - opened), 3),
                        "upper_wick": round(high - max(opened, closed), 3),
                        "lower_wick": round(min(opened, closed) - low, 3),
                    }
                )
        output[tag] = rows
    return output


def today_basket_summary(now: datetime) -> dict:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now) or []
    executions = [
        deal
        for deal in deals
        if deal.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL)
        and deal.magic == QWEN_MAGIC
    ]
    by_position = {}
    for deal in executions:
        by_position.setdefault(deal.position_id, []).append(deal)
    durations = []
    for position_deals in by_position.values():
        times = sorted(deal.time for deal in position_deals)
        if len(times) >= 2:
            durations.append(times[-1] - times[0])
    durations.sort()
    closed_profits = []
    for position_deals in by_position.values():
        if len(position_deals) >= 2:
            closed_profits.append(
                sum(deal.profit + deal.commission + deal.swap for deal in position_deals)
            )
    return {
        "deal_count": len(executions),
        "position_count": len(by_position),
        "net_profit": sum(
            deal.profit + deal.commission + deal.swap for deal in executions
        ),
        "median_hold_seconds": durations[len(durations) // 2] if durations else None,
        "max_hold_seconds": max(durations) if durations else None,
        "win_rate": (
            round(100 * sum(profit > 0 for profit in closed_profits) / len(closed_profits))
            if closed_profits
            else 0
        ),
    }


def update_dashboard(positions, levels_by_symbol, today, review=None, protection=None) -> None:
    """Write this process's own dashboard-state file.

    Reads the file back first (rather than starting from
    DEFAULT_MANAGEMENT_STATE each time) so a review-less cycle -- e.g. no
    Qwen-owned position open -- doesn't clobber the last "qwen_management"
    commentary reviewer.py may still be surfacing for a just-closed trade.
    """
    symbol = next(iter(levels_by_symbol), PRIMARY_MARKET_SYMBOL)
    tick = mt5.symbol_info_tick(symbol)
    review_tickets = load_review_tickets()
    position_rows = []
    for position in positions:
        row = position_to_dict(position)
        row["under_review"] = position.ticket in review_tickets
        row["qwen_owned"] = is_qwen_owned(position)
        position_rows.append(row)
    ui_levels = levels_for_ui(levels_by_symbol.get(symbol, {}), symbol)
    qualified_rows = []
    candidate_rows = []
    for rows in ui_levels.values():
        for row in rows:
            (qualified_rows if row.get("qualified") else candidate_rows).append(row)
    state = read_json_safe(MANAGEMENT_STATE_FILE, DEFAULT_MANAGEMENT_STATE)
    state.update(
        {
            "connected": True,
            "model": MODEL,
            "model_status": _model_status_label(),
            "symbol": symbol,
            "price": tick.bid if tick else 0.0,
            "change": 0.0,
            "levels": ui_levels,
            "level_display": {
                "qualified": qualified_rows,
                "candidate": candidate_rows,
            },
            "market_context": recent_candle_context(symbol),
            "positions": position_rows,
            "today": {
                "net_profit": today["net_profit"],
                "baskets": today["position_count"],
                "deals": today["deal_count"],
                "median_hold_seconds": today["median_hold_seconds"] or 0,
                "win_rate": today["win_rate"],
            },
            "context_cache": latest_readiness(symbol),
            "profit_protection": protection or read_json_safe(PROTECTION_STATE_FILE, {}),
        }
    )
    if review:
        review_summary = review.get("summary", "")
        inferred_bias = (
            review_summary.get("bias", "Reviewed")
            if isinstance(review_summary, dict)
            else "Reviewed"
        )
        state["qwen_management"] = {
            "bias": review.get("bias", inferred_bias),
            "confidence": normalize_confidence(review.get("confidence"), 65),
            "summary": normalize_text(review_summary, "No summary returned."),
            "invalidation": normalize_invalidation(
                review.get("invalidation"),
                review.get("execution_plan"),
            ),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    write_json_atomic(MANAGEMENT_STATE_FILE, state)


def valid_level_for_position(position, level: float, purpose: str) -> bool:
    tick = mt5.symbol_info_tick(position.symbol)
    info = mt5.symbol_info(position.symbol)
    if tick is None or info is None:
        return False
    minimum = max(info.trade_stops_level * info.point, info.point)
    if position.type == mt5.POSITION_TYPE_BUY:
        return level < tick.bid - minimum if purpose == "sl" else level > tick.ask + minimum
    return level > tick.ask + minimum if purpose == "sl" else level < tick.bid - minimum


def close_qwen_owned_positions(positions) -> list:
    results = []
    for original in positions:
        live = mt5.positions_get(ticket=original.ticket)
        if not live or not is_qwen_owned(live[0]):
            continue
        position = live[0]
        tick = mt5.symbol_info_tick(position.symbol)
        if tick is None:
            continue
        is_buy = position.type == mt5.POSITION_TYPE_BUY
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": position.ticket,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": QWEN_MAGIC,
            "comment": "QWEN_MGR_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        results.append(
            {
                "ticket": position.ticket,
                "retcode": result.retcode if result else None,
                "comment": result.comment if result else str(mt5.last_error()),
            }
        )
    return results


def management_decision_context(
    *,
    facts: dict,
    entry: dict,
    parsed_review: dict,
    guard_review: dict | None,
    applications: list,
    close_results: list,
    stale_for_execution: bool,
    decision_still_applicable: bool,
    response_age_seconds: float,
    live_price: float | None,
) -> dict:
    """The state the manager was looking at when it decided, in one flat row.

    2026-08-11 -- why this is here
    -----------------------------
    Trade management is where the exit decision is going to be made -- not by a
    static SL and TP, because the idea behind a trade changes while the trade is
    running. For the manager to get better at that, every decision it makes has
    to be scoreable afterwards, and that means recording what it SAW, not only
    what it chose.

    Before this, a close decision stored the action and the proposal id. You
    could see that it closed; you could not ask the question that matters --
    "was closing right?" -- because the position's progress toward target, how
    much open profit it gave back, how far into its risk it was, and which rule
    fired were all absent. Answering it meant re-deriving state from candles
    after the fact, which nobody does.

    Each field is here because it discriminates a good exit from a bad one:

      r_multiple          -- closing at -0.9R is a different act from -0.1R
      target_progress     -- closing at 80% of target is not the same mistake
                             as closing at 5%
      giveback_price      -- distinguishes "protected a gain" from "panicked"
      peak_favorable      -- the trade's best moment; the benchmark any exit
                             is judged against
      decided_by          -- separates the deterministic guard's exits from the
                             model's, so their records never get pooled
      executed            -- a decision that did not reach the broker must not
                             be scored as though it did
    """
    position = facts.get("position") or {}
    path = facts.get("trade_path") or {}
    levels = facts.get("level_references") or {}
    planned_target = levels.get("planned_target") or {}
    planned_invalidation = levels.get("planned_invalidation") or {}

    side = position.get("side")
    entry_price = position.get("entry")
    current = live_price if live_price is not None else position.get("current")

    def _float(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    entry_price = _float(entry_price)
    current = _float(current)
    stop = _float(planned_invalidation.get("price"))
    target = _float(planned_target.get("price"))

    direction = 1.0 if side == "buy" else -1.0
    risk = abs(entry_price - stop) if entry_price is not None and stop else None
    span = (
        direction * (target - entry_price)
        if entry_price is not None and target is not None
        else None
    )
    travelled = (
        direction * (current - entry_price)
        if entry_price is not None and current is not None
        else None
    )

    r_multiple = (
        round(travelled / risk, 3) if travelled is not None and risk else None
    )
    target_progress = (
        round(max(0.0, min(1.0, travelled / span)), 3)
        if travelled is not None and span and span > 0
        else None
    )

    action = parsed_review.get("action")
    return {
        "management_contract": facts.get("contract"),
        "decided_by": "deterministic_guard" if guard_review else "model",
        "action": action,
        "confidence": parsed_review.get("confidence"),
        "validation_failures": parsed_review.get("validation_failures") or [],
        # Did this decision actually reach the broker? A close that was stale
        # by the time it returned changed nothing and must not be scored.
        "executed": bool(close_results) if action == "close" else bool(applications),
        "stale_for_execution": bool(stale_for_execution),
        "decision_still_applicable": bool(decision_still_applicable),
        "response_age_seconds": round(float(response_age_seconds), 3),
        # --- what the trade was doing at the moment of the decision ---
        "side": side,
        "entry_price": entry_price,
        "price_at_decision": current,
        "r_multiple": r_multiple,
        "target_progress": target_progress,
        "favorable_price_move": position.get("favorable_price_move"),
        "peak_favorable_price_move": path.get("peak_favorable_price_move"),
        "giveback_price": path.get("current_giveback_price"),
        "peak_gross_pnl": path.get("peak_gross_pnl"),
        "gross_pnl_at_decision": position.get("gross_pnl"),
        "broker_stop_at_decision": position.get("broker_stop"),
        # --- the plan it is being measured against ---
        "planned_target_level_id": planned_target.get("level_id"),
        "planned_target_price": target,
        "planned_invalidation_level_id": planned_invalidation.get("level_id"),
        "planned_invalidation_price": stop,
        "initial_risk_price": round(risk, 3) if risk else None,
        "furthest_reached_level_ref": path.get("furthest_reached_level_ref"),
        "entry_reason": (facts.get("entry_thesis") or {}).get("reason"),
        "entry_proposal_id": entry.get("proposal_id"),
    }


def active_entry_context(position) -> dict | None:
    """Recover the immutable entry thesis for the one managed position."""
    cached = ENTRY_CONTEXT_BY_TICKET.get(int(position.ticket))
    if cached:
        return cached
    suffix = str(position.comment).removeprefix("QWEN_")
    started = None
    for path in _dated_log_files("paper-executions"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                event.get("event") == "mt5_execution_started"
                and str(event.get("execution_id", "")).endswith(suffix)
            ):
                started = event
                break
        if started:
            break
    if not started:
        return None
    proposal_id = started.get("proposal_id")
    for path in _dated_log_files("paper-proposals"):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                proposal = json.loads(line)
            except json.JSONDecodeError:
                continue
            if proposal.get("proposal_id") == proposal_id:
                context = {
                    "execution_id": started["execution_id"],
                    "proposal_id": proposal_id,
                    "plan": proposal.get("qwen", {}).get("execution_plan", {}),
                }
                ENTRY_CONTEXT_BY_TICKET[int(position.ticket)] = context
                return context
    return None


def refresh_execution_monitor_cache() -> None:
    """Incrementally recover each active execution's exact peak/giveback path.

    Reads paper-path, not paper-executions: the per-tick monitor rows were split
    out on 2026-08-11 because they were 96.7% of the execution log. This tail is
    their only consumer, and it now reads a file containing nothing else, so it
    parses one line per tick instead of skipping thirty.
    """
    path = _dated_log_path("paper-path")
    if PAPER_EXECUTION_TAIL_STATE["path"] != path:
        # Local midnight rolled over to a new (initially empty) file. Start
        # a fresh tail on it from offset 0; EXECUTION_MONITOR_BY_ID is left
        # alone since any still-open position keeps getting fresh monitor
        # events under the same execution_id in the new file.
        PAPER_EXECUTION_TAIL_STATE["path"] = path
        PAPER_EXECUTION_TAIL_STATE["offset"] = 0
    if not path.exists():
        return
    size = path.stat().st_size
    if size < PAPER_EXECUTION_TAIL_STATE["offset"]:
        PAPER_EXECUTION_TAIL_STATE["offset"] = 0
        EXECUTION_MONITOR_BY_ID.clear()
    with path.open("r", encoding="utf-8") as stream:
        stream.seek(PAPER_EXECUTION_TAIL_STATE["offset"])
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            execution_id = event.get("execution_id")
            if event.get("event") == "mt5_execution_monitor" and execution_id:
                EXECUTION_MONITOR_BY_ID[execution_id] = {
                    "created_at_utc": event.get("created_at_utc"),
                    "mark": event.get("mark"),
                    "peak_favorable_price_move": event.get(
                        "peak_favorable_price_move", 0.0
                    ),
                    "peak_pnl": event.get("peak_pnl"),
                    "price_giveback": event.get("price_giveback", 0.0),
                    "maximum_drawdown": event.get("maximum_drawdown"),
                }
            elif event.get("event") == "mt5_execution_closed" and execution_id:
                EXECUTION_MONITOR_BY_ID.pop(execution_id, None)
        # Use the size captured before reading. If the executor appends during
        # this pass, the extra bytes are intentionally consumed next cycle.
        PAPER_EXECUTION_TAIL_STATE["offset"] = size


def execution_management_state(entry: dict) -> dict:
    refresh_execution_monitor_cache()
    return dict(EXECUTION_MONITOR_BY_ID.get(entry.get("execution_id"), {}))


def recent_management_history(ticket: int, limit: int = 3) -> list[dict]:
    """Recover compact prior decisions so management calls are not stateless."""
    records = []
    review_files = sorted(LOG_DIR.glob("reviews-*.jsonl"), reverse=True)[:2]
    for path in review_files:
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            positions = record.get("snapshot", {}).get("positions", [])
            position = next(
                (row for row in positions if int(row.get("ticket", 0)) == ticket),
                None,
            )
            if not position:
                continue
            decision = record.get("review", {})
            trade_path = record.get("snapshot", {}).get(
                "management_facts", {}
            ).get("trade_path", {})
            records.append(
                {
                    "timestamp_utc": record.get("timestamp_utc"),
                    "observed_price": position.get("current_price"),
                    "observed_gross_pnl": position.get("profit"),
                    "action": decision.get("action"),
                    "thesis_state": decision.get("thesis_state"),
                    "decision_level_ref": decision.get("decision_level_ref"),
                    "summary": decision.get("summary"),
                    "peak_price": trade_path.get("peak_price"),
                    "reached_favorable_level_refs": trade_path.get(
                        "reached_favorable_level_refs", []
                    ),
                }
            )
            if len(records) >= limit:
                return list(reversed(records))
    return list(reversed(records))


def apply_confirmed_protection(position, decision: dict, facts: dict) -> list:
    """Replace the temporary bracket with deterministically validated structure levels."""
    if decision.get("action") != "protect":
        return []
    live = mt5.positions_get(ticket=position.ticket)
    if not live or not is_qwen_owned(live[0]):
        return []
    position = live[0]
    references = facts.get("level_references", {})
    sl_reference = references.get(decision.get("decision_level_ref"))
    tp_reference = references.get(decision.get("next_target_ref"))
    old_sl = float(position.sl or 0.0)
    old_tp = float(position.tp or 0.0)
    new_sl = old_sl
    new_tp = old_tp
    if sl_reference:
        candidate_sl = float(sl_reference["price"])
        # Management may only reduce broker risk. Initial structural bracket
        # correction is handled separately by initial_rebracket().
        tighter = (
            not old_sl
            or (position.type == mt5.POSITION_TYPE_BUY and candidate_sl > old_sl)
            or (position.type != mt5.POSITION_TYPE_BUY and candidate_sl < old_sl)
        )
        if tighter and valid_level_for_position(position, candidate_sl, "sl"):
            new_sl = candidate_sl
    if tp_reference:
        candidate_tp = float(tp_reference["price"])
        tracked = management_policy.Position(
            side="buy" if position.type == mt5.POSITION_TYPE_BUY else "sell",
            entry_price=float(position.price_open), stop_loss=old_sl,
            take_profit=old_tp, volume=float(position.volume), opened_at=0.0,
            frame=None,
        )
        adjustment = management_policy.propose_target(
            tracked, candidate_tp, price=float(position.price_current),
            level_id=decision.get("next_target_ref"),
        )
        if adjustment.accepted and valid_level_for_position(position, candidate_tp, "tp"):
            new_tp = candidate_tp
    if new_sl == old_sl and new_tp == old_tp:
        return []
    result = mt5.order_send(
        {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": new_tp,
        }
    )
    return [
        {
            "ticket": position.ticket,
            "sl_level_ref": decision.get("decision_level_ref"),
            "tp_level_ref": decision.get("next_target_ref"),
            "old_sl": old_sl,
            "new_sl": new_sl,
            "old_tp": old_tp,
            "new_tp": new_tp,
            "retcode": result.retcode if result else None,
            "comment": result.comment if result else str(mt5.last_error()),
        }
    ]


# Tickets already re-bracketed this process lifetime, so the correction runs
# once per position rather than every cycle.
_REBRACKETED_TICKETS: set[int] = set()


def structural_levels_for(position, levels_by_symbol: dict) -> tuple[float | None, float | None, str | None, str | None]:
    """Nearest named invalidation behind the position and target in front of it.

    Read from the same chart-levels map the dashboard uses, so no model call and
    no cache round-trip is required -- this has to complete inside 30s.
    """
    # chart_levels() returns {level_id: price}. Only PREVIOUS_HIGH / PREVIOUS_LOW
    # are structural invalidations; *_CURRENT_OPEN is the live bar's open and
    # moves under the position, so it is excluded.
    rows = (levels_by_symbol or {}).get(position.symbol) or {}
    entry = float(position.price_open)
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    behind: list[tuple[float, str, float]] = []
    ahead: list[tuple[float, str, float]] = []
    for name, value in (rows.items() if isinstance(rows, dict) else []):
        if "PREVIOUS_HIGH" not in name and "PREVIOUS_LOW" not in name:
            continue
        try:
            price = float(value)
        except (TypeError, ValueError):
            continue
        if not price:
            continue
        if is_buy:
            (behind if price < entry else ahead).append((abs(entry - price), name, price))
        else:
            (behind if price > entry else ahead).append((abs(price - entry), name, price))
    behind.sort()
    ahead.sort()
    stop = behind[0] if behind else None
    target = ahead[0] if ahead else None
    return (
        stop[2] if stop else None,
        target[2] if target else None,
        stop[1] if stop else None,
        target[1] if target else None,
    )


def rebracket_if_needed(position, levels_by_symbol: dict) -> None:
    """Rewrite SL and TP to structure once, within 30s of fill."""
    if position.ticket in _REBRACKETED_TICKETS:
        return

    opened_at = float(position.time)
    now = time.time()
    tick = mt5.symbol_info_tick(position.symbol)
    price = float(getattr(tick, "bid", 0) or position.price_current or position.price_open)

    stop_px, target_px, stop_id, target_id = structural_levels_for(
        position, levels_by_symbol
    )
    # Place the stop BEYOND the level, not on it -- the same buffer entry
    # geometry applies. A stop resting exactly on the invalidation is taken out
    # by the first touch, before the level has actually failed.
    if stop_px is not None:
        buffer_amount = trade_geometry.structure_buffer(abs(stop_px - float(position.price_open)))
        is_buy = position.type == mt5.POSITION_TYPE_BUY
        stop_px = stop_px - buffer_amount if is_buy else stop_px + buffer_amount

    # The executor now places the immutable planned invalidation at the broker
    # before the position exists. Once filled, this path must never add risk.
    #
    # Observed live within minutes of wiring Stage 3:
    #   19:02:42  entry bracket stop 4316.369, beyond H1_PREVIOUS_LOW, 8.84 away
    #   19:03:03  re-bracket TIGHTENED it to 4324.578 on M5_PREVIOUS_HIGH
    #             and pulled the target in from 4337.985 to 4325.541
    #   19:03:04  stopped out, -49.50
    #
    # structural_levels_for() returns the NEAREST level either side. Once the
    # executor places a correct structural bracket, the nearest level is always
    # tighter than the invalidation the trade was actually built on -- so the
    # correction systematically destroys the geometry it exists to protect.
    #
    # The purpose of this re-bracket is to rescue a bracket sitting INSIDE the
    # invalidation. A bracket already at or beyond structure needs no rescue.
    current_sl = float(position.sl or 0.0)
    current_tp = float(position.tp or 0.0)
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    # Track WHY a level was withdrawn. Withdrawn because the live bracket is
    # already at least as good is a success; never offered at all is not. Both
    # reach initial_rebracket() as None, and conflating them made a healthy
    # trade log ERROR ... still on its entry bracket ... (no structural stop or
    # target supplied) every 30s until it closed.
    stop_already_adequate = False
    target_already_adequate = False
    if current_sl:
        # A live SL is the accepted entry invalidation. The initial correction
        # may add a missing SL, but may never replace one with a wider stop.
        stop_px = None
        stop_already_adequate = True
    if target_px is not None and current_tp:
        # Never pull the target closer than the one the entry was built on.
        if is_buy and target_px <= current_tp:
            target_px = None
            target_already_adequate = True
        if not is_buy and target_px >= current_tp:
            target_px = None
            target_already_adequate = True
    bracket_already_adequate = stop_already_adequate or target_already_adequate
    tracked = management_policy.Position(
        side="buy" if position.type == mt5.POSITION_TYPE_BUY else "sell",
        entry_price=float(position.price_open),
        stop_loss=float(position.sl or 0.0),
        take_profit=float(position.tp or 0.0),
        volume=float(position.volume),
        opened_at=opened_at,
        frame=None,
    )
    rebracket = management_policy.initial_rebracket(
        tracked,
        price=price,
        structural_stop=stop_px,
        structural_target=target_px,
        now=now,
        stop_level_id=stop_id,
        target_level_id=target_id,
    )
    if not rebracket.applied:
        if bracket_already_adequate:
            # The entry bracket is at or beyond structure. There is nothing to
            # rescue, which is the outcome this whole path wants.
            logging.info(
                "rebracket not needed ticket=%s: entry bracket already at or "
                "beyond structure (sl=%.3f tp=%.3f)",
                position.ticket, current_sl, current_tp,
            )
        elif management_policy.rebracket_overdue(tracked, now):
            logging.error(
                "ALARM %s :: ticket %s still on its entry bracket %.0fs after fill (%s)",
                management_policy.AdjustReason.REBRACKET_OVERDUE,
                position.ticket,
                now - opened_at,
                rebracket.detail,
            )
        return

    new_sl = rebracket.stop.new_value if rebracket.stop else float(position.sl or 0.0)
    new_tp = rebracket.target.new_value if rebracket.target else float(position.tp or 0.0)
    result = mt5.order_send(
        {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": position.ticket,
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": new_tp,
        }
    )
    retcode = getattr(result, "retcode", None)
    for adjustment in (rebracket.stop, rebracket.target):
        if adjustment:
            logging.info(management_policy.format_adjustment(adjustment))
    logging.info(
        "rebracket applied ticket=%s %.1fs after fill sl=%.3f tp=%.3f retcode=%s%s",
        position.ticket,
        now - opened_at,
        new_sl,
        new_tp,
        retcode,
        " CLIPPED-TO-RISK-CEILING" if rebracket.clipped else "",
    )
    if retcode == getattr(mt5, "TRADE_RETCODE_DONE", 10009):
        _REBRACKETED_TICKETS.add(position.ticket)
    else:
        logging.error(
            "rebracket:order_send_failed ticket=%s retcode=%s comment=%s",
            position.ticket,
            retcode,
            getattr(result, "comment", mt5.last_error()),
        )


def reconcile_position_state(live_tickets: set[int]) -> None:
    """Drop every cached belief about a position the broker no longer has.

    2026-08-11 -- why this exists
    -----------------------------
    Four dictionaries here are keyed by ticket or execution id and were only
    ever added to:

        LAST_MANAGED_M1_BY_TICKET   ENTRY_CONTEXT_BY_TICKET
        _REBRACKETED_TICKETS        EXECUTION_MONITOR_BY_ID

    Nothing removed an entry when its position closed. In a long-running
    process that is three separate problems. It leaks memory. It keeps an entry
    thesis for a trade that ended hours ago. And -- the one that can actually
    cost money -- MT5 reuses ticket numbers, so a stale `_REBRACKETED_TICKETS`
    entry would make a NEW position look already re-bracketed and silently skip
    the correction that moves its stop beyond structure.

    That mattered on 2026-08-11: the executor died mid-trade and six positions
    ended without the executor ever recording a close, so every cache here kept
    state for trades that were long gone.

    The rule is simple and worth stating plainly: MT5 is the truth. Anything
    this process believes about an open position is a derived cache, and a
    cache that disagrees with the broker is wrong by definition. Reconciling
    every cycle -- not only when the position count reaches zero -- also covers
    the partial case where one of two positions closes.
    """
    stale_tickets = (
        set(LAST_MANAGED_M1_BY_TICKET) | set(ENTRY_CONTEXT_BY_TICKET)
        | set(_REBRACKETED_TICKETS) | set(CONSECUTIVE_QWEN_FAILURES)
    ) - live_tickets
    if not stale_tickets and (live_tickets or not EXECUTION_MONITOR_BY_ID):
        return

    for ticket in stale_tickets:
        LAST_MANAGED_M1_BY_TICKET.pop(ticket, None)
        CONSECUTIVE_QWEN_FAILURES.pop(ticket, None)
        ENTRY_CONTEXT_BY_TICKET.pop(ticket, None)
        _REBRACKETED_TICKETS.discard(ticket)

    dropped_monitors = 0
    if not live_tickets:
        # Nothing is open, so nothing in the execution-monitor cache can refer
        # to a live trade. Keyed by execution id rather than ticket, so this is
        # the only point at which it can be cleared with certainty.
        dropped_monitors = len(EXECUTION_MONITOR_BY_ID)
        EXECUTION_MONITOR_BY_ID.clear()

    if stale_tickets or dropped_monitors:
        logging.info(
            "position state reconciled against the broker: dropped %d closed "
            "ticket(s) %s and %d execution monitor entr(ies); live=%s",
            len(stale_tickets), sorted(stale_tickets) or "-",
            dropped_monitors, sorted(live_tickets) or "none",
        )


def review_positions() -> None:
    cycle_started = time.monotonic()
    positions = mt5.positions_get()
    if positions is None:
        raise RuntimeError(f"positions_get failed: {mt5.last_error()}")
    now = datetime.now(timezone.utc)
    recent_deals = mt5.history_deals_get(now - timedelta(seconds=75), now)
    if recent_deals is None:
        raise RuntimeError(f"history_deals_get failed: {mt5.last_error()}")
    symbols = sorted(
        {position.symbol for position in positions if position.symbol}
        | {deal.symbol for deal in recent_deals if deal.symbol}
    )
    if not symbols:
        symbols = [PRIMARY_MARKET_SYMBOL]
    levels_by_symbol = {symbol: chart_levels(symbol) for symbol in symbols}
    today = today_basket_summary(now)
    update_dashboard(positions, levels_by_symbol, today)
    # Qwen's execution loop sees only positions it owns. Manual and other-EA
    # positions remain dashboard-visible but never enter this management path.
    positions = tuple(position for position in positions if is_qwen_owned(position))
    # Broker truth first, before any decision is made from cached state. Runs
    # on every cycle including the empty one, so a position that closed while
    # this process was not looking cannot leave a belief behind.
    reconcile_position_state({int(p.ticket) for p in positions})
    if not positions:
        logging.info("No Qwen-owned open positions; Qwen remains loaded")
        return

    account = mt5.account_info()
    snapshot = {
        "review_time_utc": now.isoformat(),
        "account": {
            "login": account.login if account else None,
            "balance": account.balance if account else None,
            "equity": account.equity if account else None,
            "margin_free": account.margin_free if account else None,
        },
        "positions": [position_to_dict(position) for position in positions],
        "recent_deals": [deal_to_dict(deal) for deal in recent_deals[-10:]],
        "today_basket": today,
        "chart_levels": levels_by_symbol,
    }
    if len(positions) != 1:
        raise RuntimeError(
            f"Single-position manager refuses {len(positions)} simultaneous Qwen positions."
        )

    # Mandatory post-fill re-bracket, BEFORE any model call.
    #
    # Operator requirement: within 30s of fill both stop and target move to
    # structure regardless of their current values. This must be deterministic --
    # management cycles every 30s and inference takes 16-31s, so anything gated
    # on a model response cannot meet the deadline. The two fastest stop-outs on
    # 2026-08-10 died in 22s and 50s, before any review completed.
    try:
        rebracket_if_needed(positions[0], levels_by_symbol)
    except Exception:
        logging.exception("rebracket:failed")

    position = positions[0]
    entry = active_entry_context(position)
    if not entry or entry["plan"].get("status") != "ready":
        raise RuntimeError("Open Qwen position has no recoverable immutable entry plan.")
    primary_symbol = position.symbol
    market_context = recent_candle_context(primary_symbol)
    pos = position_to_dict(position)
    regime = {}
    try:
        from regime_engine import snapshot_regime

        regime = snapshot_regime(
            symbol=primary_symbol,
            current_price=float(pos["current_price"]),
            levels=levels_by_symbol.get(primary_symbol) or {},
            prev_regime=LAST_REGIME_HINT.get("hint"),
            prev_atr_ratio=LAST_REGIME_HINT.get("atr_ratio"),
        )
        LAST_REGIME_HINT["hint"] = regime.get("regime_hint")
        LAST_REGIME_HINT["atr_ratio"] = regime.get("atr_ratio_3_51")
        logging.info(
            "regime_hint=%s transition=%s atr_ratio=%s range=%s m5_swings=%s",
            regime.get("regime_hint"),
            regime.get("regime_transition"),
            regime.get("atr_ratio_3_51"),
            regime.get("range_detected"),
            regime.get("m5_swing_pattern"),
        )
    except Exception:
        logging.exception("regime_snapshot:failed")
        regime = {}
    facts = build_management_facts(
        pos,
        entry["plan"],
        levels_by_symbol[primary_symbol],
        market_context,
        execution_state=execution_management_state(entry),
        prior_management=recent_management_history(int(position.ticket)),
        regime_context=regime,
    )
    # Read-only, versioned context from the independent market-story observer.
    # It has no execution authority and cannot modify the immutable trade idea.
    facts["intraday_observer"] = (
        read_intraday_observer(primary_symbol)
        if INTRADAY_OBSERVER_PROMOTED
        else {
            "status": "shadow_only",
            "contract_version": INTRADAY_OBSERVER_CONTRACT,
            "execution_authority": False,
        }
    )
    protection = read_json_safe(PROTECTION_STATE_FILE, {})
    if int(protection.get("ticket") or 0) != int(position.ticket):
        protection = {}
    facts["profit_protection"] = protection
    candidate_stop = protection.get("candidate_stop")
    if protection.get("armed") and candidate_stop is not None:
        facts["level_references"]["profit_protection_floor"] = {
            "level_id": "PROFIT_PROTECTION_FLOOR",
            "price": float(candidate_stop),
            "source": "deterministic_mfe_atr_worker",
        }
    latest_management_candle = facts.get("latest_completed_m1")
    if not latest_management_candle:
        logging.warning(
            "Management review deferred ticket=%s reason=no_completed_m1; "
            "broker bracket and profit protection remain active",
            position.ticket,
        )
        return
    if LAST_MANAGED_M1_BY_TICKET.get(position.ticket) == latest_management_candle:
        logging.info(
            "Position %s already managed for %s",
            position.ticket,
            latest_management_candle,
        )
        return
    snapshot["management_facts"] = facts
    snapshot["regime_context"] = regime
    hard_stop = safety_guard(facts)
    model_used = MANAGEMENT_MODEL
    total_duration_ns = None
    prompt_text = None
    raw_response = None
    market_atr = None
    guard_review = None
    if hard_stop:
        guard_review = hard_stop
        raw_response = json.dumps(hard_stop, separators=(",", ":"))
        parsed_review, management_failures = validate_management_decision(
            hard_stop, facts
        )
        model_used = "safety_guard_invalidation"
        logging.info(
            "Safety guard ticket=%s action=%s level=%s",
            position.ticket,
            parsed_review.get("action"),
            parsed_review.get("decision_level_ref"),
        )
    else:
        prompt_text = build_management_prompt(facts, STORE_ROOT)
        try:
            result = ollama_generate(
                prompt_text,
                timeout=None,
                num_predict=512,
                num_ctx=4096,
                format_schema=management_schema(facts),
                model=MANAGEMENT_MODEL,
            )
            total_duration_ns = result.get("total_duration")
            market_atr = result.get("market_atr")
            raw_response = result.get("response", "{}")
            raw_review = json.loads(raw_response)
            parsed_review, management_failures = validate_management_decision(
                raw_review, facts
            )
            CONSECUTIVE_QWEN_FAILURES[position.ticket] = 0
            model_used = MANAGEMENT_MODEL
        except Exception as exc:
            ticket = int(position.ticket)
            CONSECUTIVE_QWEN_FAILURES[ticket] = (
                CONSECUTIVE_QWEN_FAILURES.get(ticket, 0) + 1
            )
            failures_count = CONSECUTIVE_QWEN_FAILURES[ticket]
            logging.warning(
                "Qwen failure %d/%d for ticket=%s: %s",
                failures_count,
                GUARD_TIMEOUT_CYCLES,
                ticket,
                exc,
            )
            if failures_count >= GUARD_TIMEOUT_CYCLES:
                guard_review = timeout_guard(facts)
                if guard_review:
                    parsed_review, management_failures = validate_management_decision(
                        guard_review, facts
                    )
                    model_used = "timeout_guard"
                    raw_response = json.dumps(guard_review, separators=(",", ":"))
                    logging.warning(
                        "Timeout guard activated: %d consecutive Qwen failures, ticket=%s",
                        failures_count,
                        ticket,
                    )
                else:
                    parsed_review = unavailable_hold(
                        f"Qwen down {failures_count} cycles, guard found no exit."
                    )
                    management_failures = []
                    model_used = "timeout_guard_hold"
                    raw_response = json.dumps(parsed_review, separators=(",", ":"))
            else:
                parsed_review = unavailable_hold(
                    f"Qwen unavailable ({failures_count}/{GUARD_TIMEOUT_CYCLES}), holding."
                )
                management_failures = []
                model_used = "qwen_unavailable_hold"
                raw_response = json.dumps(parsed_review, separators=(",", ":"))
    LAST_MANAGED_M1_BY_TICKET[position.ticket] = latest_management_candle
    parsed_review["validation_failures"] = management_failures
    try:
        from qualified_levels import remember_qualified_level_ids

        refs = facts.get("level_references") or {}
        cited = []
        for key in (
            parsed_review.get("decision_level_ref"),
            parsed_review.get("next_target_ref"),
        ):
            if key and key in refs:
                cited.append(refs[key].get("level_id"))
            elif key:
                cited.append(key)
        if cited:
            remembered = remember_qualified_level_ids(cited)
            logging.info(
                "qualified_levels count=%d cited=%s",
                len(remembered),
                ",".join(str(item) for item in cited if item),
            )
    except Exception:
        logging.exception("qualified_levels:remember_failed")
    update_dashboard(positions, levels_by_symbol, today, parsed_review, protection)
    applications = []
    response_age_seconds = time.monotonic() - cycle_started
    close_results = []
    refreshed_context = recent_candle_context(primary_symbol)
    latest_rows = refreshed_context.get("M1", [])
    latest_m1_after_response = (
        latest_rows[-1].get("evidence_id") if latest_rows else None
    )
    live = mt5.positions_get(ticket=position.ticket) or ()
    same_position_open = bool(live and is_qwen_owned(live[0]))
    current_quote = (
        mt5.symbol_info_tick(primary_symbol) if same_position_open else None
    )
    live_price = (
        float(current_quote.bid)
        if current_quote and live[0].type == mt5.POSITION_TYPE_BUY
        else float(current_quote.ask) if current_quote else None
    )
    decision_still_applicable = bool(
        live_price is not None
        and decision_is_currently_applicable(parsed_review, facts, live_price)
    )
    stale_for_execution = not same_position_open or not decision_still_applicable
    if (
        AUTO_MANAGE_QWEN_OWNED
        and same_position_open
        and not stale_for_execution
        and not management_failures
    ):
        if parsed_review.get("action") == "close":
            close_results = close_qwen_owned_positions(live)
        elif parsed_review.get("action") == "protect":
            applications = apply_confirmed_protection(live[0], parsed_review, facts)
    append_qwen_decision(
        decision_type="management",
        symbol=primary_symbol,
        price=facts.get("position", {}).get("current"),
        prompt_text=prompt_text,
        raw_response=raw_response or json.dumps(parsed_review, separators=(",", ":")),
        parsed=parsed_review,
        model=model_used,
        duration_ns=total_duration_ns,
        mt5_position_id=int(position.ticket),
        atr=market_atr,
        context={
            "entry_proposal_id": entry.get("proposal_id"),
            "guard_applied": bool(guard_review),
            "latest_completed_m1": latest_management_candle,
            **build_manifest.stamp(),
            # Everything needed to score this decision later, captured at the
            # moment it was made. See management_decision_context().
            **management_decision_context(
                facts=facts,
                entry=entry,
                parsed_review=parsed_review,
                guard_review=guard_review,
                applications=applications,
                close_results=close_results,
                stale_for_execution=stale_for_execution,
                decision_still_applicable=decision_still_applicable,
                response_age_seconds=response_age_seconds,
                live_price=live_price,
            ),
        },
    )
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot": snapshot,
        "model": model_used,
        "prompt_text": prompt_text,
        "raw_response": raw_response,
        "review": parsed_review,
        "protection_applications": applications,
        "close_applications": close_results,
        "response_age_seconds": response_age_seconds,
        "stale_for_execution": stale_for_execution,
        "newer_m1_available": (
            latest_m1_after_response != facts.get("latest_completed_m1")
        ),
        "post_qwen_price": live_price,
        "entry_context": entry,
        "guard_applied": bool(guard_review),
        "total_duration_ns": total_duration_ns,
    }
    append_tick_record("reviews", record)
    logging.info(
        "Reviewed %d open position(s) and %d recent deal(s); audit=%s",
        len(positions),
        len(recent_deals),
        LOG_DIR / f"reviews-{datetime.now():%Y-%m-%d}.jsonl",
    )


def main() -> None:
    # A localhost listener prevents duplicate trade-management instances.
    # Separate port from reviewer.py's 48631 -- these are two independent
    # processes now, each needing its own singleton guard.
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", 48633))
        singleton.listen(1)
    except OSError:
        return

    logging.info("Qwen trade-management process starting; interval=%ds", INTERVAL_SECONDS)
    # Report placement, but NEVER gate on it here.
    #
    # The entry loop skips its cycle on CPU because a late entry is worthless:
    # the proposal has expired and the level has moved. Management is the
    # opposite. It looks after money already at risk, and a slow decision about
    # an open position is far better than none -- safety_guard still closes on
    # hard invalidation, and timeout_guard can act if Qwen stays down.
    #
    # Refusing to manage a live position because inference is slow would turn a
    # performance problem into an unprotected trade.
    require_gpu("trade_management")
    while True:
        started = time.monotonic()
        try:
            market = gold_market_open()
            sync_model_residency(market)
            if not market.get("open"):
                logging.info(
                    "Market closed (%s); Qwen unloaded/idle — skip management cycle",
                    market.get("reason"),
                )
            else:
                connect_mt5()
                try:
                    review_positions()
                finally:
                    mt5.shutdown()
        except Exception:
            logging.exception("Management review cycle failed")
            try:
                mt5.shutdown()
            except Exception:
                pass
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL_SECONDS - elapsed))


if __name__ == "__main__":
    main()
