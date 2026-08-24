from pathlib import Path
from datetime import datetime, timedelta, timezone

from market_graph.client import (CONTEXT_QUERY, DELETE_EVENT_BUCKET_EDGES, Neo4jMarketGraph,
                                 UPSERT_BUCKET_EDGES, UPSERT_EVENTS, UPSERT_NEXT_EDGES)
from market_graph.config import GraphConfig
from market_graph.projector import GraphProjector
from market_graph.temporal import graph_row, time_buckets
from market_intelligence import decision_events
from market_intelligence import execution_events
from market_intelligence.store import IntelligenceStore
from market_intelligence.historical_backfill import aggregate_ny_h4, ny_h4_start
from market_graph.market_state import evidence_confidence
from market_context_cache import MarketContextCache, is_timeframe_open_aligned


def test_new_york_h4_anchor_is_1700_and_dst_aware():
    winter = ny_h4_start(datetime(2026, 1, 7, 23, 0, tzinfo=timezone.utc))
    summer = ny_h4_start(datetime(2026, 7, 7, 22, 0, tzinfo=timezone.utc))
    assert winter == datetime(2026, 1, 7, 22, 0, tzinfo=timezone.utc)
    assert summer == datetime(2026, 7, 7, 21, 0, tzinfo=timezone.utc)


def test_cache_alignment_accepts_new_york_h4_boundaries_in_both_seasons():
    assert is_timeframe_open_aligned(
        "H4", datetime(2026, 1, 8, 2, 0, tzinfo=timezone.utc)
    )
    assert is_timeframe_open_aligned(
        "H4", datetime(2026, 7, 8, 1, 0, tzinfo=timezone.utc)
    )


def test_cache_alignment_rejects_broker_h4_boundary_outside_new_york_schedule():
    assert not is_timeframe_open_aligned(
        "H4", datetime(2026, 7, 8, 0, 0, tzinfo=timezone.utc)
    )


def test_cache_clears_all_h4_before_canonical_rebuild(tmp_path: Path):
    cache = MarketContextCache(tmp_path / "context.sqlite3")
    base = {
        "symbol": "XAUUSDr", "timeframe": "H4", "close_time_utc": "2026-07-08T05:00:00Z",
        "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
        "tick_volume": 10, "spread": 2, "real_volume": 0, "is_complete": True,
    }
    cache.ingest_completed([{**base, "open_time_utc": "2026-07-08T00:00:00Z",
                             "source": "MT5", "evidence_id": "legacy"},
                            {**base, "open_time_utc": "2026-07-08T01:00:00Z",
                             "source": "MT5_H1_AGGREGATED_NY", "evidence_id": "canonical"}])
    assert cache.clear_h4_for_canonical_rebuild("XAUUSDr") == 2
    assert cache.completed("XAUUSDr", "H4") == []
    cache.connection.close()


def test_cache_audits_and_repairs_only_canonical_derived_h4(tmp_path: Path):
    cache = MarketContextCache(tmp_path / "context.sqlite3")
    base = {
        "symbol": "XAUUSDr", "timeframe": "H4",
        "open_time_utc": "2026-08-24T01:00:00Z",
        "close_time_utc": "2026-08-24T05:00:00Z",
        "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0,
        "tick_volume": 10, "spread": 2, "real_volume": 0,
        "is_complete": True, "source": "MT5_H1_AGGREGATED_NY",
        "evidence_id": "candle:XAUUSDr:H4:new_york_1700_dst:2026-08-24T01:00:00Z",
    }
    cache.ingest_completed([base])
    repaired = cache.repair_derived_h4([{**base, "open": 98.0, "low": 97.0}])
    assert repaired[0]["changed_fields"] == ["open", "low"]
    assert cache.completed("XAUUSDr", "H4")[0]["open"] == 98.0
    audit = cache.connection.execute(
        "SELECT reason FROM completed_candle_corrections"
    ).fetchone()
    assert audit["reason"] == "partial_h1_aggregate_migration_v1"
    cache.connection.close()


def test_new_york_h4_aggregates_ohlc_and_volume():
    rows = []
    for hour in range(22, 26):
        opened = datetime(2026, 1, 7, hour % 24, tzinfo=timezone.utc)
        if hour >= 24:
            opened += timedelta(days=1)
        rows.append({"open_time": opened, "open": hour, "high": hour + 2,
                     "low": hour - 1, "close": hour + 1, "tick_volume": 10,
                     "real_volume": 2, "spread": 3, "symbol": "XAUUSDr"})
    candle = aggregate_ny_h4(rows)[0]
    assert candle["open"] == 22 and candle["close"] == 26
    assert candle["tick_volume"] == 40 and candle["real_volume"] == 8
    assert candle["constituent_count"] == 4


