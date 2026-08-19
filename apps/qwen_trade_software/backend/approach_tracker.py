"""Price approach quality tracker.

Tracks how price moves toward a target zone across multiple observation cycles.
This is the missing link between zone identification and entry — professional
traders evaluate the *quality* of the approach before deciding to trade:

    - Fast approach (trending, non-overlapping candles) → zone likely breaks
    - Slow approach (overlapping, grinding candles)     → zone likely holds
    - Approach with structure breaks (CHoCH/BOS)        → momentum shifting

The tracker is stateful: it accumulates observations across cycles and
produces a summary that feeds into the next model call as context.

Symbol-agnostic. Strategy-agnostic. No side effects beyond returned state.

References:
    - Sam Seiden — "faster the approach, harder the bounce"
    - ICT — market structure shifts during price delivery
    - Al Brooks — bar-by-bar approach quality reading

Usage:
    from approach_tracker import ApproachTracker, ApproachSnapshot

    tracker = ApproachTracker()
    snapshot = tracker.observe(
        target_zone_id="M15_LIVE_L_4380",
        target_zone_low=4379.5,
        target_zone_high=4381.0,
        target_side="buy",
        live_price=4395.0,
        recent_bars=bars_m5,
        confirmations=confirmation_packet,
    )
    # Feed snapshot.to_dict() into the next Qwen call as prior_approach_context
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ApproachObservation:
    """Single point-in-time observation of price relative to target zone."""

    timestamp: float                    # monotonic or epoch
    live_price: float
    distance: float                     # signed: positive = price hasn't reached yet
    bar_overlap_ratio: float            # 0.0-1.0, how much recent bars overlap
    bar_trend_strength: float           # 0.0-1.0, directional consistency
    structure_event: str | None = None  # "choch_bearish", "bos_bullish", etc.
    candle_count: int = 0               # bars observed this cycle


@dataclass(slots=True)
class ApproachSnapshot:
    """Summary of approach quality across multiple observations.

    This is what gets serialized and fed to the model as prior_approach_context.
    """

    target_zone_id: str
    target_side: str                             # "buy" or "sell"
    target_zone_low: float
    target_zone_high: float
    observation_count: int
    elapsed_seconds: float
    initial_distance: float
    current_distance: float
    distance_trend: str                          # "closing", "stalling", "retreating"
    approach_speed: str                          # "fast", "moderate", "slow"
    overlap_quality: str                         # "trending", "mixed", "grinding"
    structure_events: list[str]                  # CHoCH/BOS events during approach
    price_reached_zone: bool
    assessment: str                              # "high_probability", "moderate", "low_probability"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_zone_id": self.target_zone_id,
            "target_side": self.target_side,
            "target_zone": [self.target_zone_low, self.target_zone_high],
            "observations": self.observation_count,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "initial_distance": round(self.initial_distance, 3),
            "current_distance": round(self.current_distance, 3),
            "distance_trend": self.distance_trend,
            "approach_speed": self.approach_speed,
            "overlap_quality": self.overlap_quality,
            "structure_events": self.structure_events,
            "price_reached_zone": self.price_reached_zone,
            "assessment": self.assessment,
        }

    def compact_log(self) -> str:
        return (
            f"approach:{self.target_zone_id} "
            f"dist={self.current_distance:.1f} "
            f"trend={self.distance_trend} "
            f"speed={self.approach_speed} "
            f"quality={self.overlap_quality} "
            f"reached={self.price_reached_zone} "
            f"assessment={self.assessment}"
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ApproachConfig:
    """Tuning per instrument class."""

    # Distance thresholds relative to zone height
    at_zone_multiple: float = 1.5         # within 1.5x zone height = "at zone"
    near_zone_multiple: float = 5.0       # within 5x zone height = "near"

    # Overlap: ratio of overlapping bars in last N
    trending_max_overlap: float = 0.3     # < 30% overlap = trending
    grinding_min_overlap: float = 0.6     # > 60% overlap = grinding

    # Speed: distance closed per observation
    fast_approach_points_per_obs: float = 2.0
    slow_approach_points_per_obs: float = 0.5

    # Minimum observations before assessment is meaningful
    min_observations: int = 2


DEFAULT_APPROACH_CONFIG = ApproachConfig()


# ---------------------------------------------------------------------------
# Core tracker
# ---------------------------------------------------------------------------

class ApproachTracker:
    """Tracks price approach quality to a target zone across cycles.

    Create one per active trade idea. Call observe() each cycle.
    Call snapshot() to get the current assessment.
    Call reset() when switching to a new target zone.
    """

    def __init__(self, config: ApproachConfig = DEFAULT_APPROACH_CONFIG) -> None:
        self._config = config
        self._target_zone_id: str = ""
        self._target_side: str = ""
        self._target_zone_low: float = 0.0
        self._target_zone_high: float = 0.0
        self._observations: list[ApproachObservation] = []
        self._structure_events: list[str] = []

    @property
    def active(self) -> bool:
        return bool(self._target_zone_id)

    @property
    def target_zone_id(self) -> str:
        return self._target_zone_id

    def reset(self) -> None:
        """Clear state for a new target zone."""
        self._target_zone_id = ""
        self._target_side = ""
        self._target_zone_low = 0.0
        self._target_zone_high = 0.0
        self._observations.clear()
        self._structure_events.clear()

    def observe(
        self,
        target_zone_id: str,
        target_zone_low: float,
        target_zone_high: float,
        target_side: str,
        live_price: float,
        recent_bars: Sequence[dict[str, Any]] | None = None,
        confirmations: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> ApproachSnapshot:
        """Record one observation and return the current snapshot.

        If target_zone_id changes from the previous call, state resets
        automatically — new zone, new approach tracking.
        """
        if target_zone_id != self._target_zone_id:
            self.reset()
            self._target_zone_id = target_zone_id
            self._target_side = target_side
            self._target_zone_low = target_zone_low
            self._target_zone_high = target_zone_high

        ts = timestamp or time.monotonic()
        bars = list(recent_bars or [])

        # Distance: positive means price hasn't reached zone yet (from approach side)
        distance = _signed_distance(
            live_price, target_zone_low, target_zone_high, target_side,
        )

        overlap_ratio = _bar_overlap_ratio(bars) if bars else 0.5
        trend_strength = _bar_trend_strength(bars, target_side) if bars else 0.5

        # Extract structure events from confirmations
        event = _extract_structure_event(confirmations)
        if event:
            self._structure_events.append(event)

        obs = ApproachObservation(
            timestamp=ts,
            live_price=live_price,
            distance=distance,
            bar_overlap_ratio=overlap_ratio,
            bar_trend_strength=trend_strength,
            structure_event=event,
            candle_count=len(bars),
        )
        self._observations.append(obs)

        return self.snapshot()

    def snapshot(self) -> ApproachSnapshot:
        """Current approach assessment from accumulated observations."""
        cfg = self._config
        obs = self._observations

        if not obs:
            return _empty_snapshot(self._target_zone_id, self._target_side,
                                   self._target_zone_low, self._target_zone_high)

        first = obs[0]
        last = obs[-1]
        elapsed = last.timestamp - first.timestamp if len(obs) > 1 else 0.0
        zone_height = max(self._target_zone_high - self._target_zone_low, 1.0)

        # Distance trend
        if len(obs) >= 2:
            recent_dists = [o.distance for o in obs[-3:]]
            if all(d <= recent_dists[0] for d in recent_dists[1:]):
                distance_trend = "closing"
            elif all(d >= recent_dists[0] for d in recent_dists[1:]):
                distance_trend = "retreating"
            else:
                distance_trend = "stalling"
        else:
            distance_trend = "initial"

        # Approach speed
        dist_covered = first.distance - last.distance
        n_obs = len(obs)
        speed_per_obs = dist_covered / n_obs if n_obs > 0 else 0.0
        if speed_per_obs >= cfg.fast_approach_points_per_obs:
            approach_speed = "fast"
        elif speed_per_obs >= cfg.slow_approach_points_per_obs:
            approach_speed = "moderate"
        else:
            approach_speed = "slow"

        # Overlap quality (average across observations)
        avg_overlap = sum(o.bar_overlap_ratio for o in obs) / len(obs)
        if avg_overlap <= cfg.trending_max_overlap:
            overlap_quality = "trending"
        elif avg_overlap >= cfg.grinding_min_overlap:
            overlap_quality = "grinding"
        else:
            overlap_quality = "mixed"

        # Has price reached the zone?
        price_reached = last.distance <= zone_height * cfg.at_zone_multiple

        # Overall assessment
        assessment = _assess_approach(
            approach_speed, overlap_quality, distance_trend,
            self._structure_events, self._target_side,
            len(obs) >= cfg.min_observations,
        )

        return ApproachSnapshot(
            target_zone_id=self._target_zone_id,
            target_side=self._target_side,
            target_zone_low=self._target_zone_low,
            target_zone_high=self._target_zone_high,
            observation_count=len(obs),
            elapsed_seconds=elapsed,
            initial_distance=first.distance,
            current_distance=last.distance,
            distance_trend=distance_trend,
            approach_speed=approach_speed,
            overlap_quality=overlap_quality,
            structure_events=list(self._structure_events[-5:]),
            price_reached_zone=price_reached,
            assessment=assessment,
        )

    def to_state(self) -> dict[str, Any]:
        """Serialize tracker state for persistence between restarts."""
        return {
            "target_zone_id": self._target_zone_id,
            "target_side": self._target_side,
            "target_zone_low": self._target_zone_low,
            "target_zone_high": self._target_zone_high,
            "observations": [
                {
                    "timestamp": o.timestamp,
                    "live_price": o.live_price,
                    "distance": o.distance,
                    "bar_overlap_ratio": o.bar_overlap_ratio,
                    "bar_trend_strength": o.bar_trend_strength,
                    "structure_event": o.structure_event,
                    "candle_count": o.candle_count,
                }
                for o in self._observations[-20:]  # keep last 20
            ],
            "structure_events": self._structure_events[-10:],
        }

    @classmethod
    def from_state(
        cls,
        state: dict[str, Any],
        config: ApproachConfig = DEFAULT_APPROACH_CONFIG,
    ) -> ApproachTracker:
        """Restore tracker from persisted state."""
        tracker = cls(config=config)
        tracker._target_zone_id = state.get("target_zone_id", "")
        tracker._target_side = state.get("target_side", "")
        tracker._target_zone_low = float(state.get("target_zone_low", 0))
        tracker._target_zone_high = float(state.get("target_zone_high", 0))
        tracker._structure_events = list(state.get("structure_events", []))
        for raw in state.get("observations", []):
            tracker._observations.append(ApproachObservation(
                timestamp=raw["timestamp"],
                live_price=raw["live_price"],
                distance=raw["distance"],
                bar_overlap_ratio=raw.get("bar_overlap_ratio", 0.5),
                bar_trend_strength=raw.get("bar_trend_strength", 0.5),
                structure_event=raw.get("structure_event"),
                candle_count=raw.get("candle_count", 0),
            ))
        return tracker


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _signed_distance(
    price: float, zone_low: float, zone_high: float, side: str,
) -> float:
    """Positive = price hasn't reached zone from the approach side."""
    if side == "buy":
        # Buy: price approaches zone from above (falling into demand)
        return price - zone_high if price > zone_high else 0.0
    else:
        # Sell: price approaches zone from below (rising into supply)
        return zone_low - price if price < zone_low else 0.0


