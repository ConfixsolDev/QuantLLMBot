from datetime import datetime, timedelta, timezone

import pytest

from market_graph.context_compiler import TIMEFRAMES, compile_market_memory
from market_graph.rag_protocol import PHASE_BUDGETS, RagRequest, empty_answer
from market_graph.semantic_memory import evaluate_memory


def candle(symbol, timeframe, close, direction="bullish", volume=100):
    return {"symbol": symbol, "timeframe": timeframe, "event_type": "candle_closed",
            "event_time": "2026-08-22T10:00:00Z", "evidence_id": f"{symbol}:{timeframe}",
            "open": close - 1, "high": close + 1, "low": close - 2, "close": close,
            "direction": direction, "tick_volume": volume,
            "session": {"name": "london", "phase": "development",
                        "starts_at": "2026-08-22T08:00:00Z", "ends_at": "2026-08-22T13:00:00Z"}}


def raw_context():
    xau = {tf: [candle("XAUUSDr", tf, 4600)] for tf in TIMEFRAMES}
    dxy = {tf: [candle("DXY", tf, 99, "bearish", 50)] for tf in TIMEFRAMES}
    xau["market_levels"] = [
        {"level_id": "H4_SUPPORT", "timeframe": "H4", "zone_low": 4590, "zone_high": 4592},
        {"level_id": "M15_SUPPORT", "timeframe": "M15", "zone_low": 4590.4, "zone_high": 4591.8},
        {"level_id": "M1_FOCUS", "timeframe": "M1", "zone_low": 4599.5, "zone_high": 4600.5},
        {"level_id": "H1_RESISTANCE", "timeframe": "H1", "zone_low": 4610, "zone_high": 4612},
    ]
    xau["market_structure"] = []
    xau["structure_evidence"] = {}
    dxy.update({"market_levels": [], "market_structure": [], "structure_evidence": {}})
    return {"status": "ready", "as_of_utc": "2026-08-22T10:00:30Z",
            "known_as_of_utc": "2026-08-22T10:00:30Z",
            "symbols": {"XAUUSDr": xau, "DXY": dxy}, "projection": {"pending": 0}}


def test_compiler_is_bounded_neutral_and_preserves_temporal_hierarchy():
    packet = compile_market_memory(raw_context())
    assert packet["execution_authority"] is False
    assert packet["within_packet_budget"] is True
    assert packet["packet_bytes"] < 14_000
    assert [row["timeframe"] for row in packet["xauusd_all_timeframe_temporal_structure"]] == list(TIMEFRAMES)
    assert packet["active_zone_positions"]["current_or_approaching_focus"]["zone_id"].startswith("price-area:")
    assert packet["active_zone_positions"]["nearest_proven_support"]["primary_owning_timeframe"] == "H4"
    assert packet["active_zone_positions"]["nearest_proven_resistance"]["primary_owning_timeframe"] == "H1"
    assert packet["active_zone_plan"]["status"] == "ready"
    assert packet["active_zone_plan"]["execution_authority"] is False
    assert packet["active_zone_plan"]["directional_authority"] is False
    assert "side" not in packet["active_zone_plan"]
    assert "zone" not in packet["active_zone_plan"]
    focus = packet["active_zone_plan"]["focus_zone"]
    assert focus["current_relation"] == "inside"
    assert focus["distance_to_zone"] == 0.0
    assert len(packet["dxy_cross_reference"]["lines"]) == 5


def test_rag_contract_is_allowlisted_neutral_and_phase_bounded():
    request = RagRequest("ZONE_HISTORY", "XAUUSDr", "2026-08-22T10:00:00Z", "zone-1", ("H4", "M15"))
    answer = empty_answer(request)
    assert answer["factual_answer"] == "insufficient_evidence"
    assert answer["execution_authority"] is False
    assert PHASE_BUDGETS == {"CONTEXT_WARMUP": 5, "ZONE_DEFINITION": 4,
                             "TRADE_DECISION": 2, "TRADE_MANAGEMENT": 2}
    with pytest.raises(ValueError):
        empty_answer(RagRequest("WRITE_CYPHER", "XAUUSDr", "2026-08-22T10:00:00Z"))


def test_semantic_memory_retires_on_equal_contradiction_during_probation():
    started = datetime(2026, 8, 20, tzinfo=timezone.utc)
    memory = {"state": "probation", "probation_started_at_utc": started.isoformat(),
              "supporting_episode_ids": ["one-move", "one-move"],
              "contradicting_episode_ids": ["counter-move"]}
    result = evaluate_memory(memory, (started + timedelta(days=2)).isoformat())
    assert result["supporting_episode_count"] == 1
    assert result["contradicting_episode_count"] == 1
    assert result["state"] == "retired"


def test_semantic_memory_becomes_human_locked_after_seven_calendar_days():
    started = datetime(2026, 8, 1, tzinfo=timezone.utc)
    memory = {"state": "probation", "probation_started_at_utc": started.isoformat(),
              "supporting_episode_ids": ["a", "b"], "contradicting_episode_ids": ["c"]}
    result = evaluate_memory(memory, (started + timedelta(days=7)).isoformat())
    assert result["state"] == "established"
    assert result["human_locked"] is True
