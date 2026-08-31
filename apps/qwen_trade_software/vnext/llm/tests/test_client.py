import json

from vnext.llm.client import QwenClient, build_arbitration_prompt, request_arbitration
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
                          "2026-01-01T00:00:00+00:00", "2026-01-01T00:15:00+00:00", state().state_hash)


def test_qwen_client_parses_strict_json_and_prompt_cites_hash():
    def opener(req, timeout):
        body = json.loads(req.data)
        assert body["format"] == "json"
        return Response(json.dumps({"response": json.dumps({"decision": "APPROVE", "candidate_id": "c1"})}).encode())
    client = QwenClient(opener=opener)
    c, s = candidate(), state()
    result = request_arbitration(client, s, c, {"facts": []})
    assert result.decision == "APPROVE"
    assert s.state_hash in build_arbitration_prompt(s, c, {})


def test_qwen_transport_failure_is_no_trade():
    def opener(*args, **kwargs): raise OSError("offline")
    result = request_arbitration(QwenClient(opener=opener), state(), candidate(), {})
    assert result.decision == "NO_TRADE"
