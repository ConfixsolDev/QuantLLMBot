"""The D1 / H4 / H1 / M15 ladder — both directions live at every timeframe.

Why a ladder of PAIRS rather than one idea per timeframe
--------------------------------------------------------
The old stack carried a single directional idea per timeframe. That makes a
perfectly normal market state unrepresentable: a bearish day containing a
bullish H1 pullback. With one idea per level the H1 disagreement can only be
expressed as a contradiction, so it surfaced as "invalidated" — and the screen
went red on a day the bullish branch reached both its targets (2026-08-11).

With a bull AND a bear branch at every level, the same market reads naturally:

    D1   bear confirmed        the day is selling
    H4   bear likely           structure agrees
    H1   bull likely           this is the pullback, not a contradiction
    M15  bull confirmed        the pullback is being bought right now

Nothing is invalidated. Each branch simply has its own state, and the operator
reads the ladder top-down: higher frames give direction, lower frames give the
entry. That is the standard hierarchy — Daily for bias, H4 for structure, H1 for
the setup zone, M15 for confirmation — and disagreement between levels is
information rather than error.

Confidence accrues (see accrue_confidence): each closed hour that goes a
branch's way, and each named level that breaks in its favour, lifts it; evidence
against lowers it. A branch is never killed by a forecast miss, only by price
closing through its own invalidation.

Pure functions, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Mapping, Sequence

import plan_branches
from plan_branches import (
    ARMED,
    CONFIRMED,
    INVALIDATED,
    LIKELY,
    SPENT,
    TERMINAL_STATES,
    Branch,
)


LADDER_VERSION = "1.0"

# Top-down. Higher frames set direction, lower frames give the entry.
LADDER_TIMEFRAMES = ("D1", "H4", "H1", "M15")

ROLE = {
    "D1": "Bias — which way the day leans and the levels that matter",
    "H4": "Structure — where the auction is building or failing",
    "H1": "Setup — the zone a trade would be taken from",
    "M15": "Trigger — the closed response that starts the trade",
}

# Confidence movement per piece of evidence. Deliberately small: confidence
# should build over a session, not swing on one candle.
HOUR_WITH = 6        # a closed hour in the branch's direction
HOUR_AGAINST = -4    # a closed hour against it
LEVEL_WITH = 8       # a named level breaking in its favour
LEVEL_AGAINST = -6
CONFIRM_BONUS = 15   # its trigger fired on a closed candle
ALIGNED_BONUS = 5    # the frame above agrees

CONFIDENCE_FLOOR = 0
CONFIDENCE_CEILING = 100


@dataclass(frozen=True)
class TimeframePair:
    """Both directions at one timeframe."""

    timeframe: str
    role: str
    bull: Branch
    bear: Branch
    note: str = ""

    @property
    def leader(self) -> Branch:
        """Whichever branch currently has the stronger claim."""
        order = {CONFIRMED: 3, LIKELY: 2, ARMED: 1, SPENT: 0, INVALIDATED: -1}
        bull_rank = (order.get(self.bull.state, 0), self.bull.confidence)
        bear_rank = (order.get(self.bear.state, 0), self.bear.confidence)
        return self.bull if bull_rank >= bear_rank else self.bear

    @property
    def side(self) -> str | None:
        """"buy" / "sell" when one branch clearly leads, else None."""
        lead = self.leader
        other = self.bear if lead is self.bull else self.bull
        if lead.state in TERMINAL_STATES and other.state in TERMINAL_STATES:
            return None
        if lead.state == other.state and lead.confidence == other.confidence:
            return None
        return lead.side

    def as_dict(self) -> dict:
        return {
            "timeframe": self.timeframe,
            "role": self.role,
            "bull": self.bull.as_dict(),
            "bear": self.bear.as_dict(),
            "side": self.side,
            "note": self.note,
        }


@dataclass
class Ladder:
    pairs: list = field(default_factory=list)
    headline: str = ""
    aligned: bool = False
    version: str = LADDER_VERSION

    def as_dict(self) -> dict:
        return {
            "pairs": [p.as_dict() for p in self.pairs],
            "headline": self.headline,
            "aligned": self.aligned,
            "version": self.version,
        }


def _clamp(value: float) -> int:
    return int(max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEILING, round(value))))


def _rebuild(branch: Branch, **changes) -> Branch:
    data = branch.as_dict()
    data.update(changes)
    data["targets"] = tuple(data.get("targets") or ())
    data["evidence"] = tuple(data.get("evidence") or ())
    return Branch(**data)


def accrue_confidence(
    branch: Branch,
    *,
    hours_with: int = 0,
    hours_against: int = 0,
    levels_with: int = 0,
    levels_against: int = 0,
    aligned_with_higher: bool = False,
) -> Branch:
    """Move a branch's confidence on accumulated evidence.

    Confidence should grow through the session as evidence stacks up, which is
    what makes the number worth showing. A flat 50 on both branches — what the
    screen displayed on 2026-08-11 — tells the operator nothing.

    Terminal branches are left alone: a spent or invalidated branch has no
    further claim to make.
    """
    if branch.state in TERMINAL_STATES:
        return branch
    delta = (
        hours_with * HOUR_WITH
        + hours_against * HOUR_AGAINST
        + levels_with * LEVEL_WITH
        + levels_against * LEVEL_AGAINST
        + (CONFIRM_BONUS if branch.state == CONFIRMED else 0)
        + (ALIGNED_BONUS if aligned_with_higher else 0)
    )
    return _rebuild(branch, confidence=_clamp(branch.confidence + delta))


def evidence_from_hours(
    hourly_updates: Sequence[Mapping],
    side: str,
    limit: int = 12,
) -> tuple[int, int]:
    """Count recent closed hours for and against a side.

    Reads the planner's own hourly artifacts; "bullish hour" / "bearish hour"
    is the observed field the hour card already displays.
    """
    with_count = against_count = 0
    for update in list(hourly_updates)[-limit:]:
        favours_bull: bool | None = None

        # Prefer the candle itself -- objective and always present. The planner
        # writes hour_ohlc on every update, whereas the narrative field is only
        # populated when the model produced one.
        ohlc = update.get("hour_ohlc")
        if isinstance(ohlc, Mapping):
            try:
                open_, close = float(ohlc["o"]), float(ohlc["c"])
                if close != open_:
                    favours_bull = close > open_
            except (KeyError, TypeError, ValueError):
                favours_bull = None

        if favours_bull is None:
            observed = str(
                (update.get("actual_vs_expected") or {}).get("observed")
                or update.get("observed")
                or ""
            ).lower()
            if "bullish" in observed:
                favours_bull = True
            elif "bearish" in observed:
                favours_bull = False

        if favours_bull is None:
            continue
        if (side == "buy") == favours_bull:
            with_count += 1
        else:
            against_count += 1
    return with_count, against_count


def evidence_from_levels(
    levels_touched: Sequence[Mapping],
    side: str,
) -> tuple[int, int]:
    """Count named levels that broke in a side's favour, and against it."""
    with_count = against_count = 0
    for row in levels_touched or []:
        result = str(row.get("result") or "").lower()
        if result not in ("broken_above", "broken_below"):
            continue
        favours_bull = result == "broken_above"
        if (side == "buy") == favours_bull:
            with_count += 1
        else:
            against_count += 1
    return with_count, against_count


