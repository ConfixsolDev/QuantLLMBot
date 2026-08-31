from vnext.recovery.coordinator import RecoveryCoordinator


class Ledger:
    def __init__(self): self.events = []
    def append(self, event): self.events.append(event); return True


class Projection:
    def project(self, events): return len(list(events))


class Memory:
    def put(self, key, value): pass


def test_recovery_plan_is_persisted_as_event():
    from vnext.storage.persistence import VNextPersistence
    ledger = Ledger()
    persistence = VNextPersistence(ledger=ledger, projection=Projection(), working_memory=Memory())
    plan = RecoveryCoordinator(persistence).run(broker_positions=[{"position_id": 1}],
        ledger_positions=[], broker_healthy=True, data_healthy=True, redis_rebuilt=True)
    assert not plan.safe_to_resume
    assert ledger.events[0].event_type == "V2_RECOVERY_RECONCILIATION"
