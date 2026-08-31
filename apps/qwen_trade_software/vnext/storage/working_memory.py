"""Disposable Redis working memory for current V2 context."""

from __future__ import annotations

import json
from typing import Any, Protocol


class RedisClient(Protocol):
    def setex(self, name: str, time: int, value: str) -> Any: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, name: str) -> Any: ...


class WorkingMemory:
    def __init__(self, client: RedisClient, *, ttl_seconds: int = 120, prefix: str = "qwen:vnext:working:") -> None:
        if ttl_seconds <= 0:
            raise ValueError("working-memory TTL must be positive")
        self.client, self.ttl_seconds, self.prefix = client, ttl_seconds, prefix

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.client.setex(self.prefix + key, self.ttl_seconds, json.dumps(value, sort_keys=True, default=str))

    def get(self, key: str) -> dict[str, Any] | None:
        raw = self.client.get(self.prefix + key)
        if not raw:
            return None
        value = json.loads(raw)
        return value if isinstance(value, dict) else None

    def invalidate(self, key: str) -> None:
        self.client.delete(self.prefix + key)
