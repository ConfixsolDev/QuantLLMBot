"""Session-hierarchy planner: day plan → session plans → hourly updates → verdicts.

Runs as a supervised child process. Session boundaries are code-owned (UTC).
Every artifact embeds a clock block and dual-writes to tick_data/.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import socket
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import plan_branches
import build_manifest
import process_logging
from market_context_cache import (
    DEFAULT_DB,
    latest_entry_context,
    latest_readiness,
    load_prompt_section,
    session_at,
)
from review_shared import (
    APP_DIR,
    DEFAULT_TERMINAL,
    LOG_DIR,
    MANAGEMENT_STATE_FILE,
    MODEL,
    PLANNER_STATE_FILE,
    STORE_ROOT,
    gold_market_open,
    ollama_generate,
    read_json_safe,
    sync_model_residency,
    write_json_atomic,
)
from tick_data_archive import (
    TICK_DATA_ROOT,
    append_qwen_decision,
    append_tick_record,
    runtime_log_path,
)


INTERVAL_SECONDS = 20
MAX_PRICE_REPAIR_ATTEMPTS = 1
SYMBOL = "XAUUSDr"
PLANNING_SESSIONS = ("asia", "london", "overlap", "new_york")
SESSION_OPEN_HOUR = {"asia": 0, "london": 8, "overlap": 13, "new_york": 16}
SESSION_CLOSE_HOUR = {"asia": 7, "london": 13, "overlap": 16, "new_york": 17}
SESSION_HOURS = {"asia": 7, "london": 5, "overlap": 3, "new_york": 1}

DEFAULT_PLANNER_STATE = {
    "updated_at_utc": "",
    "symbol": SYMBOL,
    "clock": {},
    "day_plan": None,
    "session_plan": None,
    "hourly_updates": [],
    "session_verdicts": [],
    "trade_idea_stack": None,
    "planner_status": "starting",
    "last_error": None,
}

PLAN_STATUS_VALUES = ("on_track", "drifting", "invalidated")
LAYER_IDEA_STATUS = ("active", "revised", "invalidated")

# Claims the root logger when session_planner IS the process. When it is merely
# imported (reviewer does this), the importing entrypoint reconfigures after
# this line and wins -- which is correct: the lines belong to that process's log.
_LOG_HANDLER = process_logging.configure(
    LOG_DIR / "session-planner.log", owner="session_planner"
)
# Announce the build and alarm if it has drifted from the declared freeze.
build_manifest.log_identity("session_planner")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_plan_id(trading_date: date) -> str:
    return f"dp-{trading_date:%Y%m%d}"


def session_plan_id(trading_date: date, session: str) -> str:
    return f"sp-{trading_date:%Y%m%d}-{session}"


def hourly_id(trading_date: date, utc_hour: int) -> str:
    return f"hu-{trading_date:%Y%m%d}T{utc_hour:02d}"


def sessions_completed_before(session: str) -> list[str]:
    if session not in PLANNING_SESSIONS:
        idx = -1
        for name in PLANNING_SESSIONS:
            if name == session:
                break
            idx += 1
        return list(PLANNING_SESSIONS[: idx + 1]) if idx >= 0 else []
    idx = PLANNING_SESSIONS.index(session)
    return list(PLANNING_SESSIONS[:idx])


def next_session_boundary(moment: datetime) -> datetime:
    hour = moment.hour
    minute = moment.minute
    base = moment.replace(minute=0, second=0, microsecond=0)
    boundaries = [0, 7, 8, 13, 16, 17, 24]
    for boundary in boundaries:
        if hour < boundary or (hour == boundary and minute == 0 and boundary != hour):
            if boundary == 24:
                return base.replace(hour=0) + timedelta(days=1)
            return base.replace(hour=boundary)
    return base.replace(hour=0) + timedelta(days=1)


def build_clock(moment: datetime | None = None) -> dict:
    moment = moment or utc_now()
    session = session_at(moment)
    name = session["session"]
    hour = moment.hour
    if name in PLANNING_SESSIONS:
        open_hour = SESSION_OPEN_HOUR[name]
        hour_of_session = hour - open_hour + 1
    elif name == "pre_london":
        hour_of_session = 1
    elif name == "off_session":
        hour_of_session = hour - 17 if hour >= 17 else hour + 7
    else:
        hour_of_session = 1
    return {
        "utc_time": iso_utc(moment),
        "utc_hour": hour,
        "hours_into_day": hour,
        "session": name,
        "hour_of_session": max(1, hour_of_session),
        "sessions_completed": sessions_completed_before(name),
        "next_boundary_utc": iso_utc(next_session_boundary(moment)),
        "trading_date_utc": session["trading_date_utc"],
    }


def read_chart_candles(
    symbol: str = SYMBOL,
    timeframe: str = "M15",
    count: int = 200,
    db_path: Path = DEFAULT_DB,
) -> list[dict]:
    if timeframe not in ("M5", "M15", "H1", "H4"):
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if not db_path.exists():
        return []
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT open_time_utc, open, high, low, close, tick_volume "
            "FROM completed_candles WHERE symbol=? AND timeframe=? "
            "ORDER BY open_time_utc DESC LIMIT ?",
            (symbol, timeframe, count),
        ).fetchall()
    finally:
        connection.close()
    candles = []
    for row in reversed(rows):
        ts = datetime.fromisoformat(str(row["open_time_utc"]).replace("Z", "+00:00"))
        candles.append(
            {
                "time": int(ts.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["tick_volume"]),
            }
        )
    return candles


def hour_ohlc_from_h1(symbol: str, hour_start: datetime) -> dict | None:
    """Aggregate H1 candle whose open matches the hour, else nearest completed H1."""
    if not DEFAULT_DB.exists():
        return None
    connection = sqlite3.connect(str(DEFAULT_DB))
    connection.row_factory = sqlite3.Row
    try:
        target = iso_utc(hour_start.replace(minute=0, second=0, microsecond=0))
        row = connection.execute(
            "SELECT open, high, low, close FROM completed_candles "
            "WHERE symbol=? AND timeframe='H1' AND open_time_utc=? LIMIT 1",
            (symbol, target),
        ).fetchone()
        if row is None:
            row = connection.execute(
                "SELECT open, high, low, close FROM completed_candles "
                "WHERE symbol=? AND timeframe='H1' AND open_time_utc <= ? "
                "ORDER BY open_time_utc DESC LIMIT 1",
                (symbol, target),
            ).fetchone()
        if row is None:
            return None
        return {
            "o": float(row["open"]),
            "h": float(row["high"]),
            "l": float(row["low"]),
            "c": float(row["close"]),
        }
    finally:
        connection.close()


def compute_levels_touched(
    hour_ohlc: dict,
    key_levels: list[dict],
) -> list[dict]:
    if not hour_ohlc or not key_levels:
        return []
    high = hour_ohlc["h"]
    low = hour_ohlc["l"]
    close = hour_ohlc["c"]
    touched = []
    for level in key_levels:
        price = float(level.get("price", 0))
        if price <= 0:
            continue
        if low <= price <= high:
            if close > price:
                result = "broken_above"
            elif close < price:
                result = "broken_below"
            else:
                result = "tested"
        elif abs(close - price) < 0.5:
            result = "tested"
        else:
            continue
        touched.append(
            {
                "price": price,
                "label": level.get("label", ""),
                "result": result,
            }
        )
    return touched


def observed_from_ohlc(hour_ohlc: dict | None) -> str:
    if not hour_ohlc:
        return "no_data"
    move = hour_ohlc["c"] - hour_ohlc["o"]
    if abs(move) < 0.3:
        return "ranged"
    return "bullish hour" if move > 0 else "bearish hour"


def load_jsonl_records(base_name: str, day: date) -> list[dict]:
    path = runtime_log_path(base_name, day)
    if not path.exists():
        archive = TICK_DATA_ROOT / day.isoformat() / {
            "day-plans": "day-plans.jsonl",
            "session-plans": "session-plans.jsonl",
            "hourly-updates": "hourly-updates.jsonl",
            "session-verdicts": "session-verdicts.jsonl",
        }.get(base_name, "")
        if archive.exists():
            path = archive
        else:
            return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def load_previous_day_verdicts(trading_date: date) -> list[dict]:
    prev = trading_date - timedelta(days=1)
    return load_jsonl_records("session-verdicts", prev)


def planner_facts(symbol: str = SYMBOL) -> dict:
    entry_cache = latest_entry_context(symbol)
    return {
        "symbol": symbol,
        "cache_status": entry_cache.get("status"),
        "cache_reason": entry_cache.get("reason"),
        "structure": entry_cache.get("structure", {}),
        "session": entry_cache.get("session", {}),
        "levels": entry_cache.get("levels", []),
        "recent_closed": entry_cache.get("recent_closed", {}),
        "minute": entry_cache.get("minute", {}),
        "epochs": entry_cache.get("epochs", {}),
    }


def live_mid_from_management() -> float | None:
    """Fallback mid from the management dashboard when entry-cache quote is empty."""
    state = read_json_safe(MANAGEMENT_STATE_FILE, {})
    try:
        price = float(state.get("price") or 0.0)
    except (TypeError, ValueError):
        return None
    return round(price, 3) if price > 0 else None


def live_mid_from_mt5(symbol: str = SYMBOL) -> float | None:
    """Last-resort mid from MT5 when cache/management quotes are unavailable."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None
    if not (mt5.initialize(path=DEFAULT_TERMINAL) or mt5.initialize()):
        return None
    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        bid = float(tick.bid)
        ask = float(tick.ask)
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2.0, 3)
        if bid > 0:
            return round(bid, 3)
        if ask > 0:
            return round(ask, 3)
        return None
    finally:
        mt5.shutdown()


