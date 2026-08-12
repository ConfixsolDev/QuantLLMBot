"""The model must run on the GPU, and the system must say so when it does not.

2026-08-12 -- the incident
--------------------------
The Ollama payload carried no placement option, so Ollama chose. When VRAM was
unavailable it fell back to CPU silently and the system carried on:

    entry decision latency on GPU    13-33s
    entry decision latency on CPU    190-455s
    proposal TTL                     60s

Every answer arrived after the proposal it belonged to had expired. 106
proposals produced 4 fills, with no error anywhere in the log. Correct work,
delivered too late to use -- which reads as "quiet day" rather than "broken".
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def _resident(size_gb=9.0, vram_gb=9.0, name="qwen-trading-v004:latest"):
    return {"models": [{"name": name, "size": size_gb * 1e9,
                        "size_vram": vram_gb * 1e9}]}


@pytest.fixture
def rs(monkeypatch):
    import review_shared
    return review_shared


def _fake_ps(rs, monkeypatch, payload):
    import json as _json
    import io

    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return _json.dumps(payload).encode()

    monkeypatch.setattr(rs.urllib.request, "urlopen", lambda *a, **k: R())


def test_payload_asks_for_every_layer_on_gpu():
    """The fix that stops the silent fallback: ask, explicitly, every call."""
    source = (BACKEND / "review_shared.py").read_text(encoding="utf-8")
    start = source.index("def _ollama_generate_raw")
    body = source[start:start + 1400]
    assert '"num_gpu": FORCE_GPU_LAYERS' in body, (
        "the generate payload must request GPU placement; without it Ollama "
        "decides and can fall back to CPU without saying anything"
    )


def test_full_vram_load_reads_as_gpu(rs, monkeypatch):
    _fake_ps(rs, monkeypatch, _resident(9.0, 9.0))
    assert rs.gpu_residency()["state"] == "gpu"


def test_zero_vram_reads_as_cpu(rs, monkeypatch):
    _fake_ps(rs, monkeypatch, _resident(9.0, 0.0))
    assert rs.gpu_residency()["state"] == "cpu"


def test_partial_offload_reads_as_mixed(rs, monkeypatch):
    """Half on the card is not 'on the GPU'. It still misses the deadline."""
    _fake_ps(rs, monkeypatch, _resident(9.0, 4.0))
    assert rs.gpu_residency()["state"] == "mixed"


def test_absent_model_reads_as_unloaded(rs, monkeypatch):
    _fake_ps(rs, monkeypatch, {"models": []})
    assert rs.gpu_residency()["state"] == "unloaded"


def test_probe_failure_never_raises(rs, monkeypatch):
    """A residency probe must not be able to stop trading."""
    def boom(*a, **k):
        raise OSError("ollama unreachable")
    monkeypatch.setattr(rs.urllib.request, "urlopen", boom)
    assert rs.gpu_residency()["state"] == "unknown"


# --- the gate -------------------------------------------------------------

def _reviewer(monkeypatch):
    import reviewer
    reviewer._GPU_GATE_STATE.update({"checked_at": 0.0, "ok": True, "alarmed_at": 0.0})
    return reviewer


def test_entry_is_skipped_on_cpu(monkeypatch):
    """A late entry is worthless: the proposal has expired and price moved."""
    rv = _reviewer(monkeypatch)
    monkeypatch.setattr(rv, "REQUIRE_GPU", True)
    monkeypatch.setattr(rv, "gpu_residency",
                        lambda: {"state": "cpu", "vram_share": 0.0, "detail": "x"})
    assert rv.gpu_ready_for_entry() is False


def test_entry_runs_on_gpu(monkeypatch):
    rv = _reviewer(monkeypatch)
    monkeypatch.setattr(rv, "REQUIRE_GPU", True)
    monkeypatch.setattr(rv, "gpu_residency",
                        lambda: {"state": "gpu", "vram_share": 1.0, "detail": "x"})
    assert rv.gpu_ready_for_entry() is True


def test_gate_fails_open_when_the_probe_cannot_answer(monkeypatch):
    """Refusing to trade because a diagnostic endpoint timed out would be a
    worse failure than the one being guarded against."""
    rv = _reviewer(monkeypatch)
    monkeypatch.setattr(rv, "REQUIRE_GPU", True)
    for state in ("unknown", "unloaded"):
        rv._GPU_GATE_STATE["checked_at"] = 0.0
        monkeypatch.setattr(rv, "gpu_residency",
                            lambda s=state: {"state": s, "vram_share": None, "detail": ""})
        assert rv.gpu_ready_for_entry() is True, state


def test_the_override_exists_and_works(monkeypatch):
    rv = _reviewer(monkeypatch)
    monkeypatch.setattr(rv, "REQUIRE_GPU", False)
    monkeypatch.setattr(rv, "gpu_residency",
                        lambda: {"state": "cpu", "vram_share": 0.0, "detail": "x"})
    assert rv.gpu_ready_for_entry() is True


def test_management_is_never_gated_on_placement():
    """Management looks after money already at risk.

    Blocking it because inference is slow would turn a performance problem into
    an unprotected position. It reports placement and carries on -- and the
    deterministic guard can act without the model at all.
    """
    source = (BACKEND / "trade_management.py").read_text(encoding="utf-8")
    assert "require_gpu(" in source, "management should report placement"
    assert "gpu_ready_for_entry" not in source, (
        "management must never gate its cycle on GPU placement"
    )


def test_the_quoted_ttl_matches_the_real_one():
    """reviewer duplicates the TTL for its alarm text rather than importing it.

    A deliberate duplication needs a guard, or the alarm quietly starts quoting
    a number that stopped being true -- which is exactly the kind of misleading
    log line this whole batch has been removing.
    """
    import ast

    def const(module: str, name: str):
        tree = ast.parse((BACKEND / module).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == name:
                        return ast.literal_eval(node.value)
        raise AssertionError(f"{name} not found in {module}")

    assert const("reviewer.py", "PROPOSAL_TTL_SECONDS_FOR_ALARM") == \
           const("paper_runner.py", "MAX_PROPOSAL_AGE_SECONDS"), (
        "the TTL quoted in the GPU alarm has drifted from the real proposal TTL"
    )
