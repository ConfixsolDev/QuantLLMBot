"""Stage 5: acceptance gates for entry-contract promotion.

A prompt is production code. On 2026-08-10 contract v1.9 shipped with no test,
no comparison and no alarm; it zeroed the confidence distribution and halted
trading for 2h20m. Nothing blocked it because nothing was watching.

This module is the gate that edit should have had to pass. It compares a
candidate contract's decision distribution against a known-good baseline and
returns a pass/fail with per-check detail. It is deliberately distribution-based
rather than output-matching: two contracts need not agree decision by decision,
but a contract that stops producing tradeable decisions at all, or that suddenly
trades one direction only, has regressed regardless of its wording.

Retroactively, v1.9 fails GATE_READY_RATE and GATE_ZERO_CONFIDENCE outright.

Pure functions. Feed it decision samples from replay_decisions.py or from a
shadow run; it neither reads logs nor calls the model itself.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Iterable, Mapping, Sequence


GATE_VERSION = "5.0"

# Minimum sample before a verdict means anything.
MIN_SAMPLE = 40

# --- thresholds ------------------------------------------------------------
# Absolute floor on the share of decisions that reach ready while trading is
# permitted. v1.9 produced 0.0%.
MIN_READY_RATE = 0.02

# A candidate may not lose more than this share of the baseline's ready rate.
MAX_READY_RATE_DROP = 0.60

# Share of decisions returning zero confidence. v1.9 produced 100%.
MAX_ZERO_CONFIDENCE_SHARE = 0.25

# Mean confidence may not fall more than this many points below baseline.
MAX_MEAN_CONFIDENCE_DROP = 20.0

# Directional skew among ready decisions. 2026-08-10 ran 97.8% sell.
MAX_SIDE_SHARE = 0.85

# Contradictions (ready emitted with sub-threshold confidence) are never OK.
MAX_CONTRADICTION_SHARE = 0.0

# Latency guard: a contract that doubles inference cost is a regression even if
# its decisions are fine.
MAX_LATENCY_MULTIPLE = 1.75


class GateName:
    SAMPLE = "gate:sample_size"
    READY_RATE = "gate:ready_rate"
    READY_RATE_DROP = "gate:ready_rate_drop"
    ZERO_CONFIDENCE = "gate:zero_confidence_share"
    MEAN_CONFIDENCE = "gate:mean_confidence_drop"
    SIDE_BALANCE = "gate:side_balance"
    CONTRADICTION = "gate:contradiction_share"
    LATENCY = "gate:latency_multiple"


@dataclass(frozen=True)
class Sample:
    """One decision produced by a contract under evaluation."""

    confidence: int = 0
    status: str = "wait"          # "ready" | "wait"
    side: str | None = None       # "buy" | "sell"
    trade_permitted: bool = True
    latency_seconds: float | None = None
    model_said_ready: bool = False


@dataclass(frozen=True)
class Distribution:
    n: int = 0
    ready_rate: float = 0.0
    mean_confidence: float = 0.0
    zero_confidence_share: float = 0.0
    contradiction_share: float = 0.0
    dominant_side_share: float = 0.0
    dominant_side: str | None = None
    mean_latency: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str
    observed: float = 0.0
    threshold: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GateReport:
    passed: bool
    candidate_version: str
    baseline_version: str | None
    results: tuple[GateResult, ...] = ()
    candidate: Distribution = field(default_factory=Distribution)
    baseline: Distribution | None = None
    gate_version: str = GATE_VERSION

    @property
    def failures(self) -> tuple[GateResult, ...]:
        return tuple(r for r in self.results if not r.passed)

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "candidate_version": self.candidate_version,
            "baseline_version": self.baseline_version,
            "gate_version": self.gate_version,
            "candidate": self.candidate.as_dict(),
            "baseline": self.baseline.as_dict() if self.baseline else None,
            "results": [r.as_dict() for r in self.results],
        }


def summarise(samples: Sequence[Sample]) -> Distribution:
    """Reduce a decision stream to the distribution the gates operate on."""
    live = [s for s in samples if s.trade_permitted]
    if not live:
        return Distribution()
    n = len(live)
    confidences = [int(s.confidence or 0) for s in live]
    ready = [s for s in live if s.status == "ready"]
    sides = [s.side for s in ready if s.side in ("buy", "sell")]
    contradictions = sum(
        1 for s in live
        if s.model_said_ready and int(s.confidence or 0) < 51
    )
    latencies = [s.latency_seconds for s in live if s.latency_seconds]

    dominant_side, dominant_share = None, 0.0
    if sides:
        buys = sides.count("buy")
        share_buy = buys / len(sides)
        if share_buy >= 0.5:
            dominant_side, dominant_share = "buy", share_buy
        else:
            dominant_side, dominant_share = "sell", 1 - share_buy

    return Distribution(
        n=n,
        ready_rate=len(ready) / n,
        mean_confidence=sum(confidences) / n,
        zero_confidence_share=sum(1 for c in confidences if c <= 0) / n,
        contradiction_share=contradictions / n,
        dominant_side_share=dominant_share,
        dominant_side=dominant_side,
        mean_latency=(sum(latencies) / len(latencies)) if latencies else 0.0,
    )


def evaluate(
    candidate: Sequence[Sample],
    *,
    candidate_version: str,
    baseline: Sequence[Sample] | None = None,
    baseline_version: str | None = None,
    require_sample: bool = True,
) -> GateReport:
    """Run every gate against the candidate, comparing to baseline where given."""
    cand = summarise(candidate)
    base = summarise(baseline) if baseline else None
    results: list[GateResult] = []

    def add(name: str, passed: bool, detail: str, observed=0.0, threshold=0.0):
        results.append(GateResult(name, passed, detail, float(observed), float(threshold)))

    if require_sample:
        add(GateName.SAMPLE, cand.n >= MIN_SAMPLE,
            f"{cand.n} decisions (need {MIN_SAMPLE})", cand.n, MIN_SAMPLE)

    add(GateName.READY_RATE, cand.ready_rate >= MIN_READY_RATE,
        f"ready-rate {cand.ready_rate:.1%} (floor {MIN_READY_RATE:.1%})",
        cand.ready_rate, MIN_READY_RATE)

    add(GateName.ZERO_CONFIDENCE, cand.zero_confidence_share <= MAX_ZERO_CONFIDENCE_SHARE,
        f"zero-confidence {cand.zero_confidence_share:.1%} "
        f"(max {MAX_ZERO_CONFIDENCE_SHARE:.1%})",
        cand.zero_confidence_share, MAX_ZERO_CONFIDENCE_SHARE)

    add(GateName.CONTRADICTION, cand.contradiction_share <= MAX_CONTRADICTION_SHARE,
        f"ready-with-low-confidence {cand.contradiction_share:.1%} "
        f"(max {MAX_CONTRADICTION_SHARE:.1%})",
        cand.contradiction_share, MAX_CONTRADICTION_SHARE)

    if cand.dominant_side:
        add(GateName.SIDE_BALANCE, cand.dominant_side_share <= MAX_SIDE_SHARE,
            f"{cand.dominant_side} {cand.dominant_side_share:.1%} of ready "
            f"(max {MAX_SIDE_SHARE:.1%})",
            cand.dominant_side_share, MAX_SIDE_SHARE)

    if base and base.n >= MIN_SAMPLE:
        if base.ready_rate > 0:
            drop = 1 - (cand.ready_rate / base.ready_rate)
            add(GateName.READY_RATE_DROP, drop <= MAX_READY_RATE_DROP,
                f"ready-rate fell {drop:.0%} vs baseline "
                f"({base.ready_rate:.1%} -> {cand.ready_rate:.1%}), "
                f"max {MAX_READY_RATE_DROP:.0%}",
                drop, MAX_READY_RATE_DROP)
        confidence_drop = base.mean_confidence - cand.mean_confidence
        add(GateName.MEAN_CONFIDENCE, confidence_drop <= MAX_MEAN_CONFIDENCE_DROP,
            f"mean confidence {base.mean_confidence:.1f} -> {cand.mean_confidence:.1f} "
            f"(drop {confidence_drop:.1f}, max {MAX_MEAN_CONFIDENCE_DROP})",
            confidence_drop, MAX_MEAN_CONFIDENCE_DROP)
        if base.mean_latency > 0 and cand.mean_latency > 0:
            multiple = cand.mean_latency / base.mean_latency
            add(GateName.LATENCY, multiple <= MAX_LATENCY_MULTIPLE,
                f"latency {base.mean_latency:.1f}s -> {cand.mean_latency:.1f}s "
                f"({multiple:.2f}x, max {MAX_LATENCY_MULTIPLE}x)",
                multiple, MAX_LATENCY_MULTIPLE)

    return GateReport(
        passed=all(r.passed for r in results),
        candidate_version=candidate_version,
        baseline_version=baseline_version,
        results=tuple(results),
        candidate=cand,
        baseline=base,
    )


def should_rollback(recent: Sequence[Sample]) -> tuple[bool, str]:
    """Live guard: is the running contract producing a regression right now?

    Intended for the decision loop, so a bad promotion self-reverts in minutes
    rather than persisting for hours.
    """
    live = [s for s in recent if s.trade_permitted]
    if len(live) < 10:
        return False, "insufficient sample"
    zero_share = sum(1 for s in live if int(s.confidence or 0) <= 0) / len(live)
    if zero_share >= 0.90:
        return True, f"{zero_share:.0%} of the last {len(live)} decisions returned zero confidence"
    contradictions = sum(
        1 for s in live if s.model_said_ready and int(s.confidence or 0) < 51
    )
    if contradictions / len(live) >= 0.50:
        return True, (f"{contradictions}/{len(live)} decisions emitted ready with "
                      "sub-threshold confidence")
    return False, "healthy"


def format_report(report: GateReport) -> str:
    """Human-readable gate verdict."""
    lines = [
        f"CONTRACT GATE {report.gate_version} :: candidate {report.candidate_version}"
        + (f" vs baseline {report.baseline_version}" if report.baseline_version else ""),
        f"  VERDICT: {'PASS' if report.passed else 'FAIL'}",
    ]
    for result in report.results:
        lines.append(f"    [{'PASS' if result.passed else 'FAIL'}] {result.name:32} {result.detail}")
    return "\n".join(lines)
