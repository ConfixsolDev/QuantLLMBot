"""The batch that makes results attributable.

2026-08-11. Three defects, one cause: a record did not say what produced it.

  * proposal_id was null on all 3,703 entry decisions, so no trade could be
    joined to the prompt that produced it and live trading had never once fed
    model training;
  * nothing recorded which build produced a trade, so four days of different
    behaviour were pooled into one dataset and every conclusion drawn from it
    was really a date effect;
  * per-tick heartbeat rows were 96.7% of the execution log, burying the 3.3%
    that recorded a decision.

These tests exist because all three were invisible. Nothing crashed. The data
looked fine and meant nothing.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import build_manifest  # noqa: E402
import paper_executor as _pe  # noqa: E402

# Captured at import, before the conftest fixture stubs append_event out to
# keep tests from writing into the live execution log. This test needs the real
# routing logic, so it keeps its own reference to it.
REAL_APPEND_EVENT = _pe.append_event


# --- build identity ---------------------------------------------------------

def test_stamp_is_small_and_carries_the_build():
    """Two fields. The full manifest must not ride on 30,000 rows."""
    stamp = build_manifest.stamp()
    assert set(stamp) == {"build_id", "build_dirty"}
    assert isinstance(stamp["build_id"], str) and len(stamp["build_id"]) == 12


def test_build_id_moves_when_a_tunable_moves(monkeypatch):
    """A threshold change IS a behaviour change and must produce a new build.

    Without this, someone flips QWEN_MIN_REWARD_RISK, results shift, and the
    two regimes get averaged together under one id -- exactly the failure this
    module exists to prevent.
    """
    before = build_manifest.compute()["build_id"]
    monkeypatch.setenv("QWEN_MIN_REWARD_RISK", "1.75")
    after = build_manifest.compute()["build_id"]
    assert before != after


def test_build_id_is_stable_when_nothing_changes():
    assert build_manifest.compute()["build_id"] == build_manifest.compute()["build_id"]


def test_unresolved_imports_do_not_masquerade_as_a_model_change():
    """A resolution failure and a real model change must not look identical."""
    manifest = build_manifest.compute()
    assert manifest["model"] is not None
    assert manifest["contract_hash"] is not None


def test_drift_reports_each_changed_field():
    frozen = dict(build_manifest.MANIFEST)
    frozen["tunables"] = dict(frozen["tunables"])
    frozen["tunables"]["entry_policy.MIN_ENTRY_CONFIDENCE"] = 99
    frozen["files"] = dict(frozen["files"])
    frozen["files"]["trade_geometry.py"] = "deadbeefdead"

    drift = build_manifest.drift_fields(frozen)
    assert any("MIN_ENTRY_CONFIDENCE" in d for d in drift)
    assert any("trade_geometry.py" in d for d in drift)


def test_no_declared_freeze_is_not_drift():
    """An undeclared freeze must not alarm on every startup."""
    assert build_manifest.drift_fields({}) == []
    assert build_manifest.drift_fields(None) in ([], build_manifest.drift_fields())


# --- the prompt -> outcome chain -------------------------------------------

def test_proposal_id_is_minted_before_the_decision_is_written():
    """The whole defect in one assertion.

    append_qwen_decision(decision_type="entry") must be able to see the id, so
    new_proposal_id() has to be called first. Reversing these two lines is what
    severed live trading from model training for months, silently.
    """
    source = (BACKEND / "reviewer.py").read_text(encoding="utf-8")
    mint = source.index("proposal_id = new_proposal_id()")
    decision = source.index('decision_type="entry"')
    proposal = source.index("proposal = append_paper_proposal(")
    assert mint < decision < proposal, (
        "order must be: mint id -> write decision -> write proposal"
    )


def test_the_decision_write_actually_passes_the_id():
    """Minting it is useless if it is not threaded through."""
    tree = ast.parse((BACKEND / "reviewer.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "append_qwen_decision":
            continue
        kwargs = {kw.arg for kw in node.keywords}
        if "entry" in ast.dump(node):
            assert "proposal_id" in kwargs, (
                "the entry decision record must carry proposal_id or nothing "
                "downstream can be joined to its prompt"
            )


def test_proposal_id_format_is_joinable():
    import reviewer
    pid = reviewer.new_proposal_id()
    assert pid.startswith("paper-") and len(pid.split("-")) == 3


def test_ids_are_unique():
    import reviewer
    assert len({reviewer.new_proposal_id() for _ in range(200)}) == 200


# --- heartbeat routing ------------------------------------------------------

def test_monitor_rows_go_to_the_path_log_and_decisions_do_not(monkeypatch):
    """96.7% of rows were heartbeats. They must not sit in the decision log."""
    routed = []
    monkeypatch.setattr(_pe, "append_tick_record", lambda base, event: routed.append(base))

    REAL_APPEND_EVENT({"event": "mt5_execution_monitor", "mark": 4330.0})
    REAL_APPEND_EVENT({"event": "mt5_execution_closed", "net_pnl": 10.0})
    REAL_APPEND_EVENT({"event": "mt5_fill"})
    REAL_APPEND_EVENT({"event": "geometry_observation"})

    assert routed == ["paper-path", "paper-executions",
                      "paper-executions", "paper-executions"]


def test_the_path_tail_reads_the_path_log():
    """Its only consumer must follow the rows to their new file."""
    source = (BACKEND / "trade_management.py").read_text(encoding="utf-8")
    start = source.index("def refresh_execution_monitor_cache")
    body = source[start:start + 1200]
    assert '_dated_log_path("paper-path")' in body, (
        "the monitor tail must read paper-path, or trade management loses the "
        "MFE/MAE path it depends on"
    )


# --- the dead flag ----------------------------------------------------------

def test_the_unread_policy_flag_is_gone():
    """A switch that promises a behaviour change and delivers none."""
    source = (BACKEND / "reviewer.py").read_text(encoding="utf-8")
    assert "QWEN_POLICY_V2 = " not in source


# --- log families must be fully registered ---------------------------------

def test_every_log_family_the_executor_writes_is_archive_registered():
    """2026-08-11 LIVE INCIDENT — this is the test that was missing.

    paper-path was added as a new log family but never registered in
    ARCHIVE_FILES. append_tick_record writes the runtime log first and the
    archive second, so every monitor tick wrote its line and then raised
    KeyError out of append_event, straight through the executor's monitor loop.

    Five positions were opened and left with no close record. The runner then
    blocked every new proposal on a position it thought was still open. A
    missing dictionary entry took the trading system down for 40 minutes.
    """
    import tick_data_archive as tda

    for base in (_pe.PATH_LOG, _pe.EXECUTION_LOG):
        assert base in tda.ARCHIVE_FILES, (
            f"{base!r} is written by paper_executor but has no ARCHIVE_FILES "
            "entry. archive_log_path() will raise and kill the run."
        )
        tda.archive_log_path(base)  # must not raise


def test_an_archive_failure_cannot_kill_a_trade(tmp_path, monkeypatch):
    """Recording a trade is not more important than managing one."""
    import tick_data_archive as tda

    monkeypatch.setattr(tda, "LOG_DIR", tmp_path)
    monkeypatch.setattr(tda, "runtime_log_path",
                        lambda base, day=None: tmp_path / f"{base}.jsonl")

    def boom(*a, **k):
        raise KeyError("Unknown tick archive base: whatever")

    monkeypatch.setattr(tda, "archive_log_path", boom)

    tda.append_tick_record("whatever", {"event": "mt5_execution_monitor"})

    written = (tmp_path / "whatever.jsonl").read_text(encoding="utf-8")
    assert "mt5_execution_monitor" in written, (
        "the runtime log must still receive the record"
    )


def test_append_event_never_raises_no_matter_what(monkeypatch):
    """The monitor loop watches a LIVE position. Bookkeeping cannot kill it.

    2026-08-11: append_event raised KeyError once per second from inside that
    loop and five positions were abandoned mid-trade. A failed write costs one
    row; a raised exception costs an unmanaged position.
    """
    def explode(*a, **k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(_pe, "append_tick_record", explode)

    # Must not raise, for either destination.
    REAL_APPEND_EVENT({"event": "mt5_execution_monitor", "execution_id": "x"})
    REAL_APPEND_EVENT({"event": "mt5_execution_closed", "execution_id": "x"})


def test_reconstructed_rows_are_kept_out_of_training():
    """Broker-rebuilt rows have real P&L but no observed path or thesis."""
    source = (BACKEND / "tools" / "export_training_pairs.py").read_text(encoding="utf-8")
    assert 'close.get("reconstructed_from_broker")' in source, (
        "a row with no trade path must not become a training example"
    )


# --- broker truth beats cached belief ---------------------------------------

def _tm(monkeypatch):
    import trade_management as tm
    tm.LAST_MANAGED_M1_BY_TICKET.clear()
    tm.ENTRY_CONTEXT_BY_TICKET.clear()
    tm._REBRACKETED_TICKETS.clear()
    tm.EXECUTION_MONITOR_BY_ID.clear()
    return tm


def test_closed_positions_are_dropped_from_every_cache(monkeypatch):
    """MT5 is the truth; anything this process believes is a derived cache."""
    tm = _tm(monkeypatch)
    for ticket in (111, 222, 333):
        tm.LAST_MANAGED_M1_BY_TICKET[ticket] = "candle:M1:x"
        tm.ENTRY_CONTEXT_BY_TICKET[ticket] = {"proposal_id": f"p-{ticket}"}
        tm._REBRACKETED_TICKETS.add(ticket)
    tm.EXECUTION_MONITOR_BY_ID["demo-1"] = {"peak_pnl": 10.0}

    tm.reconcile_position_state({222})

    assert set(tm.LAST_MANAGED_M1_BY_TICKET) == {222}
    assert set(tm.ENTRY_CONTEXT_BY_TICKET) == {222}
    assert tm._REBRACKETED_TICKETS == {222}
    # One position is still open, so the execution-monitor cache is left alone:
    # it is keyed by execution id and cannot be matched to a ticket here.
    assert tm.EXECUTION_MONITOR_BY_ID


def test_no_open_positions_clears_everything(monkeypatch):
    """The case the user asked for: nothing open means nothing believed."""
    tm = _tm(monkeypatch)
    tm.LAST_MANAGED_M1_BY_TICKET[111] = "candle:M1:x"
    tm.ENTRY_CONTEXT_BY_TICKET[111] = {"proposal_id": "p-111"}
    tm._REBRACKETED_TICKETS.add(111)
    tm.EXECUTION_MONITOR_BY_ID["demo-1"] = {"peak_pnl": 10.0}

    tm.reconcile_position_state(set())

    assert not tm.LAST_MANAGED_M1_BY_TICKET
    assert not tm.ENTRY_CONTEXT_BY_TICKET
    assert not tm._REBRACKETED_TICKETS
    assert not tm.EXECUTION_MONITOR_BY_ID


def test_a_reused_ticket_is_not_treated_as_already_rebracketed(monkeypatch):
    """The one that can cost money.

    MT5 reuses ticket numbers. A stale _REBRACKETED_TICKETS entry would make a
    NEW position look already corrected, silently skipping the re-bracket that
    moves its stop beyond structure -- the adjustment worth, by earlier
    measurement, the difference between winners and losers.
    """
    tm = _tm(monkeypatch)
    tm._REBRACKETED_TICKETS.add(4242)

    tm.reconcile_position_state(set())          # old position closes
    tm.reconcile_position_state({4242})         # ticket reused by a new one

    assert 4242 not in tm._REBRACKETED_TICKETS, (
        "a reused ticket must be eligible for its own re-bracket"
    )


def test_reconcile_is_called_before_any_decision(monkeypatch):
    """Reconciling after acting on stale state would be pointless."""
    source = (BACKEND / "trade_management.py").read_text(encoding="utf-8")
    start = source.index("def review_positions")
    body = source[start:]
    assert body.index("reconcile_position_state(") < body.index('if not positions:')


def test_every_live_path_module_is_in_the_manifest():
    """A module a change can break is a module the build must track.

    2026-08-11: tick_data_archive.py was omitted on the reasoning that it only
    moves data around. A one-line dictionary omission in it then killed the
    executor on every monitor tick and cost seven trades their close records --
    with build_id unchanged, so the broken system and the fixed one were
    reported as the same build.
    """
    import build_manifest as bm

    must_track = {
        "paper_executor.py", "paper_runner.py", "reviewer.py",
        "trade_management.py", "trade_manager.py", "entry_policy.py",
        "trade_geometry.py", "management_policy.py", "session_planner.py",
        "tick_data_archive.py", "process_logging.py",
        "market_context_cache.py", "review_shared.py",
    }
    missing = must_track - set(bm.DECISION_MODULES)
    assert not missing, f"live-path modules absent from the build manifest: {sorted(missing)}"


def test_manifest_modules_all_exist():
    """A typo would hash as 'missing' forever and never move the build id."""
    import build_manifest as bm

    absent = [m for m in bm.DECISION_MODULES if not (bm.APP_DIR / m).exists()]
    assert not absent, f"manifest names files that do not exist: {absent}"


# --- cooldown after every completed trade -----------------------------------

def test_a_winning_trade_now_cools_down_too():
    """2026-08-11: only losses paused the runner.

    Trades opening within 30 min of a WINNING close ran n=23, net -353.40,
    avg -15.37 at a 52% win rate -- a positive hit rate with negative
    expectancy, i.e. the winners were smaller than the losers. Re-entering
    immediately after taking profit means entering at a level that has just
    been reached and reacted to.
    """
    import paper_runner as pr

    seconds, label = pr.cooldown_for({"net_pnl": 118.0})
    assert seconds == pr.WIN_COOLDOWN_SECONDS and label == "Win"


def test_a_losing_trade_still_cools_down():
    import paper_runner as pr

    seconds, label = pr.cooldown_for({"net_pnl": -52.25})
    assert seconds == pr.LOSS_COOLDOWN_SECONDS and label == "Loss"
    assert pr.LOSS_COOLDOWN_SECONDS == 1800


def test_loss_cooldown_bypass_requires_high_confidence_and_rr():
    """2026-08-13: 30m loss pause, interruptible only by 82%+ and R:R >= 2.5."""
    import paper_runner as pr

    strong = {
        "qwen": {
            "confidence": 85,
            "execution_plan": {
                "side": "sell",
                "entry_low": 4400.0,
                "entry_high": 4402.0,
                "structural_stop_loss": 4405.0,
                "structural_take_profit": 4385.0,
            },
        }
    }
    ok, detail = pr.loss_cooldown_bypass_ok(strong)
    assert ok, detail
    assert detail["reward_risk"] >= pr.LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK

    weak_conf = {
        "qwen": {
            "confidence": 70,
            "execution_plan": strong["qwen"]["execution_plan"],
        }
    }
    ok, detail = pr.loss_cooldown_bypass_ok(weak_conf)
    assert not ok
    assert detail["confidence"] == 70.0

    weak_rr = {
        "qwen": {
            "confidence": 90,
            "execution_plan": {
                "side": "sell",
                "entry_low": 4400.0,
                "entry_high": 4402.0,
                # Fixed-style ~$3 risk / ~$5 reward -- not "very high".
                "stop_loss": 4404.0,
                "take_profit": 4396.0,
            },
        }
    }
    ok, detail = pr.loss_cooldown_bypass_ok(weak_rr)
    assert not ok
    assert detail["reward_risk"] is not None
    assert detail["reward_risk"] < pr.LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK


def test_a_trade_that_never_happened_does_not_cool_down():
    """signal_expired held no position. Pausing on it throttles for nothing."""
    import paper_runner as pr

    assert pr.cooldown_for({"reason": "signal_expired", "net_pnl": None}) == (0, "")
    assert pr.cooldown_for({}) == (0, "")


def test_an_unsettled_pnl_does_not_drive_the_cooldown():
    """net_pnl is the entry commission when the closing deal never settled, so
    its sign carries no information about whether the trade won or lost."""
    import paper_runner as pr

    assert pr.cooldown_for({"net_pnl": -3.5, "pnl_is_complete": False}) == (0, "")


def test_both_cooldowns_are_in_the_build_manifest():
    """A cooldown change is a behaviour change; it must move the build_id, or
    two regimes get averaged into one sample."""
    import build_manifest as bm

    assert "paper_runner.WIN_COOLDOWN_SECONDS" in bm.MANIFEST["tunables"]
    assert "paper_runner.LOSS_COOLDOWN_SECONDS" in bm.MANIFEST["tunables"]
    assert "paper_runner.LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE" in bm.MANIFEST["tunables"]
    assert "paper_runner.LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK" in bm.MANIFEST["tunables"]
    assert bm.MANIFEST["tunables"]["paper_runner.LOSS_COOLDOWN_SECONDS"] == 1800
    assert bm.MANIFEST["tunables"]["paper_runner.LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE"] == 82
    assert bm.MANIFEST["tunables"]["paper_runner.LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK"] == 2.5


def test_the_manifest_captures_every_named_tunable():
    """A tunable that quietly stops being captured stops moving the build id.

    2026-08-11: the import-based reader hit a circular import (five of these
    modules import build_manifest) and silently captured 0 of paper_runner's
    constants. Changing LOSS_COOLDOWN_SECONDS would not have changed build_id.
    """
    import build_manifest as bm

    broken = [k for k in bm.MANIFEST["tunables"]
              if "<missing>" in k or "<unreadable>" in k]
    assert not broken, (
        f"manifest could not read these tunables: "
        f"{ {k: bm.MANIFEST['tunables'][k] for k in broken} }"
    )


def test_manifest_reads_annotated_assignments_too():
    """SCORE_WEIGHTS is declared `X: dict[str, float] = {...}` -- a different
    AST node from a plain assignment, and originally missed."""
    import build_manifest as bm

    weights = bm.MANIFEST["tunables"].get("entry_policy.SCORE_WEIGHTS")
    assert isinstance(weights, dict) and weights, "annotated assignment not captured"


def test_manifest_does_not_import_the_modules_it_inspects():
    """Importing them from module scope is what caused the circular failure.

    Checked against the AST rather than the text, because the docstring in
    _tunables explains the old __import__ approach and a substring search
    matches its own history lesson.
    """
    tree = ast.parse((BACKEND / "build_manifest.py").read_text(encoding="utf-8"))
    tunables = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_tunables"
    )
    for node in ast.walk(tunables):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise AssertionError("_tunables must not import the modules it reads")
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "__import__":
            raise AssertionError("_tunables must parse source, not __import__")
