"""Leakage-safe hourly market-structure quality audit with post-hoc supervision.

Decision-time fields use only candles and confirmed structure whose knowledge
time is at or before the audited H1 close.  Forward candles are confined to the
``supervision`` payload and can never authorize execution or enter live context.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Iterable

from instrument_config import instrument_for
from market_intelligence.structure_labeling import RULE_VERSION, SWING_WINGS, label_structure

AUDIT_RULE_VERSION = "hourly-market-quality-v6-aligned-boundary"
AUDIT_EVENT_TYPE = "market_structure_hourly_supervision"
AUDIT_TIMEFRAMES = ("M1", "M15", "M30", "H1", "H4", "D1")
LARGE_TIMEFRAMES = ("D1", "H4", "H1")
SMALL_TIMEFRAMES = ("M30", "M15", "M1")


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(symbol: str, event_time: str, outcome_key: str = "complete") -> str:
    raw = f"{symbol}|H1|{event_time}|{outcome_key}|{AUDIT_RULE_VERSION}"
    return "supervision:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _direction(open_price: float, close_price: float, tolerance: float = 0.0) -> str:
    delta = close_price - open_price
    if delta > tolerance:
        return "bullish"
    if delta < -tolerance:
        return "bearish"
    return "ranging"


def _consensus(values: Iterable[str]) -> str:
    votes = Counter(value for value in values if value in {"bullish", "bearish"})
    if not votes:
        return "unknown"
    if votes["bullish"] == votes["bearish"]:
        return "mixed"
    return "bullish" if votes["bullish"] > votes["bearish"] else "bearish"


def _movement_relation(big: str, small: str) -> str:
    if "unknown" in {big, small}:
        return "insufficient_data"
    if "mixed" in {big, small}:
        return "mixed"
    if big == small:
        return "aligned_continuation"
    return "counter_parent_pullback"


@dataclass
class CandleSeries:
    rows: list[dict]

    def __post_init__(self) -> None:
        selected: dict[str, tuple[int, dict]] = {}
        for row in self.rows:
            convention = str(row.get("time_convention") or "").lower()
            evidence_id = str(row.get("evidence_id") or "").lower()
            priority = 3 if convention == "new_york_1700_dst" else (
                2 if convention == "broker" or ":broker:" in evidence_id else 1
            )
            key = str(row["event_time_utc"])
            if key not in selected or priority >= selected[key][0]:
                selected[key] = (priority, row)
        self.rows = sorted((value[1] for value in selected.values()),
                           key=lambda row: row["event_time_utc"])
        self.times = [_utc(row["event_time_utc"]) for row in self.rows]

    def index_at(self, moment: datetime) -> int:
        return bisect_right(self.times, moment) - 1

    def at(self, moment: datetime) -> dict | None:
        index = self.index_at(moment)
        return self.rows[index] if index >= 0 else None

    def prior(self, moment: datetime, count: int) -> list[dict]:
        index = self.index_at(moment)
        return self.rows[max(0, index - count + 1):index + 1] if index >= 0 else []


def load_candles(db_path: Path, symbol: str, timeframe: str, start: datetime,
                 end: datetime, warmup: int = 200) -> list[dict]:
    """Load completed candles plus a bounded pre-window structure warmup."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    before = db.execute(
        "SELECT event_time_utc FROM intelligence_events WHERE symbol=? AND timeframe=? "
        "AND event_type='candle_closed' AND event_time_utc<? "
        "ORDER BY event_time_utc DESC LIMIT 1 OFFSET ?",
        (symbol, timeframe, _iso(start), max(0, warmup - 1)),
    ).fetchone()
    boundary = before["event_time_utc"] if before else _iso(start)
    rows = db.execute(
        "SELECT event_time_utc,evidence_id,payload_json FROM intelligence_events "
        "WHERE symbol=? AND timeframe=? AND event_type='candle_closed' "
        "AND event_time_utc>=? AND event_time_utc<=? ORDER BY event_time_utc",
        (symbol, timeframe, boundary, _iso(end)),
    ).fetchall()
    db.close()
    result = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        if not all(payload.get(key) is not None for key in ("open", "high", "low", "close")):
            continue
        result.append({
            "event_time_utc": row["event_time_utc"],
            "evidence_id": row["evidence_id"],
            **payload,
        })
    return result


