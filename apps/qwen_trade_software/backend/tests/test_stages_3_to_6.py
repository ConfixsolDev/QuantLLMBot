"""Tests for Stage 3 (geometry), 4 (management), 5 (gates), 6 (ledger).

Each test names the 2026-08-10 behaviour it encodes or prevents.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import trade_geometry as tg          # noqa: E402
import management_policy as mp       # noqa: E402
import contract_gate as cg           # noqa: E402
import configuration_ledger as cl    # noqa: E402


# ===========================================================================
# Stage 3 -- structural bracket, size as the free variable
# ===========================================================================

def test_size_shrinks_as_stop_widens_keeping_risk_constant():
    """The inversion that makes structural stops affordable."""
    tight = tg.size_for_risk(3.0, 150.0)
    wide = tg.size_for_risk(6.0, 150.0)
    assert wide < tight
    assert tight * 3.0 * tg.VALUE_PER_PRICE_UNIT_PER_LOT == pytest.approx(150.0, abs=5)
    assert wide * 6.0 * tg.VALUE_PER_PRICE_UNIT_PER_LOT == pytest.approx(150.0, abs=5)


def test_stop_sits_beyond_the_invalidation_not_inside_it():
    """The fixed $3 stop sat a median 1.18 INSIDE the structural level."""
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0,
        invalidation_price=4344.0, target_price=4332.0, frame="M30",
    )
    assert bracket.ok
    assert bracket.stop_loss > 4344.0, "stop must sit beyond the invalidation"


def test_buy_stop_sits_below_invalidation():
    bracket = tg.build_bracket(
        side="buy", entry_price=4340.0,
        invalidation_price=4336.0, target_price=4348.0, frame="M30",
    )
    assert bracket.ok
    assert bracket.stop_loss < 4336.0


def test_wrong_side_invalidation_rejected():
    bracket = tg.build_bracket(
        side="buy", entry_price=4340.0,
        invalidation_price=4344.0, target_price=4348.0,
    )
    assert not bracket.ok
    assert bracket.reason_code == tg.GeometryReason.INVALIDATION_WRONG_SIDE


def test_wrong_side_target_rejected():
    bracket = tg.build_bracket(
        side="buy", entry_price=4340.0,
        invalidation_price=4336.0, target_price=4330.0,
    )
    assert not bracket.ok
    assert bracket.reason_code == tg.GeometryReason.TARGET_WRONG_SIDE


def test_poor_reward_risk_rejected():
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0,
        invalidation_price=4346.0, target_price=4338.0, frame="M30",
    )
    assert not bracket.ok
    assert bracket.reason_code == tg.GeometryReason.REWARD_RISK_TOO_LOW


def test_absurdly_wide_stop_rejected():
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0,
        invalidation_price=4400.0, target_price=4200.0, frame="D1",
    )
    assert not bracket.ok
    assert bracket.reason_code == tg.GeometryReason.STOP_TOO_WIDE


def test_missing_structure_falls_back_to_legacy_bracket():
    """Degrade to today's behaviour rather than leaving a position unprotected."""
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0,
        invalidation_price=None, target_price=None,
    )
    assert bracket.reason_code == tg.GeometryReason.FELL_BACK_TO_FIXED
    assert bracket.stop_distance == tg.LEGACY_STOP_DISTANCE
    assert bracket.target_distance == tg.LEGACY_TARGET_DISTANCE
    assert bracket.stop_loss == pytest.approx(4343.0)


def test_fallback_can_be_disabled():
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0, invalidation_price=None,
        target_price=4330.0, allow_fallback=False,
    )
    assert not bracket.ok
    assert bracket.reason_code == tg.GeometryReason.NO_INVALIDATION


def test_expected_risk_tracks_the_budget():
    bracket = tg.build_bracket(
        side="sell", entry_price=4340.0, invalidation_price=4345.0,
        target_price=4325.0, frame="M30", risk_budget=150.0,
    )
    assert bracket.ok
    assert bracket.expected_risk == pytest.approx(150.0, abs=20)


