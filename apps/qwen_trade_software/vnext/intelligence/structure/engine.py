"""Minimal causal structure engine for the clean-room V2 path."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from vnext.data.bars import Bar


@dataclass(frozen=True, slots=True)
class StructureEvent:
    event_id: str
    event_type: str
    pair: str
    timeframe: str
    observed_at_utc: datetime
    source_bar_start_utc: datetime
    price: float
    authority: str = "causal_structure_v1"

    def as_dict(self) -> dict:
        return {"event_id": self.event_id, "event_type": self.event_type,
                "pair": self.pair, "timeframe": self.timeframe,
                "observed_at_utc": self.observed_at_utc.isoformat(),
                "source_bar_start_utc": self.source_bar_start_utc.isoformat(),
                "price": self.price, "authority": self.authority}


class StructureEngine:
    """Confirm local swings only when a later bar supplies reversal evidence."""

    def __init__(self, *, reversal_multiple: float = 1.0) -> None:
        if reversal_multiple <= 0:
            raise ValueError("reversal_multiple must be positive")
        self.reversal_multiple = reversal_multiple

    def detect_swings(self, bars: Iterable[Bar]) -> list[StructureEvent]:
        rows = sorted(list(bars), key=lambda bar: bar.start_utc)
        if len(rows) < 3:
            return []
        events: list[StructureEvent] = []
        for previous, candidate, confirmer in zip(rows, rows[1:], rows[2:]):
            threshold = max(candidate.high - candidate.low, 1e-9) * self.reversal_multiple
            if candidate.high >= previous.high and candidate.high >= confirmer.high and candidate.high - confirmer.low >= threshold:
                events.append(self._event("SWING_HIGH_CONFIRMED", candidate, confirmer, candidate.high))
            if candidate.low <= previous.low and candidate.low <= confirmer.low and confirmer.high - candidate.low >= threshold:
                events.append(self._event("SWING_LOW_CONFIRMED", candidate, confirmer, candidate.low))
        return sorted(events, key=lambda event: (event.observed_at_utc, event.event_id))

    @staticmethod
    def _event(kind: str, source: Bar, confirmer: Bar, price: float) -> StructureEvent:
        raw = f"{kind}|{source.pair}|{source.timeframe}|{source.start_utc.isoformat()}|{confirmer.end_utc.isoformat()}"
        return StructureEvent(
            event_id=hashlib.sha256(raw.encode()).hexdigest()[:20],
            event_type=kind, pair=source.pair, timeframe=source.timeframe,
            observed_at_utc=confirmer.end_utc,
            source_bar_start_utc=source.start_utc, price=price,
        )
