"""Clean-room statistical zone engine.

The engine describes observed acceptance/rejection evidence. It does not
choose direction, create candidates, size risk, or call a broker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from statistics import median
from typing import Iterable

from vnext.data.bars import Bar


LIFECYCLE = ("CANDIDATE", "FORMING", "FRESH", "ACTIVE", "TESTED", "BROKEN", "RECLAIMED", "INVALID")
ALLOWED = {
    "CANDIDATE": {"FORMING", "INVALID"}, "FORMING": {"FRESH", "INVALID"},
    "FRESH": {"ACTIVE", "TESTED", "BROKEN", "INVALID"},
    "ACTIVE": {"TESTED", "BROKEN", "INVALID"},
    "TESTED": {"TESTED", "BROKEN", "RECLAIMED", "INVALID"},
    "BROKEN": {"RECLAIMED", "INVALID"}, "RECLAIMED": {"TESTED", "BROKEN", "INVALID"},
    "INVALID": set(),
}


@dataclass(frozen=True, slots=True)
class ZoneInteraction:
    observed_at_utc: datetime
    kind: str
    penetration: float
    normalized_penetration: float | None
    close_inside_core: bool


@dataclass(frozen=True, slots=True)
class Zone:
    pair: str
    timeframe: str
    zone_id: str
    lower: float
    upper: float
    acceptance_density: float
    upper_rejection_p90: float
    lower_rejection_p90: float
    lifecycle_state: str
    created_at_utc: datetime
    algorithm_version: str = "ZONE_V1"
    contributing_bars: tuple[str, ...] = ()
    interactions: tuple[ZoneInteraction, ...] = ()
    birth_context: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.lifecycle_state not in LIFECYCLE or self.upper <= self.lower:
            raise ValueError("invalid zone geometry or lifecycle")
        if self.acceptance_density < 0:
            raise ValueError("acceptance density cannot be negative")

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, price: float) -> bool:
        return self.lower <= price <= self.upper

    def transition(self, state: str) -> "Zone":
        if state not in ALLOWED[self.lifecycle_state]:
            raise ValueError(f"invalid zone transition {self.lifecycle_state}->{state}")
        return replace(self, lifecycle_state=state)

    def as_dict(self) -> dict:
        return {
            "pair": self.pair, "timeframe": self.timeframe, "zone_id": self.zone_id,
            "lower": self.lower, "upper": self.upper, "width": self.width,
            "acceptance_density": self.acceptance_density,
            "upper_rejection_p90": self.upper_rejection_p90,
            "lower_rejection_p90": self.lower_rejection_p90,
            "lifecycle_state": self.lifecycle_state,
            "created_at_utc": self.created_at_utc.isoformat(),
            "algorithm_version": self.algorithm_version,
            "contributing_bars": list(self.contributing_bars),
            "birth_context": dict(self.birth_context),
        }


class ZoneEngine:
    """Build statistically inspectable acceptance regions from closed bars."""

    def __init__(self, *, algorithm_version: str = "ZONE_V1") -> None:
        self.algorithm_version = algorithm_version

    def discover(self, bars: Iterable[Bar], *, pair: str, timeframe: str,
                 volatility: float | None = None) -> list[Zone]:
        rows = [bar for bar in bars if bar.pair == pair and bar.timeframe == timeframe]
        rows.sort(key=lambda bar: bar.start_utc)
        if not rows:
            return []
        # R&D baseline: deterministic 1D clustering of body midpoints. The
        # tolerance is volatility-scaled, so nearby bodies form one acceptance
        # area while separated price populations become distinct zones.
        ranges = [max(bar.high - bar.low, 1e-9) for bar in rows]
        tolerance = max(float(volatility or median(ranges)), 1e-9)
        ordered = sorted(rows, key=lambda bar: (min(bar.open, bar.close) + max(bar.open, bar.close)) / 2)
        clusters: list[list[Bar]] = []
        for bar in ordered:
            midpoint = (min(bar.open, bar.close) + max(bar.open, bar.close)) / 2
            if not clusters:
                clusters.append([bar])
                continue
            prior = clusters[-1]
            prior_midpoint = median((min(item.open, item.close) + max(item.open, item.close)) / 2 for item in prior)
            if midpoint - prior_midpoint <= tolerance:
                prior.append(bar)
            else:
                clusters.append([bar])
        minimum_count = max(2, len(rows) // 50)
        selected = [cluster for cluster in clusters if len(cluster) >= minimum_count] or [rows]
        result: list[Zone] = []
        for index, cluster in enumerate(selected):
            body_lows = [min(bar.open, bar.close) for bar in cluster]
            body_highs = [max(bar.open, bar.close) for bar in cluster]
            lower, upper = median(body_lows), median(body_highs)
            if upper <= lower:
                width = tolerance
                lower, upper = lower - width / 2, upper + width / 2
            upper_rejections = [max(0.0, bar.high - upper) for bar in cluster]
            lower_rejections = [max(0.0, lower - bar.low) for bar in cluster]
            zone_hash = hashlib.sha256(
                f"{pair}|{timeframe}|{rows[0].start_utc.isoformat()}|{rows[-1].end_utc.isoformat()}|{index}|{len(cluster)}".encode()
            ).hexdigest()[:16]
            density = sum(lower <= min(bar.open, bar.close) and max(bar.open, bar.close) <= upper for bar in cluster) / len(cluster)
            result.append(Zone(
                pair=pair, timeframe=timeframe, zone_id=f"{timeframe}-{zone_hash}",
                lower=lower, upper=upper, acceptance_density=round(density, 6),
                upper_rejection_p90=self._quantile(upper_rejections, 0.90),
                lower_rejection_p90=self._quantile(lower_rejections, 0.90),
                lifecycle_state="FRESH", created_at_utc=max(bar.end_utc for bar in cluster),
                algorithm_version=self.algorithm_version,
                contributing_bars=tuple(bar.start_utc.isoformat() for bar in sorted(cluster, key=lambda bar: bar.start_utc)),
                birth_context={"bar_count": len(cluster), "volatility": volatility, "cluster_tolerance": tolerance},
            ))
        return result

    def interact(self, zone: Zone, bar: Bar, *, volatility: float | None = None) -> tuple[Zone, ZoneInteraction]:
        penetration = max(zone.lower - bar.low, bar.high - zone.upper, 0.0)
        inside = zone.contains(bar.close)
        if penetration == 0 and inside:
            kind = "ACCEPTED" if min(bar.open, bar.close) >= zone.lower and max(bar.open, bar.close) <= zone.upper else "TOUCH"
        elif penetration > 0 and inside:
            kind = "REJECTED"
        else:
            kind = "BROKEN"
        interaction = ZoneInteraction(bar.end_utc, kind, penetration,
                                      penetration / volatility if volatility and volatility > 0 else None,
                                      inside)
        state = zone.lifecycle_state
        if kind == "BROKEN" and state not in {"BROKEN", "INVALID"}:
            state = "BROKEN"
        elif kind == "REJECTED" and state in {"FRESH", "ACTIVE"}:
            state = "TESTED"
        elif kind == "ACCEPTED" and state == "BROKEN":
            state = "RECLAIMED"
        return replace(zone, lifecycle_state=state, interactions=zone.interactions + (interaction,)), interaction

    @staticmethod
    def _quantile(values: list[float], q: float) -> float:
        values = sorted(values)
        if not values:
            return 0.0
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * q))))
        return round(float(values[index]), 8)
