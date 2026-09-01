from vnext.risk.engine import evaluate_risk


def test_risk_fails_closed_on_daily_loss_and_health():
    result = evaluate_risk(account_equity=10000, risk_fraction=.01, entry=10, stop=9, point_value=1, daily_pnl=-200, daily_loss_cap=-200, broker_healthy=False)
    assert result.approved is False
    assert "daily_loss_cap_reached" in result.reasons
    assert "broker_unhealthy" in result.reasons


def test_risk_approves_valid_hard_constraints():
    assert evaluate_risk(account_equity=10000, risk_fraction=.01, entry=10, stop=9, point_value=1).approved


def test_risk_binds_exact_market_geometry_and_normalizes_volume_down():
    result = evaluate_risk(account_equity=1000, max_cash_loss=300, entry=3000, stop=2997,
                           target=3005, direction="buy", point_value=1,
                           tick_size=.01, tick_value=1, volume_min=.01,
                           volume_max=100, volume_step=.01, daily_loss_cap=2000,
                           max_open_positions=1)
    assert result.approved
    assert result.normalized_volume == 1.0
    assert result.entry_price == 3000
    assert result.stop_price == 2997
    assert result.target_price == 3005
    assert result.request_hash


def test_risk_rejects_invalid_side_geometry_and_position_cap():
    result = evaluate_risk(account_equity=1000, max_cash_loss=300, entry=3000, stop=3003,
                           target=3005, direction="buy", point_value=1,
                           open_positions=1, max_open_positions=1)
    assert not result.approved
    assert "buy_geometry_invalid" in result.reasons
    assert "position_cap_reached" in result.reasons
