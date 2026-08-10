#!/usr/bin/env python3
"""Widen/re-anchor stage_04 open-entry SL/TP to v004 zone-based gold distances.

See model_training/CURRICULUM_AND_DATA_PREP.md §1.1.

Mins (gold price, not account P&L):
  M15/M30 → SL≥5 TP≥5
  H1      → SL≥7 TP≥10
  H4/D1   → SL≥10 TP≥20

Usage:
  python repair_zone_sl_tp_v004.py --dry-run
  python repair_zone_sl_tp_v004.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "knowledge"
STAGE_02 = "stage_02_structured_data.jsonl"
STAGE_04 = "stage_04_decision_contract.jsonl"

TF_MINS = {
    "M15": (5.0, 5.0),
    "M30": (5.0, 5.0),
    "H1": (7.0, 10.0),
    "H4": (10.0, 20.0),
    "D1": (10.0, 20.0),
}
MAX_GOLD_DISTANCE = 80.0
LEVEL_RE = re.compile(
    r"([A-Za-z0-9_]+)\s*=\s*(-?\d+(?:\.\d+)?)"
)
TINY_INV_RE = re.compile(
    r"\$[34](?:\.\d+)?\s*(?:beyond|above|below)",
    re.I,
)


def load(name: str) -> list[dict]:
    path = ROOT / name
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save(name: str, rows: list[dict]) -> None:
    (ROOT / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def parse_levels(text: str) -> list[tuple[str, float]]:
    """Parse named level=price pairs; ignore counters/flags and non-gold prices."""
    out: list[tuple[str, float]] = []
    skip_tokens = ("COUNT", "RATIO", "SCORE", "FLAG", "STATE", "BARS", "SECONDS")
    for match in LEVEL_RE.finditer(text or ""):
        level_id = match.group(1)
        price = float(match.group(2))
        upper = level_id.upper()
        if any(tok in upper for tok in skip_tokens):
            continue
        # XAU training ladder is ~2k–5k; reject junk like TEST_COUNT=3.
        if price < 1000.0 or price > 10000.0:
            continue
        out.append((level_id, price))
    return out


def _level_tf(level_id: str) -> str | None:
    for tf in ("M15", "M30", "H1", "H4", "D1", "M5", "M1"):
        if level_id.startswith(f"{tf}_") or level_id.startswith(f"{tf}-"):
            return tf
    return None


def infer_structure_tf(key_levels: str, setup: str, title: str = "") -> str:
    """Pick the trade's structure TF for min SL/TP (execution nest, not HTF tag)."""
    setup_l = f"{setup} {title}".lower()
    # Explicit nest / pullback language wins — M15 scalps must not inherit H4 mins
    # just because an H4 confluence ID is listed in key_levels.
    if re.search(r"\bm15\s+nest\b|\bm15\s+pullback\b|\bm15\s+brg\b", setup_l):
        return "M15"
    if re.search(r"\bm30\s+nest\b", setup_l):
        return "M30"
    if re.search(r"\bh1\s+nest\b|\bh1\s+refine\b", setup_l):
        return "H1"
    if re.search(r"\bh4\s+nest\b|\bh4\s*\(|\bh4\s+range\b|\bh4\s+bull\b|\bh4\s+bear\b", setup_l):
        return "H4"
    if re.search(r"\bd1\b", setup_l) and "h4" not in setup_l and "m15" not in setup_l:
        return "D1"

    votes: list[str] = []
    for level_id, _ in parse_levels(key_levels):
        tf = _level_tf(level_id)
        if tf in TF_MINS:
            votes.append(tf)
    # Prefer the traded/lower TF among named levels when nest is unclear.
    for tf in ("M15", "M30", "H1", "H4", "D1"):
        if tf in votes:
            return tf
    for tf in ("M15", "M30", "H1", "H4", "D1"):
        if re.search(rf"\b{tf}\b", setup_l, re.I):
            return tf
    return "H1"


def side_of(row: dict) -> str | None:
    direction = str(row.get("direction") or "").strip().lower()
    if direction in ("buy", "sell"):
        return direction
    td = str(row.get("trade_decision") or "").lower()
    if any(w in td for w in ("short", "sell")) and "long" not in td:
        return "sell"
    if any(w in td for w in ("long", "buy")) and "short" not in td:
        return "buy"
    entry = float(row.get("entry_price") or 0)
    sl = float(row.get("sl_price") or 0)
    if entry > 0 and sl > 0:
        return "sell" if sl > entry else "buy"
    return None


