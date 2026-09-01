"""Bounded Qwen reviewer for open strategy positions; it never executes actions."""

from __future__ import annotations

import json
from typing import Any, Mapping

from vnext.llm.client import QwenClient
from vnext.runtime.position_management import ManagedPosition


MANAGEMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["hold", "protect", "close"]},
        "reason": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "close_confirmed": {"type": "boolean"},
        "candidate_stop": {"type": "number"},
        "candidate_target": {"type": "number"},
        "deterioration_confirmed": {"type": "boolean"},
    },
    "required": ["action", "reason", "evidence_ids"],
    "additionalProperties": False,
}


class QwenManagementReviewer:
    def __init__(self, client: QwenClient) -> None:
        self.client = client

    def __call__(self, position: ManagedPosition) -> Mapping[str, Any]:
        packet = {
            "task": "review_one_open_strategy_position",
            "instruction": "Suggest only hold, protect, or close. Never add size or widen risk. Cite supplied completed M1 and M5 evidence IDs for protect or close. Return JSON only.",
            "position": {"position_id": position.position_id, "pair": position.pair,
                         "direction": position.direction, "entry": position.entry, "current": position.current,
                         "stop": position.broker_stop, "target": position.broker_target,
                         "opened_at_utc": position.opened_at.isoformat()},
            "completed_evidence": {"m1_id": position.latest_m1_id, "m1": position.latest_m1,
                                   "m5_id": position.latest_m5_id, "m5": position.latest_m5},
            "constraints": ["management suggestion only", "do not submit an order", "do not change position size"],
        }
        try:
            return self.client.generate(json.dumps(packet, sort_keys=True), response_schema=MANAGEMENT_SCHEMA)
        except (RuntimeError, ValueError) as exc:
            return {"action": "hold", "reason": f"qwen_management_unavailable:{type(exc).__name__}",
                    "evidence_ids": ()}
