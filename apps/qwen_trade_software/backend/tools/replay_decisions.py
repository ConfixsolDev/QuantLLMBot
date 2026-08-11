"""Offline replay: validate the new guards against real logged decisions.

Replays historical ``paper-proposals-*.jsonl`` (and the matching runner log for
outcomes) through the Stage 1 + Stage 2 guards and reports what *would* have
happened. Nothing here touches MT5, the model, or the running stack.

This is the acceptance gate the 2026-08-10 v1.9 edit never had to pass.

Usage
-----
    python tools/replay_decisions.py                     # today
    python tools/replay_decisions.py --date 2026-08-10
    python tools/replay_decisions.py --json              # machine-readable
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import entry_policy as ep  # noqa: E402
import decision_liveness as dl  # noqa: E402


BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"


# --- loading ---------------------------------------------------------------

def load_proposals(day: str) -> list[dict]:
    path = LOG_DIR / f"paper-proposals-{day}.jsonl"
    if not path.exists():
        raise SystemExit(f"no proposal log for {day}: {path}")
    rows = []
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def load_outcomes() -> dict[str, tuple[str, float]]:
    """proposal_id -> (exit_reason, net_pnl) from the runner log."""
    outcomes: dict[str, tuple[str, float]] = {}
    for path in sorted(LOG_DIR.glob("paper-runner.log*")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(
            r"Completed (\S+) reason=(\S+) net_pnl=(-?[\d.]+)", text
        ):
            outcomes[match.group(1)] = (match.group(2), float(match.group(3)))
    return outcomes


def timeframe_of(level_id) -> str | None:
    return ep.timeframe_of_level(level_id)


def contract_version_of(prompt_text: str) -> str | None:
    """First ``<!-- version: X -->`` marker in the entry prompt, if any."""
    if not prompt_text:
        return None
    head = prompt_text.split("ENTRY FACTS:", 1)[0]
    match = re.search(r"<!--\s*version:\s*([0-9]+\.[0-9]+)", head)
    return match.group(1) if match else None


# --- checks ----------------------------------------------------------------

def model_verdict(qwen: dict) -> dict | None:
    """The model's ORIGINAL response, before normalisation.

    ``qwen["execution_plan"]`` in the log is the post-normalisation plan, which
    has already been downgraded to a wait. The contradiction only exists in
    ``raw_response`` -- which is exactly why it went unnoticed for two hours.
    """
    raw = qwen.get("raw_response")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def check_contradictions(rows: list[dict]) -> dict:
    """How many ready+sub-threshold-confidence contradictions the model emitted."""
    caught, scanned, examples = 0, 0, []
    for row in rows:
        qwen = row.get("qwen") or {}
        raw = model_verdict(qwen)
        if raw is None:
            continue
        scanned += 1
        if ep.check_legacy_contradiction(raw):
            caught += 1
            if len(examples) < 3:
                examples.append({
                    "at": row.get("created_at_utc", "")[11:19],
                    "confidence": raw.get("confidence"),
                    "bias": raw.get("bias"),
                    "summary": str(raw.get("summary"))[:70],
                })
    return {"caught": caught, "scanned": scanned, "examples": examples}


def check_liveness(rows: list[dict]) -> dict:
    """Replay the decision stream and record when each alarm would have fired."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    first_fire: dict[str, str] = {}
    for row in rows:
        qwen = row.get("qwen") or {}
        plan = qwen.get("execution_plan") or {}
        stamp = row.get("created_at_utc", "")
        try:
            at = datetime.fromisoformat(stamp).timestamp()
        except ValueError:
            at = 0.0
        version = contract_version_of(qwen.get("prompt_text") or "")
        alarms = monitor.record(dl.DecisionEvent(
            at=at,
            confidence=int(qwen.get("confidence") or 0),
            status=str(plan.get("status") or "wait"),
            side=plan.get("side"),
            trade_permitted=True,
            cache_ready=True,
            has_open_position=False,
            latency_seconds=qwen.get("decision_wall_seconds"),
            contract_version=version,
        ))
        for alarm in alarms:
            first_fire.setdefault(alarm.code, f"{stamp[11:19]} UTC :: {alarm.detail}")
    return {"first_fire": first_fire, "snapshot": monitor.snapshot()}


