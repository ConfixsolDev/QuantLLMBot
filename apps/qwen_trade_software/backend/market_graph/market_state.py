"""Normalize the authoritative cache's levels and structure for Neo4j."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def evidence_confidence(level: dict) -> int:
    """Transparent data-quality score, not a prediction probability."""
    base = {
        "operator_mapped": 70, "latest_completed_candle": 60,
        "live_closed_swing": 55, "floor_pp_hlc3": 50,
    }.get(str(level.get("calculation_method")), 45)
    tests = max(0, int(level.get("test_count") or 0))
    evidence = len(level.get("source_candle_ids") or [])
    return min(95, base + min(20, tests * 5) + min(10, evidence * 2))


def load_current_market_state(path: Path, symbols: tuple[str, ...]) -> dict:
    if not path.exists():
        return {"levels": [], "structures": [], "prices": {}}
    connection = sqlite3.connect(path, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT cache_type,cache_epoch,symbol,valid_as_of_utc,payload_json "
            "FROM cache_objects WHERE is_current=1 AND cache_type IN ('levels','structural') "
            "ORDER BY valid_as_of_utc DESC"
        ).fetchall()
    finally:
        connection.close()
    latest: dict[tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        if row["symbol"] in symbols:
            latest.setdefault((row["symbol"], row["cache_type"]), row)
    levels, structures, prices = [], [], {}
    for (symbol, cache_type), row in latest.items():
        payload = json.loads(row["payload_json"])
        if cache_type == "levels":
            if payload.get("price") is not None:
                prices[symbol] = float(payload["price"])
            for level in payload.get("levels") or []:
                if not level.get("level_id") or not level.get("timeframe"):
                    continue
                levels.append({
                    "key": f"{symbol}:{level['timeframe']}:{level['level_id']}",
                    "symbol": symbol, "timeframe": level["timeframe"],
                    "level_id": level["level_id"], "role": level.get("role"),
                    "label": level.get("label"), "pattern": level.get("pattern"),
                    "zone_low": float(level["zone_low"]),
                    "zone_high": float(level["zone_high"]),
                    "method": level.get("calculation_method"),
                    "test_count": int(level.get("test_count") or 0),
                    "left_after_first": bool(level.get("left_after_first", False)),
                    "valid_from": level.get("valid_from_utc") or row["valid_as_of_utc"],
                    "last_seen": row["valid_as_of_utc"], "snapshot_epoch": row["cache_epoch"],
                    "confidence": evidence_confidence(level),
                    "evidence_ids": list(dict.fromkeys(level.get("source_candle_ids") or []))[:24],
                })
        else:
            for timeframe, state in (payload.get("timeframe_location") or {}).items():
                structures.append({
                    "id": f"{symbol}:{timeframe}:{row['cache_epoch']}",
                    "symbol": symbol, "timeframe": timeframe,
                    "snapshot_epoch": row["cache_epoch"], "observed_at": row["valid_as_of_utc"],
                    "location": state.get("location"), "auction_state": state.get("auction_state"),
                    "confidence": min(95, 55 + 5 * len(state.get("evidence_ids") or [])),
                    "evidence_ids": list(dict.fromkeys(state.get("evidence_ids") or []))[:24],
                })
    return {"levels": levels, "structures": structures, "prices": prices}
