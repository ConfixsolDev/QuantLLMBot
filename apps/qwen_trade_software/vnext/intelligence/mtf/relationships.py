"""Independent parent/child relationship classification."""

from __future__ import annotations

from typing import Any


RELATIONSHIPS = frozenset({
    "ALIGNED", "PULLBACK", "COUNTER_MOVE", "COMPRESSION", "CONTINUATION",
    "TRANSITION_WARNING", "TRANSITION_CONFIRMED", "UNKNOWN",
})


def classify_relationship(parent: dict[str, Any], child: dict[str, Any]) -> dict[str, Any]:
    """Describe child behavior relative to parent without forcing agreement."""
    parent_direction = str(parent.get("direction") or "neutral").lower()
    child_direction = str(child.get("direction") or "neutral").lower()
    parent_state = str(parent.get("state") or "unknown").lower()
    child_state = str(child.get("state") or "unknown").lower()
    if parent_direction == "neutral" or child_direction == "neutral":
        relation = "UNKNOWN"
    elif parent_direction == child_direction:
        relation = "CONTINUATION" if child_state in {"breakout", "expansion", "bos"} else "ALIGNED"
    elif child_state in {"compression", "range"}:
        relation = "COMPRESSION"
    elif child_state in {"transition", "choch", "mss"}:
        relation = "TRANSITION_CONFIRMED" if parent_state in {"transition", "choch", "mss"} else "TRANSITION_WARNING"
    elif parent_state in {"trend", "breakout"}:
        relation = "PULLBACK"
    else:
        relation = "COUNTER_MOVE"
    return {"relationship": relation, "parent_direction": parent_direction,
            "child_direction": child_direction, "parent_state": parent_state,
            "child_state": child_state}
