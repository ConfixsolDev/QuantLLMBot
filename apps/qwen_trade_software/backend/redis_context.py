"""Redis-only acceleration for bounded current context.

Redis is a disposable read cache. Durable evidence and projections remain in
the configured intelligence store; a Redis outage never invents context.
"""

from __future__ import annotations

import json
from typing import Any, Callable


class RedisContextUnavailable(RuntimeError):
    pass


class RedisContextCache:
    def __init__(self, url: str, *, ttl_seconds: int = 120, client: Any = None) -> None:
        self.ttl_seconds = max(5, int(ttl_seconds))
        if client is not None:
            self.client = client
            return
        try:
            import redis
            self.client = redis.Redis.from_url(url, decode_responses=True,
                                               socket_connect_timeout=1,
                                               socket_timeout=1)
        except Exception as exc:  # optional dependency/configuration failure
            raise RedisContextUnavailable(str(exc)) from exc

    def health(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def set_snapshot(self, symbol: str, snapshot: dict) -> None:
        key = f"qwen:context:v1:{symbol}"
        try:
            self.client.setex(key, self.ttl_seconds, json.dumps(snapshot, separators=(",", ":")))
        except Exception as exc:
            raise RedisContextUnavailable(str(exc)) from exc

    def get_snapshot(self, symbol: str) -> dict | None:
        try:
            raw = self.client.get(f"qwen:context:v1:{symbol}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            raise RedisContextUnavailable(str(exc)) from exc

    def set_structure(self, symbol: str, timeframe: str, state: dict) -> None:
        try:
            self.client.setex(
                f"qwen:structure:v1:{symbol}:{timeframe}", self.ttl_seconds,
                json.dumps(state, separators=(",", ":")),
            )
        except Exception as exc:
            raise RedisContextUnavailable(str(exc)) from exc

    def get_structure(self, symbol: str, timeframe: str) -> dict | None:
        try:
            raw = self.client.get(f"qwen:structure:v1:{symbol}:{timeframe}")
            return json.loads(raw) if raw else None
        except Exception as exc:
            raise RedisContextUnavailable(str(exc)) from exc

    def get_or_load(self, symbol: str, loader: Callable[[], dict]) -> tuple[dict, str]:
        try:
            cached = self.get_snapshot(symbol)
            if cached is not None:
                return cached, "redis"
        except RedisContextUnavailable:
            pass
        snapshot = loader()
        try:
            self.set_snapshot(symbol, snapshot)
        except RedisContextUnavailable:
            pass
        return snapshot, "durable"