def test_lot_rounding_never_rounds_risk_up():
    assert tg.round_lot(0.239) <= 0.24
    assert tg.round_lot(0.0) == 0.0


# ===========================================================================
# Stage 4 -- in-trade management (full discretion + solvency rail)
# ===========================================================================

def position(**kw):
    base = dict(
        side="sell", entry_price=4340.0, stop_loss=4343.0, take_profit=4335.0,
        volume=0.5, opened_at=1000.0, frame="M30", initial_stop_distance=3.0,
    )
    base.update(kw)
    return mp.Position(**base)


def test_tightening_is_accepted():
    pos = position()
    adj = mp.propose_stop(pos, 4341.0, price=4338.0)
    assert adj.accepted and adj.direction == "tighten"


def test_widening_is_permitted_under_full_discretion():
    """Operator chose full discretion; this must actually work."""
    pos = position()
    adj = mp.propose_stop(pos, 4344.0, price=4341.0, level_id="H1_PREVIOUS_HIGH")
    assert adj.accepted and adj.direction == "widen"


def test_widening_blocked_beyond_the_risk_ceiling():
    """Solvency rail: applies regardless of the discretion policy."""
    pos = position()
    adj = mp.propose_stop(pos, 4400.0, price=4341.0, level_id="D1_PREVIOUS_HIGH")
    assert not adj.accepted
    assert adj.reason_code == mp.AdjustReason.REJECTED_RISK_CEILING


def test_widening_requires_a_named_level():
    pos = position()
    adj = mp.propose_stop(pos, 4344.0, price=4341.0, level_id=None)
    assert not adj.accepted
    assert adj.reason_code == mp.AdjustReason.REJECTED_UNNAMED_LEVEL


def test_widening_limited_per_position():
    pos = position(widenings=mp.MAX_WIDENINGS_PER_POSITION)
    adj = mp.propose_stop(pos, 4344.0, price=4341.0, level_id="H1_PREVIOUS_HIGH")
    assert not adj.accepted
    assert adj.reason_code == mp.AdjustReason.REJECTED_WIDEN_LIMIT


def test_tighten_only_policy_blocks_widening():
    pos = position()
    adj = mp.propose_stop(pos, 4344.0, price=4341.0, level_id="H1",
                          policy=mp.STOP_POLICY_TIGHTEN_ONLY)
    assert not adj.accepted
    assert adj.reason_code == mp.AdjustReason.REJECTED_BY_POLICY


def test_stop_already_through_price_rejected():
    pos = position()
    adj = mp.propose_stop(pos, 4330.0, price=4338.0, level_id="M15")
    assert not adj.accepted
    assert adj.reason_code == mp.AdjustReason.REJECTED_WRONG_SIDE


def test_target_moves_both_ways_under_full_discretion():
    pos = position()
    extend = mp.propose_target(pos, 4330.0, price=4338.0, level_id="M30_LOW")
    reduce = mp.propose_target(pos, 4337.0, price=4338.5, level_id="M15_LOW")
    assert extend.accepted and extend.direction == "extend"
    assert reduce.accepted and reduce.direction == "reduce"


def test_fixed_target_policy_blocks_changes():
    pos = position()
    adj = mp.propose_target(pos, 4330.0, price=4338.0,
                            policy=mp.TARGET_POLICY_FIXED)
    assert not adj.accepted


def test_applying_a_widening_increments_the_counter():
    pos = position()
    adj = mp.propose_stop(pos, 4344.0, price=4341.0, level_id="H1_PREVIOUS_HIGH")
    updated = mp.apply(pos, adj)
    assert updated.stop_loss == 4344.0
    assert updated.widenings == pos.widenings + 1


def test_rejected_adjustment_leaves_position_untouched():
    pos = position()
    adj = mp.propose_stop(pos, 4400.0, price=4341.0, level_id="D1")
    assert mp.apply(pos, adj) == pos