def live_mid_from_facts(facts: dict) -> float | None:
    """Authoritative live mid; never trust a model-emitted price.

    Prefer the validated minute-cache quote, then management dashboard, then MT5.
    Missing live mid previously produced hallucinated ~2000 XAU levels that stuck
    in planner-state for the whole Asia session.
    """
    quote = (facts.get("minute") or {}).get("quote") or {}
    try:
        bid = quote.get("bid")
        ask = quote.get("ask")
        if bid is not None and ask is not None:
            return round((float(bid) + float(ask)) / 2.0, 3)
        if bid is not None:
            return round(float(bid), 3)
        if ask is not None:
            return round(float(ask), 3)
    except (TypeError, ValueError):
        pass
    management = live_mid_from_management()
    if management is not None:
        return management
    return live_mid_from_mt5(str(facts.get("symbol") or SYMBOL))


def price_deviation_limit(live_price: float) -> float:
    """Max allowed distance from live for planner geometry (XAUUSD units)."""
    return round(max(80.0, float(live_price) * 0.02), 3)


def _collect_plan_prices(plan: dict) -> list[tuple[str, float]]:
    prices: list[tuple[str, float]] = []
    for name in ("bullish_scenario", "bearish_scenario"):
        scenario = plan.get(name) if isinstance(plan.get(name), dict) else {}
        invalidation = scenario.get("invalidation")
        if invalidation is not None:
            try:
                prices.append((f"{name}.invalidation", float(invalidation)))
            except (TypeError, ValueError):
                prices.append((f"{name}.invalidation", float("nan")))
        for index, target in enumerate(scenario.get("targets") or []):
            try:
                prices.append((f"{name}.targets[{index}]", float(target)))
            except (TypeError, ValueError):
                prices.append((f"{name}.targets[{index}]", float("nan")))
    for index, level in enumerate(plan.get("key_levels") or []):
        if not isinstance(level, dict):
            continue
        try:
            prices.append((f"key_levels[{index}].price", float(level.get("price"))))
        except (TypeError, ValueError):
            prices.append((f"key_levels[{index}].price", float("nan")))
    for index, zone in enumerate(plan.get("entry_zones") or []):
        if not isinstance(zone, dict):
            continue
        bounds = zone.get("zone") or []
        if len(bounds) == 2:
            try:
                lo, hi = float(bounds[0]), float(bounds[1])
                prices.append((f"entry_zones[{index}].lo", lo))
                prices.append((f"entry_zones[{index}].hi", hi))
            except (TypeError, ValueError):
                prices.append((f"entry_zones[{index}].zone", float("nan")))
        for field in ("invalidation", "target"):
            if zone.get(field) is None:
                continue
            try:
                prices.append((f"entry_zones[{index}].{field}", float(zone[field])))
            except (TypeError, ValueError):
                prices.append((f"entry_zones[{index}].{field}", float("nan")))
    h4 = plan.get("trade_idea_h4")
    if isinstance(h4, dict):
        if h4.get("invalidation") is not None:
            try:
                prices.append(("trade_idea_h4.invalidation", float(h4["invalidation"])))
            except (TypeError, ValueError):
                prices.append(("trade_idea_h4.invalidation", float("nan")))
        for index, target in enumerate(h4.get("targets") or []):
            try:
                prices.append((f"trade_idea_h4.targets[{index}]", float(target)))
            except (TypeError, ValueError):
                prices.append((f"trade_idea_h4.targets[{index}]", float("nan")))
    m15 = plan.get("trade_idea_m15")
    if isinstance(m15, dict):
        zone = m15.get("pullback_zone") or []
        if len(zone) == 2:
            try:
                prices.append(("trade_idea_m15.pullback_lo", float(zone[0])))
                prices.append(("trade_idea_m15.pullback_hi", float(zone[1])))
            except (TypeError, ValueError):
                prices.append(("trade_idea_m15.pullback_zone", float("nan")))
        for field in ("invalidation", "target"):
            if m15.get(field) is None:
                continue
            try:
                prices.append((f"trade_idea_m15.{field}", float(m15[field])))
            except (TypeError, ValueError):
                prices.append((f"trade_idea_m15.{field}", float("nan")))
    return prices


def _failure_field(item: str) -> str:
    return item.split(":", 1)[0]


def _is_idea_price_field(field: str) -> bool:
    return field.startswith("trade_idea_")


def _price_out_of_band(value: object, live_price: float, limit: float) -> bool:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return True
    if price != price:
        return True
    return abs(price - live_price) > limit


def _idea_prices_out_of_band(idea: dict | None, live_price: float, limit: float) -> bool:
    if not isinstance(idea, dict):
        return False
    values: list[object] = []
    for key in ("invalidation", "target"):
        if idea.get(key) is not None:
            values.append(idea.get(key))
    values.extend(idea.get("targets") or [])
    zone = idea.get("pullback_zone") or []
    if isinstance(zone, (list, tuple)):
        values.extend(list(zone)[:2])
    for row in idea.get("levels") or []:
        if isinstance(row, dict) and row.get("price") is not None:
            values.append(row.get("price"))
    return any(_price_out_of_band(value, live_price, limit) for value in values)


def strip_invented_idea_prices(
    plan: dict, live_price: float, limit: float | None = None
) -> list[str]:
    """Drop model-invented idea geometry instead of regenerating forever.

    Session plans were looping on trade_idea_m15 prices near 261 while gold
    was ~4400. Calling Qwen again copied the same numbers back from the
    prior stack. Ideas are optional; core scenarios/zones are not.
    """
    if live_price is None or live_price <= 0:
        return []
    limit = price_deviation_limit(live_price) if limit is None else limit
    dropped: list[str] = []
    for key in ("trade_idea_h4", "trade_idea_h1", "trade_idea_m15"):
        if _idea_prices_out_of_band(plan.get(key), live_price, limit):
            plan[key] = None
            dropped.append(key)
    stack = plan.get("trade_idea_stack")
    if isinstance(stack, dict):
        dropped.extend(strip_invented_stack_prices(stack, live_price, limit))
    return dropped


def strip_invented_stack_prices(
    stack: dict, live_price: float, limit: float | None = None
) -> list[str]:
    if not isinstance(stack, dict) or live_price is None or live_price <= 0:
        return []
    limit = price_deviation_limit(live_price) if limit is None else limit
    dropped: list[str] = []
    for key in ("h4", "h1", "m15"):
        if _idea_prices_out_of_band(stack.get(key), live_price, limit):
            stack[key] = None
            dropped.append(f"trade_idea_stack.{key}")
    return dropped


