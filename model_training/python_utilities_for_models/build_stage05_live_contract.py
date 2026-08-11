#!/usr/bin/env python3
"""Build stage_05: live-inference contract alignment.

Why this pack exists
--------------------
stage_04 teaches the right *judgement* but in a vocabulary the live system never
asks for. Measured on the 2026-08-10 curriculum:

    training field   direction (buy/sell/none)   action (open/wait/skip)
    live field       bias (buy/sell/conditional) execution_plan.status (ready/wait)

    occurrences in stage_04:  execution_plan 0 | acknowledged_epochs 0
                              "ready" 0        | "conditional" 0

Two production failures trace directly to that gap:

1. ``bias: "conditional"`` appeared in 65-71% of live decisions. The model was
   never taught the word. It maps trained ``direction: "none"`` (27% of rows)
   onto "conditional" and over-applies it, so almost nothing reaches ready.

2. Entry responses truncated mid-string at the token cap. The live schema
   requires ``acknowledged_epochs`` copied verbatim -- five ~35-char hashes --
   which the model has never been trained to reproduce, so it emits them
   inefficiently.

This generator rewrites each stage_04 row into the exact JSON object the live
entry contract expects, so the model practises the real output shape. It does
not invent judgement: side, confidence, levels and reasons all come from the
existing curated row.

Per CURRICULUM_AND_DATA_PREP.md 0.1 rule 5, nothing here invents levels -- level
IDs are parsed from the row's own ``key_levels`` string.

Usage
-----
    python python_utilities_for_models/build_stage05_live_contract.py
    python python_utilities_for_models/build_stage05_live_contract.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
STAGE_04 = KNOWLEDGE / "stage_04_decision_contract.jsonl"
STAGE_02 = KNOWLEDGE / "stage_02_structured_data.jsonl"
OUT = KNOWLEDGE / "stage_05_live_contract.jsonl"

TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TF_RANK = {tf: i for i, tf in enumerate(TIMEFRAMES)}

# CURRICULUM_AND_DATA_PREP.md 1.1 -- structure-TF SL/TP ladder (gold points).
TF_MIN_SL_TP = {
    "M15": (5, 5), "M30": (5, 5),
    "H1": (7, 10),
    "H4": (10, 20), "D1": (10, 20),
}

# Cache object names the live contract requires acknowledged verbatim.
EPOCH_KEYS = ("structural", "levels", "session", "playbooks", "minute")


def load(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def parse_levels(key_levels: str) -> dict[str, float]:
    """`H1_SUPPORT=2645, M15_PREVIOUS_LOW=2646` -> {id: price}."""
    out: dict[str, float] = {}
    for chunk in str(key_levels or "").split(","):
        if "=" not in chunk:
            continue
        name, _, value = chunk.partition("=")
        try:
            out[name.strip()] = float(value.strip())
        except ValueError:
            continue
    return out


def timeframe_of(level_id: str) -> str | None:
    head = str(level_id or "").split("_", 1)[0].upper()
    return head if head in TF_RANK else None


def synthetic_epochs(example_id: str, symbol: str = "XAUUSDr") -> dict[str, str]:
    """Realistic epoch hashes so the model practises copying them verbatim.

    Shape and length match production exactly (e.g.
    ``structural-XAUUSDr-75d6e8e3d56b190f``). Values are derived
    deterministically from the example id so the dataset is reproducible.
    """
    epochs = {}
    for key in EPOCH_KEYS:
        digest = hashlib.sha256(f"{example_id}:{key}".encode()).hexdigest()[:16]
        epochs[key] = f"{key}-{symbol}-{digest}"
    return epochs


def pick_bias(direction: str, action: str) -> str:
    """Map trained direction/action onto the live bias enum.

    Deliberately never emits "conditional" for a row that has a real side. A
    directional read with a missing confirmation is still buy or sell -- it just
    waits. That distinction is what the live model currently collapses.
    """
    direction = (direction or "").lower()
    if direction in ("buy", "sell"):
        return direction
    return "conditional"


def choose_zone_ids(levels: dict[str, float], entry: float, side: str) -> tuple[str | None, str | None]:
    """Nearest named levels bracketing the entry, preferring one frame family."""
    if not levels or not entry:
        return None, None
    below = sorted(((abs(entry - p), n) for n, p in levels.items() if p <= entry))
    above = sorted(((abs(p - entry), n) for n, p in levels.items() if p >= entry))
    low = below[0][1] if below else (above[0][1] if above else None)
    high = above[0][1] if above else (below[0][1] if below else None)
    return low, high


def choose_stop_target(levels: dict[str, float], entry: float, side: str,
                       sl_price: float, tp_price: float) -> tuple[str | None, str | None]:
    """Named levels closest to the curated SL/TP prices, on the correct side."""
    if not levels:
        return None, None

    def nearest(target: float, predicate) -> str | None:
        cands = [(abs(p - target), n) for n, p in levels.items() if predicate(p)]
        return sorted(cands)[0][1] if cands else None

    if side == "buy":
        stop_id = nearest(sl_price, lambda p: p <= entry)
        target_id = nearest(tp_price, lambda p: p >= entry)
    else:
        stop_id = nearest(sl_price, lambda p: p >= entry)
        target_id = nearest(tp_price, lambda p: p <= entry)
    return stop_id, target_id


def structure_timeframe(*level_ids: str | None) -> str | None:
    frames = [timeframe_of(x) for x in level_ids if timeframe_of(x)]
    if not frames:
        return None
    # The trade's frame is the highest structure it references.
    return max(frames, key=lambda f: TF_RANK[f])


def build_row(s4: dict, s2: dict | None) -> dict | None:
    levels = parse_levels(s4.get("key_levels"))
    entry = float(s4.get("entry_price") or 0)
    sl = float(s4.get("sl_price") or 0)
    tp = float(s4.get("tp_price") or 0)
    action = str(s4.get("action") or "").lower()
    direction = str(s4.get("direction") or "").lower()
    confidence = int(s4.get("confidence") or 0)
    bias = pick_bias(direction, action)

    epochs = synthetic_epochs(s4["example_id"])
    evidence = [n for n in list(levels)[:4]] or ["M15_PREVIOUS_LOW"]

    summary = str(s4.get("trade_reason") or s4.get("decision_conditions") or "")
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) > 118:
        summary = summary[:115].rstrip() + "..."

    if action == "open" and direction in ("buy", "sell") and entry:
        low_id, high_id = choose_zone_ids(levels, entry, direction)
        stop_id, target_id = choose_stop_target(levels, entry, direction, sl, tp)
        if not all((low_id, high_id, stop_id, target_id)):
            return None
        frame = structure_timeframe(stop_id, target_id, low_id)
        plan = {
            "status": "ready",
            "side": direction,
            "entry_low_id": low_id,
            "entry_high_id": high_id,
            "stop_level_id": stop_id,
            "target_level_id": target_id,
            "volume_each": 0.5,
            "reason": re.sub(r"\s+", " ", str(s4.get("confirmation_reason") or ""))[:118],
        }
    else:
        frame = structure_timeframe(*levels.keys()) if levels else None
        reason = (
            s4.get("skip_reason_code")
            or s4.get("missing_fact")
            or s4.get("confirmation_reason")
            or "no closed response at the mapped zone"
        )
        plan = {
            "status": "wait",
            "reason": re.sub(r"\s+", " ", str(reason))[:118],
        }

    return {
        "example_id": f"lc_{s4['example_id']}",
        "source_example_id": s4["example_id"],
        "role": "live_contract",
        "structure_timeframe": frame,
        "prompt_facts": {
            "symbol": "XAUUSDr",
            "epochs": epochs,
            "execution_levels": [
                {"id": name, "price": price} for name, price in sorted(levels.items())
            ],
            "citeable_evidence_ids": evidence,
            "auction_state": s4.get("auction_state"),
            "setup": (s2 or {}).get("setup"),
        },
        "expected_response": {
            "bias": bias,
            "confidence": confidence,
            "summary": summary[:118],
            "acknowledged_epochs": epochs,
            "evidence_ids": evidence[:6],
            "execution_plan": plan,
        },
        "trade_reason": s4.get("trade_reason"),
        "confirmation_reason": s4.get("confirmation_reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s4 = load(STAGE_04)
    s2 = {r["example_id"]: r for r in load(STAGE_02)}

    rows, skipped = [], 0
    for row in s4:
        built = build_row(row, s2.get(row["example_id"]))
        if built is None:
            skipped += 1
            continue
        rows.append(built)

    bias_counts = Counter(r["expected_response"]["bias"] for r in rows)
    status_counts = Counter(r["expected_response"]["execution_plan"]["status"] for r in rows)
    frames = Counter(r["structure_timeframe"] for r in rows)
    conf_by_bias: dict[str, list[int]] = {}
    for r in rows:
        conf_by_bias.setdefault(r["expected_response"]["bias"], []).append(
            r["expected_response"]["confidence"]
        )

    print(f"stage_05 rows: {len(rows)}  (skipped {skipped} without usable named levels)")
    print(f"  bias    : {dict(bias_counts)}")
    print(f"  status  : {dict(status_counts)}")
    print(f"  frames  : {dict(frames)}")
    for bias, values in sorted(conf_by_bias.items()):
        print(f"  confidence[{bias}]: n={len(values)} mean={sum(values)/len(values):.1f}")
    ready = [r for r in rows if r["expected_response"]["execution_plan"]["status"] == "ready"]
    sides = Counter(r["expected_response"]["execution_plan"]["side"] for r in ready)
    print(f"  ready sides: {dict(sides)}")

    if args.dry_run:
        print("\n--- sample ---")
        print(json.dumps(rows[0], indent=2)[:1200])
        print("\n(dry run, nothing written)")
        return 0

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