def persisted_structure_ids(db_path: Path, symbol: str, start: datetime,
                            end: datetime) -> set[str]:
    db = sqlite3.connect(db_path)
    rows = db.execute(
        "SELECT event_id FROM intelligence_events WHERE symbol=? "
        "AND event_time_utc>=? AND event_time_utc<=? "
        "AND json_extract(payload_json,'$.rule_version')=?",
        (symbol, _iso(start), _iso(end), RULE_VERSION),
    ).fetchall()
    db.close()
    return {str(row[0]) for row in rows}


def _label_events(symbol: str, series: dict[str, CandleSeries]) -> list[dict]:
    profile = instrument_for(symbol)
    result = []
    for timeframe, candles in series.items():
        result.extend(label_structure(
            symbol,
            timeframe,
            candles.rows,
            wing=SWING_WINGS[timeframe],
            equal_tolerance=profile.equal_level_tolerance,
            displacement_min_body=profile.displacement_min_body,
        ))
    return sorted(result, key=lambda row: (row["event_time_utc"], row["event_id"]))


def _volume_ratio(rows: list[dict]) -> float | None:
    values = [float(row.get("tick_volume") or 0) for row in rows if row.get("tick_volume") is not None]
    if len(values) < 5:
        return None
    baseline = median(values[:-1]) if len(values) > 1 else 0.0
    return round(values[-1] / baseline, 3) if baseline > 0 else None


def _atr(rows: list[dict], count: int = 20) -> float | None:
    window = rows[-count:]
    if len(window) < 5:
        return None
    return sum(float(row["high"]) - float(row["low"]) for row in window) / len(window)


def _latest_structure(states: dict[str, dict], timeframe: str,
                      fallback: dict | None) -> str:
    direction = (states.get(timeframe) or {}).get("direction")
    if direction in {"bullish", "bearish"}:
        return direction
    if fallback:
        supplied = fallback.get("direction")
        if supplied in {"bullish", "bearish"}:
            return supplied
        return _direction(float(fallback["open"]), float(fallback["close"]))
    return "unknown"


def _apply_structure_event(states: dict[str, dict], zones: dict[str, dict], event: dict) -> None:
    payload = event["payload"]
    timeframe = event["timeframe"]
    state = states.setdefault(timeframe, {})
    if payload.get("direction") in {"bullish", "bearish"}:
        state["direction"] = payload["direction"]
    state["last_event_type"] = event["event_type"]
    state["last_event_time_utc"] = event["event_time_utc"]
    zone_id = payload.get("zone_id")
    if not zone_id:
        return
    zone = zones.setdefault(zone_id, {
        "zone_id": zone_id,
        "timeframe": timeframe,
        "zone_low": payload.get("zone_low"),
        "zone_high": payload.get("zone_high"),
        "zone_kind": payload.get("zone_kind"),
        "status": "candidate",
    })
    zone["status"] = payload.get("zone_status") or zone["status"]
    zone["last_event_type"] = event["event_type"]
    zone["last_event_time_utc"] = event["event_time_utc"]
    if event["event_type"] in {"liquidity_sweep", "zone_accepted", "zone_retested"}:
        zone["proven"] = True


def _nearest_zones(zones: dict[str, dict], price: float,
                   moment: datetime) -> tuple[list[dict], int, int]:
    freshness_days = {"M1": 0.25, "M15": 3, "M30": 7, "H1": 14, "H4": 60, "D1": 365}
    active = []
    for zone in zones.values():
        if zone.get("status") == "broken" or not zone.get("last_event_time_utc"):
            continue
        age = moment - _utc(zone["last_event_time_utc"])
        if age <= timedelta(days=freshness_days.get(str(zone.get("timeframe")), 14)):
            active.append(zone)
    for zone in active:
        low, high = float(zone["zone_low"]), float(zone["zone_high"])
        zone["distance"] = 0.0 if low <= price <= high else min(abs(price - low), abs(price - high))
    overlapping = sum(
        1 for zone in active
        if float(zone["zone_low"]) <= price <= float(zone["zone_high"])
    )
    return (sorted(active, key=lambda row: (row["distance"], row["timeframe"]))[:6],
            len(active), overlapping)


def _cross_status(xau_direction: str, dxy_direction: str) -> str:
    if "unknown" in {xau_direction, dxy_direction}:
        return "insufficient_data"
    if "ranging" in {xau_direction, dxy_direction}:
        return "neutral"
    return "inverse_aligned" if xau_direction != dxy_direction else "positive_correlation_conflict"


