"""Allowlisted, bounded, read-only evidence tools for Qwen."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

ALLOWED_TOOLS = {"get_completed_candles", "get_structure_state", "get_structure_events", "get_dxy_state"}
ALLOWED_TF = {"M1", "M5", "M15", "M30", "H1", "H4", "D1"}


class RetrievalBroker:
    def __init__(self, store, candle_reader, dxy_reader) -> None:
        self.store, self.candle_reader, self.dxy_reader = store, candle_reader, dxy_reader

    def execute(self, primary_symbol: str, requests: list[dict], max_requests: int = 2) -> list[dict]:
        results = []
        for request in (requests or [])[:max_requests]:
            request_id = f"retrieval-{uuid.uuid4().hex[:12]}"
            tool = str(request.get("tool") or "")
            symbol = str(request.get("symbol") or primary_symbol)
            tf = str(request.get("timeframe") or "H1").upper()
            count = max(1, min(int(request.get("count") or 20), 80))
            if tool not in ALLOWED_TOOLS or tf not in ALLOWED_TF:
                result = {"request_id": request_id, "status": "rejected", "reason": "tool_or_timeframe_not_allowed"}
            elif tool == "get_completed_candles":
                rows = self.candle_reader(symbol, tf, count)
                result = self._result(request_id, rows, completed_only=True)
            elif tool == "get_structure_state":
                row = self.store.projection(symbol, tf)
                result = self._result(request_id, [row] if row else [], completed_only=True)
            elif tool == "get_structure_events":
                result = self._result(request_id, self.store.events(symbol, tf, count), completed_only=True)
            else:
                _, rows = self.dxy_reader(tf, count)
                result = self._result(request_id, rows, completed_only=True)
            self.store.record_retrieval(request_id, symbol, request, result, result["status"])
            results.append(result)
        return results

    @staticmethod
    def _result(request_id: str, rows: list, completed_only: bool) -> dict:
        return {"request_id": request_id, "status": "ok" if rows else "empty",
                "as_of_utc": datetime.now(timezone.utc).isoformat(),
                "completed_only": completed_only, "row_count": len(rows),
                "rows": rows, "truncated": False}
