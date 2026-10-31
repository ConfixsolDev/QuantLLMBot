"""Stage 6: per-configuration expectancy ledger with automatic promotion.

Nothing in the system currently feeds outcomes back into permission. The
2026-08-10 data already contained a decisive signal that no component could act
on:

    M30-anchored trades   n=6   net +385.45   win 66.7%
    H4-anchored trades    n=7   net -116.85   win 14.3%
    H1-anchored trades    n=6   net -316.20   win 16.7%
    M15-anchored trades   n=2   net -197.50   win  0.0%

The system kept taking H1 and H4 anchored entries all day because no mechanism
existed to notice they were losing and stop.

This module makes configurations earn the right to trade:

    OBSERVATION  scored and logged, not traded (default for anything new)
    PERMITTED    proven over a minimum sample with positive expectancy
    DEMOTED      proven negative; automatically blocked from trading

A configuration is the tuple that actually characterises a trade -- frame, side,
session, trigger timeframe and geometry source. Promotion and demotion are
logged decisions with the evidence attached, not manual edits.

Storage is a plain JSON document so it can be inspected, diffed and hand-edited
in an emergency. Pure logic plus one small load/save pair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


LEDGER_VERSION = "6.0"

# Trades required before a configuration can leave OBSERVATION.
MIN_SAMPLE_TO_PROMOTE = 12

# Trades required before a configuration can be demoted, so a short unlucky run
# does not permanently disable something sound.
MIN_SAMPLE_TO_DEMOTE = 8

# Expectancy per trade, in account currency, required to hold PERMITTED.
PROMOTE_EXPECTANCY = 5.0

# Expectancy at or below which a configuration is demoted.
DEMOTE_EXPECTANCY = -15.0

# A configuration this bad is demoted early, before the usual sample.
SEVERE_EXPECTANCY = -60.0
SEVERE_MIN_SAMPLE = 5

# Only the most recent N trades count, so a configuration can recover.
ROLLING_WINDOW = 60

# A demoted configuration re-enters observation after this many new trades.
REHABILITATION_AFTER = 20


class State:
    OBSERVATION = "observation"
    PERMITTED = "permitted"
    DEMOTED = "demoted"


@dataclass(frozen=True)
class TradeRecord:
    """One closed trade, reduced to what the ledger needs."""

    frame: str | None = None
    side: str | None = None
    session: str | None = None
    trigger_tf: str | None = None
    geometry_source: str | None = None
    pnl: float = 0.0
    exit_reason: str | None = None

    def configuration_key(self) -> str:
        return "|".join([
            str(self.frame or "?"),
            str(self.side or "?"),
            str(self.session or "?"),
            str(self.trigger_tf or "?"),
            str(self.geometry_source or "?"),
        ])


@dataclass
class ConfigurationStats:
    key: str
    state: str = State.OBSERVATION
    trades: int = 0
    wins: int = 0
    net_pnl: float = 0.0
    recent: list = field(default_factory=list)
    trades_since_demotion: int = 0
    history: list = field(default_factory=list)

    @property
    def expectancy(self) -> float:
        window = self.recent[-ROLLING_WINDOW:]
        return (sum(window) / len(window)) if window else 0.0

    @property
    def win_rate(self) -> float:
        window = self.recent[-ROLLING_WINDOW:]
        if not window:
            return 0.0
        return sum(1 for x in window if x > 0) / len(window)

    @property
    def sample(self) -> int:
        return len(self.recent[-ROLLING_WINDOW:])

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "state": self.state,
            "trades": self.trades,
            "wins": self.wins,
            "net_pnl": round(self.net_pnl, 2),
            "sample": self.sample,
            "expectancy": round(self.expectancy, 2),
            "win_rate": round(self.win_rate, 4),
            "recent": self.recent[-ROLLING_WINDOW:],
            "trades_since_demotion": self.trades_since_demotion,
            "history": self.history[-20:],
        }


class ConfigurationLedger:
    """Rolling expectancy per configuration, with automatic state transitions."""

    def __init__(self, configurations: Mapping[str, ConfigurationStats] | None = None):
        self._configs: dict[str, ConfigurationStats] = dict(configurations or {})

    # -- ingestion ----------------------------------------------------------
    def record(self, trade: TradeRecord) -> ConfigurationStats:
        key = trade.configuration_key()
        stats = self._configs.get(key) or ConfigurationStats(key=key)
        stats.trades += 1
        stats.net_pnl += trade.pnl
        if trade.pnl > 0:
            stats.wins += 1
        stats.recent.append(round(trade.pnl, 2))
        if stats.state == State.DEMOTED:
            stats.trades_since_demotion += 1
        self._configs[key] = stats
        self._transition(stats)
        return stats

    def record_all(self, trades: Iterable[TradeRecord]) -> None:
        for trade in trades:
            self.record(trade)

    # -- state machine ------------------------------------------------------
    def _transition(self, stats: ConfigurationStats) -> None:
        previous = stats.state
        expectancy = stats.expectancy
        sample = stats.sample

        if stats.state == State.DEMOTED:
            if stats.trades_since_demotion >= REHABILITATION_AFTER:
                stats.state = State.OBSERVATION
                stats.trades_since_demotion = 0
                self._log(stats, previous, "rehabilitation window elapsed")
            return

        # Severe losers are stopped early rather than bleeding to full sample.
        if sample >= SEVERE_MIN_SAMPLE and expectancy <= SEVERE_EXPECTANCY:
            stats.state = State.DEMOTED
            stats.trades_since_demotion = 0
            self._log(stats, previous,
                      f"severe expectancy {expectancy:.2f} over {sample} trades")
            return

        if sample >= MIN_SAMPLE_TO_DEMOTE and expectancy <= DEMOTE_EXPECTANCY:
            stats.state = State.DEMOTED
            stats.trades_since_demotion = 0
            self._log(stats, previous,
                      f"expectancy {expectancy:.2f} at or below {DEMOTE_EXPECTANCY}")
            return

        if sample >= MIN_SAMPLE_TO_PROMOTE and expectancy >= PROMOTE_EXPECTANCY:
            if stats.state != State.PERMITTED:
                stats.state = State.PERMITTED
                self._log(stats, previous,
                          f"expectancy {expectancy:.2f} over {sample} trades")
            return

        if stats.state == State.PERMITTED and expectancy < PROMOTE_EXPECTANCY:
            stats.state = State.OBSERVATION
            self._log(stats, previous,
                      f"expectancy {expectancy:.2f} fell below {PROMOTE_EXPECTANCY}")

    def _log(self, stats: ConfigurationStats, previous: str, why: str) -> None:
        if previous == stats.state:
            return
        stats.history.append({
            "from": previous, "to": stats.state, "why": why,
            "sample": stats.sample, "expectancy": round(stats.expectancy, 2),
        })

    # -- queries ------------------------------------------------------------
    def state_of(self, trade_or_key) -> str:
        key = (trade_or_key.configuration_key()
               if isinstance(trade_or_key, TradeRecord) else str(trade_or_key))
        stats = self._configs.get(key)
        return stats.state if stats else State.OBSERVATION

    def may_trade(self, trade_or_key) -> tuple[bool, str]:
        """Permission check for a proposed configuration.

        OBSERVATION is allowed to trade but flagged, so new configurations can
        accumulate the sample they need. DEMOTED is blocked outright.
        """
        state = self.state_of(trade_or_key)
        if state == State.DEMOTED:
            return False, "configuration is demoted on measured negative expectancy"
        if state == State.OBSERVATION:
            return True, "configuration is under observation; outcome will be recorded"
        return True, "configuration is permitted"

    def configurations(self) -> dict[str, ConfigurationStats]:
        return dict(self._configs)

    def ranked(self) -> list[ConfigurationStats]:
        return sorted(self._configs.values(),
                      key=lambda s: s.expectancy, reverse=True)

    def summary(self) -> dict:
        by_state: dict[str, int] = {}
        for stats in self._configs.values():
            by_state[stats.state] = by_state.get(stats.state, 0) + 1
        return {
            "ledger_version": LEDGER_VERSION,
            "configurations": len(self._configs),
            "by_state": by_state,
            "total_trades": sum(s.trades for s in self._configs.values()),
            "total_pnl": round(sum(s.net_pnl for s in self._configs.values()), 2),
        }

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "ledger_version": LEDGER_VERSION,
            "configurations": {k: v.as_dict() for k, v in self._configs.items()},
            "summary": self.summary(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping) -> "ConfigurationLedger":
        configs = {}
        for key, row in (payload.get("configurations") or {}).items():
            configs[key] = ConfigurationStats(
                key=key,
                state=row.get("state", State.OBSERVATION),
                trades=int(row.get("trades", 0)),
                wins=int(row.get("wins", 0)),
                net_pnl=float(row.get("net_pnl", 0.0)),
                recent=list(row.get("recent") or []),
                trades_since_demotion=int(row.get("trades_since_demotion", 0)),
                history=list(row.get("history") or []),
            )
        return cls(configs)

    def save(self, path: Path | str) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path | str) -> "ConfigurationLedger":
        path = Path(path)
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls()


def format_ledger(ledger: ConfigurationLedger, limit: int = 20) -> str:
    """Human-readable ranking, best expectancy first."""
    lines = [
        f"CONFIGURATION LEDGER {LEDGER_VERSION}",
        f"  {'state':12} {'n':>3} {'expectancy':>11} {'win%':>6}  configuration",
    ]
    for stats in ledger.ranked()[:limit]:
        lines.append(
            f"  {stats.state:12} {stats.sample:>3} {stats.expectancy:>11.2f} "
            f"{stats.win_rate:>5.0%}  {stats.key}"
        )
    summary = ledger.summary()
    lines.append(
        f"  -- {summary['configurations']} configurations, "
        f"{summary['total_trades']} trades, net {summary['total_pnl']:+.2f}"
    )
    return "\n".join(lines)
