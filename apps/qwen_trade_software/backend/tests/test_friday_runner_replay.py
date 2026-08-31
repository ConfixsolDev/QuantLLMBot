"""Read-only regression replay of the agreed runner ladder on 2026-08-21.

The local ledger is operational evidence rather than a portable test fixture,
so clean checkouts without that ledger skip this integration test. Fill prices
use the crossed virtual-stop level with zero added slippage; the assertion is a
regression guard for this recorded day, not an out-of-sample performance claim.
"""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sqlite3

import pytest


BACKEND = Path(__file__).resolve().parents[1]
JOURNAL_DB = BACKEND / "cache" / "market-intelligence.sqlite3"
TICK_DB = BACKEND / "cache" / "market_context.sqlite3"
PROTECTION_LOG = BACKEND / "logs" / "profit-protection-2026-08-21.jsonl"


def _utc_sql(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _atr_by_trade() -> dict[tuple[str, float], float]:
    values = {}
    for line in PROTECTION_LOG.open(encoding="utf-8"):
        row = json.loads(line)
        key = (str(row.get("side")), round(float(row.get("entry") or 0.0), 3))
        if row.get("atr") and key not in values:
            values[key] = float(row["atr"])
    return values


def _floor_volume(value: float, step: float = 0.01) -> float:
    return math.floor((value + step * 1e-9) / step) * step


@pytest.mark.skipif(
    not (JOURNAL_DB.exists() and TICK_DB.exists() and PROTECTION_LOG.exists()),
    reason="local Friday SQLite ledger is unavailable",
)
def test_relaxed_runner_ladder_improves_recorded_friday_gross_pnl():
    journal = sqlite3.connect(f"file:{JOURNAL_DB.as_posix()}?mode=ro", uri=True)
    ticks = sqlite3.connect(f"file:{TICK_DB.as_posix()}?mode=ro", uri=True)
    tick_count = ticks.execute(
        "SELECT COUNT(*) FROM ticks WHERE symbol='XAUUSDr' "
        "AND time_utc>=? AND time_utc<?",
        ("2026-08-21T00:00:00Z", "2026-08-22T00:00:00Z"),
    ).fetchone()[0]
    if not tick_count:
        pytest.skip("recorded Friday tick evidence is unavailable in the local fixture")
    trades = journal.execute(
        "SELECT side,entry_price,exit_price,volume,gross_pnl,"
        "entry_time_utc,exit_time_utc FROM trade_journal "
        "WHERE exit_time_utc LIKE '2026-08-21%' ORDER BY entry_time_utc"
    ).fetchall()
    atrs = _atr_by_trade()
    actual_gross = sum(float(row[4]) for row in trades)
    replay_gross = actual_gross

    for side, entry, exit_price, volume, _, opened, closed in trades:
        atr = atrs[(side, round(float(entry), 3))]
        direction = 1.0 if side == "buy" else -1.0
        prices = ticks.execute(
            "SELECT bid,ask FROM ticks WHERE symbol='XAUUSDr' "
            "AND time_utc>=? AND time_utc<=? ORDER BY time_utc",
            (_utc_sql(opened), _utc_sql(closed)),
        ).fetchall()
        executable = [float(bid if side == "buy" else ask) for bid, ask in prices]
        peak_move = 0.0
        front_stop = None
        wide_stop = None
        front_volume = _floor_volume(float(volume) * 0.25)
        remaining = float(volume)
        front_closed = False

        for price in executable:
            move = direction * (price - float(entry))
            peak_move = max(peak_move, move)
            stepped = math.floor((peak_move / atr + 1e-9) / 0.25) * 0.25
            if stepped >= 1.50:
                candidate = float(entry) + direction * (stepped - 0.25) * atr
                front_stop = candidate if front_stop is None else (
                    max(front_stop, candidate) if side == "buy"
                    else min(front_stop, candidate)
                )
            if stepped >= 2.00:
                candidate = float(entry) + direction * (stepped - 0.50) * atr
                wide_stop = candidate if wide_stop is None else (
                    max(wide_stop, candidate) if side == "buy"
                    else min(wide_stop, candidate)
                )
            if (
                not front_closed and front_stop is not None and front_volume > 0
                and direction * (price - front_stop) <= 0
            ):
                replay_gross += (
                    direction * (front_stop - float(exit_price))
                    * front_volume * 100.0
                )
                remaining -= front_volume
                front_closed = True
            if wide_stop is not None and direction * (price - wide_stop) <= 0:
                replay_gross += (
                    direction * (wide_stop - float(exit_price))
                    * remaining * 100.0
                )
                break

    assert actual_gross == pytest.approx(767.89, abs=0.01)
    assert replay_gross == pytest.approx(781.66, abs=0.01)
    assert replay_gross > actual_gross
