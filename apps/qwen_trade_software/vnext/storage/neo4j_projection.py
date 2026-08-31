"""Neo4j causal relationship projection for Timescale events."""

from __future__ import annotations

import json
from typing import Any, Iterable, Protocol

from vnext.platform.events import EventEnvelope


class GraphSession(Protocol):
    def run(self, query: str, **parameters: Any) -> Any: ...


MERGE_EVENTS = """
UNWIND $rows AS row
MERGE (instrument:Instrument {symbol: row.pair})
MERGE (event:MarketEvent {id: row.event_id})
SET event.event_type=row.event_type,
    event.observed_at_utc=datetime(row.observed_at_utc),
    event.content_hash=row.content_hash,
    event.schema_version=row.schema_version,
    event.source=row.source,
    event.payload_json=row.payload_json
MERGE (event)-[:FOR_PAIR]->(instrument)
"""


class Neo4jProjection:
    def __init__(self, session: GraphSession) -> None:
        self.session = session

    def project(self, events: Iterable[EventEnvelope]) -> int:
        rows = [{"event_id": event.event_id, "event_type": event.event_type,
                 "pair": event.pair, "observed_at_utc": event.observed_at_utc.isoformat(),
                 "content_hash": event.content_hash, "schema_version": event.schema_version,
                 "source": event.source,
                 "payload_json": json.dumps(dict(event.payload), sort_keys=True, default=str)} for event in events]
        if not rows:
            return 0
        self.session.run(MERGE_EVENTS, rows=rows)
        return len(rows)
