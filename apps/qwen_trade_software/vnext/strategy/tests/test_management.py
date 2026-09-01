from datetime import datetime, timedelta, timezone

from vnext.strategy.management import (
    ScalpManagementParameters, emergency_close_required, manage_scalp,
    qwen_review_due, validate_qwen_management_review,
)


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


def test_scalp_has_ten_minute_hard_expiry_and_five_minute_review():
    result = manage_scalp(side="buy", entry=100, current=101, peak=101,
                          opened_at=BASE, now=BASE + timedelta(minutes=10), atr=1,
                          broker_stop=97, spread=.1, point=.01, parameters=PARAMETERS)
    assert result.action == "CLOSE" and result.reason == "max_scalp_duration"
    assert not qwen_review_due(opened_at=BASE, now=BASE + timedelta(minutes=4),
                               last_review_at=None, parameters=PARAMETERS)
    assert qwen_review_due(opened_at=BASE, now=BASE + timedelta(minutes=5),
                           last_review_at=None, parameters=PARAMETERS)


def test_dual_completed_candle_invalidation_requires_emergency_close():
    assert emergency_close_required(side="buy", invalidation_price=99,
                                    latest_m1={"close": 98.9}, latest_m5={"close": 98.8})
    assert not emergency_close_required(side="buy", invalidation_price=99,
                                        latest_m1={"close": 98.9}, latest_m5={"close": 99.1})


def test_qwen_management_is_bounded_to_evidence_backed_close_and_one_way_protection():
    review, failures = validate_qwen_management_review(
        response={"action": "close", "close_confirmed": True,
                  "evidence_ids": ("m1", "m5"), "reason": "structure failed"},
        side="buy", current_stop=97, current_target=105, latest_m1_id="m1", latest_m5_id="m5")
    assert not failures and review.action == "close"
    rejected, failures = validate_qwen_management_review(
        response={"action": "protect", "candidate_stop": 96.5},
        side="buy", current_stop=97, current_target=105, latest_m1_id="m1", latest_m5_id="m5")
    assert rejected.action == "hold" and "management:stop_not_tighter" in failures
    protected, failures = validate_qwen_management_review(
        response={"action": "protect", "candidate_stop": 100.1, "candidate_target": 103,
                  "deterioration_confirmed": True, "evidence_ids": ("m1", "m5")},
        side="buy", current_stop=97, current_target=105, latest_m1_id="m1", latest_m5_id="m5")
    assert not failures and protected.candidate_stop == 100.1 and protected.candidate_target == 103
