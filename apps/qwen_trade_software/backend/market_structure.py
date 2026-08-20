"""Market structure orchestrator — computes ICT/SMC structure context for Qwen entry facts.

Ties together structure_tracker, structural_event, fvg_detector, order_block,
ote_calculator, and liquidity_map into a single compact context dict that fits
inside the entry facts packet without blowing the 4K context window.
"""

import logging
from dataclasses import dataclass
from typing import Callable
from market_context_cache import get_cached_completed_bars
from instrument_config import InstrumentConfig, canonical_symbol, instrument_for
from structure_tracker import StructureTracker
from structural_event import StructuralEventDetector
from fvg_detector import FVGDetector
from order_block import OrderBlockDetector
from ote_calculator import OTECalculator
from liquidity_map import LiquidityMap
from market_atr import wilder_atr
from market_structure_shadow import publish_sample

log = logging.getLogger(__name__)

BarProvider = Callable[[str, str, int], list[dict]]


@dataclass
class MarketAnalysisEngine:
    """State-isolated analysis engine for exactly one instrument."""

    config: InstrumentConfig
    bar_provider: BarProvider = get_cached_completed_bars

    def __post_init__(self) -> None:
        self.tracker = StructureTracker()
        self.event_detector = StructuralEventDetector(
            self.config.displacement_min_body
        )
        self.fvg_detector = FVGDetector(self.config.fvg_min_width)
        self.ob_detector = OrderBlockDetector(
            self.config.order_block_touch_tolerance
        )
        self.ote_calculator = OTECalculator(self.config.ote_min_impulse)
        self.liquidity_map = LiquidityMap(
            self.config.equal_level_tolerance,
            self.config.sweep_overshoot_max,
        )

    def compute(self, current_price: float = 0.0) -> dict:
        return _compute_impl(self, current_price)


_ENGINES: dict[str, MarketAnalysisEngine] = {}


def engine_for(
    symbol: str,
    *,
    config: InstrumentConfig | None = None,
    bar_provider: BarProvider = get_cached_completed_bars,
) -> MarketAnalysisEngine:
    """Return persistent per-instrument state; no detector crosses symbols."""
    resolved = config or instrument_for(symbol)
    key = canonical_symbol(resolved.key)
    engine = _ENGINES.get(key)
    if engine is None:
        engine = MarketAnalysisEngine(resolved, bar_provider)
        _ENGINES[key] = engine
    return engine


def reset(symbol: str | None = None):
    """Reset one instrument, or all engines for tests and recovery."""
    if symbol is None:
        _ENGINES.clear()
    else:
        _ENGINES.pop(canonical_symbol(symbol), None)


def compute_structure_context(symbol: str, current_price: float = 0.0) -> dict:
    """Compute multi-timeframe market structure context.

    Called once per 30s entry cycle from compact_entry_facts().
    Returns a compact dict suitable for injection into the Qwen facts packet.

    The output is designed to be small — summary-level data only, not full
    swing lists or event histories. This keeps the facts packet within Qwen's
    4096 context window.
    """
    try:
        context = engine_for(symbol).compute(current_price)
        context["instrument"] = instrument_for(symbol).key
        return context
    except Exception:
        log.exception("market_structure:compute_failed")
        return {"status": "error"}


def _compute_impl(engine: MarketAnalysisEngine, current_price: float) -> dict:
    # 1. Fetch candles for each timeframe
    candle_data = {}
    symbol = engine.config.broker_symbol
    for tf, count in engine.config.timeframe_bars.items():
        bars = engine.bar_provider(symbol, tf, count)
        if bars:
            candle_data[tf] = bars

    if not candle_data:
        return {"status": "no_data"}

    # 2. Update structure tracker (swing detection + trend classification)
    for tf, candles in candle_data.items():
        engine.tracker.update(tf, candles)

    structure_snap = engine.tracker.snapshot()

    # 3. Detect structural events (BOS/CHoCH/MSS)
    all_events = []
    for tf, candles in candle_data.items():
        swings = engine.tracker._swings.get(tf, [])
        direction = engine.tracker.trend_for(tf)
        events = engine.event_detector.detect(tf, candles, swings, direction, current_price)
        all_events.extend(events)

    # 4. Scan for FVGs
    for tf, candles in candle_data.items():
        engine.fvg_detector.scan(tf, candles, current_price)

    # 5. Detect order blocks from structural events
    for tf, candles in candle_data.items():
        tf_events = [e for e in all_events if e.get("timeframe") == tf]
        if tf_events:
            engine.ob_detector.detect(tf, candles, tf_events)
        engine.ob_detector.update_status(tf, current_price)

    # 6. Calculate OTE zones
    for tf in candle_data:
        swings = engine.tracker._swings.get(tf, [])
        engine.ote_calculator.calculate(tf, swings,
                                  structural_events=all_events,
                                  current_price=current_price)

    # 7. Update liquidity map
    for tf, candles in candle_data.items():
        swings = engine.tracker._swings.get(tf, [])
        engine.liquidity_map.update(tf, swings, candles, current_price)

    # 8. Build the authoritative native output first.
    output = _build_compact_context(engine, structure_snap, current_price)

    # 9. Publish immutable M5 evidence across the research-process boundary.
    # The return value is deliberately not attached to output: external
    # evidence must never enter Qwen's prompt before explicit promotion.
    _publish_shadow_input(symbol, candle_data, output)
    return output


