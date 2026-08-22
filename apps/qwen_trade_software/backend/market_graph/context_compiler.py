"""Compile raw Neo4j facts into a small, neutral market-memory packet."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from statistics import mean

from .rag_protocol import protocol_descriptor
from .semantic_memory import relevant_for_zone
from .temporal import TIMEFRAME_SECONDS, utc_datetime

TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M5", "M1")
TF_RANK = {timeframe: len(TIMEFRAMES) - index for index, timeframe in enumerate(TIMEFRAMES)}


def _number(value, digits=3):
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _latest(symbol: dict, timeframe: str) -> dict:
    events = symbol.get(timeframe) or []
    return events[0] if events else {}


def _volume(events: list[dict]) -> dict:
    usable = [event for event in events if event.get("tick_volume") is not None]
    bullish = [float(e["tick_volume"]) for e in usable if float(e.get("close", 0)) > float(e.get("open", 0))]
    bearish = [float(e["tick_volume"]) for e in usable if float(e.get("close", 0)) < float(e.get("open", 0))]
    bull_avg = mean(bullish) if bullish else None
    bear_avg = mean(bearish) if bearish else None
    ratio = bull_avg / bear_avg if bull_avg is not None and bear_avg not in (None, 0) else None
    return {"measure": "tick_volume_participation_proxy", "bullish_candle_average": _number(bull_avg, 2),
            "bearish_candle_average": _number(bear_avg, 2), "bullish_to_bearish_ratio": _number(ratio, 2),
            "sample_count": len(usable)}


def _temporal_row(symbol: dict, timeframe: str, as_of: datetime) -> dict:
    event = _latest(symbol, timeframe)
    structures = {row.get("timeframe"): row for row in symbol.get("market_structure") or []}
    evidence = (symbol.get("structure_evidence") or {}).get(timeframe) or []
    latest_structure = evidence[0] if evidence else {}
    remaining = percent = None
    freshness = "missing"
    if event.get("event_time"):
        closed = utc_datetime(event["event_time"])
        seconds = TIMEFRAME_SECONDS[timeframe]
        age = max(0.0, (as_of - closed).total_seconds())
        freshness = "fresh" if age < seconds else "stale"
        if freshness == "fresh":
            remaining = max(0, int((closed + timedelta(seconds=seconds) - as_of).total_seconds()))
            percent = round(100 * (1 - remaining / seconds), 1)
    state = structures.get(timeframe, {})
    volume = _volume(symbol.get(timeframe) or [])
    return {
        "timeframe": timeframe,
        "trend_state": event.get("direction") or "unknown",
        "forming_leg": event.get("transition") or event.get("state") or "unresolved",
        "auction_state": state.get("auction_state") or latest_structure.get("zone_status") or "unknown",
        "range_location": state.get("location") or "unknown",
        "latest_structure": latest_structure.get("event_type") or "none",
        "volume_confirmation": {"ratio": volume["bullish_to_bearish_ratio"],
                                "sample_count": volume["sample_count"]},
        "candle_seconds_remaining": remaining,
        "candle_percent_complete": percent,
        "freshness": freshness,
        "evidence_id": event.get("evidence_id"),
    }


def _zone_groups(levels: list[dict], price: float) -> list[list[dict]]:
    valid = [row for row in levels if _number(row.get("zone_low")) is not None and _number(row.get("zone_high")) is not None]
    valid.sort(key=lambda row: abs((float(row["zone_low"]) + float(row["zone_high"])) / 2 - price))
    candidates = valid[:60]
    tolerance = max(0.25, abs(price) * 0.00015)
    groups: list[list[dict]] = []
    for row in candidates:
        row_low, row_high = float(row["zone_low"]), float(row["zone_high"])
        midpoint = (float(row["zone_low"]) + float(row["zone_high"])) / 2
        target = next((group for group in groups if (
            row_low <= max(float(item["zone_high"]) for item in group)
            and row_high >= min(float(item["zone_low"]) for item in group)
        ) or abs(midpoint - mean(
            (float(item["zone_low"]) + float(item["zone_high"])) / 2 for item in group
        )) <= tolerance), None)
        if target is None:
            groups.append([row])
        else:
            target.append(row)
    return groups


def _zone(group: list[dict], price: float, evidence: dict[str, list[dict]]) -> dict:
    lows, highs = [float(row["zone_low"]) for row in group], [float(row["zone_high"]) for row in group]
    timeframes = sorted({str(row.get("timeframe")) for row in group}, key=lambda tf: TF_RANK.get(tf, 0), reverse=True)
    owner = timeframes[0] if timeframes else "unknown"
    zone_id = "price-area:" + "+".join(sorted(str(row.get("level_id")) for row in group)[:4])
    matching = []
    for events in evidence.values():
        for event in events:
            if event.get("zone_low") is None or event.get("zone_high") is None:
                continue
            if float(event["zone_high"]) >= min(lows) and float(event["zone_low"]) <= max(highs):
                matching.append(event)
    matching.sort(key=lambda row: str(row.get("event_time_utc") or ""), reverse=True)
    latest = matching[0] if matching else {}
    tests = sum(1 for row in matching if row.get("event_type") in {"zone_tested", "zone_retested"})
    midpoint = (min(lows) + max(highs)) / 2
    return {
        "zone_id": zone_id, "zone_low": _number(min(lows)), "zone_high": _number(max(highs)),
        "distance": _number(abs(midpoint - price)), "contributing_timeframes": timeframes,
        "primary_owning_timeframe": owner,
        "core_overlap": [_number(max(lows)), _number(min(highs))] if max(lows) <= min(highs) else None,
        "investigation_band": [_number(min(lows)), _number(max(highs))],
        "invalidation_by_timeframe": {tf: "owning_timeframe_close_beyond_zone" for tf in timeframes},
        "structural_proof": latest.get("event_type") or "level_projection_only",
        "history": f"formed → tests:{tests} → latest:{latest.get('event_type', 'none')} → status:{latest.get('zone_status', 'unresolved')} → unresolved:owning-timeframe response",
        "evidence_ids": list(dict.fromkeys(str(row.get("evidence_id")) for row in matching if row.get("evidence_id")))[:3],
        "execution_authority": False,
    }


def _three_zones(symbol: dict, price: float) -> dict:
    evidence = symbol.get("structure_evidence") or {}
    zones = [_zone(group, price, evidence) for group in _zone_groups(symbol.get("market_levels") or [], price)]
    zones.sort(key=lambda row: (row["distance"], -TF_RANK.get(row["primary_owning_timeframe"], 0)))
    focus = zones[0] if zones else None
    support = next((row for row in zones if row["zone_high"] < price and row is not focus), None)
    resistance = next((row for row in zones if row["zone_low"] > price and row is not focus), None)
    return {"current_or_approaching_focus": focus, "nearest_proven_support": support,
            "nearest_proven_resistance": resistance, "selection_rule":
            "distance+highest_owner+freshness+structural_proof+session+volume+room"}


def _session_block(raw: dict, xau: dict, as_of: datetime) -> dict:
    summaries = (raw.get("session_summaries") or {}).get("XAUUSDr") or (raw.get("session_summaries") or {}).get("XAUUSD") or []
    current = next((row for row in summaries if row.get("status") == "current"), None)
    completed = [row for row in summaries if row.get("status") == "completed"]
    if current is None:
        session = _latest(xau, "M1").get("session") or {}
        current = {"name": session.get("name"), "phase": session.get("phase"),
                   "starts_at": session.get("starts_at"), "ends_at": session.get("ends_at"),
                   "status": "source_session"}
    if current.get("ends_at"):
        current["seconds_remaining"] = max(0, int((utc_datetime(current["ends_at"]) - as_of).total_seconds()))
    prior = completed[0] if completed else None
    same_name = [row for row in completed if row.get("name") == current.get("name")][:2]
    return {"current_session": current, "immediately_previous_session": prior,
            "previous_two_same_named_sessions": [
                {key: row.get(key) for key in ("name", "high", "low", "range", "tolerance")}
                for row in same_name
            ], "exact_price_equality_used": False}


def compile_market_memory(raw: dict, max_bytes: int = 14_000) -> dict:
    as_of = utc_datetime(raw.get("as_of_utc") or datetime.now(timezone.utc).isoformat())
    symbols = raw.get("symbols") or {}
    xau_key = next((key for key in symbols if key.upper().startswith("XAUUSD")), "XAUUSDr")
    xau, dxy = symbols.get(xau_key, {}), symbols.get("DXY", {})
    latest_m1 = _latest(xau, "M1")
    price = _number(latest_m1.get("close")) or 0.0
    temporal = [_temporal_row(xau, tf, as_of) for tf in TIMEFRAMES]
    dxy_rows = [_temporal_row(dxy, tf, as_of) for tf in TIMEFRAMES]
    zones = _three_zones(xau, price) if price else {
        "current_or_approaching_focus": None, "nearest_proven_support": None,
        "nearest_proven_resistance": None, "selection_rule": "unavailable_without_price"}
    packet = {
        "schema_version": 3, "packet_version": "neo4j-market-memory-shadow-v1",
        "status": "shadow_ready", "mode": "shadow_only", "execution_authority": False,
        "as_of_utc": raw.get("as_of_utc"), "known_as_of_utc": raw.get("known_as_of_utc"),
        "market_clock_and_sessions": _session_block(raw, xau, as_of),
        "xauusd_all_timeframe_temporal_structure": temporal,
        "active_zone_positions": zones,
        "structure_and_volume_participation": {
            "note": "tick volume is participation proxy, not true buy/sell volume",
            "by_timeframe": {tf: _volume(xau.get(tf) or []) for tf in TIMEFRAMES},
        },
        "dxy_cross_reference": {
            "lines": [
                {"scope": "D1/H4 driver", "states": {row["timeframe"]: [row["trend_state"], row["auction_state"], row["candle_seconds_remaining"]] for row in dxy_rows if row["timeframe"] in {"D1", "H4"}}},
                {"scope": "H1/M30/M15 path", "states": {row["timeframe"]: [row["trend_state"], row["auction_state"], row["candle_seconds_remaining"]] for row in dxy_rows if row["timeframe"] in {"H1", "M30", "M15"}}},
                {"scope": "M5/M1 immediate", "states": {row["timeframe"]: [row["trend_state"], row["auction_state"], row["candle_seconds_remaining"]] for row in dxy_rows if row["timeframe"] in {"M5", "M1"}}},
                {"scope": "participation", "states": {row["timeframe"]: row["volume_confirmation"] for row in dxy_rows}},
                {"scope": "relation_to_xau", "state": "Qwen_interprets_neutral_cross_reference"},
            ], "execution_authority": False,
        },
        "conflicts_missing_and_rag": {
            "missing_facts": [f"{row['timeframe']}:fresh_market_fact" for row in temporal if row["freshness"] != "fresh"],
            "optional_neo4j_rag_evidence": protocol_descriptor(),
        },
        "zone_relevant_semantic_memory": relevant_for_zone(
            raw.get("semantic_memories") or [], zones.get("current_or_approaching_focus"), 1
        ),
        "projection": raw.get("projection", {}),
    }
    encoded = json.dumps(packet, separators=(",", ":"), sort_keys=True).encode("utf-8")
    packet["packet_bytes"] = len(encoded)
    packet["packet_budget_bytes"] = max_bytes
    packet["within_packet_budget"] = len(encoded) <= max_bytes
    return packet