def test_target_reached_beats_discretion():
    """Mechanical exits are classified before discretionary ones."""
    pos = position()
    decision = mp.evaluate_exit(pos, price=4334.0, now=1100.0,
                                model_requests_close=True)
    assert decision.reason == mp.ExitReason.TARGET_REACHED


def test_stop_hit_is_classified_mechanically():
    pos = position()
    decision = mp.evaluate_exit(pos, price=4344.0, now=1100.0)
    assert decision.should_exit
    assert decision.reason == mp.ExitReason.STOP_HIT


def test_time_stop_fires():
    pos = position()
    limit = mp.TIME_STOP_SECONDS["M30"]
    decision = mp.evaluate_exit(pos, price=4339.0, now=1000.0 + limit + 1)
    assert decision.should_exit
    assert decision.reason == mp.ExitReason.TIME_STOP


def test_model_close_is_attributed_to_a_named_reason():
    """Superseded MODEL_DISCRETION: a close must now say WHICH condition ended
    the trade, so Stage 6 can measure each one separately rather than lumping
    all judgement calls into a single bucket."""
    pos = position()
    decision = mp.evaluate_exit(pos, price=4339.0, now=1100.0,
                                model_requests_close=True,
                                opposite_setup_confirmed=True)
    assert decision.reason in mp.JUSTIFIED_DISCRETION
    assert decision.reason != "exit:model_discretion"


def test_healthy_position_stays_open():
    pos = position()
    assert not mp.evaluate_exit(pos, price=4339.0, now=1100.0).should_exit


# --- topic 10: named close conditions R1-R5 --------------------------------

def test_close_on_invalidation_is_honoured(mp_pos=None):
    """R1 -- the level that defined the trade failed on its own timeframe."""
    pos = position()
    d = mp.evaluate_exit(pos, price=4339.0, now=1100.0,
                         invalidation_closed_through=True)
    assert d.should_exit and d.reason == mp.ExitReason.INVALIDATION_CLOSED_THROUGH


def test_close_on_always_in_flip():
    """R2 -- Brooks' test: the opposite entry would now be taken."""
    pos = position()
    d = mp.evaluate_exit(pos, price=4339.0, now=1100.0,
                         model_requests_close=True,
                         opposite_setup_confirmed=True)
    assert d.should_exit and d.reason == mp.ExitReason.ALWAYS_IN_FLIP


def test_close_when_remaining_reward_risk_inverts():
    """R3 -- Brooks' trader's equation applied to an open position."""
    # sell entry 4340, stop 4343, target 4335; price 4336 leaves 1.0 reward
    # against 7.0 risk.
    pos = position()
    d = mp.evaluate_exit(pos, price=4336.0, now=1100.0, model_requests_close=True)
    assert d.should_exit and d.reason == mp.ExitReason.REWARD_RISK_INVERTED


def test_close_on_time_stop_without_progress():
    """R4 -- falsified by silence."""
    pos = position()
    limit = mp.TIME_STOP_SECONDS["M30"]
    d = mp.evaluate_exit(pos, price=4339.5, now=1000.0 + limit + 1,
                         structural_progress_pct=0.05)
    assert d.should_exit and d.reason == mp.ExitReason.TIME_STOP


def test_time_stop_does_not_close_a_working_trade():
    """Dalton -- a thesis can be correct and dormant; progress overrides the clock."""
    pos = position()
    limit = mp.TIME_STOP_SECONDS["M30"]
    d = mp.evaluate_exit(pos, price=4339.5, now=1000.0 + limit + 1,
                         structural_progress_pct=0.70)
    assert not d.should_exit


def test_discomfort_alone_does_not_close(monkeypatch):
    """R5 -- the -20.22 pattern. Underwater is not evidence."""
    pos = position()
    # Underwater on a sell (price above entry) but reward:risk still healthy and
    # no structural condition met.
    monkeypatch.setattr(mp, "MIN_REMAINING_REWARD_RISK", 0.05)
    d = mp.evaluate_exit(pos, price=4341.0, now=1100.0, model_requests_close=True)
    assert not d.should_exit
    assert d.reason == mp.ExitReason.UNJUSTIFIED_DISCRETION


