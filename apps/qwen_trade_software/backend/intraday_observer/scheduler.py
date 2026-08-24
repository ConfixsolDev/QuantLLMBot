"""Pure scheduling policy for bounded intraday reflections."""

from __future__ import annotations

from datetime import datetime, timezone

from .contracts import CONTRACT_VERSION


def _utc(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def review_due(
    snapshot: dict,
    state: dict,
    now: datetime | None = None,
    *,
    event_cooldown_seconds: int = 300,
) -> tuple[bool, str]:
    if state.get("contract_version") != CONTRACT_VERSION:
        return True, "startup"
    prior = state.get("deterministic") or {}
    if snapshot.get("episode_id") != prior.get("episode_id"):
        return True, "half_hour_close"
    if snapshot.get("fingerprint") == prior.get("fingerprint"):
        return False, "unchanged"
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    generated = _utc(state.get("generated_at_utc"))
    if generated and (now - generated).total_seconds() < event_cooldown_seconds:
        return False, "event_cooldown"
    return True, "structure_or_level_event"
