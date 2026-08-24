"""Closed-candle reconstruction for Qwen's independent intraday notebook."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from statistics import median
from typing import Callable, Iterable


TIMEFRAME_WEIGHT = {"D1": 7, "H4": 6, "H1": 5, "M30": 4, "M15": 3, "M5": 2, "M1": 1}


def _utc(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _number(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _bar(row: dict) -> dict:
    return {
        "open": _number(row.get("open")),
        "high": _number(row.get("high")),
        "low": _number(row.get("low")),
        "close": _number(row.get("close")),
        "tick_volume": _number(row.get("tick_volume")),
        "open_time_utc": row.get("open_time_utc"),
        "close_time_utc": row.get("close_time_utc"),
        "evidence_id": row.get("evidence_id"),
    }


def _closed_today(rows: Iterable[dict], now: datetime) -> list[dict]:
    selected = []
    for raw in rows:
        row = _bar(raw)
        closed = _utc(row.get("close_time_utc"))
        if closed and closed.date() == now.date() and closed <= now:
            selected.append(row)
    return sorted(selected, key=lambda row: str(row.get("open_time_utc") or ""))


def _aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}
    high_row = max(rows, key=lambda row: row["high"])
    low_row = min(rows, key=lambda row: row["low"])
    first, last = rows[0], rows[-1]
    return {
        "open": round(first["open"], 3),
        "high": round(high_row["high"], 3),
        "low": round(low_row["low"], 3),
        "close": round(last["close"], 3),
        "net_move": round(last["close"] - first["open"], 3),
        "range": round(high_row["high"] - low_row["low"], 3),
        "high_time_utc": high_row.get("open_time_utc"),
        "low_time_utc": low_row.get("open_time_utc"),
        "completed_bars": len(rows),
        "tick_volume_total": round(sum(row["tick_volume"] for row in rows), 1),
        "latest_evidence_id": last.get("evidence_id"),
    }


def _swing_tolerance(rows: list[dict]) -> float:
    ranges = [row["high"] - row["low"] for row in rows if row["high"] > row["low"]]
    return max(0.05, (median(ranges) * 0.12) if ranges else 0.05)


def confirmed_swings(rows: list[dict], order: int = 2) -> list[dict]:
    """Return only pivots confirmed by closed bars on both sides."""
    if len(rows) < order * 2 + 1:
        return []
    tolerance = _swing_tolerance(rows)
    swings: list[dict] = []
    previous = {"high": None, "low": None}
    for index in range(order, len(rows) - order):
        row = rows[index]
        left = rows[index - order:index]
        right = rows[index + 1:index + order + 1]
        is_high = row["high"] > max(item["high"] for item in left) and row["high"] >= max(item["high"] for item in right)
        is_low = row["low"] < min(item["low"] for item in left) and row["low"] <= min(item["low"] for item in right)
        for kind, is_pivot, price in (("high", is_high, row["high"]), ("low", is_low, row["low"])):
            if not is_pivot:
                continue
            prior = previous[kind]
            if prior is None:
                label = "H" if kind == "high" else "L"
            elif abs(price - prior) <= tolerance:
                label = "EH" if kind == "high" else "EL"
            elif kind == "high":
                label = "HH" if price > prior else "LH"
            else:
                label = "HL" if price > prior else "LL"
            swings.append({
                "label": label,
                "kind": kind,
                "price": round(price, 3),
                "time_utc": row.get("open_time_utc"),
                "evidence_id": row.get("evidence_id"),
            })
            previous[kind] = price
    return sorted(swings, key=lambda row: str(row.get("time_utc") or ""))


def structure_state(swings: list[dict]) -> str:
    latest_high = next((row["label"] for row in reversed(swings) if row["kind"] == "high"), None)
    latest_low = next((row["label"] for row in reversed(swings) if row["kind"] == "low"), None)
    if latest_high == "HH" and latest_low == "HL":
        return "bullish_sequence"
    if latest_high == "LH" and latest_low == "LL":
        return "bearish_sequence"
    if latest_high == "HH" and latest_low == "LL":
        return "expanding_transition"
    if latest_high == "LH" and latest_low == "HL":
        return "compressing_balance"
    return "developing"


def _normalize_levels(level_rows: Iterable[dict], current_price: float, day_range: dict) -> list[dict]:
    seen: set[str] = set()
    levels = []
    day_low = _number(day_range.get("low"), current_price)
    day_high = _number(day_range.get("high"), current_price)
    allowance = max(5.0, _number(day_range.get("range")) * 0.5)
    for row in level_rows:
        level_id = str(row.get("level_id") or row.get("id") or "")
        if not level_id or level_id in seen:
            continue
        price = _number(row.get("price"))
        lo = _number(row.get("zone_low"), price)
        hi = _number(row.get("zone_high"), price)
        if lo > hi:
            lo, hi = hi, lo
        if price <= 0 or hi < day_low - allowance or lo > day_high + allowance:
            continue
        seen.add(level_id)
        timeframe = str(row.get("timeframe") or "")
        levels.append({
            "level_id": level_id,
            "timeframe": timeframe,
            "role": row.get("role"),
            "price": round(price, 3),
            "zone_low": round(lo, 3),
            "zone_high": round(hi, 3),
            "distance": round(abs(price - current_price), 3),
            "rank": TIMEFRAME_WEIGHT.get(timeframe, 0),
            "inside_today_range": bool(hi >= day_low and lo <= day_high),
        })
    # A level price actually traversed today outranks an untouched distant HTF
    # reference.  Proximity then keeps the bounded packet useful; owning
    # timeframe breaks ties rather than hiding active M5/M15 structure.
    levels.sort(key=lambda row: (
        not row["inside_today_range"], row["distance"], -row["rank"], row["level_id"]
    ))
    return levels[:24]


def _touch_groups(rows: list[dict], lo: float, hi: float) -> list[list[int]]:
    touched = [index for index, row in enumerate(rows) if row["high"] >= lo and row["low"] <= hi]
    groups: list[list[int]] = []
    for index in touched:
        if not groups or index > groups[-1][-1] + 1:
            groups.append([index])
        else:
            groups[-1].append(index)
    return groups


def verify_levels(levels: list[dict], rows: list[dict], current_price: float) -> list[dict]:
    verified = []
    for level in levels:
        lo, hi = level["zone_low"], level["zone_high"]
        groups = _touch_groups(rows, lo, hi)
        latest_response = "untested_today"
        last_touch = None
        if groups:
            group = groups[-1]
            last = rows[group[-1]]
            last_touch = last.get("close_time_utc")
            future = rows[group[-1] + 1:group[-1] + 4]
            closes = [row["close"] for row in future] or [last["close"]]
            prior_close = rows[group[0] - 1]["close"] if group[0] > 0 else None
            if all(close > hi for close in closes[-2:]) and len(closes) >= 2:
                latest_response = (
                    "rejected_from_above" if prior_close is not None and prior_close > hi
                    else "accepted_above"
                )
            elif all(close < lo for close in closes[-2:]) and len(closes) >= 2:
                latest_response = (
                    "rejected_from_below" if prior_close is not None and prior_close < lo
                    else "accepted_below"
                )
            elif last["close"] > hi:
                latest_response = "closed_above"
            elif last["close"] < lo:
                latest_response = "closed_below"
            else:
                latest_response = "balanced_inside"
        relation = "inside" if lo <= current_price <= hi else ("above" if current_price > hi else "below")
        verified.append({
            **{key: level.get(key) for key in ("level_id", "timeframe", "role", "price", "zone_low", "zone_high")},
            "touch_episodes_today": len(groups),
            "last_touch_utc": last_touch,
            "latest_closed_response": latest_response,
            "current_relation": relation,
            "_distance": level.get("distance", 0.0),
            "_rank": level.get("rank", 0),
        })
    verified.sort(key=lambda row: (
        -(row.get("touch_episodes_today") or 0), row.get("_distance", 0.0),
        -row.get("_rank", 0), row.get("level_id", ""),
    ))
    for row in verified:
        row.pop("_distance", None)
        row.pop("_rank", None)
    return verified[:12]


def _path_blocks(rows: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for row in rows:
        opened = _utc(row.get("open_time_utc"))
        if not opened:
            continue
        minute = 0 if opened.minute < 30 else 30
        key = opened.replace(minute=minute, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%MZ")
        buckets.setdefault(key, []).append(row)
    output = []
    for key in sorted(buckets)[-12:]:
        aggregate = _aggregate(buckets[key])
        output.append({"window_start_utc": key, **aggregate})
    return output


def _notable_moves(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    bodies = [abs(row["close"] - row["open"]) for row in rows]
    ranges = [row["high"] - row["low"] for row in rows]
    volumes = [row["tick_volume"] for row in rows if row["tick_volume"] > 0]
    median_body = median(bodies) if bodies else 0.0
    median_range = median(ranges) if ranges else 0.0
    median_volume = median(volumes) if volumes else 0.0
    output = []
    for row, body, candle_range in zip(rows, bodies, ranges):
        body_share = body / candle_range if candle_range > 0 else 0.0
        expanded = (
            (median_body > 0 and body >= median_body * 1.5)
            or (median_range > 0 and candle_range >= median_range * 1.5)
        )
        if not expanded or body_share < 0.55:
            continue
        output.append({
            "time_utc": row.get("open_time_utc"),
            "direction": "up" if row["close"] > row["open"] else "down",
            "open": round(row["open"], 3),
            "close": round(row["close"], 3),
            "range": round(candle_range, 3),
            "body_share": round(body_share, 3),
            "tick_volume_vs_day_median": (
                round(row["tick_volume"] / median_volume, 2) if median_volume > 0 else None
            ),
            "evidence_id": row.get("evidence_id"),
        })
    return output[-8:]


def build_snapshot(
    *,
    symbol: str,
    level_rows: Iterable[dict],
    bar_provider: Callable[[str, str, int], list[dict]],
    now: datetime | None = None,
    prior_analysis: dict | None = None,
    session: dict | None = None,
) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    m5 = _closed_today(bar_provider(symbol, "M5", 320), now)
    if len(m5) < 5:
        raise RuntimeError("insufficient_completed_m5_for_intraday_observer")
    today = _aggregate(m5)
    current_price = _number(today.get("close"))
    swings = confirmed_swings(m5, order=2)
    levels = verify_levels(_normalize_levels(level_rows, current_price, today), m5, current_price)
    episode_minute = 0 if now.minute < 30 else 30
    episode_start = now.replace(minute=episode_minute, second=0, microsecond=0)
    snapshot = {
        "symbol": symbol,
        "as_of_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "episode_id": f"{symbol}-{episode_start:%Y%m%dT%H%MZ}",
        "today_tape": today,
        "session": session or {},
        "half_hour_path": _path_blocks(m5),
        "notable_closed_moves": _notable_moves(m5),
        "structure": {
            "timeframe": "M5",
            "method": "confirmed_pivot_order_2_closed_candles",
            "state": structure_state(swings),
            "sequence": swings[-12:],
        },
        "levels": levels,
        "prior_qwen_analysis": prior_analysis or {},
        "constraints": {
            "closed_candles_only": True,
            "deterministic_facts_authoritative": True,
            "execution_authority": False,
            "causality_limited_to_supplied_evidence": True,
        },
    }
    fingerprint_payload = {
        "episode": snapshot["episode_id"],
        "structure": snapshot["structure"],
        "levels": levels,
    }
    snapshot["fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return snapshot
