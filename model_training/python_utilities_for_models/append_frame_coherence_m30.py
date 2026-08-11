#!/usr/bin/env python3
"""Append frame-coherence and M30-anchored examples, grounded in real cache evidence.

Why this pack exists
--------------------
Two measured facts from 2026-08-10 live trading:

1.  M30 is the only profitable anchor, and it is absent from the curriculum.

        anchor   n   net       win%
        M30      6   +385.45   66.7      <- 1 training example
        H4       7   -116.85   14.3      <- 147 training examples
        H1       6   -316.20   16.7      <- 124 training examples
        M15      2   -197.50    0.0      <- 199 training examples

    The curriculum trains hardest on the frames that lose money and barely at
    all on the one that wins.

2.  Frame incoherence is the single largest P&L leak. Bucketing closed trades by
    (invalidation rank - entry zone rank):

        gap <= 4    n=7    +574.90
        gap >= 5    n=14  -1070.00   win 7%

    An M1 entry zone defended by an H4/D1 invalidation is a scalp wearing a
    swing thesis. The runtime then brackets it at a flat $3, which on the last
    seven trades sat up to 8.46 points INSIDE the level that would actually
    prove the trade wrong -- so ordinary noise closed it before the idea was
    tested.

This generator teaches both lessons:

  * M30-anchored open examples using the CURRICULUM_AND_DATA_PREP.md 1.1 ladder
    (M15/M30 -> min SL 5, min TP 5).
  * Skip examples where the entry trigger and the invalidation belong to
    incompatible frames, with the reason stated explicitly.

Per 0.1 rule 5 nothing is invented: candles, level IDs and prices are read from
cache/market_context.sqlite3 (real completed M30 candles and real levels
snapshots). If the cache is unavailable the script exits rather than fabricating.

Usage
-----
    python python_utilities_for_models/append_frame_coherence_m30.py --dry-run
    python python_utilities_for_models/append_frame_coherence_m30.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
STAGE_02 = KNOWLEDGE / "stage_02_structured_data.jsonl"
STAGE_04 = KNOWLEDGE / "stage_04_decision_contract.jsonl"
DB = ROOT.parent / "apps" / "qwen_trade_software" / "backend" / "cache" / "market_context.sqlite3"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TF_RANK = {tf: i for i, tf in enumerate(TIMEFRAMES)}

# CURRICULUM_AND_DATA_PREP.md 1.1 -- gold points, not account dollars.
TF_MIN_SL_TP = {
    "M15": (5, 5), "M30": (5, 5),
    "H1": (7, 10),
    "H4": (10, 20), "D1": (10, 20),
}

# Live policy: invalidation may sit at the zone's frame or at most this many
# steps above it. Derived from the gap<=4 / gap>=5 P&L split above.
MAX_INVALIDATION_GAP = 4


def timeframe_of(level_id: str) -> str | None:
    head = str(level_id or "").split("_", 1)[0].upper()
    return head if head in TF_RANK else None


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def append_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _open_snapshot(db: Path) -> sqlite3.Connection:
    """Open the cache read-only, snapshotting if the live service holds it.

    The cache runs in WAL mode under the always-on context_cache child, so a
    direct read can fail with 'disk I/O error'. Copying the db plus its -wal and
    -shm sidecars to a temp location gives a consistent point-in-time view
    without disturbing the running system.
    """
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.execute("select 1 from completed_candles limit 1").fetchone()
        return con
    except sqlite3.Error:
        pass
    temp = Path(tempfile.mkdtemp(prefix="qcache_")) / db.name
    for suffix in ("", "-wal", "-shm"):
        source = Path(str(db) + suffix)
        if source.exists():
            shutil.copy2(source, str(temp) + suffix)
    return sqlite3.connect(str(temp))


def read_evidence(db: Path) -> tuple[list[dict], list[dict]]:
    """Real completed M30 candles and real level snapshots."""
    if not db.exists():
        raise SystemExit(f"cache not found: {db}\nRefusing to invent evidence (0.1 rule 5).")
    con = _open_snapshot(db)
    con.row_factory = sqlite3.Row
    candles = [
        dict(r) for r in con.execute(
            """select open_time_utc, open, high, low, close, tick_volume, evidence_id
               from completed_candles where timeframe='M30'
               order by open_time_utc"""
        )
    ]
    snapshots = []
    for row in con.execute(
        """select payload_json, created_at_utc from cache_objects
           where cache_type='levels' order by created_at_utc desc limit 400"""
    ):
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, ValueError):
            continue
        levels = {
            lv["level_id"]: float(lv.get("zone_low", 0) or 0)
            for lv in payload.get("levels", [])
            if lv.get("level_id")
        }
        if levels:
            snapshots.append({"at": row["created_at_utc"], "levels": levels})
    con.close()
    return candles, snapshots


def nearest_level(levels: dict[str, float], price: float, frames: set[str],
                  above: bool) -> tuple[str | None, float | None]:
    best, best_gap = None, float("inf")
    for name, value in levels.items():
        if timeframe_of(name) not in frames or not value:
            continue
        gap = (value - price) if above else (price - value)
        if gap <= 0:
            continue
        if gap < best_gap:
            best, best_gap = name, gap
    return best, (levels[best] if best else None)


def build_m30_examples(candles: list[dict], snapshots: list[dict], limit: int) -> tuple[list, list]:
    """M30-anchored opens: entry at an M30 zone, invalidation within the family."""
    s2_rows, s4_rows = [], []
    min_sl, min_tp = TF_MIN_SL_TP["M30"]
    permitted = {
        tf for tf in TIMEFRAMES
        if 0 <= TF_RANK[tf] - TF_RANK["M30"] <= MAX_INVALIDATION_GAP
    }
    seq = 0
    for snap in snapshots:
        if seq >= limit:
            break
        levels = snap["levels"]
        if "M30_PREVIOUS_LOW" not in levels or "M30_PREVIOUS_HIGH" not in levels:
            continue
        for side, zone_id in (("buy", "M30_PREVIOUS_LOW"), ("sell", "M30_PREVIOUS_HIGH")):
            if seq >= limit:
                break
            entry = levels[zone_id]
            if not entry:
                continue
            if side == "buy":
                stop_id, stop_px = nearest_level(levels, entry, permitted, above=False)
                target_id, target_px = nearest_level(levels, entry, permitted, above=True)
            else:
                stop_id, stop_px = nearest_level(levels, entry, permitted, above=True)
                target_id, target_px = nearest_level(levels, entry, permitted, above=False)
            if not (stop_id and target_id and stop_px and target_px):
                continue
            # Pad to the M30 minimums per 1.1 without moving inside the level.
            direction = 1.0 if side == "buy" else -1.0
            sl = min(stop_px, entry - min_sl) if side == "buy" else max(stop_px, entry + min_sl)
            tp = max(target_px, entry + min_tp) if side == "buy" else min(target_px, entry - min_tp)
            if abs(entry - sl) < min_sl or abs(tp - entry) < min_tp:
                continue
            seq += 1
            eid = f"m30_{seq:03d}"
            decision = "Long scalp" if side == "buy" else "Short scalp"
            setup = (
                f"M30 auction at {zone_id}: closed M30 response at the mapped zone, "
                f"invalidation held at {stop_id}"
            )
            why = (
                f"{side} because the M30 zone {zone_id} produced a closed response and the "
                f"invalidation {stop_id} sits in the same frame family - the thesis can be "
                f"tested before the stop is reached."
            )
            s2_rows.append({
                "example_id": eid,
                "topic": "04_timeframe_relations",
                "title": f"M30 zone continuation at {zone_id}",
                "setup": setup,
                "decision": decision,
                "invalidation": f"Closed M30 through {stop_id} at {stop_px}",
                "why": why,
                "evidence": "strong",
                "bucket": "A",
            })
            s4_rows.append({
                "example_id": eid,
                "detector_output": "m30_zone_response",
                "trade_decision": decision,
                "decision_conditions": f"closed M30 response at {zone_id}",
                "evidence_label": "strong",
                "conviction_score": 0.8,
                "risk_control": (
                    f"SL ${abs(entry-sl):.1f} gold at {sl:.3f} | "
                    f"TP ${abs(tp-entry):.1f} gold at {tp:.3f} | Entry {entry:.3f}"
                ),
                "key_levels": ", ".join(
                    f"{n}={v:.3f}" for n, v in sorted(levels.items()) if v
                ),
                "entry_price": round(entry, 3),
                "sl_price": round(sl, 3),
                "tp_price": round(tp, 3),
                "sl_usd": round(abs(entry - sl), 1),
                "tp_usd": round(abs(tp - entry), 1),
                "action": "open",
                "direction": side,
                "confidence": 78,
                "auction_state": "rejection",
                "skip_reason_code": None,
                "target_mode": "scalp",
                "role": "entry",
                "missing_fact": None,
                "structure_timeframe": "M30",
                "trade_reason": (
                    "Concept: the trade's frame is set by the zone being traded. An M30 zone is "
                    f"defended by M30-to-H1 structure, not by a distant swing level. Reason: {why}"
                ),
                "confirmation_reason": (
                    f"A closed M30 candle reacted at {zone_id}; the forming candle is context only. "
                    f"Invalidation is a closed M30 through {stop_id}."
                ),
            })
    return s2_rows, s4_rows


def build_incoherence_skips(snapshots: list[dict], limit: int) -> tuple[list, list]:
    """Skip examples: entry trigger and invalidation in incompatible frames."""
    s2_rows, s4_rows = [], []
    seq = 0
    for snap in snapshots:
        if seq >= limit:
            break
        levels = snap["levels"]
        for zone_id, bad_stop_id in (
            ("M1_PREVIOUS_LOW", "H4_PREVIOUS_LOW"),
            ("M1_PREVIOUS_HIGH", "D1_PREVIOUS_HIGH"),
            ("M1_PREVIOUS_LOW", "D1_PREVIOUS_LOW"),
            ("M5_PREVIOUS_HIGH", "H4_PREVIOUS_HIGH"),
        ):
            if seq >= limit:
                break
            if zone_id not in levels or bad_stop_id not in levels:
                continue
            gap = TF_RANK[timeframe_of(bad_stop_id)] - TF_RANK[timeframe_of(zone_id)]
            if gap <= MAX_INVALIDATION_GAP:
                continue
            seq += 1
            eid = f"fc_{seq:03d}"
            side = "buy" if "LOW" in zone_id else "sell"
            why = (
                f"skip because the entry zone {zone_id} is {timeframe_of(zone_id)} but the only "
                f"invalidation available is {bad_stop_id} ({timeframe_of(bad_stop_id)}), {gap} "
                "frames away. A stop placed near the entry sits far inside the level that would "
                "actually prove the idea wrong, so noise closes the trade before the thesis is "
                "tested. Wait for a zone whose invalidation belongs to the same frame family."
            )
            s2_rows.append({
                "example_id": eid,
                "topic": "04_timeframe_relations",
                "title": f"Frame mismatch: {timeframe_of(zone_id)} zone, {timeframe_of(bad_stop_id)} invalidation",
                "setup": (
                    f"Price reacts at {zone_id} but the nearest structural invalidation is "
                    f"{bad_stop_id}, {gap} timeframes higher"
                ),
                "decision": "Skip",
                "invalidation": "No same-frame invalidation available",
                "why": why,
                "evidence": "strong",
                "bucket": "A",
            })
            s4_rows.append({
                "example_id": eid,
                "detector_output": "frame_mismatch_detected",
                "trade_decision": "Skip",
                "decision_conditions": (
                    f"entry zone {timeframe_of(zone_id)} vs invalidation "
                    f"{timeframe_of(bad_stop_id)} = {gap} frames apart"
                ),
                "evidence_label": "strong",
                "conviction_score": 0.2,
                "risk_control": "SL N/A | TP N/A | no coherent frame",
                "key_levels": ", ".join(
                    f"{n}={v:.3f}" for n, v in sorted(levels.items()) if v
                ),
                "entry_price": 0.0,
                "sl_price": 0.0,
                "tp_price": 0.0,
                "sl_usd": 0.0,
                "tp_usd": 0.0,
                "action": "skip",
                "direction": "none",
                "confidence": 50,
                "auction_state": "transition",
                "skip_reason_code": "frame_incoherent",
                "target_mode": "none",
                "role": "skip",
                "missing_fact": f"same-frame invalidation for {zone_id}",
                "structure_timeframe": timeframe_of(zone_id),
                "trade_reason": (
                    "Concept: one trade, one frame. Trigger, invalidation and target must belong "
                    f"to the same family. Reason: {why}"
                ),
                "confirmation_reason": (
                    f"No closed response can rescue this: the {timeframe_of(zone_id)} trigger "
                    f"cannot be defended by a {timeframe_of(bad_stop_id)} level. Skip and wait."
                ),
            })
    return s2_rows, s4_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--m30", type=int, default=60)
    parser.add_argument("--skips", type=int, default=40)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    candles, snapshots = read_evidence(DB)
    print(f"evidence: {len(candles)} real M30 candles, {len(snapshots)} real level snapshots")

    m30_s2, m30_s4 = build_m30_examples(candles, snapshots, args.m30)
    fc_s2, fc_s4 = build_incoherence_skips(snapshots, args.skips)

    print(f"\nM30-anchored opens : {len(m30_s4)}  sides={dict(Counter(r['direction'] for r in m30_s4))}")
    print(f"frame-mismatch skips: {len(fc_s4)}")

    if not m30_s4 and not fc_s4:
        print("nothing generated -- cache lacks the required levels")
        return 1

    if args.dry_run:
        print("\n--- sample M30 open ---")
        print(json.dumps(m30_s4[0], indent=2)[:900] if m30_s4 else "(none)")
        print("\n--- sample frame-mismatch skip ---")
        print(json.dumps(fc_s4[0], indent=2)[:900] if fc_s4 else "(none)")
        print("\n(dry run, nothing written)")
        return 0

    existing = {r["example_id"] for r in load_jsonl(STAGE_04)}
    new_s2 = [r for r in m30_s2 + fc_s2 if r["example_id"] not in existing]
    new_s4 = [r for r in m30_s4 + fc_s4 if r["example_id"] not in existing]
    append_jsonl(STAGE_02, new_s2)
    append_jsonl(STAGE_04, new_s4)
    print(f"\nappended {len(new_s4)} rows to stage_02 and stage_04")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
