"""Integration tests for the two wired paths.

These exercise the seams that unit tests cannot: that paper_executor actually
consults trade_geometry when placing the entry bracket, and that
trade_management actually rewrites SL/TP to structure within 30s of fill.

Both modules import MetaTrader5 at module scope, so a minimal fake is installed
before import. The fake is only rich enough to drive the code paths under test.
"""

from __future__ import annotations

import os
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)


# --- fake MetaTrader5 -------------------------------------------------------

class _FakeMT5(types.ModuleType):
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    TRADE_ACTION_SLTP = 6
    TRADE_RETCODE_DONE = 10009

    def __init__(self, name="MetaTrader5"):
        super().__init__(name)
        self.sent: list[dict] = []
        self._tick = types.SimpleNamespace(bid=4333.0, ask=4333.2, time_msc=0)

    def set_price(self, bid: float) -> None:
        """Mark price. Kept near the entry: these tests model a 30s-old fill,
        and a stop can only be placed where price has not already passed."""
        self._tick = types.SimpleNamespace(bid=bid, ask=bid + 0.2, time_msc=0)

    def order_send(self, request):
        self.sent.append(request)
        return types.SimpleNamespace(retcode=self.TRADE_RETCODE_DONE, comment="ok")

    def symbol_info_tick(self, symbol):
        return self._tick

    def positions_get(self, **kwargs):
        return ()

    def last_error(self):
        return (0, "none")

    def __getattr__(self, name):
        if name.isupper() or name.startswith("TIMEFRAME_"):
            return 0
        return lambda *a, **k: None


@pytest.fixture
def mt5_fake(monkeypatch):
    fake = _FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    msvcrt = types.ModuleType("msvcrt")
    msvcrt.locking = lambda *a, **k: None
    msvcrt.LK_NBLCK, msvcrt.LK_UNLCK = 1, 0
    monkeypatch.setitem(sys.modules, "msvcrt", msvcrt)
    return fake


@pytest.fixture
def tm_module(mt5_fake, monkeypatch):
    """trade_management with its module-level `mt5` bound to THIS test's fake.

    Python caches modules, so the second test to import trade_management gets
    the first test's fake. Rebinding the attribute is what makes assertions on
    `mt5_fake.sent` meaningful per test.
    """
    import trade_management as tm

    monkeypatch.setattr(tm, "mt5", mt5_fake)
    tm._REBRACKETED_TICKETS.clear()
    return tm


def _position(ticket=1, side="sell", entry=4332.822, sl=4335.822, tp=4327.822,
              volume=0.5, opened=1000.0):
    return types.SimpleNamespace(
        ticket=ticket,
        symbol="XAUUSDr",
        type=_FakeMT5.POSITION_TYPE_BUY if side == "buy" else _FakeMT5.POSITION_TYPE_SELL,
        price_open=entry,
        price_current=entry,
        sl=sl,
        tp=tp,
        volume=volume,
        time=opened,
    )


# ===========================================================================
# paper_executor -- Stage 3 bracket
# ===========================================================================

def test_executor_places_stop_beyond_the_invalidation(mt5_fake):
    import paper_executor as pe

    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4315.0,
        structure_timeframe="M30", stop_level_id="H1_PREVIOUS_HIGH",
        target_level_id="M30_PREVIOUS_LOW",
    )
    sl, tp, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source == "structural_same_frame"
    assert sl > 4344.279, "stop must sit beyond the structural invalidation"


def test_executor_refuses_entry_when_reward_risk_is_poor(mt5_fake, monkeypatch):
    """Hard skip only when QWEN_SKIP_ON_GEOMETRY is enabled."""
    import paper_executor as pe

    monkeypatch.setattr(
        pe,
        "SKIP_ON_GEOMETRY_REJECTION",
        pe._GEOMETRY_SKIP_CANDIDATES,
    )
    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4324.0,
        structure_timeframe="M30", stop_level_id="H1", target_level_id="M30",
    )
    with pytest.raises(pe.GeometryRejection) as excinfo:
        pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert excinfo.value.reason_code == "geometry:reward_risk_too_low"


def test_executor_falls_back_on_poor_rr_when_skip_disabled(mt5_fake, monkeypatch):
    """Observation window: poor R:R uses fixed $3/$5 instead of refusing."""
    import paper_executor as pe

    monkeypatch.setattr(pe, "SKIP_ON_GEOMETRY_REJECTION", frozenset())
    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4324.0,
        structure_timeframe="M30", stop_level_id="H1", target_level_id="M30",
    )
    sl, tp, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source.startswith("fixed_3_5_after_")
    assert sl == pytest.approx(4332.822 + pe.INITIAL_STOP_DISTANCE)
    assert tp == pytest.approx(4332.822 - pe.INITIAL_TAKE_PROFIT_DISTANCE)


