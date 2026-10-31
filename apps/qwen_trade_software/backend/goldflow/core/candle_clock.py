"""Deterministic UTC candle-boundary context for Qwen entry and management.

The model should not have to infer bar age from an evidence-id timestamp.
These facts describe time only; they never claim that a forming candle has
closed or that a rollover by itself invalidates a trade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


FRAME_SECONDS = {
    "M15": 15 * 60,
    "M30": 30 * 60,
    "H1": 60 * 60,
    "H4": 4 * 60 * 60,
}
TRANSITION_SECONDS = {
    "M15": 3 * 60,
    "M30": 5 * 60,
    "H1": 15 * 60,
    "H4": 15 * 60,
}


def _utc(value: datetime | str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _frame_open(moment: datetime, frame_seconds: int) -> datetime:
    epoch = int(moment.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % frame_seconds), timezone.utc)


def candle_clock(
    moment: datetime | str | None = None,
    *,
    entry_time: datetime | str | None = None,
) -> dict:
    """Return explicit elapsed/remaining facts for M15/M30/H1/H4 bars."""
    now = _utc(moment)
    entered = _utc(entry_time) if entry_time is not None else None
    frames = {}
    for timeframe, duration in FRAME_SECONDS.items():
        opened = _frame_open(now, duration)
        closes = opened + timedelta(seconds=duration)
        elapsed = max(0, int((now - opened).total_seconds()))
        remaining = max(0, int((closes - now).total_seconds()))
        window = TRANSITION_SECONDS[timeframe]
        if elapsed < window:
            phase = "opening_transition"
        elif remaining <= window:
            phase = "closing_transition"
        else:
            phase = "middle"
        row = {
            "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
            "close_time_utc": closes.isoformat().replace("+00:00", "Z"),
            "elapsed_seconds": elapsed,
            "remaining_seconds": remaining,
            "elapsed_pct": round(elapsed / duration, 4),
            "phase": phase,
        }
        if entered is not None:
            entry_open = _frame_open(entered, duration)
            row["entry_seconds_before_close"] = max(
                0,
                int(
                    (
                        entry_open + timedelta(seconds=duration) - entered
                    ).total_seconds()
                ),
            )
            row["rolled_since_entry"] = opened > entry_open
        frames[timeframe] = row
    closing_together = [
        timeframe
        for timeframe, row in frames.items()
        if row["remaining_seconds"] == min(
            item["remaining_seconds"] for item in frames.values()
        )
    ]
    return {
        "as_of_utc": now.isoformat().replace("+00:00", "Z"),
        "time_basis": "UTC_fixed_buckets",
        "forming_bar_warning": (
            "Clock facts are context only; require closed price evidence for action."
        ),
        "close_hierarchy": "M15 builds M30; M30 builds H1; H1 builds H4",
        "next_boundary_frames": closing_together,
        "frames": frames,
    }
