from types import SimpleNamespace

from vnext.risk.mt5 import live_risk_inputs


class MT5:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def account_info(self):
        return SimpleNamespace(equity=1000, trade_mode=0, trade_allowed=True, trade_expert=True)

    def terminal_info(self):
        return SimpleNamespace(connected=True)

    def symbol_info(self, pair):
        return SimpleNamespace(trade_tick_value=.1, trade_tick_size=.001, volume_min=.01, volume_max=200, volume_step=.01)

    def symbol_info_tick(self, pair):
        return SimpleNamespace(bid=3000, ask=3000.1)

    def history_deals_get(self, start, end):
        return (SimpleNamespace(magic=3101, profit=-12, swap=-1, commission=-2, fee=0),)

    def positions_get(self, symbol):
        return (SimpleNamespace(magic=3101), SimpleNamespace(magic=999))


def test_live_risk_inputs_resolves_declared_market_bracket_and_owned_account_facts():
    result = live_risk_inputs(MT5(), {"pair": "XAUUSDr", "data_quality": {"status": "ready"}},
                              {"direction": "buy", "metadata": {"risk_policy": {
                                  "entry_mode": "MARKET", "stop_distance_price": 3,
                                  "target_distance_price": 5, "max_cash_loss": 300,
                                  "daily_loss_cap": 2000, "max_open_positions": 1}}}, magic_number=3101)
    assert result["entry"] == 3000.1
    assert result["stop"] == 2997.1
    assert result["target"] == 3005.1
    assert result["daily_pnl"] == -15
    assert result["open_positions"] == 1
    assert result["demo_account"] is True