def test_executor_refuses_htf_thesis_with_micro_fixed_bracket(mt5_fake, monkeypatch):
    """2026-08-13: H4+$3 stop is the Asia sudden-loss pattern — never fall back."""
    import paper_executor as pe

    monkeypatch.setattr(pe, "SKIP_ON_GEOMETRY_REJECTION", frozenset())
    monkeypatch.setattr(pe, "ENFORCE_HTF_MICRO_BRACKET", True)
    args = Namespace(
        side="sell",
        management_reference_sl=4411.434,
        management_reference_tp=4401.199,
        structure_timeframe="H4",
        stop_level_id="H4",
        target_level_id="D1",
    )
    with pytest.raises(pe.GeometryRejection) as excinfo:
        pe.broker_bracket_from_plan(args, 4406.323, 3)
    assert excinfo.value.reason_code == "htf_thesis_micro_bracket"


def test_executor_observes_htf_micro_bracket_during_establishment(mt5_fake, monkeypatch):
    """Demo establishment mode takes the protected trade and records the bypass."""
    import paper_executor as pe

    monkeypatch.setattr(pe, "SKIP_ON_GEOMETRY_REJECTION", frozenset())
    monkeypatch.setattr(pe, "ENFORCE_HTF_MICRO_BRACKET", False)
    args = Namespace(
        side="sell",
        proposal_id="establishment-1",
        management_reference_sl=4411.434,
        management_reference_tp=4401.199,
        structure_timeframe="H4",
        stop_level_id="H4",
        target_level_id="D1",
    )

    sl, tp, source = pe.broker_bracket_from_plan(args, 4406.323, 3)

    assert source.startswith("fixed_3_5_after_")
    assert sl == pytest.approx(4406.323 + pe.INITIAL_STOP_DISTANCE)
    assert tp == pytest.approx(4406.323 - pe.INITIAL_TAKE_PROFIT_DISTANCE)


def test_observation_window_records_what_it_would_have_refused(mt5_fake, monkeypatch):
    """The observation window is only worth running if it leaves evidence.

    With the gate off we take the trade anyway, so the ONLY record that the
    setup was disliked is this event. Without it, "should we enforce geometry"
    is unanswerable after two days of trading -- there is nothing to join the
    refusal to the P&L. Keyed on proposal_id, which is what the close record
    carries.
    """
    import paper_executor as pe

    captured = []
    monkeypatch.setattr(pe, "SKIP_ON_GEOMETRY_REJECTION", frozenset())
    monkeypatch.setattr(pe, "append_event", captured.append)

    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4324.0,
        structure_timeframe="M30", stop_level_id="H1", target_level_id="M30",
        proposal_id="paper-20260811T032032-31d4eaf3",
    )
    pe.broker_bracket_from_plan(args, 4332.822, 3)

    observations = [e for e in captured if e.get("event") == "geometry_observation"]
    assert len(observations) == 1, "a would-be refusal must leave exactly one record"
    record = observations[0]
    assert record["proposal_id"] == "paper-20260811T032032-31d4eaf3"
    assert record["reason_code"] == "geometry:reward_risk_too_low"
    assert record["would_refuse"] is True
    assert record["taken_on"] == "fixed_3_5"


def test_observation_recording_never_blocks_a_trade(mt5_fake, monkeypatch):
    """An observation is bookkeeping. If it throws, the trade still goes on."""
    import paper_executor as pe

    def explode(_event):
        raise OSError("disk full")

    monkeypatch.setattr(pe, "SKIP_ON_GEOMETRY_REJECTION", frozenset())
    monkeypatch.setattr(pe, "append_event", explode)

    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4324.0,
        structure_timeframe="M30", stop_level_id="H1", target_level_id="M30",
        proposal_id="p-1",
    )
    _, _, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source.startswith("fixed_3_5_after_")


def test_accepted_entries_are_not_recorded_as_observations(mt5_fake, monkeypatch):
    """Only refusals go in the log; otherwise the comparison group is polluted."""
    import paper_executor as pe

    captured = []
    monkeypatch.setattr(pe, "append_event", captured.append)

    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4315.0,
        structure_timeframe="M30", stop_level_id="H1_PREVIOUS_HIGH",
        target_level_id="M30_PREVIOUS_LOW", proposal_id="p-2",
    )
    _, _, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source == "structural_same_frame"
    assert not [e for e in captured if e.get("event") == "geometry_observation"]


