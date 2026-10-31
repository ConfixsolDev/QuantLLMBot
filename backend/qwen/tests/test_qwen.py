"""Qwen package tests: the answer contract and both server dialects (no server needed)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from qwen.client import QwenClient, QwenError, QwenSettings  # noqa: E402
from qwen.contract import check  # noqa: E402
from qwen.decider import QwenDecider, take_all  # noqa: E402

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


def test_ollama_and_openai_dialects():
    seen = {}

    def ollama(url, body, timeout):
        seen["url"], seen["body"] = url, body
        return {"model": "qwen2.5:14b", "message": {"content": '{"decision":"wait"}'},
                "prompt_eval_count": 900, "eval_count": 20}
    c = QwenClient(QwenSettings(api="ollama", url="http://h:1"), transport=ollama)
    c._digest = "sha256:abc"
    r = c.ask("system text", "user text")
    assert seen["url"] == "http://h:1/api/chat" and seen["body"]["format"] == "json"
    assert seen["body"]["options"]["temperature"] == 0 and seen["body"]["messages"][0]["role"] == "system"
    assert r.text == '{"decision":"wait"}' and r.prompt_tokens == 900 and r.model_digest == "sha256:abc"

    def openai(url, body, timeout):
        seen["url"] = url
        return {"model": "qwen", "choices": [{"message": {"content": "{}"}}], "usage": {"prompt_tokens": 5}}
    r2 = QwenClient(QwenSettings(api="openai", url="http://h:2"), transport=openai).ask("s", "u")
    assert seen["url"] == "http://h:2/v1/chat/completions" and r2.prompt_tokens == 5


def test_decider_never_raises():
    def down(url, body, timeout):
        raise QwenError("connection refused")
    d = QwenDecider(QwenClient(QwenSettings(), transport=down))(P, S)
    assert d.verdict.action == "invalid" and "unreachable" in d.verdict.errors[0]

    def good(url, body, timeout):
        return {"message": {"content": '{"decision":"C1","confidence":66,"cites":["E2"],"why":"ok"}'}}
    client = QwenClient(QwenSettings(), transport=good)
    client._digest = "d"
    d2 = QwenDecider(client)(P, S)
    assert d2.verdict.action == "take" and d2.verdict.candidate_key == "Vabc:2"
    assert take_all(P, S).verdict.candidate_key == "Vabc:2"


def test_candidate_facts_are_citable():
    v = check('{"decision":"C1","confidence":60,"cites":["C1.rejection","E2"],"why":"clean rejection"}', P, 51)
    assert v.action == "take" and v.cites == ("C1.rejection", "E2") and v.cited_events == ("ev2",)
    assert check('{"decision":"C1","confidence":60,"cites":["C7.rejection"]}', P, 51).action == "invalid"
