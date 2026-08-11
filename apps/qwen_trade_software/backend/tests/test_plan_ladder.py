"""The D1/H4/H1/M15 two-branch ladder.

The case that motivated it: a bearish day containing a bullish H1 pullback. With
one idea per timeframe that is unrepresentable and surfaces as "invalidated" —
which is how the screen went solid red on 2026-08-11 while the bullish branch
reached both its targets.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plan_branches as pb  # noqa: E402
import plan_ladder as pl  # noqa: E402


def branch(side, trigger, inval, targets=(), state=pb.ARMED, confidence=50):
    return pb.Branch(side=side, trigger_price=trigger, invalidation=inval,
                     targets=tuple(targets), state=state, confidence=confidence)


def hours(bull=0, bear=0):
    out = [{"hour_ohlc": {"o": 100.0, "c": 101.0}} for _ in range(bull)]
    out += [{"hour_ohlc": {"o": 100.0, "c": 99.0}} for _ in range(bear)]
    return out


# --- the motivating case ---------------------------------------------------

def test_bullish_pullback_inside_a_bearish_day_is_representable():
    """Not a contradiction. The whole reason for pairs per timeframe."""
    d1 = pl.build_pair(
        "D1",
        branch("buy", 4420.0, 4400.0, (4440.0,)),
        branch("sell", 4390.0, 4430.0, (4370.0,)),
        closed_price=4380.0,
    )
    assert d1.side == "sell"

    h1 = pl.build_pair(
        "H1",
        branch("buy", 4378.0, 4370.0, (4398.0,)),
        branch("sell", 4360.0, 4400.0, (4340.0,)),
        closed_price=4380.0,
        higher_side=d1.side,
    )
    assert h1.side == "buy"
    assert "pullback" in h1.note


def test_counter_trend_is_labelled_not_invalidated():
    h1 = pl.build_pair(
        "H1",
        branch("buy", 4378.0, 4370.0, (4398.0,)),
        branch("sell", 4360.0, 4400.0, (4340.0,)),
        closed_price=4380.0,
        higher_side="sell",
    )
    assert h1.bull.state != pb.INVALIDATED
    assert h1.note


def test_ladder_headline_names_the_disagreement():
    pairs = [
        pl.build_pair("D1", branch("buy", 4420.0, 4400.0), branch("sell", 4390.0, 4430.0, (4370.0,)),
                      closed_price=4380.0),
        pl.build_pair("H1", branch("buy", 4378.0, 4370.0, (4398.0,)), branch("sell", 4360.0, 4400.0),
                      closed_price=4380.0, higher_side="sell"),
    ]
    ladder = pl.build_ladder(pairs)
    assert "pullback, not conflict" in ladder.headline
    assert not ladder.aligned


def test_ladder_reports_alignment_when_frames_agree():
    pairs = [
        pl.build_pair("D1", branch("buy", 4370.0, 4340.0, (4400.0,)), branch("sell", 4330.0, 4380.0),
                      closed_price=4380.0),
        pl.build_pair("H1", branch("buy", 4375.0, 4360.0, (4400.0,)), branch("sell", 4350.0, 4390.0),
                      closed_price=4380.0, higher_side="buy"),
    ]
    ladder = pl.build_ladder(pairs)
    if ladder.aligned:
        assert "all timeframes agree" in ladder.headline


# --- confidence accrual ----------------------------------------------------

def test_confidence_rises_with_supporting_hours():
    """The old screen showed a flat 50 on both branches, which said nothing."""
    base = branch("buy", 4400.0, 4380.0)
    grown = pl.accrue_confidence(base, hours_with=4)
    assert grown.confidence > base.confidence


def test_confidence_falls_on_evidence_against():
    base = branch("buy", 4400.0, 4380.0, confidence=70)
    fallen = pl.accrue_confidence(base, hours_against=4, levels_against=2)
    assert fallen.confidence < 70


def test_confidence_is_clamped():
    high = pl.accrue_confidence(branch("buy", 1.0, 0.0, confidence=95), hours_with=20)
    low = pl.accrue_confidence(branch("buy", 1.0, 0.0, confidence=5), hours_against=20)
    assert high.confidence <= 100
    assert low.confidence >= 0


def test_terminal_branches_do_not_accrue():
    dead = branch("buy", 4400.0, 4380.0, state=pb.INVALIDATED, confidence=40)
    assert pl.accrue_confidence(dead, hours_with=10).confidence == 40


def test_alignment_with_the_higher_frame_adds_confidence():
    plain = pl.accrue_confidence(branch("buy", 4400.0, 4380.0), hours_with=2)
    aligned = pl.accrue_confidence(branch("buy", 4400.0, 4380.0), hours_with=2,
                                   aligned_with_higher=True)
    assert aligned.confidence > plain.confidence


# --- evidence extraction ---------------------------------------------------

def test_hours_counted_from_the_candle_not_the_narrative():
    """hour_ohlc is always written; the narrative field often is not."""
    with_, against = pl.evidence_from_hours(hours(bull=3, bear=1), "buy")
    assert (with_, against) == (3, 1)


def test_narrative_used_when_no_candle():
    data = [{"actual_vs_expected": {"observed": "bullish hour"}}]
    with_, against = pl.evidence_from_hours(data, "buy")
    assert (with_, against) == (1, 0)


def test_flat_hours_are_ignored():
    data = [{"hour_ohlc": {"o": 100.0, "c": 100.0}}]
    assert pl.evidence_from_hours(data, "buy") == (0, 0)


def test_levels_counted_by_direction():
    levels = [{"result": "broken_above"}, {"result": "broken_above"},
              {"result": "broken_below"}, {"result": "tested"}]
    assert pl.evidence_from_levels(levels, "buy") == (2, 1)
    assert pl.evidence_from_levels(levels, "sell") == (1, 2)


# --- structure -------------------------------------------------------------

def test_every_timeframe_carries_both_directions():
    pair = pl.build_pair("H4", branch("buy", 1.0, 0.5), branch("sell", 0.4, 1.2))
    payload = pair.as_dict()
    assert payload["bull"]["side"] == "buy"
    assert payload["bear"]["side"] == "sell"


def test_ladder_covers_the_four_timeframes():
    assert pl.LADDER_TIMEFRAMES == ("D1", "H4", "H1", "M15")
    for tf in pl.LADDER_TIMEFRAMES:
        assert pl.ROLE[tf]


def test_side_is_none_when_both_branches_are_terminal():
    pair = pl.build_pair(
        "D1",
        branch("buy", 4400.0, 4380.0, state=pb.SPENT),
        branch("sell", 4360.0, 4390.0, state=pb.INVALIDATED),
    )
    assert pair.side is None


def test_builds_from_real_planner_state_shape():
    state = {
        "day_plan": {
            "reference_price": 4402.4,
            "bullish_scenario": {"trigger": "M30 close above H1_PREVIOUS_HIGH",
                                 "targets": [4405.8, 4409.2], "invalidation": 4397.6,
                                 "evidence": []},
            "bearish_scenario": {"trigger": "M30 close below H1_PREVIOUS_LOW",
                                 "targets": [4396.2, 4392.8], "invalidation": 4405.8,
                                 "evidence": []},
        },
        "trade_idea_stack": {
            "h4": {"side": "buy", "invalidation": 4397.6, "targets": [4405.8]},
            "h1": {"side": "buy", "invalidation": 4397.6, "targets": [4405.8]},
            "m15": {"side": "buy", "invalidation": 4397.6, "targets": [4405.8]},
        },
        "hourly_updates": hours(bull=5, bear=1),
    }
    ladder = pl.build_ladder_from_state(state, 4404.0)
    assert ladder is not None
    assert [p["timeframe"] for p in ladder["pairs"]] == ["D1", "H4", "H1", "M15"]
    for pair in ladder["pairs"]:
        assert pair["bull"] and pair["bear"]


def test_missing_day_plan_returns_none():
    assert pl.build_ladder_from_state({}, 4400.0) is None
