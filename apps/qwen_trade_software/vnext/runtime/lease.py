"""Redis-backed single-instance lease for the V2 service."""

from __future__ import annotations

import secrets
import threading
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

    def renew(self) -> bool:
        """Extend only this owner's lease using one atomic Redis operation."""
        script = (
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
        )
        return bool(self.client.eval(script, 1, self.name, self.token, self.ttl_seconds))

    def release(self) -> None:
        current = self.client.get(self.name)
        if current == self.token:
            self.client.delete(self.name)


class LeaseHeartbeat:
    """Renew a held lease independently of potentially slow service work."""

    def __init__(self, lease: VNextLease, *, interval_seconds: float | None = None) -> None:
        interval = interval_seconds if interval_seconds is not None else lease.ttl_seconds / 3
        if interval <= 0 or interval >= lease.ttl_seconds:
            raise ValueError("heartbeat interval must be positive and shorter than the lease TTL")
        self.lease = lease
        self.interval_seconds = float(interval)
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("lease heartbeat is already started")
        self._thread = threading.Thread(target=self._run, name="vnext-lease-heartbeat", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                if not self.lease.renew():
                    self._lost.set()
                    return
            except Exception:
                self._lost.set()
                return

    def ensure_owned(self) -> None:
        if self.lost:
            raise RuntimeError("vNext service lost its lease")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