def build_pair(
    timeframe: str,
    bull: Branch,
    bear: Branch,
    *,
    closed_price: float | None = None,
    hourly_updates: Sequence[Mapping] = (),
    levels_touched: Sequence[Mapping] = (),
    higher_side: str | None = None,
) -> TimeframePair:
    """Evaluate both branches at one timeframe and accrue their confidence."""
    if closed_price is not None:
        bull = plan_branches.evaluate_branch(bull, closed_price=closed_price)
        bear = plan_branches.evaluate_branch(bear, closed_price=closed_price)

    for side, branch in (("buy", bull), ("sell", bear)):
        hw, ha = evidence_from_hours(hourly_updates, side)
        lw, la = evidence_from_levels(levels_touched, side)
        updated = accrue_confidence(
            branch,
            hours_with=hw, hours_against=ha,
            levels_with=lw, levels_against=la,
            aligned_with_higher=(higher_side == side),
        )
        if side == "buy":
            bull = updated
        else:
            bear = updated

    note = ""
    if higher_side and bull.state == CONFIRMED and higher_side == "sell":
        note = "counter-trend — treat as a pullback inside the higher-frame move"
    elif higher_side and bear.state == CONFIRMED and higher_side == "buy":
        note = "counter-trend — treat as a pullback inside the higher-frame move"

    return TimeframePair(
        timeframe=timeframe, role=ROLE.get(timeframe, ""), bull=bull, bear=bear, note=note
    )


