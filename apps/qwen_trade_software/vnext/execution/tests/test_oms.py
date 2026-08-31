import pytest

from vnext.execution.oms import Order


def test_submission_is_not_fill():
    order = Order("o1", "c1", "XAUUSD", "SCALP_V1")
    submitted = order.transition("SUBMITTED", broker_order_id="b1")
    assert submitted.state == "SUBMITTED"
    assert submitted.filled_volume == 0
    assert submitted.transition("ACKNOWLEDGED").state == "ACKNOWLEDGED"


def test_invalid_lifecycle_jump_is_rejected():
    with pytest.raises(ValueError):
        Order("o1", "c1", "XAUUSD", "SCALP_V1").transition("FILLED")