def test_unjustified_close_can_be_allowed_explicitly(monkeypatch):
    """Escape hatch stays available, but is labelled so it can be counted."""
    pos = position()
    monkeypatch.setattr(mp, "MIN_REMAINING_REWARD_RISK", 0.05)
    d = mp.evaluate_exit(pos, price=4341.0, now=1100.0, model_requests_close=True,
                         allow_unjustified_close=True)
    assert d.should_exit and d.reason == mp.ExitReason.UNJUSTIFIED_DISCRETION


def test_remaining_reward_risk_computation():
    pos = position()   # sell 4340, stop 4343, target 4335
    assert mp.remaining_reward_risk(pos, 4340.0) == pytest.approx(5.0 / 3.0)
    assert mp.remaining_reward_risk(pos, 4336.0) == pytest.approx(1.0 / 7.0)


def test_justified_reasons_are_the_four_from_topic_10():
    assert mp.JUSTIFIED_DISCRETION == {
        mp.ExitReason.INVALIDATION_CLOSED_THROUGH,
        mp.ExitReason.ALWAYS_IN_FLIP,
        mp.ExitReason.REWARD_RISK_INVERTED,
        mp.ExitReason.TIME_STOP,
    }
    assert mp.ExitReason.UNJUSTIFIED_DISCRETION not in mp.JUSTIFIED_DISCRETION


# --- mandatory 30s post-fill re-bracket ------------------------------------

def test_rebracket_is_outstanding_on_a_fresh_fill():
    assert mp.needs_initial_rebracket(position(), now=1001.0)


def test_rebracket_rewrites_both_stop_and_target():
    """Operator requirement: within 30s of fill, BOTH legs move to structure."""
    pos = position()  # sell, entry 4340, SL 4343, TP 4335
    rb = mp.initial_rebracket(
        pos, price=4339.0, structural_stop=4344.279, structural_target=4330.0,
        now=1010.0, stop_level_id="H1_PREVIOUS_HIGH", target_level_id="M30_PREVIOUS_LOW",
    )
    assert rb.applied
    assert rb.stop and rb.target
    assert rb.stop.new_value == pytest.approx(4344.279)
    assert rb.target.new_value == pytest.approx(4330.0)


def test_rebracket_moves_stop_out_to_structure_despite_full_discretion_rules():
    """The correction is exempt from tighten/widen policy -- that is the point.

    Trade #6 of 2026-08-10 sat 3.708 INSIDE its structural stop and was
    noise-stopped in 81s for -153.50.
    """
    pos = position(stop_loss=4340.571)
    rb = mp.initial_rebracket(pos, price=4338.0, structural_stop=4344.279,
                              structural_target=4331.171, now=1005.0,
                              stop_level_id="H1_PREVIOUS_HIGH")
    assert rb.applied
    assert rb.stop.direction == "widen"
    assert rb.stop.new_value > pos.stop_loss


def test_rebracket_is_clipped_by_the_risk_ceiling():
    """Solvency rail still binds even the mandatory correction."""
    pos = position()
    rb = mp.initial_rebracket(pos, price=4339.0, structural_stop=4500.0,
                              structural_target=4330.0, now=1005.0,
                              stop_level_id="D1_PREVIOUS_HIGH")
    assert rb.applied and rb.clipped
    assert rb.reason_code == mp.AdjustReason.REBRACKET_CLIPPED
    ceiling = pos.initial_risk * mp.MAX_RISK_MULTIPLE
    assert pos.risk_at(rb.stop.new_value) <= ceiling + 1e-6


def test_rebracket_runs_only_once():
    pos = position()
    rb = mp.initial_rebracket(pos, price=4339.0, structural_stop=4344.0,
                              structural_target=4330.0, now=1005.0)
    updated = mp.apply_rebracket(pos, rb, now=1005.0)
    assert updated.rebracketed_at == 1005.0
    assert not mp.needs_initial_rebracket(updated, now=1006.0)
    again = mp.initial_rebracket(updated, price=4339.0, structural_stop=4346.0,
                                 structural_target=4329.0, now=1006.0)
    assert not again.applied


