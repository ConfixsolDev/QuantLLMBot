from pathlib import Path

from market_intelligence.projection import reduce_event, relationship_state
from market_intelligence.retrieval import RetrievalBroker
from market_intelligence.store import IntelligenceStore
from market_intelligence.collector import ingest_bars


def event(symbol="XAUUSDr", timeframe="H1", direction="bullish", suffix="1"):
    return {
        "event_id": f"{symbol}:{timeframe}:{suffix}", "symbol": symbol,
        "timeframe": timeframe, "event_type": "candle_closed",
        "event_time_utc": f"2026-08-20T0{suffix}:00:00Z",
        "evidence_id": f"{timeframe}_{suffix}",
        "payload": {"direction": direction, "close": 4400 + int(suffix)},
    }


def test_event_ledger_is_idempotent_and_projection_replays(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    first, second = event(suffix="1"), event(direction="bearish", suffix="2")
    assert store.append_event(first)
    assert not store.append_event(first)
    state = reduce_event(None, first)
    store.put_projection("XAUUSDr", "H1", state, first["event_id"])
    assert store.append_event(second)
    state = reduce_event(state, second)
    before = store.put_projection("XAUUSDr", "H1", state, second["event_id"])
    assert store.rebuild(reduce_event) == 2
    after = store.projection("XAUUSDr", "H1")
    assert after["direction"] == "bearish"
    assert after["structure_epoch"] == before["structure_epoch"]


def test_relationship_never_grants_dxy_execution_authority():
    relation = relationship_state({"direction": "bullish"}, {"direction": "bearish"})
    assert relation["state"] == "inverse_aligned"
    assert "XAUUSD" in relation["doctrine"]


def test_retrieval_is_allowlisted_bounded_and_audited(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    broker = RetrievalBroker(
        store,
        lambda symbol, tf, count: [{"evidence_id": f"{tf}_1"}] * count,
        lambda tf, count: ("DXY", [{"evidence_id": f"DXY_{tf}_1"}]),
    )
    results = broker.execute("XAUUSDr", [
        {"tool": "get_completed_candles", "symbol": "XAUUSDr", "timeframe": "H1", "count": 500},
        {"tool": "arbitrary_sql", "symbol": "XAUUSDr", "timeframe": "H1", "count": 1},
        {"tool": "get_dxy_state", "symbol": "DXY", "timeframe": "H4", "count": 10},
    ])
    assert len(results) == 2
    assert results[0]["row_count"] == 80
    assert results[1]["status"] == "rejected"
    assert len(store.recent_retrievals()) == 2


def test_independent_collector_backfills_every_unseen_candle_in_order(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    bars = [
        {"evidence_id": f"M1_{minute}", "open_time_utc": f"2026-08-20T10:0{minute}:00Z",
         "close_time_utc": f"2026-08-20T10:0{minute + 1}:00Z",
         "open": 100 + minute, "high": 102 + minute, "low": 99 + minute,
         "close": 101 + minute, "tick_volume": 10}
        for minute in range(4)
    ]
    assert ingest_bars(store, "XAUUSDr", "M1", bars) == 4
    assert ingest_bars(store, "XAUUSDr", "M1", bars) == 0
    events = store.events("XAUUSDr", "M1", 20)
    assert [row["evidence_id"] for row in events] == ["M1_0", "M1_1", "M1_2", "M1_3"]
    assert store.projection("XAUUSDr", "M1")["latest_evidence_id"] == "M1_3"


def test_late_historical_backfill_does_not_roll_projection_backward(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    newest = [{"evidence_id": "new", "open_time_utc": "2026-08-20T10:10:00Z",
               "close_time_utc": "2026-08-20T10:11:00Z", "open": 2, "high": 3,
               "low": 1, "close": 2.5, "tick_volume": 10}]
    older = [{"evidence_id": "old", "open_time_utc": "2026-08-20T10:00:00Z",
              "close_time_utc": "2026-08-20T10:01:00Z", "open": 1, "high": 2,
              "low": 0, "close": 1.5, "tick_volume": 10}]
    ingest_bars(store, "XAUUSDr", "M1", newest)
    ingest_bars(store, "XAUUSDr", "M1", older)
    assert store.projection("XAUUSDr", "M1")["latest_evidence_id"] == "new"
    store.rebuild(reduce_event)
    assert store.projection("XAUUSDr", "M1")["latest_evidence_id"] == "new"
