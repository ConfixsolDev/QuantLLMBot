"""Live mapped zones from completed swings only.

A first-test high/low becomes a mapped zone after the swing is confirmed on
closed candles. A later return to that equivalent zone is the only place a
double-top / double-bottom entry can exist. Forming candles never mint a zone.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

LOOKBACK = {
    "M1": 180,
    "M5": 96,
    "M15": 96,
    "M30": 64,
    "H1": 48,
    "H4": 40,
}
WING = {
    "M1": 2,
    "M5": 2,
    "M15": 2,
    "M30": 2,
    "H1": 1,
    "H4": 1,
}
# XAUUSD investigation bands. H4 is the 4–5 unit doctrine band; local maps
# are tighter so a new Asia low is not merged into yesterday's shelf.
ZONE_WIDTH = {
    "M1": 1.2,
    "M5": 2.0,
    "M15": 3.0,
    "M30": 3.5,
    "H1": 4.0,
    "H4": 5.0,
}
MAX_ZONES_PER_TF = 6
NEARBY_LIMIT = 5
PIN_BAND = 40.0
LIVE_METHODS = frozenset({"live_closed_swing", "operator_mapped"})


def _mid(zone_low: float, zone_high: float) -> float:
    return (float(zone_low) + float(zone_high)) / 2.0


def _iso(value) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def fractal_swings(rows: list[dict], wing: int, kind: str) -> list[dict]:
    """Confirmed swing highs/lows. The last `wing` closed bars cannot confirm."""
    if wing < 1 or len(rows) < wing * 2 + 1:
        return []
    swings = []
    last_index = len(rows) - wing
    for index in range(wing, last_index):
        row = rows[index]
        if kind == "high":
            price = float(row["high"])
            window = [float(rows[j]["high"]) for j in range(index - wing, index + wing + 1)]
            if price < max(window) or price <= float(rows[index - 1]["high"]) or price <= float(
                rows[index + 1]["high"]
            ):
                continue
        else:
            price = float(row["low"])
            window = [float(rows[j]["low"]) for j in range(index - wing, index + wing + 1)]
            if price > min(window) or price >= float(rows[index - 1]["low"]) or price >= float(
                rows[index + 1]["low"]
            ):
                continue
        swings.append(
            {
                "kind": kind,
                "price": price,
                "index": index,
                "evidence_id": row.get("evidence_id"),
                "close_time_utc": row.get("close_time_utc"),
                "open_time_utc": row.get("open_time_utc"),
            }
        )
    return swings


def classify_swing_sequence(swings: list[dict], lookback: int = 6) -> str:
    """Classify recent swing pattern as hh_hl / lh_ll / mixed / insufficient.

    Accepts fractal_swings() rows (`kind`) or generic `{type, price}` dicts.
    """
    ordered = sorted(
        swings,
        key=lambda item: (
            item.get("index", 0),
            str(item.get("close_time_utc") or item.get("open_time_utc") or ""),
        ),
    )
    recent = ordered[-lookback:] if len(ordered) >= lookback else ordered
    if len(recent) < 4:
        return "insufficient"

    def _kind(item: dict) -> str:
        return str(item.get("kind") or item.get("type") or "")

    highs = [item for item in recent if _kind(item) == "high"]
    lows = [item for item in recent if _kind(item) == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"
    hh = highs[-1]["price"] > highs[-2]["price"]
    hl = lows[-1]["price"] > lows[-2]["price"]
    if hh and hl:
        return "hh_hl"
    if not hh and not hl:
        return "lh_ll"
    return "mixed"


def cluster_swings(swings: list[dict], width: float) -> list[dict]:
    if not swings:
        return []
    ordered = sorted(swings, key=lambda item: item["price"])
    clusters: list[list[dict]] = [[ordered[0]]]
    for swing in ordered[1:]:
        mid = _mid(clusters[-1][0]["price"], clusters[-1][-1]["price"])
        if abs(swing["price"] - mid) <= width:
            clusters[-1].append(swing)
        else:
            clusters.append([swing])
    zones = []
    for members in clusters:
        prices = [item["price"] for item in members]
        first = min(members, key=lambda item: str(item.get("open_time_utc") or ""))
        zones.append(
            {
                "kind": members[0]["kind"],
                "zone_low": min(prices),
                "zone_high": max(prices),
                "members": sorted(members, key=lambda item: str(item.get("open_time_utc") or "")),
                "source_candle_ids": [
                    item["evidence_id"] for item in members if item.get("evidence_id")
                ],
                "valid_from_utc": first.get("close_time_utc"),
            }
        )
    return zones


def count_visits(zone: dict, rows: list[dict]) -> tuple[int, bool]:
    """Distinct approaches. A second test requires a leave between visits."""
    tests = 0
    in_zone = False
    left_after_first = False
    lo = float(zone["zone_low"])
    hi = float(zone["zone_high"])
    kind = zone["kind"]
    for row in rows:
        high = float(row["high"])
        low = float(row["low"])
        touching = low <= hi and high >= lo
        if touching:
            if not in_zone:
                tests += 1
                in_zone = True
        else:
            in_zone = False
            if tests >= 1:
                if kind == "high" and high < lo:
                    left_after_first = True
                elif kind == "low" and low > hi:
                    left_after_first = True
    return tests, left_after_first


def m1_failure_at_zone(zone: dict, closed_m1: dict | None) -> bool:
    """Completed M1 probes the equivalent zone and fails to close beyond it."""
    if not closed_m1:
        return False
    high = float(closed_m1["high"])
    low = float(closed_m1["low"])
    close = float(closed_m1["close"])
    lo = float(zone["zone_low"])
    hi = float(zone["zone_high"])
    if zone["kind"] == "high":
        probed = high >= lo
        failed = close <= hi
        return probed and failed
    probed = low <= hi
    failed = close >= lo
    return probed and failed


def hunt_zone_from_band(side: str, zone_low: float, zone_high: float) -> dict:
    """Buy hunts support (low); sell hunts resistance (high)."""
    return {
        "kind": "low" if str(side).lower() == "buy" else "high",
        "zone_low": float(zone_low),
        "zone_high": float(zone_high),
    }


def m1_failure_for_entry(
    side: str,
    zone_low: float,
    zone_high: float,
    closed_m1: dict | None,
) -> bool:
    """True when a completed M1 probed the hunt band and failed to close through."""
    return m1_failure_at_zone(
        hunt_zone_from_band(side, zone_low, zone_high), closed_m1
    )


def _level_id(timeframe: str, zone: dict) -> str:
    kind = "H" if zone["kind"] == "high" else "L"
    stamp = ""
    first = zone["members"][0] if zone.get("members") else {}
    open_time = str(first.get("open_time_utc") or "")
    if "T" in open_time:
        hhmm = open_time.split("T", 1)[1][:5].replace(":", "")
        stamp = f"_{hhmm}"
    return f"{timeframe}_LIVE_{kind}_{int(round(_mid(zone['zone_low'], zone['zone_high'])))}{stamp}"


def zone_to_level(
    timeframe: str,
    zone: dict,
    *,
    tests: int,
    left: bool,
    closed_m1: dict | None,
) -> dict:
    failure = m1_failure_at_zone(zone, closed_m1)
    if zone["kind"] == "high":
        if tests >= 2 and failure:
            pattern = "double_top"
            label = "live_double_top"
        elif tests >= 2:
            pattern = "mapped_high"
            label = "live_swing_high"
        else:
            pattern = "first_test_high"
            label = "live_first_high"
    else:
        if tests >= 2 and failure:
            pattern = "double_bottom"
            label = "live_double_bottom"
        elif tests >= 2:
            pattern = "mapped_low"
            label = "live_swing_low"
        else:
            pattern = "first_test_low"
            label = "live_first_low"
    return {
        "level_id": _level_id(timeframe, zone),
        "timeframe": timeframe,
        "zone_low": round(float(zone["zone_low"]), 6),
        "zone_high": round(float(zone["zone_high"]), 6),
        "role": "mapped_important",
        "label": label,
        "pattern": pattern,
        "test_count": tests,
        "left_after_first": left,
        "source_candle_ids": zone.get("source_candle_ids") or [],
        "calculation_method": "live_closed_swing",
        "valid_from_utc": _iso(zone.get("valid_from_utc")) if zone.get("valid_from_utc") else None,
    }


def build_from_completed(
    completed_by_tf: dict[str, list[dict]],
    closed_m1: dict | None,
    price: float,
    *,
    as_of: datetime | None = None,
) -> list[dict]:
    """Mint mapped zones from completed candles. Safe to run on every M1 close."""
    del as_of
    levels: list[dict] = []
    for timeframe, lookback in LOOKBACK.items():
        rows = list(completed_by_tf.get(timeframe) or [])[-lookback:]
        if len(rows) < WING[timeframe] * 2 + 1:
            continue
        width = ZONE_WIDTH[timeframe]
        swings = fractal_swings(rows, WING[timeframe], "high") + fractal_swings(
            rows, WING[timeframe], "low"
        )
        for zone in cluster_swings(swings, width):
            tests, left = count_visits(zone, rows)
            if tests < 1:
                continue
            levels.append(
                zone_to_level(
                    timeframe,
                    zone,
                    tests=tests,
                    left=left,
                    closed_m1=closed_m1,
                )
            )
    if price:
        levels.sort(
            key=lambda row: (
                abs(_mid(row["zone_low"], row["zone_high"]) - float(price)),
                row["level_id"],
            )
        )
        kept: list[dict] = []
        per_tf: dict[str, int] = {}
        for row in levels:
            count = per_tf.get(row["timeframe"], 0)
            active = row.get("pattern") in {"double_top", "double_bottom"}
            if count >= MAX_ZONES_PER_TF and not active:
                continue
            per_tf[row["timeframe"]] = count + 1
            kept.append(row)
        levels = kept
    levels.sort(key=lambda row: (row["zone_low"], row["level_id"]))
    return levels


def overlaps_existing(row: dict, existing: Iterable[dict], width: float) -> bool:
    mid = _mid(row["zone_low"], row["zone_high"])
    for other in existing:
        other_mid = _mid(other["zone_low"], other.get("zone_high", other["zone_low"]))
        if abs(mid - other_mid) <= width:
            return True
    return False


def is_live_or_mapped(row: dict) -> bool:
    method = str(row.get("calculation_method") or "")
    role = str(row.get("role") or "")
    level_id = str(row.get("level_id") or row.get("id") or "")
    return (
        method in LIVE_METHODS
        or role == "mapped_important"
        or "_LIVE_" in level_id
        or "_MAPPED_" in level_id
    )


def select_nearby(
    level_rows: list[dict],
    bid: float,
    closed_m1: dict | None = None,
    limit: int = NEARBY_LIMIT,
) -> list[dict]:
    """Nearest live/mapped zones, not last-bar previous high/low noise."""
    bid = float(bid)
    preferred = [row for row in level_rows if is_live_or_mapped(row)]
    preferred.sort(key=lambda row: abs(_mid(row["zone_low"], row["zone_high"]) - bid))
    chosen: list[dict] = []
    seen: set[str] = set()

    def take(row: dict) -> None:
        level_id = str(row.get("level_id") or row.get("id") or "")
        if not level_id or level_id in seen:
            return
        seen.add(level_id)
        chosen.append(row)

    for row in preferred:
        if str(row.get("pattern") or "") in {"double_top", "double_bottom"}:
            take(row)
    for row in preferred:
        if len(chosen) >= limit:
            break
        take(row)
    if len(chosen) < 3:
        rest = [
            row
            for row in level_rows
            if str(row.get("timeframe") or "") not in {"M1"}
            or is_live_or_mapped(row)
        ]
        rest.sort(key=lambda row: abs(_mid(row["zone_low"], row["zone_high"]) - bid))
        for row in rest:
            if len(chosen) >= 3:
                break
            take(row)
    return chosen[:limit]


def level_kind(row: dict) -> str:
    pattern = str(row.get("pattern") or "")
    label = str(row.get("label") or "")
    level_id = str(row.get("level_id") or row.get("id") or "")
    if "double_top" in pattern or "high" in pattern or "_LIVE_H_" in level_id or "HIGH" in level_id:
        return "H"
    if "double_bottom" in pattern or "low" in pattern or "_LIVE_L_" in level_id or "LOW" in level_id:
        return "L"
    if "high" in label:
        return "H"
    return "L"


def live_map_packet(
    level_rows: list[dict],
    bid: float,
    closed_m1: dict | None,
) -> dict:
    nearby = select_nearby(level_rows, bid, closed_m1)
    double_top = None
    double_bottom = None
    for row in nearby + [item for item in level_rows if is_live_or_mapped(item)]:
        pattern = str(row.get("pattern") or "")
        zone = {
            "kind": "high" if level_kind(row) == "H" else "low",
            "zone_low": row["zone_low"],
            "zone_high": row["zone_high"],
        }
        if pattern == "double_top" and m1_failure_at_zone(zone, closed_m1) and double_top is None:
            double_top = _slim_map_row(row, bid)
        if pattern == "double_bottom" and m1_failure_at_zone(zone, closed_m1) and double_bottom is None:
            double_bottom = _slim_map_row(row, bid)
    return {
        "near": [_slim_map_row(row, bid) for row in nearby],
        "double_top": double_top,
        "double_bottom": double_bottom,
    }


def _slim_map_row(row: dict, bid: float) -> dict:
    lo = float(row["zone_low"])
    hi = float(row.get("zone_high", lo))
    return {
        "id": row.get("level_id") or row.get("id"),
        "tf": row.get("timeframe"),
        "lo": lo,
        "hi": hi,
        "tests": row.get("test_count"),
        "pattern": row.get("pattern"),
        "dist": round(_mid(lo, hi) - float(bid), 3),
    }


def nearby_payload(rows: list[dict], bid: float) -> list[dict]:
    return [
        {
            "id": row.get("level_id") or row.get("id"),
            "price": round(_mid(row["zone_low"], row["zone_high"]), 6),
            "distance": round(_mid(row["zone_low"], row["zone_high"]) - float(bid), 6),
            "pattern": row.get("pattern"),
            "test_count": row.get("test_count"),
        }
        for row in rows
    ]


def should_pin(row: dict, mid_price: float) -> bool:
    level_id = str(row.get("id") or row.get("level_id") or "")
    role = str(row.get("role") or "")
    pattern = str(row.get("pattern") or "")
    if pattern in {"double_top", "double_bottom"}:
        return True
    if role != "mapped_important" and "_LIVE_" not in level_id and "_MAPPED_" not in level_id:
        return False
    lo = float(row.get("lo", row.get("zone_low", 0)))
    hi = float(row.get("hi", row.get("zone_high", lo)))
    return abs(_mid(lo, hi) - float(mid_price)) <= PIN_BAND
