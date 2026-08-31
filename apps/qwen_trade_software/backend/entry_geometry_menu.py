"""Neutral, deterministic menus of contract-valid entry geometry.

The menu does not choose a trade.  It exposes every fresh confirmed response
and the named stop/target levels that are geometrically valid for that response
so Qwen can make the directional and opportunity decision without guessing how
level IDs relate to price.
"""

from __future__ import annotations

from typing import Iterable


STRUCTURAL_ENTRY_TIMEFRAMES = {"M15", "M30", "H1", "H4", "D1"}


def _owner_timeframe(level_id: str) -> str:
    """Return the owning timeframe encoded by a deterministic level id."""
    return str(level_id or "").split("_", 1)[0].upper()


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bounds(level: dict) -> tuple[float, float]:
    lo = _number(level.get("lo", level.get("price")))
    hi = _number(level.get("hi", level.get("zone_high", lo)))
    lo, hi = min(lo, hi), max(lo, hi)
    if abs(lo - hi) < 1e-9:
        lo, hi = lo - 0.4, hi + 0.4
    return lo, hi


def build_geometry_menu(
    levels: Iterable[dict],
    responses: Iterable[dict],
    *,
    minimum_target_distance: float = 5.0,
    choices_each: int = 4,
) -> list[dict]:
    """Return all fresh response anchors with valid named geometry choices.

    Targets and stops are named structural levels. The broker sizes risk from
    the resulting real stop distance.
    """
    level_rows = [
        dict(row) for row in levels
        if row.get("id")
        and _owner_timeframe(str(row.get("id"))) in STRUCTURAL_ENTRY_TIMEFRAMES
    ]
    by_id = {str(row["id"]): row for row in level_rows}
    menu = []
    for response in responses:
        if not response.get("confirmed"):
            continue
        side = str(response.get("direction") or "").lower()
        anchor_id = str(response.get("level_id") or "")
        anchor = by_id.get(anchor_id)
        if side not in {"buy", "sell"} or anchor is None:
            continue
        entry_low, entry_high = _bounds(anchor)
        stops = []
        targets = []
        for row in level_rows:
            level_id = str(row["id"])
            if level_id == anchor_id:
                continue
            lo, hi = _bounds(row)
            if side == "buy":
                if hi < entry_low:
                    stops.append((entry_low - hi, level_id))
                if lo >= entry_high + minimum_target_distance:
                    targets.append((lo - entry_high, level_id))
            else:
                if lo > entry_high:
                    stops.append((lo - entry_high, level_id))
                if hi <= entry_low - minimum_target_distance:
                    targets.append((entry_low - hi, level_id))
        stops.sort()
        targets.sort()
        if not stops or not targets:
            continue
        menu.append({
            "geometry_row_id": f"G{len(menu) + 1}",
            "side": side,
            "entry_low_id": anchor_id,
            "entry_high_id": anchor_id,
            "valid_stop_level_ids": [level_id for _, level_id in stops[:choices_each]],
            "valid_target_level_ids": [level_id for _, level_id in targets[:choices_each]],
            "response_state": response.get("state"),
            "response_candle_id": response.get("candle_id"),
            "instruction": "Choose stop and target from this same row only.",
        })
    return menu


def schema_level_roles(menu: Iterable[dict]) -> dict[str, list[str]]:
    """Flatten menu roles for wire-schema enums without selecting one row."""
    rows = list(menu)
    return {
        "row": sorted({str(row["geometry_row_id"]) for row in rows if row.get("geometry_row_id")}),
        "entry": sorted({
            str(row[key]) for row in rows
            for key in ("entry_low_id", "entry_high_id") if row.get(key)
        }),
        "stop": sorted({
            str(level_id) for row in rows
            for level_id in row.get("valid_stop_level_ids") or []
        }),
        "target": sorted({
            str(level_id) for row in rows
            for level_id in row.get("valid_target_level_ids") or []
        }),
    }
