from datetime import datetime, timedelta, timezone

from market_graph.live_updater import M1_FRESHNESS_LIMIT_SECONDS, _m1_freshness
from market_intelligence.live_structure_updater import update_live_structure
from market_intelligence.store import IntelligenceStore


def _candle(minute: int, high: float, low: float, close: float) -> dict:
    opened = datetime(2026, 8, 26, 0, minute, tzinfo=timezone.utc)
    closed = opened + timedelta(minutes=1)
    evidence = f"candle:XAUUSDr:M1:broker:{opened:%Y-%m-%dT%H:%M:%SZ}"
    return {
        "event_id": f"XAUUSDr:M1:{evidence}:close",
        "symbol": "XAUUSDr",
        "timeframe": "M1",
        "event_type": "candle_closed",
        "event_time_utc": closed.isoformat().replace("+00:00", "Z"),
        "evidence_id": evidence,
        "payload": {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": 10,
            "time_convention": "broker",
        },
    }


def test_live_structure_update_is_idempotent_and_uses_ledger_candles(tmp_path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    prices = [(10, 8, 9), (12, 9, 11), (15, 10, 14), (12, 8, 9), (11, 7, 8)]
    for minute, (high, low, close) in enumerate(prices):
        assert store.append_event(_candle(minute, high, low, close))

    first = update_live_structure(store, "XAUUSDr", ["M1"])
    second = update_live_structure(store, "XAUUSDr", ["M1"])
    assert first["M1"]["inserted"] > 0
    assert second["M1"]["inserted"] == 0
    assert store.graph_outbox_stats()["pending"] > len(prices)


def test_m1_freshness_reports_lag_and_fails_closed():
    raw = {
        "as_of_utc": "2026-08-26T00:02:00Z",
        "symbols": {
            "XAUUSDr": {"M1": [{
                "event_time": "2026-08-26T00:01:00Z",
                "evidence_id": "fresh",
            }]},
            "DXY": {"M1": [{
                "event_time": "2026-08-25T23:00:00Z",
                "evidence_id": "stale",
            }]},
        },
    }
    result = _m1_freshness(raw, ["XAUUSDr", "DXY"])
    assert result["symbols"]["XAUUSDr"]["lag_seconds"] == 60
    assert result["symbols"]["XAUUSDr"]["fresh"] is True
    assert result["symbols"]["DXY"]["lag_seconds"] > M1_FRESHNESS_LIMIT_SECONDS
    assert result["fresh"] is False
