"""Mechanical CHoCH / BOS / FVG / liquidity-sweep labels on closed M5/M15.

Python labels what printed. Qwen judges whether it matters at the mapped zone.
These labels are never a fill gate — executor uses M1 failure-at-zone after
direction, zone and structural geometry are already validated.

2026-08-18: M1 confirmations removed. In range markets M1 structure breaks
are noise — false CHoCH/BOS signals that mislead the model. M5 is the minimum
reliable timeframe for structural confirmation on XAUUSD; M15 is added for
higher-quality signals that yield bigger trades.
"""

from __future__ import annotations

from typing import Any

import live_mapped_levels

MAX_FVG = 2


def _kind(item: dict) -> str:
    return str(item.get("kind") or item.get("type") or "")


def _combined_swings(rows: list[dict], wing: int) -> list[dict]:
    if not rows:
        return []
    highs = live_mapped_levels.fractal_swings(rows, wing, "high")
    lows = live_mapped_levels.fractal_swings(rows, wing, "low")
    combined = highs + lows
    combined.sort(
        key=lambda item: (
            item.get("index", 0),
            str(item.get("close_time_utc") or item.get("open_time_utc") or ""),
        )
    )
    return combined


def detect_fvg(rows: list[dict], lookback: int = 24) -> list[dict]:
    """Three-candle fair-value gaps on closed bars. Most recent unfilled first."""
    if len(rows) < 3:
        return []
    window = rows[-lookback:] if len(rows) > lookback else rows
    found: list[dict] = []
    for i in range(2, len(window)):
        left = window[i - 2]
        right = window[i]
        left_high = float(left["high"])
        left_low = float(left["low"])
        right_high = float(right["high"])
        right_low = float(right["low"])
        later = window[i + 1 :]
        if left_high < right_low:
            gap_low, gap_high = left_high, right_low
            filled = any(float(bar["low"]) <= gap_low for bar in later)
            found.append(
                {
                    "side": "bullish",
                    "gap_low": round(gap_low, 3),
                    "gap_high": round(gap_high, 3),
                    "filled": filled,
                    "evidence_id": right.get("evidence_id"),
                }
            )
        elif left_low > right_high:
            gap_low, gap_high = right_high, left_low
            filled = any(float(bar["high"]) >= gap_high for bar in later)
            found.append(
                {
                    "side": "bearish",
                    "gap_low": round(gap_low, 3),
                    "gap_high": round(gap_high, 3),
                    "filled": filled,
                    "evidence_id": right.get("evidence_id"),
                }
            )
    unfilled = [row for row in reversed(found) if not row["filled"]]
    return unfilled[:MAX_FVG]


def detect_liquidity_sweep(rows: list[dict], swings: list[dict]) -> dict | None:
    """Wick through last swing, close back inside — not a closed break."""
    if not rows or not swings:
        return None
    last = rows[-1]
    highs = [item for item in swings if _kind(item) == "high"]
    lows = [item for item in swings if _kind(item) == "low"]
    high = float(last["high"])
    low = float(last["low"])
    close = float(last["close"])
    if highs:
        level = float(highs[-1]["price"])
        if high > level and close <= level:
            return {
                "kind": "sweep_high",
                "level": round(level, 3),
                "close": round(close, 3),
                "evidence_id": last.get("evidence_id"),
            }
    if lows:
        level = float(lows[-1]["price"])
        if low < level and close >= level:
            return {
                "kind": "sweep_low",
                "level": round(level, 3),
                "close": round(close, 3),
                "evidence_id": last.get("evidence_id"),
            }
    return None


