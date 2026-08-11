"""Two-branch day-plan state machine.

Each test names the 2026-08-11 behaviour it corrects. That day the screen showed
H4/H1/M15 all INVALIDATED while the bullish idea reached both of its targets.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plan_branches as pb  # noqa: E402


def bull(trigger=4405.8, inval=4397.6, targets=(4405.8, 4409.2)):
    return pb.Branch(side="buy", trigger_price=trigger, invalidation=inval,
                     targets=tuple(targets), trigger_text="M30 close above H1_PREVIOUS_HIGH")


def bear(trigger=4396.2, inval=4405.8, targets=(4396.2, 4392.8)):
    return pb.Branch(side="sell", trigger_price=trigger, invalidation=inval,
                     targets=tuple(targets), trigger_text="M30 close below H1_PREVIOUS_LOW")


# --- the incident ----------------------------------------------------------

def test_wick_through_invalidation_does_not_kill_the_branch():
    """THE bug. Hour was O 4402.30 H 4419.45 L 4396.54 C 4409.55.

    The low wicked 1.06 through the 4397.60 invalidation. The close went the
    other way and price ran through both targets.
    """
    result = pb.evaluate_branch(bull(), closed_price=4409.55,
                                high=4419.45, low=4396.54)
    assert result.state != pb.INVALIDATED


def test_the_bullish_branch_reaches_spent_not_invalidated():
    result = pb.evaluate_branch(bull(), closed_price=4409.55,
                                high=4419.45, low=4396.54)
    assert result.state == pb.SPENT


def test_the_bearish_branch_is_the_one_that_dies():
    result = pb.evaluate_branch(bear(), closed_price=4409.55,
                                high=4419.45, low=4396.54)
    assert result.state == pb.INVALIDATED
    assert "4405.8" in result.reason


def test_forecast_miss_moves_confidence_never_state():
    """-30 for 'expected range compression, observed bullish hour' used to
    invalidate every layer. It must only move confidence."""
    branch = pb.evaluate_branch(bull(), closed_price=4402.0)
    before = branch.state
    adjusted = pb.apply_confidence_delta(branch, -30)
    assert adjusted.state == before
    assert adjusted.confidence == 20


# --- state transitions -----------------------------------------------------

def test_default_state_is_armed():
    assert bull().state == pb.ARMED


def test_close_through_invalidation_invalidates():
    result = pb.evaluate_branch(bull(), closed_price=4390.0)
    assert result.state == pb.INVALIDATED


def test_close_through_trigger_confirms():
    result = pb.evaluate_branch(bull(trigger=4406.0, targets=(4420.0,)),
                                closed_price=4407.0)
    assert result.state == pb.CONFIRMED


def test_explicit_trigger_confirmation_is_honoured():
    result = pb.evaluate_branch(bull(trigger=None, targets=(4420.0,)),
                                closed_price=4400.0, trigger_confirmed=True)
    assert result.state == pb.CONFIRMED


def test_approaching_the_trigger_is_likely():
    # trigger 4405.8, invalidation 4397.6 -> span 8.2, likely within 2.87
    result = pb.evaluate_branch(bull(targets=(4420.0,)), closed_price=4404.0)
    assert result.state == pb.LIKELY


def test_far_from_trigger_stays_armed():
    result = pb.evaluate_branch(bull(targets=(4420.0,)), closed_price=4399.0)
    assert result.state == pb.ARMED


def test_terminal_states_never_change():
    dead = pb.evaluate_branch(bull(), closed_price=4390.0)
    assert dead.state == pb.INVALIDATED
    assert pb.evaluate_branch(dead, closed_price=4500.0).state == pb.INVALIDATED


def test_confidence_delta_ignored_once_terminal():
    dead = pb.evaluate_branch(bull(), closed_price=4390.0)
    assert pb.apply_confidence_delta(dead, +40).confidence == dead.confidence


# --- the day view ----------------------------------------------------------

def test_day_view_answers_buy_or_sell():
    b = pb.evaluate_branch(bull(trigger=4406.0, targets=(4420.0,)), closed_price=4407.0)
    s = pb.evaluate_branch(bear(), closed_price=4407.0)
    view = pb.build_day_view(b, s)
    assert view.callable_side == "buy"
    assert "BUY confirmed" in view.headline


def test_day_view_has_no_status_of_its_own():
    """The plan is a container. Only branches carry state."""
    view = pb.build_day_view(bull(), bear())
    assert not hasattr(view, "status")
    assert view.callable_side is None


def test_both_branches_always_present():
    """One resolving must never remove the other from the screen."""
    dead = pb.evaluate_branch(bear(), closed_price=4409.55)
    view = pb.build_day_view(bull(), dead)
    assert view.bullish is not None and view.bearish is not None
    assert view.bearish.state == pb.INVALIDATED


def test_conflict_is_reported_not_hidden():
    b = pb.evaluate_branch(bull(trigger=4400.0, targets=(4420.0,)), closed_price=4401.0)
    s = pb.evaluate_branch(bear(trigger=4402.0, inval=4500.0, targets=(4380.0,)),
                           closed_price=4401.0)
    view = pb.build_day_view(b, s)
    if b.state == pb.CONFIRMED and s.state == pb.CONFIRMED:
        assert "conflict" in view.headline.lower()
        assert view.callable_side is None


def test_waiting_headline_explains_what_it_waits_for():
    view = pb.build_day_view(bull(), bear())
    assert "No entry yet" in view.headline


def test_summary_line_is_greppable():
    view = pb.build_day_view(bull(), bear())
    assert pb.summarise(view).startswith("DAYPLAN bull=")


def test_branch_from_scenario_parses_a_real_day_plan_block():
    branch = pb.branch_from_scenario(
        {"trigger": "M30 close above H1_PREVIOUS_HIGH with level rejection",
         "targets": [4405.8, 4409.2], "invalidation": 4397.6,
         "evidence": ["M30 closes above H1_PREVIOUS_HIGH"]},
        side="buy", trigger_price=4405.8,
    )
    assert branch.targets == (4405.8, 4409.2)
    assert branch.invalidation == 4397.6
    assert branch.state == pb.ARMED


def test_malformed_scenario_does_not_explode():
    branch = pb.branch_from_scenario(
        {"targets": ["nonsense", 4400.0], "invalidation": None}, side="sell")
    assert branch.targets == (4400.0,)
    assert branch.invalidation is None