def is_open_entry(row: dict) -> bool:
    if str(row.get("role") or "entry") == "management":
        return False
    action = str(row.get("action") or "").strip().lower()
    entry = float(row.get("entry_price") or 0)
    if action == "open" and entry > 0:
        return True
    if action in ("wait", "skip"):
        return False
    td = str(row.get("trade_decision") or "").lower()
    if any(td.startswith(p) for p in ("wait", "skip", "hold")):
        return False
    return entry > 0


def pick_zone_price(
    side: str,
    entry: float,
    levels: list[tuple[str, float]],
    *,
    for_stop: bool,
    min_dist: float,
) -> float:
    """Nearest named level on the correct side, padded to min gold distance."""
    if for_stop:
        if side == "buy":
            candidates = sorted(
                ((lid, p) for lid, p in levels if p < entry - 1e-9),
                key=lambda item: item[1],
                reverse=True,
            )
            floor = entry - min_dist
            if candidates:
                price = min(candidates[0][1], floor)
            else:
                price = floor
            return round(price, 3)
        candidates = sorted(
            ((lid, p) for lid, p in levels if p > entry + 1e-9),
            key=lambda item: item[1],
        )
        ceiling = entry + min_dist
        if candidates:
            price = max(candidates[0][1], ceiling)
        else:
            price = ceiling
        return round(price, 3)

    # target
    if side == "buy":
        candidates = sorted(
            ((lid, p) for lid, p in levels if p > entry + 1e-9),
            key=lambda item: item[1],
        )
        # Prefer first level that already clears min; else pad nearest.
        for _, price in candidates:
            if price - entry >= min_dist - 1e-9:
                return round(price, 3)
        if candidates:
            return round(max(candidates[0][1], entry + min_dist), 3)
        return round(entry + min_dist, 3)

    candidates = sorted(
        ((lid, p) for lid, p in levels if p < entry - 1e-9),
        key=lambda item: item[1],
        reverse=True,
    )
    for _, price in candidates:
        if entry - price >= min_dist - 1e-9:
            return round(price, 3)
    if candidates:
        return round(min(candidates[0][1], entry - min_dist), 3)
    return round(entry - min_dist, 3)


def ensure_key_levels(
    side: str,
    entry: float,
    sl: float,
    tp: float,
    existing: str,
    structure_tf: str,
) -> str:
    levels = parse_levels(existing)
    if levels:
        return existing if existing != "N/A" else existing
    if side == "buy":
        return (
            f"{structure_tf}_PREVIOUS_LOW={sl}, "
            f"M15_PREVIOUS_LOW={min(entry - 1, sl + 1):.1f}, "
            f"{structure_tf}_TARGET={tp}"
        )
    return (
        f"{structure_tf}_PREVIOUS_HIGH={sl}, "
        f"M15_PREVIOUS_HIGH={max(entry + 1, sl - 1):.1f}, "
        f"{structure_tf}_TARGET={tp}"
    )


def apply_zone_geometry(
    row: dict,
    side: str,
    entry: float,
    structure_tf: str,
    levels: list[tuple[str, float]],
) -> tuple[float, float, float, float]:
    min_sl, min_tp = TF_MINS[structure_tf]
    sl = pick_zone_price(side, entry, levels, for_stop=True, min_dist=min_sl)
    tp = pick_zone_price(side, entry, levels, for_stop=False, min_dist=min_tp)
    if side == "buy":
        sl_usd = round(entry - sl, 3)
        tp_usd = round(tp - entry, 3)
    else:
        sl_usd = round(sl - entry, 3)
        tp_usd = round(entry - tp, 3)
    # Enforce mins after rounding / level choice.
    if sl_usd < min_sl:
        sl = round(entry - min_sl if side == "buy" else entry + min_sl, 3)
        sl_usd = min_sl
    if tp_usd < min_tp:
        tp = round(entry + min_tp if side == "buy" else entry - min_tp, 3)
        tp_usd = min_tp
    row["entry_price"] = entry
    row["sl_price"] = sl
    row["tp_price"] = tp
    row["sl_usd"] = sl_usd
    row["tp_usd"] = tp_usd
    row["key_levels"] = ensure_key_levels(
        side, entry, sl, tp, str(row.get("key_levels") or ""), structure_tf
    )
    row["risk_control"] = (
        f"SL ${sl_usd} gold at {sl} | TP ${tp_usd} gold at {tp} | Entry {entry}"
    )
    return sl, tp, sl_usd, tp_usd


