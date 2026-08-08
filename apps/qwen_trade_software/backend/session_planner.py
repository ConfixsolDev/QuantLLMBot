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

from market_context_cache import (
    DEFAULT_DB,
    latest_entry_context,
    load_prompt_section,
    session_at,
)
from review_shared import (
    APP_DIR,
    LOG_DIR,
    MODEL,
    PLANNER_STATE_FILE,
    STORE_ROOT,
    ollama_generate,
    read_json_safe,
    write_json_atomic,
)
from tick_data_archive import (
    TICK_DATA_ROOT,
    append_qwen_decision,
    append_tick_record,
    runtime_log_path,
)


INTERVAL_SECONDS = 20
SYMBOL = "XAUUSDr"
PLANNING_SESSIONS = ("asia", "london", "overlap", "new_york")
SESSION_OPEN_HOUR = {"asia": 0, "london": 8, "overlap": 13, "new_york": 16}
SESSION_CLOSE_HOUR = {"asia": 7, "london": 13, "overlap": 16, "new_york": 21}
SESSION_HOURS = {"asia": 7, "london": 5, "overlap": 3, "new_york": 5}

DEFAULT_PLANNER_STATE = {
    "updated_at_utc": "",
    "symbol": SYMBOL,
    "clock": {},
    "day_plan": None,
    "session_plan": None,
    "hourly_updates": [],
    "session_verdicts": [],
    "planner_status": "starting",
    "last_error": None,
}

_LOG_HANDLER = logging.handlers.TimedRotatingFileHandler(
    filename=LOG_DIR / "session-planner.log", when="midnight", encoding="utf-8"
)
_LOG_HANDLER.suffix = "%Y-%m-%d"
_LOG_HANDLER.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logging.basicConfig(level=logging.INFO, handlers=[_LOG_HANDLER])


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
    boundaries = [0, 7, 8, 13, 16, 21, 24]
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
        hour_of_session = hour - 21 if hour >= 21 else hour + 3
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
    if timeframe not in ("M5", "M15", "H1"):
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


def day_plan_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "reference_price": {"type": "number"},
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
        },
        "required": [
            "reference_price",
            "bullish_scenario",
            "bearish_scenario",
            "key_levels",
            "expected_session_behaviour",
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
        },
        "required": ["active_scenario", "confidence", "summary", "entry_zones"],
        "additionalProperties": False,
    }


def hourly_update_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "plan_status": {"type": "string", "enum": ["on_track", "drifting", "invalidated"]},
            "confidence_delta": {"type": "integer", "minimum": -30, "maximum": 30},
            "note": {"type": "string", "maxLength": 160},
        },
        "required": ["plan_status", "confidence_delta", "note"],
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


def generate_day_plan(clock: dict, late: bool = False) -> dict:
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    facts = planner_facts()
    facts["clock"] = clock
    facts["previous_verdicts"] = load_previous_day_verdicts(trading_date)
    facts["reference_price"] = (
        facts.get("minute", {}).get("quote", {}).get("bid")
        or facts.get("minute", {}).get("quote", {}).get("ask")
        or 0.0
    )
    plan = _call_model("qwen_day_plan", facts, day_plan_schema())
    plan["artifact"] = "day_plan"
    plan["day_plan_id"] = day_plan_id(trading_date)
    plan["clock"] = clock
    plan["late"] = late
    plan["generated_at_utc"] = iso_utc(utc_now())
    plan = run_validator(plan, facts)
    append_tick_record("day-plans", plan)
    return plan


def generate_session_plan(
    clock: dict,
    day_plan: dict,
    prior_verdicts: list[dict],
    late: bool = False,
) -> dict:
    session = clock["session"]
    if session not in PLANNING_SESSIONS:
        session = "asia"
    trading_date = date.fromisoformat(clock["trading_date_utc"])
    facts = planner_facts()
    facts["clock"] = clock
    facts["day_plan"] = day_plan
    facts["prior_session_verdicts"] = prior_verdicts
    facts["reference_price"] = day_plan.get("reference_price", 0.0)
    plan = _call_model("qwen_session_plan", facts, session_plan_schema())
    plan["artifact"] = "session_plan"
    plan["session_plan_id"] = session_plan_id(trading_date, session)
    plan["day_plan_id"] = day_plan["day_plan_id"]
    plan["session"] = session
    plan["clock"] = clock
    plan["late"] = late
    plan["generated_at_utc"] = iso_utc(utc_now())
    plan = run_validator(plan, facts)
    append_tick_record("session-plans", plan)
    return plan


def generate_hourly_update(
    clock: dict,
    day_plan: dict,
    session_plan: dict,
    hour_start: datetime,
) -> dict:
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
    }
    delta = _call_model("qwen_hourly_update", facts, hourly_update_schema(), 256)
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
        "actual_vs_expected": facts["actual_vs_expected_seed"],
        "generated_at_utc": iso_utc(utc_now()),
    }
    append_tick_record("hourly-updates", update)
    return update


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


def save_planner_state(state: dict) -> None:
    state["updated_at_utc"] = iso_utc(utc_now())
    write_json_atomic(PLANNER_STATE_FILE, state)


def load_plan_history(trading_date: date) -> dict:
    return {
        "date": trading_date.isoformat(),
        "day_plans": load_jsonl_records("day-plans", trading_date),
        "session_plans": load_jsonl_records("session-plans", trading_date),
        "hourly_updates": load_jsonl_records("hourly-updates", trading_date),
        "session_verdicts": load_jsonl_records("session-verdicts", trading_date),
    }


def should_generate_day_plan(now: datetime, state: dict) -> bool:
    trading_date = now.date()
    existing = state.get("day_plan")
    if existing and existing.get("day_plan_id") == day_plan_id(trading_date):
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
    if existing and existing.get("session_plan_id") == expected_id:
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
    close_map = {7: "asia", 13: "london", 16: "overlap", 21: "new_york"}
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

        if should_generate_day_plan(now, self.state):
            self._set_status("generating")
            try:
                self.state["day_plan"] = generate_day_plan(clock, late=now.hour != 23)
                logging.info("Day plan generated: %s", self.state["day_plan"]["day_plan_id"])
            except Exception as error:
                logging.exception("Day plan generation failed")
                self._set_status("error", str(error))
                return

        day_plan = self.state.get("day_plan")
        if not day_plan:
            self._set_status("waiting_day_plan")
            return

        need_session, session_name = should_generate_session_plan(now, self.state)
        if need_session and session_name:
            self._set_status("generating")
            try:
                self.state["session_plan"] = generate_session_plan(
                    clock,
                    day_plan,
                    self.state.get("session_verdicts", []),
                    late=now.hour != SESSION_OPEN_HOUR.get(session_name, 0),
                )
                logging.info(
                    "Session plan generated: %s",
                    self.state["session_plan"]["session_plan_id"],
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
                    update = generate_hourly_update(hour_clock, day_plan, session_plan, hour_start)
                    self.state.setdefault("hourly_updates", []).append(update)
                    self.last_hourly_key = hour_key
                    logging.info("Hourly update generated: %s", update["hourly_id"])
                except Exception as error:
                    logging.exception("Hourly update generation failed")
                    self._set_status("error", str(error))
                    return

        self._set_status("ready")


def main() -> None:
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", 48634))
        singleton.listen(1)
    except OSError:
        logging.error("Session planner already running")
        return

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


if __name__ == "__main__":
    main()
