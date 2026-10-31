"""Application settings: database connection, API port, history windows.

Where values come from (later wins):
1. Defaults below.
2. ``backend/config/app.json`` (optional; copy ``app.example.json``).
3. Environment variables:
   ``QUANTLLM_DB_DSN`` (or the existing ``QWEN_TIMESCALE_DSN``) — PostgreSQL /
   TimescaleDB connection string, e.g.
   ``postgresql://user:password@127.0.0.1:5432/quantllm``. Required.
   ``QUANTLLM_DB_SCHEMA`` — schema for this application (default ``structure``;
   the old ``fallback_positive`` schema is never touched).

MT5 properties (terminal, account, broker symbol, broker clock) are NOT here:
they live in ``config/mt5_connection.json`` (see mt5_connection.py).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, fields, replace
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CONFIG_FILE = BACKEND / "config" / "app.json"


@dataclass(frozen=True)
class Settings:
    db_dsn: str = ""
    db_schema: str = "structure"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    # On start: fetch missing M1 history from MT5 back to this many days.
    history_days: int = 365
    # On start: rebuild structure by replaying this many days of stored M1
    # bars through the engine (more days = more context, slower start).
    replay_days: int = 60
    poll_seconds: float = 2.0
    keep_bars_per_tf: int = 3000         # closed candles kept in memory per timeframe
    keep_events: int = 80000             # recent events kept in memory for the chart


def load_settings(path: Path | None = None) -> Settings:
    s = Settings()
    path = CONFIG_FILE if path is None else Path(path)
    if path.exists():
        raw = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        unknown = set(raw) - {f.name for f in fields(Settings)} - {"db_dsn"}
        if unknown:
            raise ValueError(f"{path}: unknown setting(s) {sorted(unknown)}")
        if "db_dsn" in raw:
            raise ValueError("Put the database connection in the QUANTLLM_DB_DSN environment variable, not app.json")
        s = replace(s, **raw)
    dsn = os.environ.get("QUANTLLM_DB_DSN") or os.environ.get("QWEN_TIMESCALE_DSN") or ""
    s = replace(s, db_dsn=dsn.strip(), db_schema=os.environ.get("QUANTLLM_DB_SCHEMA", s.db_schema))
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", s.db_schema):
        raise ValueError(f"invalid schema name {s.db_schema!r}")
    return s
