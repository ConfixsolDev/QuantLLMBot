"""Fair Value Gap (FVG) detector for XAUUSD scalping.

Scans candle data for price imbalance zones where the market moved too
fast for orders to fill.  An FVG is a 3-candle formation where the wicks
of candle 1 and candle 3 do not overlap:

  Bullish FVG:  candle_1.high < candle_3.low
  Bearish FVG:  candle_1.low  > candle_3.high

The middle candle is the displacement candle that created the gap.  Price
tends to retrace into the FVG zone before continuing in the original
direction.

Part of an ICT / SMC market-structure trading system.

No project imports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

MIN_FVG_WIDTH: float = 0.3          # filter out sub-0.3-point noise on XAUUSD
MAX_FVGS_PER_TF: int = 20           # keep at most 20 per timeframe
STALE_CANDLE_LIMIT: int = 200        # expire after 200 candles on the TF
FILL_THRESHOLD: float = 0.90         # >= 90 % fill  =>  fully_filled


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _evidence_id(timeframe: str, direction: str, created_at: str, low: float, high: float) -> str:
    return f"fvg:{timeframe}:{direction}:{created_at}:{low:.2f}-{high:.2f}"


def _compute_fill(fvg: dict, price: float) -> float:
    """Return fill percentage (0-1) for *price* inside *fvg* zone."""
    width = fvg["width"]
    if width <= 0:
        return 0.0

    if fvg["direction"] == "bullish":
        # Price dropping into a bullish FVG fills it from the top.
        if price >= fvg["high"]:
            return 0.0
        if price <= fvg["low"]:
            return 1.0
        return (fvg["high"] - price) / width

    else:  # bearish
        # Price rising into a bearish FVG fills it from the bottom.
        if price <= fvg["low"]:
            return 0.0
        if price >= fvg["high"]:
            return 1.0
        return (price - fvg["low"]) / width


def _status_from_fill(filled_pct: float) -> str:
    if filled_pct >= FILL_THRESHOLD:
        return "fully_filled"
    if filled_pct > 0.0:
        return "partially_filled"
    return "active"


# ---------------------------------------------------------------------------
# FVGDetector
# ---------------------------------------------------------------------------

class FVGDetector:
    """Detect and track Fair Value Gaps across multiple timeframes."""

    def __init__(self) -> None:
        self._active_fvgs: dict[str, list[dict]] = {}   # tf -> list of FVGs
        self._candle_counts: dict[str, int] = {}         # tf -> candles seen
        self._seen_ids: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # scan
    # ------------------------------------------------------------------

    def scan(
        self,
        timeframe: str,
        candles: list[dict],
        current_price: float | None = None,
    ) -> list[dict]:
        """Scan *candles* for Fair Value Gaps on *timeframe*.

        Args:
            timeframe: ``"M5"``, ``"M15"``, etc.
            candles: OHLC candle dicts with keys ``open``, ``high``, ``low``,
                ``close``, ``evidence_id``, ``closed_at_utc``.
            current_price: if provided, fill percentages are calculated.

        Returns:
            List of active (tradeable) FVGs found or updated.
        """
        if len(candles) < 3:
            return self._active_fvgs.get(timeframe, [])

        # Track candle count for staleness expiry.
        # ``candles`` is a rolling snapshot, not a batch of unseen bars. Adding
        # its full length every 30 seconds expired every stored gap and made the
        # same historical FVGs appear "new" on the next scan.
        self._candle_counts[timeframe] = len(candles)

        new_fvgs: list[dict] = []

        for i in range(len(candles) - 2):
            c1, c2, c3 = candles[i], candles[i + 1], candles[i + 2]

            # --- Bullish FVG: gap between c1.high and c3.low --------------
            if c3["low"] > c1["high"]:
                low = c1["high"]
                high = c3["low"]
                width = high - low
                if width >= MIN_FVG_WIDTH:
                    created = (
                        c2.get("close_time_utc")
                        or c2.get("closed_at_utc")
                        or datetime.now(timezone.utc).isoformat()
                    )
                    midpoint = (high + low) / 2.0
                    eid = _evidence_id(timeframe, "bullish", created, low, high)
                    fvg = {
                        "direction": "bullish",
                        "timeframe": timeframe,
                        "high": round(high, 4),
                        "low": round(low, 4),
                        "width": round(width, 4),
                        "midpoint": round(midpoint, 4),
                        "displacement_candle": dict(c2),
                        "created_at": created,
                        "evidence_id": eid,
                        "filled_pct": 0.0,
                        "status": "active",
                        "tradeable": True,
                        "_birth_candle_idx": i + 1,
                    }
                    new_fvgs.append(fvg)
                    log.debug("Bullish FVG detected on %s: %.2f-%.2f (%.2f pts)", timeframe, low, high, width)

            # --- Bearish FVG: gap between c3.high and c1.low --------------
            if c3["high"] < c1["low"]:
                high = c1["low"]
                low = c3["high"]
                width = high - low
                if width >= MIN_FVG_WIDTH:
                    created = (
                        c2.get("close_time_utc")
                        or c2.get("closed_at_utc")
                        or datetime.now(timezone.utc).isoformat()
                    )
                    midpoint = (high + low) / 2.0
                    eid = _evidence_id(timeframe, "bearish", created, low, high)
                    fvg = {
                        "direction": "bearish",
                        "timeframe": timeframe,
                        "high": round(high, 4),
                        "low": round(low, 4),
                        "width": round(width, 4),
                        "midpoint": round(midpoint, 4),
                        "displacement_candle": dict(c2),
                        "created_at": created,
                        "evidence_id": eid,
                        "filled_pct": 0.0,
                        "status": "active",
                        "tradeable": True,
                        "_birth_candle_idx": i + 1,
                    }
                    new_fvgs.append(fvg)
                    log.debug("Bearish FVG detected on %s: %.2f-%.2f (%.2f pts)", timeframe, low, high, width)

        # Merge into stored FVGs (deduplicate by evidence_id).
        existing = self._active_fvgs.get(timeframe, [])
        seen_ids = self._seen_ids.setdefault(timeframe, set())
        existing_ids = {f["evidence_id"] for f in existing}
        added_count = 0
        for fvg in new_fvgs:
            if fvg["evidence_id"] not in seen_ids:
                existing.append(fvg)
                existing_ids.add(fvg["evidence_id"])
                seen_ids.add(fvg["evidence_id"])
                added_count += 1

        # Expire stale FVGs.
        current_idx = self._candle_counts[timeframe]
        existing = [
            f for f in existing
            if (current_idx - f.get("_birth_candle_idx", current_idx)) < STALE_CANDLE_LIMIT
        ]

        # Update fills if price provided.
        if current_price is not None:
            for fvg in existing:
                fvg["filled_pct"] = round(_compute_fill(fvg, current_price), 4)
                fvg["status"] = _status_from_fill(fvg["filled_pct"])
                fvg["tradeable"] = fvg["status"] in ("active", "partially_filled")

        # Remove fully-filled FVGs.
        existing = [f for f in existing if f["status"] != "fully_filled"]

        # Cap at MAX_FVGS_PER_TF, keeping newest.
        if len(existing) > MAX_FVGS_PER_TF:
            existing = existing[-MAX_FVGS_PER_TF:]

        self._active_fvgs[timeframe] = existing

        log.info(
            "FVG scan %s: %d new, %d active",
            timeframe,
            added_count,
            len(existing),
        )
        return list(existing)

    # ------------------------------------------------------------------
    # active_fvgs
    # ------------------------------------------------------------------

    def active_fvgs(
        self,
        timeframe: str | None = None,
        direction: str | None = None,
    ) -> list[dict]:
        """Return currently active (unfilled) FVGs, optionally filtered."""
        result: list[dict] = []
        timeframes = [timeframe] if timeframe else list(self._active_fvgs.keys())

        for tf in timeframes:
            for fvg in self._active_fvgs.get(tf, []):
                if not fvg.get("tradeable", False):
                    continue
                if direction and fvg["direction"] != direction:
                    continue
                result.append(fvg)
        return result

    # ------------------------------------------------------------------
    # nearest_fvg
    # ------------------------------------------------------------------

    def nearest_fvg(
        self,
        price: float,
        direction: str | None = None,
    ) -> dict | None:
        """Find the nearest unfilled FVG to *price*."""
        candidates = self.active_fvgs(direction=direction)
        if not candidates:
            return None

        def _distance(fvg: dict) -> float:
            if fvg["low"] <= price <= fvg["high"]:
                return 0.0
            return min(abs(price - fvg["low"]), abs(price - fvg["high"]))

        return min(candidates, key=_distance)

    # ------------------------------------------------------------------
    # snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> dict:
        """All active FVGs across timeframes."""
        return {
            tf: list(fvgs)
            for tf, fvgs in self._active_fvgs.items()
            if fvgs
        }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Quick smoke test with sample candle data."""
    logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")

    # --- sample candles with a bullish FVG ----------------------------------
    # Candle 1 high = 2390.0, candle 3 low = 2391.0  =>  gap 2390.0 - 2391.0
    bullish_candles = [
        {"open": 2388.0, "high": 2390.0, "low": 2387.0, "close": 2389.5,
         "evidence_id": "c1", "closed_at_utc": "2026-08-18T10:00:00Z"},
        {"open": 2389.5, "high": 2393.0, "low": 2389.0, "close": 2392.5,
         "evidence_id": "c2", "closed_at_utc": "2026-08-18T10:05:00Z"},
        {"open": 2392.5, "high": 2395.0, "low": 2391.0, "close": 2394.0,
         "evidence_id": "c3", "closed_at_utc": "2026-08-18T10:10:00Z"},
    ]

    # --- sample candles with a bearish FVG ----------------------------------
    # Candle 1 low = 2400.0, candle 3 high = 2399.0  =>  gap 2399.0 - 2400.0
    bearish_candles = [
        {"open": 2402.0, "high": 2403.0, "low": 2400.0, "close": 2400.5,
         "evidence_id": "c4", "closed_at_utc": "2026-08-18T11:00:00Z"},
        {"open": 2400.5, "high": 2401.0, "low": 2397.0, "close": 2397.5,
         "evidence_id": "c5", "closed_at_utc": "2026-08-18T11:05:00Z"},
        {"open": 2397.5, "high": 2399.0, "low": 2396.0, "close": 2398.0,
         "evidence_id": "c6", "closed_at_utc": "2026-08-18T11:10:00Z"},
    ]

    # --- tiny gap that should be filtered out (< MIN_FVG_WIDTH) -------------
    tiny_candles = [
        {"open": 2388.0, "high": 2390.0, "low": 2387.0, "close": 2389.5,
         "evidence_id": "t1", "closed_at_utc": "2026-08-18T12:00:00Z"},
        {"open": 2389.5, "high": 2391.0, "low": 2389.0, "close": 2390.5,
         "evidence_id": "t2", "closed_at_utc": "2026-08-18T12:05:00Z"},
        {"open": 2390.5, "high": 2391.0, "low": 2390.1, "close": 2390.8,
         "evidence_id": "t3", "closed_at_utc": "2026-08-18T12:10:00Z"},
    ]

    detector = FVGDetector()

    # Bullish FVG detection
    result = detector.scan("M5", bullish_candles)
    assert len(result) == 1, f"Expected 1 bullish FVG, got {len(result)}"
    fvg = result[0]
    assert fvg["direction"] == "bullish"
    assert fvg["low"] == 2390.0
    assert fvg["high"] == 2391.0
    assert fvg["width"] == 1.0
    assert fvg["status"] == "active"
    assert fvg["tradeable"] is True
    log.info("PASS: bullish FVG detected correctly: %.2f - %.2f", fvg["low"], fvg["high"])

    # Bearish FVG detection
    result = detector.scan("M5", bearish_candles)
    bearish = [f for f in result if f["direction"] == "bearish"]
    assert len(bearish) == 1, f"Expected 1 bearish FVG, got {len(bearish)}"
    fvg = bearish[0]
    assert fvg["direction"] == "bearish"
    assert fvg["high"] == 2400.0
    assert fvg["low"] == 2399.0
    assert fvg["width"] == 1.0
    log.info("PASS: bearish FVG detected correctly: %.2f - %.2f", fvg["low"], fvg["high"])

    # Tiny gap filtered
    before = len(detector.active_fvgs(timeframe="M15"))
    detector.scan("M15", tiny_candles)
    after = len(detector.active_fvgs(timeframe="M15"))
    assert after == before, f"Tiny FVG should have been filtered; before={before}, after={after}"
    log.info("PASS: sub-%.1f-point gap correctly filtered", MIN_FVG_WIDTH)

    # Fill tracking
    result = detector.scan("M5", bullish_candles, current_price=2390.5)
    bull = [f for f in result if f["direction"] == "bullish"]
    assert len(bull) == 1
    assert bull[0]["filled_pct"] == 0.5, f"Expected 50% fill, got {bull[0]['filled_pct']}"
    assert bull[0]["status"] == "partially_filled"
    log.info("PASS: fill tracking correct (50%% fill -> partially_filled)")

    # Full fill removes FVG
    result = detector.scan("M5", bullish_candles, current_price=2390.0)
    bull = [f for f in result if f["direction"] == "bullish"]
    assert len(bull) == 0, "Fully filled bullish FVG should have been removed"
    log.info("PASS: fully filled FVG removed")

    # nearest_fvg
    nearest = detector.nearest_fvg(2399.5)
    assert nearest is not None
    assert nearest["direction"] == "bearish"
    log.info("PASS: nearest_fvg returned bearish FVG at %.2f-%.2f", nearest["low"], nearest["high"])

    # snapshot
    snap = detector.snapshot()
    assert "M5" in snap
    log.info("PASS: snapshot returns %d timeframes", len(snap))

    log.info("All self_test checks passed.")


if __name__ == "__main__":
    self_test()
