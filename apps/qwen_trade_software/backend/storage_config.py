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
