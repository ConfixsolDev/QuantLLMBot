"""Stage 3: structural bracket at entry, with size as the free variable.

Why this exists
---------------
The legacy path places a constant $3 stop and $5 target at fill regardless of
structure or volatility, and relies on trade_management to "improve" them
afterwards (sop.md prompt:qwen_trade_management v1.3).

Measured on 2026-08-10 that repair never arrives in time. Stop-outs lived
22s, 50s, 106s, 108s and 161s. Management runs on a 30s cycle with 16-31s of
model latency, so the two fastest stop-outs got *zero* completed reviews and
the rest got at most three. "Place it wrong, fix it later" loses the race on
precisely the trades that need fixing.

The deeper problem is that the constant stop sits a median 1.18 (max 7.81)
*inside* the structural level that would actually prove the trade wrong. So
ordinary noise closes the position before the thesis resolves. Every one of
the five stop-outs closed at exactly -153.5, which is the untouched $3 stop.

This module inverts the relationship:

    risk budget is fixed  ->  stop goes where structure says
                          ->  position SIZE absorbs the difference

That is the standard formulation, and it is what makes a structural stop
affordable. A wider stop is not a bigger loss; it is a smaller position.

Pure functions only -- no MT5, no model, no I/O -- so it is replayable against
historical proposals.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Mapping, Sequence

import entry_policy


GEOMETRY_VERSION = "3.0"

# Risk per trade, in account currency. The one number that stays constant.
DEFAULT_RISK_BUDGET = 150.0

# Contract value per 1.0 price unit per 1.0 lot for XAUUSD.
# 2026-08-10 calibration: the fixed $3 stop at 0.5 lot x 2 buckets produced a
# -153.5 close (3.0 * 100 = 300 gross ... observed -153.5 at the traded size),
# and the $5 target produced +246.5 / +249.15. Both are consistent with
# 50 currency units per 1.0 price unit at the size actually being sent.
VALUE_PER_PRICE_UNIT_PER_LOT = 100.0

# Broker constraints.
MIN_LOT = 0.01
MAX_LOT = 5.0
LOT_STEP = 0.01

# Structural stops need a buffer so the level itself can be tested without the
# stop being taken. Expressed as a fraction of the frame's recent range.
STRUCTURE_BUFFER_FRACTION = 0.15
MIN_STRUCTURE_BUFFER = 0.30

# Guard rails on the resulting stop distance.
#
# CURRICULUM_AND_DATA_PREP.md 1.1 defines a per-frame minimum in gold points,
# and the curriculum has taught it since v004. The runtime ignored it -- first
# with the flat $3/$5 bracket, then with a flat 1.00 floor here -- so structural
# stops were still landing at 3.32, 3.35, 4.10 and 4.44 on frames whose stated
# minimum is 5, 7 or 10.
#
#     Structure TF   Min SL   Min TP
#     M15 / M30         5        5
#     H1                7       10
#     H4 / D1          10       20
#
# A stop tighter than the frame's minimum is the same failure as a stop inside
# the invalidation: the trade is closed by noise before the idea is tested. Pad
# beyond the level to the minimum rather than accepting the nearer level.
TF_MIN_STOP = {
    "M1": 3.0, "M5": 4.0,
    "M15": 5.0, "M30": 5.0,
    "H1": 7.0,
    "H4": 10.0, "D1": 10.0,
}
TF_MIN_TARGET = {
    "M1": 3.0, "M5": 4.0,
    "M15": 5.0, "M30": 5.0,
    "H1": 10.0,
    "H4": 20.0, "D1": 20.0,
}
DEFAULT_MIN_STOP = 5.0
DEFAULT_MIN_TARGET = 5.0

MIN_STOP_DISTANCE = 1.00      # absolute sanity floor; the ladder above governs
MAX_STOP_DISTANCE = 25.00


def min_stop_for(frame: str | None) -> float:
    """Frame's minimum stop distance per CURRICULUM_AND_DATA_PREP.md 1.1."""
    return TF_MIN_STOP.get((frame or "").upper(), DEFAULT_MIN_STOP)


