#!/usr/bin/env python3
"""
Repair stage_04 SL/TP geometry and ambiguous dual-direction labels.

Legacy one-shot audit fixes (side flips / ambiguous waits). Do **not** use this
script to force tiny SL$3 / TP$7 — that teaching is obsolete for v004.

For zone-based gold-price SL/TP (M15≥5/5, H1≥7/10, H4≥10/20) run:
  python repair_zone_sl_tp_v004.py
See model_training/CURRICULUM_AND_DATA_PREP.md §1.1.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "knowledge"


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def save(name: str, rows: list[dict]) -> None:
    (ROOT / name).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def side_of(label: str) -> str:
    x = (label or "").lower()
    if any(w in x for w in ("short / long", "long / short", "long breakout / short", "short / long")):
        return "ambiguous"
    if "/" in x and "short" in x and "long" in x:
        return "ambiguous"
    if any(w in x for w in ("short", "sell")) and "long" not in x:
        return "sell"
    if any(w in x for w in ("long", "buy")) and "short" not in x:
        return "buy"
    if "reverse" in x or "reversal" in x:
        return "reversal"
    if any(w in x for w in ("skip", "wait")):
        return "skip"
    return "other"


def apply_geometry(row: dict, side: str, entry: float, sl_usd: float = 3.0, tp_usd: float = 7.0) -> None:
    if side == "sell":
        sl = entry + sl_usd
        tp = entry - tp_usd
        levels = row.get("key_levels") or f"H1_RESISTANCE={entry+2:.0f}, M15_PREVIOUS_HIGH={entry+1:.0f}, H4_PREVIOUS_HIGH={entry+4:.0f}"
    else:
        sl = entry - sl_usd
        tp = entry + tp_usd
        levels = row.get("key_levels") or f"H1_SUPPORT={entry-2:.0f}, M15_PREVIOUS_LOW={entry-1:.0f}, H4_PREVIOUS_LOW={entry-4:.0f}"
    row["entry_price"] = entry
    row["sl_price"] = sl
    row["tp_price"] = tp
    row["sl_usd"] = sl_usd
    row["tp_usd"] = tp_usd
    row["key_levels"] = levels if levels != "N/A" else (
        f"H1_RESISTANCE={entry+2:.0f}" if side == "sell" else f"H1_SUPPORT={entry-2:.0f}"
    )
    row["risk_control"] = f"SL ${sl_usd} at {sl} | TP ${tp_usd} at {tp} | Entry {entry}"


def zero_trade(row: dict, reason: str) -> None:
    row["entry_price"] = 0.0
    row["sl_price"] = 0.0
    row["tp_price"] = 0.0
    row["sl_usd"] = 0.0
    row["tp_usd"] = 0.0
    row["key_levels"] = "N/A"
    row["risk_control"] = f"SL N/A | TP N/A | Entry N/A — {reason}"


def infer_reversal_side(setup: str) -> str:
    s = setup.lower()
    bearish = any(w in s for w in ("rejection", "upper wick", "fails to exceed", "resistance", "trend high", "bear", "short"))
    bullish = any(w in s for w in ("support", "lower wick", "hammer", "bull", "long bounce"))
    if bearish and not bullish:
        return "sell"
    if bullish and not bearish:
        return "buy"
    return "sell"  # default fail-high style for Reverse when unclear


def main() -> None:
    s2 = {r["example_id"]: r for r in load("stage_02_structured_data.jsonl")}
    s4 = load("stage_04_decision_contract.jsonl")

    fixed_geom = 0
    fixed_rr = 0
    fixed_ambiguous = 0
    fixed_0927 = False

    for row in s4:
        eid = row["example_id"]
        setup = s2.get(eid, {}).get("setup", "")
        decision = row.get("trade_decision", "")
        sd = side_of(decision)
        entry = float(row.get("entry_price") or 0)
        sl_usd = float(row.get("sl_usd") or 0)
        tp_usd = float(row.get("tp_usd") or 0)

        # Explicit poison: 09_27 short rejection with long geometry
        if eid == "09_27":
            apply_geometry(row, "sell", entry or 2653.0, 3.0, 7.0)
            row["trade_decision"] = "Short reversal"
            row["decision_conditions"] = (
                "M15 bounce to old trend high rejected — short confirmation after upper-wick fail"
            )
            # keep stage_02 in sync later
            fixed_0927 = True
            fixed_geom += 1
            continue

        # Ambiguous dual labels → Wait (do not invent a side)
        if sd == "ambiguous" and entry > 0:
            row["trade_decision"] = "Wait for confirmation"
            row["decision_conditions"] = (
                "Dual-direction label — require closed rejection or acceptance before side choice"
            )
            zero_trade(row, "ambiguous dual-direction setup")
            fixed_ambiguous += 1
            continue

        if entry <= 0:
            continue

        # Bad R:R SL10/TP7 → operator micro template SL3/TP7
        if sl_usd >= 10 and tp_usd > 0 and (tp_usd / sl_usd) < 1.5:
            side = sd
            if side == "reversal":
                side = infer_reversal_side(setup)
            if side not in ("buy", "sell"):
                # keep existing geometry direction from prices
                side = "sell" if row.get("sl_price", 0) > entry else "buy"
            apply_geometry(row, side, entry, 3.0, 7.0)
            fixed_rr += 1

        # Reverse / Reversal confirmation with wrong geometry vs setup
        if sd == "reversal" and entry > 0:
            want = infer_reversal_side(setup)
            have = "sell" if row.get("sl_price", 0) > entry else "buy"
            if want != have:
                apply_geometry(row, want, entry, 3.0, max(tp_usd, 7.0) if tp_usd else 7.0)
                if "confirmation" in decision.lower() or decision == "Reverse":
                    row["trade_decision"] = "Short reversal" if want == "sell" else "Long reversal"
                fixed_geom += 1

    # Sync stage_02 for 09_27 and ambiguous wait conversions
    s2_rows = load("stage_02_structured_data.jsonl")
    s4m = {r["example_id"]: r for r in s4}
    synced = 0
    for r in s2_rows:
        eid = r["example_id"]
        c = s4m[eid]
        if eid == "09_27":
            r["decision"] = "Short reversal"
            r["why"] = "Rejection at old high after bounce — short confirmation"
            synced += 1
        elif c.get("trade_decision") == "Wait for confirmation" and " / " in r.get("decision", ""):
            r["decision"] = "Wait for confirmation"
            r["why"] = "Ambiguous dual-direction — wait closed response"
            synced += 1

    save("stage_04_decision_contract.jsonl", s4)
    save("stage_02_structured_data.jsonl", s2_rows)

    # Re-check
    remain_bad_rr = [
        r for r in s4
        if r.get("entry_price") and r.get("sl_usd") and r.get("tp_usd")
        and r["tp_usd"] / r["sl_usd"] < 1.5
    ]
    r27 = s4m["09_27"]
    print(f"fixed_0927={fixed_0927} geom={r27['entry_price']}/{r27['sl_price']}/{r27['tp_price']} dec={r27['trade_decision']}")
    print(f"fixed_rr={fixed_rr} fixed_ambiguous={fixed_ambiguous} fixed_geom_other={fixed_geom} synced_s2={synced}")
    print(f"remaining_bad_rr={len(remain_bad_rr)}")


if __name__ == "__main__":
    main()
