"""Stage 6 bootstrap: build the initial configuration ledger from real trades.

Reads closed trades out of the runner log, joins them to their proposals to
recover the configuration that produced each one, feeds them through
configuration_ledger.py and writes the result to logs/configuration-ledger.json.

Also runs the Stage 5 contract gate over the same day so the v1.9 promotion can
be re-tested against the gate that did not exist when it shipped.

Usage
-----
    python tools/bootstrap_ledger.py                  # today
    python tools/bootstrap_ledger.py --date 2026-08-10
    python tools/bootstrap_ledger.py --dry-run        # do not write the ledger
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import configuration_ledger as cl   # noqa: E402
import contract_gate as cg          # noqa: E402
import entry_policy as ep           # noqa: E402


BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"
LEDGER_PATH = LOG_DIR / "configuration-ledger.json"


def load_proposals(day: str) -> dict[str, dict]:
    path = LOG_DIR / f"paper-proposals-{day}.jsonl"
    if not path.exists():
        raise SystemExit(f"no proposal log for {day}")
    rows = {}
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("proposal_id"):
                rows[row["proposal_id"]] = row
    return rows


def load_outcomes() -> dict[str, tuple[str, float]]:
    outcomes = {}
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


def to_trade_record(proposal: dict, exit_reason: str, pnl: float) -> cl.TradeRecord:
    qwen = proposal.get("qwen") or {}
    plan = qwen.get("execution_plan") or {}
    market = proposal.get("market") or {}
    cache = market.get("cache_context") or {}
    session = cache.get("session")
    if isinstance(session, dict):
        session = session.get("session")
    return cl.TradeRecord(
        frame=plan.get("structure_timeframe"),
        side=plan.get("side"),
        session=session or "unknown",
        trigger_tf=ep.timeframe_of_level(plan.get("entry_low_id")),
        geometry_source=plan.get("geometry_source"),
        pnl=pnl,
        exit_reason=exit_reason,
    )


def build_gate_samples(proposals: dict[str, dict], version: str) -> list[cg.Sample]:
    """Decision samples for one contract version, taken from raw model output."""
    out = []
    for row in proposals.values():
        qwen = row.get("qwen") or {}
        prompt = qwen.get("prompt_text") or ""
        head = prompt.split("ENTRY FACTS:", 1)[0]
        match = re.search(r"<!--\s*version:\s*([0-9]+\.[0-9]+)", head)
        if not match or match.group(1) != version:
            continue
        try:
            raw = json.loads(qwen.get("raw_response") or "")
        except (json.JSONDecodeError, TypeError):
            continue
        model_ready = str(
            (raw.get("execution_plan") or {}).get("status", "")
        ).lower() == "ready"
        confidence = int(raw.get("confidence") or 0)
        out.append(cg.Sample(
            confidence=confidence,
            status="ready" if (model_ready and confidence >= 51) else "wait",
            side=(raw.get("execution_plan") or {}).get("side") or raw.get("bias"),
            trade_permitted=True,
            latency_seconds=qwen.get("decision_wall_seconds"),
            model_said_ready=model_ready,
        ))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    proposals = load_proposals(args.date)
    outcomes = load_outcomes()

    trades = []
    for proposal_id, (exit_reason, pnl) in outcomes.items():
        proposal = proposals.get(proposal_id)
        if proposal:
            trades.append(to_trade_record(proposal, exit_reason, pnl))

    if not trades:
        print(f"no closed trades found for {args.date}")
        return 1

    ledger = cl.ConfigurationLedger.load(LEDGER_PATH)
    ledger.record_all(trades)

    print("=" * 78)
    print(f" CONFIGURATION LEDGER BOOTSTRAP  {args.date}  ({len(trades)} closed trades)")
    print("=" * 78)
    print()
    print(cl.format_ledger(ledger))
    print()

    blocked = [s for s in ledger.configurations().values() if s.state == cl.State.DEMOTED]
    if blocked:
        print("DEMOTED -- these configurations are now blocked from trading:")
        for stats in blocked:
            print(f"   {stats.key}")
            print(f"      n={stats.sample} expectancy={stats.expectancy:+.2f} "
                  f"win={stats.win_rate:.0%} net={stats.net_pnl:+.2f}")
            if stats.history:
                print(f"      reason: {stats.history[-1]['why']}")
        avoided = sum(s.net_pnl for s in blocked)
        print(f"\n   combined realised P&L of demoted configurations: {avoided:+.2f}")
    else:
        print("no configuration met the demotion threshold yet")

    # --- Stage 5: re-test the v1.9 promotion against the gate ---------------
    print()
    print("=" * 78)
    print(" CONTRACT GATE -- retroactive test of the 2026-08-10 promotion")
    print("=" * 78)
    baseline = build_gate_samples(proposals, "1.3")
    candidate = build_gate_samples(proposals, "1.9")
    if baseline and candidate:
        report = cg.evaluate(candidate, candidate_version="1.9",
                             baseline=baseline, baseline_version="1.3")
        print(cg.format_report(report))
        print()
        print(f"   -> v1.9 would have been {'PROMOTED' if report.passed else 'BLOCKED'}"
              " by this gate")
    else:
        print(f"   insufficient samples (baseline={len(baseline)}, candidate={len(candidate)})")

    if not args.dry_run:
        ledger.save(LEDGER_PATH)
        print()
        print(f"ledger written to {LEDGER_PATH}")
    else:
        print("\n(dry run -- ledger not written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
