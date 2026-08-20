#!/usr/bin/env python3
"""Read-only audit of stage_01–05 curriculum and deployed-contract alignment."""

from __future__ import annotations

import json
import re
import sys
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
    s5 = load("stage_05_live_contract.jsonl")

    print("=== COUNTS ===")
    print(
        f"principles={len(s1)} examples={len(s2)} detectors={len(s3)} "
        f"contracts={len(s4)} live_contracts={len(s5)}"
    )
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

    failures = readiness(s4) + live_contract_readiness(s2, s4, s5)
    print(f"\n  FINAL VERDICT: {'READY TO RETRAIN' if not failures else f'{len(failures)} GATE(S) FAILING'}")
    if failures:
        raise SystemExit(1)


def readiness(s4: list[dict]) -> list[str]:
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
    return [c[0] for c in failed]


def live_contract_readiness(s2: list[dict], s4: list[dict], s5: list[dict]) -> list[str]:
    """Validate stage_05 against current reviewer/manager schemas and clock facts."""
    print("\n=== LIVE CONTRACT READINESS ===")
    checks: list[tuple[str, bool, str]] = []
    source_ids = [r["example_id"] for r in s4]
    s5_source_ids = [r.get("source_example_id") for r in s5]
    checks.append((
        "one live row per decision row",
        len(s2) == len(s4) == len(s5) and source_ids == s5_source_ids,
        f"stage02={len(s2)} stage04={len(s4)} stage05={len(s5)} ordered={source_ids == s5_source_ids}",
    ))

    entry = [r for r in s5 if r.get("role") == "live_contract"]
    management = [r for r in s5 if r.get("role") == "management"]
    checks.append((
        "current prompt contract versions",
        bool(entry) and bool(management)
        and all(r.get("contract_version") == "qwen_cached_entry:1.20" for r in entry)
        and all(r.get("contract_version") == "qwen_trade_management:2.5" for r in management),
        f"entry={len(entry)} management={len(management)}",
    ))

    entry_keys = {"bias", "confidence", "summary", "acknowledged_epochs", "evidence_ids", "execution_plan"}
    plan_ready = {
        "status", "side", "entry_low_id", "entry_high_id", "stop_level_id",
        "target_level_id", "target_mode", "volume_each", "reason",
    }
    plan_wait = {"status", "reason"}
    bad_entry = []
    for row in entry:
        out = row.get("expected_response") or {}
        plan = out.get("execution_plan") or {}
        expected_plan_keys = plan_ready if plan.get("status") == "ready" else plan_wait
        facts = row.get("prompt_facts") or {}
        level_ids = {x.get("id") for x in facts.get("execution_levels", [])}
        evidence_enum = set(facts.get("citeable_evidence_ids") or ["__no_evidence__"])
        valid_geometry = all(plan.get(k) in level_ids for k in (
            "entry_low_id", "entry_high_id", "stop_level_id", "target_level_id"
        )) if plan.get("status") == "ready" else True
        requests = out.get("data_requests") or []
        request_ok = len(requests) <= 2 and all(
            set(req) == {"tool", "symbol", "timeframe", "count", "missing_fact", "why_needed"}
            and req["tool"] in {"get_completed_candles", "get_structure_state", "get_structure_events", "get_dxy_state"}
            and 1 <= req["count"] <= 80 for req in requests
        )
        if not (
            frozenset(out) in {frozenset(entry_keys), frozenset(entry_keys | {"data_requests"})}
            and out.get("bias") in {"buy", "sell", "wait"}
            and isinstance(out.get("confidence"), int) and 1 <= out["confidence"] <= 100
            and 1 <= len(out.get("evidence_ids") or []) <= 6
            and set(out.get("evidence_ids") or []) <= evidence_enum
            and set(plan) == expected_plan_keys
            and plan.get("status") in {"ready", "wait"}
            and (plan.get("target_mode") in {"scalp", "starter_basket", "directional_basket"}
                 if plan.get("status") == "ready" else True)
            and valid_geometry
            and request_ok
            and (not requests or plan.get("status") == "wait")
        ):
            bad_entry.append(row.get("example_id"))
    checks.append(("entry schema exact", not bad_entry, f"{len(bad_entry)} offenders {bad_entry[:5]}"))

    mgmt_keys = {
        "action", "thesis_state", "decision_level_ref", "next_target_ref",
        "confirmation_type", "confirmation_evidence_ids", "close_confirmed",
        "regime_assessment", "summary",
    }
    confirmations = {
        "none", "target_rejection_confirmed", "thesis_invalidation_confirmed",
        "momentum_reversal_confirmed", "continuation_acceptance_confirmed",
        "always_in_flip_confirmed", "reward_risk_inverted", "time_stop_expired",
        "protected_profit_exit",
    }
    bad_mgmt = []
    for row in management:
        out = row.get("expected_response") or {}
        refs = set((row.get("prompt_facts") or {}).get("level_references") or {})
        nullable_refs_ok = all(out.get(k) is None or out.get(k) in refs for k in ("decision_level_ref", "next_target_ref"))
        if not (
            set(out) == mgmt_keys
            and out.get("action") in {"hold", "protect", "close"}
            and out.get("thesis_state") in {"valid", "weakening", "invalidated", "target_response"}
            and out.get("confirmation_type") in confirmations
            and out.get("regime_assessment") in {None, "range", "trend", "breakout", "exhaustion", "unknown"}
            and nullable_refs_ok
        ):
            bad_mgmt.append(row.get("example_id"))
    checks.append(("management schema exact", not bad_mgmt, f"{len(bad_mgmt)} offenders {bad_mgmt[:5]}"))

    bad_clock = []
    expected_frames = {"M15", "M30", "H1", "H4"}
    for row in s5:
        clock = (row.get("prompt_facts") or {}).get("candle_clock") or {}
        frames = clock.get("frames") or {}
        arithmetic_ok = all(
            isinstance(v.get("elapsed_seconds"), int)
            and isinstance(v.get("remaining_seconds"), int)
            and v["elapsed_seconds"] + v["remaining_seconds"] == {"M15": 900, "M30": 1800, "H1": 3600, "H4": 14400}[tf]
            and v.get("phase") in {"opening_transition", "middle", "closing_transition"}
            for tf, v in frames.items() if tf in expected_frames
        )
        if not (
            set(frames) == expected_frames and arithmetic_ok
            and clock.get("close_hierarchy") == "M15 builds M30; M30 builds H1; H1 builds H4"
        ):
            bad_clock.append(row.get("example_id"))
    checks.append(("nested candle clock exact", not bad_clock, f"{len(bad_clock)} offenders {bad_clock[:5]}"))

    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name:34} {detail}")
    return [name for name, passed, _ in checks if not passed]


if __name__ == "__main__":
    main()
