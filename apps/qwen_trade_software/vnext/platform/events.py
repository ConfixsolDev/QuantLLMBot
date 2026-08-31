"""Versioned immutable event envelope used by every V2 subsystem."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .time_frontier import TimeFrontier, utc


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    pair: str
    observed_at_utc: datetime
    payload: Mapping[str, Any]
    source: str
    schema_version: str = "EVENT_V1"
    confirmed_at_utc: datetime | None = None
    effective_from_utc: datetime | None = None
    invalidated_at_utc: datetime | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_type or not self.pair or not self.source:
            raise ValueError("event_id, event_type, pair, and source are required")
        observed = utc(self.observed_at_utc)
        object.__setattr__(self, "observed_at_utc", observed)
        for field in ("confirmed_at_utc", "effective_from_utc", "invalidated_at_utc"):
            value = getattr(self, field)
            if value is not None:
                value = utc(value)
                if value < observed and field != "invalidated_at_utc":
                    raise ValueError(f"{field} cannot precede observed_at_utc")
                object.__setattr__(self, field, value)
        object.__setattr__(self, "payload", dict(self.payload))

    def validate_against(self, frontier: TimeFrontier) -> None:
        frontier.require(self.observed_at_utc, label="observed evidence")
        for label in ("confirmed_at_utc", "effective_from_utc", "invalidated_at_utc"):
            value = getattr(self, label)
            if value is not None:
                frontier.require(value, label=label)

    def canonical(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "pair": self.pair,
            "observed_at_utc": self.observed_at_utc.isoformat(),
            "confirmed_at_utc": self.confirmed_at_utc.isoformat() if self.confirmed_at_utc else None,
            "effective_from_utc": self.effective_from_utc.isoformat() if self.effective_from_utc else None,
            "invalidated_at_utc": self.invalidated_at_utc.isoformat() if self.invalidated_at_utc else None,
            "source": self.source,
            "payload": dict(self.payload),
        }

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(_canonical(self.canonical()).encode("utf-8")).hexdigest()
