"""Digest-stale cache objects must be flushed so auto-requalify can mint a new certificate."""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_context_cache import (  # noqa: E402
    QUALIFICATION_MODEL_TIMEOUT_SECONDS,
    MarketContextCache,
    QwenContextShadow,
)


def _cache() -> MarketContextCache:
    handle = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    handle.close()
    return MarketContextCache(handle.name, report_metadata_corrections=False)


def _put(cache: MarketContextCache, cache_type: str, digest: str | None, payload: dict):
    return cache.put_object(
        cache_type,
        "XAUUSD",
        datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
        payload,
        source_hash="sha256:test",
        evidence_ids=["candle:XAUUSD:H1:test"],
        model_digest=digest,
    )


def test_flush_drops_old_digest_and_keeps_digestless_rows():
    cache = _cache()
    try:
        _put(cache, "context_qualification", "digest-v004", {"passed": True})
        _put(cache, "playbooks", "digest-v004", {"playbooks": []})
        _put(cache, "levels", None, {"levels": [{"price": 1.0}]})
        dropped = cache.flush_stale_model_objects("XAUUSD", keep_digest="digest-v005")
        assert dropped >= 2
        assert cache.object("context_qualification", "XAUUSD") is None
        assert cache.object("playbooks", "XAUUSD") is None
        kept = cache.object("levels", "XAUUSD")
        assert kept is not None
        assert kept["payload"]["levels"][0]["price"] == 1.0
    finally:
        cache.close()
        Path(cache.path).unlink(missing_ok=True)


def test_heal_overrides_no_qwen_on_digest_mismatch():
    cache = _cache()
    try:
        _put(cache, "context_qualification", "digest-v004", {"passed": True})
        shadow = QwenContextShadow(
            cache,
            SimpleNamespace(symbol="XAUUSD"),
            SimpleNamespace(),
        )
        run_qwen, benchmark = shadow._heal_stale_qualification(
            "digest-v005", run_qwen=False, benchmark_minute=True
        )
        assert run_qwen is True
        assert benchmark is False
        assert cache.object("context_qualification", "XAUUSD") is None
        assert shadow._qualification_stale_reason("digest-v005") == "qualification_missing"
    finally:
        cache.close()
        Path(cache.path).unlink(missing_ok=True)


def test_steady_state_structural_change_never_overrides_no_qwen():
    assert not QwenContextShadow._should_run_warmup(
        gate_a=True, needs_warmup=True, run_qwen=False
    )
    assert QwenContextShadow._should_run_warmup(
        gate_a=True, needs_warmup=True, run_qwen=True
    )
    assert 60 <= QUALIFICATION_MODEL_TIMEOUT_SECONDS <= 300


def test_heal_respects_cooldown_after_failed_cycle():
    cache = _cache()
    try:
        shadow = QwenContextShadow(
            cache,
            SimpleNamespace(symbol="XAUUSD"),
            SimpleNamespace(),
        )
        shadow._auto_requalify_fail_at = shadow._auto_requalify_fail_at or 1.0
        import time

        shadow._auto_requalify_fail_at = time.monotonic()
        run_qwen, _ = shadow._heal_stale_qualification(
            "digest-v005", run_qwen=False, benchmark_minute=False
        )
        assert run_qwen is False
    finally:
        cache.close()
        Path(cache.path).unlink(missing_ok=True)
