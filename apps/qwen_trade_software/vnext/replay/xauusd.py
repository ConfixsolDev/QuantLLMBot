"""Leakage-safe XAUUSD V2 candidate replay; never calls Qwen or a broker."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from vnext.data.bars import Bar
from vnext.platform.time_frontier import TimeFrontier
from vnext.runtime.engine import VNextEngine
from vnext.strategy.xau_m15_m1_structure_scalper import candidate_inputs


@dataclass(frozen=True, slots=True)
class CandidateReplayReport:
    source_bars: int
    evaluated_frontiers: int
    candidate_count: int
    skipped_by_session: int
    sessions: dict[str, int]
    errors: tuple[str, ...]

    def as_dict(self) -> dict:
        return asdict(self)


def replay_candidates(bars: Iterable[Bar], *, lookback: int = 300,
                      cadence_minutes: int = 1) -> CandidateReplayReport:
    """Evaluate each causal frontier using bars ending at or before that frontier."""
    if lookback < 3 or cadence_minutes <= 0:
        raise ValueError("replay lookback and cadence must be positive")
    rows = sorted(list(bars), key=lambda row: row.end_utc)
    sessions: Counter[str] = Counter()
    candidates = skipped = evaluated = 0
    errors: list[str] = []
    for index in range(lookback, len(rows), cadence_minutes):
        window = rows[index - lookback:index]
        frontier = TimeFrontier.from_value(window[-1].end_utc)
        try:
            state = VNextEngine(pair=window[-1].pair, frontier=frontier).compose_state(window)
            payload = state.as_dict()
            payload["state_hash"] = state.state_hash
            entry_session = payload.get("temporal_state", {}).get("entry_session", {})
            session = str(entry_session.get("session", "unknown"))
            sessions[session] += 1
            candidate = candidate_inputs(payload)
            if candidate:
                candidates += 1
            elif not entry_session.get("trade_permitted", False):
                skipped += 1
            evaluated += 1
        except Exception as exc:
            errors.append(f"{window[-1].end_utc.isoformat()}:{type(exc).__name__}")
    return CandidateReplayReport(len(rows), evaluated, candidates, skipped, dict(sorted(sessions.items())),
                                 tuple(errors[:100]))


def mt5_m1_bars(mt5: object, *, pair: str, start: datetime, end: datetime) -> list[Bar]:
    """Read completed historical M1 bars only; this operation is broker read-only."""
    timeframe = getattr(mt5, "TIMEFRAME_M1")
    rows = mt5.copy_rates_range(pair, timeframe, start.astimezone(timezone.utc), end.astimezone(timezone.utc))
    if rows is None:
        raise RuntimeError("MT5 historical M1 read failed")
    output: list[Bar] = []
    for row in rows:
        if hasattr(row, "get"):
            get = row.get
        else:
            def get(key: str, default=None):
                try:
                    return row[key]
                except (IndexError, KeyError, TypeError):
                    return default
        opened = datetime.fromtimestamp(float(get("time")), timezone.utc)
        output.append(Bar(pair, "M1", opened, opened + timedelta(minutes=1),
                          float(get("open")), float(get("high")), float(get("low")), float(get("close")),
                          tick_volume=float(get("tick_volume", 0)), spread=float(get("spread", 0)), source="mt5_replay"))
    return output
