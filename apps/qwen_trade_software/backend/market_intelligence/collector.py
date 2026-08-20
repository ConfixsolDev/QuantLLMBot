"""Direct MT5 source and lossless completed-candle backfill."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .cross_market import discover_dxy_symbol
from .projection import TIMEFRAMES, reduce_event


def _mt5_timeframe(mt5, timeframe: str):
    return getattr(mt5, f"TIMEFRAME_{timeframe}")


def closed_bars(mt5, symbol: str, timeframe: str, count: int) -> list[dict]:
    rates = mt5.copy_rates_from_pos(symbol, _mt5_timeframe(mt5, timeframe), 1, count)
    if rates is None:
        return []
    seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
               "H1": 3600, "H4": 14400, "D1": 86400}[timeframe]
    rows = []
    for rate in sorted(rates, key=lambda row: int(row["time"])):
        opened = datetime.fromtimestamp(int(rate["time"]), timezone.utc)
        prefix = "DXY" if symbol == "DXY" else symbol
        evidence_id = (
            f"DXY_{timeframe}_{opened:%Y%m%dT%H%M%SZ}" if prefix == "DXY" else
            f"candle:{symbol}:{timeframe}:{opened:%Y-%m-%dT%H:%M:%SZ}"
        )
        rows.append({
            "evidence_id": evidence_id,
            "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
            "close_time_utc": (opened + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
            "open": float(rate["open"]), "high": float(rate["high"]),
            "low": float(rate["low"]), "close": float(rate["close"]),
            "tick_volume": int(rate["tick_volume"]),
        })
    return rows


def direction_at(bars: list[dict], index: int) -> str:
    window = bars[max(0, index - 5):index + 1]
    if len(window) < 2:
        return "unknown"
    first, last = window[0]["close"], window[-1]["close"]
    highs, lows = [b["high"] for b in window], [b["low"] for b in window]
    if last > first and highs[-1] >= max(highs[:-1]):
        return "bullish"
    if last < first and lows[-1] <= min(lows[:-1]):
        return "bearish"
    return "ranging"


def ingest_bars(store, logical_symbol: str, timeframe: str, bars: list[dict]) -> int:
    """Append every unseen bar in order; never sample only the newest bar."""
    inserted = 0
    for index, bar in enumerate(bars):
        event_id = f"{logical_symbol}:{timeframe}:{bar['evidence_id']}:close"
        event = {
            "event_id": event_id, "symbol": logical_symbol,
            "timeframe": timeframe, "event_type": "candle_closed",
            "event_time_utc": bar["close_time_utc"],
            "evidence_id": bar["evidence_id"],
            "payload": {"open": bar["open"], "high": bar["high"],
                        "low": bar["low"], "close": bar["close"],
                        "tick_volume": bar["tick_volume"],
                        "direction": direction_at(bars, index)},
        }
        if not store.append_event(event):
            continue
        prior = store.projection(logical_symbol, timeframe)
        # Historical backfill belongs in the ledger but must not roll the live
        # materialized view backward. Startup replay sorts by event time.
        if not prior or str(event["event_time_utc"]) >= str(prior.get("event_time_utc") or ""):
            state = reduce_event(prior, event)
            store.put_projection(logical_symbol, timeframe, state, event_id)
        inserted += 1
    return inserted


def collect_once(store, mt5, xau_symbol: str, lookback: int = 300) -> dict:
    inserted = {}
    for timeframe in TIMEFRAMES:
        rows = closed_bars(mt5, xau_symbol, timeframe, lookback)
        inserted[f"{xau_symbol}:{timeframe}"] = ingest_bars(
            store, xau_symbol, timeframe, rows
        )
    dxy_broker = discover_dxy_symbol(mt5)
    if dxy_broker:
        for timeframe in ("H4", "H1", "M30", "M15"):
            rows = closed_bars(mt5, dxy_broker, timeframe, lookback)
            # Stable logical symbol keeps broker suffixes out of memory/RAG.
            for row in rows:
                opened = datetime.fromisoformat(row["open_time_utc"].replace("Z", "+00:00"))
                row["evidence_id"] = f"DXY_{timeframe}_{opened:%Y%m%dT%H%M%SZ}"
            inserted[f"DXY:{timeframe}"] = ingest_bars(store, "DXY", timeframe, rows)
    return {"inserted": inserted, "inserted_total": sum(inserted.values()),
            "dxy_broker_symbol": dxy_broker}
