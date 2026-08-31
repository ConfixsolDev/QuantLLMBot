from vnext.risk.engine import evaluate_risk


def test_risk_fails_closed_on_daily_loss_and_health():
    result = evaluate_risk(account_equity=10000, risk_fraction=.01, entry=10, stop=9, point_value=1, daily_pnl=-200, daily_loss_cap=-200, broker_healthy=False)
    assert result.approved is False
    assert "daily_loss_cap_reached" in result.reasons
    assert "broker_unhealthy" in result.reasons


def test_risk_approves_valid_hard_constraints():
    assert evaluate_risk(account_equity=10000, risk_fraction=.01, entry=10, stop=9, point_value=1).approved
