"""Read-only MT5 connector for DXY completed candles."""

from __future__ import annotations

from datetime import datetime, timezone

TF_MAP = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
DXY_CANDIDATES = ("DXY", "USDX", "USDIndex", "US Dollar Index")


def _mt5_timeframe(mt5, timeframe: str):
    return getattr(mt5, f"TIMEFRAME_{timeframe}")


def discover_dxy_symbol(mt5) -> str | None:
    for name in DXY_CANDIDATES:
        info = mt5.symbol_info(name)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(name, True)
            return name
    for row in mt5.symbols_get() or []:
        name = str(getattr(row, "name", ""))
        upper = name.upper()
        if "DXY" in upper or "USDX" in upper or "USDINDEX" in upper:
            mt5.symbol_select(name, True)
            return name
    return None


def completed_bars(timeframe: str, count: int = 80) -> tuple[str | None, list[dict]]:
    """Fetch only closed DXY bars; unavailable data degrades to empty context."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return None, []
    if not mt5.initialize():
        return None, []
    symbol = discover_dxy_symbol(mt5)
    if not symbol:
        return None, []
    rates = mt5.copy_rates_from_pos(symbol, _mt5_timeframe(mt5, timeframe), 1, max(10, min(count, 300)))
    rows = []
    for rate in rates if rates is not None else []:
        opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
        rows.append({"evidence_id": f"DXY_{timeframe}_{opened:%Y%m%dT%H%M%SZ}",
                     "open_time_utc": opened.isoformat(), "open": float(rate["open"]),
                     "high": float(rate["high"]), "low": float(rate["low"]),
                     "close": float(rate["close"]), "tick_volume": int(rate["tick_volume"])})
    return symbol, rows


def summarize(timeframe: str, bars: list[dict]) -> dict:
    if len(bars) < 6:
        return {"status": "unavailable", "timeframe": timeframe, "direction": "unknown"}
    recent = bars[-6:]
    first, last = recent[0]["close"], recent[-1]["close"]
    highs = [b["high"] for b in recent]
    lows = [b["low"] for b in recent]
    direction = "bullish" if last > first and highs[-1] >= max(highs[:-1]) else (
        "bearish" if last < first and lows[-1] <= min(lows[:-1]) else "range"
    )
    return {"status": "ok", "timeframe": timeframe, "direction": direction,
            "state": f"{direction}_structure", "close": last,
            "range_high": max(highs), "range_low": min(lows),
            "evidence_ids": [b["evidence_id"] for b in recent[-3:]],
            "latest": recent[-1]}
