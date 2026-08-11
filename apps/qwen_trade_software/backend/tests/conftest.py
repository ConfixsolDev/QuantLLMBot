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
import logging
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set BEFORE any entrypoint is imported. trade_management and friends call
# process_logging.configure() at module scope with force=True, so a fixture
# that swaps handlers is too late -- the import reinstalls the real file
# handler and the test's log lines land in the live log.
os.environ["QWEN_DISABLE_FILE_LOGGING"] = "1"


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
def never_write_to_the_live_log_files():
    """Keep test logging out of the real log files.

    2026-08-11: importing trade_management installs a rotating handler on the
    ROOT logger pointed at logs/trade-management.log. So running the suite
    wrote lines like

        ERROR ALARM adjust:initial_rebracket_overdue :: ticket 99 still on
        its entry bracket 1786431741s after fill

    straight into the live log, with fixture ticket numbers and a duration of
    fifty-six years. Same fault as the synthetic geometry_observation row: a
    test inventing evidence in a file used to diagnose real trading.

    Root handlers are swapped for a null handler and restored afterwards, so a
    test that asserts on logging still works via caplog.
    """
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    for handler in saved_handlers:
        root.removeHandler(handler)
    root.addHandler(logging.NullHandler())
    try:
        yield
    finally:
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


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