def meets_mins(side: str, entry: float, sl: float, tp: float, structure_tf: str) -> bool:
    min_sl, min_tp = TF_MINS[structure_tf]
    if entry < 1000.0 or entry > 10000.0:
        return False
    if sl < 1000.0 or sl > 10000.0 or tp < 1000.0 or tp > 10000.0:
        return False
    if side == "buy":
        if not (sl < entry < tp):
            return False
        sl_d, tp_d = entry - sl, tp - entry
    else:
        if not (tp < entry < sl):
            return False
        sl_d, tp_d = sl - entry, entry - tp
    if sl_d > MAX_GOLD_DISTANCE or tp_d > MAX_GOLD_DISTANCE:
        return False
    return sl_d + 1e-9 >= min_sl and tp_d + 1e-9 >= min_tp


def sync_stage02_invalidation(s2_row: dict, sl: float, sl_usd: float, structure_tf: str) -> bool:
    inv = str(s2_row.get("invalidation") or "")
    if not inv or inv.upper() == "N/A":
        return False
    changed = False
    if TINY_INV_RE.search(inv) or "beyond" in inv.lower() or "$3" in inv or "$4" in inv:
        s2_row["invalidation"] = (
            f"{structure_tf} zone invalidation at {sl} "
            f"(${sl_usd} gold beyond entry structure)"
        )
        changed = True
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print summary without writing JSONL",
    )
    args = parser.parse_args()

    s2_rows = load(STAGE_02)
    s4_rows = load(STAGE_04)
    s2_map = {r["example_id"]: r for r in s2_rows}

    widened = 0
    already_ok = 0
    skipped = 0
    s2_synced = 0
    by_tf: dict[str, int] = {}

    for row in s4_rows:
        if not is_open_entry(row):
            skipped += 1
            continue
        eid = row.get("example_id")
        s2 = s2_map.get(eid, {})
        side = side_of(row)
        entry = float(row.get("entry_price") or 0)
        if side is None or entry <= 0:
            skipped += 1
            continue

        key_levels = str(row.get("key_levels") or "")
        setup = str(s2.get("setup") or "")
        title = str(s2.get("title") or "")
        structure_tf = infer_structure_tf(key_levels, setup, title)
        levels = parse_levels(key_levels)
        if not levels:
            levels = parse_levels(setup)

        old_sl = float(row.get("sl_price") or 0)
        old_tp = float(row.get("tp_price") or 0)
        if meets_mins(side, entry, old_sl, old_tp, structure_tf) and levels:
            # Still refresh wording / distances from prices for consistency.
            if side == "buy":
                sl_usd = round(entry - old_sl, 3)
                tp_usd = round(old_tp - entry, 3)
            else:
                sl_usd = round(old_sl - entry, 3)
                tp_usd = round(entry - old_tp, 3)
            row["sl_usd"] = sl_usd
            row["tp_usd"] = tp_usd
            row["risk_control"] = (
                f"SL ${sl_usd} gold at {old_sl} | TP ${tp_usd} gold at {old_tp} | Entry {entry}"
            )
            already_ok += 1
            by_tf[structure_tf] = by_tf.get(structure_tf, 0) + 1
            if sync_stage02_invalidation(s2, old_sl, sl_usd, structure_tf):
                s2_synced += 1
            continue

        sl, tp, sl_usd, tp_usd = apply_zone_geometry(
            row, side, entry, structure_tf, levels
        )
        widened += 1
        by_tf[structure_tf] = by_tf.get(structure_tf, 0) + 1
        if sync_stage02_invalidation(s2, sl, sl_usd, structure_tf):
            s2_synced += 1

    print(
        f"open_checked={widened + already_ok} widened={widened} "
        f"already_ok={already_ok} skipped_non_open={skipped} s2_synced={s2_synced}"
    )
    print(f"by_tf={by_tf}")

    if args.dry_run:
        print("dry-run: no files written")
        return

    save(STAGE_04, s4_rows)
    save(STAGE_02, s2_rows)
    print(f"wrote {STAGE_04} and {STAGE_02}")


if __name__ == "__main__":
    main()
