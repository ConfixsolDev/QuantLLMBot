"""Environment-owned configuration for the optional market graph."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class GraphConfig:
    enabled: bool
    uri: str
    user: str
    password: str
    database: str
    symbols: tuple[str, ...]
    batch_size: int
    interval_seconds: float
    max_attempts: int
    schema_version: int = 3
    session_calendar_version: str = "utc-research-v1"

    @classmethod
    def from_env(cls) -> "GraphConfig":
        primary = os.environ.get("QWEN_PRIMARY_SYMBOL", "XAUUSDr")
        configured = os.environ.get("QWEN_GRAPH_SYMBOLS", f"{primary},DXY")
        symbols = tuple(dict.fromkeys(
            item.strip() for item in configured.split(",") if item.strip()
        ))
        return cls(
            enabled=_enabled(os.environ.get("QWEN_NEO4J_ENABLED")),
            uri=os.environ.get("QWEN_NEO4J_URI", "bolt://127.0.0.1:7687"),
            user=os.environ.get("QWEN_NEO4J_USER", "neo4j"),
            password=os.environ.get("QWEN_NEO4J_PASSWORD", ""),
            database=os.environ.get("QWEN_NEO4J_DATABASE", "neo4j"),
            symbols=symbols or (primary, "DXY"),
            batch_size=max(1, min(int(os.environ.get("QWEN_NEO4J_BATCH_SIZE", "250")), 10000)),
            interval_seconds=max(0.25, float(os.environ.get("QWEN_NEO4J_INTERVAL", "2"))),
            max_attempts=max(1, int(os.environ.get("QWEN_NEO4J_MAX_ATTEMPTS", "8"))),
            schema_version=3,
        )

    def public(self) -> dict:
        return {
            "enabled": self.enabled,
            "uri": self.uri,
            "database": self.database,
            "symbols": list(self.symbols),
            "batch_size": self.batch_size,
            "interval_seconds": self.interval_seconds,
            "schema_version": self.schema_version,
            "session_calendar_version": self.session_calendar_version,
        }


graph_config = GraphConfig.from_env()


def graph_health_path(app_dir: Path) -> Path:
    return app_dir / "cache" / "market-graph-health.json"


def graph_context_path(app_dir: Path) -> Path:
    return app_dir / "cache" / "market-graph-context.json"
