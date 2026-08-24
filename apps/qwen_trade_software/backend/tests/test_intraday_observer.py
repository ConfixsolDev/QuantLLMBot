from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from intraday_observer.contracts import CONTRACT_VERSION, read_for_trader, write_state
from intraday_observer.deterministic import (
    build_snapshot,
    confirmed_swings,
    structure_state,
    verify_levels,
)
from intraday_observer.scheduler import review_due
from market_graph.client import (
    LINK_INTRADAY_LEVELS,
    UPSERT_BUCKET_EDGES,
    UPSERT_EVENTS,
    UPSERT_INTRADAY_STORIES,
    DELETE_EVENT_BUCKET_EDGES,
    Neo4jMarketGraph,
)
from market_graph.context_compiler import TIMEFRAMES, _intraday_story_block, compile_market_memory
from market_graph.temporal import graph_row
from market_intelligence.decision_events import _intraday_story_event
from market_intelligence.store import IntelligenceStore
from market_intelligence import decision_events
from market_context_cache import MarketContextCache, latest_observer_facts


def _bars(points: list[tuple[float, float]], start: datetime | None = None) -> list[dict]:
    start = start or datetime(2026, 8, 24, tzinfo=timezone.utc)
    rows = []
    for index, (high, low) in enumerate(points):
        opened = start + timedelta(minutes=5 * index)
        rows.append({
            "open": low + 0.4,
            "high": high,
            "low": low,
            "close": high - 0.4,
            "tick_volume": 100 + index,
            "open_time_utc": opened.isoformat().replace("+00:00", "Z"),
            "close_time_utc": (opened + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "evidence_id": f"M5-{index}",
        })
    return rows


def test_observer_facts_do_not_depend_on_entry_qwen_manifest(tmp_path):
    db = tmp_path / "context.sqlite3"
    now = datetime(2026, 8, 24, 10, 5, tzinfo=timezone.utc)
    cache = MarketContextCache(db)
    candle = {
        "symbol": "XAUUSDr", "timeframe": "M5",
        "open_time_utc": "2026-08-24T10:00:00Z",
        "close_time_utc": "2026-08-24T10:05:00Z",
        "open": 3400.0, "high": 3402.0, "low": 3399.0, "close": 3401.0,
        "tick_volume": 100, "spread": 10, "real_volume": 0,
        "source": "test", "evidence_id": "M5-test", "is_complete": True,
    }
    cache.ingest_completed([candle])
    cache.put_object(
        "levels", "XAUUSDr", now, {"levels": [{"level_id": "H1_A"}]},
        source_hash="sha256:levels", evidence_ids=["M5-test"],
    )
    cache.put_object(
        "session", "XAUUSDr", now, {"phase": "london"},
        source_hash="sha256:session", evidence_ids=["M5-test"],
    )
    cache.close()

    facts = latest_observer_facts("XAUUSDr", db, now=now)
    assert facts["status"] == "ready"
    assert facts["levels"][0]["level_id"] == "H1_A"
    assert facts["session"]["phase"] == "london"


def test_confirmed_swings_reconstruct_hh_hl_sequence_from_closed_bars():
    rows = _bars([
        (10, 8), (11, 9), (15, 10), (12, 9), (11, 7),
        (13, 9), (16, 11), (14, 10), (13, 8), (15, 9), (17, 10),
    ])
    swings = confirmed_swings(rows, order=2)
    assert [row["label"] for row in swings] == ["H", "L", "HH", "HL"]
    assert structure_state(swings) == "bullish_sequence"


def test_consecutive_level_touches_count_as_one_market_episode():
    rows = _bars([(101, 99), (100.8, 99.5), (101.1, 99.7), (103, 101.5), (104, 102)])
    level = {
        "level_id": "H1_ZONE_A",
        "timeframe": "H1",
        "role": "resistance",
        "price": 100.0,
        "zone_low": 99.8,
        "zone_high": 100.2,
    }
    result = verify_levels([level], rows, current_price=103.6)[0]
    assert result["touch_episodes_today"] == 1
    assert result["latest_closed_response"] == "accepted_above"
    assert result["current_relation"] == "above"


def test_snapshot_keeps_deterministic_story_separate_from_prior_qwen_view():
    now = datetime(2026, 8, 24, 1, 1, tzinfo=timezone.utc)
    rows = _bars([
        (10, 8), (11, 9), (15, 10), (12, 9), (11, 7),
        (13, 9), (16, 11), (14, 10), (13, 8), (15, 9), (17, 10),
    ])

    def provider(symbol, timeframe, count):
        assert symbol == "XAUUSDr" and timeframe == "M5" and count == 320
        return rows

    snapshot = build_snapshot(
        symbol="XAUUSDr",
        level_rows=[{
            "level_id": "H1_A", "timeframe": "H1", "role": "support",
            "price": 9.0, "zone_low": 8.8, "zone_high": 9.2,
        }],
        bar_provider=provider,
        now=now,
        prior_analysis={"market_story": "Old view"},
    )
    assert snapshot["episode_id"] == "XAUUSDr-20260824T0100Z"
    assert snapshot["structure"]["state"] == "bullish_sequence"
    assert snapshot["prior_qwen_analysis"] == {"market_story": "Old view"}
    assert snapshot["constraints"]["execution_authority"] is False


def test_trader_contract_fails_closed_and_returns_only_bounded_projection(tmp_path):
    path = tmp_path / "observer.json"
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    write_state({
        "contract_version": CONTRACT_VERSION,
        "symbol": "XAUUSDr",
        "generated_at_utc": "2026-08-24T11:45:00Z",
        "deterministic": {
            "episode_id": "XAUUSDr-20260824T1130Z",
            "today_tape": {"open": 3300, "close": 3310},
            "structure": {"sequence": [{"label": "HH"}]},
            "levels": [{"level_id": "H1_A"}],
            "private_internal_field": "not exposed",
        },
        "qwen_analysis": {
            "market_story": "Gold accepted above H1_A.",
            "structure_read": {"state": "bullish"},
            "level_reads": [{"level_id": "H1_A"}],
            "prior_view_review": {"status": "confirmed"},
            "next_focus": "Retest of H1_A.",
        },
    }, path)
    view = read_for_trader("XAUUSDr", now=now, path=path)
    assert view["status"] == "ready"
    assert view["execution_authority"] is False
    assert "private_internal_field" not in view
    assert read_for_trader("EURUSD", now=now, path=path)["reason"] == "symbol_mismatch"
    stale = read_for_trader("XAUUSDr", now=now + timedelta(hours=1), path=path)
    assert stale["status"] == "stale"


def test_review_due_on_half_hour_or_material_fingerprint_change():
    now = datetime(2026, 8, 24, 12, 31, tzinfo=timezone.utc)
    state = {
        "contract_version": CONTRACT_VERSION,
        "generated_at_utc": "2026-08-24T12:20:00Z",
        "deterministic": {"episode_id": "old", "fingerprint": "a"},
    }
    assert review_due({"episode_id": "new", "fingerprint": "a"}, state, now) == (
        True, "half_hour_close"
    )
    state["deterministic"]["episode_id"] = "same"
    assert review_due({"episode_id": "same", "fingerprint": "b"}, state, now) == (
        True, "structure_or_level_event"
    )
    assert review_due({"episode_id": "same", "fingerprint": "b"}, {
        **state, "generated_at_utc": "2026-08-24T12:29:00Z"
    }, now) == (False, "event_cooldown")


def _story_record():
    return {
        "recorded_at_utc": "2026-08-24T12:30:10Z",
        "decision_type": "intraday_observer",
        "symbol": "XAUUSDr",
        "model": "qwen-test",
        "prompt_text": "observer prompt",
        "raw_response": "{}",
        "parsed": {
            "episode_id": "XAUUSDr-20260824T1230Z",
            "market_story": "Gold formed HH then held the HL.",
            "structure_read": {
                "state": "bullish", "sequence_explanation": "HH followed HL.",
                "drivers_so_far": "Accepted above H1_A.",
                "contradicting_evidence": "Resistance remains above.",
            },
            "level_reads": [{
                "level_id": "H1_A", "quality": "clear",
                "price_story": "Accepted and held.", "next_verification": "Retest hold.",
            }],
            "prior_view_review": {"status": "confirmed", "reason": "HL held."},
            "next_focus": "Next resistance.",
        },
        "context": {
            "contract_version": CONTRACT_VERSION,
            "episode_id": "XAUUSDr-20260824T1230Z",
            "fingerprint": "fingerprint-1",
            "trigger": "half_hour_close",
            "observer_snapshot": {
                "today_tape": {
                    "open": 3300, "high": 3320, "low": 3295, "close": 3315,
                    "net_move": 15, "range": 25, "latest_evidence_id": "M5-last",
                },
                "structure": {
                    "state": "bullish_sequence", "method": "closed_pivots",
                    "sequence": [{
                        "label": "HH", "kind": "high", "price": 3320,
                        "time_utc": "2026-08-24T12:00:00Z", "evidence_id": "M5-HH",
                    }],
                },
                "levels": [{
                    "level_id": "H1_A", "timeframe": "H1", "role": "support",
                    "price": 3310, "zone_low": 3309, "zone_high": 3311,
                    "touch_episodes_today": 2, "last_touch_utc": "2026-08-24T12:20:00Z",
                    "latest_closed_response": "rejected_from_above",
                    "current_relation": "above",
                }],
                "notable_closed_moves": [{"evidence_id": "M5-drive"}],
                "session": {"session": "london"},
            },
        },
    }


def test_intraday_story_event_is_replay_safe_and_preserves_graph_memory():
    record = _story_record()
    event = _intraday_story_event(record, record["parsed"], record["context"])
    repeated = _intraday_story_event(record, record["parsed"], record["context"])
    assert event["event_id"] == repeated["event_id"]
    assert event["event_type"] == "intraday_story"
    assert event["payload"]["episode_id"] == "XAUUSDr-20260824T1230Z"
    assert event["payload"]["structure_sequence"][0]["label"] == "HH"
    assert event["payload"]["level_reads"][0]["qwen_quality"] == "clear"
    assert event["payload"]["eligible_for_live_context"] is False


def test_observer_story_flows_through_sqlite_outbox_for_replay(tmp_path):
    record = _story_record()
    store = IntelligenceStore(tmp_path / "memory.sqlite3", busy_timeout_ms=10)
    with patch.object(decision_events, "_store", store), patch.dict(
        "os.environ", {"QWEN_DISABLE_FILE_LOGGING": "0"}
    ):
        assert decision_events.append_decision_event(record)
        assert not decision_events.append_decision_event(record)
    batch = store.graph_outbox_batch()
    assert len(batch) == 1
    assert batch[0]["event_type"] == "intraday_story"
    assert batch[0]["payload"]["structure_sequence"][0]["label"] == "HH"


class _Driver:
    def __init__(self):
        self.calls = []

    def execute_query(self, query, **parameters):
        self.calls.append((query, parameters))
        return [], None, None

    def close(self):
        pass


def test_graph_projects_first_class_story_swings_and_level_reads():
    record = _story_record()
    event = _intraday_story_event(record, record["parsed"], record["context"])
    row = graph_row({
        **event,
        "payload_hash": "hash",
        "recorded_at_utc": record["recorded_at_utc"],
        "previous_event_id": None,
    }, 2, "utc-research-v1")
    assert row["intraday_story"]["swings"][0]["label"] == "HH"
    assert row["intraday_story"]["level_reads"][0]["level_id"] == "H1_A"
    driver = _Driver()
    Neo4jMarketGraph(driver, "neo4j").upsert_rows([row])
    assert [call[0] for call in driver.calls] == [
        DELETE_EVENT_BUCKET_EDGES, UPSERT_EVENTS, UPSERT_INTRADAY_STORIES,
        LINK_INTRADAY_LEVELS, UPSERT_BUCKET_EDGES,
    ]


def test_graph_context_compacts_latest_story_without_promoting_it():
    story = {
        "id": "story-1", "as_of_utc": "2026-08-24T12:30:00Z",
        "state": "bullish", "market_story": "story", "sequence_explanation": "HH HL",
        "drivers_so_far": "accepted", "contradicting_evidence": "resistance",
        "prior_view_status": "confirmed", "next_focus": "retest",
        "deterministic_structure_state": "bullish_sequence",
        "day_open": 3300, "day_high": 3320, "day_low": 3295, "day_close": 3315,
        "day_net_move": 15, "day_range": 25,
        "swings": [{"ordinal": 1, "label": "HH", "price": 3320}],
        "level_reads": [{"level_id": "H1_A", "qwen_quality": "clear"}],
        "mode": "shadow_only", "eligible_for_live_context": False,
    }
    block = _intraday_story_block(
        {"intraday_stories": {"XAUUSDr": [story]}}, "XAUUSDr"
    )
    assert block["status"] == "shadow_ready"
    assert block["stories"][0]["confirmed_swing_sequence"][0]["label"] == "HH"
    assert block["execution_authority"] is False
    assert block["eligible_for_live_context"] is False


def test_connected_graph_without_story_reports_ready_empty():
    block = _intraday_story_block(
        {"intraday_stories": {"XAUUSDr": []}}, "XAUUSDr"
    )
    assert block["status"] == "ready_empty"
    assert block["stories"] == []


def test_story_memory_keeps_complete_graph_packet_inside_context_budget():
    def candle(symbol, timeframe, close):
        return {
            "symbol": symbol, "timeframe": timeframe, "event_type": "candle_closed",
            "event_time": "2026-08-24T12:30:00Z", "evidence_id": f"{symbol}:{timeframe}",
            "open": close - 1, "high": close + 1, "low": close - 2,
            "close": close, "direction": "bullish", "tick_volume": 100,
            "session": {"name": "london", "phase": "development",
                        "starts_at": "2026-08-24T08:00:00Z",
                        "ends_at": "2026-08-24T13:00:00Z"},
        }

    xau = {tf: [candle("XAUUSDr", tf, 3315)] for tf in TIMEFRAMES}
    dxy = {tf: [candle("DXY", tf, 99)] for tf in TIMEFRAMES}
    xau.update({"market_levels": [], "market_structure": [], "structure_evidence": {}})
    dxy.update({"market_levels": [], "market_structure": [], "structure_evidence": {}})
    story = {
        "id": "story-1", "as_of_utc": "2026-08-24T12:30:00Z",
        "state": "bullish", "market_story": "A" * 1000,
        "sequence_explanation": "B" * 1000, "drivers_so_far": "C" * 1000,
        "contradicting_evidence": "D" * 1000, "next_focus": "E" * 1000,
        "swings": [{"ordinal": i, "label": "HH", "price": 3300 + i} for i in range(12)],
        "level_reads": [{
            "level_id": f"L{i}", "qwen_price_story": "F" * 500,
            "next_verification": "G" * 500,
        } for i in range(12)],
        "mode": "shadow_only", "eligible_for_live_context": False,
    }
    packet = compile_market_memory({
        "as_of_utc": "2026-08-24T12:30:10Z",
        "known_as_of_utc": "2026-08-24T12:30:10Z",
        "symbols": {"XAUUSDr": xau, "DXY": dxy},
        "intraday_stories": {"XAUUSDr": [story]},
        "projection": {"pending": 0},
    })
    assert packet["within_packet_budget"] is True
    assert packet["qwen_intraday_story_memory"]["stories"][0]["market_story"] == "A" * 320
    assert len(packet["qwen_intraday_story_memory"]["stories"][0]["verified_level_reads"]) == 4
