"""Deterministic hierarchical structure transitions from completed evidence."""

from __future__ import annotations

TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
PARENT = {"H4": "D1", "H1": "H4", "M30": "H1", "M15": "M30", "M5": "M15", "M1": "M5"}


def reduce_event(previous: dict | None, event: dict) -> dict:
    """Pure reducer: identical ordered events always reproduce identical state."""
    payload = event.get("payload") or {}
    prior = previous or {}
    direction = str(payload.get("direction") or payload.get("trend") or prior.get("direction") or "unknown")
    transition = payload.get("transition")
    active_leg = "pullback" if payload.get("counter_parent") else (
        "transition" if transition else "continuation" if direction in {"bullish", "bearish"} else "balance"
    )
    return {
        "symbol": event["symbol"],
        "timeframe": event["timeframe"],
        "parent_timeframe": PARENT.get(event["timeframe"]),
        "direction": direction,
        "state": payload.get("state") or f"{direction}_{active_leg}",
        "active_leg": active_leg,
        "transition": transition,
        "invalidation_level_id": payload.get("invalidation_level_id") or prior.get("invalidation_level_id"),
        "latest_close": payload.get("close", prior.get("latest_close")),
        "latest_evidence_id": event.get("evidence_id"),
        "unresolved_condition": payload.get("unresolved_condition") or "next completed response at active named level",
        "event_time_utc": event["event_time_utc"],
    }


def relationship_state(xau: dict, dxy: dict) -> dict:
    x = (xau or {}).get("direction", "unknown")
    d = (dxy or {}).get("direction", "unknown")
    if "unknown" in {x, d}:
        state, pressure = "unknown", "neutral"
    elif x == "bullish" and d == "bearish" or x == "bearish" and d == "bullish":
        state, pressure = "inverse_aligned", "supports_gold_structure"
    elif x == d:
        state, pressure = "positive_aligned", "correlation_exception"
    else:
        state, pressure = "decoupled", "neutral"
    return {"state": state, "gold_pressure": pressure,
            "xau_direction": x, "dxy_direction": d,
            "doctrine": "DXY adjusts confidence; XAUUSD structure and closed trigger retain authority."}
