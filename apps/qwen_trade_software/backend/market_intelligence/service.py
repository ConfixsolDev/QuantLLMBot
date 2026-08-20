"""Facade joining event memory, projections, DXY, retrieval, and observability."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from .cross_market import completed_bars as dxy_bars, summarize
from .projection import TIMEFRAMES, reduce_event, relationship_state
from .retrieval import RetrievalBroker
from .store import IntelligenceStore

log = logging.getLogger(__name__)


class MarketIntelligenceService:
    def __init__(self, db_path: Path | str, candle_reader) -> None:
        self.store = IntelligenceStore(db_path)
        self.candle_reader = candle_reader
        self.retrieval = RetrievalBroker(self.store, candle_reader, dxy_bars)
        self.last_snapshot: dict = {}

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
        return self.compact_snapshot()

    def compact_snapshot(self) -> dict:
        snap = self.last_snapshot or {}
        hierarchy = {}
        for tf, state in (snap.get("hierarchy") or {}).items():
            if state:
                hierarchy[tf] = {k: state.get(k) for k in (
                    "state", "direction", "active_leg", "transition",
                    "invalidation_level_id", "latest_evidence_id", "structure_epoch",
                    "unresolved_condition")}
        return {"status": snap.get("status", "starting"), "hierarchy": hierarchy,
                "dxy": snap.get("dxy", {}), "relationship": snap.get("relationship", {}),
                "recent_transitions": (snap.get("recent_transitions") or [])[-4:]}

    def retrieve(self, symbol: str, requests: list[dict]) -> list[dict]:
        results = self.retrieval.execute(symbol, requests)
        self.last_snapshot["recent_retrievals"] = self.store.recent_retrievals(6)
        log.info("qwen_retrieval symbol=%s requests=%s results=%s", symbol, requests, results)
        return results

    def observability(self) -> dict:
        return {**self.last_snapshot, "recent_retrievals": self.store.recent_retrievals(10)}

    def replay(self) -> int:
        return self.store.rebuild(reduce_event)
