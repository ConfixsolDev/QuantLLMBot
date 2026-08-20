"""Instrument-agnostic Order Block (OB) detector.

Identifies Order Blocks -- the last opposing candle before a structural
break (BOS / CHoCH / MSS).  These mark institutional entry points where
smart money accumulated positions.

    Bullish OB:  last *bearish* candle before a bullish structural break.
                 Zone = candle body (open to close).  Price returning here
                 is a buy opportunity.

    Bearish OB:  last *bullish* candle before a bearish structural break.
                 Zone = candle body.  Price returning here is a sell
                 opportunity.

When price returns to the zone the same institutions are expected to
defend the level.  Mitigation occurs when price trades *through* the
zone, invalidating it.

Part of an ICT / SMC market-structure trading system.

No project imports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

MAX_OBS_PER_TF: int = 15            # cap per timeframe
STALE_CANDLE_LIMIT: int = 150        # expire after 150 candles
MITIGATION_THRESHOLD: float = 0.90   # >= 90 % mitigated  =>  fully mitigated
LOOKBACK_WINDOW: int = 10            # how many candles to scan before break
ZONE_TOUCH_TOLERANCE: float = 0.20   # points tolerance for "touched the edge"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_id(timeframe: str, direction: str, created_at: str,
                 low: float, high: float) -> str:
    return f"ob:{timeframe}:{direction}:{created_at}:{low:.2f}-{high:.2f}"


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_candle_index(candles: list[dict], break_candle: dict) -> int | None:
    """Match *break_candle* in *candles* by evidence_id or closed_at_utc."""
    eid = break_candle.get("evidence_id")
    cat = break_candle.get("closed_at_utc")

    for i, c in enumerate(candles):
        if eid and c.get("evidence_id") == eid:
            return i
        if cat and c.get("closed_at_utc") == cat:
            return i
    return None


def _compute_mitigation(ob: dict, price: float) -> float:
    """Return mitigation percentage (0-1) for *price* relative to *ob* zone."""
    width = ob["high"] - ob["low"]
    if width <= 0:
        return 0.0

    if ob["direction"] == "bullish":
        # Bullish OB mitigated when price drops through ob low.
        if price >= ob["high"]:
            return 0.0
        if price <= ob["low"]:
            return 1.0
        return (ob["high"] - price) / width

    else:  # bearish
        # Bearish OB mitigated when price rises through ob high.
        if price <= ob["low"]:
            return 0.0
        if price >= ob["high"]:
            return 1.0
        return (price - ob["low"]) / width


def _status_from_mitigation(pct: float) -> str:
    if pct >= MITIGATION_THRESHOLD:
        return "mitigated"
    if pct > 0.0:
        return "active"  # partially entered but still valid
    return "active"


def _touches_zone_edge(
    ob: dict, price: float, tolerance: float = ZONE_TOUCH_TOLERANCE
) -> bool:
    """True when *price* is within tolerance of the OB zone edge."""
    if ob["direction"] == "bullish":
        return abs(price - ob["high"]) <= tolerance
    else:
        return abs(price - ob["low"]) <= tolerance


# ---------------------------------------------------------------------------
# TF strength ordering (higher TF = stronger OB)
# ---------------------------------------------------------------------------

_TF_RANK: dict[str, int] = {
    "M1": 1, "M5": 2, "M15": 3, "M30": 4,
    "H1": 5, "H4": 6, "D1": 7, "W1": 8,
}


# ---------------------------------------------------------------------------
# OrderBlockDetector
# ---------------------------------------------------------------------------

class OrderBlockDetector:
    """Detect and track Order Blocks across multiple timeframes."""

    def __init__(self, touch_tolerance: float = ZONE_TOUCH_TOLERANCE) -> None:
        self.touch_tolerance = float(touch_tolerance)
        self._active_obs: dict[str, list[dict]] = {}   # tf -> list of OBs
        self._candle_counts: dict[str, int] = {}        # tf -> candles seen
        self._processed_events: set[str] = set()        # dedup event keys

    # ------------------------------------------------------------------
    # detect
    # ------------------------------------------------------------------

    def detect(
        self,
        timeframe: str,
        candles: list[dict],
        structural_events: list[dict],
    ) -> list[dict]:
        """Identify order blocks from structural events.

        Args:
            timeframe: ``"M5"``, ``"M15"``, etc.
            candles: OHLC candle dicts with keys ``open``, ``high``,
                ``low``, ``close``, ``evidence_id``, ``closed_at_utc``.
            structural_events: events from structural_event.py
                ``[{event_type, direction, break_candle, ...}]``

        Returns:
            List of *newly detected* order blocks this cycle.
        """
        if not candles or not structural_events:
            return []

        # Track candle count for staleness expiry.
        self._candle_counts[timeframe] = (
            self._candle_counts.get(timeframe, 0) + len(candles)
        )

        new_obs: list[dict] = []

        for event in structural_events:
            # Dedup: skip events we already processed.
            evt_key = self._event_key(event, timeframe)
            if evt_key in self._processed_events:
                continue
            self._processed_events.add(evt_key)

            break_candle = event.get("break_candle")
            if not break_candle:
                continue

            break_idx = _find_candle_index(candles, break_candle)
            if break_idx is None:
                log.debug(
                    "OB: break candle not found in candle list for %s event "
                    "on %s; skipping",
                    event.get("event_type"), timeframe,
                )
                continue

            direction = event.get("direction")
            ob_candle = None

            lower_bound = max(break_idx - LOOKBACK_WINDOW, 0)

            if direction == "bullish":
                # Find last bearish candle before the break.
                for j in range(break_idx - 1, lower_bound - 1, -1):
                    c = candles[j]
                    if float(c["close"]) < float(c["open"]):
                        ob_candle = c
                        ob_direction = "bullish"
                        birth_idx = j
                        break

            elif direction == "bearish":
                # Find last bullish candle before the break.
                for j in range(break_idx - 1, lower_bound - 1, -1):
                    c = candles[j]
                    if float(c["close"]) > float(c["open"]):
                        ob_candle = c
                        ob_direction = "bearish"
                        birth_idx = j
                        break

            if ob_candle is None:
                log.debug(
                    "OB: no opposing candle found within %d bars before "
                    "break on %s %s",
                    LOOKBACK_WINDOW, timeframe, direction,
                )
                continue

            body_high = round(max(float(ob_candle["open"]),
                                  float(ob_candle["close"])), 4)
            body_low = round(min(float(ob_candle["open"]),
                                 float(ob_candle["close"])), 4)

            created = ob_candle.get("closed_at_utc", _now_utc())
            eid = _evidence_id(timeframe, ob_direction, created,
                               body_low, body_high)

            ob = {
                "direction": ob_direction,
                "timeframe": timeframe,
                "high": body_high,
                "low": body_low,
                "body_high": body_high,
                "body_low": body_low,
                "ob_candle": dict(ob_candle),
                "trigger_event": dict(event),
                "trigger_event_type": event.get("event_type", ""),
                "created_at": created,
                "evidence_id": eid,
                "mitigated": False,
                "mitigated_pct": 0.0,
                "tested_count": 0,
                "status": "active",
                "_birth_candle_idx": (
                    self._candle_counts[timeframe] - len(candles) + birth_idx
                ),
                "_last_touch_price": None,
            }
            new_obs.append(ob)
            log.info(
                "OB detected | %s %s on %s: %.2f-%.2f (event=%s)",
                ob_direction, "order block", timeframe,
                body_low, body_high, event.get("event_type"),
            )

        # Merge into stored OBs (deduplicate by evidence_id).
        existing = self._active_obs.get(timeframe, [])
        existing_ids = {ob["evidence_id"] for ob in existing}
        for ob in new_obs:
            if ob["evidence_id"] not in existing_ids:
                existing.append(ob)
                existing_ids.add(ob["evidence_id"])

        # Expire stale OBs.
        current_idx = self._candle_counts[timeframe]
        existing = [
            ob for ob in existing
            if (current_idx - ob.get("_birth_candle_idx", current_idx))
            < STALE_CANDLE_LIMIT
        ]

        # Remove fully mitigated OBs.
        existing = [ob for ob in existing if ob["status"] != "mitigated"]

        # Cap at MAX_OBS_PER_TF, keeping newest.
        if len(existing) > MAX_OBS_PER_TF:
            existing = existing[-MAX_OBS_PER_TF:]

        self._active_obs[timeframe] = existing

        log.info(
            "OB scan %s: %d new, %d active",
            timeframe, len(new_obs), len(existing),
        )
        return new_obs

    # ------------------------------------------------------------------
    # update_status
    # ------------------------------------------------------------------

    def update_status(self, timeframe: str, current_price: float) -> None:
        """Update mitigation status of all OBs for *timeframe*."""
        obs = self._active_obs.get(timeframe, [])
        to_remove: list[int] = []

        for i, ob in enumerate(obs):
            pct = _compute_mitigation(ob, current_price)
            ob["mitigated_pct"] = round(pct, 4)
            ob["status"] = _status_from_mitigation(pct)
            ob["mitigated"] = ob["status"] == "mitigated"

            # Track zone-edge touches (price bounces off the edge).
            if _touches_zone_edge(ob, current_price, self.touch_tolerance):
                last = ob.get("_last_touch_price")
                if last is None or abs(current_price - last) > self.touch_tolerance * 3:
                    ob["tested_count"] = ob.get("tested_count", 0) + 1
                    ob["_last_touch_price"] = current_price
                    log.debug(
                        "OB %s tested (count=%d) at %.2f",
                        ob["evidence_id"], ob["tested_count"], current_price,
                    )

            if ob["status"] == "mitigated":
                to_remove.append(i)

        # Remove mitigated OBs.
        if to_remove:
            self._active_obs[timeframe] = [
                ob for i, ob in enumerate(obs) if i not in to_remove
            ]

    # ------------------------------------------------------------------
    # active_obs
    # ------------------------------------------------------------------

    def active_obs(
        self,
        timeframe: str | None = None,
        direction: str | None = None,
    ) -> list[dict]:
        """Return unmitigated order blocks, optionally filtered."""
        result: list[dict] = []
        timeframes = (
            [timeframe] if timeframe else list(self._active_obs.keys())
        )

        for tf in timeframes:
            for ob in self._active_obs.get(tf, []):
                if ob.get("status") == "mitigated":
                    continue
                if direction and ob["direction"] != direction:
                    continue
                result.append(ob)
        return result

    # ------------------------------------------------------------------
    # nearest_ob
    # ------------------------------------------------------------------

    def nearest_ob(
        self,
        price: float,
        direction: str | None = None,
    ) -> dict | None:
        """Find the nearest unmitigated OB to *price*."""
        candidates = self.active_obs(direction=direction)
        if not candidates:
            return None

        def _distance(ob: dict) -> float:
            if ob["low"] <= price <= ob["high"]:
                return 0.0
            return min(abs(price - ob["low"]), abs(price - ob["high"]))

        return min(candidates, key=_distance)

    # ------------------------------------------------------------------
    # snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """All active OBs across timeframes."""
        return {
            tf: list(obs)
            for tf, obs in self._active_obs.items()
            if obs
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _event_key(event: dict, timeframe: str) -> str:
        """Build a dedup key from a structural event."""
        etype = event.get("event_type", "")
        direction = event.get("direction", "")
        level = event.get("broken_level", "")
        detected = event.get("detected_at_utc", "")
        return f"{timeframe}:{etype}:{direction}:{level}:{detected}"


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Smoke test for OrderBlockDetector."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(name)s %(levelname)s %(message)s",
    )

    # --- Build synthetic candles -------------------------------------------
    # Candles 0-4: mixed, then a bullish structural break at candle 5.
    candles = [
        {"open": 2390.0, "high": 2392.0, "low": 2389.0, "close": 2391.5,
         "evidence_id": "c0", "closed_at_utc": "2026-08-18T10:00:00Z"},
        {"open": 2391.5, "high": 2393.0, "low": 2390.0, "close": 2392.0,
         "evidence_id": "c1", "closed_at_utc": "2026-08-18T10:05:00Z"},
        {"open": 2392.0, "high": 2393.5, "low": 2390.5, "close": 2391.0,  # bearish
         "evidence_id": "c2", "closed_at_utc": "2026-08-18T10:10:00Z"},
        {"open": 2391.0, "high": 2394.0, "low": 2390.0, "close": 2393.5,  # bullish
         "evidence_id": "c3", "closed_at_utc": "2026-08-18T10:15:00Z"},
        {"open": 2393.5, "high": 2395.0, "low": 2392.0, "close": 2392.5,  # bearish -- this should be OB
         "evidence_id": "c4", "closed_at_utc": "2026-08-18T10:20:00Z"},
        {"open": 2392.5, "high": 2400.0, "low": 2392.0, "close": 2399.0,  # break candle (bullish BOS)
         "evidence_id": "c5", "closed_at_utc": "2026-08-18T10:25:00Z"},
    ]

    # --- Bullish structural event (BOS upward) ---
    bullish_event = {
        "event_type": "BOS",
        "direction": "bullish",
        "timeframe": "M5",
        "broken_level": 2395.0,
        "break_candle": {"evidence_id": "c5",
                         "closed_at_utc": "2026-08-18T10:25:00Z",
                         "open": 2392.5, "high": 2400.0,
                         "low": 2392.0, "close": 2399.0},
        "detected_at_utc": "2026-08-18T10:25:01Z",
        "confidence": "medium",
    }

    det = OrderBlockDetector()

    # 1) Detect bullish OB
    result = det.detect("M5", candles, [bullish_event])
    assert len(result) == 1, f"Expected 1 OB, got {len(result)}"
    ob = result[0]
    assert ob["direction"] == "bullish"
    # OB candle is c4 (last bearish before break): open=2393.5, close=2392.5
    assert ob["high"] == 2393.5, f"Expected high=2393.5, got {ob['high']}"
    assert ob["low"] == 2392.5, f"Expected low=2392.5, got {ob['low']}"
    assert ob["status"] == "active"
    assert ob["mitigated"] is False
    assert ob["trigger_event_type"] == "BOS"
    log.info("PASS: bullish OB detected at %.2f-%.2f", ob["low"], ob["high"])

    # 2) Dedup: same event should not produce another OB
    result2 = det.detect("M5", candles, [bullish_event])
    assert len(result2) == 0, "Dedup failed: same event produced OB twice"
    log.info("PASS: event dedup works")

    # 3) active_obs
    active = det.active_obs(timeframe="M5")
    assert len(active) == 1
    assert active[0]["direction"] == "bullish"
    log.info("PASS: active_obs returns 1 bullish OB")

    # 4) active_obs with direction filter
    assert len(det.active_obs(direction="bearish")) == 0
    assert len(det.active_obs(direction="bullish")) == 1
    log.info("PASS: active_obs direction filter")

    # 5) nearest_ob
    nearest = det.nearest_ob(2393.0)
    assert nearest is not None
    assert nearest["direction"] == "bullish"
    log.info("PASS: nearest_ob found bullish OB")

    # 6) Mitigation tracking -- partial
    det.update_status("M5", 2393.0)
    ob_updated = det.active_obs(timeframe="M5")[0]
    assert ob_updated["mitigated_pct"] == 0.5, (
        f"Expected 50% mitigation, got {ob_updated['mitigated_pct']}"
    )
    assert ob_updated["status"] == "active"
    assert ob_updated["mitigated"] is False
    log.info("PASS: partial mitigation at 50%%")

    # 7) Mitigation tracking -- full (price through OB low)
    det.update_status("M5", 2392.0)
    active_after = det.active_obs(timeframe="M5")
    assert len(active_after) == 0, "Fully mitigated OB should be removed"
    log.info("PASS: fully mitigated OB removed")

    # --- Bearish OB test ---
    candles2 = [
        {"open": 2410.0, "high": 2412.0, "low": 2409.0, "close": 2411.5,  # bullish
         "evidence_id": "d0", "closed_at_utc": "2026-08-18T11:00:00Z"},
        {"open": 2411.5, "high": 2413.0, "low": 2410.0, "close": 2412.5,  # bullish -- this should be OB
         "evidence_id": "d1", "closed_at_utc": "2026-08-18T11:05:00Z"},
        {"open": 2412.5, "high": 2413.0, "low": 2405.0, "close": 2406.0,  # break candle (bearish)
         "evidence_id": "d2", "closed_at_utc": "2026-08-18T11:10:00Z"},
    ]

    bearish_event = {
        "event_type": "MSS",
        "direction": "bearish",
        "timeframe": "M15",
        "broken_level": 2408.0,
        "break_candle": {"evidence_id": "d2",
                         "closed_at_utc": "2026-08-18T11:10:00Z",
                         "open": 2412.5, "high": 2413.0,
                         "low": 2405.0, "close": 2406.0},
        "detected_at_utc": "2026-08-18T11:10:01Z",
        "confidence": "high",
    }

    det2 = OrderBlockDetector()
    result3 = det2.detect("M15", candles2, [bearish_event])
    assert len(result3) == 1, f"Expected 1 bearish OB, got {len(result3)}"
    ob2 = result3[0]
    assert ob2["direction"] == "bearish"
    # OB candle is d1 (last bullish before break): open=2411.5, close=2412.5
    assert ob2["high"] == 2412.5, f"Expected high=2412.5, got {ob2['high']}"
    assert ob2["low"] == 2411.5, f"Expected low=2411.5, got {ob2['low']}"
    assert ob2["trigger_event_type"] == "MSS"
    log.info("PASS: bearish OB detected at %.2f-%.2f (MSS event)", ob2["low"], ob2["high"])

    # 8) Bearish OB mitigation (price rises through OB high)
    det2.update_status("M15", 2413.0)
    assert len(det2.active_obs(timeframe="M15")) == 0
    log.info("PASS: bearish OB mitigated when price rose through high")

    # 9) Tested count
    det3 = OrderBlockDetector()
    det3.detect("M5", candles, [
        {**bullish_event, "detected_at_utc": "2026-08-18T10:25:02Z"},
    ])
    # Touch zone edge (OB high = 2393.5)
    det3.update_status("M5", 2393.5)
    ob3 = det3.active_obs(timeframe="M5")[0]
    assert ob3["tested_count"] == 1, f"Expected tested_count=1, got {ob3['tested_count']}"
    log.info("PASS: tested_count incremented on zone edge touch")

    # 10) snapshot
    snap = det3.snapshot()
    assert "M5" in snap
    assert len(snap["M5"]) == 1
    log.info("PASS: snapshot OK")

    # 11) Break candle not found in candles => skip gracefully
    det4 = OrderBlockDetector()
    orphan_event = {
        "event_type": "BOS",
        "direction": "bullish",
        "break_candle": {"evidence_id": "MISSING", "closed_at_utc": "NOPE"},
        "broken_level": 9999.0,
        "detected_at_utc": "2026-08-18T12:00:00Z",
    }
    result4 = det4.detect("M5", candles, [orphan_event])
    assert len(result4) == 0
    log.info("PASS: gracefully skips when break candle not found")

    # 12) Empty inputs
    det5 = OrderBlockDetector()
    assert det5.detect("M5", [], [bullish_event]) == []
    assert det5.detect("M5", candles, []) == []
    log.info("PASS: empty inputs return []")

    # 13) Max OBs per TF cap
    det6 = OrderBlockDetector()
    events = []
    big_candles = []
    for i in range(20):
        base = 2400.0 + i * 5
        # bearish candle (will become bullish OB)
        big_candles.append({
            "open": base + 2, "high": base + 3, "low": base,
            "close": base + 1,  # bearish: close < open
            "evidence_id": f"cap{i}_ob",
            "closed_at_utc": f"2026-08-18T13:{i:02d}:00Z",
        })
        # break candle
        big_candles.append({
            "open": base + 1, "high": base + 8, "low": base,
            "close": base + 7,
            "evidence_id": f"cap{i}_brk",
            "closed_at_utc": f"2026-08-18T13:{i:02d}:30Z",
        })
        events.append({
            "event_type": "BOS",
            "direction": "bullish",
            "break_candle": {
                "evidence_id": f"cap{i}_brk",
                "closed_at_utc": f"2026-08-18T13:{i:02d}:30Z",
            },
            "broken_level": base + 5,
            "detected_at_utc": f"2026-08-18T13:{i:02d}:31Z",
        })
    det6.detect("M5", big_candles, events)
    assert len(det6.active_obs(timeframe="M5")) <= MAX_OBS_PER_TF, (
        f"Should cap at {MAX_OBS_PER_TF}"
    )
    log.info("PASS: OBs capped at %d per timeframe", MAX_OBS_PER_TF)

    log.info("order_block self_test PASSED")


if __name__ == "__main__":
    self_test()
