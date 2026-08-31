from vnext.runtime.lease import VNextLease


class FakeRedis:
    def __init__(self): self.value = None
    def set(self, name, value, *, ex, nx):
        if nx and self.value is not None: return False
        self.value = value
        return True
    def get(self, name): return self.value
    def delete(self, name): self.value = None


def test_lease_allows_one_owner_and_releases_only_its_token():
    redis = FakeRedis()
    first, second = VNextLease(redis), VNextLease(redis)
    assert first.acquire() is True
    assert second.acquire() is False
    second.release()
    assert redis.value == first.token
    first.release()
    assert redis.value is None
