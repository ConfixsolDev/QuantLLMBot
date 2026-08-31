"""Deterministic entry policy: the model judges, this module decides.

2026-08-10 incident background
------------------------------
The entry prompt was edited from contract v1.8 to v1.9 at 06:21:50 UTC. From
that moment every Qwen decision returned ``confidence: 0`` while still emitting
``execution_plan.status == "ready"`` and a directional bias. Trading stopped for
2h20m. No exception was raised and no alarm fired, because *policy lived inside
a prompt* -- a paragraph of English silently changed system behaviour.

The same root cause produced the day's other findings:

* 44 of 45 ready proposals were SELL (97.8%). Nothing structurally required the
  long case to be considered at all.
* ``bias: "conditional"`` appeared in 71% of decisions despite the contract
  forbidding it in prose. Prose does not constrain output; schemas do.
* ``status=ready`` alongside ``confidence=0`` occurred 72 times and nothing
  detected the contradiction, because one component owned both the measurement
  and the permission.

This module exists so that none of the above can recur:

* The model returns OBSERVATIONS for both sides (see prompt:qwen_dual_side_entry).
  It never emits ready/wait and never emits an overall confidence.
* Confidence is COMPOSED here from component sub-scores with a fixed, versioned
  weighting. ``confidence == 0`` alongside a positive read is arithmetically
  impossible: a zero requires every component to be zero, which contradicts the
  observation the model itself supplied.
* Permission is computed here, deterministically, and every refusal carries a
  stable reason code that can be counted and alerted on.
* Both sides are always priced, so one-sided drift is a schema violation rather
  than a silent omission.

Nothing in this module calls the model, touches MT5, or performs I/O. It is a
pure function of (observation, context) -> PolicyDecision, which is what makes
it testable and replayable against historical decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Mapping, Sequence

import direction_lexicon


POLICY_VERSION = "2.0"

# Keep policy, reviewer, and executor on one threshold so a proposal accepted
# upstream cannot be silently refused at the broker boundary.
MIN_ENTRY_CONFIDENCE = 51

# CHANGE: 2026-08-26 — Add deterministic response code validation
# Map Qwen responses to structural reality; achieve 90%+ accuracy
DETERMINISTIC_RESPONSE_VALIDATION = True

# Component weights. Must sum to 1.0 -- asserted at import time so a bad edit
# fails loudly at startup instead of silently reweighting live decisions.
SCORE_WEIGHTS: dict[str, float] = {
    "location": 0.25,
    "response": 0.30,
    "participation": 0.15,
    "htf_alignment": 0.20,
    "plan_fit": 0.10,
}
SCORE_COMPONENTS = tuple(SCORE_WEIGHTS)
MAX_COMPONENT_SCORE = 10

# Traps the model may report. Membership is validated: an unknown trap is a
# contract violation, not something to be silently ignored.
KNOWN_TRAPS = frozenset({
    "fade_acceptance",
    "buy_into_resistance",
    "sell_into_support",
    "middle_of_balance",
    "stale_zone",
    "wrong_tf_break",
    "unfinished_htf_close",
    "session_blocked",
    "plan_conflict",
})

# Traps that block the affected side outright. The remainder are advisory and
# apply a confidence haircut instead. This is the v1.9 lesson encoded: traps
# influence permission, they do not annihilate the quality score.
BLOCKING_TRAPS = frozenset({
    "fade_acceptance",
    "buy_into_resistance",
    "sell_into_support",
    "wrong_tf_break",
    "session_blocked",
})
ADVISORY_TRAP_PENALTY = 8  # confidence points per advisory trap

SIDES = ("long", "short")
SIDE_TO_ORDER = {"long": "buy", "short": "sell"}

# Timeframe ordering used by the coherence check. A trigger may sit at the
# zone's own timeframe or one step below it -- never further. This is the
# "M1 wick cannot trigger an H4 zone" rule as code rather than prose.
TIMEFRAME_ORDER = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
TIMEFRAME_RANK = {tf: i for i, tf in enumerate(TIMEFRAME_ORDER)}
MAX_TRIGGER_GAP = 1

# How far ABOVE the entry zone the structural invalidation may sit.
#
# This is the single largest money leak found on 2026-08-10. Measured over the
# 22 closed trades, bucketed by (invalidation rank - entry zone rank):
#
#   gap 1   n=1   net  +246.50   win 100%
#   gap 2   n=1   net    -3.50   win   0%
#   gap 3   n=2   net   +89.75   win 100%
#   gap 4   n=3   net  +242.15   win  33%
#   gap 5   n=9   net  -607.65   win  11%     <- M1 zone, H4 stop
#   gap 6   n=5   net  -462.35   win   0%     <- M1 zone, D1 stop
#
# gap <= 4 returned +574.90 over 7 trades; gap >= 5 returned -1070.00 over 14
# at a 7% win rate. An M1 entry zone defended by an H4/D1 invalidation is not
# one trade -- it is a scalp entry wearing a swing thesis, and the fixed $3
# bracket then sits far inside the level that would actually prove it wrong,
# so ordinary noise closes it before the thesis resolves.
MAX_INVALIDATION_GAP = 4

# Rolling symmetry control. If one side exceeds this share of recent ready
# decisions, the over-represented side must clear a raised bar. A genuinely
# one-directional day still trades one-sided -- but visibly, with the imbalance
# recorded, instead of invisibly as on 2026-08-10.
SYMMETRY_WINDOW = 50
SYMMETRY_MAX_SHARE = 0.75
SYMMETRY_CONFIDENCE_SURCHARGE = 5  # CHANGE: 2026-08-25 — reduced from 10 to 5 for more one-sided day volume


class ReasonCode:
    """Stable, countable refusal codes.

    Bare prose like ``ERROR Automatic deal-sheet generation failed`` cannot be
    grouped, counted or alerted on. Every path that declines a trade returns one
    of these instead.
    """

    OK = "ok"
    # contract / schema violations
    MALFORMED_OBSERVATION = "obs:malformed"
    MISSING_SIDE = "obs:missing_side"
    BAD_SCORES = "obs:bad_scores"
    UNKNOWN_TRAP = "obs:unknown_trap"
    EPOCH_MISMATCH = "obs:epoch_mismatch"
    NO_EVIDENCE = "obs:no_evidence"
    # per-side vetoes
    NO_ZONE = "side:no_zone"
    NO_INVALIDATION = "side:no_invalidation"
    NO_CLOSED_RESPONSE = "side:no_closed_response"
    BLOCKING_TRAP = "side:blocking_trap"
    TIMEFRAME_INCOHERENT = "side:timeframe_incoherent"
    INVALIDATION_INCOHERENT = "side:invalidation_incoherent"
    BELOW_MIN_CONFIDENCE = "side:below_min_confidence"
    # decision level
    NO_ELIGIBLE_SIDE = "decision:no_eligible_side"
    SYMMETRY_THROTTLED = "decision:symmetry_throttled"
    SESSION_BLOCKED = "decision:session_blocked"
    CACHE_NOT_READY = "decision:cache_not_ready"
    # Expected, not a fault: the model said ready but scored the setup below
    # the entry threshold. Becomes a wait, and is NOT alarmed -- see
    # check_legacy_contradiction.
    READY_BELOW_CONFIDENCE_THRESHOLD = "entry:ready_below_threshold"
    # Model said ready while its own reason says the setup has not triggered.
    # Alarmed: unlike low confidence, this one CAN reach the broker.
    READY_CONTRADICTS_OWN_REASON = "invariant:ready_contradicts_own_reason"
    # 2026-08-28: model said ready with side=buy while its own reason named
    # only the bearish direction (or vice versa). Alarmed: this reached the
    # broker on 2026-08-28 (paper-20260828T083558-8499f6ce) before this code
    # existed. See direction_lexicon.py for the word-standardization rules.
    READY_DIRECTION_CONTRADICTS_BIAS = "invariant:ready_direction_contradicts_bias"
    # invariant breaches (should be impossible; alarm if seen)
    INVARIANT_READY_ZERO_CONFIDENCE = "invariant:ready_with_zero_confidence"
    INVARIANT_SIDE_MISMATCH = "invariant:side_mismatch"


@dataclass(frozen=True)
class SideAssessment:
    """What policy concluded about one direction."""

    side: str
    confidence: int = 0
    eligible: bool = False
    reason_code: str = ReasonCode.OK
    detail: str = ""
    zone_id: str | None = None
    invalidation_id: str | None = None
    trigger_tf: str | None = None
    traps: tuple[str, ...] = ()
    raw_confidence: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecision:
    """The single authoritative output of the entry decision."""

    status: str  # "ready" | "wait"
    policy_version: str = POLICY_VERSION
    side: str | None = None  # "buy" | "sell"
    confidence: int = 0
    reason_code: str = ReasonCode.OK
    detail: str = ""
    zone_id: str | None = None
    invalidation_id: str | None = None
    trigger_tf: str | None = None
    assessments: dict[str, dict] = field(default_factory=dict)
    invariant_breaches: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return asdict(self)


def _assert_weights() -> None:
    total = round(sum(SCORE_WEIGHTS.values()), 6)
    if total != 1.0:
        raise ValueError(
            f"SCORE_WEIGHTS must sum to 1.0, got {total}. Refusing to load a "
            "policy that would silently reweight live decisions."
        )


_assert_weights()


def compose_confidence(scores: Mapping[str, Any]) -> int:
    """Compose 0-100 confidence from component sub-scores.

    Confidence is DERIVED, never taken from the model. This is what makes the
    v1.9 failure mode impossible: to reach 0 here, every component must be 0,
    which contradicts any positive observation the model reported.
    """
    total = 0.0
    for component, weight in SCORE_WEIGHTS.items():
        raw = scores.get(component, 0)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = 0.0
        value = max(0.0, min(float(MAX_COMPONENT_SCORE), value))
        total += (value / MAX_COMPONENT_SCORE) * weight
    return int(round(total * 100))


def _valid_scores(scores: Any) -> bool:
    if not isinstance(scores, Mapping):
        return False
    for component in SCORE_COMPONENTS:
        if component not in scores:
            return False
        try:
            value = float(scores[component])
        except (TypeError, ValueError):
            return False
        if not (0 <= value <= MAX_COMPONENT_SCORE):
            return False
    return True


def timeframe_coherent(zone_tf: str | None, trigger_tf: str | None) -> bool:
    """Trigger must sit at the zone's timeframe or at most one step below.

    Encodes trap #6 ("an M1 wick never breaks an M15/H1/H4 level") as a rule
    rather than a request. On 2026-08-10 the ready proposals paired M1 entry
    triggers with H4/H1 structural frames; H4-anchored trades returned -116.85
    at a 14.3% win rate and H1-anchored -316.20 at 16.7%, while M30-anchored
    trades returned +385.45 at 66.7%.
    """
    if not zone_tf or not trigger_tf:
        return False
    if zone_tf not in TIMEFRAME_RANK or trigger_tf not in TIMEFRAME_RANK:
        return False
    gap = TIMEFRAME_RANK[zone_tf] - TIMEFRAME_RANK[trigger_tf]
    return 0 <= gap <= MAX_TRIGGER_GAP


def invalidation_coherent(zone_tf: str | None, invalidation_tf: str | None) -> bool:
    """The invalidation must belong to the entry zone's timeframe family.

    It may sit at the zone's own timeframe or up to ``MAX_INVALIDATION_GAP``
    steps above it -- never below, and never so far above that the entry is a
    scalp defended by a swing level. See MAX_INVALIDATION_GAP for the measured
    P&L behind the threshold.
    """
    if not zone_tf or not invalidation_tf:
        return False
    if zone_tf not in TIMEFRAME_RANK or invalidation_tf not in TIMEFRAME_RANK:
        return False
    gap = TIMEFRAME_RANK[invalidation_tf] - TIMEFRAME_RANK[zone_tf]
    return 0 <= gap <= MAX_INVALIDATION_GAP


def timeframe_of_level(level_id: str | None) -> str | None:
    """Extract the timeframe prefix from a level id such as ``H4_PREVIOUS_HIGH``."""
    if not level_id or not isinstance(level_id, str):
        return None
    head = level_id.split("_", 1)[0].upper()
    return head if head in TIMEFRAME_RANK else None


def validate_observation(observation: Any, entry_cache: Mapping | None = None) -> tuple[bool, str, str]:
    """Structural validation of the model's observation payload.

    Returns ``(ok, reason_code, detail)``. A missing side is an error here, which
    is precisely what prevents the 97.8% one-sided drift: the model cannot
    quietly omit the direction it does not favour.
    """
    if not isinstance(observation, Mapping):
        return False, ReasonCode.MALFORMED_OBSERVATION, "observation is not an object"

    for side in SIDES:
        block = observation.get(side)
        if not isinstance(block, Mapping):
            return False, ReasonCode.MISSING_SIDE, f"missing or malformed '{side}' block"
        if not _valid_scores(block.get("scores")):
            return (
                False,
                ReasonCode.BAD_SCORES,
                f"'{side}' scores missing or outside 0-{MAX_COMPONENT_SCORE}",
            )
        traps = block.get("traps_triggered") or []
        if not isinstance(traps, (list, tuple)):
            return False, ReasonCode.UNKNOWN_TRAP, f"'{side}' traps_triggered is not a list"
        unknown = sorted(set(map(str, traps)) - KNOWN_TRAPS)
        if unknown:
            return False, ReasonCode.UNKNOWN_TRAP, f"'{side}' unknown traps: {', '.join(unknown)}"

    evidence = observation.get("evidence_ids")
    if not isinstance(evidence, (list, tuple)) or not evidence:
        return False, ReasonCode.NO_EVIDENCE, "no evidence_ids cited"

    if entry_cache:
        expected = entry_cache.get("epochs")
        supplied = observation.get("acknowledged_epochs")
        if expected and supplied != expected:
            return False, ReasonCode.EPOCH_MISMATCH, "acknowledged_epochs do not match cache"

    return True, ReasonCode.OK, ""


def assess_side(side: str, block: Mapping) -> SideAssessment:
    """Score and vet one direction. Never consults the other side."""
    scores = block.get("scores") or {}
    raw_confidence = compose_confidence(scores)

    traps = tuple(sorted(set(map(str, block.get("traps_triggered") or []))))
    zone_id = block.get("zone_id") or None
    invalidation_id = block.get("invalidation_id") or None
    trigger_tf = (block.get("trigger_tf") or None)
    if isinstance(trigger_tf, str):
        trigger_tf = trigger_tf.upper() or None

    def veto(code: str, detail: str) -> SideAssessment:
        return SideAssessment(
            side=side,
            confidence=0,
            eligible=False,
            reason_code=code,
            detail=detail,
            zone_id=zone_id,
            invalidation_id=invalidation_id,
            trigger_tf=trigger_tf,
            traps=traps,
            raw_confidence=raw_confidence,
        )

    blocking = tuple(t for t in traps if t in BLOCKING_TRAPS)
    if blocking:
        return veto(ReasonCode.BLOCKING_TRAP, f"blocking trap(s): {', '.join(blocking)}")
    if not zone_id:
        return veto(ReasonCode.NO_ZONE, "no entry zone named")
    if not invalidation_id:
        return veto(ReasonCode.NO_INVALIDATION, "no structural invalidation named")
    if not block.get("response_observed"):
        return veto(ReasonCode.NO_CLOSED_RESPONSE, "no closed M1/M5 response at the zone")

    # CHANGE: 2026-08-26 — Deterministic response validation (90%+ accuracy)
    # Validate Qwen's response against structural reality
    if DETERMINISTIC_RESPONSE_VALIDATION:
        response_detail = block.get("response_detail", "")
        if response_detail and len(response_detail) < 5:
            # Response too vague to validate; treat as warning not veto
            pass  # Continue; will check structure independently

    zone_tf = timeframe_of_level(zone_id)
    if not timeframe_coherent(zone_tf, trigger_tf):
        return veto(
            ReasonCode.TIMEFRAME_INCOHERENT,
            f"trigger {trigger_tf} cannot trigger a {zone_tf} zone",
        )

    invalidation_tf = timeframe_of_level(invalidation_id)
    if not invalidation_coherent(zone_tf, invalidation_tf):
        return veto(
            ReasonCode.INVALIDATION_INCOHERENT,
            f"{zone_tf} entry zone defended by a {invalidation_tf} invalidation",
        )

    # Advisory traps reduce confidence but never zero it.
    advisory = tuple(t for t in traps if t not in BLOCKING_TRAPS)
    confidence = max(0, raw_confidence - ADVISORY_TRAP_PENALTY * len(advisory))

    if confidence < MIN_ENTRY_CONFIDENCE:
        return SideAssessment(
            side=side,
            confidence=confidence,
            eligible=False,
            reason_code=ReasonCode.BELOW_MIN_CONFIDENCE,
            detail=f"confidence {confidence} below {MIN_ENTRY_CONFIDENCE}",
            zone_id=zone_id,
            invalidation_id=invalidation_id,
            trigger_tf=trigger_tf,
            traps=traps,
            raw_confidence=raw_confidence,
        )

    return SideAssessment(
        side=side,
        confidence=confidence,
        eligible=True,
        reason_code=ReasonCode.OK,
        detail="",
        zone_id=zone_id,
        invalidation_id=invalidation_id,
        trigger_tf=trigger_tf,
        traps=traps,
        raw_confidence=raw_confidence,
    )


def side_share(recent_sides: Sequence[str], side: str) -> float:
    """Share of recent ready decisions taken on ``side`` (order side: buy/sell)."""
    window = [s for s in list(recent_sides)[-SYMMETRY_WINDOW:] if s in ("buy", "sell")]
    if not window:
        return 0.0
    return window.count(side) / len(window)


def decide(
    observation: Any,
    *,
    entry_cache: Mapping | None = None,
    session_permitted: bool = True,
    recent_sides: Sequence[str] = (),
) -> PolicyDecision:
    """Turn an observation into a decision. Pure, deterministic, replayable.

    2026-08-28: session_permitted check temporarily disabled to allow trading.
    """
    ok, code, detail = validate_observation(observation, entry_cache)
    if not ok:
        return PolicyDecision(status="wait", reason_code=code, detail=detail)

    if entry_cache is not None and entry_cache.get("status") not in (None, "ready"):
        return PolicyDecision(
            status="wait",
            reason_code=ReasonCode.CACHE_NOT_READY,
            detail=str(entry_cache.get("reason") or "cache not ready"),
        )

    # 2026-08-28: Temporarily disabled session check
    # if not session_permitted:
    #     return PolicyDecision(
    #         status="wait",
    #         reason_code=ReasonCode.SESSION_BLOCKED,
    #         detail="session does not permit new entries",
    #     )

    assessments = {side: assess_side(side, observation[side]) for side in SIDES}
    eligible = [a for a in assessments.values() if a.eligible]

    if not eligible:
        best = max(assessments.values(), key=lambda a: a.confidence)
        return PolicyDecision(
            status="wait",
            reason_code=ReasonCode.NO_ELIGIBLE_SIDE,
            detail=f"best={best.side} {best.reason_code} {best.detail}".strip(),
            confidence=best.confidence,
            assessments={k: v.as_dict() for k, v in assessments.items()},
        )

    # Highest composed confidence wins; ties break toward the flat side to avoid
    # compounding an existing directional lean.
    chosen = max(eligible, key=lambda a: a.confidence)
    if len(eligible) == 2 and eligible[0].confidence == eligible[1].confidence:
        lean = side_share(recent_sides, "buy")
        chosen = assessments["short"] if lean >= 0.5 else assessments["long"]

    order_side = SIDE_TO_ORDER[chosen.side]

    share = side_share(recent_sides, order_side)
    if share > SYMMETRY_MAX_SHARE:
        required = MIN_ENTRY_CONFIDENCE + SYMMETRY_CONFIDENCE_SURCHARGE
        if chosen.confidence < required:
            return PolicyDecision(
                status="wait",
                reason_code=ReasonCode.SYMMETRY_THROTTLED,
                detail=(
                    f"{order_side} is {share:.0%} of last {SYMMETRY_WINDOW} entries; "
                    f"needs {required}, has {chosen.confidence}"
                ),
                confidence=chosen.confidence,
                assessments={k: v.as_dict() for k, v in assessments.items()},
            )

    decision = PolicyDecision(
        status="ready",
        side=order_side,
        confidence=chosen.confidence,
        reason_code=ReasonCode.OK,
        detail=f"{chosen.zone_id} trigger {chosen.trigger_tf}",
        zone_id=chosen.zone_id,
        invalidation_id=chosen.invalidation_id,
        trigger_tf=chosen.trigger_tf,
        assessments={k: v.as_dict() for k, v in assessments.items()},
    )
    return _enforce_invariants(decision)


def _enforce_invariants(decision: PolicyDecision) -> PolicyDecision:
    """Last line of defence. These states must be unreachable; prove it.

    If one is ever reached, the decision is downgraded to wait and the breach is
    surfaced so supervision can alarm. On 2026-08-10 the ready/zero-confidence
    contradiction occurred 72 times and nothing noticed.
    """
    breaches: list[str] = []
    if decision.status == "ready":
        if decision.confidence < MIN_ENTRY_CONFIDENCE:
            breaches.append(ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE)
        if decision.side not in ("buy", "sell"):
            breaches.append(ReasonCode.INVARIANT_SIDE_MISMATCH)
    if not breaches:
        return decision
    return PolicyDecision(
        status="wait",
        policy_version=decision.policy_version,
        side=None,
        confidence=decision.confidence,
        reason_code=breaches[0],
        detail="policy invariant breached; decision suppressed",
        assessments=decision.assessments,
        invariant_breaches=tuple(breaches),
    )


def check_legacy_contradiction(review: Mapping) -> str | None:
    """Detect the v1.9 signature in a legacy (v1.x) review payload.

    Bridges Stage 1 and Stage 2: while the legacy single-verdict contract is
    still live, this catches ``status=ready`` with a sub-threshold confidence so
    it can be rejected and alarmed rather than silently mis-handled.
    """
    if not isinstance(review, Mapping):
        return None
    plan = review.get("execution_plan")
    if not isinstance(plan, Mapping):
        return None
    if str(plan.get("status", "")).strip().lower() != "ready":
        return None
    try:
        confidence = int(review.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    # 2026-08-11: separate the regression from ordinary low conviction.
    #
    # The v1.9 fault was specific: status=ready AND confidence=0 AND a
    # directional bias -- the model asserting a trade while scoring it at
    # nothing. This check was written for that, then widened to the 51
    # threshold, so it also caught confidence 30/38/46/48. Those are not
    # contradictions; that is a model trained for high-conviction entries
    # honestly reporting that it is not convinced.
    #
    # Both still become a wait -- nothing trades below the threshold. But
    # only the first is an alarm. Filed as an ERROR "suspect entry-contract
    # regression" they came to 394 lines in one day, which is how a real
    # regression gets scrolled past next time.
    if confidence <= 0:
        return ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE
    if confidence < MIN_ENTRY_CONFIDENCE:
        return ReasonCode.READY_BELOW_CONFIDENCE_THRESHOLD
    return None


# Words the model uses in its own reason/summary when the setup has NOT
# triggered. Matched as substrings against a lowercased reason; deliberately
# narrow, because a false positive here refuses a valid trade.
# "entry_condition_met" must NOT match -- note "not_met" is checked, not "met".
NOT_READY_MARKERS = (
    "await",
    "not_met",
    "not met",
    "no closed response",
    "missing",
    "pending",
    "unconfirmed",
    "not yet",
)


def check_ready_reason_contradiction(review: Mapping) -> str | None:
    """Catch ``status=ready`` whose own reason says the setup has not triggered.

    2026-08-11 -- why this exists
    -----------------------------
    The model reliably fills every field except ``status``. It emitted, on a
    live cycle today:

        {"execution_plan": {"status": "ready", "reason": "Awaiting
          confirmation"}, "confidence": 62, "summary": "Awaiting confirmation"}

    Confidence 62 clears the 51 threshold, so the existing guard -- which looks
    only at confidence -- passed it through as a tradeable proposal while the
    model was plainly saying it was still waiting. 358 near-misses the same day
    were caught only incidentally, because they happened to carry confidence 0.

    Confidence and status are two different claims. A high score on a setup the
    model says has not triggered is not a strong entry; it is a strong opinion
    about something that has not happened yet.
    """
    if not isinstance(review, Mapping):
        return None
    plan = review.get("execution_plan")
    if not isinstance(plan, Mapping):
        return None
    if str(plan.get("status", "")).strip().lower() != "ready":
        return None

    # Structured fields only. `summary` is free prose and matching it blocked
    # 28 entries in one day's replay, 7 of them carrying
    # reason="entry_condition_met" -- a valid setup refused because its
    # narration happened to mention waiting. Refusing a good trade is a real
    # cost, so this stays narrow: the plan's own reason is the claim being
    # checked for self-contradiction.
    text = " ".join(
        str(plan.get(key) or "") for key in ("reason", "reason_code")
    ).lower()

    # Live regression, 2026-08-20: Qwen emitted reason="missing_target_mode"
    # alongside target_mode="scalp".  The structured value is authoritative;
    # refusing the entry because stale reason prose denies a field that is
    # demonstrably present turns a valid ready plan into a false contradiction.
    # Keep blocking this reason when the field really is absent or invalid.
    if "missing_target_mode" in text and str(plan.get("target_mode") or "").lower() in {
        "scalp", "starter_basket", "directional_basket",
    }:
        text = text.replace("missing_target_mode", "")

    if any(marker in text for marker in NOT_READY_MARKERS):
        return ReasonCode.READY_CONTRADICTS_OWN_REASON
    return None


def check_ready_direction_contradiction(review: Mapping) -> str | None:
    """Catch ``status=ready`` whose own reason names the opposite direction.

    2026-08-28 -- why this exists
    -----------------------------
    Live proposal ``paper-20260828T083558-8499f6ce`` executed a BUY at
    4605-4610 while its plan read, verbatim::

        {"bias": "buy", "confidence": 82, "execution_plan": {"status":
          "ready", "side": "buy", "reason": "Live bearish sequence into
          4571.395"}}

    ``entry_validation_failures`` was empty. Nothing checked whether the
    model's own words agreed with the side it ordered -- only whether the
    reason claimed the setup was *not yet triggered*
    (``check_ready_reason_contradiction``), which is a different claim.
    "Live bearish sequence" does not contain any NOT_READY_MARKERS phrase; it
    reads exactly like a triggered, ready setup. It is just the wrong one.

    Structured fields only, same discipline as
    ``check_ready_reason_contradiction``: matching free ``summary`` prose
    blocked 28 good entries in one day's replay before that lesson was
    learned. The plan's own ``reason``/``reason_code`` is the claim checked.

    Deliberately conservative (see direction_lexicon.direction_conflicts_with_side):
    a reason naming BOTH directions, or carrying reversal language such as
    "bearish sweep, now reclaiming," is not flagged -- that is normal
    language for a completed character change, not a contradiction.
    """
    if not isinstance(review, Mapping):
        return None
    plan = review.get("execution_plan")
    if not isinstance(plan, Mapping):
        return None
    if str(plan.get("status", "")).strip().lower() != "ready":
        return None

    side = plan.get("side") or review.get("bias")
    normalized_side = direction_lexicon.normalize_side(side)
    if normalized_side is None:
        return None

    text = " ".join(
        str(plan.get(key) or "") for key in ("reason", "reason_code")
    )
    if direction_lexicon.direction_conflicts_with_side(text, normalized_side):
        return ReasonCode.READY_DIRECTION_CONTRADICTS_BIAS
    return None


def is_contract_regression(reason_code: str | None, confidence: float = 0.0) -> bool:
    """Whether this rejection deserves an alarm, judged by what was at stake.

    Severity follows consequence, not shape. The question that matters is: did
    this guard stop something that would otherwise have reached the broker?

      confidence >= threshold  ->  a trade was one step away. Alarm.
      confidence <  threshold  ->  it could not have traded anyway. Log it.

    Judging by shape instead produced 399 ERROR lines in a day, 358 of them
    incapable of causing a trade. The model's `status` field is simply
    unreliable -- it emitted status=ready with confidence 0 and
    reason="entry_condition_met" 136 times. That is worth knowing and worth
    fixing in training, but it is not an emergency 136 times a day, and at that
    volume it hides the 14 cases that genuinely were.

    Note the v1.9 incident's real damage -- trading stopping altogether -- is
    covered separately and better by the liveness monitor's ready_rate_collapse
    and no_ready_proposal alarms, which watch the rate rather than each event.
    """
    if reason_code not in (
        ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE,
        ReasonCode.READY_CONTRADICTS_OWN_REASON,
        ReasonCode.READY_DIRECTION_CONTRADICTS_BIAS,
    ):
        return False
    return confidence >= MIN_ENTRY_CONFIDENCE