def apply_live_price_sanity(
    plan: dict,
    live_price: float | None,
    *,
    source: str = "cache_quote",
    overwrite_reference: bool = True,
    check_stored_reference: bool = False,
) -> dict:
    """Bind reference_price to live mid and veto invented geometry.

    Model-emitted reference_price has been observed wildly wrong (e.g. ~3541
    vs live ~4342). Code owns the reference; scenario/key/zone prices must
    stay within a live-relative band or the plan is marked not tradeable.
    """
    prior_reference = plan.get("reference_price")
    try:
        prior_reference_f = float(prior_reference) if prior_reference is not None else None
    except (TypeError, ValueError):
        prior_reference_f = None

    failures: list[str] = []
    if live_price is None or live_price <= 0:
        failures.append("live_price_unavailable")
        if overwrite_reference:
            plan["reference_price"] = prior_reference_f or 0.0
        sanity = {
            "ok": False,
            "live_price": None,
            "reference_price": plan.get("reference_price"),
            "prior_reference_price": prior_reference_f,
            "max_deviation_allowed": None,
            "source": source,
            "failures": failures,
        }
        plan["price_sanity"] = sanity
        plan["tradeable"] = False
        return sanity

    live_price = float(live_price)
    limit = price_deviation_limit(live_price)
    if overwrite_reference:
        plan["reference_price"] = live_price
        # Defense in depth: if a model still emitted a fake anchor, record it.
        if prior_reference_f is not None and abs(prior_reference_f - live_price) > limit:
            failures.append(
                f"prior_reference_price:{prior_reference_f:.3f} vs live:{live_price:.3f}"
            )

    if (
        check_stored_reference
        and prior_reference_f is not None
        and abs(prior_reference_f - live_price) > limit
    ):
        failures.append(
            f"reference_price:{prior_reference_f:.3f} vs live:{live_price:.3f}"
        )

    for label, price in _collect_plan_prices(plan):
        if price != price:  # NaN
            failures.append(f"{label}:not_a_number")
            continue
        if abs(price - live_price) > limit:
            failures.append(f"{label}:{price:.3f} vs live:{live_price:.3f}")

    idea_failures = [
        item for item in failures if _is_idea_price_field(_failure_field(item))
    ]
    stripped = (
        strip_invented_idea_prices(plan, live_price, limit) if idea_failures else []
    )
    if stripped:
        failures = [
            item
            for item in failures
            if not _is_idea_price_field(_failure_field(item))
        ]

    ok = not failures
    sanity = {
        "ok": ok,
        "live_price": live_price,
        "reference_price": plan.get("reference_price"),
        "prior_reference_price": prior_reference_f,
        "max_deviation_allowed": limit,
        "source": source,
        "failures": failures,
        "stripped_ideas": stripped,
    }
    plan["price_sanity"] = sanity
    if not ok and overwrite_reference:
        plan["tradeable"] = False
        validator = plan.get("validator")
        if isinstance(validator, dict):
            notes = str(validator.get("notes") or "").strip()
            extra = "live price sanity failed: " + "; ".join(failures[:3])
            validator["notes"] = (notes + " | " + extra).strip(" |")[:200]
            validator["tradeable"] = False
    return sanity


def live_sanity_snapshot(plan: dict | None, live_price: float | None) -> dict | None:
    """Re-check stored plan geometry against current live mid for Plan View."""
    if not plan or live_price is None or live_price <= 0:
        return None
    probe = {
        "reference_price": plan.get("reference_price"),
        "bullish_scenario": plan.get("bullish_scenario"),
        "bearish_scenario": plan.get("bearish_scenario"),
        "key_levels": plan.get("key_levels"),
        "entry_zones": plan.get("entry_zones"),
    }
    return apply_live_price_sanity(
        probe,
        live_price,
        source="live_recheck",
        overwrite_reference=False,
        check_stored_reference=False,
    )


def _prompt(role: str, facts: dict) -> str:
    core_skill = (STORE_ROOT / "core_skill.md").read_text(encoding="utf-8")
    contract = load_prompt_section(role, STORE_ROOT)
    return (
        core_skill
        + "\n\n"
        + contract
        + "\n\nPLANNER FACTS:\n"
        + json.dumps(facts, separators=(",", ":"))
    )


def _call_model(role: str, facts: dict, schema: dict, num_predict: int = 768) -> dict:
    prompt = _prompt(role, facts)
    result = ollama_generate(
        prompt,
        timeout=None,
        num_predict=num_predict,
        num_ctx=8192,
        format_schema=schema,
    )
    parsed = json.loads(result.get("response", "{}"))
    append_qwen_decision(
        decision_type=f"planner_{role.replace('qwen_', '')}",
        symbol=facts.get("symbol", SYMBOL),
        price=facts.get("reference_price"),
        prompt_text=prompt,
        raw_response=result.get("response", "{}"),
        parsed=parsed,
        model=MODEL,
        duration_ns=result.get("total_duration"),
        atr=result.get("market_atr"),
        context={"role": role, "clock": facts.get("clock")},
    )
    return parsed


def validator_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["agree", "disagree"]},
            "per_scenario": {
                "type": "object",
                "properties": {
                    "bullish": {"type": "string", "enum": ["agree", "disagree"]},
                    "bearish": {"type": "string", "enum": ["agree", "disagree"]},
                },
                "required": ["bullish", "bearish"],
            },
            "notes": {"type": "string", "maxLength": 200},
            "tradeable": {"type": "boolean"},
        },
        "required": ["verdict", "per_scenario", "notes", "tradeable"],
        "additionalProperties": False,
    }


def _h4_idea_schema(include_status: bool = False) -> dict:
    props = {
        "side": {"type": "string", "enum": ["buy", "sell", "neutral"]},
        "thesis": {"type": "string", "maxLength": 160},
        "invalidation": {"type": "number"},
        "targets": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": 1,
            "maxItems": 3,
        },
        "key_level_refs": {
            "type": "array",
            "items": {"type": "string", "maxLength": 60},
            "maxItems": 6,
        },
    }
    required = ["side", "thesis", "invalidation", "targets", "key_level_refs"]
    if include_status:
        props["status"] = {"type": "string", "enum": list(LAYER_IDEA_STATUS)}
        required.append("status")
    return {
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _h1_idea_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "maxLength": 160},
            "levels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "price": {"type": "number"},
                        "label": {"type": "string", "maxLength": 60},
                    },
                    "required": ["price", "label"],
                    "additionalProperties": False,
                },
                "maxItems": 6,
            },
            "invalidation": {"type": "number"},
        },
        "required": ["summary", "levels", "invalidation"],
        "additionalProperties": False,
    }


def _m15_idea_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "pullback_zone": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            },
            "invalidation": {"type": "number"},
            "target": {"type": "number"},
        },
        "required": ["side", "pullback_zone", "invalidation", "target"],
        "additionalProperties": False,
    }


def _layer_validation_schema() -> dict:
    status = {"type": "string", "enum": list(PLAN_STATUS_VALUES)}
    return {
        "type": "object",
        "properties": {"h4": status, "h1": status, "m15": status},
        "required": ["h4", "h1", "m15"],
        "additionalProperties": False,
    }


def _side_from_scenario(active: str) -> str:
    if active == "bullish":
        return "buy"
    if active == "bearish":
        return "sell"
    return "neutral"


def _fallback_h4_from_day_plan(plan: dict) -> dict:
    """Derive a provisional H4 idea from whichever branch price has confirmed.

    2026-08-11: this used to choose with
        use_bull = len(bull_targets) >= len(bear_targets)
    i.e. it picked the side that happened to list more target numbers. That is
    an artifact of the model's formatting, not a read of the market, and it is
    how a two-sided plan silently became one directional bet.

    The day plan keeps BOTH branches (see plan_branches.py). This fallback now
    only reports which branch price has actually confirmed. When neither has,
    it returns a neutral placeholder rather than inventing a direction --
    "no branch confirmed yet" is a legitimate and useful answer.
    """
    bull = plan.get("bullish_scenario") or {}
    bear = plan.get("bearish_scenario") or {}
    reference = plan.get("reference_price")

    bull_branch = plan_branches.branch_from_scenario(bull, "buy")
    bear_branch = plan_branches.branch_from_scenario(bear, "sell")
    if reference:
        try:
            price = float(reference)
            bull_branch = plan_branches.evaluate_branch(bull_branch, closed_price=price)
            bear_branch = plan_branches.evaluate_branch(bear_branch, closed_price=price)
        except (TypeError, ValueError):
            pass

    # Prefer a confirmed branch; otherwise the one still alive; otherwise bull.
    if bull_branch.state == plan_branches.CONFIRMED and bear_branch.state != plan_branches.CONFIRMED:
        use_bull = True
    elif bear_branch.state == plan_branches.CONFIRMED and bull_branch.state != plan_branches.CONFIRMED:
        use_bull = False
    elif bear_branch.state == plan_branches.INVALIDATED:
        use_bull = True
    elif bull_branch.state == plan_branches.INVALIDATED:
        use_bull = False
    else:
        use_bull = True

    scenario = bull if use_bull else bear
    side = "buy" if use_bull else "sell"
    refs = [str(row.get("label") or "") for row in (plan.get("key_levels") or [])[:6]]
    refs = [r for r in refs if r]
    return {
        "side": side,
        "thesis": str(scenario.get("trigger") or "H4 day thesis")[:160],
        "invalidation": float(scenario.get("invalidation") or plan.get("reference_price") or 0.0),
        "targets": [float(t) for t in (scenario.get("targets") or [plan.get("reference_price") or 0.0])[:3]],
        "key_level_refs": refs or ["day_key_level"],
        "status": "active",
        "revision": 0,
    }