def build_hourly_audit(db_path: Path, *, symbol: str = "XAUUSDr",
                       cross_symbol: str = "DXY", days: int = 60,
                       forward_hours: int = 4) -> tuple[list[dict], dict]:
    """Build one post-hoc supervision event per completed XAU H1 market hour."""
    with sqlite3.connect(db_path) as db:
        latest_value = db.execute(
            "SELECT MAX(event_time_utc) FROM intelligence_events WHERE symbol=? "
            "AND timeframe='H1' AND event_type='candle_closed'", (symbol,),
        ).fetchone()[0]
    if not latest_value:
        raise RuntimeError(f"no completed H1 candles for {symbol}")
    end = _utc(latest_value)
    start = end - timedelta(days=max(1, days))
    load_end = end
    series: dict[str, dict[str, CandleSeries]] = {symbol: {}, cross_symbol: {}}
    for current_symbol in (symbol, cross_symbol):
        for timeframe in AUDIT_TIMEFRAMES:
            series[current_symbol][timeframe] = CandleSeries(load_candles(
                db_path, current_symbol, timeframe, start, load_end,
            ))

    generated = {current_symbol: _label_events(current_symbol, series[current_symbol])
                 for current_symbol in (symbol, cross_symbol)}
    persisted = {current_symbol: persisted_structure_ids(db_path, current_symbol, start, end)
                 for current_symbol in (symbol, cross_symbol)}
    pointers = {symbol: 0, cross_symbol: 0}
    states = {symbol: {}, cross_symbol: {}}
    zones = {symbol: {}, cross_symbol: {}}
    h1 = series[symbol]["H1"]
    audit_hours = [row for row in h1.rows if start <= _utc(row["event_time_utc"]) <= end]
    events: list[dict] = []
    defect_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for hour_index, candle in enumerate(audit_hours):
        moment = _utc(candle["event_time_utc"])
        newly_known: dict[str, list[dict]] = {symbol: [], cross_symbol: []}
        for current_symbol in (symbol, cross_symbol):
            rows = generated[current_symbol]
            while pointers[current_symbol] < len(rows) and _utc(rows[pointers[current_symbol]]["event_time_utc"]) <= moment:
                event = rows[pointers[current_symbol]]
                _apply_structure_event(states[current_symbol], zones[current_symbol], event)
                if _utc(event["event_time_utc"]) == moment:
                    newly_known[current_symbol].append(event)
                pointers[current_symbol] += 1

        current = {tf: series[symbol][tf].at(moment) for tf in AUDIT_TIMEFRAMES}
        cross = {tf: series[cross_symbol][tf].at(moment) for tf in AUDIT_TIMEFRAMES}
        coverage = {f"xau_{tf.lower()}": current[tf] is not None for tf in AUDIT_TIMEFRAMES}
        coverage.update({f"dxy_{tf.lower()}": cross[tf] is not None for tf in AUDIT_TIMEFRAMES})
        directions = {tf: _latest_structure(states[symbol], tf, current[tf]) for tf in AUDIT_TIMEFRAMES}
        cross_directions = {tf: _latest_structure(states[cross_symbol], tf, cross[tf]) for tf in AUDIT_TIMEFRAMES}
        big_direction = _consensus(directions[tf] for tf in LARGE_TIMEFRAMES)
        small_direction = _consensus(directions[tf] for tf in SMALL_TIMEFRAMES)
        movement_status = _movement_relation(big_direction, small_direction)
        cross_status = _cross_status(directions["H1"], cross_directions["H1"])
        nearest, total_active_zones, overlapping_zones = _nearest_zones(
            zones[symbol], float(candle["close"]), moment
        )
        touched = [zone for zone in nearest if float(candle["low"]) <= float(zone["zone_high"])
                   and float(candle["high"]) >= float(zone["zone_low"])]
        xau_h1_window = h1.prior(moment, 20)
        dxy_h1_window = series[cross_symbol]["H1"].prior(moment, 20)
        xau_volume_ratio = _volume_ratio(xau_h1_window)
        dxy_volume_ratio = _volume_ratio(dxy_h1_window)
        atr = _atr(xau_h1_window)
        volume_status = (
            "elevated_at_level" if touched and (xau_volume_ratio or 0) >= 1.5
            else "level_interaction_normal" if touched
            else "elevated_away_from_level" if (xau_volume_ratio or 0) >= 1.5
            else "normal"
        )

        future = audit_hours[hour_index + 1:hour_index + 1 + max(1, forward_hours)]
        next_one = future[0] if future else None
        forward_complete = len(future) >= max(1, forward_hours)
        entry = float(candle["close"])
        future_high = max((float(row["high"]) for row in future), default=entry)
        future_low = min((float(row["low"]) for row in future), default=entry)
        final_close = float(future[-1]["close"]) if future else entry
        next_1h_return = float(next_one["close"]) - entry if next_one else None
        next_4h_return = final_close - entry if forward_complete else None
        forward_direction = _direction(entry, final_close) if forward_complete else "unknown"
        large_move = bool(forward_complete and atr and abs(final_close - entry) >= 1.5 * atr)

        defects: list[str] = []
        missing_frames = [name for name, present in coverage.items() if not present]
        if missing_frames:
            defects.append("timeframe_data_incomplete")
        unpersisted = [event for current_symbol in (symbol, cross_symbol)
                       for event in newly_known[current_symbol]
                       if event["event_id"] not in persisted[current_symbol]]
        if unpersisted:
            defects.append("deterministic_structure_not_persisted")
        if total_active_zones >= 500 or overlapping_zones >= 12:
            defects.append("zone_map_saturated")
        if large_move and not nearest:
            defects.append("missing_level_context_before_large_move")
        if large_move and big_direction in {"unknown", "mixed"}:
            defects.append("large_timeframe_structure_underclassified")
        if large_move and cross_status == "inverse_aligned" and not persisted[cross_symbol]:
            defects.append("cross_pair_structure_not_persisted")
        if large_move and volume_status == "elevated_at_level" and not any(
            event["event_type"] in {"zone_tested", "liquidity_sweep", "zone_broken"}
            for event in newly_known[symbol]
        ):
            defects.append("volume_level_response_unlabeled")
        latest_event = (states[symbol].get("H1") or {}).get("last_event_type")
        if large_move and latest_event in {"bos_confirmed", "choch_confirmed", "mss_confirmed"}:
            structure_direction = directions["H1"]
            if forward_direction in {"bullish", "bearish"} and structure_direction != forward_direction:
                defects.append("structure_break_failed_forward_validation")
        if not forward_complete:
            defects.append("forward_window_incomplete")

        unique_defects = list(dict.fromkeys(defects))
        hard_defects = [value for value in unique_defects if value not in {
            "forward_window_incomplete", "timeframe_data_incomplete",
        }]
        if not forward_complete or missing_frames:
            quality_status = "insufficient_data"
        elif hard_defects:
            quality_status = "defect"
        elif movement_status in {"mixed", "counter_parent_pullback"} or cross_status.endswith("conflict"):
            quality_status = "partial"
        else:
            quality_status = "good"
        score = max(0, 100 - 18 * len(hard_defects) - 8 * len(missing_frames)
                    - (10 if quality_status == "partial" else 0))
        level_status = "proven" if any(zone.get("proven") for zone in nearest) else (
            "candidate" if nearest else "missing"
        )
        zone_status = (
            "saturated" if total_active_zones >= 500 or overlapping_zones >= 12
            else "proven_tested_now" if any(zone.get("proven") for zone in touched)
            else "candidate_tested_now" if touched
            else "mapped_proven" if level_status == "proven"
            else "mapped_candidate" if nearest
            else "missing"
        )
        structure_status = f"big_{big_direction}__small_{small_direction}"
        supervised_analysis = (
            f"{quality_status}: {len(unique_defects)} defect(s); levels={level_status}; "
            f"zones={zone_status}; structure={structure_status}; cross={cross_status}; "
            f"movement={movement_status}; volume={volume_status}."
        )
        evidence_ids = [candle.get("evidence_id")]
        evidence_ids.extend(row.get("evidence_id") for row in (current["M1"], current["M15"], current["M30"], current["H4"], current["D1"], cross["H1"]) if row)
        payload = {
            "mode": "posthoc_supervised",
            "supervision_mode": "forward_validation",
            "status": "proposed",
            "execution_authority": False,
            "uses_forward_visibility": True,
            "eligible_for_live_context": False,
            "eligible_for_training": False,
            "audit_rule_version": AUDIT_RULE_VERSION,
            "decision_as_of_utc": _iso(moment),
            "knowledge_time_utc": _iso(end),
            "forward_end_utc": _iso(_utc(future[-1]["event_time_utc"])) if future else None,
            "quality_status": quality_status,
            "quality_score": score,
            "combined_status": quality_status,
            "defect_count": len(unique_defects),
            "defects": unique_defects,
            "supervised_analysis": supervised_analysis,
            "level_status": level_status,
            "zone_status_summary": zone_status,
            "market_structure_status": structure_status,
            "cross_pair_status": cross_status,
            "timeframe_movement_status": movement_status,
            "volume_profile_status": volume_status,
            "big_tf_direction": big_direction,
            "small_tf_direction": small_direction,
            "xau_h1_direction": directions["H1"],
            "dxy_h1_direction": cross_directions["H1"],
            "xau_h1_volume_ratio": xau_volume_ratio,
            "dxy_h1_volume_ratio": dxy_volume_ratio,
            "active_zone_count": len(nearest),
            "total_active_zone_count": total_active_zones,
            "overlapping_zone_count": overlapping_zones,
            "next_1h_return": round(next_1h_return, 6) if next_1h_return is not None else None,
            "next_4h_return": round(next_4h_return, 6) if next_4h_return is not None else None,
            "next_4h_mfe": round(future_high - entry, 6) if forward_complete else None,
            "next_4h_mae": round(entry - future_low, 6) if forward_complete else None,
            "evidence_ids": list(dict.fromkeys(str(value) for value in evidence_ids if value))[:24],
            "decision_facts": {
                "coverage": coverage,
                "directions": directions,
                "cross_directions": cross_directions,
                "nearest_zones": [{key: zone.get(key) for key in (
                    "zone_id", "timeframe", "zone_low", "zone_high", "status", "proven", "distance"
                )} for zone in nearest],
                "new_structure_events": [{"symbol": row["symbol"], "timeframe": row["timeframe"],
                                           "event_type": row["event_type"], "event_id": row["event_id"]}
                                          for row in newly_known[symbol] + newly_known[cross_symbol]],
            },
            "supervision": {
                "forward_window_complete": forward_complete,
                "forward_direction": forward_direction,
                "large_move_vs_h1_atr": large_move,
                "unpersisted_structure_event_ids": [row["event_id"] for row in unpersisted],
            },
        }
        event_time = _iso(moment)
        events.append({
            # Completed outcomes are stable forever. An incomplete tail is
            # scoped to its current audit boundary, allowing a later immutable
            # completed supervision event instead of mutating history.
            "event_id": _stable_id(
                symbol, event_time,
                _iso(_utc(future[-1]["event_time_utc"])) if forward_complete else f"incomplete:{_iso(end)}",
            ),
            "symbol": symbol,
            "timeframe": "H1",
            "event_type": AUDIT_EVENT_TYPE,
            "event_time_utc": event_time,
            "evidence_id": candle.get("evidence_id"),
            "payload": payload,
        })
        status_counts[quality_status] += 1
        defect_counts.update(unique_defects)

    expected_calendar_hours = int((end - start).total_seconds() // 3600) + 1
    summary = {
        "audit_rule_version": AUDIT_RULE_VERSION,
        "symbol": symbol,
        "cross_symbol": cross_symbol,
        "start_utc": _iso(start),
        "end_utc": _iso(end),
        "market_hours_audited": len(events),
        "calendar_hours_in_window": expected_calendar_hours,
        "calendar_hours_without_xau_h1_close": max(0, expected_calendar_hours - len(events)),
        "status_counts": dict(sorted(status_counts.items())),
        "defect_counts": dict(defect_counts.most_common()),
        "source_candle_counts": {
            current_symbol: {tf: len(series[current_symbol][tf].rows) for tf in AUDIT_TIMEFRAMES}
            for current_symbol in (symbol, cross_symbol)
        },
        "persisted_structure_counts": {key: len(value) for key, value in persisted.items()},
        "generated_structure_counts": {key: len(value) for key, value in generated.items()},
        "safety": {
            "uses_forward_visibility": True,
            "execution_authority": False,
            "eligible_for_live_context": False,
            "eligible_for_training": False,
        },
    }
    return events, summary
