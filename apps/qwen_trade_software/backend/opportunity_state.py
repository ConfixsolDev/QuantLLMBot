"""Deterministic, shadow-only opportunity map.

The map keeps bullish and bearish evidence alive at the same time while Qwen
retains the only discretionary directional commitment.  Live price may move a
branch between ``outside_zone``, ``approaching`` and ``inside_zone``; only a
completed candle on the zone's owning timeframe may prove a trigger or an
invalidation.

This module has no I/O and no execution authority.  It is safe to replay.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


OPPORTUNITY_STATE_VERSION = "1.0-shadow"

OUTSIDE_ZONE = "outside_zone"
APPROACHING = "approaching"
INSIDE_ZONE = "inside_zone"
ARMED = "armed"
TRIGGERED = "triggered"
INVALIDATED = "invalidated"

VALID_SIDES = frozenset({"buy", "sell"})
STRUCTURE_TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15", "M1")
TIMEFRAME_PRIORITY = {
    "D1": 6,
    "H4": 5,
    "H1": 4,
    "M30": 3,
    "M15": 2,
    "M1": 1,
}


@dataclass(frozen=True, slots=True)
class ActiveZone:
    zone_id: str
    side: str
    timeframe: str
    low: float
    high: float
    distance: float
    location_state: str
    role: str = ""
    lifecycle_status: str = "candidate"
    structure_proven: bool = False
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class OpportunityBranch:
    side: str
    state: str
    committed: bool
    zone: ActiveZone | None
    reason: str
    proof_timeframe: str | None = None
    proof_evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["zone"] = self.zone.to_dict() if self.zone else None
        return data


def _float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _zone_side(row: Mapping) -> str | None:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("side", "role", "kind", "pattern", "level_id", "id")
    ).lower()
    explicit = str(row.get("side") or "").lower()
    if explicit in VALID_SIDES:
        return explicit
    if any(token in text for token in ("support", "demand", "previous_low", "swing_low")):
        return "buy"
    if any(token in text for token in ("resistance", "supply", "previous_high", "swing_high")):
        return "sell"
    return None


def _bounds(row: Mapping) -> tuple[float, float] | None:
    price = _float(row.get("price"))
    low = _float(row.get("zone_low"))
    high = _float(row.get("zone_high"))
    if low is None:
        low = price
    if high is None:
        high = price
    if low is None or high is None:
        return None
    if high < low:
        low, high = high, low
    if high == low:
        # A level remains a narrow zone.  The fallback is deliberately relative
        # and only affects location display; it is never structural proof.
        half = max(abs(low) * 0.00005, 1e-9)
        low, high = low - half, high + half
    return low, high


def _distance(price: float, low: float, high: float) -> float:
    if low <= price <= high:
        return 0.0
    return low - price if price < low else price - high


def _location(price: float, low: float, high: float) -> str:
    distance = _distance(price, low, high)
    if distance == 0:
        return INSIDE_ZONE
    width = max(high - low, 1e-9)
    if distance <= width * 1.5:
        return APPROACHING
    return OUTSIDE_ZONE


def build_active_zone_registry(
    levels: Sequence[Mapping],
    *,
    live_price: float,
    per_side_limit: int = 3,
) -> dict:
    """Return a bounded, deduplicated shadow registry around live price.

    Overlapping levels are not counted as independent votes.  For the same
    side and timeframe, intersecting bands collapse to the closest band, with
    structure-proven evidence preferred when distance is equal.
    """
    candidates: list[ActiveZone] = []
    for row in levels or ():
        side = _zone_side(row)
        timeframe = str(row.get("timeframe") or row.get("tf") or "").upper()
        bounds = _bounds(row)
        if side is None or timeframe not in STRUCTURE_TIMEFRAMES or bounds is None:
            continue
        low, high = bounds
        zone_id = str(row.get("zone_id") or row.get("level_id") or row.get("id") or "")
        if not zone_id:
            continue
        evidence = row.get("evidence_ids") or row.get("used_evidence_ids") or ()
        if isinstance(evidence, str):
            evidence = (evidence,)
        candidates.append(ActiveZone(
            zone_id=zone_id,
            side=side,
            timeframe=timeframe,
            low=low,
            high=high,
            distance=_distance(live_price, low, high),
            location_state=_location(live_price, low, high),
            role=str(row.get("role") or row.get("kind") or ""),
            lifecycle_status=str(row.get("lifecycle_status") or row.get("status") or "candidate"),
            structure_proven=bool(row.get("structure_proven") or row.get("proof_event_id")),
            evidence_ids=tuple(str(item) for item in evidence if item)[:8],
        ))

    deduped: list[ActiveZone] = []
    for candidate in sorted(
        candidates,
        key=lambda zone: (
            -int(zone.structure_proven),
            zone.distance,
            -TIMEFRAME_PRIORITY[zone.timeframe],
            zone.zone_id,
        ),
    ):
        overlaps = any(
            kept.side == candidate.side
            and kept.timeframe == candidate.timeframe
            and candidate.low <= kept.high
            and candidate.high >= kept.low
            for kept in deduped
        )
        if not overlaps:
            deduped.append(candidate)

    selected: list[ActiveZone] = []
    for side in ("buy", "sell"):
        side_rows = [zone for zone in deduped if zone.side == side]
        side_rows.sort(
            key=lambda zone: (
                zone.distance,
                -int(zone.structure_proven),
                -TIMEFRAME_PRIORITY[zone.timeframe],
                zone.zone_id,
            )
        )
        selected.extend(side_rows[:max(1, int(per_side_limit))])
    selected.sort(key=lambda zone: (zone.distance, -TIMEFRAME_PRIORITY[zone.timeframe], zone.zone_id))
    return {
        "version": OPPORTUNITY_STATE_VERSION,
        "mode": "shadow_only",
        "execution_authority": False,
        "live_price": live_price,
        "raw_zone_count": len(candidates),
        "deduplicated_zone_count": len(deduped),
        "selected_zone_count": len(selected),
        "zones": [zone.to_dict() for zone in selected],
    }


def _proof_for_side(confirmations: Sequence[Mapping], side: str, zone: ActiveZone) -> Mapping | None:
    for proof in confirmations or ():
        if str(proof.get("side") or "").lower() != side:
            continue
        if str(proof.get("zone_id") or "") != zone.zone_id:
            continue
        if str(proof.get("timeframe") or "").upper() != zone.timeframe:
            continue
        if not bool(proof.get("closed_candle")):
            continue
        if str(proof.get("status") or "confirmed").lower() != "confirmed":
            continue
        return proof
    return None


def evaluate_branch(
    side: str,
    zone: ActiveZone | None,
    *,
    committed_side: str | None,
    owning_timeframe_close: float | None = None,
    confirmations: Sequence[Mapping] = (),
) -> OpportunityBranch:
    """Evaluate one side without manufacturing Qwen commitment or proof."""
    committed = committed_side == side
    if zone is None:
        return OpportunityBranch(side, OUTSIDE_ZONE, committed, None, "no bounded active zone")

    if owning_timeframe_close is not None:
        broken = (
            side == "buy" and owning_timeframe_close < zone.low
        ) or (
            side == "sell" and owning_timeframe_close > zone.high
        )
        if broken:
            return OpportunityBranch(
                side, INVALIDATED, committed, zone,
                f"{zone.timeframe} closed through the zone's invalidation edge",
                proof_timeframe=zone.timeframe,
            )

    proof = _proof_for_side(confirmations, side, zone)
    if proof is not None and committed:
        evidence = proof.get("evidence_ids") or proof.get("used_evidence_ids") or ()
        if isinstance(evidence, str):
            evidence = (evidence,)
        return OpportunityBranch(
            side, TRIGGERED, True, zone,
            "Qwen-committed side has owning-timeframe closed-candle proof",
            proof_timeframe=zone.timeframe,
            proof_evidence_ids=tuple(str(item) for item in evidence if item)[:8],
        )

    if committed and zone.location_state in (APPROACHING, INSIDE_ZONE):
        return OpportunityBranch(
            side, ARMED, True, zone,
            "Qwen-committed side is at its mapped zone and awaits closed-candle proof",
        )
    return OpportunityBranch(
        side, zone.location_state, committed, zone,
        "analytical branch only; Qwen has not committed this side" if not committed
        else "committed side remains outside its mapped zone",
    )


def build_opportunity_shadow(
    levels: Sequence[Mapping],
    *,
    live_price: float,
    committed_side: str | None = None,
    closed_prices_by_timeframe: Mapping[str, float] | None = None,
    confirmations: Sequence[Mapping] = (),
) -> dict:
    """Build the two-sided evidence packet and one-sided commitment view."""
    committed_side = str(committed_side or "").lower() or None
    if committed_side not in VALID_SIDES:
        committed_side = None
    registry = build_active_zone_registry(levels, live_price=live_price)
    zones = [ActiveZone(**row) for row in registry["zones"]]
    closed = {str(key).upper(): _float(value) for key, value in (closed_prices_by_timeframe or {}).items()}

    branches: dict[str, dict] = {}
    triggered: list[str] = []
    for side in ("buy", "sell"):
        zone = next((item for item in zones if item.side == side), None)
        branch = evaluate_branch(
            side,
            zone,
            committed_side=committed_side,
            owning_timeframe_close=closed.get(zone.timeframe) if zone else None,
            confirmations=confirmations,
        )
        branches[side] = branch.to_dict()
        if branch.state == TRIGGERED:
            triggered.append(side)

    shadow_side = triggered[0] if len(triggered) == 1 else None
    return {
        "version": OPPORTUNITY_STATE_VERSION,
        "mode": "shadow_only",
        "execution_authority": False,
        "committed_side": committed_side or "wait",
        "shadow_triggered_side": shadow_side,
        "decision": shadow_side or "wait",
        "branches": branches,
        "active_zone_registry": registry,
    }


def qwen_committed_side(planner: Mapping) -> str | None:
    """Read an existing Qwen thesis without creating a deterministic bias.

    Lower timeframes are preferred because they represent the latest qualified
    layer.  Placeholder or terminal ideas do not count as commitments.
    """
    stack = planner.get("trade_idea_stack") or {}
    if not isinstance(stack, Mapping):
        return None
    for timeframe in ("m15", "h1", "h4"):
        idea = stack.get(timeframe)
        if not isinstance(idea, Mapping):
            continue
        side = str(idea.get("side") or "").lower()
        status = str(idea.get("status") or "active").lower()
        thesis = str(idea.get("thesis") or idea.get("summary") or "").strip().lower()
        if side not in VALID_SIDES or status in {"invalidated", "expired", "resolved", "spent"}:
            continue
        if thesis in {"", "none", "no_evidence"}:
            continue
        return side
    return None
