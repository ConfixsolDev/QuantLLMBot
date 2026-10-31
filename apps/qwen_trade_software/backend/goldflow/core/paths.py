"""Filesystem anchors shared by every goldflow module.

Runtime state, logs, caches and data files live in the backend directory
(``apps/qwen_trade_software/backend``), not next to the module that reads
them. Modules import ``APP_DIR`` from here instead of deriving it from their
own ``__file__``, so moving a module between packages never moves its data.
"""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
PACKAGE_DIR = APP_DIR / "goldflow"


def module_source(module_name: str) -> Path:
    """Return the source file of a goldflow module given its bare name."""
    for path in sorted(PACKAGE_DIR.rglob(f"{module_name}.py")):
        if "__pycache__" not in path.parts:
            return path
    return PACKAGE_DIR / f"{module_name}.py"  # nonexistent: callers report it
