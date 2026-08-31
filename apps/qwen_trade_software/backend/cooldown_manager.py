"""Single authority for post-trade and market-volatility entry cooldowns."""

from __future__ import annotations

import json
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOSS_COOLDOWN_SECONDS = 300
WIN_COOLDOWN_SECONDS = 120
LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE = 82
LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK = 2.5
VOLATILITY_COOLDOWN_SECONDS = 300
VOLATILITY_MOVE_1M = 5.0
VOLATILITY_MOVE_2M = 7.0
VOLATILITY_REARM_QUIET_SECONDS = 30.0
STATE_FILE = Path(__file__).resolve().parent / "volatility-cooldown-state.json"
_POST_TRADE = {"until_monotonic": 0.0, "label": ""}


def cooldown_for(result: dict) -> tuple[int, str]:
    if result.get("pnl_is_complete") is False:
        return 0, ""
    try:
        net = float(result["net_pnl"])
    except (KeyError, TypeError, ValueError):
        return 0, ""
    reason = str(result.get("reason") or "").strip().lower()
    attribution = str(result.get("attribution_source") or "").strip().lower()
    stop_comment = any(
        "[sl" in str(comment).lower()
        for comment in (result.get("close_comments") or [])
    )
    # A stop can be a tightened profit floor.  Once broker-backed net P&L is
    # positive, that exit must not throttle the next independent setup.  Use
    # the normalized close reason/attribution as well as the broker comment so
    # this remains true when a broker omits or reformats ``[sl ...]``.
    positive_sl = net > 0 and (
        stop_comment
        or reason == "managed_or_safety_sl"
        or attribution in {"broker_sl", "broker_stop", "stop_loss"}
    )
    if positive_sl:
        return 0, ""
    return ((LOSS_COOLDOWN_SECONDS, "Loss") if net < 0 else
            (WIN_COOLDOWN_SECONDS, "Win") if net > 0 else (0, ""))


def start_cooldown(seconds: int, label: str) -> None:
    _POST_TRADE.update({
        "until_monotonic": time.monotonic() + max(0, float(seconds)),
        "label": label if seconds > 0 else "",
    })


def clear_cooldown() -> None:
    _POST_TRADE.update({"until_monotonic": 0.0, "label": ""})


def _volatility_state(now: datetime | None = None) -> dict:
    try:
        from runtime_store import live_runtime_store
        store = live_runtime_store()
        if store is not None:
            state = store.get_state(STATE_FILE)
            if state:
                until = datetime.fromisoformat(str(state["until_utc"]).replace("Z", "+00:00"))
                current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
                return state if until > current else {}
    except Exception:
        pass
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        until = datetime.fromisoformat(str(state["until_utc"]).replace("Z", "+00:00"))
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return state if until > current else {}
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {}


def volatility_cooldown_active(now: datetime | None = None) -> bool:
    return bool(_volatility_state(now))


def start_volatility_cooldown(event: dict, now: datetime | None = None) -> dict:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    state = {"schema_version": 1, "label": "Volatility",
             "started_at_utc": current.isoformat(),
             "until_utc": (current + timedelta(seconds=VOLATILITY_COOLDOWN_SECONDS)).isoformat(),
             "event": event}
    try:
        from runtime_store import live_runtime_store
        store = live_runtime_store()
        if store is not None:
            store.put_state(STATE_FILE, state, owner="cooldown_manager")
            return state
    except Exception:
        pass
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, STATE_FILE)
    return state


def cooldown_remaining_seconds(now: datetime | None = None) -> float:
    post = max(0.0, float(_POST_TRADE["until_monotonic"]) - time.monotonic())
    state = _volatility_state(now)
    market = 0.0
    if state:
        until = datetime.fromisoformat(state["until_utc"].replace("Z", "+00:00"))
        market = max(0.0, (until - (now or datetime.now(timezone.utc))).total_seconds())
    return max(post, market)


def active_cooldown_label(now: datetime | None = None) -> str:
    if _volatility_state(now):
        return "Volatility"
    return str(_POST_TRADE["label"]) if cooldown_remaining_seconds(now) > 0 else ""


class VolatilityDetector:
    def __init__(self) -> None:
        self._ticks: dict[str, deque[tuple[float, float]]] = {}
        self._active: dict[str, bool] = {}
        self._quiet_since: dict[str, float] = {}

    def observe(self, symbol: str, timestamp: float, price: float) -> dict | None:
        rows = self._ticks.setdefault(symbol, deque())
        rows.append((float(timestamp), float(price)))
        while rows and timestamp - rows[0][0] > 120:
            rows.popleft()
        triggers = []
        for seconds, threshold in ((60, VOLATILITY_MOVE_1M), (120, VOLATILITY_MOVE_2M)):
            prices = [p for t, p in rows if timestamp - t <= seconds]
            if prices:
                move = max(abs(price - min(prices)), abs(price - max(prices)))
                if move >= threshold:
                    triggers.append((seconds, threshold, move))
        if not triggers:
            quiet_since = self._quiet_since.setdefault(symbol, float(timestamp))
            if timestamp - quiet_since >= VOLATILITY_REARM_QUIET_SECONDS:
                self._active[symbol] = False
            return None
        self._quiet_since.pop(symbol, None)
        if self._active.get(symbol):
            return None
        self._active[symbol] = True
        seconds, threshold, move = max(triggers, key=lambda x: x[2] / x[1])
        return {"symbol": symbol, "window_seconds": seconds, "threshold": threshold,
                "observed_move": round(move, 6), "price": price}
