"""Idempotent outbox-to-Neo4j projection orchestration."""

from __future__ import annotations

from .temporal import graph_row


class GraphProjector:
    def __init__(self, store, graph, config) -> None:
        self.store = store
        self.graph = graph
        self.config = config

    def project_once(self) -> dict:
        pending = int(self.store.graph_outbox_stats().get("pending", 0))
        # Historical rebuilds should use the memory already allocated to Neo4j;
        # steady-state projection remains at the conservative configured batch.
        batch_size = min(10000, max(
            self.config.batch_size,
            10000 if pending > 10000 else (
                1000 if pending > 1000 else self.config.batch_size
            ),
        ))
        events = self.store.graph_outbox_batch(
            batch_size, self.config.max_attempts
        )
        if not events:
            return {"status": "idle", "selected": 0, "projected": 0}
        event_ids = [event["event_id"] for event in events]
        try:
            rows = [graph_row(
                event,
                self.config.schema_version,
                self.config.session_calendar_version,
            ) for event in events]
            self.graph.upsert_rows(rows)
            self.store.mark_graph_projected(event_ids)
            return {"status": "ready", "selected": len(events), "projected": len(events)}
        except Exception as error:
            retryable_check = getattr(error, "is_retryable", None)
            retryable = bool(retryable_check()) if callable(retryable_check) else False
            if not retryable:
                self.store.mark_graph_failed(event_ids, str(error), self.config.max_attempts)
            return {
                "status": "error",
                "selected": len(events),
                "projected": 0,
                "error": str(error),
                "retryable": retryable,
            }
