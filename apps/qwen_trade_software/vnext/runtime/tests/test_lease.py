import time

from vnext.runtime.lease import LeaseHeartbeat, VNextLease


class FakeRedis:
    def __init__(self): self.value = None
    def set(self, name, value, *, ex, nx):
        if nx and self.value is not None: return False
        self.value = value
        return True
    def get(self, name): return self.value
    def delete(self, name): self.value = None
    def eval(self, script, key_count, name, token, ttl):
        assert key_count == 1 and ttl > 0
        return 1 if self.value == token else 0


def test_lease_allows_one_owner_and_releases_only_its_token():
    redis = FakeRedis()
    first, second = VNextLease(redis), VNextLease(redis)
    assert first.acquire() is True
    assert second.acquire() is False
    second.release()
    assert redis.value == first.token
    first.release()
    assert redis.value is None


def test_lease_renews_only_for_current_owner():
    redis = FakeRedis()
    first, second = VNextLease(redis), VNextLease(redis)
    assert first.acquire() is True
    assert first.renew() is True
    assert second.renew() is False


def test_heartbeat_renews_during_slow_work_and_reports_loss():
    redis = FakeRedis()
    lease = VNextLease(redis, ttl_seconds=1)
    assert lease.acquire() is True
    renewals = []
    original_renew = lease.renew

    def recorded_renew():
        renewals.append(True)
        return original_renew()

    lease.renew = recorded_renew
    heartbeat = LeaseHeartbeat(lease, interval_seconds=0.01)
    heartbeat.start()
    time.sleep(0.03)
    heartbeat.stop()
    assert len(renewals) >= 1
    heartbeat.ensure_owned()


def test_heartbeat_detects_lost_lease():
    redis = FakeRedis()
    lease = VNextLease(redis, ttl_seconds=1)
    assert lease.acquire() is True
    heartbeat = LeaseHeartbeat(lease, interval_seconds=0.01)
    heartbeat.start()
    redis.value = "different-owner"
    time.sleep(0.03)
    heartbeat.stop()
    assert heartbeat.lost is True
