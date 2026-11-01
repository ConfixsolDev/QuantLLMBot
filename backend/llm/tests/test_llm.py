"""LLM package tests: answer contract, JSON schema, llama-server / OpenAI / Ollama dialects (no server needed)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llm.client import LLMClient, LLMError, LLMSettings, load_settings  # noqa: E402
from llm.contract import answer_schema, check  # noqa: E402
from llm.decider import LLMDecider, take_all  # noqa: E402

P = SimpleNamespace(candidate_map={"C1": "Vabc:2", "C2": "Vdef:1"}, evidence_map={"E1": "ev1", "E2": "ev2"},
                    system="sys", user="{}")
S = SimpleNamespace(rules={"min_confidence": 51})


def test_valid_take_and_wait():
    v = check('{"decision":"C2","confidence":70,"cites":["E1","E2"],"why":"2nd test"}', P, 51)
    assert v.action == "take" and v.candidate_key == "Vdef:1" and v.cited_events == ("ev1", "ev2")
    w = check('```json\n{"decision":"wait","confidence":20,"cites":[],"why":"mixed"}\n```', P, 51)
    assert w.action == "wait" and not w.errors


def test_contract_violations_never_trade():
    bad = [
        ('not json at all', "not a JSON object"),
        ('{"decision":"C9","confidence":80,"cites":["E1"]}', "not a candidate"),
        ('{"decision":"C1","confidence":40,"cites":["E1"]}', "< 51"),
        ('{"decision":"C1","confidence":80,"cites":[]}', "at least one citation"),
        ('{"decision":"C1","confidence":80,"cites":["E7"]}', "unknown evidence"),
        ('{"decision":"C1","confidence":"high","cites":["E1"]}', "not a number"),
        ('{"decision":"buy at 2001","confidence":90,"cites":["E1"]}', "not a candidate"),
    ]
    for text, err in bad:
        v = check(text, P, 51)
        assert v.action == "invalid" and any(err in e for e in v.errors), (text, v.errors)


def test_candidate_facts_are_citable():
    v = check('{"decision":"C1","confidence":60,"cites":["C1.rejection","E2"],"why":"clean rejection"}', P, 51)
    assert v.action == "take" and v.cited_events == ("ev2",)
    assert check('{"decision":"C1","confidence":60,"cites":["C7.rejection"]}', P, 51).action == "invalid"


def test_answer_schema_only_allows_this_prompts_ids():
    sch = answer_schema(P)
    assert sch["properties"]["decision"]["enum"] == ["C1", "C2", "wait"]
    cites = sch["properties"]["cites"]["items"]["enum"]
    assert "E1" in cites and "C2.rejection" in cites and "E9" not in cites
    assert sch["required"] == ["decision", "confidence", "cites", "why"] and sch["additionalProperties"] is False


def test_llama_server_request_is_tailored_to_bonsai():
    seen = {}

    def post(url, body, timeout):
        seen["url"], seen["body"] = url, body
        return {"model": "bonsai", "choices": [{"message": {"content": '{"decision":"wait"}',
                                                            "reasoning_content": ""}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1500, "completion_tokens": 30}}

    def get(url, timeout):
        return {"model_path": "C:\\models\\Ternary-Bonsai-2-27B-PTQ1_0.gguf", "build_info": "b10772-e8fd209"}
    c = LLMClient(LLMSettings(), transport=post, getter=get)
    r = c.ask("system text", "user text", answer_schema(P))
    b = seen["body"]
    assert seen["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert b["reasoning_effort"] == "none" and b["top_k"] == 20 and b["presence_penalty"] == 1.5
    assert b["messages"][0]["role"] == "system" and len([m for m in b["messages"] if m["role"] == "system"]) == 1
    assert b["response_format"]["type"] == "json_schema"
    assert b["response_format"]["json_schema"]["schema"]["properties"]["decision"]["enum"] == ["C1", "C2", "wait"]
    assert r.prompt_tokens == 1500 and r.model_digest == "Ternary-Bonsai-2-27B-PTQ1_0.gguf @ b10772-e8fd209"


def test_thinking_out_of_budget_is_an_error_not_an_empty_trade():
    def post(url, body, timeout):
        return {"choices": [{"message": {"content": "", "reasoning_content": "hmm " * 500},
                             "finish_reason": "length"}]}
    c = LLMClient(LLMSettings(), transport=post, getter=lambda u, t: {})
    with pytest.raises(LLMError, match="without answering"):
        c.ask("s", "u")
    d = LLMDecider(c)(P, S)
    assert d.verdict.action == "invalid" and "without answering" in d.verdict.errors[0]


def test_settings_guard_bonsai_reasoning_pitfalls(tmp_path):
    f = tmp_path / "llm.json"
    f.write_text(json.dumps({"reasoning_effort": "high"}))
    with pytest.raises(ValueError, match="HTTP 500"):
        load_settings(f)
    f.write_text(json.dumps({"reasoning_effort": "medium", "max_tokens": 512}))
    with pytest.raises(ValueError, match="max_tokens"):
        load_settings(f)
    f.write_text(json.dumps({"reasoning_effort": "medium", "max_tokens": 16384}))
    assert load_settings(f).reasoning_effort == "medium"


def test_openai_and_ollama_dialects_still_work():
    seen = {}

    def openai(url, body, timeout):
        seen["url"], seen["body"] = url, body
        return {"model": "x", "choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 5}}
    r = LLMClient(LLMSettings(api="openai", url="http://h:1"), transport=openai, getter=lambda u, t: {}).ask("s", "u")
    assert seen["url"] == "http://h:1/v1/chat/completions" and "reasoning_effort" not in seen["body"]
    assert r.prompt_tokens == 5

    def ollama(url, body, timeout):
        seen["url"], seen["body"] = url, body
        return {"message": {"content": '{"decision":"wait"}'}, "prompt_eval_count": 9}
    r2 = LLMClient(LLMSettings(api="ollama", url="http://h:2"), transport=ollama,
                   getter=lambda u, t: {"models": []}).ask("s", "u", answer_schema(P))
    assert seen["url"] == "http://h:2/api/chat" and seen["body"]["format"]["type"] == "object"
    assert r2.prompt_tokens == 9


def test_decider_never_raises_and_take_all():
    def down(url, body, timeout):
        raise LLMError("connection refused")
    d = LLMDecider(LLMClient(LLMSettings(), transport=down, getter=lambda u, t: {}))(P, S)
    assert d.verdict.action == "invalid" and "unreachable" in d.verdict.errors[0]

    def good(url, body, timeout):
        return {"choices": [{"message": {"content": '{"decision":"C1","confidence":66,"cites":["E2"],"why":"ok"}'}}]}
    d2 = LLMDecider(LLMClient(LLMSettings(), transport=good, getter=lambda u, t: {}))(P, S)
    assert d2.verdict.action == "take" and d2.verdict.candidate_key == "Vabc:2"
    assert take_all(P, S).verdict.candidate_key == "Vabc:2"


def test_bench_runs_a_dataset_through_the_model_and_scores_it(tmp_path):
    from llm.__main__ import _bench
    from strategy.dataset import build
    from structure_engine.verification.synthetic import random_walk_m1
    bars = random_walk_m1(4, 8 * 1440)
    build(iter(bars), tmp_path, start=bars[0].time + 2 * 86400, end=None)
    sent = []

    def post(url, body, timeout):
        sent.append(body)
        return {"choices": [{"message": {"content": json.dumps(
            {"decision": "C1", "confidence": 70, "cites": ["C1.rejection"], "why": "test"})}}],
                "usage": {"prompt_tokens": 1600, "completion_tokens": 40}}
    client = LLMClient(LLMSettings(), transport=post, getter=lambda u, t: {})
    res = _bench(client, tmp_path, 5, tmp_path / "out.jsonl", 51)
    assert res["valid_pct"] == 100.0 and res["take_pct"] == 100.0 and res["prompts"] == len(sent) > 0
    assert res["avg_r_taken"] is not None and (tmp_path / "out.jsonl").exists()
    system = (tmp_path / "system.txt").read_text(encoding="utf-8")
    assert sent[0]["messages"][0]["content"] == system                   # exactly the live system message
