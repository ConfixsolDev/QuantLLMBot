"""Stage 4: in-trade management policy.

The entry invalidation is immutable after fill. Management may close early on
confirmed invalidation or tighten the stop behind newly completed structure,
but it may never increase the risk accepted at entry. Qwen may move a target in
either direction to an exact supplied level after deterministic evidence
validation; a reduced target must remain beyond the executable price.

Pure functions only. No MT5, no model call, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Mapping, Sequence


MANAGEMENT_VERSION = "4.0"

# --- regime configuration --------------------------------------------------
STOP_POLICY_FULL = "full_discretion"
STOP_POLICY_TIGHTEN_ONLY = "tighten_only"
STOP_POLICY_WIDEN_ONCE = "widen_once_to_structure"

TARGET_POLICY_FULL = "full_discretion"
TARGET_POLICY_FIXED = "fixed_at_entry"
TARGET_POLICY_EXTEND_ONLY = "extend_only"

# Live professional-capital-protection regime.
STOP_POLICY = STOP_POLICY_TIGHTEN_ONLY
TARGET_POLICY = TARGET_POLICY_FULL

# Solvency rail. Applies regardless of policy: the live stop may never place
# more than this multiple of the originally accepted risk at stake.
MAX_RISK_MULTIPLE = 1.75

# A widened stop must still be justified by a named structural level rather
# than a round number pulled from nowhere.
REQUIRE_NAMED_LEVEL_TO_WIDEN = True

# Cap on how many times a single position may have its stop widened, so a
# trade cannot be nursed indefinitely.
MAX_WIDENINGS_PER_POSITION = 2

# --- mandatory initial re-bracket ------------------------------------------
# Operator requirement (2026-08-10): within 30s of fill, BOTH stop and target
# must be rewritten to structure, regardless of what the broker bracket
# currently holds.
#
# The evidence supports this directly. Across the last seven closed trades the
# only column that separated winners from losers was how far the live stop sat
# INSIDE the structural invalidation:
#
#     +246.50  stop exactly ON structural (0.000)   -> reached target
#     +246.50  stop exactly ON structural (0.000)   -> reached target
#     +249.15  0.274 inside                          -> reached target
#     -153.50  0.423 inside, frame gap 6             -> stopped out
#     -153.50  3.708 inside                          -> stopped out in 81s
#
# CRITICAL DESIGN POINT: this re-bracket must be computed in CODE from levels
# already present on the proposal. It must NOT wait for a model call. Management
# cycles every 30s and inference takes 16-31s, so a model-gated re-bracket
# cannot meet a 30s deadline -- the two fastest stop-outs today died in 22s and
# 50s, before any review completed. Deterministic placement is the only thing
# fast enough to matter.
INITIAL_REBRACKET_SECONDS = 30.0

# The initial re-bracket is exempt from the tighten/widen direction policy --
# it is a correction of the entry bracket, not a discretionary adjustment. It
# remains bound by the risk ceiling below; if structure demands more room than
# the ceiling allows, the stop is clipped and the clip is reported rather than
# silently swallowed.
REBRACKET_RESPECTS_RISK_CEILING = True

# Time stop: a frame's thesis should resolve within a bounded window.
TIME_STOP_SECONDS = {
    "M1": 15 * 60, "M5": 45 * 60, "M15": 2 * 3600,
    "M30": 4 * 3600, "H1": 8 * 3600, "H4": 24 * 3600, "D1": 72 * 3600,
}
DEFAULT_TIME_STOP_SECONDS = 4 * 3600


class ExitReason:
    """Deterministic exit taxonomy. Every close maps to exactly one.

    The discretionary reasons (R1-R4) come from topic 10, distilled from the
    corpus. Management MAY close whenever the idea is genuinely dead -- that is
    doctrinally correct and explicitly permitted:

        Grimes p.172: "developing price action may suggest that the trend is
        losing integrity ... it is often advisable to scratch the trade,
        exiting for a small win or loss"

    What it may not do is close because the position is uncomfortable. Douglas
    p.99 gives the mechanism: a holder who fears losing "will gather information
    against the trade", i.e. manufactures the justification it already wants.
    That is what our -20.22 average discretionary close most likely is.

    So each discretionary close must name WHICH condition ended the trade, and
    the condition must be checkable against closed price rather than P&L.
    """

    # Mechanical -- evaluated before anything discretionary.
    TARGET_REACHED = "exit:target_reached"
    STOP_HIT = "exit:stop_hit"
    RISK_CEILING = "exit:risk_ceiling_breached"
    SESSION_END = "exit:session_end"
    EXTERNAL = "exit:external"

    # R1: the named invalidation failed on a closed candle of its own timeframe.
    INVALIDATION_CLOSED_THROUGH = "exit:invalidation_closed_through"
    # R2: always-in flip -- the opposite entry would now be taken with
    # confidence, at a named level, with its own closed response.
    ALWAYS_IN_FLIP = "exit:always_in_flip"
    # R3: remaining reward no longer clears remaining risk (trader's equation).
    REWARD_RISK_INVERTED = "exit:reward_risk_inverted"
    # R4: the frame's time budget expired with no structural progress.
    TIME_STOP = "exit:time_stop"

    # R5 violation: a close whose only support is unrealised P&L. Recorded so it
    # can be counted, not silently accepted.
    UNJUSTIFIED_DISCRETION = "exit:unjustified_discretion"


# Discretionary closes the model is permitted to request, per topic 10.
JUSTIFIED_DISCRETION = frozenset({
    ExitReason.INVALIDATION_CLOSED_THROUGH,
    ExitReason.ALWAYS_IN_FLIP,
    ExitReason.REWARD_RISK_INVERTED,
    ExitReason.TIME_STOP,
})

# R4 companion: time alone never closes a working trade (Dalton -- a thesis can
# be correct and dormant). Progress below this fraction counts as "not working".
TIME_STOP_MAX_PROGRESS = 0.15

# R3 floor. Brooks' "significantly greater" is not a number; topic 10 Gap 2
# records that. Until measured, the entry-time minimum is the floor.
MIN_REMAINING_REWARD_RISK = 0.75


class AdjustReason:
    OK = "adjust:ok"
    REBRACKET_OK = "adjust:initial_rebracket"
    REBRACKET_CLIPPED = "adjust:initial_rebracket_clipped_to_ceiling"
    REBRACKET_MISSING_STRUCTURE = "adjust:initial_rebracket_no_structure"
    REBRACKET_OVERDUE = "adjust:initial_rebracket_overdue"
    NO_CHANGE = "adjust:no_change"
    REJECTED_RISK_CEILING = "adjust:rejected_risk_ceiling"
    REJECTED_UNNAMED_LEVEL = "adjust:rejected_unnamed_level"
    REJECTED_WIDEN_LIMIT = "adjust:rejected_widen_limit"
    REJECTED_WRONG_SIDE = "adjust:rejected_wrong_side"
    REJECTED_BY_POLICY = "adjust:rejected_by_policy"


@dataclass(frozen=True)
class Position:
    """Minimal view of a live position that this module needs."""

    side: str                    # "buy" | "sell"
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    opened_at: float             # epoch seconds
    frame: str | None = None
    initial_stop_distance: float = 0.0
    widenings: int = 0
    value_per_price_unit_per_lot: float = 100.0
    # None until the mandatory post-fill re-bracket has been applied.
    rebracketed_at: float | None = None

    @property
    def initial_risk(self) -> float:
        distance = self.initial_stop_distance or abs(self.entry_price - self.stop_loss)
        return distance * self.value_per_price_unit_per_lot * self.volume

    def risk_at(self, stop_loss: float) -> float:
        return abs(self.entry_price - stop_loss) * self.value_per_price_unit_per_lot * self.volume

    def unrealised(self, price: float) -> float:
        direction = 1.0 if self.side == "buy" else -1.0
        return direction * (price - self.entry_price) * self.value_per_price_unit_per_lot * self.volume


@dataclass(frozen=True)
class Adjustment:
    """One proposed change to a live position, accepted or rejected."""

    accepted: bool
    reason_code: str
    field_changed: str | None = None      # "stop_loss" | "take_profit"
    old_value: float = 0.0
    new_value: float = 0.0
    direction: str | None = None          # "tighten" | "widen" | "extend" | "reduce"
    level_id: str | None = None
    risk_before: float = 0.0
    risk_after: float = 0.0
    unrealised_at_change: float = 0.0
    detail: str = ""
    management_version: str = MANAGEMENT_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Rebracket:
    """Result of the mandatory post-fill bracket correction."""

    applied: bool
    reason_code: str
    stop: Adjustment | None = None
    target: Adjustment | None = None
    clipped: bool = False
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "applied": self.applied,
            "reason_code": self.reason_code,
            "clipped": self.clipped,
            "detail": self.detail,
            "stop": self.stop.as_dict() if self.stop else None,
            "target": self.target.as_dict() if self.target else None,
        }


def needs_initial_rebracket(position: Position, now: float) -> bool:
    """True while the mandatory post-fill re-bracket is still outstanding."""
    return position.rebracketed_at is None


def rebracket_overdue(position: Position, now: float) -> bool:
    """True when the 30s deadline passed without the re-bracket being applied."""
    return (
        position.rebracketed_at is None
        and (now - position.opened_at) > INITIAL_REBRACKET_SECONDS
    )


def initial_rebracket(
    position: Position,
    *,
    price: float,
    structural_stop: float | None,
    structural_target: float | None,
    now: float,
    stop_level_id: str | None = None,
    target_level_id: str | None = None,
) -> Rebracket:
    """Rewrite BOTH stop and target to structure within 30s of fill.

    Runs once per position, exempt from the tighten/widen direction policy,
    because it corrects the entry bracket rather than exercising discretion.
    Deterministic: takes structural levels supplied by the caller and performs
    no model call, so it can complete inside the deadline.

    The risk ceiling still applies. If structure needs more room than the
    ceiling permits, the stop is clipped to the ceiling and ``clipped`` is set
    so the shortfall is visible rather than silently absorbed.
    """
    if position.rebracketed_at is not None:
        return Rebracket(False, AdjustReason.NO_CHANGE,
                         detail="already re-bracketed")
    if structural_stop is None and structural_target is None:
        return Rebracket(False, AdjustReason.REBRACKET_MISSING_STRUCTURE,
                         detail="no structural stop or target supplied")

    direction = 1.0 if position.side == "buy" else -1.0
    clipped = False
    stop_adjustment = None
    target_adjustment = None

    if structural_stop is not None:
        new_stop = float(structural_stop)
        # Ceiling check -- the only bound on the mandatory correction.
        if REBRACKET_RESPECTS_RISK_CEILING:
            ceiling_risk = position.initial_risk * MAX_RISK_MULTIPLE
            if position.risk_at(new_stop) > ceiling_risk > 0:
                max_distance = ceiling_risk / (
                    position.value_per_price_unit_per_lot * position.volume
                )
                new_stop = position.entry_price - direction * max_distance
                clipped = True
        # Never place a stop already through price.
        if direction * (price - new_stop) > 0:
            stop_adjustment = Adjustment(
                accepted=True,
                reason_code=(AdjustReason.REBRACKET_CLIPPED if clipped
                             else AdjustReason.REBRACKET_OK),
                field_changed="stop_loss",
                old_value=position.stop_loss,
                new_value=round(new_stop, 3),
                direction=("tighten" if _is_tightening(position.side,
                                                       position.stop_loss, new_stop)
                           else "widen"),
                level_id=stop_level_id,
                risk_before=position.risk_at(position.stop_loss),
                risk_after=position.risk_at(new_stop),
                unrealised_at_change=position.unrealised(price),
                detail=(f"post-fill re-bracket to structure "
                        f"{position.stop_loss:.3f} -> {new_stop:.3f}"
                        + (" (clipped to risk ceiling)" if clipped else "")),
            )

    if structural_target is not None:
        new_target = float(structural_target)
        if direction * (new_target - price) > 0:
            target_adjustment = Adjustment(
                accepted=True,
                reason_code=AdjustReason.REBRACKET_OK,
                field_changed="take_profit",
                old_value=position.take_profit,
                new_value=round(new_target, 3),
                direction=("extend"
                           if direction * (new_target - position.take_profit) > 0
                           else "reduce"),
                level_id=target_level_id,
                unrealised_at_change=position.unrealised(price),
                detail=(f"post-fill re-bracket to structure "
                        f"{position.take_profit:.3f} -> {new_target:.3f}"),
            )

    if not stop_adjustment and not target_adjustment:
        return Rebracket(False, AdjustReason.REBRACKET_MISSING_STRUCTURE,
                         detail="structural levels are already through price")

    return Rebracket(
        applied=True,
        reason_code=(AdjustReason.REBRACKET_CLIPPED if clipped
                     else AdjustReason.REBRACKET_OK),
        stop=stop_adjustment,
        target=target_adjustment,
        clipped=clipped,
        detail=f"re-bracketed {(now - position.opened_at):.1f}s after fill",
    )


def apply_rebracket(position: Position, rebracket: Rebracket, now: float) -> Position:
    """Apply both legs of the re-bracket and mark the position as corrected."""
    if not rebracket.applied:
        return position
    updated = position
    if rebracket.stop:
        updated = apply(updated, rebracket.stop)
    if rebracket.target:
        updated = apply(updated, rebracket.target)
    return Position(
        side=updated.side,
        entry_price=updated.entry_price,
        stop_loss=updated.stop_loss,
        take_profit=updated.take_profit,
        volume=updated.volume,
        opened_at=updated.opened_at,
        frame=updated.frame,
        # The structural stop becomes the reference risk from here on, so later
        # tighten/widen decisions are measured against the corrected bracket.
        initial_stop_distance=abs(updated.entry_price - updated.stop_loss),
        widenings=updated.widenings,
        value_per_price_unit_per_lot=updated.value_per_price_unit_per_lot,
        rebracketed_at=now,
    )


def _is_tightening(side: str, old_stop: float, new_stop: float) -> bool:
    """True when the new stop sits closer to price in the profitable direction."""
    return (new_stop > old_stop) if side == "buy" else (new_stop < old_stop)


def propose_stop(
    position: Position,
    new_stop: float,
    *,
    price: float,
    level_id: str | None = None,
    policy: str = None,
) -> Adjustment:
    """Validate a stop change. Honours the configured policy plus the risk ceiling."""
    policy = policy or STOP_POLICY
    old_stop = position.stop_loss
    risk_before = position.risk_at(old_stop)
    risk_after = position.risk_at(new_stop)
    unrealised = position.unrealised(price)

    def reject(code: str, detail: str) -> Adjustment:
        return Adjustment(
            accepted=False, reason_code=code, field_changed="stop_loss",
            old_value=old_stop, new_value=new_stop, level_id=level_id,
            risk_before=risk_before, risk_after=risk_after,
            unrealised_at_change=unrealised, detail=detail,
        )

    if abs(new_stop - old_stop) < 1e-9:
        return reject(AdjustReason.NO_CHANGE, "stop unchanged")

    # The stop must remain on the correct side of the entry-to-price geometry.
    direction = 1.0 if position.side == "buy" else -1.0
    if direction * (price - new_stop) <= 0:
        return reject(AdjustReason.REJECTED_WRONG_SIDE,
                      f"stop {new_stop} is already through price {price}")

    tightening = _is_tightening(position.side, old_stop, new_stop)
    move = "tighten" if tightening else "widen"

    if not tightening:
        if policy == STOP_POLICY_TIGHTEN_ONLY:
            return reject(AdjustReason.REJECTED_BY_POLICY,
                          "policy is tighten-only; cannot move stop away from price")
        if policy == STOP_POLICY_WIDEN_ONCE and position.widenings >= 1:
            return reject(AdjustReason.REJECTED_WIDEN_LIMIT,
                          "policy allows a single widening and it is already used")
        if position.widenings >= MAX_WIDENINGS_PER_POSITION:
            return reject(AdjustReason.REJECTED_WIDEN_LIMIT,
                          f"already widened {position.widenings} times "
                          f"(max {MAX_WIDENINGS_PER_POSITION})")
        if REQUIRE_NAMED_LEVEL_TO_WIDEN and not level_id:
            return reject(AdjustReason.REJECTED_UNNAMED_LEVEL,
                          "widening requires a named structural level")
        # Solvency rail -- applies no matter what the policy permits.
        ceiling = position.initial_risk * MAX_RISK_MULTIPLE
        if risk_after > ceiling:
            return reject(
                AdjustReason.REJECTED_RISK_CEILING,
                f"risk would rise to {risk_after:.2f}, above ceiling "
                f"{ceiling:.2f} ({MAX_RISK_MULTIPLE}x initial {position.initial_risk:.2f})",
            )

    return Adjustment(
        accepted=True, reason_code=AdjustReason.OK, field_changed="stop_loss",
        old_value=old_stop, new_value=new_stop, direction=move, level_id=level_id,
        risk_before=risk_before, risk_after=risk_after,
        unrealised_at_change=unrealised,
        detail=f"{move} stop {old_stop:.3f} -> {new_stop:.3f}",
    )


def propose_target(
    position: Position,
    new_target: float,
    *,
    price: float,
    level_id: str | None = None,
    policy: str = None,
) -> Adjustment:
    """Validate a target change under the configured target policy."""
    policy = policy or TARGET_POLICY
    old_target = position.take_profit
    unrealised = position.unrealised(price)

    def reject(code: str, detail: str) -> Adjustment:
        return Adjustment(
            accepted=False, reason_code=code, field_changed="take_profit",
            old_value=old_target, new_value=new_target, level_id=level_id,
            unrealised_at_change=unrealised, detail=detail,
        )

    if abs(new_target - old_target) < 1e-9:
        return reject(AdjustReason.NO_CHANGE, "target unchanged")

    direction = 1.0 if position.side == "buy" else -1.0
    if direction * (new_target - price) <= 0:
        return reject(AdjustReason.REJECTED_WRONG_SIDE,
                      f"target {new_target} is not beyond price {price}")

    extending = direction * (new_target - old_target) > 0
    move = "extend" if extending else "reduce"

    if policy == TARGET_POLICY_FIXED:
        return reject(AdjustReason.REJECTED_BY_POLICY,
                      "policy fixes the target at entry")
    if policy == TARGET_POLICY_EXTEND_ONLY and not extending:
        return reject(AdjustReason.REJECTED_BY_POLICY,
                      "policy is extend-only; cannot pull the target closer")

    return Adjustment(
        accepted=True, reason_code=AdjustReason.OK, field_changed="take_profit",
        old_value=old_target, new_value=new_target, direction=move, level_id=level_id,
        unrealised_at_change=unrealised,
        detail=f"{move} target {old_target:.3f} -> {new_target:.3f}",
    )


# R3 only applies to a trade that has not progressed.
#
# 2026-08-11, and worth stating plainly: R3 as formulated is close to inert, by
# design rather than by accident. Remaining reward:risk DEGRADES as a trade
# succeeds (near the target there is little left to win and the stop is far) and
# IMPROVES as it fails (near the stop there is a lot left to win and little left
# to lose). Applied naively it therefore closes winners and holds losers --
# precisely backwards.
#
# On a 1:1 scalp with a 0.90 entry floor it fired at 20-40% progress, killing
# trades that were working. Requiring low progress as well means R3 now only
# fires on a trade that is both going nowhere AND badly priced, which is rare.
#
# That is the honest outcome: R1 (invalidation), R2 (always-in flip) and R4
# (time stop) do the real work. R3 is kept because Brooks' equation is sound
# reasoning for a human deciding whether to keep capital committed, but as a
# mechanical trigger it needs this guard or it inverts.
R3_MAX_PROGRESS = 0.30


def target_progress(position: Position, price: float) -> float:
    """How far the trade has travelled from entry toward its target, 0.0-1.0."""
    direction = 1.0 if position.side == "buy" else -1.0
    span = direction * (position.take_profit - position.entry_price)
    if span <= 0:
        return 0.0
    travelled = direction * (price - position.entry_price)
    return max(0.0, min(1.0, travelled / span))


def remaining_reward_risk(position: Position, price: float) -> float:
    """Reward:risk still on the table from the current mark (R3).

    Brooks' trader's equation applied to an open position: exiting is itself a
    decision that must clear a bar. Computed from structural distances so the
    inputs cannot be coloured by how the trade feels (Douglas p.99).
    """
    direction = 1.0 if position.side == "buy" else -1.0
    to_target = direction * (position.take_profit - price)
    to_stop = direction * (price - position.stop_loss)
    if to_stop <= 0:
        return 0.0
    return max(0.0, to_target) / to_stop


def classify_close_request(
    position: Position,
    *,
    price: float,
    now: float,
    invalidation_closed_through: bool = False,
    opposite_setup_confirmed: bool = False,
    structural_progress_pct: float | None = None,
) -> tuple[str, str]:
    """Decide WHICH named condition (if any) justifies closing early.

    Returns ``(reason, detail)``. Reason is UNJUSTIFIED_DISCRETION when the only
    thing supporting the close is that the position is underwater -- topic 10 R5.
    """
    if invalidation_closed_through:
        return (ExitReason.INVALIDATION_CLOSED_THROUGH,
                "named invalidation failed on a closed candle of its own timeframe")

    if opposite_setup_confirmed:
        return (ExitReason.ALWAYS_IN_FLIP,
                "opposite entry would now be taken with confidence at a named level")

    # R3 -- but only when the trade has NOT made progress.
    #
    # 2026-08-11: on a ~1:1 scalp the remaining reward:risk always looks awful
    # near the target -- 1 point left to gain against 8.5 back to the stop reads
    # as 0.12 -- so a naive R3 closes winners one point short. That is the exact
    # opposite of the intended construction, which is to take the 1:1 entry and
    # EXTEND the target while the move runs.
    #
    # Brooks' equation is about an idea that is no longer worth holding, not one
    # that is nearly paid. So R3 requires poor arithmetic AND little progress:
    # if price has covered most of the distance to target, hold or extend.
    progress = target_progress(position, price)
    reward_risk = remaining_reward_risk(position, price)
    if reward_risk < MIN_REMAINING_REWARD_RISK and progress < R3_MAX_PROGRESS:
        return (ExitReason.REWARD_RISK_INVERTED,
                f"remaining reward:risk {reward_risk:.2f} below "
                f"{MIN_REMAINING_REWARD_RISK} with only {progress:.0%} progress")

    limit = TIME_STOP_SECONDS.get(position.frame or "", DEFAULT_TIME_STOP_SECONDS)
    held = now - position.opened_at
    if held >= limit and (structural_progress_pct or 0.0) < TIME_STOP_MAX_PROGRESS:
        return (ExitReason.TIME_STOP,
                f"held {held/60:.0f}m with {(structural_progress_pct or 0):.0%} progress")

    return (ExitReason.UNJUSTIFIED_DISCRETION,
            "no named condition met; close is supported only by open P&L")


def evaluate_exit(
    position: Position,
    *,
    price: float,
    now: float,
    invalidation_closed_through: bool = False,
    session_ending: bool = False,
    model_requests_close: bool = False,
    opposite_setup_confirmed: bool = False,
    structural_progress_pct: float | None = None,
    allow_unjustified_close: bool = False,
) -> ExitDecision:
    """Deterministic exit taxonomy.

    Mechanical conditions are evaluated before discretionary ones, so a trade
    that has genuinely hit its target or stop is never recorded as a
    discretionary close. That separation is what lets Stage 6 measure the value
    of discretion honestly.
    """
    direction = 1.0 if position.side == "buy" else -1.0

    if direction * (price - position.take_profit) >= 0:
        return ExitDecision(True, ExitReason.TARGET_REACHED,
                            f"price {price} reached target {position.take_profit}")
    if direction * (price - position.stop_loss) <= 0:
        return ExitDecision(True, ExitReason.STOP_HIT,
                            f"price {price} reached stop {position.stop_loss}")
    if position.risk_at(position.stop_loss) > position.initial_risk * MAX_RISK_MULTIPLE:
        return ExitDecision(True, ExitReason.RISK_CEILING,
                            "live stop exceeds the risk ceiling")
    # R1 -- always honoured, whether or not the model asked. The level that
    # defined the trade has failed; there is nothing left to be right about.
    if invalidation_closed_through:
        return ExitDecision(True, ExitReason.INVALIDATION_CLOSED_THROUGH,
                            "named invalidation closed through")

    if session_ending:
        return ExitDecision(True, ExitReason.SESSION_END, "session closing")

    # R2/R3/R4 -- the model may end the trade whenever the idea is genuinely
    # dead. It must name which condition, and the condition is checked here
    # rather than taken on trust.
    if model_requests_close:
        reason, detail = classify_close_request(
            position,
            price=price,
            now=now,
            invalidation_closed_through=invalidation_closed_through,
            opposite_setup_confirmed=opposite_setup_confirmed,
            structural_progress_pct=structural_progress_pct,
        )
        if reason in JUSTIFIED_DISCRETION:
            return ExitDecision(True, reason, detail)
        # R5: the only support is that the position is underwater. Recorded
        # either way so the -20.22 can be attributed rather than guessed at.
        if allow_unjustified_close:
            return ExitDecision(True, ExitReason.UNJUSTIFIED_DISCRETION, detail)
        return ExitDecision(False, ExitReason.UNJUSTIFIED_DISCRETION, detail)

    # R4 also fires unattended -- a dead trade should not need to be noticed.
    limit = TIME_STOP_SECONDS.get(position.frame or "", DEFAULT_TIME_STOP_SECONDS)
    held = now - position.opened_at
    if held >= limit and (structural_progress_pct or 0.0) < TIME_STOP_MAX_PROGRESS:
        return ExitDecision(
            True, ExitReason.TIME_STOP,
            f"held {held/60:.0f}m (limit {limit/60:.0f}m for {position.frame}) "
            f"with {(structural_progress_pct or 0):.0%} structural progress",
        )
    return ExitDecision(False)


def apply(position: Position, adjustment: Adjustment) -> Position:
    """Return a new Position with an accepted adjustment applied."""
    if not adjustment.accepted:
        return position
    updates = {}
    widenings = position.widenings
    if adjustment.field_changed == "stop_loss":
        updates["stop_loss"] = adjustment.new_value
        if adjustment.direction == "widen":
            widenings += 1
    elif adjustment.field_changed == "take_profit":
        updates["take_profit"] = adjustment.new_value
    return Position(
        side=position.side,
        entry_price=position.entry_price,
        stop_loss=updates.get("stop_loss", position.stop_loss),
        take_profit=updates.get("take_profit", position.take_profit),
        volume=position.volume,
        opened_at=position.opened_at,
        frame=position.frame,
        initial_stop_distance=(
            position.initial_stop_distance
            or abs(position.entry_price - position.stop_loss)
        ),
        widenings=widenings,
        value_per_price_unit_per_lot=position.value_per_price_unit_per_lot,
        rebracketed_at=position.rebracketed_at,
    )


def format_adjustment(adjustment: Adjustment) -> str:
    """Single-line, greppable audit record."""
    verdict = "ACCEPT" if adjustment.accepted else "REJECT"
    return (
        f"MANAGE {verdict} {adjustment.reason_code} "
        f"{adjustment.field_changed} {adjustment.old_value:.3f}->{adjustment.new_value:.3f} "
        f"dir={adjustment.direction} level={adjustment.level_id} "
        f"risk {adjustment.risk_before:.2f}->{adjustment.risk_after:.2f} "
        f"open_pnl={adjustment.unrealised_at_change:.2f} :: {adjustment.detail}"
    )
