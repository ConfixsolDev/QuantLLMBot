"""Zone quality scoring engine.

Scores supply/demand zones using the institutional 4-factor grading system
derived from Sam Seiden's odds enhancers and ICT order flow concepts:

    1. Freshness     — untested zones carry more unfilled orders
    2. Departure     — explosive moves away signal large imbalance
    3. Base time     — tight bases mean fast fills, more orders remain
    4. Profit margin — room to next opposing zone for R:R viability

Each factor scores 1–3 (weak/moderate/strong). Total 4–12.
Zones scoring 8+ are institutional-grade.

Symbol-agnostic. Strategy-agnostic. No side effects.

References:
    - Sam Seiden, Online Trading Academy — supply/demand odds enhancers
    - ICT (Michael Huddleston) — order blocks, fair value gaps
    - PriceActionNinja — zone grading methodology

Usage:
    from zone_scorer import score_zone, ZoneScore

    score = score_zone(
        zone=zone_dict,
        completed_bars=bars_list,
        opposing_zones=opposing_list,
        live_price=4395.0,
    )
    print(score.total, score.grade)  # 10, "A"
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Sequence


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ZoneScore:
    """Immutable quality score for a single zone."""

    zone_id: str
    freshness: int          # 1-3
    departure: int          # 1-3
    base_time: int          # 1-3
    profit_margin: int      # 1-3
    total: int = field(init=False)
    grade: str = field(init=False)
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        total = self.freshness + self.departure + self.base_time + self.profit_margin
        grade = "A" if total >= 10 else "B" if total >= 8 else "C" if total >= 6 else "D"
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "grade", grade)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "freshness": self.freshness,
            "departure": self.departure,
            "base_time": self.base_time,
            "profit_margin": self.profit_margin,
            "total": self.total,
            "grade": self.grade,
            "detail": self.detail,
        }


# ---------------------------------------------------------------------------
# Configuration — instrument-aware defaults
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ScoringConfig:
    """Tuning knobs per instrument class.

    Override for different pairs:
        gold_config = ScoringConfig(strong_departure_atr_multiple=2.5)
        fx_config   = ScoringConfig(strong_departure_atr_multiple=2.0, min_rr=2.0)
    """

    # Freshness
    max_tests_for_fresh: int = 1          # 0-1 tests = fresh
    stale_test_count: int = 3             # 3+ = stale

    # Departure strength (multiples of ATR or zone height)
    strong_departure_atr_multiple: float = 2.5
    moderate_departure_atr_multiple: float = 1.5

    # Base time (candle count at the zone)
    tight_base_max_candles: int = 2       # 1-2 candles = tight
    wide_base_max_candles: int = 5        # 3-5 = moderate; 6+ = wide

    # Profit margin (R:R to next opposing zone)
    min_rr: float = 1.5                   # below this = weak margin
    strong_rr: float = 3.0               # above this = strong margin


DEFAULT_CONFIG = ScoringConfig()


# ---------------------------------------------------------------------------
# Scoring functions — each returns 1-3
# ---------------------------------------------------------------------------

def _score_freshness(
    test_count: int,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> tuple[int, dict[str, Any]]:
    """Untested zones are strongest — orders remain unfilled."""
    if test_count <= config.max_tests_for_fresh:
        return 3, {"test_count": test_count, "assessment": "fresh"}
    if test_count < config.stale_test_count:
        return 2, {"test_count": test_count, "assessment": "tested"}
    return 1, {"test_count": test_count, "assessment": "stale"}


def _score_departure(
    zone: dict[str, Any],
    completed_bars: Sequence[dict[str, Any]],
    config: ScoringConfig = DEFAULT_CONFIG,
) -> tuple[int, dict[str, Any]]:
    """How explosively did price leave the zone?

    Measures the largest single-bar range in the 3 bars immediately after
    the zone was formed, compared to the average bar range (proxy ATR).
    """
    zone_low = float(zone.get("zone_low", 0))
    zone_high = float(zone.get("zone_high", zone_low))
    zone_mid = (zone_low + zone_high) / 2.0

    if not completed_bars or len(completed_bars) < 5:
        return 2, {"reason": "insufficient_bars"}

    # Calculate average bar range as ATR proxy
    ranges = [float(b["high"]) - float(b["low"]) for b in completed_bars[-20:]]
    avg_range = sum(ranges) / len(ranges) if ranges else 1.0
    if avg_range <= 0:
        avg_range = 1.0

    # Find the departure: largest bar range in the 3 bars after zone formation
    # Zone source candles tell us where the zone was born
    source_ids = set(zone.get("source_candle_ids") or [])
    departure_start = None
    for i, bar in enumerate(completed_bars):
        if bar.get("evidence_id") in source_ids:
            departure_start = i + 1
    if departure_start is None:
        # Fallback: find bars near the zone price
        for i, bar in enumerate(completed_bars):
            bar_mid = (float(bar["high"]) + float(bar["low"])) / 2.0
            if abs(bar_mid - zone_mid) < avg_range * 0.5:
                departure_start = i + 1
                break

    if departure_start is None or departure_start >= len(completed_bars):
        return 2, {"reason": "zone_origin_not_found"}

    departure_bars = completed_bars[departure_start:departure_start + 3]
    if not departure_bars:
        return 2, {"reason": "no_departure_bars"}

    max_departure = max(float(b["high"]) - float(b["low"]) for b in departure_bars)
    ratio = max_departure / avg_range

    detail = {
        "max_departure_range": round(max_departure, 3),
        "avg_bar_range": round(avg_range, 3),
        "atr_multiple": round(ratio, 2),
    }

    if ratio >= config.strong_departure_atr_multiple:
        return 3, {**detail, "assessment": "explosive"}
    if ratio >= config.moderate_departure_atr_multiple:
        return 2, {**detail, "assessment": "moderate"}
    return 1, {**detail, "assessment": "weak"}


def _score_base_time(
    zone: dict[str, Any],
    completed_bars: Sequence[dict[str, Any]],
    config: ScoringConfig = DEFAULT_CONFIG,
) -> tuple[int, dict[str, Any]]:
    """How long did price consolidate at the zone?

    Fewer candles at the base = more unfilled orders remain.
    """
    zone_low = float(zone.get("zone_low", 0))
    zone_high = float(zone.get("zone_high", zone_low))

    candles_in_zone = 0
    for bar in completed_bars:
        bar_low = float(bar["low"])
        bar_high = float(bar["high"])
        # Bar overlaps the zone
        if bar_low <= zone_high and bar_high >= zone_low:
            candles_in_zone += 1

    detail = {"candles_in_zone": candles_in_zone}

    if candles_in_zone <= config.tight_base_max_candles:
        return 3, {**detail, "assessment": "tight"}
    if candles_in_zone <= config.wide_base_max_candles:
        return 2, {**detail, "assessment": "moderate"}
    return 1, {**detail, "assessment": "wide"}


def _score_profit_margin(
    zone: dict[str, Any],
    opposing_zones: Sequence[dict[str, Any]],
    live_price: float,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> tuple[int, dict[str, Any]]:
    """Room to the next opposing zone — is the R:R viable?

    For a demand zone (buy), the opposing zone is the nearest supply above.
    For a supply zone (sell), the opposing zone is the nearest demand below.
    """
    zone_low = float(zone.get("zone_low", 0))
    zone_high = float(zone.get("zone_high", zone_low))
    zone_mid = (zone_low + zone_high) / 2.0
    zone_height = zone_high - zone_low if zone_high > zone_low else 1.0

    kind = str(zone.get("kind", zone.get("pattern", ""))).lower()
    is_demand = "low" in kind or "bottom" in kind or "demand" in kind
    is_supply = "high" in kind or "top" in kind or "supply" in kind

    # Determine risk (zone edge to invalidation — approximate as zone height + buffer)
    risk = zone_height + 3.0  # small buffer beyond zone

    # Find nearest opposing zone
    target_distance = None
    for opp in opposing_zones:
        opp_mid = (float(opp.get("zone_low", 0)) + float(opp.get("zone_high", 0))) / 2.0
        if is_demand and opp_mid > zone_mid:
            dist = opp_mid - zone_mid
            if target_distance is None or dist < target_distance:
                target_distance = dist
        elif is_supply and opp_mid < zone_mid:
            dist = zone_mid - opp_mid
            if target_distance is None or dist < target_distance:
                target_distance = dist

    if target_distance is None:
        # No opposing zone found — use distance from live price as proxy
        target_distance = abs(live_price - zone_mid)

    rr = target_distance / risk if risk > 0 else 0.0
    detail = {
        "risk": round(risk, 3),
        "target_distance": round(target_distance, 3),
        "rr_ratio": round(rr, 2),
    }

    if rr >= config.strong_rr:
        return 3, {**detail, "assessment": "excellent"}
    if rr >= config.min_rr:
        return 2, {**detail, "assessment": "viable"}
    return 1, {**detail, "assessment": "thin"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_zone(
    zone: dict[str, Any],
    completed_bars: Sequence[dict[str, Any]],
    opposing_zones: Sequence[dict[str, Any]] | None = None,
    live_price: float = 0.0,
    config: ScoringConfig = DEFAULT_CONFIG,
) -> ZoneScore:
    """Score a single zone on the 4-factor institutional grading system.

    Args:
        zone: Zone dict with zone_low, zone_high, test_count, source_candle_ids,
              kind/pattern, level_id.
        completed_bars: Closed OHLC bars for the zone's timeframe.
        opposing_zones: Zones on the opposite side for profit margin calc.
        live_price: Current market mid price.
        config: Instrument-specific scoring parameters.

    Returns:
        ZoneScore with per-factor scores (1-3), total (4-12), grade (A-D).
    """
    test_count = int(zone.get("test_count", 0))
    freshness, f_detail = _score_freshness(test_count, config)
    departure, d_detail = _score_departure(zone, completed_bars, config)
    base_time, b_detail = _score_base_time(zone, completed_bars, config)
    profit_margin, p_detail = _score_profit_margin(
        zone, opposing_zones or [], live_price, config,
    )

    return ZoneScore(
        zone_id=str(zone.get("level_id") or zone.get("id") or "unknown"),
        freshness=freshness,
        departure=departure,
        base_time=base_time,
        profit_margin=profit_margin,
        detail={
            "freshness": f_detail,
            "departure": d_detail,
            "base_time": b_detail,
            "profit_margin": p_detail,
        },
    )


def score_zones(
    zones: Sequence[dict[str, Any]],
    completed_bars: Sequence[dict[str, Any]],
    live_price: float = 0.0,
    config: ScoringConfig = DEFAULT_CONFIG,
    min_grade: str = "D",
) -> list[ZoneScore]:
    """Score multiple zones, split into demand/supply for opposing-zone calc.

    Returns scores sorted by total descending (best first).
    Optionally filters by min_grade ("A", "B", "C", "D").
    """
    kind_map = {"A": 10, "B": 8, "C": 6, "D": 4}
    min_total = kind_map.get(min_grade, 4)

    demand = [z for z in zones if _is_demand(z)]
    supply = [z for z in zones if not _is_demand(z)]

    scores: list[ZoneScore] = []
    for zone in zones:
        opposing = supply if _is_demand(zone) else demand
        s = score_zone(zone, completed_bars, opposing, live_price, config)
        if s.total >= min_total:
            scores.append(s)

    scores.sort(key=lambda s: s.total, reverse=True)
    return scores


def compact_score_log(scores: Sequence[ZoneScore], limit: int = 5) -> str:
    """One-line log summary of top scored zones."""
    parts = []
    for s in scores[:limit]:
        parts.append(f"{s.zone_id}:{s.grade}({s.total})")
    return " ".join(parts) if parts else "no_scored_zones"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_demand(zone: dict[str, Any]) -> bool:
    kind = str(zone.get("kind", zone.get("pattern", ""))).lower()
    return "low" in kind or "bottom" in kind or "demand" in kind


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    zone = {
        "level_id": "M15_LIVE_L_4380",
        "zone_low": 4379.5,
        "zone_high": 4381.0,
        "kind": "low",
        "test_count": 0,
        "source_candle_ids": ["bar_5"],
    }
    bars = [
        {"evidence_id": f"bar_{i}", "open": 4380 + i, "high": 4382 + i,
         "low": 4378 + i, "close": 4381 + i}
        for i in range(20)
    ]
    opposing = [{"zone_low": 4410.0, "zone_high": 4412.0, "kind": "high"}]

    score = score_zone(zone, bars, opposing, live_price=4390.0)
    assert score.total >= 4
    assert score.total <= 12
    assert score.grade in ("A", "B", "C", "D")
    assert score.zone_id == "M15_LIVE_L_4380"

    scores = score_zones([zone], bars, live_price=4390.0)
    assert len(scores) >= 1

    log = compact_score_log(scores)
    assert "M15_LIVE_L_4380" in log

    # Verify frozen dataclass
    try:
        score.freshness = 1  # type: ignore
        assert False, "should be immutable"
    except AttributeError:
        pass


if __name__ == "__main__":
    self_test()
    print("zone_scorer: all tests passed")
