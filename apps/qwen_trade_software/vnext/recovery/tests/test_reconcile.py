from vnext.recovery.reconcile import reconcile


def test_mismatch_halts_new_trade_creation():
    result = reconcile(broker_positions=[{"position_id": 1}], ledger_positions=[], broker_healthy=True, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert result.safe_to_resume is False
    assert "broker_ledger_position_mismatch" in result.reasons


def test_healthy_matching_state_can_resume():
    result = reconcile(broker_positions=[{"position_id": 1}], ledger_positions=[{"position_id": 1}], broker_healthy=True, data_healthy=True, timescale_healthy=True, redis_rebuilt=True)
    assert result.safe_to_resume is True
