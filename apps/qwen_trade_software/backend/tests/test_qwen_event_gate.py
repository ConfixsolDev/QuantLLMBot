from qwen_event_gate import QwenEventGate, fingerprint


def test_unchanged_state_skips_until_heartbeat(tmp_path):
    gate = QwenEventGate(tmp_path / "gate.json", heartbeat_seconds=120)
    snapshot = {"xau": {"M1": {"epoch": "one"}}}
    call, reason, current = gate.evaluate(snapshot, now=1000)
    assert call and reason == "startup"
    gate.record_call(current, reason, now=1000)
    assert gate.evaluate(snapshot, now=1050)[:2] == (False, "unchanged_state")
    assert gate.evaluate(snapshot, now=1120)[:2] == (True, "safety_heartbeat")


def test_new_completed_candle_epoch_triggers_immediately(tmp_path):
    gate = QwenEventGate(tmp_path / "gate.json", heartbeat_seconds=900)
    before = {"xau": {"M1": {"epoch": "one", "evidence": "M1_1"}}}
    after = {"xau": {"M1": {"epoch": "two", "evidence": "M1_2"}}}
    _, reason, current = gate.evaluate(before, now=1000)
    gate.record_call(current, reason, now=1000)
    assert gate.evaluate(after, now=1001)[:2] == (True, "market_event")


def test_fingerprint_is_order_independent():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
