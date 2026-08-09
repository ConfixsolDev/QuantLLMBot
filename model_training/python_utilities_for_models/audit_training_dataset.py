#!/usr/bin/env python3
"""Read-only audit of stage_01–04 training curriculum."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "knowledge"


def load(name: str) -> list[dict]:
    path = ROOT / name
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def side(label: str) -> str:
    x = (label or "").lower()
    has_short = any(w in x for w in ("short", "sell"))
    has_long = any(w in x for w in ("long", "buy"))
    if has_short and not has_long:
        return "sell"
    if has_long and not has_short:
        return "buy"
    if "reverse" in x or "reversal" in x:
        return "neutral_reversal"
    if any(w in x for w in ("skip", "wait", "hold")):
        return "skip_wait"
    return "other"


def main() -> None:
    s1 = load("stage_01_principle_foundation.jsonl")
    s2 = load("stage_02_structured_data.jsonl")
    s3 = load("stage_03_detector_definitions.jsonl")
    s4 = load("stage_04_decision_contract.jsonl")

    print("=== COUNTS ===")
    print(f"principles={len(s1)} examples={len(s2)} detectors={len(s3)} contracts={len(s4)}")
    print(f"topics={dict(Counter(r['topic'] for r in s2))}")

    sides = Counter(side(r.get("trade_decision", "")) for r in s4)
    print(f"sides={dict(sides)}")

    print("=== TOP DECISIONS ===")
    for k, v in Counter(r["trade_decision"] for r in s4).most_common(20):
        print(f"  {v:3d}  {k}")

    print("=== TRADE MGMT FIELDS ===")
    for k in ("key_levels", "entry_price", "sl_price", "tp_price", "sl_usd", "tp_usd", "pattern_type"):
        print(f"  {k}: {sum(k in r for r in s4)}/{len(s4)}")

    bad = []
    for r in s4:
        sd = side(r.get("trade_decision", ""))
        e, sl, tp = r.get("entry_price", 0), r.get("sl_price", 0), r.get("tp_price", 0)
        if not e:
            continue
        if sd == "buy" and not (sl < e < tp):
            bad.append((r["example_id"], sd, e, sl, tp))
        if sd == "sell" and not (tp < e < sl):
            bad.append((r["example_id"], sd, e, sl, tp))
    print(f"bad_geometry={len(bad)}")
    for row in bad[:25]:
        print(" ", row)

    print("=== TIMEFRAMES ===")
    for tf in ("M1", "M5", "M15", "M30", "H1", "H4", "D1"):
        print(f"  {tf}: {sum(tf in r.get('setup', '') for r in s2)}")

    concepts = {
        "session": r"session|asia|london|overlap|new.?york|\bNY\b",
        "juke": r"juke|judas|false first",
        "fakeout_sweep": r"fakeout|false break|sweep|close inside",
        "breakout": r"breakout|accepted break|close outside|retest hold",
        "rejection": r"reject|rejection|wick",
        "acceptance": r"accept|acceptance",
        "candle_timing": r"last 5min|last 30min|end.?bar|forming|developing|underlying",
        "day_bias": r"daily rhythm|range day|trend day|day bias|D1 trend",
        "news": r"\bnews\b|release",
        "basket": r"basket|runner|partial",
        "volume": r"volume|participation",
    }
    print("=== DOCTRINE KEYWORDS IN SETUPS ===")
    for name, pat in concepts.items():
        n = sum(bool(re.search(pat, r.get("setup", ""), re.I)) for r in s2)
        print(f"  {name}: {n}")

    # sell vs buy in fakeout/breakout tagged
    print("=== PATTERN_TYPE BY SIDE ===")
    pt = Counter()
    for r in s4:
        p = r.get("pattern_type", "untagged")
        pt[(p, side(r.get("trade_decision", "")))] += 1
    for k, v in sorted(pt.items()):
        print(f"  {k}: {v}")

    # holdout tail
    print("=== HOLDOUT TAIL ===")
    print("last10=", [r["example_id"] for r in s2[-10:]])

    # sell examples lacking rejection/close confirmation language
    sell_ids = [r["example_id"] for r in s4 if side(r.get("trade_decision", "")) == "sell"]
    s2m = {r["example_id"]: r for r in s2}
    weak_sell = []
    for eid in sell_ids:
        setup = s2m.get(eid, {}).get("setup", "")
        if not re.search(r"close|reject|wick|sweep|fakeout|engulf|pin|star|hammer", setup, re.I):
            weak_sell.append(eid)
    print(f"sell_total={len(sell_ids)} weak_confirmation_language={len(weak_sell)}")
    print("weak_sell_sample=", weak_sell[:20])


if __name__ == "__main__":
    main()
