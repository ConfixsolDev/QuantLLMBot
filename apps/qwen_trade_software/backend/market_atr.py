"""ATR snapshot for every Qwen request/response record.

2026-08-13 -- V5 convention (fast leg 3)
---------------------------------------
Train and live both use two M1 Wilder ATRs on closed bars:

    atr_m1_51       — slower volatility baseline (51-period M1)
    atr_m1_3        — fast local volatility (3-period M1)
    atr_ratio_3_51  — atr_m1_3 / atr_m1_51 when both present

Use the ratio as a regime *hint* (compress / normal / expand). Do not hard-gate
entries on fixed ratio thresholds in code — teach location in curriculum.

Capture at request time; inject the same snapshot onto the response so the
I/O record and the decision record stay joined.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# V5 dual ATR on M1 only (fast=3, slow=51).
ATR_M1_PERIODS = (51, 3)
ATR_TIMEFRAME = "M1"


def wilder_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int,
) -> float | None:
    """Classic Wilder ATR from oldest→newest closed OHLC series."""
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(float(tr))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 5)


def atr_ratio_3_51(atr_m1_3: float | None, atr_m1_51: float | None) -> float | None:
    """Fast/slow ATR ratio; None when either leg is missing or slow is zero."""
    if atr_m1_3 is None or atr_m1_51 is None:
        return None
    if atr_m1_51 <= 0:
        return None
    return round(float(atr_m1_3) / float(atr_m1_51), 4)


def _rates_to_series(rates) -> tuple[list[float], list[float], list[float], int | None]:
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    last_time: int | None = None
    for row in rates:
        highs.append(float(row["high"]))
        lows.append(float(row["low"]))
        closes.append(float(row["close"]))
        try:
            last_time = int(row["time"])
        except (KeyError, TypeError, ValueError):
            continue
    return highs, lows, closes, last_time


def empty_atr_snapshot(
    symbol: str | None = None,
    *,
    error: str | None = None,
    bars: int = 0,
    as_of: datetime | None = None,
    source: str = "cache",
) -> dict[str, Any]:
    """Failed ATR snapshot that never touches MT5."""
    as_of_utc = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "timeframe": ATR_TIMEFRAME,
        "periods": list(ATR_M1_PERIODS),
        "symbol": symbol,
        "as_of_utc": as_of_utc.isoformat(),
        "ok": False,
        "atr_m1_51": None,
        "atr_m1_3": None,
        "atr_ratio_3_51": None,
        "bars": bars,
        "last_closed_time_utc": None,
        "source": source,
        "error": error,
    }


def snapshot_atr_from_cache(
    m1_bars: list | None,
    symbol: str | None = None,
    *,
    periods: tuple[int, ...] = ATR_M1_PERIODS,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Compute ATR from already-cached M1 bars. No MT5 call.

    m1_bars: oldest→newest rows with high/low/close (cache or dict rates).
    """
    as_of_utc = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    count = 0 if not m1_bars else len(m1_bars)
    out = empty_atr_snapshot(symbol, bars=count, as_of=as_of_utc, source="cache")
    need = max(periods) + 1
    if not m1_bars or count < need:
        out["error"] = f"insufficient_cached_bars:{count}<{need}"
        return out
    try:
        computed = atr_from_rates(m1_bars, periods=periods)
        out["atr_m1_51"] = computed.get("atr_m1_51")
        out["atr_m1_3"] = computed.get("atr_m1_3")
        out["atr_ratio_3_51"] = computed.get("atr_ratio_3_51")
        out["bars"] = computed.get("bars") or count
        out["last_closed_time_utc"] = computed.get("last_closed_time_utc")
        if out["last_closed_time_utc"] is None:
            stamp = m1_bars[-1].get("close_time_utc") or m1_bars[-1].get("open_time_utc")
            if stamp:
                out["last_closed_time_utc"] = str(stamp)
        out["ok"] = out["atr_m1_51"] is not None and out["atr_m1_3"] is not None
        if not out["ok"] and out["error"] is None:
            out["error"] = "atr_unavailable"
    except Exception as exc:
        out["error"] = str(exc)
    return out


def atr_from_rates(rates, periods: tuple[int, ...] = ATR_M1_PERIODS) -> dict[str, float | None]:
    """Compute named atr_m1_<period> values from an MT5 rates array."""
    highs, lows, closes, last_time = _rates_to_series(rates)
    out: dict[str, float | None] = {
        "last_closed_time_utc": (
            datetime.fromtimestamp(last_time, tz=timezone.utc).isoformat()
            if last_time is not None
            else None
        ),
        "bars": len(closes),
    }
    for period in periods:
        out[f"atr_m1_{period}"] = wilder_atr(highs, lows, closes, period=period)
    out["atr_ratio_3_51"] = atr_ratio_3_51(out.get("atr_m1_3"), out.get("atr_m1_51"))
    return out


def snapshot_atr(
    symbol: str | None = None,
    *,
    periods: tuple[int, ...] = ATR_M1_PERIODS,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Non-fatal M1 ATR snapshot. Never raises into a Qwen call path.

    as_of: when set, use closed M1 bars ending at/before that UTC time (backfill).
    """
    as_of_utc = (as_of or datetime.now(timezone.utc)).astimezone(timezone.utc)
    out: dict[str, Any] = {
        "timeframe": ATR_TIMEFRAME,
        "periods": list(periods),
        "symbol": symbol,
        "as_of_utc": as_of_utc.isoformat(),
        "ok": False,
        "atr_m1_51": None,
        "atr_m1_3": None,
        "atr_ratio_3_51": None,
        "bars": 0,
        "last_closed_time_utc": None,
        "error": None,
    }
    try:
        import MetaTrader5 as mt5
        from review_shared import GOLD_SYMBOL

        symbol = symbol or GOLD_SYMBOL
        out["symbol"] = symbol
        term = mt5.terminal_info()
        if term is None:
            out["error"] = f"mt5_not_connected:{mt5.last_error()}"
            return out

        need = max(periods) + 1
        # Extra bars so Wilder smoothing is stable past the seed window.
        count = need + max(periods)
        if as_of is None:
            # Closed bars only: skip the forming bar at position 0.
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 1, count)
        else:
            rates = mt5.copy_rates_from(
                symbol, mt5.TIMEFRAME_M1, as_of_utc.replace(tzinfo=None), count
            )
        if rates is None or len(rates) < need:
            out["error"] = "insufficient_bars"
            out["bars"] = 0 if rates is None else int(len(rates))
            out["mt5_last_error"] = list(mt5.last_error()) if rates is None else None
            return out

        computed = atr_from_rates(rates, periods=periods)
        out["atr_m1_51"] = computed.get("atr_m1_51")
        out["atr_m1_3"] = computed.get("atr_m1_3")
        out["atr_ratio_3_51"] = computed.get("atr_ratio_3_51")
        out["bars"] = computed.get("bars") or 0
        out["last_closed_time_utc"] = computed.get("last_closed_time_utc")
        out["ok"] = out["atr_m1_51"] is not None and out["atr_m1_3"] is not None
        if not out["ok"] and out["error"] is None:
            out["error"] = "atr_unavailable"
    except Exception as exc:
        out["error"] = str(exc)
    return out
