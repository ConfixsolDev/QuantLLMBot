"""MetaTrader 5 connection settings — the ONE place that says how we reach MT5.

Why this file exists
--------------------
Before 2026-10-31 every service opened MT5 on its own: ten separate
``mt5.initialize(...)`` calls, two hard-coded copies of the terminal path, and
the broker symbol buried in ``instrument_config``. Moving to a new PC, a new
broker or a new demo account meant hunting through the code. Now every caller
goes through :func:`initialize`, and every machine-specific property lives in
one small JSON file.

Where the settings come from (later wins)
-----------------------------------------
1. Built-in defaults below. They reproduce the old behaviour exactly: attach to
   ``C:\\Program Files\\MetaTrader 5\\terminal64.exe`` using whatever account
   the terminal is already logged in to, and trade ``XAUUSDr``.
2. ``backend/config/mt5_connection.json`` — your local copy. It is git-ignored
   because it is per-machine. Start from ``mt5_connection.example.json``.
3. Environment variables, for one-off overrides without editing the file:
   ``QWEN_MT5_TERMINAL``, ``QWEN_MT5_LOGIN``, ``QWEN_MT5_SERVER``,
   ``QWEN_MT5_SYMBOL``.

The password is NEVER stored in the JSON file and never in git. If you want
the Python side to log in (instead of relying on the terminal's saved login),
put the password in the environment variable named by ``password_env``
(default ``QWEN_MT5_PASSWORD``). Leave it unset and the terminal's own saved
credentials are used — which is how the system has always run.

Why callers pass their own ``mt5`` module in
--------------------------------------------
Tests replace ``MetaTrader5`` with a fake per module (for example
``paper_executor.mt5``). If this file imported MetaTrader5 itself, those fakes
would be bypassed and tests would try to reach a real terminal. So callers
hand over the module they already hold: ``mt5_connection.initialize(mt5)``.

Broker clock
------------
MT5 bar timestamps are in the broker SERVER's clock, not UTC. Most XAUUSD
brokers run "New York close" time: UTC+2 in northern winter, UTC+3 while US
daylight saving is active. ``server_time`` tells the structure engine (and
anything else that converts bar times) which rule to use:

* ``"ny_close"``   UTC+2 / UTC+3 following the US DST calendar (default)
* ``"utc"``        the broker already reports UTC
* a number         a fixed offset in hours, e.g. ``3`` or ``-5``
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[1]   # backend/  (config/ lives here)

#: Your machine's settings. Git-ignored (see .gitignore) — never commit it.
CONFIG_FILE = APP_DIR / "config" / "mt5_connection.json"
#: Tracked template showing every key. Copy it to CONFIG_FILE and edit.
EXAMPLE_FILE = APP_DIR / "config" / "mt5_connection.example.json"


@dataclass(frozen=True)
class MT5Settings:
    """Every property needed to reach the broker. One instance per process."""

    # Full path to terminal64.exe. Pointing at a specific install matters when
    # several terminals are installed: MT5's Python API attaches to the one at
    # this path (and starts it if it is not running).
    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    # Account number. None = use whichever account the terminal is logged in
    # to. Set it to make the connection refuse to run on the wrong account.
    login: int | None = None
    # Broker server name exactly as shown in MT5's login dialog,
    # e.g. "MetaQuotes-Demo". Only used together with ``login``.
    server: str | None = None
    # NAME of the environment variable holding the password (not the password).
    password_env: str = "QWEN_MT5_PASSWORD"
    # How long MT5 may take to start/attach before giving up, in milliseconds.
    timeout_ms: int = 60_000
    # MT5 "portable mode" (terminal keeps its data next to the exe).
    portable: bool = False
    # If attaching at ``terminal_path`` fails, try attaching to ANY running
    # terminal. This was the old behaviour of several services; keep it on
    # unless you run more than one terminal on the machine.
    fallback_attach_any: bool = True
    # Safety: services that place orders already refuse non-demo accounts.
    # This flag is reported in diagnostics and checked by ensure_demo().
    require_demo: bool = True
    # The broker's name for gold. Brokers add suffixes: XAUUSD, XAUUSDr,
    # XAUUSD.m, GOLD ... Must match the Market Watch symbol exactly.
    broker_symbol: str = "XAUUSDr"
    # Broker clock rule for bar timestamps — see module docstring.
    server_time: Any = "ny_close"

    def password(self) -> str | None:
        """Read the password from the environment at call time (never cached)."""
        value = os.environ.get(self.password_env, "")
        return value or None

    def public_dict(self) -> dict:
        """Settings safe to log: the password is never included."""
        data = {f.name: getattr(self, f.name) for f in fields(self)}
        data["password_set"] = self.password() is not None
        return data


_KNOWN_KEYS = {f.name for f in fields(MT5Settings)}
_CACHED: MT5Settings | None = None


def load_settings(path: Path | None = None, *, use_env: bool = True) -> MT5Settings:
    """Build settings from defaults <- JSON file <- environment.

    Unknown keys in the JSON are an error, not a warning: a typo such as
    ``"logn"`` would otherwise silently fall back to the default account.
    Keys starting with ``_`` are treated as comments and ignored.
    """
    settings = MT5Settings()
    path = CONFIG_FILE if path is None else Path(path)
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a JSON object")
        raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        unknown = sorted(set(raw) - _KNOWN_KEYS)
        if unknown:
            raise ValueError(f"{path}: unknown MT5 setting(s) {unknown}; known: {sorted(_KNOWN_KEYS)}")
        if "password" in raw:  # belt and braces: _KNOWN_KEYS has no 'password'
            raise ValueError("Do not put the MT5 password in the file; use password_env")
        settings = replace(settings, **raw)
    if use_env:
        env = os.environ
        if env.get("QWEN_MT5_TERMINAL"):
            settings = replace(settings, terminal_path=env["QWEN_MT5_TERMINAL"])
        if env.get("QWEN_MT5_LOGIN"):
            settings = replace(settings, login=int(env["QWEN_MT5_LOGIN"]))
        if env.get("QWEN_MT5_SERVER"):
            settings = replace(settings, server=env["QWEN_MT5_SERVER"])
        if env.get("QWEN_MT5_SYMBOL"):
            settings = replace(settings, broker_symbol=env["QWEN_MT5_SYMBOL"])
    if settings.login is not None:
        settings = replace(settings, login=int(settings.login))
    _validate_server_time(settings.server_time)
    return settings


def settings() -> MT5Settings:
    """Process-wide settings, loaded once on first use."""
    global _CACHED
    if _CACHED is None:
        _CACHED = load_settings()
    return _CACHED


def initialize(mt5: Any, *, terminal: str | None = None, cfg: MT5Settings | None = None) -> bool:
    """Open (or attach to) the MT5 terminal. Returns True on success.

    ``mt5`` is the caller's ``MetaTrader5`` module (or a test fake).
    ``terminal`` overrides the configured path for this call only (the paper
    executor's ``--terminal`` flag uses this).

    Order of attempts:
      1. ``mt5.initialize(path=..., [login, password, server], timeout, portable)``
      2. if that fails and ``fallback_attach_any``: plain ``mt5.initialize()``
         (only when no explicit login was requested — falling back to an
         unknown account would defeat the point of pinning one).
    After connecting with a pinned ``login``, the account number is verified.
    """
    cfg = cfg or settings()
    kwargs: dict[str, Any] = {"path": terminal or cfg.terminal_path, "timeout": cfg.timeout_ms}
    if cfg.portable:
        kwargs["portable"] = True
    if cfg.login is not None:
        kwargs["login"] = cfg.login
        if cfg.server:
            kwargs["server"] = cfg.server
        password = cfg.password()
        if password:
            kwargs["password"] = password
    ok = bool(mt5.initialize(**kwargs))
    if not ok and cfg.fallback_attach_any and cfg.login is None:
        ok = bool(mt5.initialize())
    if ok and cfg.login is not None:
        account = mt5.account_info()
        if account is None or int(getattr(account, "login", -1)) != cfg.login:
            mt5.shutdown()
            return False
    return ok


def ensure_demo(mt5: Any) -> None:
    """Raise unless the connected account is a DEMO account (when required)."""
    if not settings().require_demo:
        return
    account = mt5.account_info()
    if account is None:
        raise RuntimeError(f"MT5 account unavailable: {mt5.last_error()}")
    if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        raise RuntimeError("MT5 account is not a demo account; refusing (require_demo=true).")


# --------------------------------------------------------------------------
# Broker clock -> UTC
# --------------------------------------------------------------------------

def _validate_server_time(rule: Any) -> None:
    if rule in ("ny_close", "utc") or (isinstance(rule, (int, float)) and not isinstance(rule, bool)):
        return
    raise ValueError(f"server_time must be 'ny_close', 'utc' or a number of hours, got {rule!r}")


def _nth_sunday(year: int, month: int, n: int) -> datetime:
    first = datetime(year, month, 1)
    offset = (6 - first.weekday()) % 7  # weekday(): Monday=0 ... Sunday=6
    return first + timedelta(days=offset + 7 * (n - 1))


def _us_dst_active(utc: datetime) -> bool:
    """US daylight saving: 2nd Sunday of March 07:00 UTC -> 1st Sunday of Nov 06:00 UTC.

    (2:00 local New York time expressed in UTC on each side of the change.)
    """
    start = _nth_sunday(utc.year, 3, 2).replace(hour=7)
    end = _nth_sunday(utc.year, 11, 1).replace(hour=6)
    naive = utc.replace(tzinfo=None)
    return start <= naive < end


def server_offset_hours(server_epoch: int, rule: Any = None) -> float:
    """Offset (hours) to SUBTRACT from a broker timestamp to get UTC."""
    rule = settings().server_time if rule is None else rule
    _validate_server_time(rule)
    if rule == "utc":
        return 0.0
    if rule == "ny_close":
        # Guess with +2, then check DST at that UTC instant. Near the switch
        # hour this is exact because DST is defined on the UTC instant.
        utc_guess = datetime.fromtimestamp(server_epoch - 2 * 3600, tz=timezone.utc)
        return 3.0 if _us_dst_active(utc_guess) else 2.0
    return float(rule)


def server_to_utc_epoch(server_epoch: int, rule: Any = None) -> int:
    """Convert an MT5 bar/tick ``time`` (broker clock) to a real UTC epoch."""
    return int(server_epoch - server_offset_hours(server_epoch, rule) * 3600)


if __name__ == "__main__":
    # Diagnostic: `python -m quantllm.mt5_connection` (from backend/)
    # prints the effective settings and tries to connect.
    cfg = settings()
    print(json.dumps(cfg.public_dict(), indent=2, default=str))
    try:
        import MetaTrader5 as _mt5
    except ImportError:
        raise SystemExit("MetaTrader5 package not installed (pip install MetaTrader5)")
    if not initialize(_mt5):
        raise SystemExit(f"MT5 connection FAILED: {_mt5.last_error()}")
    try:
        acc = _mt5.account_info()
        demo = acc.trade_mode == _mt5.ACCOUNT_TRADE_MODE_DEMO
        print(f"Connected: login={acc.login} server={acc.server} demo={demo}")
        info = _mt5.symbol_info(cfg.broker_symbol)
        print(f"Symbol {cfg.broker_symbol}: {'OK' if info else 'NOT FOUND in Market Watch'}")
    finally:
        _mt5.shutdown()
