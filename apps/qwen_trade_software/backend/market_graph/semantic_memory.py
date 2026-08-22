"""Deterministic lifecycle gates for zone-relevant semantic market memory."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

PROBATION_DAYS = 7


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def evaluate_memory(memory: dict, as_of_utc: str) -> dict:
    """Apply simple unique-episode counts; nested multi-TF evidence is one episode."""
    row = dict(memory)
    created = _utc(row["probation_started_at_utc"])
    as_of = _utc(as_of_utc)
    supports = set(row.get("supporting_episode_ids") or [])
    contradictions = set(row.get("contradicting_episode_ids") or [])
    state = str(row.get("state") or "candidate")
    human_locked = bool(row.get("human_locked"))

    if state in {"candidate", "retired"} and row.get("reactivate"):
        state, created, human_locked = "probation", as_of, False
    elif state == "candidate":
        state = "probation"

    probation_end = created + timedelta(days=PROBATION_DAYS)
    if state == "probation" and as_of < probation_end and len(contradictions) >= len(supports):
        state = "retired"
    elif state == "probation" and as_of >= probation_end:
        state, human_locked = "established", True

    row.update({
        "state": state,
        "probation_started_at_utc": created.isoformat().replace("+00:00", "Z"),
        "probation_ends_at_utc": probation_end.isoformat().replace("+00:00", "Z"),
        "supporting_episode_count": len(supports),
        "contradicting_episode_count": len(contradictions),
        "human_locked": human_locked,
        "execution_authority": False,
    })
    return row


def relevant_for_zone(memories: list[dict], zone: dict | None, limit: int = 1) -> list[dict]:
    if not zone:
        return []
    zone_id = zone.get("zone_id")
    ranked = [row for row in memories if row.get("state") in {"probation", "established"}
              and (row.get("zone_id") == zone_id or row.get("price_area_id") == zone_id)]
    ranked.sort(key=lambda row: (row.get("relevance", 0), row.get("timeframe_rank", 0)), reverse=True)
    return ranked[:max(0, limit)]