def test_new_york_h4_does_not_certify_partial_constituent_set():
    opened = datetime(2026, 1, 7, 22, 0, tzinfo=timezone.utc)
    rows = [{
        "open_time": opened + timedelta(hours=hour),
        "open": 100 + hour, "high": 102 + hour, "low": 99 + hour,
        "close": 101 + hour, "tick_volume": 10, "real_volume": 0,
        "spread": 2, "symbol": "XAUUSDr",
    } for hour in range(2)]
    as_of = opened + timedelta(hours=6)
    assert aggregate_ny_h4(rows, as_of=as_of) == []
    forming = aggregate_ny_h4(rows, include_forming=True, as_of=as_of)
    assert len(forming) == 1
    assert forming[0]["is_complete"] is False


def test_level_confidence_is_bounded_and_evidence_based():
    assert evidence_confidence({"calculation_method": "live_closed_swing",
                                "test_count": 3, "source_candle_ids": ["a", "b"]}) == 74
    assert evidence_confidence({"calculation_method": "operator_mapped",
                                "test_count": 100, "source_candle_ids": list(range(20))}) == 95


def test_vertical_h4_bucket_uses_new_york_anchor_in_summer():
    buckets = time_buckets("XAUUSDr", datetime(2026, 7, 7, 23, 0,
                                                tzinfo=timezone.utc), "M1")
    h4 = next(row for row in buckets if row["timeframe"] == "H4")
    assert h4["starts_at"] == "2026-07-07T21:00:00Z"
    assert h4["ends_at"] == "2026-07-08T01:00:00Z"
    assert h4["time_convention"] == "new_york_1700_dst"


def config(**overrides):
    values = {
        "enabled": True,
        "uri": "bolt://example:7687",
        "user": "neo4j",
        "password": "secret",
        "database": "neo4j",
        "symbols": ("XAUUSDr", "DXY", "EURUSD"),
        "batch_size": 100,
        "interval_seconds": 1.0,
        "max_attempts": 2,
    }
    values.update(overrides)
    return GraphConfig(**values)


def event(symbol="XAUUSDr", timeframe="M1", minute=1):
    return {
        "event_id": f"{symbol}:{timeframe}:{minute}",
        "symbol": symbol,
        "timeframe": timeframe,
        "event_type": "candle_closed",
        "event_time_utc": f"2026-08-21T00:{minute:02d}:00Z",
        "evidence_id": f"{symbol}_{timeframe}_{minute}",
        "payload": {"open": 100.0, "high": 102.0, "low": 99.0,
                    "close": 101.0, "direction": "bullish"},
    }


class RecordingGraph:
    def __init__(self, error=None):
        self.error = error
        self.rows = []

    def upsert_rows(self, rows):
        if self.error:
            raise self.error
        self.rows.extend(rows)


class RetryableGraphError(RuntimeError):
    def is_retryable(self):
        return True


