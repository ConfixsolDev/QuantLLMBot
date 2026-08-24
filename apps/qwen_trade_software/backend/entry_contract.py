"""Stable wire contract between Qwen strategy output and entry execution.

Ollama's structured-output implementation used by the live Qwen runtime
enforces top-level ``required`` fields but does not reliably enforce nested
conditional requirements.  Keep the wire shape flat, then adapt it into the
internal ``execution_plan`` shape used by the rest of the application.

Strategy doctrine may change prompts and scoring.  It must not change these
transport fields or the deterministic fail-closed validation here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable, Mapping


WIRE_CONTRACT_VERSION = "2.0"
NONE = "__none__"

READY_PLAN_LEVEL_FIELDS = (
    "entry_low_id",
    "entry_high_id",
    "stop_level_id",
    "target_level_id",
)
READY_PLAN_REQUIRED_FIELDS = (
    "status",
    "side",
    *READY_PLAN_LEVEL_FIELDS,
    "target_mode",
    "volume_each",
    "reason",
)

WIRE_PLAN_FIELDS = (
    "plan_status",
    "plan_side",
    "entry_low_id",
    "entry_high_id",
    "stop_level_id",
    "target_level_id",
    "target_mode",
    "volume_each",
    "plan_reason",
)


def build_schema(
    *,
    epochs: Mapping[str, str],
    level_ids: list[str],
    evidence_ids: list[str],
) -> dict:
    """Return the flat schema supported by the live Ollama decoder."""
    available_levels = sorted(set(level_ids)) or ["__no_level__"]
    level_enum = available_levels + [NONE]
    evidence_enum = list(dict.fromkeys(evidence_ids)) or ["__no_evidence__"]
    request_schema = {
        "type": "object",
        "properties": {
            "tool": {"type": "string", "enum": [
                "get_completed_candles", "get_structure_state",
                "get_structure_events", "get_dxy_state",
            ]},
            "symbol": {"type": "string"},
            "timeframe": {"type": "string", "enum": [
                "M1", "M5", "M15", "M30", "H1", "H4", "D1",
            ]},
            "count": {"type": "integer", "minimum": 1, "maximum": 80},
            "missing_fact": {"type": "string", "maxLength": 120},
            "why_needed": {"type": "string", "maxLength": 160},
        },
        "required": [
            "tool", "symbol", "timeframe", "count",
            "missing_fact", "why_needed",
        ],
        "additionalProperties": False,
    }
    properties = {
        "bias": {"type": "string", "enum": ["buy", "sell", "wait"]},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 100},
        "summary": {"type": "string", "maxLength": 120},
        "acknowledged_epochs": {
            "type": "object",
            "properties": {
                key: {"type": "string", "const": value}
                for key, value in epochs.items()
            },
            "required": sorted(epochs),
            "additionalProperties": False,
        },
        "evidence_ids": {
            "type": "array",
            "items": {"type": "string", "enum": evidence_enum},
            "minItems": 1,
            "maxItems": 6,
        },
        # All plan fields are top-level and always required. Wait uses NONE for
        # non-applicable geometry; ready must use actual enum values.
        "plan_status": {"type": "string", "enum": ["ready", "wait"]},
        "plan_side": {"type": "string", "enum": ["buy", "sell", NONE]},
        "entry_low_id": {"type": "string", "enum": level_enum},
        "entry_high_id": {"type": "string", "enum": level_enum},
        "stop_level_id": {"type": "string", "enum": level_enum},
        "target_level_id": {"type": "string", "enum": level_enum},
        "target_mode": {"type": "string", "enum": [
            "scalp", "starter_basket", "directional_basket", NONE,
        ]},
        "volume_each": {"type": "number", "const": 0.5},
        "plan_reason": {"type": "string", "minLength": 1, "maxLength": 120},
        "data_requests": {
            "type": "array",
            "items": request_schema,
            "maxItems": 2,
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def adapt_wire_response(value: dict) -> dict:
    """Convert the flat wire response into the stable internal plan shape.

    Legacy nested responses are returned unchanged so a schema rollout fails
    closed through normal validation instead of crashing the reviewer.
    """
    if not isinstance(value, dict) or "plan_status" not in value:
        return value
    review = deepcopy(value)
    status = str(review.get("plan_status") or "").lower()
    plan = {
        "status": status,
        "reason": str(review.get("plan_reason") or ""),
    }
    if status == "ready":
        mapped = {
            "side": review.get("plan_side"),
            "entry_low_id": review.get("entry_low_id"),
            "entry_high_id": review.get("entry_high_id"),
            "stop_level_id": review.get("stop_level_id"),
            "target_level_id": review.get("target_level_id"),
            "target_mode": review.get("target_mode"),
            "volume_each": review.get("volume_each"),
        }
        plan.update({key: item for key, item in mapped.items() if item != NONE})
    review["execution_plan"] = plan
    for key in WIRE_PLAN_FIELDS:
        review.pop(key, None)
    return review


def correction_reason(
    review: Mapping,
    *,
    ready_reason_checker: Callable[[Mapping], str | None] | None = None,
) -> str | None:
    """Return all contract violations for one bounded correction attempt."""
    plan = review.get("execution_plan") or {}
    bias = str(review.get("bias") or "").lower()
    try:
        confidence = int(review.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if bias in ("buy", "sell") and confidence == 0:
        return "directional_bias_with_zero_confidence"
    if str(plan.get("status") or "").lower() != "ready":
        return None

    failures = []
    missing = [
        field for field in READY_PLAN_REQUIRED_FIELDS
        if plan.get(field) in (None, "", NONE)
    ]
    if missing:
        failures.append("ready_missing_fields:" + ",".join(missing))
    if review.get("data_requests"):
        failures.append("ready_with_unresolved_data_request")
    declared_side = str(plan.get("side") or "").lower()
    if declared_side and bias in ("buy", "sell") and declared_side != bias:
        failures.append("ready_side_contradicts_bias")
    if ready_reason_checker and ready_reason_checker(review):
        failures.append("ready_contradicts_own_reason")
    return ";".join(failures) if failures else None


def wait_reason(contract_failure: str) -> str:
    if contract_failure.startswith("ready_missing_fields:"):
        missing = contract_failure.split(":", 1)[1].split(";", 1)[0]
        return (
            "Qwen returned ready without required fields after its correction "
            f"attempt ({missing.replace(',', ', ')})."
        )
    return f"Qwen entry contract remained invalid after correction ({contract_failure})."
