from datetime import datetime, timedelta, timezone

from vnext.data.bars import Bar
from vnext.intelligence.indicators.evidence import indicator_evidence


def test_indicator_evidence_is_supportive_and_volume_weighted():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [Bar("XAUUSD", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i + 1), 10, 12, 9, 11, i + 1) for i in range(6)]
    result = indicator_evidence(bars, spread=0.2)
    assert result["status"] == "ready"
    assert result["vwap"] is not None
    assert result["authority"] == "supportive_evidence_only"
