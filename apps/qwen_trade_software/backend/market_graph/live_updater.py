"""One explicit live SQLite-outbox -> Neo4j update cycle.

The worker process owns scheduling and recovery.  This class owns every write
performed during a normal cycle and publishes a measurable M1 freshness
contract.  Neo4j is never allowed to describe stale data as fresh.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .context_compiler import compile_market_memory
from .projector import GraphProjector
from .temporal import utc_datetime


M1_FRESHNESS_LIMIT_SECONDS = 125


def _m1_freshness(raw_context: dict, symbols: tuple[str, ...] | list[str]) -> dict:
    now = utc_datetime(raw_context.get("as_of_utc") or datetime.now(timezone.utc).isoformat())
    rows = {}
    for symbol in symbols:
        events = ((raw_context.get("symbols") or {}).get(symbol) or {}).get("M1") or []
        latest = events[0] if events else {}
        closed_at = latest.get("event_time")
        lag = max(0.0, (now - utc_datetime(closed_at)).total_seconds()) if closed_at else None
        rows[symbol] = {
            "latest_completed_m1_utc": closed_at,
            "lag_seconds": round(lag, 3) if lag is not None else None,
            "fresh": lag is not None and lag <= M1_FRESHNESS_LIMIT_SECONDS,
            "evidence_id": latest.get("evidence_id"),
        }
    return {
        "limit_seconds": M1_FRESHNESS_LIMIT_SECONDS,
        "symbols": rows,
        "fresh": bool(rows) and all(row["fresh"] for row in rows.values()),
    }


class Neo4jLiveUpdater:
    """Project pending facts, update market maps, and compile fresh context."""

    def __init__(self, store, graph, config) -> None:
        self.store = store
        self.graph = graph
        self.config = config
        self.projector = GraphProjector(store, graph, config)

    def update(self, market_state: dict) -> dict:
        projection = self.projector.project_once()
        self.graph.upsert_market_state(market_state)
        stats = self.store.graph_outbox_stats()
        raw_context = self.graph.context(self.config.symbols)
        raw_context.update({
            "projection": stats,
            "schema_version": self.config.schema_version,
            "current_prices": market_state.get("prices") or {},
        })
        freshness = _m1_freshness(raw_context, self.config.symbols)
        context = compile_market_memory(raw_context)
        context["m1_freshness"] = freshness
        if not freshness["fresh"]:
            context["status"] = "stale"
        return {
            "projection": projection,
            "outbox": stats,
            "context": context,
            "m1_freshness": freshness,
        }
