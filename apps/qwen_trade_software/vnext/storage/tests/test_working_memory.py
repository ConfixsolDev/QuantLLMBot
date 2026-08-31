from vnext.storage.working_memory import WorkingMemory


class FakeRedis:
    def __init__(self): self.values = {}
    def setex(self, name, time, value): self.values[name] = value
    def get(self, name): return self.values.get(name)
    def delete(self, name): self.values.pop(name, None)


def test_working_memory_is_ttl_scoped_and_disposable():
    redis = FakeRedis()
    memory = WorkingMemory(redis, ttl_seconds=30)
    memory.put("state", {"hash": "h"})
    assert memory.get("state") == {"hash": "h"}
    assert redis.values["qwen:vnext:working:state"]
    memory.invalidate("state")
    assert memory.get("state") is None
