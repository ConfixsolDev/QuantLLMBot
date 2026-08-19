"""Market structure orchestrator — computes ICT/SMC structure context for Qwen entry facts.

Ties together structure_tracker, structural_event, fvg_detector, order_block,
ote_calculator, and liquidity_map into a single compact context dict that fits
inside the entry facts packet without blowing the 4K context window.
"""

import logging
from market_context_cache import get_cached_completed_bars
from live_mapped_levels import fractal_swings
from structure_tracker import StructureTracker
from structural_event import StructuralEventDetector
from fvg_detector import FVGDetector
from order_block import OrderBlockDetector
from ote_calculator import OTECalculator
from liquidity_map import LiquidityMap

log = logging.getLogger(__name__)

# Module-level singletons — persist across 30s reviewer cycles
_tracker = StructureTracker()
_event_detector = StructuralEventDetector()
_fvg_detector = FVGDetector()
_ob_detector = OrderBlockDetector()
_ote_calculator = OTECalculator()
_liquidity_map = LiquidityMap()


# Timeframes and how many bars to fetch for each
STRUCTURE_TIMEFRAMES = {
    "M5": 50,   # 50 M5 bars ≈ 4 hours
    "M15": 40,  # 40 M15 bars ≈ 10 hours
    "H1": 30,   # 30 H1 bars ≈ 30 hours
    "H4": 20,   # 20 H4 bars ≈ 80 hours
}


def reset():
    """Re-initialise all module-level singletons. Useful for testing."""
    global _tracker, _event_detector, _fvg_detector, _ob_detector
    global _ote_calculator, _liquidity_map
    _tracker = StructureTracker()
    _event_detector = StructuralEventDetector()
    _fvg_detector = FVGDetector()
    _ob_detector = OrderBlockDetector()
    _ote_calculator = OTECalculator()
    _liquidity_map = LiquidityMap()


def compute_structure_context(symbol: str = "XAUUSDr", current_price: float = 0.0) -> dict:
    """Compute multi-timeframe market structure context.

    Called once per 30s entry cycle from compact_entry_facts().
    Returns a compact dict suitable for injection into the Qwen facts packet.

    The output is designed to be small — summary-level data only, not full
    swing lists or event histories. This keeps the facts packet within Qwen's
    4096 context window.
    """
    try:
        return _compute_impl(symbol, current_price)
    except Exception:
        log.exception("market_structure:compute_failed")
        return {"status": "error"}


def _compute_impl(symbol: str, current_price: float) -> dict:
    # 1. Fetch candles for each timeframe
    candle_data = {}
    for tf, count in STRUCTURE_TIMEFRAMES.items():
        bars = get_cached_completed_bars(symbol, tf, count)
        if bars:
            candle_data[tf] = bars

    if not candle_data:
        return {"status": "no_data"}

    # 2. Update structure tracker (swing detection + trend classification)
    for tf, candles in candle_data.items():
        _tracker.update(tf, candles)

    structure_snap = _tracker.snapshot()

    # 3. Detect structural events (BOS/CHoCH/MSS)
    all_events = []
    for tf, candles in candle_data.items():
        swings = _tracker._swings.get(tf, [])
        direction = _tracker.trend_for(tf)
        events = _event_detector.detect(tf, candles, swings, direction, current_price)
        all_events.extend(events)

    # 4. Scan for FVGs
    for tf, candles in candle_data.items():
        _fvg_detector.scan(tf, candles, current_price)

    # 5. Detect order blocks from structural events
    for tf, candles in candle_data.items():
        tf_events = [e for e in all_events if e.get("timeframe") == tf]
        if tf_events:
            _ob_detector.detect(tf, candles, tf_events)
        _ob_detector.update_status(tf, current_price)

    # 6. Calculate OTE zones
    for tf in candle_data:
        swings = _tracker._swings.get(tf, [])
        _ote_calculator.calculate(tf, swings,
                                  structural_events=all_events,
                                  current_price=current_price)

    # 7. Update liquidity map
    for tf, candles in candle_data.items():
        swings = _tracker._swings.get(tf, [])
        _liquidity_map.update(tf, swings, candles, current_price)

    # 8. Build compact output
    return _build_compact_context(structure_snap, current_price)


