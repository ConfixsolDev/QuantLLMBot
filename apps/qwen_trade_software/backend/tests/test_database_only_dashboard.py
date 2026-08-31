from __future__ import annotations

import json

import pytest

from review_shared import read_json_safe, write_json_atomic


def test_database_only_mode_never_reads_stale_json(tmp_path, monkeypatch):
    path = tmp_path / "dashboard-state.json"
    path.write_text(json.dumps({"stale": True}), encoding="utf-8")
    monkeypatch.setenv("QWEN_WEB_DB_ONLY", "1")
    assert read_json_safe(path, {"stale": False}) == {"stale": False}


def test_database_only_mode_rejects_file_write_when_database_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_WEB_DB_ONLY", "1")
    with pytest.raises(RuntimeError, match="database-only mode"):
        write_json_atomic(tmp_path / "dashboard-state.json", {"state": "new"})
