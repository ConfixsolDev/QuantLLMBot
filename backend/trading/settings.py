"""Trading settings: ``backend/config/trading.json`` (copy ``trading.example.json``).

    strategy             active strategy id (strategy/library/<id>.v<N>.json)
    strategy_version     null = the latest version
    risk_pct             % of balance risked per trade (demo: may be 10 or more)
    max_open_positions   1 — one model position at a time (V3 Part E1)
    daily_loss_limit_pct null = off (demo, learning phase); a number turns it on
    magic                MT5 magic number that marks OUR positions
    deviation_points     max slippage MT5 may fill at, in points
    slippage_allowance   price units added to the stop distance when sizing
    require_demo         true — refuse to trade on a non-demo account (never switch off)
    mode                 "off" | "paper" | "demo": off = decide and journal only;
                         paper = simulated broker; demo = MT5 demo account
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parents[1] / "config" / "trading.json"


@dataclass(frozen=True)
class TradingSettings:
    strategy: str = "htf_level_m1_rejection"
    strategy_version: int | None = None
    risk_pct: float = 10.0
    max_open_positions: int = 1
    daily_loss_limit_pct: float | None = None
    magic: int = 26110101
    deviation_points: int = 30
    slippage_allowance: float = 0.2
    require_demo: bool = True
    mode: str = "off"


def load_settings(path: Path | None = None) -> TradingSettings:
    s = TradingSettings()
    path = path or CONFIG_FILE
    if path.exists():
        raw = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        unknown = set(raw) - set(TradingSettings.__dataclass_fields__)
        if unknown:
            raise ValueError(f"{path}: unknown trading setting(s) {sorted(unknown)}")
        s = replace(s, **raw)
    if s.mode not in ("off", "paper", "demo"):
        raise ValueError("trading mode must be off, paper or demo")
    if not s.require_demo:
        raise ValueError("require_demo must stay true: this system trades demo accounts only")
    if s.risk_pct <= 0 or s.max_open_positions < 1:
        raise ValueError("risk_pct must be > 0 and max_open_positions >= 1")
    return s
