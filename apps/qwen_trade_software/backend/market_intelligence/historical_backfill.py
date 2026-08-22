"""Maximum MT5 history backfill with DST-aware New York H4 construction."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .collector import direction_at

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
TIMEFRAME_SECONDS = {
    "M1": 60, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


def native_rows(mt5, broker_symbol: str, logical_symbol: str, timeframe: str,
                count: int = 99_999) -> list[dict]:
    rates = mt5.copy_rates_from_pos(
        broker_symbol, getattr(mt5, f"TIMEFRAME_{timeframe}"), 1, min(count, 99_999)
    )
    if rates is None:
        raise RuntimeError(f"MT5 {broker_symbol} {timeframe}: {mt5.last_error()}")
    seconds = TIMEFRAME_SECONDS[timeframe]
    rows = []
    for rate in sorted(rates, key=lambda item: int(item["time"])):
        opened = datetime.fromtimestamp(int(rate["time"]), UTC)
        rows.append({
            "open_time": opened, "close_time": opened + timedelta(seconds=seconds),
            "open": float(rate["open"]), "high": float(rate["high"]),
            "low": float(rate["low"]), "close": float(rate["close"]),
            "tick_volume": int(rate["tick_volume"]),
            "spread": int(rate["spread"]), "real_volume": int(rate["real_volume"]),
            "source": "MT5", "symbol": logical_symbol,
        })
    return rows


def ny_h4_start(opened_utc: datetime) -> datetime:
    local = opened_utc.astimezone(NEW_YORK)
    anchor_date = local.date() if local.hour >= 17 else (local - timedelta(days=1)).date()
    anchor = datetime(anchor_date.year, anchor_date.month, anchor_date.day, 17,
                      tzinfo=NEW_YORK)
    slot = int((local - anchor).total_seconds() // 14_400)
    return (anchor + timedelta(hours=slot * 4)).astimezone(UTC)


def aggregate_ny_h4(h1_rows: list[dict], *, include_forming: bool = False) -> list[dict]:
    groups: dict[datetime, list[dict]] = {}
    for row in h1_rows:
        groups.setdefault(ny_h4_start(row["open_time"]), []).append(row)
    result = []
    for opened, rows in sorted(groups.items()):
        rows.sort(key=lambda row: row["open_time"])
        closed = (opened.astimezone(NEW_YORK) + timedelta(hours=4)).astimezone(UTC)
        complete = closed <= datetime.now(UTC)
        if not complete and not include_forming:
            continue
        result.append({
            "open_time": opened, "close_time": closed,
            "open": rows[0]["open"], "high": max(row["high"] for row in rows),
            "low": min(row["low"] for row in rows), "close": rows[-1]["close"],
            "tick_volume": sum(row["tick_volume"] for row in rows),
            "real_volume": sum(row["real_volume"] for row in rows),
            "spread": rows[-1]["spread"], "source": "MT5_H1_AGGREGATED",
            "symbol": rows[0]["symbol"], "constituent_count": len(rows),
            "is_complete": complete,
        })
    return result


def candle_events(symbol: str, timeframe: str, rows: list[dict],
                  convention: str = "broker") -> list[dict]:
    bars = [{"close": row["close"], "high": row["high"], "low": row["low"]}
            for row in rows]
    events = []
    for index, row in enumerate(rows):
        opened = row["open_time"]
        evidence = f"candle:{symbol}:{timeframe}:{convention}:{opened:%Y-%m-%dT%H:%M:%SZ}"
        payload = {key: row[key] for key in
                   ("open", "high", "low", "close", "tick_volume", "real_volume", "spread", "source")}
        payload["direction"] = direction_at(bars, index)
        payload["time_convention"] = convention
        if "constituent_count" in row:
            payload["constituent_count"] = row["constituent_count"]
        events.append({
            "event_id": f"{symbol}:{timeframe}:{evidence}:close", "symbol": symbol,
            "timeframe": timeframe, "event_type": "candle_closed",
            "event_time_utc": row["close_time"].isoformat().replace("+00:00", "Z"),
            "evidence_id": evidence, "payload": payload,
        })
    return events
