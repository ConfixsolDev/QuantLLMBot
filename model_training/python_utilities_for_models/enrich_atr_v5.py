#!/usr/bin/env python3
"""Backfill M1 ATR(51)/ATR(3) for past tick days and stamp all V5 curriculum rows.

V5 dual ATR (CURRICULUM_AND_DATA_PREP.md):
    atr_m1_51       — Wilder ATR period 51 on closed M1 bars
    atr_m1_3        — Wilder ATR period 3 on closed M1 bars
    atr_ratio_3_51  — atr_m1_3 / atr_m1_51 (regime hint; not a hard gate)

What this does
--------------
1. For every day folder under model_training/tick_data/, fetch M1 history from
   MT5 and write atr-m1.jsonl (end-of-day snapshot + hourly points).
2. Stamp atr_m1_51 / atr_m1_3 / atr_ratio_3_51 onto every stage_02, stage_04,
   and stage_05 row so Sample Prepared / LoRA see volatility on all V5 data.
3. Drops legacy atr_m1_6 from stamped rows when rewriting.

Join rule for curriculum rows
-----------------------------
- Live-dated rows (example_id / detector containing YYYYMMDD or 2026-08-DD)
  get that day's end-of-day ATR.
- All other rows get the most recent successfully backfilled day's ATR, with
  atr_source naming the day. Absolute ATR on synthetic ~2600-price seeds is a
  regime label for the prompt contract, not a claim that gold was there.

Usage
-----
    python python_utilities_for_models/enrich_atr_v5.py --dry-run
    python python_utilities_for_models/enrich_atr_v5.py
    python python_utilities_for_models/enrich_atr_v5.py --skip-backfill
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
KNOW = ROOT / "knowledge"
TICKS = ROOT / "tick_data"
BACKEND = REPO / "apps" / "qwen_trade_software" / "backend"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_COMPACT_RE = re.compile(r"(20\d{2})(\d{2})(\d{2})")
DATE_DASH_RE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")

# Known pack → session day when the example_id itself has no date.
PACK_DAY = {
    "sw_live_": "2026-08-12",
    "sw_mgmt_": "2026-08-12",
    "07_swc_": "2026-08-12",
    "09_swc_": "2026-08-12",
    "08_5": "2026-08-12",  # 08_50..08_54 sideways live box
    "live_": "2026-08-10",  # live_outcome_replay pack from 2026-08-10 ledger
    "rg_": "2026-08-13",
    "ds_": "2026-08-13",
    "m5c_": "2026-08-13",
    "fvg_": "2026-08-13",
    "pb_": "2026-08-13",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def save_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def list_tick_days() -> list[str]:
    if not TICKS.exists():
        return []
    return sorted(
        p.name for p in TICKS.iterdir() if p.is_dir() and DATE_DIR_RE.match(p.name)
    )


def row_day(row: dict) -> str | None:
    blob = " ".join(
        str(row.get(k) or "")
        for k in (
            "example_id",
            "detector_output",
            "decision_conditions",
            "trade_reason",
            "confirmation_reason",
            "risk_control",
        )
    )
    m = DATE_DASH_RE.search(blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = DATE_COMPACT_RE.search(blob)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    eid = str(row.get("example_id") or "")
    for prefix, day in PACK_DAY.items():
        if eid.startswith(prefix):
            return day
    return None


def atr_fields(snap: dict, source: str) -> dict:
    from market_atr import atr_ratio_3_51

    a51 = snap.get("atr_m1_51")
    a3 = snap.get("atr_m1_3")
    if a3 is None and snap.get("atr_m1_6") is not None:
        # Legacy atr-m1.jsonl from ATR6 era: recompute ratio only after backfill.
        a3 = None
    ratio = snap.get("atr_ratio_3_51")
    if ratio is None:
        ratio = atr_ratio_3_51(a3, a51)
    fields = {
        "atr_m1_51": a51,
        "atr_m1_3": a3,
        "atr_ratio_3_51": ratio,
        "atr_timeframe": "M1",
        "atr_source": source,
        "atr_as_of_utc": snap.get("as_of_utc") or snap.get("last_closed_time_utc"),
    }
    return fields


def backfill_day(day: str, symbol: str) -> dict | None:
    """Write tick_data/<day>/atr-m1.jsonl and return the EOD snapshot."""
    from market_atr import snapshot_atr

    day_dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # Gold day end near 21:00 UTC; capture just before that when possible.
    eod = day_dt + timedelta(hours=20, minutes=59)
    now = datetime.now(timezone.utc)
    if eod > now:
        eod = now - timedelta(minutes=2)

    records: list[dict] = []
    # Hourly points through the session + EOD.
    hour = day_dt
    while hour <= eod:
        snap = snapshot_atr(symbol, as_of=hour)
        records.append(
            {
                "artifact": "atr_m1",
                "day": day,
                "kind": "hourly",
                **snap,
            }
        )
        hour += timedelta(hours=1)

    eod_snap = snapshot_atr(symbol, as_of=eod)
    records.append(
        {
            "artifact": "atr_m1",
            "day": day,
            "kind": "eod",
            **eod_snap,
        }
    )

    out_dir = TICKS / day
    out_dir.mkdir(parents=True, exist_ok=True)
    save_jsonl(out_dir / "atr-m1.jsonl", records)
    return eod_snap if eod_snap.get("ok") else None


def load_day_eod_atr(day: str) -> dict | None:
    path = TICKS / day / "atr-m1.jsonl"
    if not path.exists():
        return None
    eod = None
    for row in load_jsonl(path):
        if row.get("kind") == "eod" and row.get("ok"):
            eod = row
    return eod


def enrich_rows(
    rows: list[dict],
    by_day: dict[str, dict],
    fallback: dict,
    fallback_day: str,
) -> tuple[list[dict], dict]:
    stats = {"dated": 0, "fallback": 0, "missing": 0}
    out = []
    for row in rows:
        day = row_day(row)
        snap = by_day.get(day) if day else None
        cleaned = {k: v for k, v in row.items() if k != "atr_m1_6"}
        if snap and snap.get("ok") and snap.get("atr_m1_3") is not None:
            stamped = {**cleaned, **atr_fields(snap, f"mt5_m1_eod:{day}")}
            stats["dated"] += 1
        elif fallback and fallback.get("ok") and fallback.get("atr_m1_3") is not None:
            stamped = {
                **cleaned,
                **atr_fields(fallback, f"mt5_m1_eod_fallback:{fallback_day}"),
            }
            stats["fallback"] += 1
        else:
            stamped = {
                **cleaned,
                "atr_m1_51": None,
                "atr_m1_3": None,
                "atr_ratio_3_51": None,
                "atr_timeframe": "M1",
                "atr_source": "unavailable",
                "atr_as_of_utc": None,
            }
            stats["missing"] += 1
        out.append(stamped)
    return out, stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-backfill",
        action="store_true",
        help="Only stamp curriculum from existing atr-m1.jsonl files",
    )
    args = parser.parse_args()

    from review_shared import GOLD_SYMBOL, connect_mt5

    connect_mt5()
    symbol = GOLD_SYMBOL
    days = list_tick_days()
    print(f"tick days: {len(days)} ({days[0] if days else '-'} .. {days[-1] if days else '-'})")

    by_day: dict[str, dict] = {}
    if not args.skip_backfill:
        for day in days:
            if args.dry_run:
                from market_atr import snapshot_atr

                day_dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                eod = min(
                    day_dt + timedelta(hours=20, minutes=59),
                    datetime.now(timezone.utc) - timedelta(minutes=2),
                )
                snap = snapshot_atr(symbol, as_of=eod)
                if snap.get("ok"):
                    by_day[day] = snap
                    print(
                        f"  dry {day} atr_m1_51={snap.get('atr_m1_51')} "
                        f"atr_m1_3={snap.get('atr_m1_3')} "
                        f"ratio={snap.get('atr_ratio_3_51')}"
                    )
                else:
                    print(f"  dry {day} FAIL {snap.get('error')}")
            else:
                snap = backfill_day(day, symbol)
                if snap:
                    by_day[day] = snap
                    print(
                        f"  wrote {day}/atr-m1.jsonl atr_m1_51={snap.get('atr_m1_51')} "
                        f"atr_m1_3={snap.get('atr_m1_3')} "
                        f"ratio={snap.get('atr_ratio_3_51')}"
                    )
                else:
                    print(f"  {day} backfill failed")
    else:
        for day in days:
            snap = load_day_eod_atr(day)
            if snap and snap.get("atr_m1_3") is not None:
                by_day[day] = snap

    if not by_day:
        from market_atr import snapshot_atr

        live = snapshot_atr(symbol)
        if not live.get("ok"):
            print("ERROR: no ATR available from MT5", live.get("error"))
            return 1
        fallback_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        by_day[fallback_day] = live
        print(f"using live snapshot as only source: {live}")

    fallback_day = sorted(by_day.keys())[-1]
    fallback = by_day[fallback_day]
    print(
        f"fallback day={fallback_day} atr_m1_51={fallback.get('atr_m1_51')} "
        f"atr_m1_3={fallback.get('atr_m1_3')} ratio={fallback.get('atr_ratio_3_51')}"
    )

    targets = [
        "stage_02_structured_data.jsonl",
        "stage_04_decision_contract.jsonl",
        "stage_05_live_contract.jsonl",
    ]
    for name in targets:
        path = KNOW / name
        rows = load_jsonl(path)
        if not rows:
            print(f"skip missing {name}")
            continue
        enriched, stats = enrich_rows(rows, by_day, fallback, fallback_day)
        print(
            f"{name}: n={len(enriched)} dated={stats['dated']} "
            f"fallback={stats['fallback']} missing={stats['missing']}"
        )
        if not args.dry_run:
            save_jsonl(path, enriched)
            print(f"  saved {path}")

    if args.dry_run:
        print("dry-run only — no files written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
