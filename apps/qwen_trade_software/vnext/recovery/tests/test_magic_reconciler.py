from vnext.recovery.magic_reconciler import MagicPositionReconciler


class Store:
    def __init__(self, positions=()): self.positions, self.events = list(positions), []
    def latest_magic_positions(self, magic): return list(self.positions)
    def append_events(self, events): self.events.extend(events); return len(events)


class Broker:
    def __init__(self, positions): self.positions = positions
    def snapshot(self): return {"healthy": True, "positions": self.positions}


def test_magic_reconciler_records_only_the_supplied_broker_namespace_snapshot():
    store = Store()
    plan = MagicPositionReconciler(magic_number=3101, store=store).run(
        Broker([{"position_id": "1", "pair": "XAUUSDr", "direction": "buy", "volume": .1}]),
        data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert not plan.safe_to_resume
    event = store.events[0]
    assert event.payload["magic_number"] == 3101
    assert event.payload["positions"][0]["position_id"] == "1"


def test_matching_magic_snapshot_can_resume():
    store = Store([{"position_id": "1"}])
    plan = MagicPositionReconciler(magic_number=3101, store=store).run(
        Broker([{"position_id": "1"}]), data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert plan.safe_to_resume


def test_identical_successive_snapshots_have_distinct_observation_identity():
    store = Store()
    reconciler = MagicPositionReconciler(magic_number=3101, store=store)
    broker = Broker([])
    reconciler.run(broker, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    reconciler.run(broker, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert store.events[0].event_id != store.events[1].event_id
    assert store.events[0].content_hash != store.events[1].content_hash