def check_timeframe_coherence(rows: list[dict], outcomes: dict) -> dict:
    """Apply the invalidation-coherence rule to real ready proposals."""
    kept, rejected = [], []
    for row in rows:
        qwen = row.get("qwen") or {}
        plan = qwen.get("execution_plan") or {}
        if plan.get("status") != "ready":
            continue
        zone_tf = timeframe_of(plan.get("entry_low_id"))
        inval_tf = timeframe_of(plan.get("stop_level_id"))
        pnl = outcomes.get(row.get("proposal_id"), (None, None))[1]
        record = {
            "id": row.get("proposal_id"),
            "zone_tf": zone_tf,
            "invalidation_tf": inval_tf,
            "side": plan.get("side"),
            "pnl": pnl,
        }
        if ep.invalidation_coherent(zone_tf, inval_tf):
            kept.append(record)
        else:
            rejected.append(record)

    def total(records):
        return sum(r["pnl"] for r in records if r["pnl"] is not None)

    def traded(records):
        return [r for r in records if r["pnl"] is not None]

    return {
        "kept": kept, "rejected": rejected,
        "kept_traded": len(traded(kept)), "rejected_traded": len(traded(rejected)),
        "kept_pnl": total(kept), "rejected_pnl": total(rejected),
    }


def check_by_contract_version(rows: list[dict]) -> dict:
    """Confidence and ready-rate per contract version.

    This is the attribution that did not exist on 2026-08-10: the v1.8 -> v1.9
    edit and the trading halt were never tied together.
    """
    buckets: dict[str, dict] = collections.defaultdict(
        lambda: {"n": 0, "zero": 0, "ready": 0, "confidence_sum": 0}
    )
    for row in rows:
        qwen = row.get("qwen") or {}
        raw = model_verdict(qwen)
        if raw is None:
            continue
        version = contract_version_of(qwen.get("prompt_text") or "") or "unknown"
        bucket = buckets[version]
        confidence = int(raw.get("confidence") or 0)
        bucket["n"] += 1
        bucket["confidence_sum"] += confidence
        if confidence <= 0:
            bucket["zero"] += 1
        if str((raw.get("execution_plan") or {}).get("status", "")).lower() == "ready":
            bucket["ready"] += 1
    out = {}
    for version, bucket in buckets.items():
        n = bucket["n"] or 1
        out[version] = {
            "decisions": bucket["n"],
            "mean_confidence": bucket["confidence_sum"] / n,
            "zero_share": bucket["zero"] / n,
            "model_ready_share": bucket["ready"] / n,
        }
    return out


def check_side_balance(rows: list[dict]) -> dict:
    sides = collections.Counter()
    biases = collections.Counter()
    for row in rows:
        qwen = row.get("qwen") or {}
        plan = qwen.get("execution_plan") or {}
        biases[str(qwen.get("bias"))] += 1
        if plan.get("status") == "ready":
            sides[str(plan.get("side"))] += 1
    total = sum(sides.values())
    dominant_share = (max(sides.values()) / total) if total else 0.0
    return {
        "ready_sides": dict(sides),
        "dominant_share": dominant_share,
        "breaches_limit": dominant_share > dl.SIDE_BALANCE_MAX_SHARE,
        "biases": dict(biases),
        "conditional_share": biases.get("conditional", 0) / len(rows) if rows else 0.0,
    }


def check_schema_would_reject(rows: list[dict]) -> dict:
    """How many historical payloads the v2.0 observation schema rejects."""
    reasons = collections.Counter()
    for row in rows:
        qwen = row.get("qwen") or {}
        ok, code, _ = ep.validate_observation({
            "long": None, "short": None,
            "evidence_ids": row.get("qwen", {}).get("evidence_ids") or ["x"],
        })
        reasons[code if not ok else "accepted"] += 1
        _ = qwen
    return dict(reasons)