def test_executor_falls_back_when_structure_is_missing(mt5_fake):
    """Missing information degrades to legacy; it never leaves a fill unprotected."""
    import paper_executor as pe

    args = Namespace(side="sell", management_reference_sl=None,
                     management_reference_tp=None)
    sl, tp, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source == "fixed_3_5_no_structure"
    assert sl == pytest.approx(4332.822 + pe.INITIAL_STOP_DISTANCE)
    assert tp == pytest.approx(4332.822 - pe.INITIAL_TAKE_PROFIT_DISTANCE)


def test_submit_single_position_always_returns_a_four_tuple():
    """Regression: a rejection once returned a 5-key dict from a function whose
    caller unpacks 4 values, crashing every refused entry live with
    'too many values to unpack (expected 4, got 5)'.

    GeometryRejection must PROPAGATE from submit_single_position; only _run,
    which owns the skip record, may convert it into a result.
    """
    import ast

    source = (Path(__file__).resolve().parents[1] / "paper_executor.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    submit = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "submit_single_position"
    )
    returns = [n for n in ast.walk(submit) if isinstance(n, ast.Return)]
    assert returns, "submit_single_position must return something"
    for node in returns:
        assert isinstance(node.value, ast.Tuple), (
            "submit_single_position must only return a tuple; the caller unpacks it"
        )
        assert len(node.value.elts) == 4, "caller unpacks exactly 4 values"

    run = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_run"
    )
    caught = {
        getattr(handler.type, "id", None)
        for node in ast.walk(run) if isinstance(node, ast.Try)
        for handler in node.handlers
    }
    assert "GeometryRejection" in caught, "_run must convert the rejection to a skip"


def test_order_uses_planned_invalidation_as_live_broker_stop():
    """A crossed invalidation exits on the first broker quote, not M1/M5 close."""
    source = (Path(__file__).resolve().parents[1] / "paper_executor.py").read_text(
        encoding="utf-8"
    )
    assert "safety_sl = planned_invalidation" in source
    assert '"geometry:invalidation_already_crossed"' in source


def test_structural_stop_distance_controls_submitted_volume(mt5_fake):
    """Wide structural invalidation reduces size instead of increasing risk."""
    import paper_executor as pe

    args = Namespace(
        side="sell", management_reference_sl=4344.279,
        management_reference_tp=4320.0, structure_timeframe="M30",
        stop_level_id="H1_PREVIOUS_HIGH", target_level_id="M30_PREVIOUS_LOW",
        proposal_id="risk-sized", risk_budget=150.0,
    )
    sl, _, source, volume = pe.broker_bracket_from_plan(
        args, 4332.822, 3, include_volume=True
    )
    assert source == "structural_same_frame"
    assert sl > args.management_reference_sl
    assert volume < 0.5
    assert volume == pytest.approx(0.12, abs=0.02)


def test_flag_disables_structural_bracket(mt5_fake, monkeypatch):
    import paper_executor as pe

    monkeypatch.setattr(pe, "STRUCTURAL_BRACKET_ENABLED", False)
    args = Namespace(side="sell", management_reference_sl=4344.279,
                     management_reference_tp=4315.0)
    _, _, source = pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert source == "fixed_3_5"


# ===========================================================================
# trade_management -- 30s re-bracket
# ===========================================================================

def test_rebracket_sends_an_sltp_order(mt5_fake, tm_module):
    """Post-fill correction may extend TP but cannot increase accepted risk."""
    tm = tm_module
    mt5_fake.set_price(4333.2)
    position = _position()
    levels = {"XAUUSDr": {
        "H1_PREVIOUS_HIGH": 4344.279,
        "M30_PREVIOUS_LOW": 4320.0,
        "M1_CURRENT_OPEN": 4333.0,
    }}
    tm.rebracket_if_needed(position, levels)

    assert mt5_fake.sent, "no order_send issued"
    sent = mt5_fake.sent[-1]
    assert sent["action"] == _FakeMT5.TRADE_ACTION_SLTP
    assert sent["position"] == position.ticket
    assert sent["sl"] == position.sl
    assert sent["tp"] == pytest.approx(4320.0)


def test_rebracket_never_widens_a_legacy_tight_stop(
    mt5_fake, tm_module
):
    """A legacy fill cannot be rescued by increasing risk after acceptance."""
    tm = tm_module
    mt5_fake.set_price(4333.2)
    position = _position()   # sized for a 3.00 stop
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    room_before = abs(position.price_open - position.sl)
    room_after = abs(position.price_open - sent["sl"])
    assert room_after == pytest.approx(room_before)


