from __future__ import annotations

import pytest

from storage_config import StorageConfig


def test_timescale_activation_requires_dsn():
    config = StorageConfig("timescale", None, None, 120, False)
    with pytest.raises(RuntimeError, match="QWEN_TIMESCALE_DSN"):
        config.validate_activation()


def test_sqlite_activation_does_not_require_external_services():
    result = StorageConfig("sqlite", None, None, 120, False).validate_activation()
    assert result["backend"] == "sqlite"
