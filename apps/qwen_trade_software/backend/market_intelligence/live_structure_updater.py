"""Fresh completed-candle -> deterministic structure-event updater.

This module is deliberately independent of Qwen.  It runs only after a new
completed candle was committed to the immutable SQLite ledger.  Stable event
IDs make the bounded replay idempotent; newly discovered labels enter the same
transactional Neo4j outbox as their source candles.
"""

from __future__ import annotations

from instrument_config import instrument_for

from .structure_labeling import SWING_WINGS, label_structure


REPLAY_WINDOWS = {
    "M1": 500,
    "M15": 400,
    "M30": 320,
    "H1": 300,
    "H4": 240,
    "D1": 180,
}


def update_live_structure(store, symbol: str, timeframes: list[str]) -> dict:
    """Append any structure labels made knowable by newly closed candles."""
    profile = instrument_for(symbol)
    report: dict[str, dict] = {}
    for timeframe in dict.fromkeys(timeframes):
        if timeframe not in REPLAY_WINDOWS:
            continue
        candles = store.completed_candles(
            symbol, timeframe, REPLAY_WINDOWS[timeframe]
        )
        generated = label_structure(
            symbol,
            timeframe,
            candles,
            wing=SWING_WINGS[timeframe],
            equal_tolerance=profile.equal_level_tolerance,
            displacement_min_body=profile.displacement_min_body,
        )
        inserted = store.append_events(generated)
        report[timeframe] = {
            "candles": len(candles),
            "generated": len(generated),
            "inserted": inserted,
            "latest_candle_close_utc": (
                candles[-1]["event_time_utc"] if candles else None
            ),
        }
    return report
