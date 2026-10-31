"""Deterministic event gate for expensive Qwen entry inference."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


def fingerprint(snapshot: dict) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


class QwenEventGate:
    def __init__(self, path: Path | str, heartbeat_seconds: float = 900.0) -> None:
        self.path = Path(path)
        self.heartbeat_seconds = max(60.0, float(heartbeat_seconds))
        self.state = self._load()

    def _load(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def evaluate(self, snapshot: dict, now: float | None = None) -> tuple[bool, str, str]:
        now = time.time() if now is None else float(now)
        current = fingerprint(snapshot)
        previous = str(self.state.get("fingerprint") or "")
        last_call = float(self.state.get("called_at_epoch") or 0.0)
        if not previous:
            return True, "startup", current
        if current != previous:
            return True, "market_event", current
        if now - last_call >= self.heartbeat_seconds:
            return True, "safety_heartbeat", current
        return False, "unchanged_state", current

    def record_call(self, current: str, reason: str, now: float | None = None) -> None:
        now = time.time() if now is None else float(now)
        self.state = {"fingerprint": current, "called_at_epoch": now, "reason": reason}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
