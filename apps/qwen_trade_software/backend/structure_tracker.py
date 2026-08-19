"""Market structure tracking (HH/HL/LH/LL swing sequences).

Detects swing highs and swing lows via fractal pivot logic, then classifies
the resulting sequence as bullish (HH+HL), bearish (LH+LL), ranging, or
insufficient.  Maintains rolling swing history per timeframe and detects
transitions (e.g., bullish -> bearish = CHoCH opportunity).

No external dependencies beyond the standard library.

2026-08-18
"""

from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_SWINGS = 20          # rolling window of swing points per timeframe
_MIN_CANDLES = 8          # minimum candles required for swing detection
_WING = 2                 # bars on each side for fractal pivot confirmation

StructureDirection = Literal["bullish", "bearish", "ranging", "insufficient"]


# ---------------------------------------------------------------------------
# Swing detection helpers
# ---------------------------------------------------------------------------

def _detect_swings(candles: list[dict]) -> list[dict]:
    """Detect swing highs and swing lows using 2-bar wing fractal logic.

    A swing high at index *i* requires:
        high[i] > high[i-1]  AND  high[i] > high[i+1]
        high[i] > high[i-2]  AND  high[i] > high[i+2]

    Swing lows use the same test inverted on the low array.

    Returns a list of dicts sorted by bar index:
        {"kind": "high"|"low", "price": float, "bar_index": int,
         "time": str|None, "evidence_id": str|None}
    """
    n = len(candles)
    if n < _MIN_CANDLES:
        return []

    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]

    swings: list[dict] = []

    for i in range(_WING, n - _WING):
        # --- swing high check ---
        is_sh = True
        for w in range(1, _WING + 1):
            if highs[i] <= highs[i - w] or highs[i] <= highs[i + w]:
                is_sh = False
                break
        if is_sh:
            swings.append({
                "kind": "high",
                "price": highs[i],
                "bar_index": i,
                "time": candles[i].get("closed_at_utc"),
                "evidence_id": candles[i].get("evidence_id"),
            })

        # --- swing low check ---
        is_sl = True
        for w in range(1, _WING + 1):
            if lows[i] >= lows[i - w] or lows[i] >= lows[i + w]:
                is_sl = False
                break
        if is_sl:
            swings.append({
                "kind": "low",
                "price": lows[i],
                "bar_index": i,
                "time": candles[i].get("closed_at_utc"),
                "evidence_id": candles[i].get("evidence_id"),
            })

    swings.sort(key=lambda s: s["bar_index"])
    return swings


def _classify_structure(swings: list[dict]) -> StructureDirection:
    """Classify the swing sequence as bullish, bearish, ranging, or insufficient.

    Requires at least 2 swing highs and 2 swing lows.

    Rules:
        latest_high > prev_high  AND  latest_low > prev_low  -> bullish  (HH + HL)
        latest_high < prev_high  AND  latest_low < prev_low  -> bearish  (LH + LL)
        Otherwise -> ranging
    """
    recent_highs = [s for s in swings if s["kind"] == "high"]
    recent_lows = [s for s in swings if s["kind"] == "low"]

    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return "insufficient"

    prev_high, latest_high = recent_highs[-2]["price"], recent_highs[-1]["price"]
    prev_low, latest_low = recent_lows[-2]["price"], recent_lows[-1]["price"]

    if latest_high > prev_high and latest_low > prev_low:
        return "bullish"
    if latest_high < prev_high and latest_low < prev_low:
        return "bearish"
    return "ranging"


# ---------------------------------------------------------------------------
# StructureTracker
# ---------------------------------------------------------------------------