def _bar_overlap_ratio(bars: Sequence[dict[str, Any]]) -> float:
    """Fraction of consecutive bar pairs that overlap significantly.

    High overlap = grinding/ranging. Low overlap = trending.
    """
    if len(bars) < 2:
        return 0.5
    overlaps = 0
    for i in range(1, len(bars)):
        prev_low = float(bars[i - 1]["low"])
        prev_high = float(bars[i - 1]["high"])
        curr_low = float(bars[i]["low"])
        curr_high = float(bars[i]["high"])
        overlap = min(prev_high, curr_high) - max(prev_low, curr_low)
        bar_range = max(curr_high - curr_low, 0.001)
        if overlap > bar_range * 0.5:
            overlaps += 1
    return overlaps / (len(bars) - 1)


def _bar_trend_strength(bars: Sequence[dict[str, Any]], side: str) -> float:
    """Fraction of bars that closed in the approach direction.

    For buy (approaching demand from above): bearish closes are "with" the approach.
    For sell (approaching supply from below): bullish closes are "with" the approach.
    """
    if not bars:
        return 0.5
    with_trend = 0
    for bar in bars:
        close = float(bar["close"])
        open_ = float(bar["open"])
        if side == "buy" and close < open_:
            with_trend += 1
        elif side == "sell" and close > open_:
            with_trend += 1
    return with_trend / len(bars)


