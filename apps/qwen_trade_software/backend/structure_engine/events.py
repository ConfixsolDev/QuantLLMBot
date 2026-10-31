"""Event: the ONLY thing Module 1 hands to the rest of the system.

Rule 1 of the architecture: modules talk through data. The structure engine
never calls Qwen, a strategy or a broker; it emits ``Event`` records and
keeps a ``snapshot()``. Module 2 (decision) reads them; Module 3 (risk) never
needs to know how they were computed.

Fields
------
kind          what happened, e.g. ``swing``, ``zone_created``, ``zone_tested``,
              ``zone_broken``, ``zone_expired``, ``session_level``,
              ``prior_day_level``, ``pattern_pending``, ``pattern_confirmed``,
              ``pattern_invalidated``, ``pattern_superseded``
tf            timeframe the structure lives on (M1 ... H4)
time          the structure's own anchor time (e.g. the swing candle's open)
available_at  the earliest moment this event could be known live: the close
              of the M1 bar whose arrival produced it. Rule 4 (no look-ahead)
              is proven by tests on exactly this field.
data          kind-specific payload (prices, ids, tags) — plain JSON types
config_hash   fingerprint of the thresholds used (see config.py)
id            deterministic id: same input + same config => same id, forever

"Forming" vs "confirmed" (Rule 5): events are always CONFIRMED facts. Things
still in progress (the running session high, a pattern waiting for its
neckline break) live in ``snapshot()['forming']`` / ``pending`` instead, so a
consumer can never mistake an unfinished structure for a finished one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    tf: str
    time: int
    available_at: int
    data: dict = field(default_factory=dict)
    config_hash: str = ""
    id: str = ""

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "tf": self.tf, "time": self.time,
                "available_at": self.available_at, "config_hash": self.config_hash,
                "data": self.data}


def make_event(kind: str, tf: str, time: int, available_at: int, data: dict,
               config_hash: str, key: str = "") -> Event:
    """Build an Event with a deterministic id.

    ``key`` distinguishes several events of the same kind/tf/time (e.g. a
    swing high and a swing low on the same candle).
    """
    raw = f"{config_hash}|{kind}|{tf}|{time}|{key}"
    eid = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return Event(kind, tf, int(time), int(available_at), data, config_hash, eid)


def fingerprint(events: list[Event]) -> str:
    """One hash over a whole event stream: the determinism test compares these."""
    h = hashlib.sha256()
    for e in events:
        h.update(json.dumps(e.as_dict(), sort_keys=True, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()