class StructureTracker:
    """Track market structure (HH/HL/LH/LL) across multiple timeframes.

    Usage::

        tracker = StructureTracker()
        tracker.update("M5", m5_candles)
        tracker.update("H1", h1_candles)
        snap = tracker.snapshot()
    """

    def __init__(self) -> None:
        # tf -> list of {kind, price, time, evidence_id, bar_index}
        self._swings: dict[str, list[dict]] = {}
        # tf -> bullish / bearish / ranging / insufficient
        self._structure: dict[str, str] = {}
        # tf -> previous structure (for transition detection)
        self._prev_structure: dict[str, str] = {}

    # ---- public API -------------------------------------------------------

    def update(self, timeframe: str, candles: list[dict]) -> dict:
        """Process candles for *timeframe*, refresh swings and structure.

        Parameters
        ----------
        timeframe:
            Label such as ``"M5"``, ``"M15"``, ``"H1"``, ``"H4"``.
        candles:
            List of OHLC dicts.  Required keys: ``open``, ``high``, ``low``,
            ``close``.  Optional: ``evidence_id``, ``closed_at_utc``.

        Returns
        -------
        dict
            ``{"direction": ..., "swings_count": ..., "transition": ...}``
        """
        new_swings = _detect_swings(candles)

        # Merge: keep existing swings that are older (by bar_index) than the
        # first new swing, then append new ones.  This avoids duplicates when
        # candle windows overlap.
        existing = self._swings.get(timeframe, [])
        if new_swings and existing:
            first_new_idx = new_swings[0]["bar_index"]
            kept = [s for s in existing if s["bar_index"] < first_new_idx]
            merged = kept + new_swings
        elif new_swings:
            merged = new_swings
        else:
            merged = existing

        # Trim to rolling window.
        merged = merged[-_MAX_SWINGS:]
        self._swings[timeframe] = merged

        # Structure classification.
        old_dir = self._structure.get(timeframe, "insufficient")
        new_dir = _classify_structure(merged)

        self._prev_structure[timeframe] = old_dir
        self._structure[timeframe] = new_dir

        transition = None
        if old_dir != new_dir and old_dir != "insufficient":
            transition = f"{old_dir}_to_{new_dir}"
            logger.info(
                "structure transition on %s: %s -> %s", timeframe, old_dir, new_dir
            )

        return {
            "direction": new_dir,
            "swings_count": len(merged),
            "transition": transition,
        }

    def snapshot(self) -> dict:
        """Return full multi-timeframe structure state.

        Returns a dict keyed by timeframe with direction, swings (last 6),
        and transition info.  Also includes ``alignment`` and ``htf_bias``.
        """
        result: dict = {}
        for tf in self._swings:
            old = self._prev_structure.get(tf, "insufficient")
            cur = self._structure.get(tf, "insufficient")
            transition = (
                f"{old}_to_{cur}"
                if old != cur and old != "insufficient"
                else None
            )
            result[tf] = {
                "direction": cur,
                "swings": self._swings[tf][-6:],
                "transition": transition,
            }

        # Alignment: check if all tracked timeframes agree.
        directions = [v["direction"] for v in result.values()]
        unique = set(directions) - {"insufficient"}
        if len(unique) == 1:
            result["alignment"] = f"aligned_{unique.pop()}"
        else:
            result["alignment"] = "mixed"

        # HTF bias: consensus of H4 and H1 (if present).
        htf_dirs = []
        for htf in ("H4", "H1"):
            d = self._structure.get(htf)
            if d and d != "insufficient":
                htf_dirs.append(d)
        if htf_dirs and len(set(htf_dirs)) == 1:
            result["htf_bias"] = htf_dirs[0]
        elif htf_dirs:
            result["htf_bias"] = "mixed"
        else:
            result["htf_bias"] = "insufficient"

        return result

    def trend_for(self, timeframe: str) -> str:
        """Current trend direction for a single timeframe."""
        return self._structure.get(timeframe, "insufficient")

    def last_swing(self, timeframe: str, kind: str | None = None) -> dict | None:
        """Most recent swing point, optionally filtered by ``'high'`` or ``'low'``."""
        swings = self._swings.get(timeframe, [])
        if kind is not None:
            swings = [s for s in swings if s["kind"] == kind]
        return swings[-1] if swings else None


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Validate core logic with synthetic candle data."""

    # --- helper to build candles ---
    def _candle(o: float, h: float, l: float, c: float, idx: int) -> dict:
        return {
            "open": o, "high": h, "low": l, "close": c,
            "evidence_id": f"test_{idx}",
            "closed_at_utc": f"2026-01-01T00:{idx:02d}:00Z",
        }

    # 1. Bullish structure: series of higher highs and higher lows.
    #    Build a zigzag:  low, high, higher_low, higher_high, ...
    #    We need at least 8 candles with 2-bar wings.
    bullish_candles = [
        _candle(100, 102, 99,  101, 0),   # base
        _candle(101, 103, 100, 102, 1),   # rising
        _candle(102, 110, 101, 109, 2),   # swing high candidate
        _candle(109, 108, 100, 101, 3),   # pull back
        _candle(101, 105, 98,  100, 4),   # lower — confirms swing high at 2, swing low candidate
        _candle(100, 104, 99,  103, 5),   # rising
        _candle(103, 106, 102, 105, 6),   # rising
        _candle(105, 115, 104, 114, 7),   # higher swing high candidate
        _candle(114, 113, 103, 104, 8),   # pullback
        _candle(104, 107, 101, 103, 9),   # swing low area
        _candle(103, 105, 102, 104, 10),  # rising
        _candle(104, 108, 103, 107, 11),  # continues up
    ]

    tracker = StructureTracker()
    res = tracker.update("M5", bullish_candles)
    swings = tracker._swings["M5"]

    assert len(swings) > 0, "should detect at least one swing"
    logger.info("bullish test — detected %d swings: %s", len(swings), swings)

    # 2. Test swing detection directly with a clean zigzag.
    #    Create an unambiguous pattern with clear 2-bar wing fractals.
    clean_candles = [
        # low region
        _candle(100, 101, 99, 100, 0),
        _candle(100, 101, 98, 99,  1),
        _candle(99,  100, 95, 96,  2),   # swing low at index 2 (low=95)
        _candle(96,  101, 96, 100, 3),
        _candle(100, 103, 99, 102, 4),
        # high region
        _candle(102, 108, 101, 107, 5),
        _candle(107, 112, 106, 111, 6),
        _candle(111, 120, 110, 119, 7),  # swing high at index 7 (high=120)
        _candle(119, 118, 108, 109, 8),
        _candle(109, 115, 107, 110, 9),
        # lower low region
        _candle(110, 111, 100, 101, 10),
        _candle(101, 102, 97,  98,  11),
        _candle(98,  99,  90,  91,  12), # swing low at index 12 (low=90)
        _candle(91,  98,  91,  97,  13),
        _candle(97,  103, 96,  102, 14),
        # lower high region
        _candle(102, 106, 101, 105, 15),
        _candle(105, 110, 104, 109, 16),
        _candle(109, 115, 108, 114, 17), # swing high at index 17 (high=115, < 120 = LH)
        _candle(114, 113, 105, 106, 18),
        _candle(106, 109, 104, 107, 19),
    ]

    tracker2 = StructureTracker()
    res2 = tracker2.update("H1", clean_candles)
    swings2 = tracker2._swings["H1"]

    # We expect: SL@95 (idx2), SH@120 (idx7), SL@90 (idx12), SH@115 (idx17)
    sh_list = [s for s in swings2 if s["kind"] == "high"]
    sl_list = [s for s in swings2 if s["kind"] == "low"]
    logger.info("clean test — highs: %s, lows: %s", sh_list, sl_list)

    assert len(sh_list) >= 2, f"expected >=2 swing highs, got {len(sh_list)}"
    assert len(sl_list) >= 2, f"expected >=2 swing lows, got {len(sl_list)}"

    # LH + LL -> bearish
    direction = tracker2.trend_for("H1")
    assert direction == "bearish", f"expected bearish, got {direction}"
    logger.info("clean test — direction=%s (correct)", direction)

    # 3. Transition detection: feed bullish first, then bearish.
    tracker3 = StructureTracker()

    # Bullish candles: HH + HL (clear fractals at idx 2, 7, 12, 17)
    bull = [
        # SL1 region — swing low at idx 2 (low=90)
        _candle(100, 102, 96, 97,  0),
        _candle(97,  99,  93, 94,  1),
        _candle(94,  96,  90, 92,  2),   # SL @ 90
        _candle(92,  98,  92, 97,  3),
        _candle(97,  103, 96, 102, 4),
        # SH1 region — swing high at idx 7 (high=115)
        _candle(102, 108, 101, 107, 5),
        _candle(107, 112, 106, 111, 6),
        _candle(111, 115, 110, 114, 7),  # SH @ 115
        _candle(114, 112, 105, 106, 8),
        _candle(106, 109, 104, 107, 9),
        # SL2 region — swing low at idx 12 (low=93, HL vs 90)
        _candle(107, 108, 99, 100, 10),
        _candle(100, 101, 95, 96,  11),
        _candle(96,  98,  93, 95,  12),  # SL @ 93 (HL)
        _candle(95,  103, 95, 102, 13),
        _candle(102, 110, 101, 109, 14),
        # SH2 region — swing high at idx 17 (high=122, HH vs 115)
        _candle(109, 116, 108, 115, 15),
        _candle(115, 120, 114, 119, 16),
        _candle(119, 122, 118, 121, 17), # SH @ 122 (HH)
        _candle(121, 119, 112, 113, 18),
        _candle(113, 116, 111, 115, 19),
    ]
    r1 = tracker3.update("M15", bull)
    assert r1["direction"] == "bullish", f"expected bullish, got {r1['direction']}"

    # Now feed bearish candles (fresh set treated as new window).
    tracker3.update("M15", clean_candles)
    r3_dir = tracker3.trend_for("M15")
    snap = tracker3.snapshot()
    logger.info("transition test — M15 direction=%s, snapshot=%s", r3_dir, snap)

    # 4. Snapshot alignment.
    tracker4 = StructureTracker()
    tracker4._structure["H4"] = "bullish"
    tracker4._structure["H1"] = "bullish"
    tracker4._structure["M15"] = "bullish"
    tracker4._swings["H4"] = [{"kind": "high", "price": 100, "time": None, "evidence_id": None, "bar_index": 0}]
    tracker4._swings["H1"] = [{"kind": "high", "price": 100, "time": None, "evidence_id": None, "bar_index": 0}]
    tracker4._swings["M15"] = [{"kind": "high", "price": 100, "time": None, "evidence_id": None, "bar_index": 0}]
    snap4 = tracker4.snapshot()
    assert snap4["alignment"] == "aligned_bullish", f"expected aligned_bullish, got {snap4['alignment']}"
    assert snap4["htf_bias"] == "bullish", f"expected htf_bias=bullish, got {snap4['htf_bias']}"
    logger.info("alignment test — OK")

    # 5. last_swing helper.
    tracker5 = StructureTracker()
    tracker5.update("H1", clean_candles)
    lsh = tracker5.last_swing("H1", kind="high")
    lsl = tracker5.last_swing("H1", kind="low")
    assert lsh is not None, "expected a swing high"
    assert lsl is not None, "expected a swing low"
    assert lsh["kind"] == "high"
    assert lsl["kind"] == "low"
    logger.info("last_swing test — high=%s, low=%s", lsh, lsl)

    # 6. Insufficient data.
    tracker6 = StructureTracker()
    r6 = tracker6.update("M1", [_candle(100, 101, 99, 100, i) for i in range(3)])
    assert r6["direction"] == "insufficient"
    logger.info("insufficient test — OK")

    logger.info("all self_test checks passed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    self_test()
