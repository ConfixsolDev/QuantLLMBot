from datetime import datetime, timedelta, timezone

from vnext.strategy.management import ScalpManagementParameters, manage_scalp


BASE = datetime(2026, 1, 1, 12, 0, 20, tzinfo=timezone.utc)
PARAMETERS = ScalpManagementParameters()


def test_quick_scalp_waits_for_initial_favorable_confirmation():
    result = manage_scalp(side="buy", entry=100, current=100, peak=100,
                          opened_at=BASE, now=BASE + timedelta(seconds=5), atr=1,
                          broker_stop=99, spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "WAIT" and result.phase == "INITIAL_CHECK"


def test_quick_scalp_cuts_fast_adverse_move():
    result = manage_scalp(side="buy", entry=100, current=99.7, peak=100,
                          opened_at=BASE, now=BASE + timedelta(seconds=5), atr=1,
                          broker_stop=99, spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "CLOSE" and result.reason == "early_adverse_move"


def test_quick_scalp_uses_next_m1_fifteen_second_check_then_waits():
    now = BASE.replace(second=0) + timedelta(minutes=1, seconds=10)
    result = manage_scalp(side="buy", entry=100, current=100, peak=100,
                          opened_at=BASE, now=now, atr=1, broker_stop=99,
                          spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "WAIT" and result.phase == "NEXT_M1_CHECK"
    later = BASE.replace(second=0) + timedelta(minutes=1, seconds=30)
    assert manage_scalp(side="buy", entry=100, current=100, peak=100,
                        opened_at=BASE, now=later, atr=1, broker_stop=99,
                        spread=.1, point=.01, parameters=PARAMETERS).phase == "FAILED_CHECK_WAIT"


def test_quick_scalp_expires_after_failed_confirmation_window():
    now = BASE.replace(second=0) + timedelta(minutes=2, seconds=1)
    result = manage_scalp(side="sell", entry=100, current=100, peak=100,
                          opened_at=BASE, now=now, atr=1, broker_stop=101,
                          spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "CLOSE" and result.reason == "scalp_confirmation_expired"


def test_quick_scalp_moves_stop_above_breakeven_after_one_atr():
    result = manage_scalp(side="buy", entry=100, current=101.2, peak=101.2,
                          opened_at=BASE, now=BASE + timedelta(minutes=3), atr=1,
                          broker_stop=99, spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "MOVE_STOP" and result.candidate_stop > 100


def test_quick_scalp_never_widens_existing_protection():
    result = manage_scalp(side="sell", entry=100, current=99, peak=98.9,
                          opened_at=BASE, now=BASE + timedelta(minutes=3), atr=1,
                          broker_stop=98.0, spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "HOLD"
