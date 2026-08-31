from __future__ import annotations

from redis_context import RedisContextCache


class FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = (ttl, value)

    def get(self, key):
        return self.values.get(key, (None, None))[1]

    def ping(self):
        return True


def test_redis_cache_round_trips_bounded_context():
    cache = RedisContextCache("redis://unused", client=FakeRedis(), ttl_seconds=30)
    cache.set_snapshot("XAUUSDr", {"status": "ready", "hierarchy": {"M15": {}}})
    assert cache.get_snapshot("XAUUSDr")["status"] == "ready"
    assert cache.health()


def test_cache_loader_falls_back_to_durable_reader():
    cache = RedisContextCache("redis://unused", client=FakeRedis())
    snapshot, source = cache.get_or_load("XAUUSDr", lambda: {"status": "durable"})
    assert snapshot["status"] == "durable"
    assert source == "durable"
    assert cache.get_or_load("XAUUSDr", lambda: {"status": "wrong"})[1] == "redis"
