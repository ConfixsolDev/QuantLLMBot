"""One place that decides which log file a process writes to.

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


def configure(log_path: Path, owner: str, level: int = logging.INFO) -> logging.Handler:
    """Point this process's root logger at `log_path`, replacing any previous.

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

    handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_path, when="midnight", encoding="utf-8"
    )
    handler.suffix = "%Y-%m-%d"
    handler.setFormatter(logging.Formatter(FORMAT))

    logging.basicConfig(level=level, handlers=[handler], force=True)
    OWNER = owner
    return handler
