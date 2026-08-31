"""One place that routes process events to durable observability storage.

2026-08-11 -- why this exists
----------------------------
Every long-running module here set up its own rotating handler and called
`logging.basicConfig(handlers=[...])` at import time. That works only for the
module that gets imported first, because `basicConfig` is a no-op once the root
logger already has a handler -- it does not raise, it does not warn, it just
silently does nothing.

`reviewer.py` imports `session_planner` (line 59). So session_planner's handler
claimed the root logger, and reviewer's own `basicConfig` a few hundred lines
later did nothing at all. Every reviewer line -- proposals, confidence, model
responses -- went to session-planner.log for months, and reviewer.log stayed
empty. Nothing looked broken; the records were just filed under the wrong name,
which is worse than missing, because you go looking in the empty file and
conclude nothing happened.

The rule now: the log file belongs to the PROCESS, not to whichever module
Python happened to import first. The entrypoint claims it, explicitly and last,
and `force=True` means claiming actually takes effect. A module that gets
imported by another process contributes its lines to that process's log, which
is what you want when you are reading one process's story top to bottom.
"""

from __future__ import annotations

import logging
import os
import logging.handlers
import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(message)s"

# Set by the test conftest. Importing an entrypoint runs configure() at module
# scope with force=True, which reinstalls the real file handler and defeats any
# handler swap a fixture has already done -- that is how test fixtures wrote
# "ticket 99 ... 1786431741s after fill" into the live trade-management.log.
# The block has to live here, at the point the handler is built.
DISABLE_ENV = "QWEN_DISABLE_FILE_LOGGING"

# Which module currently owns the root logger. Exposed for tests and for
# diagnosing "why is this line in that file" without guessing at import order.
OWNER: str | None = None


class TimescaleRuntimeHandler(logging.Handler):
    """Write ordinary log records to the authoritative runtime event ledger."""

    def __init__(self, owner: str) -> None:
        super().__init__(level=logging.INFO)
        self.owner = owner
        self._store = None
        self._schema_ready = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._store is None:
                from runtime_store import RuntimeStore
                self._store = RuntimeStore()
            if not self._store.enabled:
                return
            if not self._schema_ready:
                self._store.ensure_schema()
                self._schema_ready = True
            rendered = self.format(record)
            event_name = None
            payload = {}
            message = record.getMessage()
            if message.startswith("EVENT "):
                try:
                    payload = json.loads(message[6:])
                    event_name = payload.get("event")
                except (TypeError, ValueError):
                    pass
            self._store.append_event(owner=self.owner, level=record.levelname,
                                     message=rendered, event_name=event_name,
                                     payload=payload)
        except Exception:
            # Logging must never recursively crash a worker. The error-only
            # file handler remains available for diagnosing a DB outage.
            self._schema_ready = False


def structured_event(event: str, *, level: int = logging.INFO, **fields: object) -> None:
    """Write one stable JSON event while retaining the ordinary process log.

    The ``EVENT`` marker makes these records cheap to grep without forcing all
    existing human-readable diagnostics through a disruptive format migration.
    Field ordering is stable so diffs and operational comparisons remain useful.
    """
    payload = {
        "event": str(event),
        "owner": OWNER,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    logging.log(
        level,
        "EVENT %s",
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )


def configure(log_path: Path, owner: str, level: int = logging.INFO) -> logging.Handler:
    """Route logs to Timescale in live mode and retain only error files.

    `force=True` is the whole point: it tears down handlers installed by
    modules imported earlier, so the entrypoint wins regardless of import
    order. Call it from the module that owns the process.
    """
    global OWNER

    if os.environ.get(DISABLE_ENV) == "1":
        handler: logging.Handler = logging.NullHandler()
        logging.basicConfig(level=level, handlers=[handler], force=True)
        OWNER = owner
        return handler

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    live_timescale = bool(os.environ.get("QWEN_TIMESCALE_DSN")) and os.environ.get(
        "QWEN_INTELLIGENCE_BACKEND", "sqlite").strip().lower() == "timescale"
    if live_timescale:
        handler: logging.Handler = TimescaleRuntimeHandler(owner)
        handler.setFormatter(logging.Formatter(FORMAT))
        bug_file = logging.handlers.TimedRotatingFileHandler(
            filename=log_path, when="midnight", encoding="utf-8", delay=True
        )
        bug_file.suffix = "%Y-%m-%d"
        bug_file.setLevel(logging.ERROR)
        bug_file.setFormatter(logging.Formatter(FORMAT))
        handlers = [handler, bug_file]
    else:
        handler = logging.handlers.TimedRotatingFileHandler(
            filename=log_path, when="midnight", encoding="utf-8"
        )
        handler.suffix = "%Y-%m-%d"
        handler.setFormatter(logging.Formatter(FORMAT))
        handlers = [handler]

    logging.basicConfig(level=level, handlers=handlers, force=True)
    OWNER = owner
    return handler
