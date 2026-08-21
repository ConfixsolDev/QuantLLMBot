"""Time-aware entry and open-position protection context."""

from __future__ import annotations

from datetime import datetime, timezone


PROTECTION_WINDOWS = {"M30": (30, 10), "H1": (60, 10), "H4": (240, 15)}


def temporal_protection_window(now: datetime | None = None) -> dict | None:
    """Describe active parent-candle closing windows without blocking entry."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    seconds = current.hour * 3600 + current.minute * 60 + current.second
    active, remaining = [], []
    for frame, (period_minutes, window_minutes) in PROTECTION_WINDOWS.items():
        period_seconds = period_minutes * 60
        seconds_left = period_seconds - (seconds % period_seconds)
        if 0 < seconds_left <= window_minutes * 60:
            active.append(frame)
            remaining.append(seconds_left)
    if not active:
        return None
    return {
        "mode": "temporal_close_protection",
        "frames": active,
        "seconds_to_nearest_close": min(remaining),
        "as_of_utc": current.isoformat().replace("+00:00", "Z"),
    }
