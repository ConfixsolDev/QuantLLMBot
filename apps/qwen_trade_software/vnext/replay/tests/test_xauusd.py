from datetime import datetime, timedelta, timezone

from vnext.data.bars import Bar
from vnext.replay.xauusd import replay_candidates


def test_candidate_replay_is_causal_and_reports_session_coverage():
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    bars = [Bar("XAUUSDr", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i + 1),
                100 + (i % 4), 101 + (i % 4), 99 + (i % 4), 100.5 + (i % 4)) for i in range(340)]
    report = replay_candidates(bars, lookback=300, cadence_minutes=10)
    assert report.source_bars == 340 and report.evaluated_frontiers == 4
    assert sum(report.sessions.values()) == 4
    assert not report.errors
