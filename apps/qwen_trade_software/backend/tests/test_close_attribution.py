"""A close must be attributed to whoever made it, with P&L that is real.

2026-08-11 -- the incident these tests lock down
-----------------------------------------------
Seven closed trades were recorded as `external_position_close`, gross_pnl
exactly 0.00, costs exactly -3.50, close_comments empty. Two separate faults
produced that row:

  1. A position leaves positions_get the moment the broker accepts the close,
     but its closing DEAL reaches history a moment later. The executor read the
     gap, found only the ENTRY deal, and reported its commission as the final
     P&L. The trades' real results were never recorded -- and a false 0.00 is
     worse than a gap, because it silently pulls every average toward nothing.

  2. The trade manager HAD closed those positions and logged a close decision
     for each. The broker did not preserve our order comment, and attribution
     was comment-only, so the manager's own work was filed as somebody else's.

Both faults were silent. Nothing raised, no test failed, and the label
"external" actively misdirected the investigation.
"""

from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


DEAL_ENTRY_IN = 0
DEAL_ENTRY_OUT = 1


def _deal(position_id, entry, profit=0.0, commission=0.0, comment="", volume=0.5,
          price=4330.0):
    return types.SimpleNamespace(
        position_id=position_id, entry=entry, profit=profit,
        commission=commission, swap=0.0, fee=0.0, comment=comment,
        volume=volume, price=price,
    )


@pytest.fixture
def executor(monkeypatch):
    import paper_executor as pe

    fake = types.SimpleNamespace(
        DEAL_ENTRY_IN=DEAL_ENTRY_IN,
        history_deals_get=lambda *a, **k: (),
    )
    monkeypatch.setattr(pe, "mt5", fake)
    monkeypatch.setattr(pe, "EXIT_SETTLE_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(pe, "EXIT_SETTLE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pe, "manager_closed_position", lambda ids: None)
    return pe, fake


FILLS = [{"order": 555, "deal": 1, "price": 4330.0, "volume": 0.5}]
SINCE = datetime(2026, 8, 11, tzinfo=timezone.utc)


def test_waits_for_the_exit_deal_instead_of_reading_the_gap(executor):
    """The exact race: entry deal visible first, exit deal lands a beat later."""
    pe, fake = executor
    calls = {"n": 0}

    def history(*_a, **_k):
        calls["n"] += 1
        entry = _deal(555, DEAL_ENTRY_IN, profit=0.0, commission=-3.5)
        if calls["n"] < 3:
            return (entry,)  # the gap: close accepted, deal not yet in history
        return (entry, _deal(555, DEAL_ENTRY_OUT, profit=117.65, comment="[tp 4435]"))

    fake.history_deals_get = history

    outcome = pe.realized_execution_outcome(FILLS, SINCE)

    assert outcome["gross_pnl"] == pytest.approx(117.65), (
        "must report the real result, not the entry commission alone"
    )
    assert outcome["net_pnl"] == pytest.approx(114.15)
    assert outcome["reason"] == "managed_or_safety_tp"
    assert outcome["pnl_is_complete"] is True


def test_a_missing_exit_deal_is_reported_as_unsettled_not_as_zero(executor):
    """A trade with unknown P&L must be visible as unknown."""
    pe, fake = executor
    fake.history_deals_get = lambda *a, **k: (
        _deal(555, DEAL_ENTRY_IN, profit=0.0, commission=-3.5),
    )

    outcome = pe.realized_execution_outcome(FILLS, SINCE)

    assert outcome["reason"] == "exit_deals_unsettled", (
        "this is the row that used to read 'external_position_close' at -3.50"
    )
    assert outcome["pnl_is_complete"] is False, (
        "downstream averages and training must be able to skip this row"
    )
    assert outcome["exit_deal_count"] == 0


def test_manager_close_is_attributed_to_the_manager_without_a_comment(executor):
    """The broker stripping our comment must not reassign the manager's work."""
    pe, fake = executor
    fake.history_deals_get = lambda *a, **k: (
        _deal(555, DEAL_ENTRY_IN, commission=-3.5),
        _deal(555, DEAL_ENTRY_OUT, profit=-12.0, comment=""),
    )
    pe_decision = {
        "decision_id": "d-1",
        "mt5_position_id": 555,
        "model": "qwen-trading-v004:latest",
        "parsed": {"action": "close", "confidence": 62, "reason": "idea invalidated"},
    }
    object.__setattr__(pe, "manager_closed_position", lambda ids: pe_decision)

    outcome = pe.realized_execution_outcome(FILLS, SINCE)

    assert outcome["reason"] == "qwen_confirmed_close"
    assert outcome["attribution_source"] == "manager_decision_log"
    assert outcome["manager_close_decision"]["reason"] == "idea invalidated"
    assert outcome["manager_close_decision"]["confidence"] == 62


def test_genuinely_external_close_is_still_called_external(executor):
    """The category must keep meaning something: nobody of ours claimed it."""
    pe, fake = executor
    fake.history_deals_get = lambda *a, **k: (
        _deal(555, DEAL_ENTRY_IN, commission=-3.5),
        _deal(555, DEAL_ENTRY_OUT, profit=-8.0, comment="manual close"),
    )

    outcome = pe.realized_execution_outcome(FILLS, SINCE)

    assert outcome["reason"] == "external_position_close"
    assert outcome["attribution_source"] == "broker_comment"
    assert outcome["manager_close_decision"] is None


def test_broker_comment_wins_over_the_decision_log(executor):
    """The comment is direct evidence of HOW it closed; prefer it when present."""
    pe, fake = executor
    fake.history_deals_get = lambda *a, **k: (
        _deal(555, DEAL_ENTRY_IN, commission=-3.5),
        _deal(555, DEAL_ENTRY_OUT, profit=-150.0, comment="[sl 4409.22]"),
    )
    object.__setattr__(
        pe, "manager_closed_position", lambda ids: {"parsed": {"action": "close"}}
    )

    outcome = pe.realized_execution_outcome(FILLS, SINCE)

    assert outcome["reason"] == "managed_or_safety_sl", (
        "the stop fired; a stale close decision must not relabel it"
    )


def test_manager_lookup_reads_the_decision_log(tmp_path, monkeypatch):
    """manager_closed_position must find a real close record by position id."""
    import paper_executor as pe

    log = tmp_path / "qwen-decisions-2026-08-11.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"mt5_position_id": 999, "parsed": {"action": "hold"}}),
                json.dumps(
                    {
                        "mt5_position_id": 555,
                        "decision_id": "d-7",
                        "parsed": {"action": "close", "reason": "target unreachable"},
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pe, "_dated_log_files", lambda base, days_back=1: [log])

    found = pe.manager_closed_position({555})
    assert found is not None and found["decision_id"] == "d-7"

    assert pe.manager_closed_position({12345}) is None
    assert pe.manager_closed_position({999}) is None, "a hold is not a close"
