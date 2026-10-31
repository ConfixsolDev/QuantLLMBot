"""Why the system is or is not trading, in one object the screen can render.

The planner screen showed plans, ideas and hour validation -- but nothing about
what happened when an idea actually tried to become a trade. On 2026-08-11 that
mattered: 9 entries were attempted, 7 were refused, and the only way to discover
that was to read paper-runner.log by hand.

    proposals ──▶ ready ──▶ entry attempted ──▶ filled ──▶ closed
                    │              │
                    │              └── refused: geometry:reward_risk_too_low x6
                    └── blocked: confidence below 51, cache not ready, cooldown

Every stage reports a count and, more importantly, the REASON the drop happened.
"No trade today" is not an answer; "6 refused because the target was below the
D1 minimum" is.

Pure reads of the log/jsonl artifacts already on disk. No MT5, no model call.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path


FUNNEL_VERSION = "1.0"

# Refusal codes rendered with friendlier wording for the screen. The raw code is
# always kept alongside so the log stays greppable.
REASON_LABEL = {
    "geometry:reward_risk_too_low": "Reward too small for the risk",
    "geometry:stop_too_wide": "Stop wider than the cap",
    "geometry:stop_too_tight": "Stop tighter than the frame minimum",
    "geometry:target_wrong_side": "Target on the wrong side of entry",
    "geometry:invalidation_wrong_side": "Invalidation on the wrong side of entry",
    "geometry:size_below_minimum": "Position size below the broker minimum",
    "invariant:ready_with_zero_confidence": "Model said ready but scored 0",
    "entry:ready_below_threshold": "Confidence below the entry threshold",
    "invariant:ready_contradicts_own_reason": "Ready, but its own reason says no trigger",
    "entry:provenance_failed": "Cache provenance check failed",
}


@dataclass
class FunnelStage:
    name: str
    count: int = 0
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ExecutionFunnel:
    stages: list = field(default_factory=list)
    blockers: list = field(default_factory=list)
    headline: str = ""
    net_pnl: float | None = None
    closed_trades: int = 0
    wins: int = 0
    version: str = FUNNEL_VERSION

    def as_dict(self) -> dict:
        return {
            "stages": [s.as_dict() for s in self.stages],
            "blockers": self.blockers,
            "headline": self.headline,
            "net_pnl": self.net_pnl,
            "closed_trades": self.closed_trades,
            "wins": self.wins,
            "version": self.version,
        }


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def _read_lines(path: Path, prefix: str) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    return "\n".join(line for line in text.splitlines() if line.startswith(prefix))


def _count_proposals(log_dir: Path, day: str) -> tuple[int, int, Counter]:
    """Proposals written today, how many reached ready, and why the rest waited."""
    path = log_dir / f"paper-proposals-{day}.jsonl"
    total = ready = 0
    waits: Counter = Counter()
    try:
        handle = path.open(encoding="utf-8", errors="ignore")
    except OSError:
        return 0, 0, waits
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            plan = ((row.get("qwen") or {}).get("execution_plan") or {})
            if plan.get("status") == "ready":
                ready += 1
            else:
                reason = str(plan.get("reason") or "no reason given")
                waits[reason[:70]] += 1
    return total, ready, waits


def build_funnel(log_dir: Path | str, day: str | None = None,
                 now: datetime | None = None) -> ExecutionFunnel:
    """Assemble the funnel from artifacts already on disk."""
    log_dir = Path(log_dir)
    day = day or _today(now)
    runner = _read_lines(log_dir / "paper-runner.log", day.replace("-", "-"))

    total, ready, waits = _count_proposals(log_dir, day)
    attempted = runner.count("Starting validated proposal")
    refused_codes = Counter(
        re.findall(r"entry refused by structural geometry: (\S+)", runner)
    )
    filled = runner.count("structural bracket:") + runner.count("fixed_3_5")
    pnl = [float(x) for x in re.findall(r"net_pnl=(-?[0-9.]+)", runner)]

    stages = [
        FunnelStage("Proposals", total, "entry decisions produced"),
        FunnelStage("Ready", ready, "cleared confidence and validation"),
        FunnelStage("Entry attempted", attempted, "sent to the executor"),
        FunnelStage("Filled", filled, "bracket placed at the broker"),
        FunnelStage("Closed", len(pnl), "trades with a realised result"),
    ]

    blockers = []
    for code, count in refused_codes.most_common(4):
        blockers.append({
            "stage": "Entry attempted",
            "code": code,
            "label": REASON_LABEL.get(code, code),
            "count": count,
        })
    for reason, count in waits.most_common(3):
        blockers.append({
            "stage": "Proposals",
            "code": "wait",
            "label": reason,
            "count": count,
        })

    # The headline names the single biggest drop, because that is the thing to
    # act on. Counting is not the point; attribution is.
    if len(pnl):
        net = sum(pnl)
        wins = sum(1 for p in pnl if p > 0)
        headline = (
            f"{len(pnl)} trade{'s' if len(pnl) != 1 else ''} closed · "
            f"{wins}W/{len(pnl) - wins}L · net {net:+.2f}"
        )
    elif refused_codes:
        code, count = refused_codes.most_common(1)[0]
        headline = (
            f"No trades — {count} refused at entry: "
            f"{REASON_LABEL.get(code, code)}"
        )
    elif ready == 0 and total:
        reason = waits.most_common(1)[0][0] if waits else "no setup cleared the bar"
        headline = f"No trades — nothing reached ready ({reason})"
    elif total == 0:
        headline = "No entry decisions produced yet"
    else:
        headline = "Waiting — ready setups but no entry taken yet"

    return ExecutionFunnel(
        stages=stages,
        blockers=blockers,
        headline=headline,
        net_pnl=round(sum(pnl), 2) if pnl else None,
        closed_trades=len(pnl),
        wins=sum(1 for p in pnl if p > 0),
    )