def _fallback_h1_from_session(plan: dict, h4: dict) -> dict:
    levels = []
    for zone in plan.get("entry_zones") or []:
        z = zone.get("zone") or []
        if len(z) == 2:
            levels.append({"price": float(z[0]), "label": f"{zone.get('side', 'zone')}_lo"})
            levels.append({"price": float(z[1]), "label": f"{zone.get('side', 'zone')}_hi"})
    if not levels:
        for ref, price in zip(h4.get("key_level_refs") or [], h4.get("targets") or []):
            levels.append({"price": float(price), "label": str(ref)})
    return {
        "summary": str(plan.get("summary") or "H1 refine of day idea")[:160],
        "levels": levels[:6],
        "invalidation": float(
            (plan.get("entry_zones") or [{}])[0].get("invalidation")
            if plan.get("entry_zones")
            else h4.get("invalidation")
            or 0.0
        ),
        "status": "active",
    }


def _fallback_m15_from_session(plan: dict, h4: dict) -> dict | None:
    zones = plan.get("entry_zones") or []
    if not zones:
        if h4.get("side") in ("buy", "sell") and h4.get("targets"):
            inv = float(h4.get("invalidation") or 0.0)
            tgt = float(h4["targets"][0])
            mid = (inv + tgt) / 2.0
            width = abs(tgt - inv) * 0.08
            return {
                "side": h4["side"],
                "pullback_zone": [round(mid - width, 3), round(mid + width, 3)],
                "invalidation": inv,
                "target": tgt,
                "status": "active",
            }
        return None
    zone = zones[0]
    z = list(zone.get("zone") or [0.0, 0.0])
    return {
        "side": zone.get("side") or _side_from_scenario(plan.get("active_scenario", "neutral")),
        "pullback_zone": [float(z[0]), float(z[1])],
        "invalidation": float(zone.get("invalidation") or h4.get("invalidation") or 0.0),
        "target": float(zone.get("target") or (h4.get("targets") or [0.0])[0]),
        "status": "active",
    }


def build_initial_trade_idea_stack(day_plan: dict) -> dict:
    raw = day_plan.get("trade_idea_h4")
    if isinstance(raw, dict) and raw.get("thesis"):
        h4 = {
            "side": raw.get("side") if raw.get("side") in ("buy", "sell", "neutral") else "neutral",
            "thesis": str(raw.get("thesis") or "")[:160],
            "invalidation": float(raw.get("invalidation") or 0.0),
            "targets": [float(t) for t in (raw.get("targets") or [])[:3]],
            "key_level_refs": [str(x)[:60] for x in (raw.get("key_level_refs") or [])[:6]],
            "status": "active",
            "revision": 0,
        }
        if not h4["targets"]:
            h4 = _fallback_h4_from_day_plan(day_plan)
    else:
        h4 = _fallback_h4_from_day_plan(day_plan)
    return {
        "day_idea_id": day_plan.get("day_plan_id"),
        "h4": h4,
        "h1": None,
        "m15": None,
        "revisions": [],
        "layer_validation": {"h4": "pending", "h1": "pending", "m15": "pending"},
        "updated_at_utc": iso_utc(utc_now()),
    }


def revise_trade_idea_stack(
    stack: dict | None,
    session_plan: dict,
    prior_verdicts: list[dict],
) -> dict:
    base = dict(stack or {})
    day_idea_id = session_plan.get("day_plan_id") or base.get("day_idea_id")
    prior_h4 = dict((base.get("h4") or {}))
    raw_h4 = session_plan.get("trade_idea_h4")
    if isinstance(raw_h4, dict) and raw_h4.get("thesis"):
        h4 = {
            "side": raw_h4.get("side")
            if raw_h4.get("side") in ("buy", "sell", "neutral")
            else prior_h4.get("side", "neutral"),
            "thesis": str(raw_h4.get("thesis") or prior_h4.get("thesis") or "")[:160],
            "invalidation": float(
                raw_h4.get("invalidation")
                if raw_h4.get("invalidation") is not None
                else prior_h4.get("invalidation")
                or 0.0
            ),
            "targets": [float(t) for t in (raw_h4.get("targets") or prior_h4.get("targets") or [])[:3]],
            "key_level_refs": [
                str(x)[:60]
                for x in (raw_h4.get("key_level_refs") or prior_h4.get("key_level_refs") or [])[:6]
            ],
            "status": raw_h4.get("status")
            if raw_h4.get("status") in LAYER_IDEA_STATUS
            else "revised",
            "revision": int(prior_h4.get("revision") or 0) + 1,
        }
    else:
        h4 = dict(prior_h4) if prior_h4 else {
            "side": _side_from_scenario(session_plan.get("active_scenario", "neutral")),
            "thesis": str(session_plan.get("summary") or "Session-revised day idea")[:160],
            "invalidation": 0.0,
            "targets": [],
            "key_level_refs": [],
            "status": "revised",
            "revision": 1,
        }
        h4["status"] = "revised"
        h4["revision"] = int(h4.get("revision") or 0) + (0 if prior_h4 else 0)
        if prior_h4:
            h4["revision"] = int(prior_h4.get("revision") or 0) + 1

    raw_h1 = session_plan.get("trade_idea_h1")
    if isinstance(raw_h1, dict) and raw_h1.get("summary"):
        h1 = {
            "summary": str(raw_h1.get("summary") or "")[:160],
            "levels": [
                {"price": float(row.get("price")), "label": str(row.get("label") or "")[:60]}
                for row in (raw_h1.get("levels") or [])[:6]
                if isinstance(row, dict) and row.get("price") is not None
            ],
            "invalidation": float(raw_h1.get("invalidation") or h4.get("invalidation") or 0.0),
            "status": "active",
        }
    else:
        h1 = _fallback_h1_from_session(session_plan, h4)

    raw_m15 = session_plan.get("trade_idea_m15")
    if isinstance(raw_m15, dict) and raw_m15.get("pullback_zone"):
        zone = list(raw_m15.get("pullback_zone") or [0.0, 0.0])
        m15 = {
            "side": raw_m15.get("side")
            if raw_m15.get("side") in ("buy", "sell")
            else (h4.get("side") if h4.get("side") in ("buy", "sell") else "buy"),
            "pullback_zone": [float(zone[0]), float(zone[1])],
            "invalidation": float(raw_m15.get("invalidation") or h4.get("invalidation") or 0.0),
            "target": float(raw_m15.get("target") or (h4.get("targets") or [0.0])[0]),
            "status": "active",
        }
    else:
        m15 = _fallback_m15_from_session(session_plan, h4)

    prior = prior_verdicts[-1] if prior_verdicts else {}
    revisions = list(base.get("revisions") or [])
    revisions.append(
        {
            "session": session_plan.get("session"),
            "from_revision": int(prior_h4.get("revision") or 0),
            "to_revision": int(h4.get("revision") or 0),
            "prior_verdict_summary": str(prior.get("planned_vs_actual") or prior.get("lesson_candidate") or "")[:200],
            "performance": str(prior.get("scenario_outcome") or "none")[:40],
            "change_summary": str(
                session_plan.get("revision_note") or session_plan.get("summary") or "session revise"
            )[:160],
            "at_utc": iso_utc(utc_now()),
        }
    )
    return {
        "day_idea_id": day_idea_id,
        "h4": h4,
        "h1": h1,
        "m15": m15,
        "revisions": revisions[-12:],
        "layer_validation": base.get("layer_validation")
        or {"h4": "pending", "h1": "pending", "m15": "pending"},
        "updated_at_utc": iso_utc(utc_now()),
    }


