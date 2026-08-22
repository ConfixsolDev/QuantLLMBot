"""Deterministic, no-lookahead market-structure events for graph shadowing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

RULE_VERSION = "market-structure-shadow-v3-deduped"
DETECTOR = "confirmed-fractal-zone"
STRUCTURE_TIMEFRAMES = ("M1", "M15", "M30", "H1", "H4", "D1")
SWING_WINGS = {"M1": 2, "M15": 3, "M30": 3, "H1": 3, "H4": 3, "D1": 3}


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return "structure:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class Zone:
    zone_id: str
    kind: str
    low: float
    high: float
    source_evidence_id: str
    source_time_utc: str
    structure_label: str
    broken: bool = False
    tested: bool = False
    accepted: bool = False
    retested: bool = False


def _event(symbol: str, timeframe: str, event_type: str, event_time: str,
           evidence_id: str, payload: dict, identity: object) -> dict:
    facts = {
        "mode": "shadow_only",
        "execution_authority": False,
        "status": "confirmed",
        "detector": DETECTOR,
        "detector_version": "1",
        "rule_version": RULE_VERSION,
        "confirmation_time_utc": event_time,
        "knowledge_time_utc": event_time,
        **payload,
    }
    zone = ""
    if facts.get("zone_low") is not None and facts.get("zone_high") is not None:
        zone = f" zone {facts['zone_low']:.3f}-{facts['zone_high']:.3f}"
    direction = f" {facts['direction']}" if facts.get("direction") in {"bullish", "bearish"} else ""
    descriptions = {
        "swing_high_confirmed": "swing high confirmed after the right wing closed",
        "swing_low_confirmed": "swing low confirmed after the right wing closed",
        "zone_created": "body-to-wick structure zone created from the confirmed swing",
        "zone_tested": "confirmed structure zone received its first later test",
        "liquidity_sweep": "wick crossed the zone but the owning-timeframe close returned",
        "bos_confirmed": "BOS confirmed by an owning-timeframe close beyond the zone",
        "choch_confirmed": "CHoCH confirmed against the prior structure by an owning-timeframe close",
        "mss_confirmed": "MSS confirmed because CHoCH also met the displacement rule",
        "zone_broken": "structure zone broken by an owning-timeframe close",
        "zone_accepted": "break accepted after the next owning-timeframe candle held beyond the zone",
        "zone_retested": "accepted zone retested and held on its owning timeframe",
    }
    facts["explanation"] = f"{timeframe}{direction} {descriptions[event_type]}{zone}."
    facts["evidence_ids"] = list(dict.fromkeys(
        str(value) for value in facts.get("evidence_ids", []) if value
    ))[:24]
    return {
        "event_id": _stable_id(symbol, timeframe, event_type, identity, RULE_VERSION),
        "symbol": symbol,
        "timeframe": timeframe,
        "event_type": event_type,
        "event_time_utc": event_time,
        "evidence_id": evidence_id,
        "payload": facts,
    }


def _swing_kind(bars: list[dict], index: int, wing: int) -> str | None:
    center = bars[index]
    neighbors = bars[index - wing:index] + bars[index + 1:index + wing + 1]
    if all(center["high"] > row["high"] for row in neighbors):
        return "swing_high"
    if all(center["low"] < row["low"] for row in neighbors):
        return "swing_low"
    return None


def _deduplicated_bars(candles: Iterable[dict]) -> list[dict]:
    """Select one authoritative candle per close without altering the ledger."""
    selected: dict[str, tuple[int, dict]] = {}
    for source in candles:
        row = dict(source)
        convention = str(row.get("time_convention") or "").lower()
        evidence_id = str(row.get("evidence_id") or "").lower()
        priority = 3 if convention == "new_york_1700_dst" else (
            2 if convention == "broker" or ":broker:" in evidence_id else 1
        )
        key = str(row["event_time_utc"])
        if key not in selected or priority >= selected[key][0]:
            selected[key] = (priority, row)
    return sorted((value[1] for value in selected.values()),
                  key=lambda row: row["event_time_utc"])


def label_structure(symbol: str, timeframe: str, candles: Iterable[dict], *,
                    wing: int = 3, equal_tolerance: float = 1.0,
                    displacement_min_body: float = 1.5) -> list[dict]:
    """Return stable shadow events from completed candles ordered oldest first.

    A swing at index i is emitted only at the close of i+wing. All break,
    sweep, acceptance, and retest decisions use the owning timeframe close.
    """
    bars = _deduplicated_bars(candles)
    if len(bars) < wing * 2 + 1:
        return []
    events: list[dict] = []
    zones: list[Zone] = []
    prior_price: dict[str, float] = {}
    latest_label: dict[str, str] = {}
    trend = "unknown"
    pending_acceptance: dict[str, tuple[str, str]] = {}

    def emit(event_type: str, bar: dict, evidence_ids: list[str], payload: dict,
             identity: object) -> None:
        events.append(_event(
            symbol, timeframe, event_type, bar["event_time_utc"],
            bar["evidence_id"], {**payload, "evidence_ids": evidence_ids}, identity,
        ))

    for current_index, bar in enumerate(bars):
        if current_index >= wing * 2:
            swing_index = current_index - wing
            kind = _swing_kind(bars, swing_index, wing)
            if kind:
                source = bars[swing_index]
                price = source["high"] if kind == "swing_high" else source["low"]
                prior = prior_price.get(kind)
                if prior is None:
                    label = "SH" if kind == "swing_high" else "SL"
                elif abs(price - prior) <= equal_tolerance:
                    label = "EH" if kind == "swing_high" else "EL"
                elif kind == "swing_high":
                    label = "HH" if price > prior else "LH"
                else:
                    label = "HL" if price > prior else "LL"
                prior_price[kind] = price
                latest_label[kind] = label
                if latest_label.get("swing_high") == "HH" and latest_label.get("swing_low") == "HL":
                    trend = "bullish"
                elif latest_label.get("swing_high") == "LH" and latest_label.get("swing_low") == "LL":
                    trend = "bearish"
                body_edge = max(source["open"], source["close"]) if kind == "swing_high" else min(source["open"], source["close"])
                low, high = sorted((float(price), float(body_edge)))
                zone_id = "zone:" + _stable_id(
                    symbol, timeframe, kind, source["evidence_id"], RULE_VERSION
                ).split(":", 1)[1]
                zone = Zone(zone_id, kind, low, high, source["evidence_id"],
                            source["event_time_utc"], label)
                zones.append(zone)
                evidence = [source["evidence_id"], bar["evidence_id"]]
                common = {
                    "zone_id": zone_id, "zone_kind": kind,
                    "zone_low": low, "zone_high": high,
                    "structure_label": label, "direction": trend,
                    "source_time_utc": source["event_time_utc"],
                    "source_evidence_id": source["evidence_id"],
                }
                emit(f"{kind}_confirmed", bar, evidence, common, zone_id)
                emit("zone_created", bar, evidence,
                     {**common, "zone_status": "candidate"}, zone_id)

        # Evaluate only zones known before this candle; a just-confirmed old
        # swing may legitimately be tested by the confirmation candle.
        for zone in zones:
            if zone.broken:
                if zone.zone_id in pending_acceptance:
                    direction, break_evidence = pending_acceptance.pop(zone.zone_id)
                    held = bar["close"] > zone.high if direction == "bullish" else bar["close"] < zone.low
                    if held:
                        zone.accepted = True
                        emit("zone_accepted", bar, [zone.source_evidence_id, break_evidence, bar["evidence_id"]], {
                            "zone_id": zone.zone_id, "zone_kind": zone.kind,
                            "zone_low": zone.low, "zone_high": zone.high,
                            "zone_status": "accepted", "direction": direction,
                        }, (zone.zone_id, bar["evidence_id"]))
                elif zone.accepted and not zone.retested:
                    entered = bar["low"] <= zone.high and bar["high"] >= zone.low
                    held = bar["close"] > zone.high if zone.kind == "swing_high" else bar["close"] < zone.low
                    if entered and held:
                        zone.retested = True
                        emit("zone_retested", bar, [zone.source_evidence_id, bar["evidence_id"]], {
                            "zone_id": zone.zone_id, "zone_kind": zone.kind,
                            "zone_low": zone.low, "zone_high": zone.high,
                            "zone_status": "accepted", "direction": "bullish" if zone.kind == "swing_high" else "bearish",
                        }, (zone.zone_id, bar["evidence_id"]))
                continue

            entered = bar["high"] >= zone.low and bar["low"] <= zone.high
            if entered and not zone.tested and bar["event_time_utc"] > zone.source_time_utc:
                zone.tested = True
                emit("zone_tested", bar, [zone.source_evidence_id, bar["evidence_id"]], {
                    "zone_id": zone.zone_id, "zone_kind": zone.kind,
                    "zone_low": zone.low, "zone_high": zone.high,
                    "zone_status": "tested", "structure_label": zone.structure_label,
                }, (zone.zone_id, bar["evidence_id"]))

            upward_break = zone.kind == "swing_high" and bar["close"] > zone.high
            downward_break = zone.kind == "swing_low" and bar["close"] < zone.low
            if upward_break or downward_break:
                direction = "bullish" if upward_break else "bearish"
                transition = trend in {"bullish", "bearish"} and direction != trend
                event_type = "choch_confirmed" if transition else "bos_confirmed"
                evidence = [zone.source_evidence_id, bar["evidence_id"]]
                common = {
                    "zone_id": zone.zone_id, "zone_kind": zone.kind,
                    "zone_low": zone.low, "zone_high": zone.high,
                    "zone_status": "broken", "direction": direction,
                    "prior_structure": trend,
                }
                emit(event_type, bar, evidence, common, (zone.zone_id, bar["evidence_id"]))
                if transition and abs(bar["close"] - bar["open"]) >= displacement_min_body:
                    emit("mss_confirmed", bar, evidence,
                         {**common, "displacement_body": abs(bar["close"] - bar["open"])},
                         (zone.zone_id, bar["evidence_id"]))
                emit("zone_broken", bar, evidence, common, (zone.zone_id, bar["evidence_id"]))
                zone.broken = True
                pending_acceptance[zone.zone_id] = (direction, bar["evidence_id"])
                trend = direction
            elif zone.kind == "swing_high" and bar["high"] > zone.high and bar["close"] <= zone.high:
                emit("liquidity_sweep", bar, [zone.source_evidence_id, bar["evidence_id"]], {
                    "zone_id": zone.zone_id, "zone_kind": zone.kind,
                    "zone_low": zone.low, "zone_high": zone.high,
                    "zone_status": "rejected", "direction": "bearish",
                }, (zone.zone_id, bar["evidence_id"]))
            elif zone.kind == "swing_low" and bar["low"] < zone.low and bar["close"] >= zone.low:
                emit("liquidity_sweep", bar, [zone.source_evidence_id, bar["evidence_id"]], {
                    "zone_id": zone.zone_id, "zone_kind": zone.kind,
                    "zone_low": zone.low, "zone_high": zone.high,
                    "zone_status": "rejected", "direction": "bullish",
                }, (zone.zone_id, bar["evidence_id"]))
        # A broken zone that failed its one-candle acceptance test can never
        # emit another event.  Likewise, a completed accepted retest is final.
        # Removing terminal zones preserves output semantics while preventing
        # historical M1 backfills from repeatedly scanning thousands of dead
        # zones on every later candle.
        zones = [zone for zone in zones if (
            not zone.broken
            or zone.zone_id in pending_acceptance
            or (zone.accepted and not zone.retested)
        )]
    return sorted(events, key=lambda row: (row["event_time_utc"], row["event_id"]))