def test_append_transactionally_enqueues_one_graph_projection(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    item = event()
    assert store.append_event(item)
    assert not store.append_event(item)
    batch = store.graph_outbox_batch()
    assert [row["event_id"] for row in batch] == [item["event_id"]]
    assert store.graph_outbox_stats()["pending"] == 1


def test_outbox_orders_each_symbol_and_timeframe_independently(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    items = [event("XAUUSDr", "M1", 1), event("DXY", "M1", 1),
             event("EURUSD", "M1", 1), event("XAUUSDr", "M1", 2)]
    for item in items:
        assert store.append_event(item)
    rows = {row["event_id"]: row for row in store.graph_outbox_batch()}
    assert rows[items[3]["event_id"]]["previous_event_id"] == items[0]["event_id"]
    assert rows[items[1]["event_id"]]["previous_event_id"] is None
    assert rows[items[2]["event_id"]]["previous_event_id"] is None


def test_shadow_structure_evidence_is_not_starved_by_candle_backlog(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    ordinary = event("XAUUSDr", "H4", 1)
    shadow = event("XAUUSDr", "M1", 2)
    shadow["event_type"] = "bos_confirmed"
    shadow["payload"].update({"mode": "shadow_only", "execution_authority": False})
    store.append_event(ordinary)
    store.append_event(shadow)
    assert [row["event_id"] for row in store.graph_outbox_batch()] == [shadow["event_id"]]


def test_projector_is_idempotent_and_marks_success(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    store.append_event(event())
    graph = RecordingGraph()
    projector = GraphProjector(store, graph, config())
    assert projector.project_once()["projected"] == 1
    assert projector.project_once()["status"] == "idle"
    assert len(graph.rows) == 1
    assert store.graph_outbox_stats() == {
        "pending": 0, "projected": 1, "dead": 0,
        "last_projected_at_utc": store.graph_outbox_stats()["last_projected_at_utc"],
    }


def test_projector_failure_is_isolated_and_eventually_dead_letters(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    store.append_event(event())
    projector = GraphProjector(store, RecordingGraph(RuntimeError("offline")), config())
    assert projector.project_once()["status"] == "error"
    assert store.graph_outbox_stats()["pending"] == 1
    assert projector.project_once()["status"] == "error"
    assert store.graph_outbox_stats()["dead"] == 1
    assert store.events("XAUUSDr", "M1", 10)[0]["event_id"] == event()["event_id"]


def test_retryable_graph_outage_does_not_consume_dead_letter_budget(tmp_path: Path):
    store = IntelligenceStore(tmp_path / "memory.sqlite3")
    store.append_event(event())
    projector = GraphProjector(store, RecordingGraph(RetryableGraphError("offline")), config())
    result = projector.project_once()
    assert result["retryable"] is True
    assert store.graph_outbox_stats()["pending"] == 1
    assert store.graph_outbox_batch()[0]["attempts"] == 0


def test_temporal_projection_uses_parent_buckets_and_prior_session_at_boundary():
    raw = {
        **event(timeframe="M1", minute=0),
        "event_time_utc": "2026-08-21T07:00:00Z",
        "payload_hash": "abc",
        "recorded_at_utc": "2026-08-21T07:00:00.1Z",
        "previous_event_id": None,
    }
    row = graph_row(raw, 1, "utc-research-v1")
    assert row["session"]["name"] == "asia"
    assert [bucket["timeframe"] for bucket in row["buckets"]] == [
        "M1", "M5", "M15", "M30", "H1", "H4", "D1"
    ]
    assert row["buckets"][1]["starts_at"] == "2026-08-21T06:55:00Z"
    assert row["bucket_edges"][0] == {
        "child_id": row["buckets"][0]["id"],
        "parent_id": row["buckets"][1]["id"],
    }


class FakeDriver:
    def __init__(self):
        self.calls = []

    def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return [], None, None

    def close(self):
        pass


def test_client_batches_nodes_then_relationships_without_creating_stub_events():
    driver = FakeDriver()
    graph = Neo4jMarketGraph(driver, "neo4j")
    first = graph_row({
        **event(minute=2), "payload_hash": "hash",
        "recorded_at_utc": "2026-08-21T00:02:01Z",
        "previous_event_id": "XAUUSDr:M1:1",
    }, 1, "utc-research-v1")
    graph.upsert_rows([first])
    assert [call[0] for call in driver.calls] == [
        DELETE_EVENT_BUCKET_EDGES, UPSERT_EVENTS, UPSERT_BUCKET_EDGES, UPSERT_NEXT_EDGES
    ]
    assert driver.calls[-1][1]["edges"] == [{
        "previous_id": "XAUUSDr:M1:1", "current_id": "XAUUSDr:M1:2"
    }]


def test_context_query_limits_rows_before_collecting_them():
    assert CONTEXT_QUERY.index("LIMIT $per_timeframe") < CONTEXT_QUERY.index("RETURN collect(")


def test_qwen_decision_event_is_compact_deduplicated_and_episode_linked(tmp_path, monkeypatch):
    store = IntelligenceStore(tmp_path / "memory.sqlite3", busy_timeout_ms=10)
    monkeypatch.setattr(decision_events, "_store", store)
    monkeypatch.delenv("QWEN_DISABLE_FILE_LOGGING", raising=False)
    record = {
        "recorded_at_utc": "2026-08-21T10:15:00Z",
        "decision_type": "entry",
        "symbol": "EURUSD",
        "price": 1.17,
        "proposal_id": "paper-eurusd-1",
        "model": "qwen-test",
        "prompt_text": "large prompt remains outside graph",
        "raw_response": '{"bias":"buy"}',
        "parsed": {
            "bias": "buy", "confidence": 72, "summary": "Confirmed response.",
            "evidence_ids": ["candle-1", "candle-1", "candle-2"],
            "execution_plan": {"signal_timeframe": "M5"},
        },
    }
    assert decision_events.append_decision_event(record)
    stored = store.events("EURUSD", "M5", 5)[0]
    assert stored["event_type"] == "qwen_decision"
    assert stored["payload"]["episode_id"] == "paper-eurusd-1"
    assert stored["payload"]["evidence_ids"] == ["candle-1", "candle-2"]
    assert "prompt_text" not in stored["payload"]
    row = graph_row(store.graph_outbox_batch()[0], 1, "utc-research-v1")
    assert row["episode_id"] == "paper-eurusd-1"
    assert row["used_evidence_ids"] == ["candle-1", "candle-2"]


def test_execution_lifecycle_event_closes_episode_without_path_samples(tmp_path, monkeypatch):
    store = IntelligenceStore(tmp_path / "memory.sqlite3", busy_timeout_ms=10)
    monkeypatch.setattr(execution_events, "_store", store)
    monkeypatch.delenv("QWEN_DISABLE_FILE_LOGGING", raising=False)
    close = {
        "event": "mt5_execution_closed",
        "execution_id": "demo-1",
        "proposal_id": "paper-1",
        "symbol": "GBPUSD",
        "created_at_utc": "2026-08-21T11:00:00Z",
        "reason": "managed_or_safety_tp",
        "exit_price": 1.35,
        "net_pnl": 42.0,
        "peak_favorable_price_move": 0.003,
        "adverse_price_move": 0.001,
        "position_holding_seconds": 180,
    }
    assert execution_events.append_execution_event(close)
    assert not execution_events.append_execution_event({**close, "event": "mt5_execution_monitor"})
    row = graph_row(store.graph_outbox_batch()[0], 1, "utc-research-v1")
    assert row["episode_id"] == "paper-1"
    assert row["episode_status"] == "closed"
    assert row["facts"]["net_pnl"] == 42.0