def _branch_from_idea(idea: Mapping | None, side: str, fallback: Mapping | None) -> Branch:
    """Build one branch from a stack idea, falling back to the day scenario.

    The model currently emits a single directional idea per lower timeframe, so
    the opposite branch is seeded from the day plan's opposite scenario. Once
    the contract produces two-sided ideas per frame this fallback simply stops
    being used.
    """
    idea = idea or {}
    source = idea if str(idea.get("side") or "").lower() == side else (fallback or {})
    targets = []
    for value in (source.get("targets") or []):
        try:
            targets.append(float(value))
        except (TypeError, ValueError):
            continue
    try:
        invalidation = float(source.get("invalidation"))
    except (TypeError, ValueError):
        invalidation = None
    return Branch(
        side=side,
        trigger_price=targets[0] if targets else None,
        trigger_text=str(source.get("thesis") or source.get("trigger")
                         or source.get("summary") or "")[:160],
        targets=tuple(targets[:3]),
        invalidation=invalidation,
        evidence=tuple(str(x)[:80] for x in (source.get("key_level_refs")
                                             or source.get("evidence") or [])[:4]),
        state=ARMED,
        confidence=50,
    )


def _level_map(levels: Sequence[Mapping]) -> dict[str, float]:
    """{level_id: price} from the cache's levels list."""
    out: dict[str, float] = {}
    for row in levels or []:
        name = row.get("level_id") or row.get("label")
        price = row.get("zone_low", row.get("price"))
        if not name:
            continue
        try:
            value = float(price)
        except (TypeError, ValueError):
            continue
        if value:
            out[str(name)] = value
    return out


def branches_from_levels(
    timeframe: str,
    levels: Mapping[str, float],
    price: float | None,
) -> tuple[Branch, Branch] | None:
    """Build BOTH directions at a timeframe from that timeframe's own levels.

    No training change required. The model still emits one directional idea per
    lower frame, but the counter-side does not need the model -- it is fully
    determined by structure:

        bull at H1 :  trigger H1_PREVIOUS_HIGH, invalidation H1_PREVIOUS_LOW
        bear at H1 :  trigger H1_PREVIOUS_LOW,  invalidation H1_PREVIOUS_HIGH

    Previously the counter-branch was inherited from the DAY plan's opposite
    scenario, so every lower frame showed the same numbers and the ladder had
    nothing to say. Derived this way each frame has its own real levels, which
    is what makes "H1 bull inside a D1 bear" a genuine reading rather than a
    copy of the day.

    Targets are the next named levels beyond the trigger in that direction, so
    they too come from structure rather than being invented.
    """
    high = levels.get(f"{timeframe}_PREVIOUS_HIGH")
    low = levels.get(f"{timeframe}_PREVIOUS_LOW")
    if high is None or low is None or high <= low:
        return None

    ordered = sorted(set(levels.values()))

    def beyond(from_price: float, up: bool, count: int = 2) -> tuple[float, ...]:
        if up:
            return tuple(v for v in ordered if v > from_price)[:count]
        return tuple(reversed([v for v in ordered if v < from_price]))[:count]

    bull = Branch(
        side="buy",
        trigger_price=high,
        trigger_text=f"close above {timeframe}_PREVIOUS_HIGH",
        targets=beyond(high, up=True) or (high + (high - low),),
        invalidation=low,
        evidence=(f"{timeframe}_PREVIOUS_HIGH", f"{timeframe}_PREVIOUS_LOW"),
        confidence=50,
    )
    bear = Branch(
        side="sell",
        trigger_price=low,
        trigger_text=f"close below {timeframe}_PREVIOUS_LOW",
        targets=beyond(low, up=False) or (low - (high - low),),
        invalidation=high,
        evidence=(f"{timeframe}_PREVIOUS_LOW", f"{timeframe}_PREVIOUS_HIGH"),
        confidence=50,
    )
    return bull, bear