def test_rebracket_updates_the_reference_risk():
    """Later tighten/widen decisions measure against the corrected bracket."""
    pos = position()
    rb = mp.initial_rebracket(pos, price=4339.0, structural_stop=4344.279,
                              structural_target=4330.0, now=1005.0)
    updated = mp.apply_rebracket(pos, rb, now=1005.0)
    assert updated.initial_stop_distance == pytest.approx(4.279, abs=1e-3)


def test_rebracket_overdue_is_detectable():
    pos = position()
    assert not mp.rebracket_overdue(pos, now=1000.0 + 10)
    assert mp.rebracket_overdue(pos, now=1000.0 + mp.INITIAL_REBRACKET_SECONDS + 1)


def test_rebracket_without_structure_reports_a_code():
    pos = position()
    rb = mp.initial_rebracket(pos, price=4339.0, structural_stop=None,
                              structural_target=None, now=1005.0)
    assert not rb.applied
    assert rb.reason_code == mp.AdjustReason.REBRACKET_MISSING_STRUCTURE


def test_rebracket_flag_survives_later_adjustments():
    pos = position()
    rb = mp.initial_rebracket(pos, price=4339.0, structural_stop=4344.0,
                              structural_target=4330.0, now=1005.0)
    updated = mp.apply_rebracket(pos, rb, now=1005.0)
    adj = mp.propose_stop(updated, 4342.0, price=4338.0)
    assert mp.apply(updated, adj).rebracketed_at == 1005.0


def test_adjustment_audit_line_is_greppable():
    pos = position()
    adj = mp.propose_stop(pos, 4341.0, price=4338.0)
    assert mp.format_adjustment(adj).startswith("MANAGE ACCEPT")


# ===========================================================================
# Stage 5 -- contract gates
# ===========================================================================

def samples(n, *, confidence, ready, side="sell", model_ready=None, latency=16.0):
    return [
        cg.Sample(
            confidence=confidence,
            status="ready" if ready else "wait",
            side=side if ready else None,
            trade_permitted=True,
            latency_seconds=latency,
            model_said_ready=(ready if model_ready is None else model_ready),
        )
        for _ in range(n)
    ]


def test_v19_regression_fails_the_gate():
    """The exact edit that shipped unchecked on 2026-08-10."""
    baseline = samples(60, confidence=70, ready=True)
    candidate = samples(60, confidence=0, ready=False, model_ready=True)
    report = cg.evaluate(candidate, candidate_version="1.9",
                         baseline=baseline, baseline_version="1.8")
    assert not report.passed
    failed = {r.name for r in report.failures}
    assert cg.GateName.READY_RATE in failed
    assert cg.GateName.ZERO_CONFIDENCE in failed
    assert cg.GateName.CONTRADICTION in failed


def test_healthy_contract_passes():
    baseline = samples(60, confidence=70, ready=True)
    candidate = (samples(30, confidence=72, ready=True, side="buy")
                 + samples(30, confidence=68, ready=True, side="sell"))
    report = cg.evaluate(candidate, candidate_version="1.11",
                         baseline=baseline, baseline_version="1.8")
    assert report.passed, cg.format_report(report)


def test_one_sided_contract_fails_side_balance():
    """44 sell / 1 buy would not have been promotable."""
    candidate = samples(60, confidence=70, ready=True, side="sell")
    report = cg.evaluate(candidate, candidate_version="x", require_sample=False)
    assert cg.GateName.SIDE_BALANCE in {r.name for r in report.failures}


def test_small_sample_fails_until_enough_data():
    report = cg.evaluate(samples(5, confidence=70, ready=True),
                         candidate_version="x")
    assert cg.GateName.SAMPLE in {r.name for r in report.failures}


def test_latency_regression_is_caught():
    baseline = samples(60, confidence=70, ready=True, latency=16.0)
    candidate = samples(60, confidence=70, ready=True, side="buy", latency=40.0)
    report = cg.evaluate(candidate, candidate_version="x", baseline=baseline,
                         baseline_version="b")
    assert cg.GateName.LATENCY in {r.name for r in report.failures}


