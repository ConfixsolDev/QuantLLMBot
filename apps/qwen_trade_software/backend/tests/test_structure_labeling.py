from market_intelligence.projection import reduce_event
from market_intelligence.structure_labeling import label_structure


def candle(index, high, low, close=None, open_=None):
    close = (high + low) / 2 if close is None else close
    open_ = close if open_ is None else open_
    return {
        "event_time_utc": f"2026-01-01T{index:02d}:00:00Z",
        "evidence_id": f"candle-{index}",
        "open": open_, "high": high, "low": low, "close": close,
    }


def test_swing_is_not_known_before_right_wing_closes():
    bars = [candle(0, 2, 0), candle(1, 3, 1), candle(2, 8, 2),
            candle(3, 4, 1), candle(4, 3, 0)]
    assert label_structure("XAUUSDr", "H1", bars[:4], wing=2) == []
    events = label_structure("XAUUSDr", "H1", bars, wing=2)
    swing = next(row for row in events if row["event_type"] == "swing_high_confirmed")
    assert swing["event_time_utc"] == bars[4]["event_time_utc"]
    assert swing["payload"]["source_time_utc"] == bars[2]["event_time_utc"]
    assert swing["payload"]["knowledge_time_utc"] == bars[4]["event_time_utc"]


def test_replay_produces_stable_ids_and_shadow_has_no_authority():
    bars = [candle(i, high, low) for i, (high, low) in enumerate(
        [(2, 0), (3, 1), (8, 2), (4, 1), (3, 0), (5, 1), (4, 0)])]
    first = label_structure("XAUUSDr", "H1", bars, wing=2)
    second = label_structure("XAUUSDr", "H1", bars, wing=2)
    assert [row["event_id"] for row in first] == [row["event_id"] for row in second]
    assert all(row["payload"]["execution_authority"] is False for row in first)


def test_wick_through_closing_back_is_sweep_not_bos():
    bars = [candle(0, 2, 0), candle(1, 3, 1), candle(2, 8, 2, 4),
            candle(3, 4, 1), candle(4, 3, 0), candle(5, 9, 2, 7)]
    events = label_structure("XAUUSDr", "H1", bars, wing=2)
    at_last = [row["event_type"] for row in events if row["event_time_utc"] == bars[5]["event_time_utc"]]
    assert "liquidity_sweep" in at_last
    assert "bos_confirmed" not in at_last


def test_close_beyond_zone_then_hold_confirms_acceptance():
    bars = [candle(0, 2, 0), candle(1, 3, 1), candle(2, 8, 2, 4),
            candle(3, 4, 1), candle(4, 3, 0), candle(5, 10, 5, 9, 6),
            candle(6, 11, 8.5, 9.5, 9)]
    events = label_structure("XAUUSDr", "H1", bars, wing=2)
    types = [row["event_type"] for row in events]
    assert "bos_confirmed" in types
    assert "zone_broken" in types
    assert "zone_accepted" in types


def test_shadow_event_cannot_mutate_live_projection():
    prior = {"direction": "bullish", "state": "bullish_continuation",
             "event_time_utc": "2026-01-01T00:00:00Z"}
    shadow = {"symbol": "XAUUSDr", "timeframe": "H1",
              "event_time_utc": "2026-01-01T01:00:00Z",
              "payload": {"mode": "shadow_only", "direction": "bearish",
                          "execution_authority": False}}
    assert reduce_event(prior, shadow) is prior


def test_duplicate_close_prefers_explicit_broker_candle():
    bars = [candle(0, 2, 0), candle(1, 3, 1), candle(2, 8, 2, 4),
            candle(3, 4, 1), candle(4, 3, 0)]
    legacy = {**bars[-1], "evidence_id": "legacy", "high": 9999.0}
    broker = {**bars[-1], "evidence_id": "candle:XAUUSDr:H1:broker:source",
              "time_convention": "broker"}
    events = label_structure("XAUUSDr", "H1", bars[:-1] + [legacy, broker], wing=2)
    assert events
    assert all("legacy" not in row["payload"].get("evidence_ids", []) for row in events)