def min_target_for(frame: str | None) -> float:
    """Frame's minimum target distance per CURRICULUM_AND_DATA_PREP.md 1.1."""
    return TF_MIN_TARGET.get((frame or "").upper(), DEFAULT_MIN_TARGET)

# A trade must clear this reward:risk after costs or it is not worth taking.
MIN_REWARD_RISK = 1.20

# Typical round-trip cost in price units, used when checking reward:risk.
ROUND_TRIP_COST = 0.35

# Legacy constants, kept so the fallback reproduces current behaviour exactly.
LEGACY_STOP_DISTANCE = 3.0
LEGACY_TARGET_DISTANCE = 5.0


class GeometryReason:
    OK = "geometry:ok"
    NO_ENTRY_PRICE = "geometry:no_entry_price"
    NO_INVALIDATION = "geometry:no_invalidation"
    NO_TARGET = "geometry:no_target"
    INVALIDATION_WRONG_SIDE = "geometry:invalidation_wrong_side"
    TARGET_WRONG_SIDE = "geometry:target_wrong_side"
    STOP_TOO_TIGHT = "geometry:stop_too_tight"
    STOP_TOO_WIDE = "geometry:stop_too_wide"
    REWARD_RISK_TOO_LOW = "geometry:reward_risk_too_low"
    SIZE_BELOW_MINIMUM = "geometry:size_below_minimum"
    FELL_BACK_TO_FIXED = "geometry:fell_back_to_fixed"


@dataclass(frozen=True)
class Bracket:
    """A complete, executable entry geometry."""

    ok: bool
    reason_code: str
    side: str | None = None
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    stop_distance: float = 0.0
    target_distance: float = 0.0
    reward_risk: float = 0.0
    volume: float = 0.0
    risk_budget: float = 0.0
    expected_risk: float = 0.0
    frame: str | None = None
    invalidation_id: str | None = None
    target_id: str | None = None
    geometry_source: str = ""
    geometry_version: str = GEOMETRY_VERSION
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def round_lot(volume: float) -> float:
    """Snap to the broker lot step, always downward so risk is never exceeded."""
    if volume <= 0:
        return 0.0
    steps = int(volume / LOT_STEP)
    return round(steps * LOT_STEP, 2)


def size_for_risk(stop_distance: float, risk_budget: float) -> float:
    """Position size such that a stop-out costs approximately the risk budget.

    This is the inversion that makes structural stops affordable: a wider stop
    produces a smaller position, not a larger loss.
    """
    if stop_distance <= 0:
        return 0.0
    raw = risk_budget / (stop_distance * VALUE_PER_PRICE_UNIT_PER_LOT)
    return max(0.0, min(MAX_LOT, round_lot(raw)))


def structure_buffer(frame_range: float) -> float:
    """Room beyond the level so the level can be tested without a stop-out."""
    return max(MIN_STRUCTURE_BUFFER, abs(frame_range) * STRUCTURE_BUFFER_FRACTION)


def _fixed_fallback(side: str, entry_price: float, risk_budget: float,
                    detail: str) -> Bracket:
    """Reproduce the legacy $3/$5 bracket when structure is unusable.

    Kept so that turning this module on can never leave a trade unprotected --
    if structure is missing the system degrades to exactly what it does today
    rather than refusing or improvising.
    """
    direction = 1.0 if side == "buy" else -1.0
    stop = entry_price - direction * LEGACY_STOP_DISTANCE
    target = entry_price + direction * LEGACY_TARGET_DISTANCE
    volume = size_for_risk(LEGACY_STOP_DISTANCE, risk_budget)
    return Bracket(
        ok=volume >= MIN_LOT,
        reason_code=GeometryReason.FELL_BACK_TO_FIXED,
        side=side,
        entry_price=entry_price,
        stop_loss=round(stop, 3),
        take_profit=round(target, 3),
        stop_distance=LEGACY_STOP_DISTANCE,
        target_distance=LEGACY_TARGET_DISTANCE,
        reward_risk=LEGACY_TARGET_DISTANCE / LEGACY_STOP_DISTANCE,
        volume=volume,
        risk_budget=risk_budget,
        expected_risk=LEGACY_STOP_DISTANCE * VALUE_PER_PRICE_UNIT_PER_LOT * volume,
        geometry_source="legacy_fixed_3_5",
        detail=detail,
    )


