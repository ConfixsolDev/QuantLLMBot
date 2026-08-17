"""ATR snapshot attaches to every Qwen request/response record."""

from __future__ import annotations

import io_performance_log as iol
import market_atr


def test_wilder_atr_known_series():
    highs = [10] + [12] * 14
    lows = [8] + [10] * 14
    closes = [10] + [11] * 14
    atr = market_atr.wilder_atr(highs, lows, closes, period=14)
    assert atr == 2.0


def test_wilder_atr_needs_period_plus_one():
    assert market_atr.wilder_atr([1, 2], [0, 1], [1, 1], period=51) is None


def test_atr_ratio_3_51():
    assert market_atr.atr_ratio_3_51(1.8, 1.5) == 1.2
    assert market_atr.atr_ratio_3_51(None, 1.5) is None
    assert market_atr.atr_ratio_3_51(1.8, 0) is None


def test_log_qwen_generate_records_dual_m1_atr(monkeypatch):
    captured = []
    monkeypatch.setattr(
        iol,
        "_append_jsonl",
        lambda base, record: captured.append((base, record)),
    )
    fake_atr = {
        "timeframe": "M1",
        "periods": [51, 3],
        "ok": True,
        "atr_m1_51": 1.85,
        "atr_m1_3": 0.62,
        "atr_ratio_3_51": 0.3351,
    }
    monkeypatch.setattr(iol, "capture_atr_snapshot", lambda symbol=None: fake_atr)

    result = iol.log_qwen_generate(
        model="test-model",
        prompt='{"hello":1}',
        num_ctx=4096,
        num_predict=64,
        timeout=5,
        format_schema={"type": "object"},
        caller="test",
        fn=lambda: {"response": '{"action":"wait"}', "total_duration": 123},
    )

    assert result["market_atr"] == fake_atr
    assert captured[0][1]["request"]["atr"]["atr_m1_51"] == 1.85
    assert captured[0][1]["response"]["atr"]["atr_m1_3"] == 0.62
    assert captured[0][1]["atr"]["atr_ratio_3_51"] == 0.3351
    assert captured[0][1]["atr"] == fake_atr


def test_append_qwen_decision_stores_atr(monkeypatch):
    from tick_data_archive import append_qwen_decision

    captured = []
    monkeypatch.setattr(
        "tick_data_archive.append_tick_record",
        lambda base, record: captured.append((base, record)),
    )
    atr = {
        "atr_m1_51": 1.8,
        "atr_m1_3": 0.5,
        "atr_ratio_3_51": 0.2778,
        "ok": True,
    }
    append_qwen_decision(
        decision_type="entry",
        symbol="XAUUSDr",
        price=4400.0,
        prompt_text="p",
        raw_response="{}",
        parsed={"action": "wait"},
        model="m",
        atr=atr,
    )
    assert captured[0][1]["atr"] == atr


def test_snapshot_atr_from_cache_ok_without_mt5():
    bars = [
        {"high": 12, "low": 10, "close": 11, "open": 11, "time": i}
        for i in range(60)
    ]
    snap = market_atr.snapshot_atr_from_cache(bars, "XAUUSDr")
    assert snap["ok"] is True
    assert snap["source"] == "cache"
    assert snap["atr_m1_51"] is not None
    assert snap["atr_m1_3"] is not None
    assert snap["atr_ratio_3_51"] is not None
    assert snap["error"] is None


def test_snapshot_atr_from_cache_insufficient_bars():
    snap = market_atr.snapshot_atr_from_cache([], "XAUUSDr")
    assert snap["ok"] is False
    assert "insufficient_cached_bars" in str(snap["error"])
