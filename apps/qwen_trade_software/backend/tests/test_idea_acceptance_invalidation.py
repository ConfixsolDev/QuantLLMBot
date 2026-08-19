from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from idea_lifecycle import IdeaManager  # noqa: E402


def _idea(side: str) -> IdeaManager:
    manager = IdeaManager()
    manager.create_idea("ZONE", side, 100.0, 102.0, "test")
    return manager


def test_closed_acceptance_above_invalidates_sell():
    manager = _idea("sell")
    resolved = manager.invalidate_on_closed_acceptance(102.01, "m1-close")
    assert resolved is not None
    assert resolved.outcome == "invalidated"
    assert not manager.has_active
    assert manager.prior_idea_context()["broken_level_becomes_sr"] is True


def test_closed_acceptance_below_invalidates_buy():
    manager = _idea("buy")
    assert manager.invalidate_on_closed_acceptance(99.99) is not None
    assert not manager.has_active


def test_close_inside_or_on_boundary_keeps_idea():
    sell = _idea("sell")
    buy = _idea("buy")
    assert sell.invalidate_on_closed_acceptance(102.0) is None
    assert buy.invalidate_on_closed_acceptance(100.0) is None
    assert sell.has_active and buy.has_active


def test_buy_zone_is_recovered_after_market_moves_far_above_it():
    manager = _idea("buy")
    idea = manager.active_idea
    resolved = manager.recover_stale(
        108.0,
        current_level_ids={"ZONE"},
        now=idea.created_at + 30,
    )
    assert resolved is not None
    assert resolved.outcome == "missed"
    assert "zone_traversed_without_fill" in resolved.resolution_reason
    assert not manager.has_active


def test_sell_zone_is_recovered_after_market_moves_far_below_it():
    manager = _idea("sell")
    idea = manager.active_idea
    assert manager.recover_stale(
        94.0, current_level_ids={"ZONE"}, now=idea.created_at + 30,
    ) is not None
    assert not manager.has_active


def test_current_nearby_zone_is_not_recovered():
    manager = _idea("buy")
    idea = manager.active_idea
    assert manager.recover_stale(
        104.0, current_level_ids={"ZONE"}, now=idea.created_at + 30,
    ) is None
    assert manager.has_active


def test_removed_level_and_old_idea_are_recovered():
    manager = _idea("buy")
    idea = manager.active_idea
    resolved = manager.recover_stale(
        101.0, current_level_ids={"NEW_ZONE"}, now=idea.created_at + 121,
    )
    assert resolved is not None
    assert "level_no_longer_current" in resolved.resolution_reason