def build_bracket(
    *,
    side: str,
    entry_price: float,
    invalidation_price: float | None,
    target_price: float | None,
    frame: str | None = None,
    frame_range: float = 0.0,
    invalidation_id: str | None = None,
    target_id: str | None = None,
    risk_budget: float = DEFAULT_RISK_BUDGET,
    allow_fallback: bool = True,
) -> Bracket:
    """Build the entry bracket from structure, sizing to a constant risk.

    ``invalidation_price`` is the level that proves the trade wrong; the stop is
    placed just beyond it. ``target_price`` is a structural level of the same
    frame. Neither is invented -- if they are missing the caller either falls
    back to the legacy bracket or the trade is skipped.
    """
    if side not in ("buy", "sell"):
        return Bracket(ok=False, reason_code=GeometryReason.NO_ENTRY_PRICE,
                       detail=f"bad side {side!r}")
    if not entry_price or entry_price <= 0:
        return Bracket(ok=False, reason_code=GeometryReason.NO_ENTRY_PRICE)

    direction = 1.0 if side == "buy" else -1.0

    if invalidation_price is None:
        if allow_fallback:
            return _fixed_fallback(side, entry_price, risk_budget,
                                   "no structural invalidation supplied")
        return Bracket(ok=False, reason_code=GeometryReason.NO_INVALIDATION)
    if target_price is None:
        if allow_fallback:
            return _fixed_fallback(side, entry_price, risk_budget,
                                   "no structural target supplied")
        return Bracket(ok=False, reason_code=GeometryReason.NO_TARGET)

    # The invalidation must sit behind the entry, the target in front of it.
    if direction * (entry_price - invalidation_price) <= 0:
        return Bracket(ok=False, reason_code=GeometryReason.INVALIDATION_WRONG_SIDE,
                       detail=f"invalidation {invalidation_price} is not behind entry {entry_price}")
    if direction * (target_price - entry_price) <= 0:
        return Bracket(ok=False, reason_code=GeometryReason.TARGET_WRONG_SIDE,
                       detail=f"target {target_price} is not beyond entry {entry_price}")

    buffer_amount = structure_buffer(frame_range)
    stop_loss = invalidation_price - direction * buffer_amount
    stop_distance = abs(entry_price - stop_loss)
    target_distance = abs(target_price - entry_price)

    # Pad out to the frame's minimum (curriculum 1.1). "Pad to mins if nearer
    # level is tighter" -- the level is where the idea fails, the minimum is how
    # much room that frame's noise demands. Take whichever is further.
    floor_stop = min_stop_for(frame)
    if stop_distance < floor_stop:
        stop_distance = floor_stop
        stop_loss = entry_price - direction * floor_stop

    # A target inside the frame's minimum cannot pay for the frame's risk.
    floor_target = min_target_for(frame)
    if target_distance < floor_target:
        return Bracket(ok=False, reason_code=GeometryReason.REWARD_RISK_TOO_LOW,
                       stop_distance=stop_distance, target_distance=target_distance,
                       frame=frame,
                       detail=(f"target {target_distance:.2f} below the {frame} "
                               f"minimum {floor_target}"))

    if stop_distance < MIN_STOP_DISTANCE:
        return Bracket(ok=False, reason_code=GeometryReason.STOP_TOO_TIGHT,
                       stop_distance=stop_distance,
                       detail=f"stop {stop_distance:.2f} below minimum {MIN_STOP_DISTANCE}")
    if stop_distance > MAX_STOP_DISTANCE:
        return Bracket(ok=False, reason_code=GeometryReason.STOP_TOO_WIDE,
                       stop_distance=stop_distance,
                       detail=f"stop {stop_distance:.2f} above maximum {MAX_STOP_DISTANCE}")

    reward_risk = (target_distance - ROUND_TRIP_COST) / stop_distance
    if reward_risk < MIN_REWARD_RISK:
        return Bracket(ok=False, reason_code=GeometryReason.REWARD_RISK_TOO_LOW,
                       stop_distance=stop_distance, target_distance=target_distance,
                       reward_risk=reward_risk,
                       detail=f"reward:risk {reward_risk:.2f} below {MIN_REWARD_RISK}")

    volume = size_for_risk(stop_distance, risk_budget)
    if volume < MIN_LOT:
        return Bracket(ok=False, reason_code=GeometryReason.SIZE_BELOW_MINIMUM,
                       stop_distance=stop_distance, volume=volume,
                       detail=f"risk {risk_budget} over stop {stop_distance:.2f} is below {MIN_LOT} lots")

    return Bracket(
        ok=True,
        reason_code=GeometryReason.OK,
        side=side,
        entry_price=entry_price,
        stop_loss=round(stop_loss, 3),
        take_profit=round(target_price, 3),
        stop_distance=round(stop_distance, 3),
        target_distance=round(target_distance, 3),
        reward_risk=round(reward_risk, 3),
        volume=volume,
        risk_budget=risk_budget,
        expected_risk=round(stop_distance * VALUE_PER_PRICE_UNIT_PER_LOT * volume, 2),
        frame=frame,
        invalidation_id=invalidation_id,
        target_id=target_id,
        geometry_source="structural_same_frame",
    )


