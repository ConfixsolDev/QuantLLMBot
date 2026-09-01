import json

from vnext.llm.client import (
    QwenClient,
    arbitration_response_schema,
    build_arbitration_prompt,
    request_arbitration,
)
from vnext.llm.gateway import StrategyQwenGateway
from vnext.strategy.contracts import StrategyDefinition, TradeCandidate
from vnext.market.state import PairMarketState
from vnext.platform.time_frontier import TimeFrontier


class Response:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.body


def state():
    return PairMarketState("XAUUSD", TimeFrontier.from_value("2026-01-01T00:00:00Z").as_of_utc, {}, {})


def candidate():
    definition = StrategyDefinition("XAUUSD", "S1", "1", 1, "SCALP")
    return TradeCandidate("c1", "XAUUSD", definition, "buy", "reclaim", "z1", "z1-low", ("z2",),
                          "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00", state().state_hash,
                          metadata={"qwen_feedback": {"schema_version": "S1_QWEN_V1", "focus": {
                              "context_timeframes": (), "setup_timeframes": (), "execution_timeframes": (),
                              "excluded_timeframes": (), "focus_tags": ()}}})


def story():
    return {"schema_version": "STORY_V1", "pair": "XAUUSD",
            "request": {"context_timeframes": (), "setup_timeframes": (), "execution_timeframes": (),
                        "excluded_timeframes": (), "focus_tags": ()},
            "facts": {"timeframes": {}}}


def test_qwen_client_parses_strict_json_and_prompt_cites_hash():
    def opener(req, timeout):
        body = json.loads(req.data)
        assert body["format"]["properties"]["decision"]["enum"] == ["APPROVE", "WAIT", "VETO", "NO_TRADE"]
        assert body["format"]["additionalProperties"] is False
        assert body["options"]["num_ctx"] == 8192
        return Response(json.dumps({"response": json.dumps({"decision": "APPROVE", "candidate_id": "c1"})}).encode())
    client = QwenClient(opener=opener)
    c, s = candidate(), state()
    result = request_arbitration(client, s, c, story())
    assert result.decision == "APPROVE"
    assert s.state_hash in build_arbitration_prompt(s, c, story())


def test_prompt_contains_exact_output_contract():
    packet = json.loads(build_arbitration_prompt(state(), candidate(), story()))
    assert packet["output_contract"]["candidate_id"] == "c1"
    assert "decision" in packet["output_contract"]
    assert packet["strategy_package"]["feedback"]["schema_version"] == "S1_QWEN_V1"


def test_response_schema_binds_exact_candidate_identity():
    schema = arbitration_response_schema(candidate())
    assert schema["properties"]["candidate_id"]["const"] == "c1"
    assert schema["properties"]["state_hash"]["const"] == candidate().state_hash


def test_strategy_packet_rejects_shared_or_excluded_timeframes():
    invalid_story = story()
    invalid_story["facts"]["timeframes"] = {"M5": []}
    feedback = dict(candidate().metadata["qwen_feedback"])
    feedback["focus"] = {**feedback["focus"], "excluded_timeframes": ("M5",)}
    invalid_story["request"]["excluded_timeframes"] = ("M5",)
    invalid_candidate = TradeCandidate("c2", "XAUUSD", candidate().strategy, "buy", "reclaim", "z1", "z1-low", ("z2",),
                                       "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00", state().state_hash,
                                       metadata={"qwen_feedback": feedback})
    try:
        build_arbitration_prompt(state(), invalid_candidate, invalid_story)
    except ValueError as exc:
        assert "excluded timeframe" in str(exc)
    else:
        raise AssertionError("strategy-excluded facts must not reach Qwen")


def test_qwen_transport_failure_is_no_trade():
    def opener(*args, **kwargs): raise OSError("offline")
    result = request_arbitration(QwenClient(opener=opener), state(), candidate(), story())
    assert result.decision == "NO_TRADE"


def test_invalid_json_reports_only_a_bounded_preview():
    raw = "not-json-" + ("x" * 500)
    client = QwenClient(opener=lambda *args, **kwargs: Response(
        json.dumps({"response": raw}).encode()))
    result = request_arbitration(client, state(), candidate(), story())
    assert result.decision == "NO_TRADE"
    assert "length=509, head='not-json-" in result.reason
    assert "tail='" in result.reason
    assert len(result.reason) < 360


def test_strategy_gateway_is_the_shared_arbitration_boundary():
    calls = []

    class FakeClient:
        def generate(self, prompt, *, response_schema=None):
            calls.append(prompt)
            assert response_schema["properties"]["candidate_id"]["const"] == "c1"
            return {"decision": "WAIT", "state_hash": state().state_hash}

    result = StrategyQwenGateway(FakeClient()).arbitrate(state(), candidate(), story())
    assert result.decision == "WAIT"
    assert len(calls) == 1
    assert "c1" in calls[0]