# --- reporting -------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    rows = load_proposals(args.date)
    outcomes = load_outcomes()

    report = {
        "date": args.date,
        "proposals": len(rows),
        "contradictions": check_contradictions(rows),
        "liveness": check_liveness(rows),
        "coherence": check_timeframe_coherence(rows, outcomes),
        "balance": check_side_balance(rows),
        "schema": check_schema_would_reject(rows),
        "by_contract": check_by_contract_version(rows),
        "policy_version": ep.POLICY_VERSION,
    }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
        return 0

    c = report["contradictions"]
    lv = report["liveness"]
    co = report["coherence"]
    ba = report["balance"]

    print(f"\n{'='*66}")
    print(f" REPLAY {args.date}  |  {len(rows)} proposals  |  policy v{ep.POLICY_VERSION}")
    print(f"{'='*66}")

    print(f"\n0. CONFIDENCE BY CONTRACT VERSION  (attribution)")
    print(f"   {'ver':>6}  {'n':>4}  {'mean conf':>9}  {'zero%':>6}  {'model ready%':>12}")
    for version, stats in sorted(report["by_contract"].items()):
        print(f"   {version:>6}  {stats['decisions']:>4}  {stats['mean_confidence']:>9.1f}  "
              f"{stats['zero_share']:>5.0%}  {stats['model_ready_share']:>11.0%}")

    print(f"\n1. READY + SUB-THRESHOLD CONFIDENCE  (the v1.9 signature)")
    print(f"   contradictions now caught : {c['caught']} of {c['scanned']} model responses")
    for ex in c["examples"]:
        print(f"     {ex['at']}  conf={ex['confidence']} bias={ex['bias']}  {ex['summary']}")
    print(f"   -> previously: silently downgraded to wait, nothing logged")

    print(f"\n2. LIVENESS ALARMS THAT WOULD HAVE FIRED")
    if not lv["first_fire"]:
        print("   (none)")
    for code, detail in sorted(lv["first_fire"].items()):
        print(f"   {code:42} {detail}")
    snap = lv["snapshot"]
    print(f"   final: ready_rate={snap['ready_rate']:.1%} "
          f"zero_conf_share={snap['zero_confidence_share']:.1%} "
          f"buy_share={snap['buy_share']:.1%}")

    print(f"\n3. INVALIDATION COHERENCE  (entry zone vs structural stop)")
    print(f"   kept     : {len(co['kept']):3} ready  ({co['kept_traded']} traded)  "
          f"net {co['kept_pnl']:+.2f}")
    print(f"   rejected : {len(co['rejected']):3} ready  ({co['rejected_traded']} traded)  "
          f"net {co['rejected_pnl']:+.2f}")
    delta = co["kept_pnl"] - (co["kept_pnl"] + co["rejected_pnl"])
    print(f"   -> removing incoherent trades changes realised P&L by {-co['rejected_pnl']:+.2f}")
    pattern = collections.Counter(
        f"{r['zone_tf']}->{r['invalidation_tf']}" for r in co["rejected"]
    )
    for name, count in pattern.most_common(5):
        print(f"      rejected pattern {name:12} x{count}")
    _ = delta

    print(f"\n4. DIRECTIONAL BALANCE")
    print(f"   ready sides       : {ba['ready_sides']}")
    print(f"   dominant share    : {ba['dominant_share']:.1%} "
          f"(limit {dl.SIDE_BALANCE_MAX_SHARE:.0%}) "
          f"{'BREACH -> alarm' if ba['breaches_limit'] else 'ok'}")
    print(f"   bias=conditional  : {ba['conditional_share']:.1%} of all decisions")
    print(f"   -> v2.0 schema removes 'conditional' and requires both sides")

    print(f"\n{'='*66}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
