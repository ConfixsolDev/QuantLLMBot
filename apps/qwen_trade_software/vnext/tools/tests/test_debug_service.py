from datetime import datetime, timezone

from vnext.market.state import PairMarketState
from vnext.runtime.service import ServiceResult
from vnext.tools.run_debug_service import diagnostic_payload


def test_diagnostic_payload_is_explicitly_non_ordering():
    state = PairMarketState("XAUUSDr", datetime(2026, 1, 1, tzinfo=timezone.utc),
                            {"completed_bars": 300}, {"M1": []})
    payload = diagnostic_payload(ServiceResult(state, None, None), cycle_number=1, model="qwen-test")
    assert payload["mode"] == "DEBUG_NO_ORDERS"
    assert payload["execution_enabled"] is False
    assert payload["order_submitted"] is False
    assert payload["candidate_blockers"] == ["strategy_evidence_missing"]
    assert payload["story_schema"] is None
    assert payload["story_timeframes"] == []
    assert payload["strategy_feedback_schema"] is None