def bracket_from_decision(
    decision: "entry_policy.PolicyDecision",
    *,
    entry_price: float,
    level_prices: Mapping[str, float],
    frame_range: float = 0.0,
    risk_budget: float = DEFAULT_RISK_BUDGET,
    target_id: str | None = None,
    allow_fallback: bool = True,
) -> Bracket:
    """Convenience bridge from a Stage 2 PolicyDecision to an executable bracket."""
    if decision.status != "ready" or not decision.side:
        return Bracket(ok=False, reason_code=GeometryReason.NO_ENTRY_PRICE,
                       detail="decision is not ready")
    invalidation_price = level_prices.get(str(decision.invalidation_id))
    resolved_target_id = target_id or _same_frame_target(
        decision.side, entry_price, decision.zone_id, level_prices
    )
    target_price = level_prices.get(str(resolved_target_id)) if resolved_target_id else None
    return build_bracket(
        side=decision.side,
        entry_price=entry_price,
        invalidation_price=invalidation_price,
        target_price=target_price,
        frame=entry_policy.timeframe_of_level(decision.zone_id),
        frame_range=frame_range,
        invalidation_id=decision.invalidation_id,
        target_id=resolved_target_id,
        risk_budget=risk_budget,
        allow_fallback=allow_fallback,
    )


def _same_frame_target(side: str, entry_price: float, zone_id: str | None,
                       level_prices: Mapping[str, float]) -> str | None:
    """Nearest level in front of the entry belonging to the zone's frame family.

    Keeps entry, invalidation and target inside one timeframe, which is the
    coherence law from the design doc. On 2026-08-10 the M30-anchored trades
    returned +385.45 at 66.7% while H1/H4-anchored returned -433 at ~15%.
    """
    frame = entry_policy.timeframe_of_level(zone_id)
    if not frame or frame not in entry_policy.TIMEFRAME_RANK:
        return None
    direction = 1.0 if side == "buy" else -1.0
    permitted = {
        tf for tf in entry_policy.TIMEFRAME_ORDER
        if 0 <= entry_policy.TIMEFRAME_RANK[tf] - entry_policy.TIMEFRAME_RANK[frame]
        <= entry_policy.MAX_INVALIDATION_GAP
    }
    best_id, best_distance = None, float("inf")
    for level_id, price in level_prices.items():
        level_frame = entry_policy.timeframe_of_level(level_id)
        if level_frame not in permitted:
            continue
        gap = direction * (price - entry_price)
        if gap <= 0:
            continue
        if gap < best_distance:
            best_id, best_distance = level_id, gap
    return best_id