def _build_compact_context(structure_snap: dict, current_price: float) -> dict:
    """Build the compact context dict for the facts packet.

    MUST BE COMPACT. Each section is 1-3 lines of summary data.
    No full lists of swings or events.
    """

    # -- Trend summary: one line per TF --
    trends = {}
    for tf in ("M5", "M15", "H1", "H4"):
        tf_data = structure_snap.get(tf, {})
        trends[tf] = tf_data.get("direction", "unknown")

    # -- Recent structural events: last 2 events max --
    recent_events = _event_detector.active_events(max_age_minutes=30)
    event_summaries = []
    for evt in recent_events[-2:]:
        event_summaries.append({
            "type": evt["event_type"],      # BOS/CHoCH/MSS
            "dir": evt["direction"],         # bullish/bearish
            "tf": evt["timeframe"],
            "level": round(evt["broken_level"], 1),
            "confidence": evt.get("confidence", "medium"),
        })

    # -- Nearest FVGs: max 2 (nearest bullish + nearest bearish) --
    fvg_context = []
    for direction in ("bullish", "bearish"):
        fvg = _fvg_detector.nearest_fvg(current_price, direction)
        if fvg:
            fvg_context.append({
                "dir": fvg["direction"],
                "tf": fvg["timeframe"],
                "hi": round(fvg["high"], 1),
                "lo": round(fvg["low"], 1),
                "filled_pct": round(fvg.get("filled_pct", 0), 2),
            })

    # -- Nearest order blocks: max 2 --
    ob_context = []
    for direction in ("bullish", "bearish"):
        ob = _ob_detector.nearest_ob(current_price, direction)
        if ob:
            ob_context.append({
                "dir": ob["direction"],
                "tf": ob["timeframe"],
                "hi": round(ob["high"], 1),
                "lo": round(ob["low"], 1),
                "trigger": ob.get("trigger_event", {}).get("event_type", ""),
                "tests": ob.get("tested_count", 0),
            })

    # -- Nearest OTE: max 1 --
    ote_context = None
    ote = _ote_calculator.nearest_ote(current_price)
    if ote:
        ote_context = {
            "dir": ote["direction"],
            "tf": ote["timeframe"],
            "sweet_spot": round(ote["sweet_spot"], 1),
            "ote_hi": round(ote["ote_high"], 1),
            "ote_lo": round(ote["ote_low"], 1),
            "in_zone": ote.get("price_in_zone", False),
        }

    # -- Liquidity: nearest pools + recent sweeps --
    liq_pools = []
    for side in ("buy_side", "sell_side"):
        pools = _liquidity_map.active_pools(side=side)
        if pools:
            # Find nearest to current price
            nearest = min(pools, key=lambda p: abs(p["price"] - current_price))
            liq_pools.append({
                "type": nearest["type"],  # EQH/EQL
                "price": round(nearest["price"], 1),
                "touches": nearest.get("count", 0),
                "strength": nearest.get("strength", "moderate"),
            })

    recent_sweeps = _liquidity_map.recent_sweeps(max_age_minutes=30)
    sweep_summaries = []
    for sw in recent_sweeps[-1:]:  # last sweep only
        sweep_summaries.append({
            "pool": sw.get("pool_type", ""),
            "dir": sw.get("direction", ""),
            "price": round(sw.get("pool_price", 0), 1),
            "overshoot": round(sw.get("overshoot", 0), 1),
        })

    return {
        "status": "ok",
        "trends": trends,
        "alignment": structure_snap.get("alignment", "mixed"),
        "htf_bias": structure_snap.get("htf_bias", "mixed"),
        "transition": next(
            (structure_snap[tf]["transition"]
             for tf in ("M5", "M15", "H1", "H4")
             if structure_snap.get(tf, {}).get("transition")),
            None
        ),
        "events": event_summaries,
        "fvgs": fvg_context,
        "order_blocks": ob_context,
        "ote": ote_context,
        "liquidity_pools": liq_pools,
        "sweeps": sweep_summaries,
    }
