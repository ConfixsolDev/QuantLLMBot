"""Shared test guards.

2026-08-11 -- why this exists
----------------------------
A test that exercised the geometry observation path wrote a real
`geometry_observation` record into logs/paper-executions-<today>.jsonl, with a
null proposal_id. That log is evidence: the observation window decides whether
to enforce the geometry gate by joining those records to realised P&L. A
synthetic row from a unit test is a fabricated data point in a decision about
real money.

So: no test may append to the live execution log. A test that wants to inspect
what was written patches `append_event` itself and reads its own list.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- make the Windows-only modules importable off Windows -------------------
# paper_executor and paper_runner import msvcrt (file locking) and MetaTrader5
# at module scope, so neither can be imported on Linux CI without a stand-in.
# setdefault, never overwrite: on Windows the real modules must win, and a test
# that installs its own richer fake via monkeypatch.setitem still overrides
# these for its own duration.

if "msvcrt" not in sys.modules:
    try:
        import msvcrt  # noqa: F401
    except ImportError:
        _msvcrt = types.ModuleType("msvcrt")
        _msvcrt.locking = lambda *a, **k: None
        _msvcrt.LK_NBLCK, _msvcrt.LK_UNLCK = 1, 0
        sys.modules["msvcrt"] = _msvcrt

if "MetaTrader5" not in sys.modules:
    try:
        import MetaTrader5  # noqa: F401
    except ImportError:
        class _StubMT5(types.ModuleType):
            """Enough to import. Any test that exercises MT5 installs its own."""

            def __getattr__(self, name):
                if name.isupper() or name.startswith("TIMEFRAME_"):
                    return 0
                return lambda *a, **k: None

        sys.modules["MetaTrader5"] = _StubMT5("MetaTrader5")


@pytest.fixture(autouse=True)
def never_write_to_the_live_execution_log(monkeypatch):
    try:
        import paper_executor
    except Exception:
        return
    monkeypatch.setattr(
        paper_executor,
        "append_event",
        lambda event: None,
        raising=False,
    )
