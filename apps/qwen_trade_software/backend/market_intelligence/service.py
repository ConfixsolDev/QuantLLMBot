"""Facade joining event memory, projections, DXY, retrieval, and observability."""

from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from pathlib import Path

from .cross_market import completed_bars as dxy_bars, summarize
from .projection import TIMEFRAMES, reduce_event, relationship_state
from .retrieval import RetrievalBroker
from .store import IntelligenceStore
from redis_context import RedisContextCache, RedisContextUnavailable
from storage_config import StorageConfig
from storage_factory import create_intelligence_store

log = logging.getLogger(__name__)
GRAPH_CONTEXT_MAX_AGE_SECONDS = 120


class MarketIntelligenceService:
    def __init__(self, db_path: Path | str, candle_reader) -> None:
        self.store = create_intelligence_store(db_path)
        self.cache_dir = Path(__file__).resolve().parents[1] / "cache"
        self.candle_reader = candle_reader
        self.retrieval = RetrievalBroker(self.store, candle_reader, dxy_bars)
        self.last_snapshot: dict = {}
        config = StorageConfig.from_env()
        self.redis_cache = None
        if config.redis_url:
            try:
                self.redis_cache = RedisContextCache(config.redis_url, ttl_seconds=config.redis_ttl_seconds)
            except RedisContextUnavailable:
                if config.redis_required:
                    raise

    def observe(self, symbol: str, native_structure: dict) -> dict:
        """Record new completed evidence and return bounded cross-market memory."""
        xau_states = {}
        trends = native_structure.get("trends") or {}
        now = datetime.now(timezone.utc).isoformat()
        for tf in TIMEFRAMES:
            bars = self.candle_reader(symbol, tf, 3)
            if not bars:
                continue
            bar = bars[-1]
            evidence_id = str(bar.get("evidence_id") or bar.get("id") or f"{symbol}_{tf}_{bar.get('open_time_utc')}")
            close_time = str(bar.get("close_time_utc") or bar.get("open_time_utc") or now)
            event = {"event_id": f"{symbol}:{tf}:{evidence_id}:close", "symbol": symbol,
                     "timeframe": tf, "event_type": "candle_closed", "event_time_utc": close_time,
                     "evidence_id": evidence_id,
                     "payload": {"open": bar.get("open", bar.get("o")), "high": bar.get("high", bar.get("h")),
                                 "low": bar.get("low", bar.get("l")), "close": bar.get("close", bar.get("c")),
                                 "direction": trends.get(tf, "unknown"),
                                 "transition": native_structure.get("transition") if tf in {"H1", "H4"} else None}}
            if self.store.append_event(event):
                state = reduce_event(self.store.projection(symbol, tf), event)
                self.store.put_projection(symbol, tf, state, event["event_id"])
            xau_states[tf] = self.store.projection(symbol, tf)

        dxy_states = {}
        dxy_symbol = None
        for tf in ("H4", "H1", "M30", "M15"):
            broker_symbol, bars = dxy_bars(tf, 40)
            dxy_symbol = dxy_symbol or broker_symbol
            summary = summarize(tf, bars)
            dxy_states[tf] = summary
            if summary.get("status") != "ok":
                continue
            latest = summary["latest"]
            event = {"event_id": f"DXY:{tf}:{latest['evidence_id']}:close", "symbol": "DXY",
                     "timeframe": tf, "event_type": "candle_closed",
                     "event_time_utc": latest["open_time_utc"], "evidence_id": latest["evidence_id"],
                     "payload": summary}
            if self.store.append_event(event):
                state = reduce_event(self.store.projection("DXY", tf), event)
                self.store.put_projection("DXY", tf, state, event["event_id"])

        relation = relationship_state(xau_states.get("H1") or {}, self.store.projection("DXY", "H1") or {})
        self.last_snapshot = {"status": "ready", "symbol": symbol,
                              "updated_at_utc": now, "hierarchy": xau_states,
                              "dxy": {"broker_symbol": dxy_symbol, "states": dxy_states},
                              "relationship": relation,
                              "recent_transitions": self.store.events(symbol, limit=6),
                              "recent_retrievals": self.store.recent_retrievals(6)}
        self._cache_snapshot(symbol)
        return self.compact_snapshot()

    def _cache_snapshot(self, symbol: str) -> None:
        if not self.redis_cache:
            return
        try:
            self.redis_cache.set_snapshot(symbol, self.compact_snapshot(include_graph=True))
            for tf, state in (self.last_snapshot.get("hierarchy") or {}).items():
                if state:
                    self.redis_cache.set_structure(symbol, tf, state)
        except RedisContextUnavailable:
            if StorageConfig.from_env().redis_required:
                raise

    def compact_snapshot(self, include_graph: bool = False) -> dict:
        snap = self.last_snapshot or {}
        hierarchy = {}
        for tf, state in (snap.get("hierarchy") or {}).items():
            if state:
                hierarchy[tf] = {k: state.get(k) for k in (
                    "state", "direction", "active_leg", "transition",
                    "invalidation_level_id", "latest_evidence_id", "structure_epoch",
                    "unresolved_condition")}
        graph = snap.get("graph_context", {"status": "unavailable"})
        result = {"status": snap.get("status", "starting"), "hierarchy": hierarchy,
                "dxy": snap.get("dxy", {}), "relationship": snap.get("relationship", {}),
                "recent_transitions": (snap.get("recent_transitions") or [])[-4:],
                "worker_health": snap.get("worker_health", {}),
                "graph_health": snap.get("graph_health", {}),
                "neo4j_shadow_status": {key: graph.get(key) for key in (
                    "status", "mode", "packet_version", "packet_bytes",
                    "within_packet_budget", "age_seconds")}}
        if include_graph:
            result["graph_context"] = graph
        return result

    def refresh_snapshot(self, symbol: str) -> dict:
        """Load worker-owned projections without collecting any market data."""
        if self.redis_cache:
            try:
                cached = self.redis_cache.get_snapshot(symbol)
                if cached:
                    self.last_snapshot = cached
                    return cached
            except RedisContextUnavailable:
                if StorageConfig.from_env().redis_required:
                    raise
        hierarchy = self.store.projections(symbol)
        dxy_states = self.store.projections("DXY")
        relation = relationship_state(
            hierarchy.get("H1") or {}, dxy_states.get("H1") or {}
        )
        worker_health = {}
        health_path = self.cache_dir / "market-memory-health.json"
        try:
            worker_health = json.loads(health_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            worker_health = {"status": "unavailable"}
        graph_context = {"status": "unavailable"}
        graph_health = {"status": "unavailable"}
        graph_path = self.cache_dir / "market-graph-context.json"
        try:
            graph_context = json.loads(graph_path.read_text(encoding="utf-8"))
            as_of = datetime.fromisoformat(
                str(graph_context.get("as_of_utc")).replace("Z", "+00:00")
            )
            age = max(0.0, (datetime.now(timezone.utc) - as_of).total_seconds())
            graph_context["age_seconds"] = round(age, 3)
            if age > GRAPH_CONTEXT_MAX_AGE_SECONDS:
                graph_context["status"] = "stale"
        except (OSError, ValueError):
            pass
        try:
            graph_health = json.loads(
                (self.cache_dir / "market-graph-health.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            pass
        self.last_snapshot = {
            "status": "ready" if hierarchy else "starting",
            "symbol": symbol,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "hierarchy": hierarchy,
            "dxy": {"states": dxy_states},
            "relationship": relation,
            "recent_transitions": self.store.events(symbol, limit=6),
            "recent_retrievals": self.store.recent_retrievals(6),
            "worker_health": worker_health,
            "graph_context": graph_context,
            "graph_health": graph_health,
        }
        # Neo4j remains non-authoritative: Qwen may inspect the bounded zone
        # plan for validation, while deterministic entry/risk gates retain the
        # right to reject it.  The website still receives the full packet.
        # The reviewer consumes only the bounded zone plan from this graph
        # packet.  Keeping the full context behind the service boundary makes
        # the plan auditable without granting Neo4j execution authority.
        return self.compact_snapshot(include_graph=True)

    def retrieve(self, symbol: str, requests: list[dict]) -> list[dict]:
        results = self.retrieval.execute(symbol, requests)
        self.last_snapshot["recent_retrievals"] = self.store.recent_retrievals(6)
        log.info("qwen_retrieval symbol=%s requests=%s results=%s", symbol, requests, results)
        return results

    def observability(self) -> dict:
        return {**self.last_snapshot, "recent_retrievals": self.store.recent_retrievals(10)}

    def replay(self) -> int:
        return self.store.rebuild(reduce_event)
