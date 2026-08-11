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


def test_executor_refuses_entry_when_reward_risk_is_poor(mt5_fake):
    """Must NOT silently fall back to the flat $3 it just rejected."""
    import paper_executor as pe

    args = Namespace(
        side="sell", management_reference_sl=4344.279, management_reference_tp=4324.0,
        structure_timeframe="M30", stop_level_id="H1", target_level_id="M30",
    )
    with pytest.raises(pe.GeometryRejection) as excinfo:
        pe.broker_bracket_from_plan(args, 4332.822, 3)
    assert excinfo.value.reason_code == "geometry:reward_risk_too_low"


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
    """The whole point: SL and TP actually move at the broker."""
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
    assert sent["sl"] > position.sl, "stop must move away from the entry bracket"
    assert sent["tp"] == pytest.approx(4320.0)


def test_rebracket_is_clipped_when_the_position_was_sized_for_a_tight_stop(
    mt5_fake, tm_module
):
    """The ceiling and the structural stop genuinely conflict on legacy fills.

    A position sized for a $3 stop cannot be re-bracketed to an 11.46-point
    invalidation without ~4x-ing the risk, so the 1.75x solvency rail clips it.
    The stop still improves (3.00 -> 5.25 points of room) but does not reach
    structure.

    This is why Stage 3 matters: sizing for the structural stop AT ENTRY means
    the re-bracket becomes a small correction instead of a risk explosion. The
    clip only affects fills opened under the old flat-$3 sizing.
    """
    tm = tm_module
    mt5_fake.set_price(4333.2)
    position = _position()   # sized for a 3.00 stop
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    room_before = abs(position.price_open - position.sl)
    room_after = abs(position.price_open - sent["sl"])
    assert room_after > room_before, "must gain room"
    assert room_after == pytest.approx(5.25, abs=0.01), "clipped to 1.75x initial risk"
    assert sent["sl"] < 4344.279, "ceiling prevents reaching structure on a legacy fill"


def test_rebracket_reaches_structure_when_sized_correctly(mt5_fake, tm_module):
    """With Stage 3 sizing, the re-bracket reaches structure without clipping."""
    tm = tm_module
    # Same invalidation, but the position was sized for it at entry: a wider
    # initial stop means the ceiling is proportionally wider too.
    position = _position(sl=4344.579, volume=0.13)
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    assert sent["sl"] > 4344.279, "stop should sit beyond the invalidation"


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
    # Direction is what matters here: a buy stop moves DOWN, away from entry.
    # How far it gets is bounded by the risk ceiling (see the clipping test).
    assert sent["sl"] < position.sl, "buy stop must move below the entry bracket"
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


def test_rebracket_still_rescues_a_bracket_inside_structure(mt5_fake, tm_module):
    """The rescue case must keep working -- that is the whole point of R1."""
    tm = tm_module
    mt5_fake.set_price(4333.2)
    position = _position()   # sell, stop 4335.822, only 3.00 of room
    levels = {"XAUUSDr": {"H1_PREVIOUS_HIGH": 4344.279, "M30_PREVIOUS_LOW": 4320.0}}
    tm.rebracket_if_needed(position, levels)

    sent = mt5_fake.sent[-1]
    assert abs(position.price_open - sent["sl"]) > abs(position.price_open - position.sl)


def test_rebracket_no_structure_is_a_noop(mt5_fake, tm_module):
    tm = tm_module
    tm.rebracket_if_needed(_position(ticket=3), {"XAUUSDr": {}})
    assert not mt5_fake.sent