def last_structure_event(rows: list[dict], swings: list[dict]) -> dict:
    """BOS with the swing sequence; CHoCH against it. Last closed bar only."""
    pattern = live_mapped_levels.classify_swing_sequence(swings)
    empty = {"bos": None, "choch": None, "swing_pattern": pattern}
    if not rows or not swings:
        return empty
    highs = [item for item in swings if _kind(item) == "high"]
    lows = [item for item in swings if _kind(item) == "low"]
    if not highs or not lows:
        return empty
    close = float(rows[-1]["close"])
    last_high = float(highs[-1]["price"])
    last_low = float(lows[-1]["price"])
    evidence = rows[-1].get("evidence_id")
    bos = None
    choch = None
    if pattern == "hh_hl":
        if close > last_high:
            bos = {
                "direction": "bullish",
                "broken": round(last_high, 3),
                "evidence_id": evidence,
            }
        elif close < last_low:
            choch = {
                "direction": "bearish",
                "broken": round(last_low, 3),
                "evidence_id": evidence,
            }
    elif pattern == "lh_ll":
        if close < last_low:
            bos = {
                "direction": "bearish",
                "broken": round(last_low, 3),
                "evidence_id": evidence,
            }
        elif close > last_high:
            choch = {
                "direction": "bullish",
                "broken": round(last_high, 3),
                "evidence_id": evidence,
            }
    elif pattern == "mixed":
        if close > last_high:
            choch = {
                "direction": "bullish",
                "broken": round(last_high, 3),
                "evidence_id": evidence,
            }
        elif close < last_low:
            choch = {
                "direction": "bearish",
                "broken": round(last_low, 3),
                "evidence_id": evidence,
            }
    return {"bos": bos, "choch": choch, "swing_pattern": pattern}


def confirmations_for_bars(rows: list[dict], timeframe: str) -> dict[str, Any]:
    wing = live_mapped_levels.WING.get(timeframe, 2)
    swings = _combined_swings(rows, wing)
    event = last_structure_event(rows, swings)
    sweep = detect_liquidity_sweep(rows, swings)
    return {
        "timeframe": timeframe,
        "swing_pattern": event["swing_pattern"],
        "bos": event["bos"],
        "choch": event["choch"],
        "liquidity_sweep": sweep,
        "fvg": detect_fvg(rows),
        "bars": len(rows),
    }


def snapshot_confirmations(symbol: str | None = None) -> dict[str, Any]:
    """Cached M5/M15 labels. Never raises; never calls MT5.

    2026-08-18: M1 dropped — too noisy in range markets. M5 is the minimum
    confirmation timeframe; M15 added for higher-conviction structure breaks.
    """
    empty_tf = {
        "timeframe": "",
        "swing_pattern": "insufficient",
        "bos": None,
        "choch": None,
        "liquidity_sweep": None,
        "fvg": [],
        "bars": 0,
    }
    packet = {
        "m5": {**empty_tf, "timeframe": "M5"},
        "m15": {**empty_tf, "timeframe": "M15"},
    }
    try:
        from market_context_cache import get_cached_completed_bars

        m5 = get_cached_completed_bars(symbol, "M5", 96)
        m15 = get_cached_completed_bars(symbol, "M15", 96)
        if m5:
            packet["m5"] = confirmations_for_bars(m5, "M5")
        if m15:
            packet["m15"] = confirmations_for_bars(m15, "M15")
    except Exception:
        pass
    return packet


def compact_confirmation_log(packet: dict | None) -> str:
    """One-line log token: m5_choch=bearish m15_sweep=sweep_high m5_fvg=1."""
    parts = []
    for tf in ("m5", "m15"):
        row = (packet or {}).get(tf) or {}
        if row.get("bos"):
            parts.append(f"{tf}_bos={row['bos'].get('direction')}")
        if row.get("choch"):
            parts.append(f"{tf}_choch={row['choch'].get('direction')}")
        sweep = row.get("liquidity_sweep") or {}
        if sweep.get("kind"):
            parts.append(f"{tf}_sweep={sweep['kind']}")
        fvg_n = len(row.get("fvg") or [])
        if fvg_n:
            parts.append(f"{tf}_fvg={fvg_n}")
    return " ".join(parts) if parts else "none"