def apply_layer_validation(
    stack: dict | None,
    layer_validation: dict | None,
    plan_status: str,
    closed_price: float | None = None,
) -> dict:
    """Record layer verdicts, but only PRICE may invalidate an idea.

    2026-08-11 INCIDENT. This function used to mirror the model's
    layer_validation verdict straight onto idea status with no price check. A
    session-forecast miss -- "expected range compression before London open",
    observed a bullish hour, confidence delta -30 -- propagated to
    h4/h1/m15 = invalidated. Meanwhile price ran through BOTH of that idea's
    targets (4405.80, 4409.20) and never touched its 4397.60 invalidation.

    The idea was correct and was marked dead, which is why the board was solid
    red and why "the ideas are not likely improving": they were being killed by
    forecast misses rather than by being wrong.

    "My forecast of session character was wrong" and "my trade idea is wrong"
    are independent claims. On that day they were opposite. So the model verdict
    is retained for display and scoring, and an idea is only marked invalidated
    when ``closed_price`` has closed through that idea's OWN invalidation level.
    """
    base = dict(stack or {})
    lv = dict(base.get("layer_validation") or {})
    incoming = layer_validation if isinstance(layer_validation, dict) else {}
    for key in ("h4", "h1", "m15"):
        value = incoming.get(key)
        if value in PLAN_STATUS_VALUES:
            lv[key] = value
        elif key not in lv:
            lv[key] = plan_status if plan_status in PLAN_STATUS_VALUES else "pending"

    def price_invalidates(idea: dict) -> tuple[bool, str]:
        """True only when a CLOSE went through this idea's own level."""
        if closed_price is None or not isinstance(idea, dict):
            return False, ""
        level = idea.get("invalidation")
        try:
            level = float(level)
        except (TypeError, ValueError):
            return False, ""
        if not level:
            return False, ""
        side = str(idea.get("side") or "").lower()
        if side not in ("buy", "sell"):
            # H1 refine blocks carry no side; inherit from the H4 idea.
            side = str((base.get("h4") or {}).get("side") or "").lower()
        if side not in ("buy", "sell"):
            return False, ""
        direction = 1.0 if side == "buy" else -1.0
        if direction * (float(closed_price) - level) < 0:
            return True, f"closed {float(closed_price):.3f} through invalidation {level:.3f}"
        return False, ""

    for idea_key in ("h4", "h1", "m15"):
        idea = base.get(idea_key)
        if not isinstance(idea, dict):
            continue
        idea = dict(idea)
        dead, reason = price_invalidates(idea)
        if dead:
            idea["status"] = "invalidated"
            idea["invalidation_reason"] = reason
        elif idea.get("status") == "invalidated":
            # A previous forecast-driven invalidation that price never backed.
            idea["status"] = "active"
            idea["invalidation_reason"] = "restored: price never closed through the level"
        base[idea_key] = idea

    base["layer_validation"] = lv
    base["updated_at_utc"] = iso_utc(utc_now())
    return base


def day_plan_schema() -> dict:
    # reference_price is code-owned from the live cache quote after generation.
    return {
        "type": "object",
        "properties": {
            "bullish_scenario": {
                "type": "object",
                "properties": {
                    "trigger": {"type": "string", "maxLength": 120},
                    "targets": {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 3},
                    "invalidation": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                },
                "required": ["trigger", "targets", "invalidation", "evidence"],
            },
            "bearish_scenario": {
                "type": "object",
                "properties": {
                    "trigger": {"type": "string", "maxLength": 120},
                    "targets": {"type": "array", "items": {"type": "number"}, "minItems": 1, "maxItems": 3},
                    "invalidation": {"type": "number"},
                    "evidence": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                },
                "required": ["trigger", "targets", "invalidation", "evidence"],
            },
            "key_levels": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "price": {"type": "number"},
                        "label": {"type": "string", "maxLength": 60},
                        "role": {"type": "string", "maxLength": 40},
                    },
                    "required": ["price", "label", "role"],
                },
                "minItems": 1,
                "maxItems": 8,
            },
            "expected_session_behaviour": {
                "type": "object",
                "properties": {
                    key: {"type": "string", "maxLength": 80}
                    for key in PLANNING_SESSIONS
                },
                "required": list(PLANNING_SESSIONS),
            },
            "trade_idea_h4": _h4_idea_schema(include_status=False),
        },
        "required": [
            "bullish_scenario",
            "bearish_scenario",
            "key_levels",
            "expected_session_behaviour",
            "trade_idea_h4",
        ],
        "additionalProperties": False,
    }


def session_plan_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "active_scenario": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "summary": {"type": "string", "maxLength": 160},
            "entry_zones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "side": {"type": "string", "enum": ["buy", "sell"]},
                        "zone": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                        "invalidation": {"type": "number"},
                        "target": {"type": "number"},
                    },
                    "required": ["side", "zone", "invalidation", "target"],
                },
                "maxItems": 4,
            },
            "trade_idea_h4": _h4_idea_schema(include_status=True),
            "trade_idea_h1": _h1_idea_schema(),
            "trade_idea_m15": _m15_idea_schema(),
            "revision_note": {"type": "string", "maxLength": 160},
        },
        "required": [
            "active_scenario",
            "confidence",
            "summary",
            "entry_zones",
            "trade_idea_h4",
            "trade_idea_h1",
            "trade_idea_m15",
            "revision_note",
        ],
        "additionalProperties": False,
    }


def hourly_update_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "plan_status": {"type": "string", "enum": list(PLAN_STATUS_VALUES)},
            "confidence_delta": {"type": "integer", "minimum": -30, "maximum": 30},
            "note": {"type": "string", "maxLength": 160},
            "layer_validation": _layer_validation_schema(),
        },
        "required": ["plan_status", "confidence_delta", "note", "layer_validation"],
        "additionalProperties": False,
    }


def session_verdict_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "planned_vs_actual": {"type": "string", "maxLength": 200},
            "scenario_outcome": {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
            "zones_hit": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "lesson_candidate": {"type": "string", "maxLength": 160},
        },
        "required": ["planned_vs_actual", "scenario_outcome", "zones_hit", "lesson_candidate"],
        "additionalProperties": False,
    }


def run_validator(plan_artifact: dict, facts: dict) -> dict:
    validator_facts = {
        **facts,
        "plan_under_review": plan_artifact,
    }
    validator = _call_model("qwen_plan_validator", validator_facts, validator_schema(), 256)
    plan_artifact["validator"] = validator
    plan_artifact["tradeable"] = bool(validator.get("tradeable"))
    return plan_artifact


def generate_day_plan(clock: dict, late: bool = False) -> tuple[dict, dict]:
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    facts = planner_facts()
    facts["clock"] = clock
    facts["previous_verdicts"] = load_previous_day_verdicts(trading_date)
    live_price = live_mid_from_facts(facts)
    if live_price is None:
        raise RuntimeError("live_price_unavailable; defer day plan until quote/MT5 mid exists")
    facts["reference_price"] = live_price
    facts["reference_price_source"] = "live_mid"
    facts["trade_idea_rules"] = {
        "one_day_idea": True,
        "h4_owns_day_thesis": True,
        "no_m1_ideas": True,
        "all_prices_near_reference": True,
    }
    plan = _call_model("qwen_day_plan", facts, day_plan_schema())
    plan["artifact"] = "day_plan"
    plan["day_plan_id"] = day_plan_id(trading_date)
    plan["clock"] = clock
    plan["late"] = late
    plan["generated_at_utc"] = iso_utc(utc_now())
    plan = run_validator(plan, facts)
    sanity = apply_live_price_sanity(plan, live_price, source="live_mid")
    stack = build_initial_trade_idea_stack(plan)
    plan["trade_idea_stack"] = stack
    logging.info(
        "Day plan price sanity ok=%s live=%s failures=%s h4_side=%s",
        sanity.get("ok"),
        sanity.get("live_price"),
        sanity.get("failures"),
        (stack.get("h4") or {}).get("side"),
    )
    append_tick_record("day-plans", plan)
    return plan, stack


