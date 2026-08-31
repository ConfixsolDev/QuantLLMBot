from datetime import datetime, timedelta, timezone

import pytest

from vnext.data.bars import Bar
from vnext.intelligence.zones.engine import ZoneEngine


def bars():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = [(10, 12, 9, 11), (11, 13, 10, 12), (10.5, 12, 9.5, 10.8)]
    return [Bar("XAUUSD", "M1", start + timedelta(minutes=i), start + timedelta(minutes=i + 1), *row) for i, row in enumerate(values)]


def test_zone_has_birth_certificate_and_rejection_distribution():
    zone = ZoneEngine().discover(bars(), pair="XAUUSD", timeframe="M1")[0]
    assert zone.zone_id.startswith("M1-")
    assert zone.birth_context["bar_count"] == 3
    assert zone.upper_rejection_p90 >= 0


def test_zone_lifecycle_records_rejection_and_break():
    zone = ZoneEngine().discover(bars(), pair="XAUUSD", timeframe="M1")[0]
    tested, rejected = ZoneEngine().interact(zone, bars()[0], volatility=1)
    assert rejected.kind in {"REJECTED", "ACCEPTED", "TOUCH"}
    assert len(tested.interactions) == 1
    broken_bar = Bar("XAUUSD", "M1", bars()[-1].end_utc, bars()[-1].end_utc + timedelta(minutes=1), 20, 21, 19, 20)
    broken, interaction = ZoneEngine().interact(tested, broken_bar)
    assert interaction.kind == "BROKEN"
    assert broken.lifecycle_state == "BROKEN"


def test_zone_transition_rejects_invalid_jump():
    zone = ZoneEngine().discover(bars(), pair="XAUUSD", timeframe="M1")[0]
    with pytest.raises(ValueError):
        zone.transition("RECLAIMED")