def test_live_rollback_trigger_on_zero_confidence_run():
    should, why = cg.should_rollback(samples(20, confidence=0, ready=False))
    assert should and "zero confidence" in why


def test_live_rollback_quiet_when_healthy():
    should, _ = cg.should_rollback(samples(20, confidence=70, ready=True))
    assert not should


# ===========================================================================
# Stage 6 -- configuration ledger
# ===========================================================================

def trade(frame="M30", side="sell", pnl=10.0, session="london",
          trigger="M30", geometry="structural_same_frame"):
    return cl.TradeRecord(frame=frame, side=side, session=session,
                          trigger_tf=trigger, geometry_source=geometry, pnl=pnl)


def test_new_configuration_starts_under_observation():
    ledger = cl.ConfigurationLedger()
    stats = ledger.record(trade())
    assert stats.state == cl.State.OBSERVATION


def test_observation_may_still_trade():
    ledger = cl.ConfigurationLedger()
    allowed, _ = ledger.may_trade(trade())
    assert allowed


def test_profitable_configuration_is_promoted():
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.MIN_SAMPLE_TO_PROMOTE):
        stats = ledger.record(trade(pnl=60.0))
    assert stats.state == cl.State.PERMITTED


def test_losing_configuration_is_demoted_and_blocked():
    """H1/H4 anchors lost -433 all day with nothing able to stop them."""
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.MIN_SAMPLE_TO_DEMOTE):
        stats = ledger.record(trade(frame="H4", pnl=-40.0))
    assert stats.state == cl.State.DEMOTED
    allowed, why = ledger.may_trade(trade(frame="H4"))
    assert not allowed and "demoted" in why


def test_severely_losing_configuration_demoted_early():
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.SEVERE_MIN_SAMPLE):
        stats = ledger.record(trade(frame="H4", pnl=-153.5))
    assert stats.state == cl.State.DEMOTED
    assert stats.sample < cl.MIN_SAMPLE_TO_DEMOTE


def test_demoted_configuration_rehabilitates():
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.SEVERE_MIN_SAMPLE):
        ledger.record(trade(frame="H4", pnl=-153.5))
    for _ in range(cl.REHABILITATION_AFTER):
        stats = ledger.record(trade(frame="H4", pnl=5.0))
    assert stats.state == cl.State.OBSERVATION


def test_configurations_are_kept_separate():
    ledger = cl.ConfigurationLedger()
    ledger.record(trade(frame="M30", pnl=100.0))
    ledger.record(trade(frame="H4", pnl=-100.0))
    assert len(ledger.configurations()) == 2


def test_state_transitions_are_logged_with_evidence():
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.SEVERE_MIN_SAMPLE):
        stats = ledger.record(trade(frame="H4", pnl=-153.5))
    assert stats.history
    assert stats.history[-1]["to"] == cl.State.DEMOTED
    assert "expectancy" in stats.history[-1]


def test_ledger_round_trips_through_json(tmp_path):
    ledger = cl.ConfigurationLedger()
    for _ in range(cl.MIN_SAMPLE_TO_PROMOTE):
        ledger.record(trade(pnl=60.0))
    path = tmp_path / "ledger.json"
    ledger.save(path)
    restored = cl.ConfigurationLedger.load(path)
    assert restored.summary()["total_trades"] == ledger.summary()["total_trades"]
    assert restored.state_of(trade()) == cl.State.PERMITTED


def test_loading_a_missing_ledger_is_empty_not_an_error():
    assert cl.ConfigurationLedger.load("/nonexistent/ledger.json").summary()["configurations"] == 0


def test_ranking_puts_best_expectancy_first():
    ledger = cl.ConfigurationLedger()
    ledger.record(trade(frame="H4", pnl=-100.0))
    ledger.record(trade(frame="M30", pnl=100.0))
    assert ledger.ranked()[0].key.startswith("M30")