def generate_session_plan(
    clock: dict,
    day_plan: dict,
    prior_verdicts: list[dict],
    trade_idea_stack: dict | None = None,
    late: bool = False,
) -> tuple[dict, dict]:
    session = clock["session"]
    if session not in PLANNING_SESSIONS:
        session = "asia"
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    facts = planner_facts()
    facts["clock"] = clock
    facts["day_plan"] = day_plan
    facts["prior_session_verdicts"] = prior_verdicts
    incoming_stack = trade_idea_stack or day_plan.get("trade_idea_stack")
    live_price = live_mid_from_facts(facts)
    if live_price is None:
        try:
            live_price = float(day_plan.get("reference_price") or 0.0) or None
        except (TypeError, ValueError):
            live_price = None
    if live_price is None:
        raise RuntimeError(
            "live_price_unavailable; defer session plan until quote/MT5 mid exists"
        )
    facts["reference_price"] = live_price
    facts["reference_price_source"] = "live_mid"
    if isinstance(incoming_stack, dict):
        incoming_stack = dict(incoming_stack)
        strip_invented_stack_prices(incoming_stack, live_price)
        trade_idea_stack = incoming_stack
    facts["trade_idea_stack"] = incoming_stack
    facts["trade_idea_rules"] = {
        "revise_same_day_idea": True,
        "h1_refine_only": True,
        "m15_pullback_only": True,
        "no_m1_ideas": True,
        "use_prior_session_performance": True,
        "all_prices_near_reference": True,
    }
    plan = _call_model("qwen_session_plan", facts, session_plan_schema())
    plan["artifact"] = "session_plan"
    plan["session_plan_id"] = session_plan_id(trading_date, session)
    plan["day_plan_id"] = day_plan["day_plan_id"]
    plan["session"] = session
    plan["clock"] = clock
    plan["late"] = late
    plan["generated_at_utc"] = iso_utc(utc_now())
    plan = run_validator(plan, facts)
    sanity = apply_live_price_sanity(plan, live_price, source="live_mid")
    stack = revise_trade_idea_stack(
        trade_idea_stack or day_plan.get("trade_idea_stack"),
        plan,
        prior_verdicts,
    )
    strip_invented_stack_prices(stack, live_price)
    plan["trade_idea_stack"] = stack
    logging.info(
        "Session plan price sanity ok=%s live=%s failures=%s stripped=%s revision=%s",
        sanity.get("ok"),
        sanity.get("live_price"),
        sanity.get("failures"),
        sanity.get("stripped_ideas"),
        (stack.get("h4") or {}).get("revision"),
    )
    append_tick_record("session-plans", plan)
    return plan, stack


def generate_hourly_update(
    clock: dict,
    day_plan: dict,
    session_plan: dict,
    hour_start: datetime,
    trade_idea_stack: dict | None = None,
) -> tuple[dict, dict]:
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    hour_ohlc = hour_ohlc_from_h1(SYMBOL, hour_start)
    key_levels = day_plan.get("key_levels", [])
    levels_touched = compute_levels_touched(hour_ohlc or {}, key_levels)
    session_name = clock["session"]
    expected = (
        day_plan.get("expected_session_behaviour", {}).get(session_name, "")
        if session_name in PLANNING_SESSIONS
        else ""
    )
    observed = observed_from_ohlc(hour_ohlc)
    stack_in = trade_idea_stack or session_plan.get("trade_idea_stack") or day_plan.get("trade_idea_stack")
    facts = {
        "symbol": SYMBOL,
        "clock": clock,
        "day_plan_id": day_plan["day_plan_id"],
        "session_plan_id": session_plan["session_plan_id"],
        "hour_ohlc": hour_ohlc,
        "levels_touched": levels_touched,
        "actual_vs_expected_seed": {
            "expected": expected,
            "observed": observed,
            "match": expected.lower() in observed.lower()
            or (expected and "range" in expected.lower() and observed == "ranged"),
        },
        "session_plan_summary": session_plan.get("summary", ""),
        "active_scenario": session_plan.get("active_scenario", "neutral"),
        "trade_idea_stack": stack_in,
        "trade_idea_rules": {
            "validate_layers": ["h4", "h1", "m15"],
            "no_m1_ideas": True,
        },
    }
    delta = _call_model("qwen_hourly_update", facts, hourly_update_schema(), 320)
    layer_validation = delta.get("layer_validation") or {
        "h4": delta["plan_status"],
        "h1": delta["plan_status"],
        "m15": delta["plan_status"],
    }
    # Pass the CLOSED hour price so only price can invalidate an idea. Without
    # it the model's verdict alone would kill ideas again (2026-08-11).
    _closed = (hour_ohlc or {}).get("c") if isinstance(hour_ohlc, dict) else None
    stack = apply_layer_validation(
        stack_in, layer_validation, delta["plan_status"], closed_price=_closed
    )
    update = {
        "artifact": "hourly_update",
        "hourly_id": hourly_id(trading_date, hour_start.hour),
        "day_plan_id": day_plan["day_plan_id"],
        "session_plan_id": session_plan["session_plan_id"],
        "clock": clock,
        "hour_ohlc": hour_ohlc,
        "levels_touched": levels_touched,
        "plan_status": delta["plan_status"],
        "confidence_delta": delta["confidence_delta"],
        "note": delta["note"],
        "layer_validation": stack.get("layer_validation"),
        "actual_vs_expected": facts["actual_vs_expected_seed"],
        "generated_at_utc": iso_utc(utc_now()),
    }
    append_tick_record("hourly-updates", update)
    return update, stack


def generate_session_verdict(
    clock: dict,
    day_plan: dict,
    session_plan: dict,
    hourly_updates: list[dict],
) -> dict:
    session = session_plan.get("session", clock["session"])
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    facts = {
        "symbol": SYMBOL,
        "clock": clock,
        "day_plan": day_plan,
        "session_plan": session_plan,
        "hourly_updates": hourly_updates,
    }
    verdict_body = _call_model("qwen_session_verdict", facts, session_verdict_schema(), 384)
    verdict = {
        "artifact": "session_verdict",
        "session_verdict_id": f"sv-{trading_date:%Y%m%d}-{session}",
        "day_plan_id": day_plan["day_plan_id"],
        "session_plan_id": session_plan["session_plan_id"],
        "session": session,
        "clock": clock,
        **verdict_body,
        "generated_at_utc": iso_utc(utc_now()),
    }
    append_tick_record("session-verdicts", verdict)
    return verdict


def load_planner_state() -> dict:
    return read_json_safe(PLANNER_STATE_FILE, DEFAULT_PLANNER_STATE)


def build_branch_view(state: dict) -> dict | None:
    """Evaluate both day-plan branches against the live close, for the screen.

    The day plan is a container of two branches and has no status of its own.
    Each branch resolves independently, and only a CLOSE through a branch's own
    invalidation can kill it. See plan_branches.py for the 2026-08-11 incident
    that motivated this.
    """
    plan = state.get("day_plan")
    if not isinstance(plan, dict):
        return None
    bull = plan_branches.branch_from_scenario(plan.get("bullish_scenario"), "buy")
    bear = plan_branches.branch_from_scenario(plan.get("bearish_scenario"), "sell")

    # A branch's trigger price is its first target's side of the key level; when
    # the model gave no explicit number, fall back to the opposite branch's
    # invalidation, which is the level the trigger is phrased against.
    if bull.trigger_price is None and bear.invalidation is not None:
        bull = plan_branches.Branch(**{**bull.as_dict(), "trigger_price": bear.invalidation})
    if bear.trigger_price is None and bull.invalidation is not None:
        bear = plan_branches.Branch(**{**bear.as_dict(), "trigger_price": bull.invalidation})

    closed = plan.get("reference_price")
    live = (state.get("live") or {}).get("mid") if isinstance(state.get("live"), dict) else None
    price = live if live else closed
    try:
        price = float(price)
    except (TypeError, ValueError):
        return plan_branches.build_day_view(bull, bear).as_dict()

    bull = plan_branches.evaluate_branch(bull, closed_price=price)
    bear = plan_branches.evaluate_branch(bear, closed_price=price)
    return plan_branches.build_day_view(bull, bear).as_dict()


