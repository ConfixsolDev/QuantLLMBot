"""Causal strategy-scoped timeframe expectation and outcome audit events."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Protocol

from vnext.market.state import PairMarketState
from vnext.platform.events import EventEnvelope
from vnext.strategy.definition import StrategySpec


AUDIT_TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15")
EXPECTATION_EVENT = "TIMEFRAME_EXPECTATION_RECORDED"
OUTCOME_EVENT = "TIMEFRAME_EXPECTATION_ASSESSED"
EXPECTATION_SCHEMA = "TIMEFRAME_EXPECTATION_V1"
OUTCOME_SCHEMA = "TIMEFRAME_EXPECTATION_OUTCOME_V1"


class AuditStore(Protocol):
    def append_events(self, events: list[EventEnvelope]) -> int: ...
    def latest_timeframe_expectation(self, *, pair: str, strategy_id: str,
                                     target_close_utc: str) -> dict[str, Any] | None: ...
    def latest_completed_candles(self, *, pair: str, timeframes: tuple[str, ...],
                                 as_of_utc: datetime) -> dict[str, dict[str, Any]]: ...


def _utc(value: Any) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (result if result.tzinfo else result.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _direction(bar: Mapping[str, Any] | None) -> str:
    if not bar:
        return "unknown"
    try:
        opened, closed = float(bar["open"]), float(bar["close"])
    except (KeyError, TypeError, ValueError):
        return "unknown"
    return "buy" if closed > opened else "sell" if closed < opened else "neutral"


def _latest_as_of(rows: Any, frontier: datetime) -> dict[str, Any] | None:
    eligible = []
    for row in rows or ():
        if not isinstance(row, Mapping):
            continue
        end = row.get("end_utc", row.get("close_time_utc"))
        if end is not None and _utc(end) <= frontier:
            eligible.append(dict(row))
    return max(eligible, key=lambda row: _utc(row.get("end_utc", row.get("close_time_utc")))) if eligible else None


def _event_id(kind: str, pair: str, strategy_id: str, close_utc: datetime) -> str:
    raw = f"{kind}|{pair}|{strategy_id}|{close_utc.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


class TimeframeExpectationAuditor:
    """Persist a non-authoritative continuation baseline and next-M15 outcome."""

    def __init__(self, store: AuditStore) -> None:
        self.store = store

    def record(self, state: PairMarketState, strategy: StrategySpec) -> int:
        m15 = _latest_as_of(state.timeframes.get("M15", ()), state.time_frontier_utc)
        if not m15:
            return 0
        origin = _utc(m15.get("end_utc", m15.get("close_time_utc")))
        prior = self.store.latest_timeframe_expectation(
            pair=state.pair, strategy_id=strategy.definition.strategy_id,
            target_close_utc=origin.isoformat(),
        )
        durable = self.store.latest_completed_candles(
            pair=state.pair, timeframes=AUDIT_TIMEFRAMES, as_of_utc=origin,
        )
        frame_bars: dict[str, dict[str, Any] | None] = {}
        for timeframe in AUDIT_TIMEFRAMES:
            active = _latest_as_of(state.timeframes.get(timeframe, ()), origin)
            frame_bars[timeframe] = active or durable.get(timeframe)

        events: list[EventEnvelope] = []
        if prior:
            events.append(self._outcome_event(state, strategy, origin, m15, frame_bars, prior))
        events.append(self._expectation_event(state, strategy, origin, frame_bars))
        return self.store.append_events(events)

    def _expectation_event(self, state: PairMarketState, strategy: StrategySpec,
                           origin: datetime, frame_bars: Mapping[str, Mapping[str, Any] | None]) -> EventEnvelope:
        target = origin + timedelta(minutes=15)
        frames: dict[str, Any] = {}
        for timeframe in AUDIT_TIMEFRAMES:
            bar = frame_bars.get(timeframe)
            end_value = bar.get("end_utc", bar.get("close_time_utc")) if bar else None
            end = _utc(end_value) if end_value else None
            observed = _direction(bar)
            frames[timeframe] = {
                "observed_direction": observed,
                "expected_direction": observed if observed in {"buy", "sell"} else "neutral",
                "basis": "LAST_COMPLETED_CANDLE_CONTINUATION_BASELINE_V1",
                "basis_bar_end_utc": end.isoformat() if end else None,
                "freshness_seconds": max(0, int((origin - end).total_seconds())) if end else None,
                "available": bool(bar),
            }
        basis_hash = hashlib.sha256(json.dumps(
            {"pair": state.pair, "origin_close_utc": origin.isoformat(), "frames": frames},
            sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        payload = {
            "schema_version": EXPECTATION_SCHEMA,
            "strategy_id": strategy.definition.strategy_id,
            "strategy_version": strategy.definition.version,
            "pair": state.pair,
            "origin_close_utc": origin.isoformat(),
            "target_close_utc": target.isoformat(),
            # Hash only the closed-candle basis available at the causal boundary.
            # A later runtime cycle can contain newer M1 bars while referring to the
            # same M15 close, so the full live-state hash is deliberately excluded.
            "basis_hash": basis_hash,
            "target_profile": strategy.definition.metadata.get("target_profile"),
            "frames": frames,
            "non_authoritative": True,
            "training_eligible": False,
            "review_requirement": "human_review_before_curriculum_promotion",
        }
        return EventEnvelope(
            _event_id(EXPECTATION_EVENT, state.pair, strategy.definition.strategy_id, origin),
            EXPECTATION_EVENT, state.pair, origin, payload, "vnext_timeframe_audit",
            confirmed_at_utc=origin,
        )

    def _outcome_event(self, state: PairMarketState, strategy: StrategySpec,
                       close_utc: datetime, m15: Mapping[str, Any],
                       frame_bars: Mapping[str, Mapping[str, Any] | None],
                       prior: Mapping[str, Any]) -> EventEnvelope:
        contribution = _direction(m15)
        outcomes: dict[str, Any] = {}
        prior_frames = prior.get("frames", {}) if isinstance(prior.get("frames"), Mapping) else {}
        for timeframe in AUDIT_TIMEFRAMES:
            expected = (prior_frames.get(timeframe) or {}).get("expected_direction", "neutral")
            current = frame_bars.get(timeframe)
            current_end_value = current.get("end_utc", current.get("close_time_utc")) if current else None
            current_end = _utc(current_end_value) if current_end_value else None
            if expected not in {"buy", "sell"} or contribution not in {"buy", "sell"}:
                result, matched = "UNAVAILABLE", None
            else:
                matched = expected == contribution
                result = "ALIGNED" if matched else "COUNTER"
            outcomes[timeframe] = {
                "expected_direction": expected,
                "m15_contribution_direction": contribution,
                "result": result,
                "matched": matched,
                "timeframe_direction_after": _direction(current),
                "timeframe_closed_at_target": bool(current_end and current_end == close_utc),
            }
        payload = {
            "schema_version": OUTCOME_SCHEMA,
            "strategy_id": strategy.definition.strategy_id,
            "strategy_version": strategy.definition.version,
            "pair": state.pair,
            "expectation_event_id": str(prior.get("event_id", "")),
            "origin_close_utc": prior.get("origin_close_utc"),
            "target_close_utc": close_utc.isoformat(),
            "m15_actual": {key: m15.get(key) for key in ("start_utc", "end_utc", "open", "high", "low", "close")},
            "frames": outcomes,
            "non_authoritative": True,
            "training_eligible": False,
        }
        return EventEnvelope(
            _event_id(OUTCOME_EVENT, state.pair, strategy.definition.strategy_id, close_utc),
            OUTCOME_EVENT, state.pair, close_utc, payload, "vnext_timeframe_audit",
            confirmed_at_utc=close_utc,
        )
