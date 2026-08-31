"""Select the configured durable intelligence store."""

from __future__ import annotations

from pathlib import Path

from storage_config import StorageConfig


def create_intelligence_store(db_path: Path | str):
    config = StorageConfig.from_env()
    if config.backend == "timescale":
        if not config.timescale_dsn:
            raise RuntimeError("QWEN_TIMESCALE_DSN is required when TimescaleDB is enabled")
        from timescale_store import TimescaleIntelligenceStore
        return TimescaleIntelligenceStore(config.timescale_dsn)
    # Import lazily: market_intelligence.__init__ imports the service, and the
    # service imports this factory. A module-level SQLite import creates a
    # circular import when workers start under the Timescale configuration.
    from market_intelligence.store import IntelligenceStore
    return IntelligenceStore(db_path)
