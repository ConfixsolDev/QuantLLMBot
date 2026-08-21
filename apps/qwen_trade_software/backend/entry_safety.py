"""Deterministic entry-only safety policies.

These checks never manage or close an existing position.  They only prevent a
new thesis from being opened during a known market-microstructure hazard.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone


BOUNDARY_FRAMES_MINUTES = (15, 30, 60, 240)
BOUNDARY_BLOCK_BEFORE_SECONDS = max(
    0, int(os.environ.get("QWEN_BOUNDARY_BLOCK_BEFORE_SECONDS", "180"))
)
BOUNDARY_BLOCK_AFTER_SECONDS = max(
    0, int(os.environ.get("QWEN_BOUNDARY_BLOCK_AFTER_SECONDS", "60"))
)


def candle_boundary_entry_block(now: datetime | None = None) -> dict | None:
    """Return the active M15/M30/H1/H4 entry blackout, if any.

    A higher-timeframe boundary is also an M15 boundary.  We nevertheless
    report every closing frame so research logs preserve the nesting context.
    The window is deliberately short and symmetric around the close: no new
    risk just before the auction resets, and no entry during its first minute.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    seconds_of_day = (
        current.hour * 3600
        + current.minute * 60
        + current.second
        + current.microsecond / 1_000_000
    )
    day_seconds = 24 * 60 * 60
    blocked_frames = []
    nearest = None
    for minutes in BOUNDARY_FRAMES_MINUTES:
        period = minutes * 60
        since = seconds_of_day % period
        until = period - since
        # At the exact boundary, ``since`` is zero and belongs to the opening
        # side of the blackout rather than the next close.
        in_window = (
            0 <= since < BOUNDARY_BLOCK_AFTER_SECONDS
            or 0 < until <= BOUNDARY_BLOCK_BEFORE_SECONDS
        )
        if in_window:
            blocked_frames.append("H4" if minutes == 240 else f"M{minutes}" if minutes < 60 else "H1")
            distance = min(since, until)
            nearest = distance if nearest is None else min(nearest, distance)
    if not blocked_frames:
        return None
    return {
        "reason": "candle_boundary_blackout",
        "frames": blocked_frames,
        "before_seconds": BOUNDARY_BLOCK_BEFORE_SECONDS,
        "after_seconds": BOUNDARY_BLOCK_AFTER_SECONDS,
        "nearest_boundary_seconds": round(float(nearest or 0.0), 3),
        "as_of_utc": current.isoformat().replace("+00:00", "Z"),
    }