def refresh_idea_states(state: dict, live_price: float | None) -> dict | None:
    """Re-evaluate the H4/H1/M15 idea statuses against the live price.

    2026-08-11: apply_layer_validation() only runs on the HOURLY tick, so a
    stale "invalidated" persisted for up to an hour while the branch panel --
    which recomputes every snapshot -- already showed TARGET REACHED. The screen
    contradicted itself: Day Plan said the bullish branch had reached its final
    target while the Trade Idea Stack, the chart ribbon and the hour card all
    showed H4/H1/M15 INVALIDATED.

    Same rule as apply_layer_validation: an idea is invalidated only when price
    has CLOSED through that idea's own invalidation level, and an idea killed by
    a forecast miss that price never backed is restored.
    """
    stack = state.get("trade_idea_stack")
    if not isinstance(stack, dict) or live_price is None:
        return stack
    try:
        price = float(live_price)
    except (TypeError, ValueError):
        return stack

    updated = dict(stack)
    h4_side = str((updated.get("h4") or {}).get("side") or "").lower()
    for key in ("h4", "h1", "m15"):
        idea = updated.get(key)
        if not isinstance(idea, dict):
            continue
        idea = dict(idea)
        level = idea.get("invalidation")
        side = str(idea.get("side") or h4_side).lower()
        try:
            level = float(level)
        except (TypeError, ValueError):
            level = 0.0
        if not level or side not in ("buy", "sell"):
            updated[key] = idea
            continue
        direction = 1.0 if side == "buy" else -1.0
        through = direction * (price - level) < 0
        if through:
            idea["status"] = "invalidated"
            idea["invalidation_reason"] = (
                f"price {price:.3f} is through invalidation {level:.3f}"
            )
        elif idea.get("status") == "invalidated":
            idea["status"] = "active"
            idea["invalidation_reason"] = (
                f"restored: price {price:.3f} never closed through {level:.3f}"
            )
        updated[key] = idea

    lv = dict(updated.get("layer_validation") or {})
    for layer_key in ("h4", "h1", "m15"):
        idea = updated.get(layer_key)
        if isinstance(idea, dict) and idea.get("status") == "invalidated":
            lv[layer_key] = "invalidated"
        elif lv.get(layer_key) == "invalidated":
            lv[layer_key] = "on_track"
    updated["layer_validation"] = lv
    return updated


def save_planner_state(state: dict) -> None:
    state["updated_at_utc"] = iso_utc(utc_now())
    try:
        state["day_branches"] = build_branch_view(state)
    except Exception:
        logging.exception("planner:branch_view_failed")
        state["day_branches"] = None
    write_json_atomic(PLANNER_STATE_FILE, state)


def load_plan_history(trading_date: date) -> dict:
    return {
        "date": trading_date.isoformat(),
        "day_plans": load_jsonl_records("day-plans", trading_date),
        "session_plans": load_jsonl_records("session-plans", trading_date),
        "hourly_updates": load_jsonl_records("hourly-updates", trading_date),
        "session_verdicts": load_jsonl_records("session-verdicts", trading_date),
    }


def _core_price_failures(failures: list | None) -> list[str]:
    return [
        item
        for item in (failures or [])
        if not _is_idea_price_field(_failure_field(str(item)))
    ]


def plan_needs_price_repair(plan: dict | None, live_price: float | None = None) -> bool:
    """True when core geometry is invented and another Qwen pass may help.

    Invented trade_idea_* prices are stripped locally. Regenerating for those
    alone kept planner_status=generating and held the GPU for hours.
    """
    if not isinstance(plan, dict):
        return False
    if int(plan.get("price_repair_attempts") or 0) >= MAX_PRICE_REPAIR_ATTEMPTS:
        return False
    sanity = plan.get("price_sanity") if isinstance(plan.get("price_sanity"), dict) else {}
    core_failures = _core_price_failures(sanity.get("failures"))
    if sanity.get("ok") is False and core_failures:
        return True
    if sanity.get("live_price") in (None, 0, 0.0):
        if "live_price_unavailable" in (sanity.get("failures") or []):
            return True
    try:
        reference = float(plan.get("reference_price") or 0.0)
    except (TypeError, ValueError):
        reference = 0.0
    if reference <= 0:
        return True
    if live_price is None or live_price <= 0:
        return False
    recheck = live_sanity_snapshot(plan, live_price)
    if not recheck or recheck.get("ok") is not False:
        return False
    return bool(_core_price_failures(recheck.get("failures")))


def should_generate_day_plan(now: datetime, state: dict) -> bool:
    trading_date = now.date()
    existing = state.get("day_plan")
    if existing and existing.get("day_plan_id") == day_plan_id(trading_date):
        live_price = live_mid_from_facts(planner_facts())
        if plan_needs_price_repair(existing, live_price):
            logging.info(
                "Day plan %s needs price repair (sanity=%s); regenerating",
                existing.get("day_plan_id"),
                (existing.get("price_sanity") or {}).get("failures"),
            )
            return True
        return False
    if now.hour == 23 and now.minute >= 45:
        return True
    if existing is None:
        return True
    return existing.get("day_plan_id") != day_plan_id(trading_date)


def should_generate_session_plan(now: datetime, state: dict) -> tuple[bool, str | None]:
    session = session_at(now)["session"]
    if session not in PLANNING_SESSIONS:
        return False, None
    trading_date = now.date()
    existing = state.get("session_plan")
    expected_id = session_plan_id(trading_date, session)
    live_price = live_mid_from_facts(planner_facts())
    if existing and existing.get("session_plan_id") == expected_id:
        if plan_needs_price_repair(existing, live_price):
            logging.info(
                "Session plan %s needs price repair; regenerating",
                existing.get("session_plan_id"),
            )
            return True, session
        return False, session
    open_hour = SESSION_OPEN_HOUR[session]
    if now.hour == open_hour and now.minute < 30:
        return True, session
    if existing is None or existing.get("session_plan_id") != expected_id:
        return True, session
    return False, session


def should_generate_hourly(now: datetime, state: dict) -> bool:
    if now.minute > 5:
        return False
    trading_date = now.date()
    target_id = hourly_id(trading_date, now.hour - 1 if now.hour > 0 else 23)
    for update in state.get("hourly_updates", []):
        if update.get("hourly_id") == target_id:
            return False
    return True


def should_generate_verdict(now: datetime, state: dict) -> tuple[bool, str | None]:
    hour = now.hour
    close_map = {7: "asia", 13: "london", 16: "overlap", 17: "new_york"}
    if hour not in close_map or now.minute > 10:
        return False, None
    session = close_map[hour]
    trading_date = now.date()
    verdict_id = f"sv-{trading_date:%Y%m%d}-{session}"
    for verdict in state.get("session_verdicts", []):
        if verdict.get("session_verdict_id") == verdict_id:
            return False, session
    return True, session


