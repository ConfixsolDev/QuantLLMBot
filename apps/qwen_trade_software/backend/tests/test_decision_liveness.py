"""Tests for the liveness invariants.

Every test here corresponds to something that went unnoticed on 2026-08-10.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decision_liveness as dl  # noqa: E402


def event(**kw):
    base = dict(
        at=1000.0, confidence=70, status="wait", side=None,
        trade_permitted=True, cache_ready=True, has_open_position=False,
        latency_seconds=16.0, contract_version="1.10",
    )
    base.update(kw)
    return dl.DecisionEvent(**base)


def codes(alarms):
    return {a.code for a in alarms}


def test_zero_confidence_streak_alarms():
    """72 consecutive zero-confidence decisions passed unnoticed for 2h20m."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    fired = set()
    for i in range(dl.ZERO_CONFIDENCE_STREAK_ALARM):
        fired |= codes(monitor.record(event(at=float(i), confidence=0)))
    assert dl.AlarmCode.ZERO_CONFIDENCE_STREAK in fired


def test_zero_streak_resets_on_a_healthy_decision():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    for i in range(3):
        monitor.record(event(at=float(i), confidence=0))
    monitor.record(event(at=9.0, confidence=75))
    assert monitor.snapshot()["zero_confidence_streak"] == 0


def test_ready_with_zero_confidence_alarms_immediately():
    """The exact v1.9 contradiction, which occurred 72 times undetected."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    alarms = monitor.record(event(confidence=0, status="ready", side="buy"))
    assert dl.AlarmCode.READY_WITH_LOW_CONFIDENCE in codes(alarms)


def test_proposal_stall_alarms():
    """The silent 61.6-minute gap on 2026-08-10 emitted nothing."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    monitor.record(event(at=0.0))
    alarms = monitor.check_time_based(
        dl.PROPOSAL_STALL_SECONDS + 1,
        trade_permitted=True, cache_ready=True, has_open_position=False,
    )
    assert dl.AlarmCode.PROPOSAL_STALL in codes(alarms)


def test_no_stall_alarm_when_trading_not_permitted():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    monitor.record(event(at=0.0))
    alarms = monitor.check_time_based(
        dl.PROPOSAL_STALL_SECONDS + 1,
        trade_permitted=False, cache_ready=True, has_open_position=False,
    )
    assert dl.AlarmCode.PROPOSAL_STALL not in codes(alarms)


def test_no_ready_proposal_alarms_when_flat_and_open():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    alarms = monitor.check_time_based(
        dl.NO_READY_PROPOSAL_SECONDS + 1,
        trade_permitted=True, cache_ready=True, has_open_position=False,
    )
    assert dl.AlarmCode.NO_READY_PROPOSAL in codes(alarms)


def test_no_ready_alarm_suppressed_while_in_a_position():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    alarms = monitor.check_time_based(
        dl.NO_READY_PROPOSAL_SECONDS + 1,
        trade_permitted=True, cache_ready=True, has_open_position=True,
    )
    assert dl.AlarmCode.NO_READY_PROPOSAL not in codes(alarms)


def test_ready_rate_collapse_alarms():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    fired = set()
    for i in range(dl.READY_RATE_WINDOW):
        fired |= codes(monitor.record(event(at=float(i), confidence=0, status="wait")))
    assert dl.AlarmCode.READY_RATE_COLLAPSE in fired


def test_side_imbalance_alarms():
    """44 sell / 1 buy produced no signal at all."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    fired = set()
    for i in range(dl.SIDE_BALANCE_WINDOW):
        fired |= codes(monitor.record(
            event(at=float(i), status="ready", side="sell", confidence=80)
        ))
    assert dl.AlarmCode.SIDE_IMBALANCE in fired


def test_balanced_stream_does_not_alarm():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    fired = set()
    for i in range(dl.SIDE_BALANCE_WINDOW):
        fired |= codes(monitor.record(
            event(at=float(i), status="ready",
                  side="buy" if i % 2 else "sell", confidence=80)
        ))
    assert dl.AlarmCode.SIDE_IMBALANCE not in fired


def test_contract_version_change_is_flagged():
    """Ties a behaviour shift to the edit that caused it."""
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    monitor.record(event(at=0.0, contract_version="1.8"))
    alarms = monitor.record(event(at=1.0, contract_version="1.9"))
    assert dl.AlarmCode.CONTRACT_VERSION_CHANGED in codes(alarms)


def test_high_latency_warns():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    fired = set()
    for i in range(dl.LATENCY_WINDOW):
        fired |= codes(monitor.record(event(at=float(i), latency_seconds=31.0)))
    assert dl.AlarmCode.MODEL_LATENCY_HIGH in fired


def test_snapshot_reports_distribution():
    monitor = dl.DecisionLivenessMonitor(now=0.0)
    for i in range(10):
        monitor.record(event(at=float(i), confidence=0))
    snap = monitor.snapshot()
    assert snap["zero_confidence_share"] == 1.0
    assert snap["decisions_seen"] == 10


def test_format_alarm_is_greppable():
    alarm = dl.Alarm(code="liveness:test", severity="critical",
                     detail="something", observed_at=0.0)
    line = dl.format_alarm(alarm)
    assert line.startswith("ALARM CRITICAL liveness:test")
