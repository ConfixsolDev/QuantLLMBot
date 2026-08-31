"""2026-08-28: latest_entry_context() must retry a manifest/object race
before reporting cache_provenance_invalid.

The cache writer commits objects immediately before its readiness manifest.
A reader landing between those two commits sees new objects against the
preceding manifest and reports a false epoch mismatch. This was previously a
single re-read; under concurrent readers it was not always enough, and
cache_provenance_invalid was the single largest "wait" cause across eight
days of proposal logs. These tests prove the bounded retry actually
converges on a self-consistent snapshot, and still blocks a real mismatch.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import market_context_cache as mcc  # noqa: E402


NAMES = ("structural", "levels", "session", "playbooks", "minute")


def _manifest(epochs: dict) -> dict:
    return {
        "status": "ready",
        "compatible_epochs": dict(epochs),
        "validated_at_utc": "2026-08-28T00:00:00+00:00",
        "model": {"digest": "test-digest"},
    }


def _objects(epochs: dict) -> dict:
    return {
        name: {
            "cache_epoch": epochs[name],
            "payload": {"levels": [], "playbooks": [], "timeframe_location": {}},
        }
        for name in NAMES
    }


def _make_cache() -> mcc.MarketContextCache:
    tmp = Path(tempfile.mkdtemp()) / "test_cache.sqlite3"
    return mcc.MarketContextCache(tmp)


def test_epoch_mismatch_resolves_on_a_later_attempt(monkeypatch):
    """Simulate a writer that finishes committing between attempt 1 and 2:
    the manifest lags on the first read, catches up on the second. This
    must NOT report cache_provenance_invalid."""
    cache = _make_cache()
    try:
        stale_epochs = {name: "epoch-old" for name in NAMES}
        fresh_epochs = {name: "epoch-new" for name in NAMES}

        calls = {"manifest": 0}

        def fake_latest_manifest(symbol):
            calls["manifest"] += 1
            # First call (outside the loop) and the loop's first attempt see
            # the stale manifest; from the second loop attempt on, the
            # writer has finished and the manifest caught up.
            if calls["manifest"] <= 2:
                return _manifest(stale_epochs)
            return _manifest(fresh_epochs)

        def fake_object(cache_type, symbol):
            # Objects always reflect the fresh write -- exactly the race:
            # objects commit before the manifest does.
            return _objects(fresh_epochs)[cache_type]

        monkeypatch.setattr(cache, "latest_manifest", fake_latest_manifest)
        monkeypatch.setattr(cache, "object", fake_object)
        monkeypatch.setattr(mcc, "MarketContextCache", lambda path: cache)

        result = mcc.latest_entry_context("XAUUSDr", path=cache.path)
        assert result["status"] == "ready", result
    finally:
        cache.close()


def test_genuine_mismatch_still_blocks_after_every_attempt(monkeypatch):
    """A real mismatch (not a timing artifact) must still be reported --
    the retry must not weaken the actual validation."""
    cache = _make_cache()
    try:
        manifest_epochs = {name: "epoch-A" for name in NAMES}
        object_epochs = {name: "epoch-B" for name in NAMES}  # never matches

        monkeypatch.setattr(
            cache, "latest_manifest", lambda symbol: _manifest(manifest_epochs)
        )
        monkeypatch.setattr(
            cache, "object", lambda cache_type, symbol: _objects(object_epochs)[cache_type]
        )
        monkeypatch.setattr(mcc, "MarketContextCache", lambda path: cache)

        result = mcc.latest_entry_context("XAUUSDr", path=cache.path)
        assert result["status"] == "blocked"
        assert result["reason"] == "cache_provenance_invalid"
        assert len(result["failures"]) == len(NAMES)
    finally:
        cache.close()
