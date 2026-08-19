"""Optimal Trade Entry (OTE) calculator using Fibonacci retracement.

After an impulse move (a strong directional move that breaks structure),
price typically retraces before continuing.  The OTE zone is the 62%-79%
Fibonacci retracement of the impulse, with the "sweet spot" at 70.5%.

  Bullish OTE:  swing low -> swing high impulse, buy zone at 62-79% retrace
  Bearish OTE:  swing high -> swing low impulse, sell zone at 62-79% retrace

Part of an ICT / SMC market-structure trading system for XAUUSD scalping.

No project imports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

MIN_IMPULSE_PTS: float = 3.0        # minimum impulse size in points (XAUUSD)
MAX_OTES_PER_TF: int = 5            # cap active OTEs per timeframe
STALE_CANDLE_LIMIT: int = 100        # expire after 100 candles on the TF
MAX_IMPULSE_PAIRS: int = 3           # only consider last N impulse moves


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_id(timeframe: str, direction: str, start: float, end: float) -> str:
    return f"ote:{timeframe}:{direction}:{start:.2f}-{end:.2f}"


def _price_in_zone(price: float, ote_low: float, ote_high: float) -> bool:
    return ote_low <= price <= ote_high


def _distance_to_zone(price: float, ote_low: float, ote_high: float) -> float:
    if price < ote_low:
        return ote_low - price
    if price > ote_high:
        return price - ote_high
    return 0.0


def _impulse_has_structural_break(
    swing_a: dict,
    swing_b: dict,
    structural_events: list[dict] | None,
) -> bool:
    """Check whether a structural event (BOS/CHoCH) occurred during the impulse."""
    if not structural_events:
        return False
    a_time = swing_a.get("time", "")
    b_time = swing_b.get("time", "")
    if not a_time or not b_time:
        return False
    for evt in structural_events:
        evt_time = evt.get("time", evt.get("created_at", ""))
        if a_time <= evt_time <= b_time:
            return True
    return False


# ---------------------------------------------------------------------------
# OTECalculator
# ---------------------------------------------------------------------------

class OTECalculator:
    """Calculate and track Optimal Trade Entry zones across timeframes."""

    # Fibonacci levels for OTE
    FIB_62 = 0.618
    FIB_705 = 0.705   # sweet spot
    FIB_79 = 0.786

    def __init__(self) -> None:
        self._active_otes: dict[str, list[dict]] = {}   # tf -> list of OTEs
        self._candle_counts: dict[str, int] = {}         # tf -> candles seen

    # ------------------------------------------------------------------
    # calculate
    # ------------------------------------------------------------------

    def calculate(
        self,
        timeframe: str,
        swings: list[dict],
        structural_events: list[dict] | None = None,
        current_price: float | None = None,
    ) -> list[dict]:
        """Calculate OTE zones from recent impulse moves.

        Args:
            timeframe: ``"M5"``, ``"M15"``, etc.
            swings: swing points from structure_tracker
                ``[{kind, price, time, evidence_id}, ...]``
            structural_events: optional, to identify which impulses had
                structural breaks (BOS / CHoCH).
            current_price: for calculating proximity and zone status.

        Returns:
            List of active OTE zones (see module docstring for schema).
        """
        if len(swings) < 2:
            return self._active_otes.get(timeframe, [])

        # Bump candle count (approximate; caller drives this).
        self._candle_counts[timeframe] = self._candle_counts.get(timeframe, 0) + 1

        now_iso = datetime.now(timezone.utc).isoformat()

        # Only consider the most recent MAX_IMPULSE_PAIRS consecutive pairs.
        pairs = list(zip(swings, swings[1:]))
        pairs = pairs[-MAX_IMPULSE_PAIRS:]

        new_otes: list[dict] = []

        for swing_a, swing_b in pairs:
            kind_a = swing_a.get("kind", "")
            kind_b = swing_b.get("kind", "")
            price_a = float(swing_a["price"])
            price_b = float(swing_b["price"])

            if kind_a == "low" and kind_b == "high":
                # Bullish impulse (up-move) -> bullish OTE (buy zone)
                impulse_size = price_b - price_a
                if impulse_size < MIN_IMPULSE_PTS:
                    continue
                fib_62 = round(price_b - (impulse_size * self.FIB_62), 4)
                fib_705 = round(price_b - (impulse_size * self.FIB_705), 4)
                fib_79 = round(price_b - (impulse_size * self.FIB_79), 4)
                ote_high = fib_62
                ote_low = fib_79
                direction = "bullish"

            elif kind_a == "high" and kind_b == "low":
                # Bearish impulse (down-move) -> bearish OTE (sell zone)
                impulse_size = price_a - price_b
                if impulse_size < MIN_IMPULSE_PTS:
                    continue
                fib_62 = round(price_b + (impulse_size * self.FIB_62), 4)
                fib_705 = round(price_b + (impulse_size * self.FIB_705), 4)
                fib_79 = round(price_b + (impulse_size * self.FIB_79), 4)
                ote_high = fib_79
                ote_low = fib_62
                direction = "bearish"

            else:
                continue

            has_sb = _impulse_has_structural_break(swing_a, swing_b, structural_events)
            eid = _evidence_id(timeframe, direction, price_a, price_b)

            in_zone = False
            dist = None
            if current_price is not None:
                in_zone = _price_in_zone(current_price, ote_low, ote_high)
                dist = round(_distance_to_zone(current_price, ote_low, ote_high), 4)

            ote = {
                "direction": direction,
                "timeframe": timeframe,
                "impulse_start": price_a,
                "impulse_end": price_b,
                "impulse_size": round(impulse_size, 4),
                "fib_62": fib_62,
                "fib_705": fib_705,
                "fib_79": fib_79,
                "ote_high": ote_high,
                "ote_low": ote_low,
                "sweet_spot": fib_705,
                "has_structural_break": has_sb,
                "created_at": now_iso,
                "evidence_id": eid,
                "status": "active",
                "price_in_zone": in_zone,
                "distance_to_zone": dist,
                "_birth_candle_idx": self._candle_counts[timeframe],
            }
            new_otes.append(ote)
            log.debug(
                "%s OTE on %s: %.2f-%.2f (sweet %.2f), impulse %.2f pts",
                direction.capitalize(), timeframe,
                ote_low, ote_high, fib_705, impulse_size,
            )

        # Merge into stored OTEs (deduplicate by evidence_id).
        existing = self._active_otes.get(timeframe, [])
        existing_ids = {o["evidence_id"] for o in existing}
        added_count = 0
        for ote in new_otes:
            if ote["evidence_id"] not in existing_ids:
                existing.append(ote)
                existing_ids.add(ote["evidence_id"])
                added_count += 1

        # Expire stale OTEs.
        current_idx = self._candle_counts[timeframe]
        existing = [
            o for o in existing
            if (current_idx - o.get("_birth_candle_idx", current_idx)) < STALE_CANDLE_LIMIT
        ]

        # Update status based on current price.
        if current_price is not None:
            for ote in existing:
                ote["price_in_zone"] = _price_in_zone(
                    current_price, ote["ote_low"], ote["ote_high"],
                )
                ote["distance_to_zone"] = round(
                    _distance_to_zone(current_price, ote["ote_low"], ote["ote_high"]), 4,
                )
                # Triggered: price is inside the zone.
                if ote["price_in_zone"] and ote["status"] == "active":
                    ote["status"] = "triggered"
                    log.info(
                        "OTE TRIGGERED: %s %s zone %.2f-%.2f (price %.2f)",
                        ote["direction"], timeframe,
                        ote["ote_low"], ote["ote_high"], current_price,
                    )
                # Invalidated: price broke through impulse start.
                if ote["direction"] == "bullish" and current_price < ote["impulse_start"]:
                    ote["status"] = "invalidated"
                elif ote["direction"] == "bearish" and current_price > ote["impulse_start"]:
                    ote["status"] = "invalidated"

        # Remove invalidated OTEs.
        existing = [o for o in existing if o["status"] != "invalidated"]

        # Cap at MAX_OTES_PER_TF, keeping newest.
        if len(existing) > MAX_OTES_PER_TF:
            existing = existing[-MAX_OTES_PER_TF:]

        self._active_otes[timeframe] = existing

        log.info(
            "OTE calculate %s: %d new, %d active",
            timeframe, added_count, len(existing),
        )
        return list(existing)

    # ------------------------------------------------------------------
    # active_otes
    # ------------------------------------------------------------------

    def active_otes(
        self,
        timeframe: str | None = None,
        direction: str | None = None,
    ) -> list[dict]:
        """Get active OTE zones, optionally filtered by timeframe/direction."""
        result: list[dict] = []
        timeframes = [timeframe] if timeframe else list(self._active_otes.keys())

        for tf in timeframes:
            for ote in self._active_otes.get(tf, []):
                if ote.get("status") == "invalidated":
                    continue
                if direction and ote["direction"] != direction:
                    continue
                result.append(ote)
        return result

    # ------------------------------------------------------------------
    # nearest_ote
    # ------------------------------------------------------------------

    def nearest_ote(
        self,
        price: float,
        direction: str | None = None,
    ) -> dict | None:
        """Find nearest active OTE zone to *price*."""
        candidates = self.active_otes(direction=direction)
        if not candidates:
            return None

        def _dist(ote: dict) -> float:
            return _distance_to_zone(price, ote["ote_low"], ote["ote_high"])

        return min(candidates, key=_dist)

    # ------------------------------------------------------------------
    # snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """All active OTEs across timeframes."""
        return {
            tf: list(otes)
            for tf, otes in self._active_otes.items()
            if otes
        }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Quick smoke test with synthetic swing data."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(name)s %(levelname)s %(message)s",
    )

    calc = OTECalculator()

    # --- Bullish OTE: swing low 2380 -> swing high 2400 (20pt impulse) ----
    bullish_swings = [
        {"kind": "low",  "price": 2380.0, "time": "2026-08-18T09:00:00Z", "evidence_id": "sw1"},
        {"kind": "high", "price": 2400.0, "time": "2026-08-18T09:30:00Z", "evidence_id": "sw2"},
    ]

    result = calc.calculate("M15", bullish_swings, current_price=2395.0)
    assert len(result) == 1, f"Expected 1 bullish OTE, got {len(result)}"
    ote = result[0]
    assert ote["direction"] == "bullish"
    assert ote["impulse_size"] == 20.0
    # fib_62 = 2400 - (20 * 0.618) = 2400 - 12.36 = 2387.64
    assert ote["fib_62"] == 2387.64, f"fib_62 expected 2387.64, got {ote['fib_62']}"
    # fib_705 = 2400 - (20 * 0.705) = 2400 - 14.10 = 2385.90
    assert ote["fib_705"] == 2385.9, f"fib_705 expected 2385.9, got {ote['fib_705']}"
    # fib_79 = 2400 - (20 * 0.786) = 2400 - 15.72 = 2384.28
    assert ote["fib_79"] == 2384.28, f"fib_79 expected 2384.28, got {ote['fib_79']}"
    assert ote["ote_high"] == ote["fib_62"]
    assert ote["ote_low"] == ote["fib_79"]
    assert ote["sweet_spot"] == ote["fib_705"]
    assert ote["status"] == "active"
    assert ote["price_in_zone"] is False   # 2395 is above the zone
    assert ote["distance_to_zone"] == round(2395.0 - 2387.64, 4)
    log.info("PASS: bullish OTE levels correct")

    # --- Price enters zone -> triggered -----------------------------------
    result = calc.calculate("M15", bullish_swings, current_price=2386.0)
    triggered = [o for o in result if o["status"] == "triggered"]
    assert len(triggered) == 1, f"Expected 1 triggered OTE, got {len(triggered)}"
    assert triggered[0]["price_in_zone"] is True
    assert triggered[0]["distance_to_zone"] == 0.0
    log.info("PASS: bullish OTE triggered when price enters zone")

    # --- Price breaks impulse start -> invalidated (removed) --------------
    calc2 = OTECalculator()
    calc2.calculate("M15", bullish_swings, current_price=2395.0)
    result = calc2.calculate("M15", bullish_swings, current_price=2379.0)
    assert len(result) == 0, f"Expected 0 OTEs after invalidation, got {len(result)}"
    log.info("PASS: bullish OTE invalidated when price breaks impulse start")

    # --- Bearish OTE: swing high 2420 -> swing low 2400 (20pt impulse) ----
    bearish_swings = [
        {"kind": "high", "price": 2420.0, "time": "2026-08-18T10:00:00Z", "evidence_id": "sw3"},
        {"kind": "low",  "price": 2400.0, "time": "2026-08-18T10:30:00Z", "evidence_id": "sw4"},
    ]

    calc3 = OTECalculator()
    result = calc3.calculate("M5", bearish_swings, current_price=2405.0)
    assert len(result) == 1, f"Expected 1 bearish OTE, got {len(result)}"
    ote = result[0]
    assert ote["direction"] == "bearish"
    # fib_62 = 2400 + (20 * 0.618) = 2412.36
    assert ote["fib_62"] == 2412.36, f"fib_62 expected 2412.36, got {ote['fib_62']}"
    # fib_705 = 2400 + (20 * 0.705) = 2414.10
    assert ote["fib_705"] == 2414.1, f"fib_705 expected 2414.1, got {ote['fib_705']}"
    # fib_79 = 2400 + (20 * 0.786) = 2415.72
    assert ote["fib_79"] == 2415.72, f"fib_79 expected 2415.72, got {ote['fib_79']}"
    # Bearish: ote_high = fib_79, ote_low = fib_62
    assert ote["ote_high"] == ote["fib_79"]
    assert ote["ote_low"] == ote["fib_62"]
    assert ote["status"] == "active"
    log.info("PASS: bearish OTE levels correct")

    # --- Minimum impulse filter -------------------------------------------
    tiny_swings = [
        {"kind": "low",  "price": 2400.0, "time": "2026-08-18T11:00:00Z", "evidence_id": "sw5"},
        {"kind": "high", "price": 2402.0, "time": "2026-08-18T11:05:00Z", "evidence_id": "sw6"},
    ]
    calc4 = OTECalculator()
    result = calc4.calculate("M5", tiny_swings)
    assert len(result) == 0, f"2pt impulse should produce no OTE, got {len(result)}"
    log.info("PASS: sub-%.1f-point impulse correctly filtered", MIN_IMPULSE_PTS)

    # --- Structural break flag --------------------------------------------
    events = [
        {"type": "BOS", "time": "2026-08-18T09:15:00Z"},
    ]
    calc5 = OTECalculator()
    result = calc5.calculate("M15", bullish_swings, structural_events=events)
    assert result[0]["has_structural_break"] is True
    log.info("PASS: structural break flag set correctly")

    # --- nearest_ote ------------------------------------------------------
    calc6 = OTECalculator()
    calc6.calculate("M15", bullish_swings, current_price=2395.0)
    calc6.calculate("M5", bearish_swings, current_price=2405.0)
    nearest = calc6.nearest_ote(2388.0)
    assert nearest is not None
    assert nearest["direction"] == "bullish"
    log.info("PASS: nearest_ote returns closest zone")

    nearest_bear = calc6.nearest_ote(2413.0, direction="bearish")
    assert nearest_bear is not None
    assert nearest_bear["direction"] == "bearish"
    log.info("PASS: nearest_ote with direction filter")

    # --- snapshot ---------------------------------------------------------
    snap = calc6.snapshot()
    assert "M15" in snap
    assert "M5" in snap
    log.info("PASS: snapshot returns %d timeframes", len(snap))

    # --- Max 3 impulse pairs processed ------------------------------------
    many_swings = [
        {"kind": "low",  "price": 2350.0, "time": "2026-08-18T08:00:00Z", "evidence_id": "m1"},
        {"kind": "high", "price": 2360.0, "time": "2026-08-18T08:05:00Z", "evidence_id": "m2"},
        {"kind": "low",  "price": 2355.0, "time": "2026-08-18T08:10:00Z", "evidence_id": "m3"},
        {"kind": "high", "price": 2370.0, "time": "2026-08-18T08:15:00Z", "evidence_id": "m4"},
        {"kind": "low",  "price": 2362.0, "time": "2026-08-18T08:20:00Z", "evidence_id": "m5"},
        {"kind": "high", "price": 2380.0, "time": "2026-08-18T08:25:00Z", "evidence_id": "m6"},
        {"kind": "low",  "price": 2370.0, "time": "2026-08-18T08:30:00Z", "evidence_id": "m7"},
        {"kind": "high", "price": 2390.0, "time": "2026-08-18T08:35:00Z", "evidence_id": "m8"},
    ]
    calc7 = OTECalculator()
    result = calc7.calculate("M15", many_swings)
    # 7 consecutive pairs, but only last 3 processed; of those some might be
    # same-direction consecutive (low->high vs high->low alternating).
    assert len(result) <= MAX_IMPULSE_PAIRS, (
        f"Should process at most {MAX_IMPULSE_PAIRS} pairs, got {len(result)}"
    )
    log.info("PASS: max impulse pairs cap respected (%d OTEs)", len(result))

    log.info("All self_test checks passed.")


if __name__ == "__main__":
    self_test()