class SessionPlanner:
    def __init__(self) -> None:
        self.state = load_planner_state()
        self.last_hourly_key = ""

    def _set_status(self, status: str, error: str | None = None) -> None:
        self.state["planner_status"] = status
        self.state["last_error"] = error
        self.state["clock"] = build_clock()
        save_planner_state(self.state)

    def tick(self) -> None:
        now = utc_now()
        clock = build_clock(now)
        self.state["clock"] = clock
        self.state["symbol"] = SYMBOL

        market = gold_market_open(now)
        sync_model_residency(market)

        # Keep / rebuild trade_idea_stack even when the market is closed so Plan View
        # can still show the last H4→H1→M15 idea hierarchy.
        day_plan = self.state.get("day_plan")
        if day_plan and not self.state.get("trade_idea_stack"):
            stack = build_initial_trade_idea_stack(day_plan)
            session_plan = self.state.get("session_plan")
            if session_plan:
                stack = revise_trade_idea_stack(
                    stack,
                    session_plan,
                    self.state.get("session_verdicts") or [],
                )
                session_plan["trade_idea_stack"] = stack
            day_plan["trade_idea_stack"] = stack
            self.state["trade_idea_stack"] = stack
            self.state["day_plan"] = day_plan

        if not market.get("open"):
            self._set_status("market_closed")
            logging.info(
                "Market closed (%s); Qwen unloaded/idle — skip planner cycle",
                market.get("reason"),
            )
            return

        live_price = live_mid_from_facts(planner_facts())
        if live_price:
            for key in ("day_plan", "session_plan"):
                plan = self.state.get(key)
                if isinstance(plan, dict):
                    apply_live_price_sanity(plan, live_price)
            stack = self.state.get("trade_idea_stack")
            if isinstance(stack, dict):
                strip_invented_stack_prices(stack, live_price)

        readiness = latest_readiness(SYMBOL)
        if not readiness or readiness.get("status") != "ready":
            logging.info(
                "Defer planner Qwen until cache is ready (status=%s failures=%s)",
                (readiness or {}).get("status"),
                (readiness or {}).get("failures"),
            )
            self._set_status("waiting_cache")
            return

        if should_generate_day_plan(now, self.state):
            self._set_status("generating")
            prior_day = self.state.get("day_plan") or {}
            repairing_day = prior_day.get("day_plan_id") == day_plan_id(now.date())
            try:
                day_plan, stack = generate_day_plan(clock, late=now.hour != 23)
                day_plan["price_repair_attempts"] = (
                    int(prior_day.get("price_repair_attempts") or 0) + 1
                    if repairing_day
                    else 0
                )
                self.state["day_plan"] = day_plan
                self.state["trade_idea_stack"] = stack
                # Price-repaired day plans invalidate the prior session geometry.
                self.state["session_plan"] = None
                logging.info("Day plan generated: %s", day_plan["day_plan_id"])
            except Exception as error:
                logging.exception("Day plan generation failed")
                self._set_status("error", str(error))
                return

        day_plan = self.state.get("day_plan")
        if not day_plan:
            self._set_status("waiting_day_plan")
            return

        # Backfill stack for plans created before trade_idea_stack existed.
        if not self.state.get("trade_idea_stack"):
            self.state["trade_idea_stack"] = build_initial_trade_idea_stack(day_plan)
            day_plan["trade_idea_stack"] = self.state["trade_idea_stack"]

        need_session, session_name = should_generate_session_plan(now, self.state)
        if need_session and session_name:
            self._set_status("generating")
            prior_session = self.state.get("session_plan") or {}
            repairing = prior_session.get("session_plan_id") == session_plan_id(
                now.date(), session_name
            )
            try:
                session_plan, stack = generate_session_plan(
                    clock,
                    day_plan,
                    self.state.get("session_verdicts", []),
                    trade_idea_stack=self.state.get("trade_idea_stack"),
                    late=now.hour != SESSION_OPEN_HOUR.get(session_name, 0),
                )
                session_plan["price_repair_attempts"] = (
                    int(prior_session.get("price_repair_attempts") or 0) + 1
                    if repairing
                    else 0
                )
                self.state["session_plan"] = session_plan
                self.state["trade_idea_stack"] = stack
                logging.info(
                    "Session plan generated: %s",
                    session_plan["session_plan_id"],
                )
            except Exception as error:
                logging.exception("Session plan generation failed")
                self._set_status("error", str(error))
                return

        session_plan = self.state.get("session_plan")
        need_verdict, verdict_session = should_generate_verdict(now, self.state)
        if need_verdict and verdict_session and session_plan and day_plan:
            self._set_status("generating")
            try:
                session_hourlies = [
                    u
                    for u in self.state.get("hourly_updates", [])
                    if u.get("session_plan_id") == session_plan.get("session_plan_id")
                ]
                verdict = generate_session_verdict(clock, day_plan, session_plan, session_hourlies)
                self.state.setdefault("session_verdicts", []).append(verdict)
                logging.info("Session verdict generated: %s", verdict["session_verdict_id"])
            except Exception as error:
                logging.exception("Session verdict generation failed")
                self._set_status("error", str(error))
                return

        if session_plan and should_generate_hourly(now, self.state):
            hour_key = f"{now.date():%Y%m%d}-{now.hour}"
            if hour_key != self.last_hourly_key:
                self._set_status("generating")
                try:
                    hour_start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
                    hour_clock = build_clock(hour_start + timedelta(minutes=30))
                    update, stack = generate_hourly_update(
                        hour_clock,
                        day_plan,
                        session_plan,
                        hour_start,
                        trade_idea_stack=self.state.get("trade_idea_stack"),
                    )
                    self.state.setdefault("hourly_updates", []).append(update)
                    self.state["trade_idea_stack"] = stack
                    self.last_hourly_key = hour_key
                    logging.info("Hourly update generated: %s", update["hourly_id"])
                except Exception as error:
                    logging.exception("Hourly update generation failed")
                    self._set_status("error", str(error))
                    return

        self._set_status("ready")


def _accept_singleton_probes(singleton: socket.socket) -> None:
    """Drain health-check connects so the listen backlog never fills."""
    while True:
        try:
            conn, _addr = singleton.accept()
            conn.close()
        except OSError:
            return


def main() -> None:
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", 48634))
        singleton.listen(8)
    except OSError:
        logging.error("Session planner already running")
        return

    import threading

    threading.Thread(
        target=_accept_singleton_probes,
        args=(singleton,),
        name="planner-singleton-accept",
        daemon=True,
    ).start()

    logging.info("Session planner starting; interval=%ds", INTERVAL_SECONDS)
    planner = SessionPlanner()
    while True:
        started = time.monotonic()
        try:
            planner.tick()
        except Exception:
            logging.exception("Session planner cycle failed")
        elapsed = time.monotonic() - started
        time.sleep(max(1, INTERVAL_SECONDS - elapsed))


def self_test_price_sanity() -> None:
    live = 4342.5
    invented = {
        "reference_price": 3541.0,
        "bullish_scenario": {
            "trigger": "accept above",
            "targets": [3550.0, 3560.0],
            "invalidation": 3530.0,
            "evidence": ["H4_1"],
        },
        "bearish_scenario": {
            "trigger": "reject",
            "targets": [3520.0],
            "invalidation": 3555.0,
            "evidence": ["H1_1"],
        },
        "key_levels": [{"price": 3540.0, "label": "asia high", "role": "resistance"}],
        "validator": {"verdict": "agree", "notes": "ok", "tradeable": True},
        "tradeable": True,
    }
    sanity = apply_live_price_sanity(invented, live, source="self-test")
    assert invented["reference_price"] == live
    assert sanity["ok"] is False
    assert invented["tradeable"] is False
    assert sanity["prior_reference_price"] == 3541.0
    assert any("targets" in item or "invalidation" in item or "key_levels" in item
               for item in sanity["failures"])
    coherent = {
        "bullish_scenario": {
            "trigger": "accept",
            "targets": [4355.0],
            "invalidation": 4320.0,
            "evidence": ["H4_1"],
        },
        "bearish_scenario": {
            "trigger": "reject",
            "targets": [4310.0],
            "invalidation": 4360.0,
            "evidence": ["H1_1"],
        },
        "key_levels": [{"price": 4340.0, "label": "pivot", "role": "two_sided"}],
        "validator": {"verdict": "agree", "notes": "ok", "tradeable": True},
        "tradeable": True,
    }
    ok = apply_live_price_sanity(coherent, live, source="self-test")
    assert ok["ok"] is True
    assert coherent["reference_price"] == live
    assert coherent["tradeable"] is True
    recheck = live_sanity_snapshot(coherent, live)
    assert recheck and recheck["ok"] is True
    idea_only = {
        "reference_price": live,
        "bullish_scenario": coherent["bullish_scenario"],
        "bearish_scenario": coherent["bearish_scenario"],
        "key_levels": coherent["key_levels"],
        "trade_idea_m15": {
            "side": "sell",
            "pullback_zone": [261.5, 260.5],
            "invalidation": 262.5,
            "target": 259.5,
        },
        "tradeable": True,
    }
    idea_sanity = apply_live_price_sanity(idea_only, live, source="self-test")
    assert idea_sanity["ok"] is True
    assert idea_only["trade_idea_m15"] is None
    assert "trade_idea_m15" in (idea_sanity.get("stripped_ideas") or [])
    assert plan_needs_price_repair(idea_only, live) is False
    print("session_planner price-sanity self-test passed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test_price_sanity()
    else:
        main()