def _extract_structure_event(confirmations: dict[str, Any] | None) -> str | None:
    """Pull the most significant structure event from confirmation packet."""
    if not confirmations:
        return None
    for tf in ("m15", "m5"):
        row = confirmations.get(tf) or {}
        if row.get("choch"):
            return f"{tf}_choch_{row['choch'].get('direction', 'unknown')}"
        if row.get("bos"):
            return f"{tf}_bos_{row['bos'].get('direction', 'unknown')}"
        sweep = row.get("liquidity_sweep") or {}
        if sweep.get("kind"):
            return f"{tf}_{sweep['kind']}"
    return None


def _assess_approach(
    speed: str,
    overlap: str,
    distance_trend: str,
    structure_events: list[str],
    side: str,
    enough_data: bool,
) -> str:
    """Combine factors into overall approach assessment.

    Professional logic (from supply/demand literature):
    - Slow, grinding approach to demand/supply → zone likely holds → HIGH probability
    - Fast, trending approach → zone likely breaks → LOW probability
    - Structure break in approach direction near zone → confirmation → boosts assessment
    """
    if not enough_data:
        return "insufficient_data"

    # Slow grinding approach = zone likely holds = good for entry
    if overlap == "grinding" and speed == "slow" and distance_trend == "closing":
        base = "high_probability"
    elif overlap == "trending" and speed == "fast":
        base = "low_probability"  # likely to blow through
    elif distance_trend == "retreating":
        base = "low_probability"  # price moving away
    elif distance_trend == "closing" and speed in ("moderate", "slow"):
        base = "moderate"
    else:
        base = "moderate"

    # Structure events can upgrade/downgrade
    if structure_events:
        last_event = structure_events[-1]
        # CHoCH against approach direction near zone = rejection starting = upgrade
        if side == "buy" and "choch_bullish" in last_event:
            if base == "moderate":
                base = "high_probability"
        elif side == "sell" and "choch_bearish" in last_event:
            if base == "moderate":
                base = "high_probability"

    return base


