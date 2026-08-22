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
        evidence_id = f"candle:{prefix}:{timeframe}:broker:{opened:%Y-%m-%dT%H:%M:%SZ}"
        rows.append({
            "evidence_id": evidence_id,
            "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
            "close_time_utc": (opened + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z"),
            "open": float(rate["open"]), "high": float(rate["high"]),
            "low": float(rate["low"]), "close": float(rate["close"]),
            "tick_volume": int(rate["tick_volume"]),
            "spread": int(rate["spread"]),
            "real_volume": int(rate["real_volume"]),
            "source": "MT5",
            "time_convention": "broker",
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
            "payload": {**{key: bar[key] for key in (
                            "open", "high", "low", "close", "tick_volume",
                            "spread", "real_volume", "source", "time_convention",
                            "constituent_count") if key in bar},
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
    xau_h1 = []
    for timeframe in (tf for tf in TIMEFRAMES if tf != "H4"):
        rows = closed_bars(mt5, xau_symbol, timeframe, lookback)
        if timeframe == "H1":
            xau_h1 = rows
        inserted[f"{xau_symbol}:{timeframe}"] = ingest_bars(
            store, xau_symbol, timeframe, rows
        )
    inserted[f"{xau_symbol}:H4"] = ingest_bars(
        store, xau_symbol, "H4", _ny_h4_bars(xau_symbol, xau_h1)
    )
    dxy_broker = discover_dxy_symbol(mt5)
    if dxy_broker:
        dxy_h1 = []
        for timeframe in ("M1", "M15", "M30", "H1", "D1"):
            rows = closed_bars(mt5, dxy_broker, timeframe, lookback)
            for row in rows:
                opened = datetime.fromisoformat(row["open_time_utc"].replace("Z", "+00:00"))
                row["evidence_id"] = (
                    f"candle:DXY:{timeframe}:broker:{opened:%Y-%m-%dT%H:%M:%SZ}"
                )
            if timeframe == "H1":
                dxy_h1 = rows
            inserted[f"DXY:{timeframe}"] = ingest_bars(store, "DXY", timeframe, rows)
        inserted["DXY:H4"] = ingest_bars(store, "DXY", "H4", _ny_h4_bars("DXY", dxy_h1))
    return {"inserted": inserted, "inserted_total": sum(inserted.values()),
            "dxy_broker_symbol": dxy_broker}


def _ny_h4_bars(symbol: str, h1_bars: list[dict]) -> list[dict]:
    """Adapt completed H1 rows into the sole DST-aware H4 convention."""
    from .historical_backfill import aggregate_ny_h4
    native = []
    for row in h1_bars:
        native.append({
            **row, "symbol": symbol,
            "open_time": datetime.fromisoformat(row["open_time_utc"].replace("Z", "+00:00")),
            "close_time": datetime.fromisoformat(row["close_time_utc"].replace("Z", "+00:00")),
        })
    result = []
    for row in aggregate_ny_h4(native):
        opened = row["open_time"]
        result.append({
            **row,
            "evidence_id": f"candle:{symbol}:H4:new_york_1700_dst:{opened:%Y-%m-%dT%H:%M:%SZ}",
            "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
            "close_time_utc": row["close_time"].isoformat().replace("+00:00", "Z"),
            "time_convention": "new_york_1700_dst",
        })
    return result
