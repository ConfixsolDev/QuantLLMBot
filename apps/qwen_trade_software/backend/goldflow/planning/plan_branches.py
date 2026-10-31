"""Two-branch day-plan state machine.

Why this exists
---------------
The day plan already produced both a bullish_scenario and a bearish_scenario --
the correct two-sided structure. Two places then destroyed it:

1. ``_fallback_h4_from_day_plan()`` collapsed the pair into ONE directional idea
   with ``use_bull = len(bull_targets) >= len(bear_targets)`` -- it picked the
   side that happened to list more target numbers. Not analysis, an artifact.

2. ``apply_layer_validation()`` copied the model's layer verdict straight onto
   idea status with no price check. On 2026-08-11 a session-forecast miss
   ("expected range compression, observed bullish hour", confidence delta -30)
   flipped H4/H1/M15 to INVALIDATED -- while price ran through BOTH of that
   idea's targets (4405.80, 4409.20) and never touched its 4397.60
   invalidation. The idea was right and was marked dead.

The fix is conceptual: a day plan is a CONTAINER of two branches, not a
directional bet. It is never invalidated as a whole. Each branch carries its own
state, and only price closing through a branch's own invalidation kills that
branch.

    armed        waiting for its trigger              (default)
    likely       evidence accumulating in its favour
    confirmed    trigger fired on a CLOSED candle     <- now callable buy/sell
    spent        targets reached
    invalidated  price CLOSED through its own level   <- the only way to die

A session-forecast miss moves confidence, never state. "My forecast of session
character was wrong" and "my trade idea is wrong" are independent claims; on
2026-08-11 they were opposite.

Pure functions, no I/O, so the whole thing is replayable against history.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Iterable, Mapping, Sequence


BRANCH_STATE_VERSION = "1.0"

ARMED = "armed"
LIKELY = "likely"
CONFIRMED = "confirmed"
SPENT = "spent"
INVALIDATED = "invalidated"

BRANCH_STATES = (ARMED, LIKELY, CONFIRMED, SPENT, INVALIDATED)

# States a branch can never leave.
TERMINAL_STATES = frozenset({SPENT, INVALIDATED})

# How close price must come to a trigger before the branch is "likely".
# Expressed as a fraction of the distance from trigger to invalidation, so it
# scales with how wide the branch is rather than assuming a fixed gold distance.
LIKELY_PROXIMITY = 0.35


@dataclass(frozen=True)
class Branch:
    """One side of the day plan."""

    side: str                       # "buy" | "sell"
    trigger_price: float | None = None
    trigger_text: str = ""
    targets: tuple[float, ...] = ()
    invalidation: float | None = None
    evidence: tuple[str, ...] = ()
    state: str = ARMED
    reason: str = ""
    confidence: int = 50

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DayPlanView:
    """What the screen renders. The plan itself has no status."""

    bullish: Branch
    bearish: Branch
    headline: str
    callable_side: str | None = None
    version: str = BRANCH_STATE_VERSION

    def as_dict(self) -> dict:
        return {
            "bullish": self.bullish.as_dict(),
            "bearish": self.bearish.as_dict(),
            "headline": self.headline,
            "callable_side": self.callable_side,
            "version": self.version,
        }


def branch_from_scenario(scenario: Mapping | None, side: str,
                         trigger_price: float | None = None) -> Branch:
    """Build a Branch from a day-plan scenario block."""
    scenario = scenario or {}
    targets = []
    for value in (scenario.get("targets") or []):
        try:
            targets.append(float(value))
        except (TypeError, ValueError):
            continue
    invalidation = scenario.get("invalidation")
    try:
        invalidation = float(invalidation) if invalidation is not None else None
    except (TypeError, ValueError):
        invalidation = None
    return Branch(
        side=side,
        trigger_price=trigger_price,
        trigger_text=str(scenario.get("trigger") or "")[:160],
        targets=tuple(targets[:3]),
        invalidation=invalidation,
        evidence=tuple(str(x)[:80] for x in (scenario.get("evidence") or [])[:6]),
        state=ARMED,
    )


def evaluate_branch(
    branch: Branch,
    *,
    closed_price: float,
    high: float | None = None,
    low: float | None = None,
    trigger_confirmed: bool = False,
) -> Branch:
    """Advance one branch against a CLOSED candle.

    ``closed_price`` is the only input that can invalidate. ``high``/``low`` are
    accepted for target detection but never for invalidation -- a wick through a
    level is the level being tested, not broken. On 2026-08-11 the hour low
    (4396.54) wicked 1.06 through the 4397.60 invalidation and the close
    (4409.55) went the other way entirely.
    """
    if branch.state in TERMINAL_STATES:
        return branch

    direction = 1.0 if branch.side == "buy" else -1.0

    # 1. Invalidation -- requires a CLOSE through the branch's own level.
    if branch.invalidation is not None:
        if direction * (closed_price - branch.invalidation) < 0:
            return _with(branch, INVALIDATED,
                         f"closed {closed_price:.3f} through invalidation "
                         f"{branch.invalidation:.3f}")

    # 2. Targets reached. Use the extreme in the branch's favour if supplied,
    #    since a target can be tagged intrabar and still count as reached.
    if branch.targets:
        reach = closed_price
        if direction > 0 and high is not None:
            reach = max(reach, high)
        if direction < 0 and low is not None:
            reach = min(reach, low)
        final_target = branch.targets[-1]
        if direction * (reach - final_target) >= 0:
            return _with(branch, SPENT,
                         f"reached final target {final_target:.3f}")

    # 3. Trigger fired on a closed candle -> callable.
    if trigger_confirmed:
        return _with(branch, CONFIRMED,
                     f"trigger confirmed on closed candle at {closed_price:.3f}")
    if branch.trigger_price is not None and direction * (closed_price - branch.trigger_price) >= 0:
        return _with(branch, CONFIRMED,
                     f"closed {closed_price:.3f} through trigger "
                     f"{branch.trigger_price:.3f}")

    # 4. Approaching its trigger -> likely.
    if branch.trigger_price is not None and branch.invalidation is not None:
        span = abs(branch.trigger_price - branch.invalidation)
        if span > 0:
            distance = abs(branch.trigger_price - closed_price)
            if distance <= span * LIKELY_PROXIMITY:
                return _with(branch, LIKELY,
                             f"{distance:.2f} from trigger {branch.trigger_price:.3f}")

    return _with(branch, ARMED, "waiting for trigger")


def _with(branch: Branch, state: str, reason: str) -> Branch:
    return Branch(
        side=branch.side,
        trigger_price=branch.trigger_price,
        trigger_text=branch.trigger_text,
        targets=branch.targets,
        invalidation=branch.invalidation,
        evidence=branch.evidence,
        state=state,
        reason=reason,
        confidence=branch.confidence,
    )


def apply_confidence_delta(branch: Branch, delta: int) -> Branch:
    """Session-forecast accuracy moves CONFIDENCE only, never state.

    This is the 2026-08-11 lesson encoded: a wrong forecast of session character
    is not evidence that the trade idea is wrong. Keep the two signals apart so
    the ledger can measure whether forecast accuracy predicts idea quality at
    all -- currently an open question, not an assumption.
    """
    if branch.state in TERMINAL_STATES:
        return branch
    updated = max(0, min(100, int(branch.confidence) + int(delta)))
    return Branch(
        side=branch.side, trigger_price=branch.trigger_price,
        trigger_text=branch.trigger_text, targets=branch.targets,
        invalidation=branch.invalidation, evidence=branch.evidence,
        state=branch.state, reason=branch.reason, confidence=updated,
    )


def build_day_view(
    bullish: Branch,
    bearish: Branch,
) -> DayPlanView:
    """Compose the two branches into what the screen shows.

    The plan has no status of its own. The headline answers the one question the
    old screen could not: are we buying, selling, or waiting -- and if waiting,
    for what.
    """
    callable_side = None
    if bullish.state == CONFIRMED and bearish.state != CONFIRMED:
        callable_side = "buy"
    elif bearish.state == CONFIRMED and bullish.state != CONFIRMED:
        callable_side = "sell"

    if callable_side == "buy":
        headline = f"BUY confirmed — {bullish.reason}"
    elif callable_side == "sell":
        headline = f"SELL confirmed — {bearish.reason}"
    elif bullish.state == CONFIRMED and bearish.state == CONFIRMED:
        headline = "Both branches confirmed — conflict, stand aside"
    else:
        live = [b for b in (bullish, bearish) if b.state not in TERMINAL_STATES]
        if not live:
            headline = "Day resolved — both branches closed out"
        else:
            nearest = min(
                live,
                key=lambda b: abs((b.trigger_price or 0) - 0) if b.trigger_price else 1e9,
            )
            leaning = [b for b in live if b.state == LIKELY]
            if leaning:
                sides = " and ".join(b.side.upper() for b in leaning)
                headline = f"No entry yet — {sides} leaning, waiting for a closed trigger"
            else:
                headline = "No entry yet — both branches armed, waiting for a trigger"
            _ = nearest

    return DayPlanView(
        bullish=bullish, bearish=bearish,
        headline=headline, callable_side=callable_side,
    )


_CJK = None


def clean_model_text(value: str, *, replacement: str = "") -> str:
    """Strip CJK characters the base model occasionally leaks into English text.

    Qwen is a Chinese-origin base model and a light fine-tune leaks source-
    language tokens at a low rate. Measured: 0.9% of proposals on 2026-08-07
    (v003) and 1.1% on 2026-08-11 (v004) -- so it is pre-existing and NOT a
    v004 regression, but it reaches the screen as

        "new_york": "纽约"
        "Tighter range than full伦敦和"

    which makes the planner look broken. Cosmetic only: the numbers, level ids
    and states are unaffected. Strip it at the display boundary rather than
    trying to prompt it away, because the leak is a property of the base model.
    """
    global _CJK
    if not value:
        return value
    if _CJK is None:
        import re as _re
        _CJK = _re.compile(r"[　-〿぀-ヿ㐀-䶿一-鿿＀-￯]+")
    cleaned = _CJK.sub(replacement, str(value))
    # Collapse the double spaces stripping can leave behind.
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip(" ,;:-")


def has_leaked_text(value: str) -> bool:
    """True when a string contains CJK, so the UI can flag rather than hide it."""
    return bool(value) and clean_model_text(value) != str(value).strip(" ,;:-")


def summarise(view: DayPlanView) -> str:
    """One greppable line for the logs."""
    return (
        f"DAYPLAN bull={view.bullish.state}({view.bullish.confidence}) "
        f"bear={view.bearish.state}({view.bearish.confidence}) "
        f"callable={view.callable_side or 'none'}"
    )
