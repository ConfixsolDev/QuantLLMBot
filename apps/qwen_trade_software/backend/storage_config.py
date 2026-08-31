"""Explicit storage configuration for the live intelligence path."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StorageConfig:
    backend: str
    timescale_dsn: str | None
    redis_url: str | None
    redis_ttl_seconds: int
    redis_required: bool

    @classmethod
    def from_env(cls) -> "StorageConfig":
        backend = os.environ.get("QWEN_INTELLIGENCE_BACKEND", "sqlite").strip().lower()
        if backend not in {"sqlite", "timescale"}:
            raise ValueError("QWEN_INTELLIGENCE_BACKEND must be sqlite or timescale")
        dsn = os.environ.get("QWEN_TIMESCALE_DSN") or None
        redis_url = os.environ.get("QWEN_REDIS_URL") or None
        return cls(
            backend=backend,
            timescale_dsn=dsn,
            redis_url=redis_url,
            redis_ttl_seconds=max(5, int(os.environ.get("QWEN_REDIS_CONTEXT_TTL", "120"))),
            redis_required=os.environ.get("QWEN_REDIS_REQUIRED", "0").lower() in {"1", "true", "yes"},
        )

    def validate_activation(self) -> dict[str, object]:
        """Validate the explicitly requested live backend before child start."""
        if self.backend == "timescale" and not self.timescale_dsn:
            raise RuntimeError("QWEN_TIMESCALE_DSN is required for Timescale activation")
        if os.environ.get("QWEN_CONTEXT_BACKEND", "sqlite").strip().lower() == "timescale" and not self.timescale_dsn:
            raise RuntimeError("QWEN_TIMESCALE_DSN is required for context activation")
        result: dict[str, object] = {"backend": self.backend, "timescale_configured": bool(self.timescale_dsn), "redis_configured": bool(self.redis_url)}
        if self.backend == "timescale":
            from timescale_store import TimescaleIntelligenceStore
            store = TimescaleIntelligenceStore(self.timescale_dsn)
            try:
                store.schema()
            finally:
                store.close()
            result["timescale_ready"] = True
        if os.environ.get("QWEN_CONTEXT_BACKEND", "sqlite").strip().lower() == "timescale":
            from timescale_context_store import TimescaleMarketContextCache
            cache = TimescaleMarketContextCache(self.timescale_dsn)
            try:
                result["timescale_context_ready"] = True
            finally:
                cache.close()
        if self.redis_url:
            from redis_context import RedisContextCache
            cache = RedisContextCache(self.redis_url, ttl_seconds=self.redis_ttl_seconds)
            if not cache.health() and self.redis_required:
                raise RuntimeError("Redis is required but health check failed")
            result["redis_ready"] = cache.health()
        return result
