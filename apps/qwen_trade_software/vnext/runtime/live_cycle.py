"""Closed-bar live orchestration for the direct V2 runtime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Iterable, Mapping, Protocol

from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine
from vnext.storage.persistence import VNextPersistence


class ClosedBarSource(Protocol):
    def closed_m1(self, pair: str, count: int) -> Iterable[Mapping[str, Any]]: ...


class MT5ClosedBarSource:
    """Read only completed M1 bars from an already-connected MT5 client."""

    def __init__(self, mt5_client: Any) -> None:
        self.mt5 = mt5_client

    def closed_m1(self, pair: str, count: int) -> Iterable[Mapping[str, Any]]:
        if count < 3:
            raise ValueError("count must allow causal confirmation")
        rates = self.mt5.copy_rates_from_pos(pair, self.mt5.TIMEFRAME_M1, 1, count)
        if rates is None:
            raise RuntimeError(f"MT5 closed-bar read failed: {self.mt5.last_error()}")
        return [{
            "time": _row_value(row, "time"), "open": _row_value(row, "open"),
            "high": _row_value(row, "high"), "low": _row_value(row, "low"),
            "close": _row_value(row, "close"),
            "tick_volume": _row_value(row, "tick_volume", 0),
            "spread": _row_value(row, "spread", 0),
        } for row in rates]

    def forming_timeframes(self, pair: str) -> list[dict[str, Any]]:
        """Read display-only current bars; never feed them into market state."""
        sampled = datetime.now(timezone.utc)
        definitions = (
            ("D1", self.mt5.TIMEFRAME_D1, 86400),
            ("H4", self.mt5.TIMEFRAME_H4, 14400),
            ("H1", self.mt5.TIMEFRAME_H1, 3600),
            ("M30", self.mt5.TIMEFRAME_M30, 1800),
            ("M15", self.mt5.TIMEFRAME_M15, 900),
        )
        result: list[dict[str, Any]] = []
        for label, timeframe, duration in definitions:
            rates = self.mt5.copy_rates_from_pos(pair, timeframe, 0, 1)
            if rates is None or len(rates) == 0:
                continue
            row = rates[-1]
            start = _utc_datetime(_row_value(row, "time"))
            end = start + timedelta(seconds=duration)
            if not start <= sampled < end:
                continue
            result.append({
                "timeframe": label, "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                "open": float(_row_value(row, "open")), "high": float(_row_value(row, "high")),
                "low": float(_row_value(row, "low")), "close": float(_row_value(row, "close")),
                "tick_volume": float(_row_value(row, "tick_volume", 0)),
                "spread": float(_row_value(row, "spread", 0)),
                "sampled_at_utc": sampled.isoformat(), "is_forming": True,
                "source": "mt5_display_only",
            })
        return result


class TimescaleClosedBarSource:
    """Read canonical completed M1 bars from the durable V2 numerical store."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("Timescale DSN is required")
        self.dsn = dsn

    def closed_m1(self, pair: str, count: int) -> Iterable[Mapping[str, Any]]:
        if count < 3:
            raise ValueError("count must allow causal confirmation")
        import psycopg
        with psycopg.connect(self.dsn, connect_timeout=3) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT open_time_utc,open,high,low,close,tick_volume,spread "
                "FROM completed_candles WHERE symbol=%s AND timeframe='M1' "
                "ORDER BY open_time_utc DESC LIMIT %s", (pair, int(count)))
            rows = list(reversed(cursor.fetchall()))
        return [{"time": row[0], "open": row[1], "high": row[2], "low": row[3],
                 "close": row[4], "tick_volume": row[5], "spread": row[6]} for row in rows]


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (IndexError, KeyError, TypeError):
        return default


def canonical_bar(pair: str, row: Mapping[str, Any]) -> Bar:
    """Convert one broker row; reject missing or non-finite market fields."""
    start_value = row.get("start_utc", row.get("time"))
    end_value = row.get("end_utc")
    if start_value is None:
        raise ValueError("broker bar has no start time")
    start = _utc_datetime(start_value)
    end = _utc_datetime(end_value) if end_value is not None else start + timedelta(minutes=1)
    prices = tuple(float(row[name]) for name in ("open", "high", "low", "close"))
    volume = float(row.get("tick_volume", row.get("volume", 0)))
    spread = float(row.get("spread", 0))
    if not all(isfinite(value) for value in (*prices, volume, spread)):
        raise ValueError("broker bar contains non-finite values")
    return Bar(pair, "M1", start, end, *prices, tick_volume=volume, spread=spread,
               source="mt5_closed_m1")


def _utc_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    if hasattr(value, "item") and callable(value.item):
        value = value.item()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


class LiveVNextCycle:
    """One deterministic closed-bar cycle; no shadow mode or file persistence."""

    def __init__(self, *, pair: str, source: ClosedBarSource,
                 persistence: VNextPersistence, lookback: int = 300) -> None:
        if lookback < 3:
            raise ValueError("lookback must allow causal confirmation")
        self.pair, self.source, self.persistence, self.lookback = pair, source, persistence, lookback

    def run_once(self):
        bars = [canonical_bar(self.pair, row) for row in self.source.closed_m1(self.pair, self.lookback)]
        if not bars:
            raise RuntimeError("closed-bar source returned no data")
        bars.sort(key=lambda bar: bar.start_utc)
        frontier = TimeFrontier.from_value(bars[-1].end_utc)
        engine = VNextEngine(pair=self.pair, frontier=frontier,
                             event_sink=self.persistence.append_events)
        state = engine.compose_state(bars)
        context = state.as_dict()
        context["state_hash"] = state.state_hash
        self.persistence.publish_context(self.pair, context)
        forming_reader = getattr(self.source, "forming_timeframes", None)
        if callable(forming_reader):
            try:
                self.persistence.publish_context(f"forming:{self.pair}", {
                    "schema_version": "FORMING_CANDLE_DISPLAY_V1",
                    "pair": self.pair,
                    "display_only": True,
                    "strategy_eligible": False,
                    "bars": list(forming_reader(self.pair)),
                })
            except Exception:
                # Display-only forming bars must never affect the closed-bar cycle.
                pass
        return state
