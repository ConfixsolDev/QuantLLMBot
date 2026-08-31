"""Canonical direction vocabulary — standardize free-text bias words to buy/sell.

2026-08-28 incident background
-------------------------------
Live proposal ``paper-20260828T083558-8499f6ce`` executed a BUY at 4605-4610
while its own ``reason``/``summary`` read verbatim: "Live bearish sequence into
4571.395" -- a bearish narrative, naming a target 34 points below the entry,
attached to a buy order. ``entry_validation_failures`` was empty: nothing in
the contract checked whether the model's own words agreed with the side it
ordered.

The existing ``check_ready_reason_contradiction`` in entry_policy.py only
catches *readiness* contradictions (model says "awaiting confirmation" but
status=ready). It was deliberately never extended to catch *directional*
contradictions, because doing that safely requires a single, deterministic
place that knows every word Qwen might use for "up" or "down" -- otherwise
every attempt to catch this ships its own ad-hoc keyword list, drifts from
the others, and either misses real contradictions or refuses good trades.

This module is that single place. It does not decide anything by itself --
it only answers "what direction(s), if any, does this text name?" Policy
(entry_policy.py) decides what to do with the answer.

Design rules, matched to the lesson already learned from
``check_ready_reason_contradiction``'s NOT_READY_MARKERS:

* Substring matching on a lowercased string. Simple, auditable, greppable.
* Every marker list here is deliberately narrow. A false positive refuses a
  valid trade; a false negative is merely one contradiction slipping through
  a second, independent gate that already exists elsewhere. Narrow-but-late
  beats broad-but-early.
* Reversal/qualifier language ("bearish sweep, now reclaiming...") describes
  a change of character, not a contradiction -- this is exactly the
  doctrine's CHOCH-as-early-warning distinction, not a confirmed reversal.
  Text containing a reversal stem is never flagged, even if it also names
  the opposite direction, because that is normal language for "the old
  direction just ended."
"""

from __future__ import annotations

BUY = "buy"
SELL = "sell"

# Words/stems that name a bullish/upward direction. Checked as substrings.
BUY_WORDS: tuple[str, ...] = (
    "buy",
    "bullish",
    "long",
    "upside",
    "uptrend",
    "up-trend",
    "higher high",
    "higher low",
    "rally",
    "advance",
    "accumulation",
    "demand zone",
    "bounce",
)

# Words/stems that name a bearish/downward direction. Checked as substrings.
SELL_WORDS: tuple[str, ...] = (
    "sell",
    "bearish",
    "short",
    "downside",
    "downtrend",
    "down-trend",
    "lower high",
    "lower low",
    "decline",
    "sell-off",
    "selloff",
    "distribution",
    "supply zone",
    "breakdown",
)

# Stems that mark a change of character rather than a straight statement of
# direction. If present, an opposite-direction word is not a contradiction --
# it is very likely describing what just ended ("bearish sweep, now
# reclaiming the level" is a legitimate buy reason that contains "bearish").
REVERSAL_QUALIFIER_STEMS: tuple[str, ...] = (
    "revers",     # reversal, reversing, reversed
    "reject",     # reject, rejecting, rejection, rejected
    "reclaim",    # reclaim, reclaimed, reclaiming
    "recover",    # recover, recovering, recovered
    "turn",       # turning, turned
    "shift",      # shift, shifted
    "sweep",      # sweep, swept -- liquidity sweep language
    "exhaust",    # exhaustion, exhausted
    "fail",       # failed breakdown, failed breakout
    "invalidat",  # invalidated, invalidation
)


def normalize_side(value: str | None) -> str | None:
    """Map a bias/side field to canonical 'buy'/'sell', or None if unknown.

    Accepts the values already used across the codebase ('buy', 'sell',
    'long', 'short', 'bullish', 'bearish') so callers do not need their own
    ad-hoc mapping.
    """
    if not value:
        return None
    text = str(value).strip().lower()
    if text in ("buy", "long", "bullish"):
        return BUY
    if text in ("sell", "short", "bearish"):
        return SELL
    return None


def directions_named(text: str) -> set[str]:
    """Return the canonical direction(s) ('buy', 'sell') mentioned in *text*.

    Can return both, one, or neither. Returning both is common and expected
    for legitimate reversal narratives ("bearish sequence now reclaiming
    support") and is NOT itself a contradiction -- see has_reversal_qualifier.
    """
    if not text:
        return set()
    lowered = str(text).lower()
    found: set[str] = set()
    if any(word in lowered for word in BUY_WORDS):
        found.add(BUY)
    if any(word in lowered for word in SELL_WORDS):
        found.add(SELL)
    return found


def has_reversal_qualifier(text: str) -> bool:
    """Whether *text* contains language describing a change of character."""
    if not text:
        return False
    lowered = str(text).lower()
    return any(stem in lowered for stem in REVERSAL_QUALIFIER_STEMS)


def opposite(side: str) -> str:
    return SELL if side == BUY else BUY


def direction_conflicts_with_side(text: str, side: str) -> bool:
    """True when *text* names ONLY the opposite direction of *side*.

    Conservative by construction:
    * text must name the opposite direction,
    * text must NOT also name *side*'s own direction (mixed language is not
      a clean contradiction -- e.g. a genuine reversal call),
    * text must NOT carry a reversal qualifier (that is normal language for
      "the old direction just ended," not a contradiction).
    """
    side = normalize_side(side)
    if side is None:
        return False
    if has_reversal_qualifier(text):
        return False
    named = directions_named(text)
    other = opposite(side)
    return other in named and side not in named
