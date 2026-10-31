"""goldflow.core.mt5_connection: settings loading, initialize() call shape, broker clock."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from goldflow.core import mt5_connection as mc  # noqa: E402


def test_defaults_match_the_historical_behaviour(tmp_path):
    cfg = mc.load_settings(tmp_path / "absent.json", use_env=False)
    assert cfg.terminal_path == r"C:\Program Files\MetaTrader 5\terminal64.exe"
    assert cfg.login is None and cfg.broker_symbol == "XAUUSDr"


def test_example_file_is_valid_and_complete():
    cfg = mc.load_settings(mc.EXAMPLE_FILE, use_env=False)
    raw = {k for k in json.loads(mc.EXAMPLE_FILE.read_text()) if not k.startswith("_")}
    assert raw == mc._KNOWN_KEYS  # every setting is documented in the template
    assert cfg == mc.MT5Settings()


def test_unknown_key_and_password_in_file_are_rejected(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"logn": 1}))
    with pytest.raises(ValueError, match="unknown"):
        mc.load_settings(p, use_env=False)
    p.write_text(json.dumps({"password": "x"}))
    with pytest.raises(ValueError):
        mc.load_settings(p, use_env=False)


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("QWEN_MT5_LOGIN", "123")
    monkeypatch.setenv("QWEN_MT5_SERVER", "Broker-Demo")
    monkeypatch.setenv("QWEN_MT5_SYMBOL", "XAUUSD")
    cfg = mc.load_settings(tmp_path / "absent.json")
    assert (cfg.login, cfg.server, cfg.broker_symbol) == (123, "Broker-Demo", "XAUUSD")


def test_initialize_attaches_with_path_then_falls_back():
    fake = mock.MagicMock()
    fake.initialize.side_effect = [False, True]
    assert mc.initialize(fake, cfg=mc.MT5Settings(terminal_path="T"))
    assert fake.initialize.call_args_list[0] == mock.call(path="T", timeout=60000)
    assert fake.initialize.call_args_list[1] == mock.call()


def test_pinned_login_passes_credentials_and_verifies_account(monkeypatch):
    monkeypatch.setenv("QWEN_MT5_PASSWORD", "secret")
    fake = mock.MagicMock()
    fake.initialize.return_value = True
    fake.account_info.return_value = SimpleNamespace(login=999)
    cfg = mc.MT5Settings(terminal_path="T", login=42, server="S")
    assert mc.initialize(fake, cfg=cfg) is False      # wrong account -> refused
    kwargs = fake.initialize.call_args.kwargs
    assert kwargs["login"] == 42 and kwargs["server"] == "S" and kwargs["password"] == "secret"
    fake.initialize.side_effect = [False]
    assert mc.initialize(fake, cfg=cfg) is False      # no fallback to an unknown account
    assert "secret" not in json.dumps(cfg.public_dict(), default=str)


def test_ny_close_clock():
    winter = int(datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp())
    summer = int(datetime(2026, 7, 15, 12, tzinfo=timezone.utc).timestamp())
    assert mc.server_to_utc_epoch(winter + 2 * 3600, "ny_close") == winter
    assert mc.server_to_utc_epoch(summer + 3 * 3600, "ny_close") == summer
    assert mc.server_to_utc_epoch(summer, "utc") == summer
    assert mc.server_to_utc_epoch(summer + 3600, 1) == summer
