"""Trade idea lifecycle state machine.

A trade idea is not a single signal — it's a lifecycle that mirrors how
professional traders think about the market:

    STALKING  →  AT_ZONE  →  ARMED  →  RESOLVED
       ↑            |           |          |
       └────────────┴───────────┘          │
            (invalidated → new idea)       │
                                           ↓
                                    feeds next idea

States:
    STALKING   — Zone identified, watching price approach. Model builds
                 conviction based on approach quality.
    AT_ZONE    — Price has reached the target zone. Evaluating reaction
                 quality (M5 failure, CHoCH, volume).
    ARMED      — Reaction confirmed. Entry conditions met, executor
                 attempting to fill.
    RESOLVED   — Idea completed. Either traded (with P&L) or invalidated
                 (with reason). Resolution context feeds the next idea.

Each resolved idea produces a `resolution_context` dict that chains into
the next idea's `prior_idea_context`. This gives the model memory:
"I was watching 4410 sell, price broke through → now watching 4420 sell."

Symbol-agnostic. Strategy-agnostic. Serializable for persistence.

References:
    - ICT Power of Three — accumulation/manipulation/distribution phases
    - Al Brooks — context carries across bars, not independent signals
    - Lance Beggs YTC — setup phase → trigger phase → execution

Usage:
    from idea_lifecycle import IdeaManager

    mgr = IdeaManager()
    idea = mgr.create_idea(
        zone_id="M15_L_4380", side="buy",
        zone_low=4379.5, zone_high=4381.0,
        thesis="Demand zone with 2 prior rejections",
    )
    mgr.transition(idea.idea_id, "at_zone", reason="price_reached")
    mgr.transition(idea.idea_id, "armed", reason="m5_failure_confirmed")
    mgr.resolve(idea.idea_id, outcome="traded", pnl=15.5)
    ctx = mgr.prior_idea_context()  # feeds into next Qwen call
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# A watched execution zone is short-lived market state, not a permanent
# directional thesis.  These defaults cover several entry-review cycles while
# forcing a remap when the market has plainly moved on.
MAX_ACTIVE_IDEA_AGE_SECONDS = 30 * 60
MAX_MISSING_LEVEL_AGE_SECONDS = 2 * 60
MIN_ZONE_DEPARTURE_POINTS = 5.0
ZONE_DEPARTURE_WIDTHS = 3.0


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class IdeaState(str, Enum):
    STALKING = "stalking"
    AT_ZONE = "at_zone"
    ARMED = "armed"
    RESOLVED = "resolved"

    def __str__(self) -> str:
        return self.value


VALID_TRANSITIONS: dict[IdeaState, set[IdeaState]] = {
    IdeaState.STALKING: {IdeaState.AT_ZONE, IdeaState.RESOLVED},
    IdeaState.AT_ZONE: {IdeaState.ARMED, IdeaState.STALKING, IdeaState.RESOLVED},
    IdeaState.ARMED: {IdeaState.RESOLVED, IdeaState.AT_ZONE},
    IdeaState.RESOLVED: set(),  # terminal
}


# ---------------------------------------------------------------------------
# Trade Idea
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TradeIdea:
    """One trade idea moving through the lifecycle."""

    idea_id: str
    zone_id: str
    side: str                                  # "buy" or "sell"
    zone_low: float
    zone_high: float
    thesis: str                                # ≤160 chars, why this zone
    state: IdeaState = IdeaState.STALKING
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # Accumulated context through the lifecycle
    approach_summary: dict[str, Any] = field(default_factory=dict)
    zone_score: dict[str, Any] = field(default_factory=dict)
    reaction_detail: dict[str, Any] = field(default_factory=dict)

    # Resolution
    outcome: str = ""                          # "traded", "invalidated", "expired"
    resolution_reason: str = ""                # why it resolved
    pnl: float | None = None

    # Chain
    prior_idea_id: str | None = None           # what idea came before this one
    transition_log: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "idea_id": self.idea_id,
            "zone_id": self.zone_id,
            "side": self.side,
            "zone": [self.zone_low, self.zone_high],
            "thesis": self.thesis,
            "state": str(self.state),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "approach_summary": self.approach_summary,
            "zone_score": self.zone_score,
            "reaction_detail": self.reaction_detail,
            "outcome": self.outcome,
            "resolution_reason": self.resolution_reason,
            "pnl": self.pnl,
            "prior_idea_id": self.prior_idea_id,
            "transition_count": len(self.transition_log),
        }

    def compact_log(self) -> str:
        return (
            f"idea:{self.idea_id[:12]} zone={self.zone_id} "
            f"side={self.side} state={self.state} "
            f"outcome={self.outcome or 'pending'}"
        )


# ---------------------------------------------------------------------------
# Idea Manager
# ---------------------------------------------------------------------------

class IdeaManager:
    """Manages the lifecycle of trade ideas with chaining.

    Maintains at most one active idea at a time (STALKING/AT_ZONE/ARMED).
    Resolved ideas are kept in a history ring for context chaining.

    Thread-safe: no. Call from a single process only.
    """

    def __init__(self, max_history: int = 10) -> None:
        self._active: TradeIdea | None = None
        self._history: list[TradeIdea] = []
        self._max_history = max_history

    @property
    def active_idea(self) -> TradeIdea | None:
        return self._active

    @property
    def has_active(self) -> bool:
        return self._active is not None

    @property
    def history(self) -> list[TradeIdea]:
        return list(self._history)

    def create_idea(
        self,
        zone_id: str,
        side: str,
        zone_low: float,
        zone_high: float,
        thesis: str,
        zone_score: dict[str, Any] | None = None,
    ) -> TradeIdea:
        """Create a new trade idea in STALKING state.

        If an active idea already exists, it is auto-resolved as 'superseded'.
        """
        if self._active is not None:
            self.resolve(
                self._active.idea_id,
                outcome="superseded",
                reason=f"new_idea_for_{zone_id}",
            )

        prior_id = self._history[-1].idea_id if self._history else None

        idea = TradeIdea(
            idea_id=_short_id(),
            zone_id=zone_id,
            side=side,
            zone_low=zone_low,
            zone_high=zone_high,
            thesis=thesis[:160],
            zone_score=zone_score or {},
            prior_idea_id=prior_id,
        )
        idea.transition_log.append({
            "from": None,
            "to": str(IdeaState.STALKING),
            "reason": "created",
            "at": idea.created_at,
        })

        self._active = idea
        return idea

    def transition(
        self,
        idea_id: str,
        to_state: str | IdeaState,
        reason: str = "",
        detail: dict[str, Any] | None = None,
    ) -> TradeIdea:
        """Move the active idea to a new state.

        Raises ValueError if the transition is invalid.
        """
        idea = self._active
        if idea is None or idea.idea_id != idea_id:
            raise ValueError(f"No active idea with id {idea_id}")

        target = IdeaState(to_state) if isinstance(to_state, str) else to_state
        if target not in VALID_TRANSITIONS[idea.state]:
            raise ValueError(
                f"Invalid transition {idea.state} → {target}. "
                f"Valid: {VALID_TRANSITIONS[idea.state]}"
            )

        now = time.time()
        idea.transition_log.append({
            "from": str(idea.state),
            "to": str(target),
            "reason": reason,
            "detail": detail,
            "at": now,
        })
        idea.state = target
        idea.updated_at = now

        if target == IdeaState.RESOLVED:
            self._finalize(idea, reason)

        return idea

    def resolve(
        self,
        idea_id: str,
        outcome: str = "invalidated",
        reason: str = "",
        pnl: float | None = None,
    ) -> TradeIdea:
        """Resolve the active idea — terminal state.

        Outcomes: "traded", "invalidated", "expired", "superseded"
        """
        idea = self._active
        if idea is None or idea.idea_id != idea_id:
            raise ValueError(f"No active idea with id {idea_id}")

        if idea.state == IdeaState.RESOLVED:
            return idea  # already resolved

        now = time.time()
        idea.transition_log.append({
            "from": str(idea.state),
            "to": str(IdeaState.RESOLVED),
            "reason": reason,
            "outcome": outcome,
            "at": now,
        })
        idea.state = IdeaState.RESOLVED
        idea.outcome = outcome
        idea.resolution_reason = reason
        idea.pnl = pnl
        idea.updated_at = now
        self._finalize(idea, reason)
        return idea

    def update_approach(
        self,
        idea_id: str,
        approach_summary: dict[str, Any],
    ) -> None:
        """Attach approach tracker snapshot to the active idea."""
        if self._active and self._active.idea_id == idea_id:
            self._active.approach_summary = approach_summary
            self._active.updated_at = time.time()

    def update_reaction(
        self,
        idea_id: str,
        reaction_detail: dict[str, Any],
    ) -> None:
        """Attach reaction evaluation to the active idea at AT_ZONE/ARMED."""
        if self._active and self._active.idea_id == idea_id:
            self._active.reaction_detail = reaction_detail
            self._active.updated_at = time.time()

    def invalidate_on_closed_acceptance(
        self,
        closed_price: float | None,
        evidence_id: str | None = None,
    ) -> TradeIdea | None:
        """Resolve a directional idea when a closed bar accepts beyond its zone.

        Wicks and forming prices are intentionally ignored by the caller. This
        removes stale directional memory before the next model assessment.
        """
        idea = self._active
        if idea is None or closed_price is None:
            return None
        try:
            price = float(closed_price)
        except (TypeError, ValueError):
            return None
        crossed = (
            idea.side == "sell" and price > idea.zone_high
        ) or (
            idea.side == "buy" and price < idea.zone_low
        )
        if not crossed:
            return None
        boundary = idea.zone_high if idea.side == "sell" else idea.zone_low
        reason = (
            f"closed_acceptance_broke_through_{idea.side}_zone "
            f"close={price:.3f} boundary={boundary:.3f}"
        )
        if evidence_id:
            reason += f" evidence={evidence_id}"
        return self.resolve(idea.idea_id, outcome="invalidated", reason=reason)

    def recover_stale(
        self,
        closed_price: float | None,
        *,
        current_level_ids: set[str] | None = None,
        now: float | None = None,
        max_age_seconds: float = MAX_ACTIVE_IDEA_AGE_SECONDS,
        missing_level_age_seconds: float = MAX_MISSING_LEVEL_AGE_SECONDS,
    ) -> TradeIdea | None:
        """Resolve stale execution memory so the next cycle remaps the market.

        Directional invalidation and freshness are deliberately separate:
        a buy idea is invalidated by acceptance below support, but it also
        becomes stale when price rallies far beyond an unfilled support zone.
        The latter is a missed/finished opportunity, not a bearish signal.

        Recovery triggers are deterministic and based only on a closed price:
        excessive lifetime, disappearance from the current level map, or a
        favorable traversal away from the watched entry zone.  Forming quotes
        never resolve an idea.
        """
        idea = self._active
        if idea is None:
            return None
        clock = float(now if now is not None else time.time())
        age = max(0.0, clock - float(idea.created_at or clock))

        reason = ""
        outcome = "expired"
        if age > max_age_seconds:
            reason = f"stale:max_age age_seconds={age:.1f}"
        elif (
            current_level_ids is not None
            and idea.zone_id not in current_level_ids
            and age > missing_level_age_seconds
        ):
            reason = (
                f"stale:level_no_longer_current zone={idea.zone_id} "
                f"age_seconds={age:.1f}"
            )
        elif closed_price is not None:
            try:
                price = float(closed_price)
            except (TypeError, ValueError):
                price = 0.0
            width = max(0.0, idea.zone_high - idea.zone_low)
            departure = max(
                MIN_ZONE_DEPARTURE_POINTS,
                width * ZONE_DEPARTURE_WIDTHS,
            )
            favorable_distance = (
                price - idea.zone_high
                if idea.side == "buy"
                else idea.zone_low - price
            )
            if price > 0 and favorable_distance >= departure:
                outcome = "missed"
                reason = (
                    f"stale:zone_traversed_without_fill close={price:.3f} "
                    f"distance={favorable_distance:.3f} threshold={departure:.3f}"
                )

        if not reason:
            return None
        return self.resolve(idea.idea_id, outcome=outcome, reason=reason)

    def prior_idea_context(self) -> dict[str, Any]:
        """Build context from the last resolved idea for the next Qwen call.

        This is the chain link: what the model was doing before, why it
        ended, and what changed. Enables idea continuity.
        """
        if not self._history:
            return {"has_prior": False}

        last = self._history[-1]
        ctx: dict[str, Any] = {
            "has_prior": True,
            "prior_idea_id": last.idea_id,
            "prior_zone_id": last.zone_id,
            "prior_side": last.side,
            "prior_zone": [last.zone_low, last.zone_high],
            "prior_thesis": last.thesis,
            "prior_outcome": last.outcome,
            "prior_resolution_reason": last.resolution_reason,
            "prior_pnl": last.pnl,
            "prior_approach": last.approach_summary,
            "prior_duration_seconds": round(
                last.updated_at - last.created_at, 1
            ),
            "prior_transition_count": len(last.transition_log),
        }

        # If the zone was invalidated by a break, the model should know
        # that the broken level is now potential support/resistance
        if last.outcome == "invalidated" and "broke_through" in last.resolution_reason:
            ctx["broken_level_becomes_sr"] = True
            ctx["broken_zone"] = [last.zone_low, last.zone_high]
            ctx["broken_side"] = last.side

        return ctx

    def active_idea_for_facts(self) -> dict[str, Any]:
        """Serialize the active idea for inclusion in Qwen entry facts.

        Returns empty dict if no active idea.
        """
        if self._active is None:
            return {}
        return {
            "active_idea": self._active.to_dict(),
            "state": str(self._active.state),
            "watching_zone": self._active.zone_id,
            "watching_side": self._active.side,
        }

    # -- Persistence --

    def to_state(self) -> dict[str, Any]:
        """Serialize for file/DB persistence across restarts."""
        return {
            "active": self._active.to_dict() if self._active else None,
            "active_transitions": (
                self._active.transition_log if self._active else []
            ),
            "history": [h.to_dict() for h in self._history],
        }

    @classmethod
    def from_state(cls, state: dict[str, Any], max_history: int = 10) -> IdeaManager:
        """Restore from persisted state."""
        mgr = cls(max_history=max_history)
        for raw in state.get("history", []):
            mgr._history.append(_idea_from_dict(raw))
        raw_active = state.get("active")
        if raw_active and raw_active.get("state") != "resolved":
            idea = _idea_from_dict(raw_active)
            idea.transition_log = state.get("active_transitions", [])
            mgr._active = idea
        return mgr

    # -- Internal --

    def _finalize(self, idea: TradeIdea, reason: str) -> None:
        self._history.append(idea)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]
        if self._active is idea:
            self._active = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_id() -> str:
    return uuid.uuid4().hex[:12]


def _idea_from_dict(raw: dict[str, Any]) -> TradeIdea:
    zone = raw.get("zone", [0.0, 0.0])
    return TradeIdea(
        idea_id=raw.get("idea_id", _short_id()),
        zone_id=raw.get("zone_id", ""),
        side=raw.get("side", ""),
        zone_low=float(zone[0]) if isinstance(zone, list) else float(raw.get("zone_low", 0)),
        zone_high=float(zone[1]) if isinstance(zone, list) else float(raw.get("zone_high", 0)),
        thesis=raw.get("thesis", ""),
        state=IdeaState(raw.get("state", "resolved")),
        created_at=float(raw.get("created_at", 0)),
        updated_at=float(raw.get("updated_at", 0)),
        approach_summary=raw.get("approach_summary", {}),
        zone_score=raw.get("zone_score", {}),
        reaction_detail=raw.get("reaction_detail", {}),
        outcome=raw.get("outcome", ""),
        resolution_reason=raw.get("resolution_reason", ""),
        pnl=raw.get("pnl"),
        prior_idea_id=raw.get("prior_idea_id"),
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    mgr = IdeaManager()
    assert not mgr.has_active

    # Create
    idea = mgr.create_idea(
        zone_id="M15_L_4380", side="buy",
        zone_low=4379.5, zone_high=4381.0,
        thesis="Demand zone with 2 prior rejections, first touch",
        zone_score={"total": 10, "grade": "A"},
    )
    assert mgr.has_active
    assert idea.state == IdeaState.STALKING

    # Transition to AT_ZONE
    mgr.transition(idea.idea_id, "at_zone", reason="price_reached_zone")
    assert idea.state == IdeaState.AT_ZONE

    # Update approach
    mgr.update_approach(idea.idea_id, {"distance_trend": "closing", "speed": "slow"})
    assert idea.approach_summary["speed"] == "slow"

    # Transition to ARMED
    mgr.transition(idea.idea_id, "armed", reason="m5_failure_confirmed")
    assert idea.state == IdeaState.ARMED

    # Resolve as traded
    mgr.resolve(idea.idea_id, outcome="traded", reason="filled_at_4380.5", pnl=15.5)
    assert idea.state == IdeaState.RESOLVED
    assert idea.pnl == 15.5
    assert not mgr.has_active

    # Prior context chains
    ctx = mgr.prior_idea_context()
    assert ctx["has_prior"]
    assert ctx["prior_zone_id"] == "M15_L_4380"
    assert ctx["prior_outcome"] == "traded"
    assert ctx["prior_pnl"] == 15.5

    # Create second idea — should chain
    idea2 = mgr.create_idea(
        zone_id="M15_H_4420", side="sell",
        zone_low=4419.0, zone_high=4421.0,
        thesis="Supply zone after buy target hit",
    )
    assert idea2.prior_idea_id == idea.idea_id

    # Invalid transition
    try:
        mgr.transition(idea2.idea_id, "armed", reason="skip_at_zone")
        assert False, "should raise ValueError"
    except ValueError:
        pass

    # Supersede by creating new idea
    idea3 = mgr.create_idea(
        zone_id="M15_L_4400", side="buy",
        zone_low=4399.0, zone_high=4401.0,
        thesis="Superseding previous idea",
    )
    assert len(mgr.history) == 2  # idea (traded), idea2 (superseded); idea3 is active

    # Serialize / restore
    state = mgr.to_state()
    restored = IdeaManager.from_state(state)
    assert restored.has_active
    assert restored.active_idea.zone_id == "M15_L_4400"
    assert len(restored.history) == 2

    # Active idea for facts
    facts = restored.active_idea_for_facts()
    assert facts["watching_zone"] == "M15_L_4400"


if __name__ == "__main__":
    self_test()
    print("idea_lifecycle: all tests passed")