def build_ladder_from_state(
    state: Mapping,
    live_price: float | None = None,
    levels: Sequence[Mapping] | None = None,
) -> dict | None:
    """Assemble the four-timeframe ladder from live planner state.

    ``levels`` is the cache's per-timeframe level list (planner_facts()['levels']).
    When supplied, each frame's two branches are derived from its OWN levels.
    """
    plan = state.get("day_plan")
    if not isinstance(plan, dict):
        return None
    stack = state.get("trade_idea_stack") or {}
    hourly = state.get("hourly_updates") or []
    # Levels that broke across the session, not just the latest hour -- evidence
    # accumulates through the day, which is the whole point of the confidence
    # moving rather than sitting at 50.
    levels_touched = []
    for update in hourly[-12:]:
        levels_touched.extend(update.get("levels_touched") or [])

    price = live_price
    if price is None:
        price = plan.get("reference_price")
    try:
        price = float(price)
    except (TypeError, ValueError):
        price = None

    level_map = _level_map(levels or [])
    bull_scenario = plan.get("bullish_scenario") or {}
    bear_scenario = plan.get("bearish_scenario") or {}

    sources = {
        "D1": (bull_scenario, bear_scenario),
        "H4": (stack.get("h4"), stack.get("h4")),
        "H1": (stack.get("h1"), stack.get("h1")),
        "M15": (stack.get("m15"), stack.get("m15")),
    }

    pairs: list[TimeframePair] = []
    higher_side: str | None = None
    for timeframe in LADDER_TIMEFRAMES:
        bull_src, bear_src = sources.get(timeframe, (None, None))
        if timeframe == "D1":
            # The day plan is genuinely two-sided already, so use it directly.
            bull = plan_branches.branch_from_scenario(bull_src, "buy")
            bear = plan_branches.branch_from_scenario(bear_src, "sell")
            if bull.trigger_price is None and bear.invalidation is not None:
                bull = _rebuild(bull, trigger_price=bear.invalidation)
            if bear.trigger_price is None and bull.invalidation is not None:
                bear = _rebuild(bear, trigger_price=bull.invalidation)
        else:
            # Prefer this timeframe's OWN levels so both directions are real
            # structure rather than a copy of the day plan.
            derived = branches_from_levels(timeframe, level_map, price)
            if derived:
                bull, bear = derived
                # Keep the model's wording on whichever side it argued for.
                idea = bull_src if isinstance(bull_src, Mapping) else {}
                side = str(idea.get("side") or "").lower()
                thesis = str(idea.get("thesis") or idea.get("summary") or "")[:160]
                if thesis and side == "buy":
                    bull = _rebuild(bull, trigger_text=thesis)
                elif thesis and side == "sell":
                    bear = _rebuild(bear, trigger_text=thesis)
            else:
                bull = _branch_from_idea(bull_src, "buy", bull_scenario)
                bear = _branch_from_idea(bear_src, "sell", bear_scenario)

        pair = build_pair(
            timeframe, bull, bear,
            closed_price=price,
            hourly_updates=hourly,
            levels_touched=levels_touched,
            higher_side=higher_side,
        )
        pairs.append(pair)
        if pair.side:
            higher_side = pair.side

    return build_ladder(pairs).as_dict()


def build_ladder(pairs: Sequence[TimeframePair]) -> Ladder:
    """Compose the ladder and describe how the frames relate."""
    pairs = list(pairs)
    sides = [(p.timeframe, p.side) for p in pairs if p.side]
    directional = [s for _, s in sides]
    aligned = bool(directional) and len(set(directional)) == 1

    if not directional:
        headline = "No direction on any timeframe yet"
    elif aligned:
        word = "BUY" if directional[0] == "buy" else "SELL"
        frames = ", ".join(tf for tf, _ in sides)
        headline = f"{word} — all timeframes agree ({frames})"
    else:
        top = sides[0]
        disagreeing = [tf for tf, s in sides if s != top[1]]
        word = "BUY" if top[1] == "buy" else "SELL"
        headline = (
            f"{top[0]} says {word}; {', '.join(disagreeing)} counter — "
            "pullback, not conflict"
        )

    return Ladder(pairs=pairs, headline=headline, aligned=aligned)
