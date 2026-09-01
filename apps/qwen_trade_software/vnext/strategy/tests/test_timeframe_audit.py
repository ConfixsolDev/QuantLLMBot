from datetime import datetime, timezone

from vnext.market.state import PairMarketState
from vnext.strategy.timeframe_audit import (
    EXPECTATION_EVENT,
    OUTCOME_EVENT,
    TimeframeExpectationAuditor,
)
from vnext.strategy.xau_m15_m1_structure_scalper import SPEC


def bar(timeframe: str, start: str, end: str, opened: float, closed: float) -> dict:
    return {
        "timeframe": timeframe,
        "start_utc": start,
        "end_utc": end,
        "open": opened,
        "high": max(opened, closed) + 1,
        "low": min(opened, closed) - 1,
        "close": closed,
    }


class FakeStore:
    def __init__(self, prior=None, durable=None):
        self.prior = prior
        self.durable = durable or {}
        self.events = []

    def latest_timeframe_expectation(self, **_kwargs):
        return self.prior

    def latest_completed_candles(self, **_kwargs):
        return self.durable

    def append_events(self, events):
        self.events.extend(events)
        return len(events)


def state_with_m15() -> PairMarketState:
    return PairMarketState(
        pair="XAUUSDr",
        time_frontier_utc=datetime(2026, 9, 1, 0, 20, tzinfo=timezone.utc),
        data_quality={},
        timeframes={
            "M15": [bar("M15", "2026-09-01T00:00:00+00:00", "2026-09-01T00:15:00+00:00", 2501, 2498)],
            "H1": [bar("H1", "2026-08-31T23:00:00+00:00", "2026-09-01T00:00:00+00:00", 2490, 2500)],
        },
    )


def test_records_causal_expectation_and_assesses_prior_interval():
    prior = {
        "event_id": "prior-expectation",
        "origin_close_utc": "2026-09-01T00:00:00+00:00",
        "target_close_utc": "2026-09-01T00:15:00+00:00",
        "frames": {
            "D1": {"expected_direction": "buy"},
            "H4": {"expected_direction": "neutral"},
            "H1": {"expected_direction": "sell"},
            "M30": {"expected_direction": "buy"},
            "M15": {"expected_direction": "sell"},
        },
    }
    durable = {
        "D1": bar("D1", "2026-08-30T00:00:00+00:00", "2026-08-31T00:00:00+00:00", 2480, 2500),
        "H4": bar("H4", "2026-08-31T20:00:00+00:00", "2026-09-01T00:00:00+00:00", 2500, 2500),
        "M30": bar("M30", "2026-08-31T23:30:00+00:00", "2026-09-01T00:00:00+00:00", 2495, 2497),
    }
    store = FakeStore(prior=prior, durable=durable)

    assert TimeframeExpectationAuditor(store).record(state_with_m15(), SPEC) == 2
    assert [event.event_type for event in store.events] == [OUTCOME_EVENT, EXPECTATION_EVENT]

    outcome = store.events[0].payload
    assert outcome["expectation_event_id"] == "prior-expectation"
    assert outcome["frames"]["M15"]["result"] == "ALIGNED"
    assert outcome["frames"]["D1"]["result"] == "COUNTER"
    assert outcome["frames"]["H4"]["result"] == "UNAVAILABLE"
    assert outcome["training_eligible"] is False

    expectation = store.events[1].payload
    assert expectation["origin_close_utc"] == "2026-09-01T00:15:00+00:00"
    assert expectation["target_close_utc"] == "2026-09-01T00:30:00+00:00"
    assert expectation["frames"]["D1"]["expected_direction"] == "buy"
    assert expectation["frames"]["M15"]["expected_direction"] == "sell"
    assert "state_hash" not in expectation
    assert len(expectation["basis_hash"]) == 64
    assert expectation["non_authoritative"] is True
    assert expectation["training_eligible"] is False


def test_expectation_identity_and_basis_are_stable_for_same_closed_boundary():
    first, second = FakeStore(), FakeStore()
    TimeframeExpectationAuditor(first).record(state_with_m15(), SPEC)
    state = state_with_m15()
    changed_live_state = PairMarketState(
        pair=state.pair,
        time_frontier_utc=datetime(2026, 9, 1, 0, 29, tzinfo=timezone.utc),
        data_quality={"later_runtime_detail": True},
        timeframes=state.timeframes,
    )
    TimeframeExpectationAuditor(second).record(changed_live_state, SPEC)

    assert first.events[0].event_id == second.events[0].event_id
    assert first.events[0].payload["basis_hash"] == second.events[0].payload["basis_hash"]


def test_does_not_write_without_a_completed_m15_boundary():
    store = FakeStore()
    state = PairMarketState(
        pair="XAUUSDr",
        time_frontier_utc=datetime(2026, 9, 1, tzinfo=timezone.utc),
        data_quality={},
        timeframes={},
    )
    assert TimeframeExpectationAuditor(store).record(state, SPEC) == 0
    assert store.events == []
