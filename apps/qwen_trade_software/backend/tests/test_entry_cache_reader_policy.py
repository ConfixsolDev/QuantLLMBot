"""Latency-critical cache readers must never own model/cache recovery."""

from __future__ import annotations

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_context_cache import latest_entry_context  # noqa: E402


def test_latest_entry_context_is_read_only_by_default():
    parameter = inspect.signature(latest_entry_context).parameters["auto_upgrade"]
    assert parameter.default is False
