"""Redis-backed single-instance lease for the V2 service."""

from __future__ import annotations

import secrets
from typing import Any


class VNextLease:
    def __init__(self, client: Any, *, name: str = "qwen:vnext:service:lease", ttl_seconds: int = 90) -> None:
        if not name or ttl_seconds <= 0:
            raise ValueError("lease name and TTL are required")
        self.client, self.name, self.ttl_seconds = client, name, ttl_seconds
        self.token = secrets.token_urlsafe(18)

    def acquire(self) -> bool:
        result = self.client.set(self.name, self.token, ex=self.ttl_seconds, nx=True)
        return bool(result)

    def release(self) -> None:
        current = self.client.get(self.name)
        if current == self.token:
            self.client.delete(self.name)