def _publish_shadow_input(symbol: str, candle_data: dict[str, list[dict]],
                          native_context: dict) -> dict:
    """Publish normalized comparison input without importing research packages."""
    timeframe = next((tf for tf in ("M5", "M15", "H1", "H4") if candle_data.get(tf)), None)
    if timeframe is None:
        return {"mode": "shadow_only", "status": "no_data", "execution_authority": False}
    bars = candle_data[timeframe]
    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]
    closes = [float(bar["close"]) for bar in bars]
    period = min(14, len(bars) - 1)
    atr = wilder_atr(highs, lows, closes, period) if period >= 2 else None
    if atr is None or atr <= 0:
        return {"mode": "shadow_only", "status": "atr_unavailable",
                "timeframe": timeframe, "execution_authority": False}
    return publish_sample(symbol, bars, atr, native_context)


def _build_compact_context(
    engine: MarketAnalysisEngine, structure_snap: dict, current_price: float
) -> dict:
    """Build the compact context dict for the facts packet.

    MUST BE COMPACT. Each section is 1-3 lines of summary data.
    No full lists of swings or events.
    """
    price_digits = engine.config.analysis_round_digits

    # -- Trend summary: one line per TF --
    trends = {}
    for tf in ("M5", "M15", "H1", "H4"):
        tf_data = structure_snap.get(tf, {})
        trends[tf] = tf_data.get("direction", "unknown")

    # -- Recent structural events: last 2 events max --
    recent_events = engine.event_detector.active_events(max_age_minutes=30)
    event_summaries = []
    for evt in recent_events[-2:]:
        event_summaries.append({
            "type": evt["event_type"],      # BOS/CHoCH/MSS
            "dir": evt["direction"],         # bullish/bearish
            "tf": evt["timeframe"],
            "level": round(evt["broken_level"], price_digits),
            "confidence": evt.get("confidence", "medium"),
        })

    # -- Nearest FVGs: max 2 (nearest bullish + nearest bearish) --
    fvg_context = []
    for direction in ("bullish", "bearish"):
        fvg = engine.fvg_detector.nearest_fvg(current_price, direction)
        if fvg:
            fvg_context.append({
                "dir": fvg["direction"],
                "tf": fvg["timeframe"],
                "hi": round(fvg["high"], price_digits),
                "lo": round(fvg["low"], price_digits),
                "filled_pct": round(fvg.get("filled_pct", 0), 2),
            })

    # -- Nearest order blocks: max 2 --
    ob_context = []
    for direction in ("bullish", "bearish"):
        ob = engine.ob_detector.nearest_ob(current_price, direction)
        if ob:
            ob_context.append({
                "dir": ob["direction"],
                "tf": ob["timeframe"],
                "hi": round(ob["high"], price_digits),
                "lo": round(ob["low"], price_digits),
                "trigger": ob.get("trigger_event", {}).get("event_type", ""),
                "tests": ob.get("tested_count", 0),
            })

    # -- Nearest OTE: max 1 --
    ote_context = None
    ote = engine.ote_calculator.nearest_ote(current_price)
    if ote:
        ote_context = {
            "dir": ote["direction"],
            "tf": ote["timeframe"],
            "sweet_spot": round(ote["sweet_spot"], price_digits),
            "ote_hi": round(ote["ote_high"], price_digits),
            "ote_lo": round(ote["ote_low"], price_digits),
            "in_zone": ote.get("price_in_zone", False),
        }

    # -- Liquidity: nearest pools + recent sweeps --
    liq_pools = []
    for side in ("buy_side", "sell_side"):
        pools = engine.liquidity_map.active_pools(side=side)
        if pools:
            # Find nearest to current price
            nearest = min(pools, key=lambda p: abs(p["price"] - current_price))
            liq_pools.append({
                "type": nearest["type"],  # EQH/EQL
                "price": round(nearest["price"], price_digits),
                "touches": nearest.get("count", 0),
                "strength": nearest.get("strength", "moderate"),
            })

    recent_sweeps = engine.liquidity_map.recent_sweeps(max_age_minutes=30)
    sweep_summaries = []
    for sw in recent_sweeps[-1:]:  # last sweep only
        sweep_summaries.append({
            "pool": sw.get("pool_type", ""),
            "dir": sw.get("direction", ""),
            "price": round(sw.get("pool_price", 0), price_digits),
            "overshoot": round(sw.get("overshoot", 0), price_digits),
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
