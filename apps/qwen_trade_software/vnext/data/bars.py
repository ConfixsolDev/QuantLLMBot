"""Canonical OHLCV bars with causal parent/child construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping

from vnext.platform.time_frontier import TimeFrontier, utc


TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


@dataclass(frozen=True, slots=True)
class Bar:
    pair: str
    timeframe: str
    start_utc: datetime
    end_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: float = 0.0
    spread: float | None = None
    source: str = "canonical"
    child_count: int = 1
    child_slots: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.timeframe not in TF_MINUTES:
            raise ValueError(f"unsupported timeframe: {self.timeframe}")
        start, end = utc(self.start_utc), utc(self.end_utc)
        if end <= start or end - start != timedelta(minutes=TF_MINUTES[self.timeframe]):
            raise ValueError("bar interval does not match timeframe")
        if not self.pair or min(self.open, self.high, self.low, self.close) < 0:
            raise ValueError("invalid bar identity or prices")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC extremes do not contain open and close")
        if self.child_count <= 0:
            raise ValueError("child_count must be positive")
        object.__setattr__(self, "start_utc", start)
        object.__setattr__(self, "end_utc", end)

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe,
            "start_utc": self.start_utc.isoformat(), "end_utc": self.end_utc.isoformat(),
            "open": self.open, "high": self.high, "low": self.low, "close": self.close,
            "tick_volume": self.tick_volume, "spread": self.spread, "source": self.source,
            "child_count": self.child_count, "child_slots": list(self.child_slots),
        }


class TimeframeBuilder:
    """Build complete higher-timeframe bars only from complete child bars."""

    def __init__(self, pair: str, *, frontier: TimeFrontier) -> None:
        self.pair = pair
        self.frontier = frontier

    def build(self, m1_bars: Iterable[Bar], timeframe: str) -> list[Bar]:
        if timeframe == "M1":
            rows = list(m1_bars)
            return self._complete(rows, timeframe)
        if timeframe not in TF_MINUTES or TF_MINUTES[timeframe] < 1:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        rows = [bar for bar in m1_bars if bar.timeframe == "M1" and bar.pair == self.pair]
        rows = sorted(rows, key=lambda bar: bar.start_utc)
        minutes = TF_MINUTES[timeframe]
        grouped: dict[datetime, list[Bar]] = {}
        for bar in rows:
            self.frontier.require(bar.end_utc, label="bar")
            epoch = int(bar.start_utc.timestamp())
            bucket = datetime.fromtimestamp(epoch - (epoch % (minutes * 60)), tz=timezone.utc)
            grouped.setdefault(bucket, []).append(bar)
        result: list[Bar] = []
        for start, children in sorted(grouped.items()):
            children = sorted(children, key=lambda bar: bar.start_utc)
            expected = minutes
            if len(children) != expected:
                continue
            if any(child.start_utc != start + timedelta(minutes=i) for i, child in enumerate(children)):
                continue
            end = start + timedelta(minutes=minutes)
            if end > self.frontier.as_of_utc:
                continue
            result.append(Bar(
                pair=self.pair, timeframe=timeframe, start_utc=start, end_utc=end,
                open=children[0].open, high=max(child.high for child in children),
                low=min(child.low for child in children), close=children[-1].close,
                tick_volume=sum(child.tick_volume for child in children),
                spread=max((child.spread for child in children if child.spread is not None), default=None),
                source="timeframe_builder", child_count=len(children),
                child_slots=tuple(range(1, len(children) + 1)),
            ))
        return result

    def _complete(self, rows: list[Bar], timeframe: str) -> list[Bar]:
        result = []
        for bar in sorted(rows, key=lambda item: item.start_utc):
            if bar.pair == self.pair and bar.timeframe == timeframe and self.frontier.permits(bar.end_utc):
                result.append(bar)
        return result
