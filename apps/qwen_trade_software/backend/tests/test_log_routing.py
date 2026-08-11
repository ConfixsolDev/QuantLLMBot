"""Each process's log lines must land in that process's file.

2026-08-11 -- why these tests exist
-----------------------------------
`reviewer.py` imports `session_planner`, whose module-level
`logging.basicConfig(...)` claimed the root logger first. Reviewer's own
`basicConfig` several hundred lines later was therefore a silent no-op --
basicConfig does nothing, and says nothing, once a handler exists. Every
reviewer line went to session-planner.log and reviewer.log stayed empty.

Nothing crashed, no test failed, and the empty reviewer.log read as "the
reviewer produced nothing" rather than "the reviewer's output is filed
elsewhere". That is the failure mode worth a regression test: silent
misfiling, not an exception.
"""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import process_logging  # noqa: E402

ENTRYPOINTS = ("reviewer", "session_planner", "trade_management", "paper_runner")


@pytest.fixture(autouse=True)
def restore_root_logger():
    """These tests reconfigure the root logger; put it back afterwards."""
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    for handler in saved[0]:
        root.addHandler(handler)
    root.setLevel(saved[1])


@pytest.fixture
def real_file_logging(monkeypatch):
    """Lift the conftest block for the two tests that must write real files.

    The block exists so the suite cannot write into the live logs. These tests
    verify the file handler itself, and are pointed at tmp_path, so they are
    the one place it has to come off.
    """
    monkeypatch.delenv(process_logging.DISABLE_ENV, raising=False)


def test_configure_overrides_a_handler_installed_by_an_imported_module(tmp_path, real_file_logging):
    """The exact bug: an earlier module claims root, the entrypoint must win."""
    already_claimed = tmp_path / "imported-module.log"
    logging.basicConfig(
        level=logging.INFO,
        handlers=[logging.FileHandler(already_claimed, encoding="utf-8")],
        force=True,
    )

    mine = tmp_path / "entrypoint.log"
    process_logging.configure(mine, owner="entrypoint")

    logging.getLogger().info("belongs to the entrypoint")
    for handler in logging.getLogger().handlers:
        handler.flush()

    assert "belongs to the entrypoint" in mine.read_text(encoding="utf-8")
    assert already_claimed.read_text(encoding="utf-8") == "", (
        "the imported module's handler must no longer receive this process's lines"
    )
    assert process_logging.OWNER == "entrypoint"


def test_configure_creates_the_log_directory(tmp_path, real_file_logging):
    target = tmp_path / "missing" / "deep" / "out.log"
    process_logging.configure(target, owner="whoever")
    logging.getLogger().info("hello")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert target.exists()


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_entrypoints_do_not_use_bare_basic_config(module):
    """A bare basicConfig is the bug. Only process_logging.configure may set up
    the root logger, because only it passes force=True."""
    tree = ast.parse((BACKEND / f"{module}.py").read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if (
            isinstance(target, ast.Attribute)
            and target.attr == "basicConfig"
            and isinstance(target.value, ast.Name)
            and target.value.id == "logging"
        ):
            forced = any(kw.arg == "force" for kw in node.keywords)
            assert forced, (
                f"{module}.py calls logging.basicConfig without force=True. "
                "If any module imported above it configures logging first, this "
                "call does nothing and the log silently goes to the wrong file. "
                "Use process_logging.configure()."
            )


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_each_entrypoint_claims_a_distinct_log_file(module):
    """Two processes writing one file interleaves two stories into one."""
    tree = ast.parse((BACKEND / f"{module}.py").read_text(encoding="utf-8"))

    owners = [
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "process_logging"
        for kw in node.keywords
        if kw.arg == "owner" and isinstance(kw.value, ast.Constant)
    ]
    assert owners == [module], (
        f"{module}.py must claim its log exactly once, as owner={module!r}"
    )
