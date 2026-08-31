from __future__ import annotations

import pytest

from storage_config import StorageConfig
from tools.storage_acceptance import run


def test_timescale_activation_requires_dsn():
    config = StorageConfig("timescale", None, None, 120, False)
    with pytest.raises(RuntimeError, match="QWEN_TIMESCALE_DSN"):
        config.validate_activation()


def test_sqlite_activation_does_not_require_external_services():
    result = StorageConfig("sqlite", None, None, 120, False).validate_activation()
    assert result["backend"] == "sqlite"


def test_cutover_gate_blocks_partial_sqlite_configuration(tmp_path):
    result = run(tmp_path / "context.sqlite3", tmp_path / "intelligence.sqlite3")
    assert result["status"] == "blocked"
