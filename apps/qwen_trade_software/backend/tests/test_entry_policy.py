"""Invariant tests for entry_policy.

Each test names the 2026-08-10 failure it prevents. If one of these fails, the
corresponding production incident is reachable again.

Run:  python -m pytest apps/qwen_trade_software/backend/tests -q
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import entry_policy as ep  # noqa: E402


# --- helpers ---------------------------------------------------------------

def scores(location=8, response=8, participation=7, htf_alignment=8, plan_fit=7):
    return {
        "location": location,
        "response": response,
        "participation": participation,
        "htf_alignment": htf_alignment,
        "plan_fit": plan_fit,
    }


def side_block(zone="M30_PREVIOUS_LOW", invalidation="H1_PREVIOUS_LOW",
               trigger="M30", response_observed=True, traps=(), **score_kw):
    return {
        "zone_id": zone,
        "invalidation_id": invalidation,
        "trigger_tf": trigger,
        "response_observed": response_observed,
        "traps_triggered": list(traps),
        "scores": scores(**score_kw),
    }


def observation(long_block=None, short_block=None, epochs=None, evidence=("E1",)):
    obs = {
        "read": {"htf_auction": "bullish_unfinished", "htf_timeframe": "H4",
                 "location": "at_support", "acceptance": "none"},
        "long": long_block if long_block is not None else side_block(),
        "short": short_block if short_block is not None else side_block(
            zone="M15_PREVIOUS_HIGH", invalidation="H4_PREVIOUS_HIGH",
            trigger="M15", location=2, response=1, participation=1,
            htf_alignment=1, plan_fit=1,
        ),
        "evidence_ids": list(evidence),
    }
    if epochs is not None:
        obs["acknowledged_epochs"] = epochs
    return obs


# --- weights ---------------------------------------------------------------

def test_weights_sum_to_one():
    assert round(sum(ep.SCORE_WEIGHTS.values()), 6) == 1.0


# --- the v1.9 regression ---------------------------------------------------

def test_confidence_zero_impossible_with_positive_scores():
    """v1.9 signature: confidence 0 alongside a positive directional read."""
    assert ep.compose_confidence(scores()) > 0
    assert ep.compose_confidence(scores(1, 1, 1, 1, 1)) > 0


def test_confidence_zero_only_when_everything_is_zero():
    assert ep.compose_confidence(scores(0, 0, 0, 0, 0)) == 0


def test_confidence_is_bounded():
    assert ep.compose_confidence(scores(10, 10, 10, 10, 10)) == 100
    assert ep.compose_confidence(scores(99, 99, 99, 99, 99)) == 100
    assert ep.compose_confidence(scores(-5, -5, -5, -5, -5)) == 0


def test_ready_can_never_carry_subthreshold_confidence():
    """The 72 ready+confidence=0 contradictions become unreachable."""
    decision = ep.decide(observation())
    if decision.status == "ready":
        assert decision.confidence >= ep.MIN_ENTRY_CONFIDENCE


def test_invariant_suppresses_a_forged_ready():
    forged = ep.PolicyDecision(status="ready", side="buy", confidence=0)
    guarded = ep._enforce_invariants(forged)
    assert guarded.status == "wait"
    assert ep.ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE in guarded.invariant_breaches


def test_legacy_contradiction_detector_catches_v19():
    review = {"confidence": 0, "bias": "buy",
              "execution_plan": {"status": "ready", "reason": "confirmed"}}
    assert ep.check_legacy_contradiction(review) == ep.ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE


def test_legacy_detector_passes_healthy_review():
    review = {"confidence": 82, "bias": "sell",
              "execution_plan": {"status": "ready", "reason": "confirmed"}}
    assert ep.check_legacy_contradiction(review) is None


# --- one-sided drift -------------------------------------------------------

def test_missing_side_is_a_contract_violation():
    """44 sell / 1 buy could happen because nothing required both sides."""
    obs = observation()
    del obs["short"]
    ok, code, _ = ep.validate_observation(obs)
    assert not ok and code == ep.ReasonCode.MISSING_SIDE


def test_better_side_is_selected_regardless_of_direction():
    strong_short = side_block(zone="M15_PREVIOUS_HIGH", invalidation="H4_PREVIOUS_HIGH",
                              trigger="M15")
    weak_long = side_block(location=1, response=1, participation=1,
                           htf_alignment=1, plan_fit=1)
    decision = ep.decide(observation(long_block=weak_long, short_block=strong_short))
    assert decision.status == "ready"
    assert decision.side == "sell"

    decision = ep.decide(observation())  # long strong, short weak
    assert decision.status == "ready"
    assert decision.side == "buy"


def test_symmetry_throttle_raises_the_bar_for_a_dominant_side():
    recent = ["sell"] * 50
    marginal = side_block(zone="M15_PREVIOUS_HIGH", invalidation="H4_PREVIOUS_HIGH",
                          trigger="M15", location=6, response=5, participation=5,
                          htf_alignment=6, plan_fit=5)
    weak_long = side_block(location=0, response=0, participation=0,
                           htf_alignment=0, plan_fit=0)
    decision = ep.decide(
        observation(long_block=weak_long, short_block=marginal),
        recent_sides=recent,
    )
    assert decision.status == "wait"
    assert decision.reason_code == ep.ReasonCode.SYMMETRY_THROTTLED


def test_symmetry_throttle_still_allows_a_strong_dominant_side():
    recent = ["sell"] * 50
    strong_short = side_block(zone="M15_PREVIOUS_HIGH", invalidation="H4_PREVIOUS_HIGH",
                              trigger="M15", location=10, response=10, participation=10,
                              htf_alignment=10, plan_fit=10)
    weak_long = side_block(location=0, response=0, participation=0,
                           htf_alignment=0, plan_fit=0)
    decision = ep.decide(
        observation(long_block=weak_long, short_block=strong_short),
        recent_sides=recent,
    )
    assert decision.status == "ready" and decision.side == "sell"


def test_side_share_is_windowed():
    assert ep.side_share(["buy"] * 50, "buy") == 1.0
    assert ep.side_share(["sell"] * 25 + ["buy"] * 25, "buy") == 0.5
    assert ep.side_share([], "buy") == 0.0


# --- timeframe coherence ---------------------------------------------------

def test_m1_trigger_cannot_fire_an_h4_zone():
    """The M1-entry / H4-frame mismatch behind every -153.5 loss."""
    assert not ep.timeframe_coherent("H4", "M1")
    assert not ep.timeframe_coherent("H1", "M1")


def test_trigger_may_be_same_or_one_step_below():
    assert ep.timeframe_coherent("M30", "M30")
    assert ep.timeframe_coherent("M30", "M15")
    assert not ep.timeframe_coherent("M30", "M5")


def test_trigger_above_zone_timeframe_is_rejected():
    assert not ep.timeframe_coherent("M5", "H1")


def test_incoherent_side_is_vetoed_with_a_code():
    block = side_block(zone="H4_PREVIOUS_HIGH", invalidation="D1_PREVIOUS_HIGH",
                       trigger="M1")
    assessment = ep.assess_side("short", block)
    assert not assessment.eligible
    assert assessment.reason_code == ep.ReasonCode.TIMEFRAME_INCOHERENT


def test_timeframe_of_level():
    assert ep.timeframe_of_level("H4_PREVIOUS_HIGH") == "H4"
    assert ep.timeframe_of_level("M30_PREVIOUS_LOW") == "M30"
    assert ep.timeframe_of_level("SYNTH_STOP_M30") is None
    assert ep.timeframe_of_level(None) is None


# --- traps -----------------------------------------------------------------

def test_blocking_trap_vetoes_the_side():
    block = side_block(traps=["sell_into_support"])
    assessment = ep.assess_side("short", block)
    assert not assessment.eligible
    assert assessment.reason_code == ep.ReasonCode.BLOCKING_TRAP


def test_advisory_trap_reduces_confidence_but_does_not_zero_it():
    """The v1.9 lesson: traps govern permission, they do not annihilate score."""
    clean = ep.assess_side("long", side_block())
    advised = ep.assess_side("long", side_block(traps=["stale_zone"]))
    assert advised.confidence < clean.confidence
    assert advised.confidence > 0
    assert advised.raw_confidence == clean.raw_confidence


def test_unknown_trap_is_rejected():
    obs = observation(long_block=side_block(traps=["made_up_trap"]))
    ok, code, _ = ep.validate_observation(obs)
    assert not ok and code == ep.ReasonCode.UNKNOWN_TRAP


# --- other vetoes ----------------------------------------------------------

def test_missing_closed_response_is_vetoed():
    assessment = ep.assess_side("long", side_block(response_observed=False))
    assert not assessment.eligible
    assert assessment.reason_code == ep.ReasonCode.NO_CLOSED_RESPONSE


def test_missing_invalidation_is_vetoed():
    assessment = ep.assess_side("long", side_block(invalidation=""))
    assert not assessment.eligible
    assert assessment.reason_code == ep.ReasonCode.NO_INVALIDATION


def test_bad_scores_rejected():
    obs = observation()
    obs["long"]["scores"]["location"] = 99
    ok, code, _ = ep.validate_observation(obs)
    assert not ok and code == ep.ReasonCode.BAD_SCORES


def test_missing_evidence_rejected():
    obs = observation(evidence=())
    ok, code, _ = ep.validate_observation(obs)
    assert not ok and code == ep.ReasonCode.NO_EVIDENCE


def test_epoch_mismatch_rejected():
    obs = observation(epochs={"minute": "wrong"})
    ok, code, _ = ep.validate_observation(obs, {"epochs": {"minute": "right"}})
    assert not ok and code == ep.ReasonCode.EPOCH_MISMATCH


def test_session_block_is_respected():
    decision = ep.decide(observation(), session_permitted=False)
    assert decision.status == "wait"
    assert decision.reason_code == ep.ReasonCode.SESSION_BLOCKED


def test_cache_not_ready_is_respected():
    decision = ep.decide(observation(), entry_cache={"status": "blocked", "reason": "x"})
    assert decision.status == "wait"
    assert decision.reason_code == ep.ReasonCode.CACHE_NOT_READY


def test_no_eligible_side_reports_the_best_attempt():
    weak = side_block(location=0, response=0, participation=0,
                      htf_alignment=0, plan_fit=0)
    decision = ep.decide(observation(long_block=weak, short_block=weak))
    assert decision.status == "wait"
    assert decision.reason_code == ep.ReasonCode.NO_ELIGIBLE_SIDE


def test_decision_is_deterministic():
    obs = observation()
    assert ep.decide(obs).as_dict() == ep.decide(obs).as_dict()


def test_every_wait_carries_a_reason_code():
    """Bare prose failures cannot be counted or alerted on."""
    cases = [
        ep.decide("not a dict"),
        ep.decide(observation(), session_permitted=False),
        ep.decide(observation(), entry_cache={"status": "blocked"}),
    ]
    for decision in cases:
        assert decision.status == "wait"
        assert decision.reason_code and decision.reason_code != ep.ReasonCode.OK


# --- low confidence is not a contract regression ----------------------------

def test_sub_threshold_confidence_is_not_reported_as_a_regression():
    """2026-08-11: 394 ERROR lines in one day, 38 of them at confidence 30-48.

    The model is trained for high-conviction entries. Scoring a setup at 46 and
    declining to trade it is the system working, not the contract breaking.
    Filing it as 'suspect entry-contract regression' buries the alarm that
    exists to catch the real thing.
    """
    for confidence in (30, 38, 46, 48, 50):
        review = {"confidence": confidence, "bias": "buy",
                  "execution_plan": {"status": "ready", "reason": "confirmed"}}
        code = ep.check_legacy_contradiction(review)
        assert code == ep.ReasonCode.READY_BELOW_CONFIDENCE_THRESHOLD, confidence
        assert not ep.is_contract_regression(code, confidence), (
            f"confidence {confidence} must not be alarmed -- it cannot trade"
        )


def test_zero_confidence_is_still_a_regression():
    """The v1.9 signature -- ready, a bias, and a score of nothing."""
    review = {"confidence": 0, "bias": "buy",
              "execution_plan": {"status": "ready", "reason": "confirmed"}}
    code = ep.check_legacy_contradiction(review)
    assert code == ep.ReasonCode.INVARIANT_READY_ZERO_CONFIDENCE
    # Confidence 0 cannot reach the broker, so it is logged, not alarmed.
    assert not ep.is_contract_regression(code, 0)


def test_both_cases_still_refuse_to_trade():
    """Severity changed; behaviour did not. Nothing trades below threshold."""
    for confidence in (0, 46):
        review = {"confidence": confidence, "bias": "buy",
                  "execution_plan": {"status": "ready", "reason": "confirmed"}}
        assert ep.check_legacy_contradiction(review) is not None


def test_threshold_confidence_passes_clean():
    review = {"confidence": ep.MIN_ENTRY_CONFIDENCE, "bias": "buy",
              "execution_plan": {"status": "ready", "reason": "confirmed"}}
    assert ep.check_legacy_contradiction(review) is None


# --- ready that contradicts its own reason ----------------------------------

def test_ready_with_a_reason_that_says_not_triggered_is_blocked():
    """2026-08-11, live: confidence 62 (over the 51 gate) on a plan whose own
    reason read 'Awaiting confirmation'. Confidence and status are separate
    claims; a high score on something that has not happened is not an entry.

    Replay of the day found 14 such proposals at tradeable confidence."""
    for reason in (
        "Awaiting confirmation",
        "entry_trigger_missing",
        "entry_signal_missing",
        "missing_evidence",
        "entry_condition_not_met",
        "no closed response at H4_PREVIOUS_LOW",
    ):
        review = {"confidence": 62, "bias": "buy",
                  "execution_plan": {"status": "ready", "reason": reason}}
        assert ep.check_ready_reason_contradiction(review) == (
            ep.ReasonCode.READY_CONTRADICTS_OWN_REASON
        ), reason
        assert ep.is_contract_regression(
            ep.ReasonCode.READY_CONTRADICTS_OWN_REASON, 62
        ), "at tradeable confidence this one can reach the broker -- alarm"


def test_a_genuinely_triggered_setup_is_not_blocked():
    """Refusing a valid trade is a real cost. 'entry_condition_met' contains
    'met' but not 'not_met' -- the marker list must not fire on it."""
    for reason in ("entry_condition_met", "entry_rule_match", "entry_trigger",
                   "no_conflict", "opposite side of printed extreme", ""):
        review = {"confidence": 62, "bias": "buy",
                  "execution_plan": {"status": "ready", "reason": reason}}
        assert ep.check_ready_reason_contradiction(review) is None, reason


def test_present_target_mode_overrules_stale_missing_target_reason():
    """Exact 2026-08-20 live contract inconsistency must not reject a scalp."""
    review = {
        "confidence": 60,
        "bias": "sell",
        "execution_plan": {
            "status": "ready",
            "reason": "missing_target_mode",
            "target_mode": "scalp",
        },
    }
    assert ep.check_ready_reason_contradiction(review) is None


def test_missing_target_mode_is_still_blocked_when_really_missing():
    review = {
        "confidence": 60,
        "bias": "sell",
        "execution_plan": {"status": "ready", "reason": "missing_target_mode"},
    }
    assert ep.check_ready_reason_contradiction(review) == (
        ep.ReasonCode.READY_CONTRADICTS_OWN_REASON
    )


def test_free_prose_summary_is_not_matched():
    """Matching the narration blocked 28 entries in one day's replay, 7 of them
    reason='entry_condition_met'. Only the structured reason is checked."""
    review = {
        "confidence": 62, "bias": "buy",
        "summary": "Buying the retest; we were awaiting this all session.",
        "execution_plan": {"status": "ready", "reason": "entry_condition_met"},
    }
    assert ep.check_ready_reason_contradiction(review) is None


def test_wait_status_is_left_alone():
    review = {"confidence": 20, "bias": "buy",
              "execution_plan": {"status": "wait", "reason": "missing_evidence"}}
    assert ep.check_ready_reason_contradiction(review) is None


def test_alarm_severity_follows_what_was_at_stake():
    """Alarm when the guard stopped a trade; log when nothing could have traded.

    399 ERROR lines in one day, 358 of them incapable of causing a trade, is
    how the 14 that could have gets missed.
    """
    code = ep.ReasonCode.READY_CONTRADICTS_OWN_REASON
    assert ep.is_contract_regression(code, ep.MIN_ENTRY_CONFIDENCE)
    assert ep.is_contract_regression(code, 95)
    assert not ep.is_contract_regression(code, ep.MIN_ENTRY_CONFIDENCE - 1)
    assert not ep.is_contract_regression(code, 0)
    assert not ep.is_contract_regression(None, 95)
    assert not ep.is_contract_regression("entry:provenance_failed", 95)
