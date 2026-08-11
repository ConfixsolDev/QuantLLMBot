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
    for k in (
        "key_levels", "entry_price", "sl_price", "tp_price", "sl_usd", "tp_usd",
        "pattern_type", "trade_reason", "confirmation_reason",
    ):
        print(f"  {k}: {sum(k in r and bool(r.get(k)) for r in s4)}/{len(s4)}")
    thin_reason = [
        r["example_id"]
        for r in s4
        if len(str(r.get("trade_reason") or "")) < 40
        or len(str(r.get("confirmation_reason") or "")) < 40
    ]
    print(f"thin_reason_or_confirmation={len(thin_reason)} sample={thin_reason[:10]}")

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

    readiness(s4)


def readiness(s4: list[dict]) -> None:
    """Retrain-readiness gates derived from measured live failures.

    Each check corresponds to a production problem, so a PASS here means the
    curriculum actually addresses it rather than merely being larger.
    """
    print("\n=== RETRAIN READINESS ===")
    checks: list[tuple[str, bool, str]] = []

    # 1. Directional symmetry. Live: buy scored non-zero 1 time in 112.
    by_dir = Counter(str(r.get("direction")) for r in s4)
    buy, sell = by_dir.get("buy", 0), by_dir.get("sell", 0)
    share = min(buy, sell) / max(buy, sell) if max(buy, sell) else 0
    checks.append((
        "side balance", share >= 0.75,
        f"buy={buy} sell={sell} ratio={share:.2f} (need >=0.75)",
    ))

    # 2. Confidence must be taught symmetrically, or the model cannot score one side.
    conf = {"buy": [], "sell": []}
    for r in s4:
        d = str(r.get("direction"))
        if d in conf and isinstance(r.get("confidence"), (int, float)):
            conf[d].append(r["confidence"])
    means = {k: (sum(v) / len(v) if v else 0) for k, v in conf.items()}
    delta = abs(means["buy"] - means["sell"])
    checks.append((
        "confidence symmetry", delta <= 5,
        f"buy={means['buy']:.1f} sell={means['sell']:.1f} delta={delta:.1f} (need <=5)",
    ))

    # 3. Zero-confidence directional rows would teach the exact live bug.
    bad = [
        r["example_id"] for r in s4
        if str(r.get("direction")) in ("buy", "sell") and not r.get("confidence")
    ]
    checks.append((
        "no zero-confidence directional rows", not bad,
        f"{len(bad)} offenders {bad[:5]}",
    ))

    # 4. M30 coverage. Live: the only profitable anchor, previously 1 example.
    m30 = sum(1 for r in s4 if str(r.get("structure_timeframe")) == "M30")
    checks.append((
        "M30 anchored examples", m30 >= 30,
        f"{m30} rows (need >=30; M30 was the only profitable live frame)",
    ))

    # 5. Frame-incoherence teaching. Live: gap>=5 cost -1070 over 14 trades.
    fc = sum(1 for r in s4 if r.get("skip_reason_code") == "frame_incoherent")
    checks.append((
        "frame-incoherence skips", fc >= 20,
        f"{fc} rows (need >=20)",
    ))

    # 6. Outcome-grounded rows so the curriculum learns from realised P&L.
    live = sum(1 for r in s4 if r.get("detector_output") == "live_outcome_replay")
    checks.append((
        "outcome-grounded rows", live >= 10,
        f"{live} rows (need >=10)",
    ))

    # 7. Patience. Live: hold-to-target +247.38 vs discretionary close -20.22.
    patience = sum(1 for r in s4 if r.get("skip_reason_code") == "premature_discretionary_close")
    checks.append((
        "premature-close lessons", patience >= 5,
        f"{patience} rows (need >=5)",
    ))

    # 8. In-trade management coverage. Live: discretionary closes averaged
    #    -20.22 against +247.38 for trades left alone, and only 6 of 508 rows
    #    taught any management action at all.
    mgmt = [r for r in s4 if r.get("management_action")]
    checks.append((
        "management examples", len(mgmt) >= 60,
        f"{len(mgmt)} rows (need >=60)",
    ))

    # 9. Management must not be biased toward closing -- the distribution IS
    #    the lesson. Most review cycles should resolve to hold.
    actions = Counter(r.get("management_action") for r in mgmt)
    holds, closes = actions.get("hold", 0), actions.get("close", 1)
    checks.append((
        "management hold:close balance", holds >= closes,
        f"hold={holds} close={closes} protect={actions.get('protect', 0)} "
        f"(hold must not be outnumbered)",
    ))

    # 10. All four named close conditions from topic 10 must be taught.
    required_confirmations = {
        "thesis_invalidation_confirmed", "always_in_flip_confirmed",
        "reward_risk_inverted", "time_stop_expired",
    }
    present = {r.get("confirmation_type") for r in mgmt}
    missing = sorted(required_confirmations - present)
    checks.append((
        "all four close conditions taught", not missing,
        f"missing {missing}" if missing else "R1-R4 all present",
    ))

    # 11. Geometry sanity must stay clean after appends.
    bad_geo = 0
    for r in s4:
        sd = side(r.get("trade_decision", ""))
        e, sl, tp = r.get("entry_price", 0), r.get("sl_price", 0), r.get("tp_price", 0)
        if not e:
            continue
        if sd == "buy" and not (sl < e < tp):
            bad_geo += 1
        if sd == "sell" and not (tp < e < sl):
            bad_geo += 1
    checks.append(("geometry clean", bad_geo == 0, f"{bad_geo} bad rows"))

    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:34} {detail}")
    failed = [c for c in checks if not c[1]]
    print(f"\n  VERDICT: {'READY TO RETRAIN' if not failed else f'{len(failed)} GATE(S) FAILING'}")


if __name__ == "__main__":
    main()
