from datetime import datetime, timedelta, timezone

from vnext.runtime.live_cycle import LiveVNextCycle, _utc_datetime, canonical_bar


class Source:
    def closed_m1(self, pair, count):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [{"time": start + timedelta(minutes=i), "open": 10+i, "high": 12+i,
                 "low": 9+i, "close": 11+i, "tick_volume": i+1} for i in range(5)]

    def forming_timeframes(self, pair):
        return [{"timeframe": "M15", "is_forming": True, "pair": pair}]


class Ledger:
    def __init__(self): self.events = []
    def ensure_schema(self): pass
    def append(self, event): self.events.append(event); return True


class Projection:
    def project(self, events): return len(list(events))


class Memory:
    def __init__(self): self.values = {}
    def put(self, key, value): self.values[key] = value


def test_canonical_bar_rejects_missing_price():
    try:
        canonical_bar("XAUUSD", {"time": 1, "open": 1})
    except KeyError:
        return
    raise AssertionError("missing OHLC must be rejected")


def test_utc_datetime_accepts_broker_scalar_timestamp():
    class BrokerScalar:
        def item(self):
            return 1_700_000_000

    assert _utc_datetime(BrokerScalar()).timestamp() == 1_700_000_000


def test_live_cycle_routes_state_event_and_context():
    from vnext.storage.persistence import VNextPersistence
    ledger, memory = Ledger(), Memory()
    persistence = VNextPersistence(ledger=ledger, projection=Projection(), working_memory=memory)
    state = LiveVNextCycle(pair="XAUUSD", source=Source(), persistence=persistence).run_once()
    assert state.schema_version == "PAIR_MARKET_STATE_V1"
    assert ledger.events[0].event_type == "PAIR_MARKET_STATE_COMPOSED"
    assert memory.values["XAUUSD"]["state_hash"] == state.state_hash
    assert memory.values["forming:XAUUSD"]["display_only"] is True
    assert memory.values["forming:XAUUSD"]["strategy_eligible"] is False
