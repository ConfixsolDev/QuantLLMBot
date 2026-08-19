"""Detect Break of Structure (BOS), Change of Character (CHoCH), and
Market Structure Shift (MSS) events from swing point data and candle
displacement.

ICT/SMC market structure event detection for XAUUSD scalping:

    BOS   -- price breaks a swing point IN the direction of the current trend.
             Confirms continuation.  Bullish BOS = new HH in uptrend,
             bearish BOS = new LL in downtrend.

    CHoCH -- price breaks a swing point AGAINST the current trend.
             First signal of potential reversal.  Bearish CHoCH in uptrend =
             price breaks below the last Higher Low.  Bullish CHoCH in
             downtrend = price breaks above the last Lower High.

    MSS   -- CHoCH with displacement (impulsive break candle: large body,
             small wicks relative to body).  Higher-conviction reversal.

Events are deduped per (broken_level, timeframe) so the same swing break
does not fire twice.

2026-08-18
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_MAX_EVENTS = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _displacement(candle: dict) -> tuple[float, float, bool]:
    """Return (body_range_ratio, body_pts, is_displacement) for *candle*."""
    o = float(candle["open"])
    h = float(candle["high"])
    l = float(candle["low"])
    c = float(candle["close"])
    body = abs(c - o)
    range_ = h - l
    ratio = body / range_ if range_ > 0 else 0.0
    return round(ratio, 4), round(body, 4), (ratio > 0.6 and body > 1.5)


def _candle_direction(candle: dict) -> str:
    c, o = float(candle["close"]), float(candle["open"])
    if c > o:
        return "bullish"
    if c < o:
        return "bearish"
    return "neutral"


def _swing_by_kind(swings: list[dict], kind: str) -> dict | None:
    """Most recent swing of *kind* ('high' or 'low')."""
    for sw in reversed(swings):
        if sw.get("kind") == kind:
            return sw
    return None


def _dedup_key(timeframe: str, broken_level: float) -> str:
    return f"{timeframe}:{broken_level}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class StructuralEventDetector:
    """Detect BOS / CHoCH / MSS from swing points and live price."""

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._last_event_by_tf: dict[str, dict] = {}
        self._seen_keys: set[str] = set()      # dedup broken_level+tf

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        timeframe: str,
        candles: list[dict],
        swings: list[dict],
        current_structure: str,
        current_price: float,
    ) -> list[dict]:
        """Detect structural events from swing points and current price.

        Args:
            timeframe: ``"M5"``, ``"M15"``, ``"H1"``, etc.
            candles: recent OHLC candle dicts (last 10-20).
            swings: swing points from structure_tracker
                    ``[{kind, price, time, evidence_id}, ...]``
            current_structure: ``"bullish"`` / ``"bearish"`` / ``"ranging"``
                               from structure_tracker.
            current_price: live price.

        Returns:
            List of new events detected this cycle.
        """
        if not swings or not candles:
            return []

        new_events: list[dict] = []

        last_high = _swing_by_kind(swings, "high")
        last_low = _swing_by_kind(swings, "low")
        break_candle = candles[-1]
        candle_close = float(break_candle["close"])

        # --- BOS -------------------------------------------------------
        if current_structure == "bullish" and last_high:
            level = float(last_high["price"])
            if candle_close > level:
                evt = self._make_event(
                    "BOS", "bullish", timeframe, level, last_high,
                    break_candle, current_price,
                )
                if evt:
                    new_events.append(evt)

        if current_structure == "bearish" and last_low:
            level = float(last_low["price"])
            if candle_close < level:
                evt = self._make_event(
                    "BOS", "bearish", timeframe, level, last_low,
                    break_candle, current_price,
                )
                if evt:
                    new_events.append(evt)

        # --- CHoCH / MSS ----------------------------------------------
        if current_structure == "bullish" and last_low:
            level = float(last_low["price"])
            if candle_close < level:
                ratio, body_pts, has_disp = _displacement(break_candle)
                event_type = "MSS" if has_disp else "CHoCH"
                evt = self._make_event(
                    event_type, "bearish", timeframe, level, last_low,
                    break_candle, current_price,
                )
                if evt:
                    new_events.append(evt)

        if current_structure == "bearish" and last_high:
            level = float(last_high["price"])
            if candle_close > level:
                ratio, body_pts, has_disp = _displacement(break_candle)
                event_type = "MSS" if has_disp else "CHoCH"
                evt = self._make_event(
                    event_type, "bullish", timeframe, level, last_high,
                    break_candle, current_price,
                )
                if evt:
                    new_events.append(evt)

        # bookkeeping
        for evt in new_events:
            self._events.append(evt)
            self._last_event_by_tf[timeframe] = evt
            logger.info(
                "%s detected | tf=%s dir=%s level=%.2f disp=%.2f conf=%s",
                evt["event_type"], timeframe, evt["direction"],
                evt["broken_level"], evt["displacement"], evt["confidence"],
            )

        # trim rolling buffer
        if len(self._events) > _MAX_EVENTS:
            removed = self._events[:-_MAX_EVENTS]
            self._events = self._events[-_MAX_EVENTS:]
            for r in removed:
                key = _dedup_key(r["timeframe"], r["broken_level"])
                self._seen_keys.discard(key)

        return new_events

    def last_event(self, timeframe: str | None = None) -> dict | None:
        """Most recent structural event, optionally filtered by *timeframe*."""
        if timeframe is not None:
            return self._last_event_by_tf.get(timeframe)
        return self._events[-1] if self._events else None

    def active_events(self, max_age_minutes: int = 60) -> list[dict]:
        """Events still relevant (not older than *max_age_minutes*)."""
        cutoff = datetime.now(timezone.utc)
        result: list[dict] = []
        for evt in reversed(self._events):
            try:
                ts = datetime.fromisoformat(evt["detected_at_utc"])
            except (KeyError, ValueError):
                continue
            age = (cutoff - ts).total_seconds() / 60.0
            if age <= max_age_minutes:
                result.append(evt)
            else:
                break  # events are chronological; older ones follow
        return list(reversed(result))

    def snapshot(self) -> dict:
        """Current structural event state across all timeframes."""
        return {
            "total_events": len(self._events),
            "last_event_by_tf": dict(self._last_event_by_tf),
            "active_events_60m": self.active_events(60),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_event(
        self,
        event_type: str,
        direction: str,
        timeframe: str,
        broken_level: float,
        broken_swing: dict,
        break_candle: dict,
        current_price: float,
    ) -> dict | None:
        """Build an event dict, returning *None* if already seen."""
        key = _dedup_key(timeframe, broken_level)
        if key in self._seen_keys:
            return None
        self._seen_keys.add(key)

        ratio, body_pts, has_disp = _displacement(break_candle)

        # confidence
        if event_type == "MSS":
            confidence = "high"
        elif event_type == "CHoCH":
            confidence = "medium"
        else:
            # BOS — continuation
            confidence = "medium"

        return {
            "event_type": event_type,
            "direction": direction,
            "timeframe": timeframe,
            "broken_level": broken_level,
            "broken_swing": dict(broken_swing),
            "displacement": ratio,
            "displacement_pts": body_pts,
            "break_candle": dict(break_candle),
            # Event age belongs to the closed break candle, not the process
            # restart that rediscovered it. Otherwise old BOS/CHoCH appears
            # freshly actionable after every restart.
            "detected_at_utc": (
                break_candle.get("close_time_utc")
                or break_candle.get("closed_at_utc")
                or _now_utc()
            ),
            "confidence": confidence,
        }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Smoke test for StructuralEventDetector."""
    det = StructuralEventDetector()

    # Build synthetic swings
    swings = [
        {"kind": "low",  "price": 2380.0, "time": "2026-08-18T10:00:00Z", "evidence_id": "s1"},
        {"kind": "high", "price": 2400.0, "time": "2026-08-18T10:05:00Z", "evidence_id": "s2"},
        {"kind": "low",  "price": 2385.0, "time": "2026-08-18T10:10:00Z", "evidence_id": "s3"},
        {"kind": "high", "price": 2405.0, "time": "2026-08-18T10:15:00Z", "evidence_id": "s4"},
    ]

    # --- Test BOS (bullish continuation) ---
    # Candle closes above last swing high (2405)
    bos_candle = {"open": 2404.0, "high": 2408.0, "low": 2403.5, "close": 2407.5}
    candles = [bos_candle]
    events = det.detect("M15", candles, swings, "bullish", 2407.5)
    assert len(events) == 1, f"Expected 1 BOS event, got {len(events)}"
    assert events[0]["event_type"] == "BOS"
    assert events[0]["direction"] == "bullish"
    assert events[0]["broken_level"] == 2405.0
    logger.info("PASS: bullish BOS detected")

    # --- Test dedup: same swing should NOT fire again ---
    events2 = det.detect("M15", candles, swings, "bullish", 2407.5)
    assert len(events2) == 0, "Dedup failed: same BOS fired twice"
    logger.info("PASS: BOS dedup works")

    # --- Test CHoCH (bearish reversal in uptrend) ---
    det2 = StructuralEventDetector()
    # Candle closes below last swing low (2385) — small body, no displacement
    choch_candle = {"open": 2386.0, "high": 2387.0, "low": 2383.0, "close": 2384.0}
    events3 = det2.detect("M15", [choch_candle], swings, "bullish", 2384.0)
    assert len(events3) == 1, f"Expected 1 CHoCH event, got {len(events3)}"
    assert events3[0]["event_type"] == "CHoCH"
    assert events3[0]["direction"] == "bearish"
    logger.info("PASS: bearish CHoCH detected")

    # --- Test MSS (CHoCH with displacement) ---
    det3 = StructuralEventDetector()
    # Large body candle closes below last swing low — displacement
    mss_candle = {"open": 2388.0, "high": 2388.5, "low": 2383.0, "close": 2383.5}
    events4 = det3.detect("M15", [mss_candle], swings, "bullish", 2383.5)
    assert len(events4) == 1, f"Expected 1 MSS event, got {len(events4)}"
    assert events4[0]["event_type"] == "MSS"
    assert events4[0]["direction"] == "bearish"
    assert events4[0]["confidence"] == "high"
    logger.info("PASS: bearish MSS detected (CHoCH + displacement)")

    # --- Test last_event / active_events / snapshot ---
    last = det3.last_event("M15")
    assert last is not None and last["event_type"] == "MSS"
    assert det3.last_event("H1") is None

    active = det3.active_events(max_age_minutes=1)
    assert len(active) == 1

    snap = det3.snapshot()
    assert snap["total_events"] == 1
    logger.info("PASS: last_event / active_events / snapshot OK")

    # --- Test bullish CHoCH in bearish structure ---
    det4 = StructuralEventDetector()
    bearish_swings = [
        {"kind": "high", "price": 2400.0, "time": "2026-08-18T11:00:00Z", "evidence_id": "s5"},
        {"kind": "low",  "price": 2390.0, "time": "2026-08-18T11:05:00Z", "evidence_id": "s6"},
        {"kind": "high", "price": 2395.0, "time": "2026-08-18T11:10:00Z", "evidence_id": "s7"},
        {"kind": "low",  "price": 2385.0, "time": "2026-08-18T11:15:00Z", "evidence_id": "s8"},
    ]
    # Candle closes above last LH (2395) — no displacement
    choch_bull = {"open": 2394.0, "high": 2397.0, "low": 2393.0, "close": 2396.0}
    events5 = det4.detect("M5", [choch_bull], bearish_swings, "bearish", 2396.0)
    assert len(events5) == 1
    assert events5[0]["event_type"] == "CHoCH"
    assert events5[0]["direction"] == "bullish"
    logger.info("PASS: bullish CHoCH in bearish structure")

    # --- Test bearish BOS ---
    det5 = StructuralEventDetector()
    # Candle closes below last swing low (2385) in bearish structure
    bos_bear = {"open": 2386.0, "high": 2387.0, "low": 2383.0, "close": 2384.0}
    events6 = det5.detect("M5", [bos_bear], bearish_swings, "bearish", 2384.0)
    assert len(events6) == 1
    assert events6[0]["event_type"] == "BOS"
    assert events6[0]["direction"] == "bearish"
    logger.info("PASS: bearish BOS detected")

    # --- Test rolling buffer trim ---
    det6 = StructuralEventDetector()
    for i in range(60):
        sw = [
            {"kind": "high", "price": 3000.0 + i, "time": f"T{i}", "evidence_id": f"x{i}"},
            {"kind": "low",  "price": 2900.0 - i, "time": f"T{i}", "evidence_id": f"y{i}"},
        ]
        c = {"open": 3000.0 + i - 1, "high": 3002.0 + i, "low": 2999.0 + i, "close": 3001.0 + i}
        det6.detect("M1", [c], sw, "bullish", 3001.0 + i)
    assert len(det6._events) <= _MAX_EVENTS, "Rolling buffer not trimmed"
    logger.info("PASS: rolling buffer trim (%d events)", len(det6._events))

    # --- Test empty inputs ---
    det7 = StructuralEventDetector()
    assert det7.detect("M5", [], swings, "bullish", 2400.0) == []
    assert det7.detect("M5", candles, [], "bullish", 2400.0) == []
    logger.info("PASS: empty inputs return []")

    logger.info("structural_event self_test PASSED")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    self_test()