def test_rebracket_reaches_structure_when_sized_correctly(mt5_fake, tm_module):
    """With Stage 3 sizing, the re-bracket reaches structure without clipping."""
    tm = tm_module
    # Same invalidation, but the position was sized for it at entry: a wider
    # initial stop means the ceiling is proportionally wider too.
    position = _position(sl=4344.579, volume=0.13)
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    assert sent["sl"] == position.sl


def test_rebracket_ignores_current_open_levels(mt5_fake, tm_module):
    """*_CURRENT_OPEN moves under the position; it is not an invalidation."""
    tm = tm_module
    position = _position()
    levels = {"XAUUSDr": {"M1_CURRENT_OPEN": 4334.0, "H1_CURRENT_OPEN": 4340.0}}
    tm.rebracket_if_needed(position, levels)
    assert not mt5_fake.sent, "CURRENT_OPEN must not be used as structure"


def test_rebracket_runs_once_per_ticket(mt5_fake, tm_module):
    tm = tm_module
    position = _position()
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)
    first = len(mt5_fake.sent)
    tm.rebracket_if_needed(position, levels)
    assert len(mt5_fake.sent) == first, "re-bracket must not repeat every cycle"


def test_rebracket_picks_nearest_structure_on_each_side(mt5_fake, tm_module):
    tm = tm_module
    position = _position()
    stop_px, target_px, stop_id, target_id = tm.structural_levels_for(
        position,
        {"XAUUSDr": {
            "H1_PREVIOUS_HIGH": 4344.279,
            "H4_PREVIOUS_HIGH": 4356.737,   # further away, should lose
            "M30_PREVIOUS_LOW": 4320.0,
            "D1_PREVIOUS_LOW": 4300.0,      # further away, should lose
        }},
    )
    assert stop_id == "H1_PREVIOUS_HIGH"
    assert target_id == "M30_PREVIOUS_LOW"
    assert stop_px == pytest.approx(4344.279)
    assert target_px == pytest.approx(4320.0)


def test_rebracket_handles_buy_side(mt5_fake, tm_module):
    tm = tm_module
    mt5_fake.set_price(4338.6)
    position = _position(ticket=2, side="buy", entry=4339.107,
                         sl=4336.107, tp=4344.107)
    levels = {"XAUUSDr": {"H1_PREVIOUS_LOW": 4331.974, "M30_PREVIOUS_HIGH": 4355.0}}
    tm.rebracket_if_needed(position, levels)
    sent = mt5_fake.sent[-1]
    assert sent["sl"] == position.sl
    assert sent["tp"] == pytest.approx(4355.0)


def test_rebracket_never_tightens_a_correct_structural_bracket(mt5_fake, tm_module):
    """Reproduces the 2026-08-10 19:03 incident exactly.

    Stage 3 placed a correct bracket (stop 4316.369 beyond H1_PREVIOUS_LOW,
    8.84 away). The re-bracket then tightened it onto M5_PREVIOUS_HIGH at
    4324.578 and pulled the target in from 4337.985 to 4325.541. The trade was
    stopped out one second later for -49.50.

    The correction exists to rescue a bracket sitting INSIDE the invalidation.
    It must never remove room from one that is already correct.
    """
    tm = tm_module
    mt5_fake.set_price(4325.5)
    position = _position(ticket=99, side="buy", entry=4325.2,
                         sl=4316.369, tp=4337.985, volume=0.16)
    levels = {"XAUUSDr": {
        "M5_PREVIOUS_HIGH": 4324.578,     # nearer than the real invalidation
        "M1_PREVIOUS_HIGH": 4325.541,     # nearer than the real target
        "H1_PREVIOUS_LOW": 4316.5,
        "D1_FLOOR_PIVOT": 4337.985,
    }}
    tm.rebracket_if_needed(position, levels)

    if mt5_fake.sent:
        sent = mt5_fake.sent[-1]
        room_before = abs(position.price_open - position.sl)
        room_after = abs(position.price_open - sent["sl"])
        assert room_after >= room_before, (
            f"re-bracket removed room: {room_before:.3f} -> {room_after:.3f}"
        )
        assert sent["tp"] >= position.tp, "re-bracket pulled the target closer"


def test_rebracket_does_not_rescue_by_widening_after_fill(mt5_fake, tm_module):
    """An inadequate entry bracket is an entry defect, not management licence."""
    tm = tm_module
    mt5_fake.set_price(4333.2)
    position = _position()   # sell, stop 4335.822, only 3.00 of room
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    assert sent["sl"] == position.sl


def test_rebracket_no_structure_is_a_noop(mt5_fake, tm_module):
    tm = tm_module
    tm.rebracket_if_needed(_position(ticket=3), {"XAUUSDr": {}})
    assert not mt5_fake.sent
