"""Liveness and distribution invariants for the entry-decision loop.

2026-08-10: the system produced no ready proposal for 2h20m while the market was
open, the cache was ready, London was in session and Qwen was answering normally
in ~16s. Nothing alarmed, because nothing in the system held an opinion about
what a *healthy* decision stream looks like.

This module holds those opinions. Each check describes a state that should be
impossible; if one is observed, it is an incident, not a log line.

Design notes
------------
* Pure and in-memory. No I/O, no MT5, no model calls -- so it is unit-testable
  and cheap to call on every decision.
* Emits structured ``Alarm`` records with stable codes so occurrences can be
  counted and grouped rather than read.
* The caller owns delivery (log, dashboard, notification). This module only
  decides *whether* something is wrong.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Deque, Iterable


# --- thresholds -------------------------------------------------------------
# A zero-confidence run this long is the v1.9 signature. On 2026-08-10 the run
# reached 72 before a human noticed.
ZERO_CONFIDENCE_STREAK_ALARM = 5

# No proposal at all while trading is permitted. The silent stall on 2026-08-10
# ran 61.6 minutes (07:00:33 -> 08:02:12 UTC) with nothing logged.
PROPOSAL_STALL_SECONDS = 600

# Market open, cache ready, flat, and yet nothing ready to trade.
NO_READY_PROPOSAL_SECONDS = 1800

# Ready-rate collapse detection over a rolling window.
READY_RATE_WINDOW = 60
READY_RATE_FLOOR = 0.01

# Side imbalance. 2026-08-10 ran 97.8% sell across ready proposals.
SIDE_BALANCE_WINDOW = 50
SIDE_BALANCE_MAX_SHARE = 0.80

# Model latency vs the 30s decision interval. Sustained latency above the loop
# interval means proposals arrive near-stale against the 60s freshness window.
LATENCY_WINDOW = 20
LATENCY_WARN_SECONDS = 25.0


class AlarmCode:
    ZERO_CONFIDENCE_STREAK = "liveness:zero_confidence_streak"
    PROPOSAL_STALL = "liveness:proposal_stall"
    NO_READY_PROPOSAL = "liveness:no_ready_proposal"
    READY_RATE_COLLAPSE = "liveness:ready_rate_collapse"
    SIDE_IMBALANCE = "liveness:side_imbalance"
    READY_WITH_LOW_CONFIDENCE = "liveness:ready_with_low_confidence"
    MODEL_LATENCY_HIGH = "liveness:model_latency_high"
    CONTRACT_VERSION_CHANGED = "liveness:contract_version_changed"


SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING = "warning"


@dataclass(frozen=True)
class Alarm:
    code: str
    severity: str
    detail: str
    observed_at: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionEvent:
    """One pass of the entry-decision loop."""

    at: float
    confidence: int = 0
    status: str = "wait"          # "ready" | "wait"
    side: str | None = None       # "buy" | "sell"
    trade_permitted: bool = False
    cache_ready: bool = False
    has_open_position: bool = False
    latency_seconds: float | None = None
    contract_version: str | None = None


class DecisionLivenessMonitor:
    """Rolling health view of the decision stream."""

    def __init__(self, *, now: float | None = None) -> None:
        started = now if now is not None else time.time()
        self._events: Deque[DecisionEvent] = deque(maxlen=max(READY_RATE_WINDOW, SIDE_BALANCE_WINDOW) * 4)
        self._latencies: Deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._ready_sides: Deque[str] = deque(maxlen=SIDE_BALANCE_WINDOW)
        self._zero_streak = 0
        self._last_proposal_at = started
        self._last_ready_at = started
        self._contract_version: str | None = None
        self._fired: set[str] = set()

    # -- ingestion ----------------------------------------------------------
    def record(self, event: DecisionEvent) -> list[Alarm]:
        """Record one decision and return any alarms it triggers."""
        self._events.append(event)
        self._last_proposal_at = event.at

        if event.latency_seconds is not None:
            self._latencies.append(float(event.latency_seconds))

        if event.confidence <= 0:
            self._zero_streak += 1
        else:
            self._zero_streak = 0
            self._clear(AlarmCode.ZERO_CONFIDENCE_STREAK)

        if event.status == "ready":
            self._last_ready_at = event.at
            if event.side in ("buy", "sell"):
                self._ready_sides.append(event.side)
            self._clear(AlarmCode.NO_READY_PROPOSAL)
            self._clear(AlarmCode.READY_RATE_COLLAPSE)

        alarms: list[Alarm] = []
        alarms.extend(self._check_contract_version(event))
        alarms.extend(self._check_contradiction(event))
        alarms.extend(self._check_zero_streak(event))
        alarms.extend(self._check_ready_rate(event))
        alarms.extend(self._check_side_balance(event))
        alarms.extend(self._check_latency(event))
        return alarms

    def check_time_based(self, now: float, *, trade_permitted: bool,
                         cache_ready: bool, has_open_position: bool) -> list[Alarm]:
        """Alarms that depend on elapsed time rather than a new decision.

        Must be called even when no decision is produced -- that is exactly the
        failure being guarded against.
        """
        alarms: list[Alarm] = []
        if trade_permitted:
            stalled = now - self._last_proposal_at
            if stalled >= PROPOSAL_STALL_SECONDS:
                alarms.extend(self._fire(
                    AlarmCode.PROPOSAL_STALL, SEVERITY_CRITICAL, now,
                    f"no decision produced for {stalled/60:.1f} min while trading permitted",
                ))
        if trade_permitted and cache_ready and not has_open_position:
            idle = now - self._last_ready_at
            if idle >= NO_READY_PROPOSAL_SECONDS:
                alarms.extend(self._fire(
                    AlarmCode.NO_READY_PROPOSAL, SEVERITY_CRITICAL, now,
                    f"market open, cache ready, flat, but nothing ready for {idle/60:.1f} min",
                ))
        return alarms

    # -- individual checks --------------------------------------------------
    def _check_contradiction(self, event: DecisionEvent) -> list[Alarm]:
        """status=ready with sub-threshold confidence. Occurred 72x on 2026-08-10."""
        if event.status == "ready" and event.confidence <= 0:
            return self._fire(
                AlarmCode.READY_WITH_LOW_CONFIDENCE, SEVERITY_CRITICAL, event.at,
                "decision marked ready while reporting zero confidence",
                repeatable=True,
            )
        return []

    def _check_zero_streak(self, event: DecisionEvent) -> list[Alarm]:
        if self._zero_streak >= ZERO_CONFIDENCE_STREAK_ALARM:
            return self._fire(
                AlarmCode.ZERO_CONFIDENCE_STREAK, SEVERITY_CRITICAL, event.at,
                f"{self._zero_streak} consecutive zero-confidence decisions; "
                "suspect a contract regression -- consider rollback",
            )
        return []

    def _check_ready_rate(self, event: DecisionEvent) -> list[Alarm]:
        window = list(self._events)[-READY_RATE_WINDOW:]
        if len(window) < READY_RATE_WINDOW:
            return []
        if not any(e.trade_permitted for e in window):
            return []
        rate = sum(1 for e in window if e.status == "ready") / len(window)
        if rate <= READY_RATE_FLOOR:
            return self._fire(
                AlarmCode.READY_RATE_COLLAPSE, SEVERITY_CRITICAL, event.at,
                f"ready-rate {rate:.1%} over last {len(window)} decisions while trading permitted",
            )
        return []

    def _check_side_balance(self, event: DecisionEvent) -> list[Alarm]:
        if len(self._ready_sides) < SIDE_BALANCE_WINDOW:
            return []
        buys = self._ready_sides.count("buy")
        share_buy = buys / len(self._ready_sides)
        share = max(share_buy, 1 - share_buy)
        if share > SIDE_BALANCE_MAX_SHARE:
            dominant = "buy" if share_buy >= 0.5 else "sell"
            return self._fire(
                AlarmCode.SIDE_IMBALANCE, SEVERITY_WARNING, event.at,
                f"{dominant} is {share:.0%} of last {len(self._ready_sides)} ready entries",
            )
        return []

    def _check_latency(self, event: DecisionEvent) -> list[Alarm]:
        if len(self._latencies) < LATENCY_WINDOW:
            return []
        mean = sum(self._latencies) / len(self._latencies)
        if mean >= LATENCY_WARN_SECONDS:
            return self._fire(
                AlarmCode.MODEL_LATENCY_HIGH, SEVERITY_WARNING, event.at,
                f"mean model latency {mean:.1f}s over last {len(self._latencies)} decisions",
            )
        return []

    def _check_contract_version(self, event: DecisionEvent) -> list[Alarm]:
        """Attribute behaviour shifts to the version that caused them."""
        version = event.contract_version
        if not version:
            return []
        if self._contract_version is None:
            self._contract_version = version
            return []
        if version != self._contract_version:
            previous, self._contract_version = self._contract_version, version
            self._fired.discard(AlarmCode.ZERO_CONFIDENCE_STREAK)
            self._fired.discard(AlarmCode.READY_RATE_COLLAPSE)
            return self._fire(
                AlarmCode.CONTRACT_VERSION_CHANGED, SEVERITY_WARNING, event.at,
                f"entry contract changed {previous} -> {version}; watching for distribution shift",
                repeatable=True,
            )
        return []

    # -- helpers ------------------------------------------------------------
    def _fire(self, code: str, severity: str, at: float, detail: str,
              *, repeatable: bool = False) -> list[Alarm]:
        """Emit once per condition unless repeatable, to avoid alarm spam."""
        if not repeatable:
            if code in self._fired:
                return []
            self._fired.add(code)
        return [Alarm(code=code, severity=severity, detail=detail, observed_at=at)]

    def _clear(self, code: str) -> None:
        self._fired.discard(code)

    # -- introspection ------------------------------------------------------
    def snapshot(self) -> dict:
        window = list(self._events)[-READY_RATE_WINDOW:]
        ready = sum(1 for e in window if e.status == "ready")
        confidences = [e.confidence for e in window]
        buys = self._ready_sides.count("buy")
        return {
            "decisions_seen": len(self._events),
            "zero_confidence_streak": self._zero_streak,
            "ready_rate": (ready / len(window)) if window else 0.0,
            "mean_confidence": (sum(confidences) / len(confidences)) if confidences else 0.0,
            "zero_confidence_share": (
                sum(1 for c in confidences if c <= 0) / len(confidences) if confidences else 0.0
            ),
            "ready_sides_window": len(self._ready_sides),
            "buy_share": (buys / len(self._ready_sides)) if self._ready_sides else 0.0,
            "mean_latency_seconds": (
                sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
            ),
            "contract_version": self._contract_version,
            "seconds_since_last_ready": max(0.0, time.time() - self._last_ready_at),
        }


def format_alarm(alarm: Alarm) -> str:
    """Single-line, greppable rendering for the logs."""
    return f"ALARM {alarm.severity.upper()} {alarm.code} :: {alarm.detail}"
