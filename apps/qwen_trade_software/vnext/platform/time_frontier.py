"""Causal time-frontier enforcement for replay, paper, and live adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


UTC = timezone.utc


def utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("time frontier values must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class TimeFrontier:
    """The latest event time a component is legally allowed to consume."""

    as_of_utc: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_utc", utc(self.as_of_utc))

    @classmethod
    def from_value(cls, value: datetime | str) -> "TimeFrontier":
        return cls(utc(value))

    def permits(self, value: datetime | str) -> bool:
        return utc(value) <= self.as_of_utc

    def require(self, value: datetime | str, *, label: str = "evidence") -> datetime:
        normalized = utc(value)
        if normalized > self.as_of_utc:
            raise ValueError(
                f"{label} at {normalized.isoformat()} exceeds time frontier "
                f"{self.as_of_utc.isoformat()}"
            )
        return normalized

    def advance(self, value: datetime | str) -> "TimeFrontier":
        normalized = utc(value)
        if normalized < self.as_of_utc:
            raise ValueError("time frontier cannot move backwards")
        return TimeFrontier(normalized)