def _empty_snapshot(
    zone_id: str, side: str, zone_low: float, zone_high: float,
) -> ApproachSnapshot:
    return ApproachSnapshot(
        target_zone_id=zone_id,
        target_side=side,
        target_zone_low=zone_low,
        target_zone_high=zone_high,
        observation_count=0,
        elapsed_seconds=0.0,
        initial_distance=0.0,
        current_distance=0.0,
        distance_trend="initial",
        approach_speed="unknown",
        overlap_quality="unknown",
        structure_events=[],
        price_reached_zone=False,
        assessment="insufficient_data",
    )


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    tracker = ApproachTracker()
    assert not tracker.active

    # Simulate price approaching a demand zone from above
    snap = tracker.observe(
        target_zone_id="M15_L_4380",
        target_zone_low=4379.5,
        target_zone_high=4381.0,
        target_side="buy",
        live_price=4395.0,
        recent_bars=[
            {"open": 4397, "high": 4398, "low": 4394, "close": 4395},
            {"open": 4396, "high": 4397, "low": 4393, "close": 4394},
        ],
        timestamp=1000.0,
    )
    assert tracker.active
    assert snap.observation_count == 1
    assert snap.current_distance > 0

    # Second observation — price closer
    snap2 = tracker.observe(
        target_zone_id="M15_L_4380",
        target_zone_low=4379.5,
        target_zone_high=4381.0,
        target_side="buy",
        live_price=4388.0,
        recent_bars=[
            {"open": 4392, "high": 4393, "low": 4387, "close": 4388},
            {"open": 4390, "high": 4391, "low": 4386, "close": 4387},
        ],
        timestamp=1030.0,
    )
    assert snap2.observation_count == 2
    assert snap2.current_distance < snap.current_distance
    assert snap2.distance_trend == "closing"

    # Serialize and restore
    state = tracker.to_state()
    restored = ApproachTracker.from_state(state)
    snap3 = restored.snapshot()
    assert snap3.observation_count == snap2.observation_count
    assert snap3.target_zone_id == "M15_L_4380"

    # Switch zone — auto reset
    snap4 = tracker.observe(
        target_zone_id="M15_H_4420",
        target_zone_low=4419.0,
        target_zone_high=4421.0,
        target_side="sell",
        live_price=4410.0,
        timestamp=1060.0,
    )
    assert snap4.observation_count == 1
    assert snap4.target_zone_id == "M15_H_4420"

    # Compact log
    log = snap2.compact_log()
    assert "M15_L_4380" in log
    assert "closing" in log


if __name__ == "__main__":
    self_test()
    print("approach_tracker: all tests passed")
