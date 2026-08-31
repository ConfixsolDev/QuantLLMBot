"""Convert raw candlestick data into narrative chart descriptions for LLM reasoning.

2026-08-28 R&D finding: LLMs reason better from narrative structure descriptions
than from raw OHLC arrays. This module encodes the "chart language" that traders
use when describing price action to each other, converting arrays into stories
that Qwen can reason about directly.

Design principle: Every candlestick, level, and pattern gets ONE sentence that
describes its meaning, not its numbers. Qwen then reasons about the story, not
the data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class CandleNarrative:
    """One timeframe's current price action in narrative form."""
    timeframe: str
    trend_direction: str  # "up" | "down" | "consolidating"
    highest_high: float | None = None
    lowest_low: float | None = None
    pattern: str = ""  # "higher_high", "lower_low", "double_top", etc.
    current_state: str = ""  # "breaking_above_resistance", "testing_support", etc.
    confluence_notes: list[str] = None  # e.g., ["order_block_4600", "fvg_unfilled_below"]
    next_level_watch: str = ""  # "watching 4610 for breakout confirmation"

    def as_narrative(self) -> str:
        """Render as one 2-3 sentence story."""
        lines = []

        # Trend line
        if self.highest_high and self.lowest_low:
            if self.trend_direction == "up":
                lines.append(
                    f"{self.timeframe}: Uptrend intact with HH at {self.highest_high}, "
                    f"HL at {self.lowest_low}."
                )
            elif self.trend_direction == "down":
                lines.append(
                    f"{self.timeframe}: Downtrend with LH at {self.highest_high}, "
                    f"LL at {self.lowest_low}."
                )
            else:
                lines.append(
                    f"{self.timeframe}: Consolidating between {self.lowest_low} "
                    f"and {self.highest_high}."
                )

        # Pattern and confluence
        if self.confluence_notes:
            confluence_str = ", ".join(self.confluence_notes)
            lines.append(f"Confluence: {confluence_str}.")

        # Next watch level
        if self.next_level_watch:
            lines.append(f"Next: {self.next_level_watch}")

        return " ".join(lines)


def describe_timeframe(
    timeframe: str,
    candles: Sequence[Mapping[str, Any]],
    levels: Sequence[Mapping[str, Any]] | None = None,
    fvg_list: Sequence[Mapping[str, Any]] | None = None,
    order_blocks: Sequence[Mapping[str, Any]] | None = None,
) -> CandleNarrative:
    """Convert raw candle data into a narrative description.

    Args:
        timeframe: "H4", "H1", "M15", etc.
        candles: List of recent candles, ordered oldest→newest.
                 Each: {"open", "high", "low", "close", "volume", ...}
        levels: Structural levels (support/resistance).
        fvg_list: Fair value gaps.
        order_blocks: Order block zones.

    Returns:
        CandleNarrative: One paragraph story of this timeframe's state.
    """
    if not candles or len(candles) < 2:
        return CandleNarrative(timeframe=timeframe, trend_direction="unknown")

    # Analyze trend from recent candles (last 5-10)
    recent = candles[-5:] if len(candles) >= 5 else candles
    highs = [float(c.get("high", 0)) for c in recent]
    lows = [float(c.get("low", 0)) for c in recent]
    closes = [float(c.get("close", 0)) for c in recent]

    current_high = max(highs)
    current_low = min(lows)
    prev_high = max(highs[:-1]) if len(highs) > 1 else highs[0]
    prev_low = min(lows[:-1]) if len(lows) > 1 else lows[0]

    # Determine trend direction
    if current_high > prev_high and current_low > prev_low:
        trend = "up"
        pattern = "higher_high_higher_low"
    elif current_high < prev_high and current_low < prev_low:
        trend = "down"
        pattern = "lower_high_lower_low"
    elif closes[-1] > closes[0]:
        trend = "up"
        pattern = "consolidating_upward"
    elif closes[-1] < closes[0]:
        trend = "down"
        pattern = "consolidating_downward"
    else:
        trend = "consolidating"
        pattern = "sideways"

    # Collect confluence points
    confluence = []
    if levels:
        for level in levels:
            level_price = float(level.get("price", 0))
            level_name = level.get("name", "level")
            # Only note levels near recent price action
            if abs(level_price - closes[-1]) / closes[-1] < 0.01:  # Within 1%
                confluence.append(f"{level_name} ({level_price:.2f})")

    if fvg_list:
        for fvg in fvg_list:
            if not fvg.get("filled"):
                confluence.append(f"FVG gap unfilled")

    if order_blocks:
        for ob in order_blocks:
            confluence.append(f"order block {ob.get('name', 'zone')}")

    # Determine next watch level
    if trend == "up":
        next_watch = f"watching {current_high:.2f} for breakout confirmation"
    elif trend == "down":
        next_watch = f"watching {current_low:.2f} for breakdown confirmation"
    else:
        next_watch = f"watching bounds {current_low:.2f}-{current_high:.2f}"

    return CandleNarrative(
        timeframe=timeframe,
        trend_direction=trend,
        highest_high=current_high,
        lowest_low=current_low,
        pattern=pattern,
        confluence_notes=confluence,
        next_level_watch=next_watch,
    )


def compose_market_narrative(
    price_data: Mapping[str, Any],
) -> str:
    """Build a complete multi-timeframe market narrative for Qwen.

    Args:
        price_data: Dict with keys like "H4", "H1", "M15", "M5", "M1",
                   each containing candles, levels, FVG, order blocks.

    Returns:
        A narrative story that describes the market structure across timeframes
        in a way Qwen can reason about (not raw data).
    """
    narratives: dict[str, str] = {}

    for tf in ["D1", "H4", "H1", "M30", "M15", "M5", "M1"]:
        if tf not in price_data:
            continue

        tf_data = price_data[tf]
        candles = tf_data.get("candles", [])
        levels = tf_data.get("levels", [])
        fvg = tf_data.get("fvg", [])
        ob = tf_data.get("order_blocks", [])

        narrative = describe_timeframe(tf, candles, levels, fvg, ob)
        narratives[tf] = narrative.as_narrative()

    # Compose hierarchical narrative: HTF first, then LTF
    story_lines = []

    # Higher timeframes (structure)
    for tf in ["D1", "H4", "H1"]:
        if tf in narratives:
            story_lines.append(narratives[tf])

    # Middle timeframes (confirmation)
    for tf in ["M30", "M15"]:
        if tf in narratives:
            story_lines.append(narratives[tf])

    # Lower timeframes (execution)
    for tf in ["M5", "M1"]:
        if tf in narratives:
            story_lines.append(narratives[tf])

    return "\n".join(story_lines)


def prompt_section_market_narrative(
    price_data: Mapping[str, Any],
    title: str = "MARKET STRUCTURE NARRATIVE",
) -> str:
    """Format market narrative as a prompt section ready for Qwen.

    Returns:
        A complete section that can be inserted into the Qwen prompt.
    """
    narrative = compose_market_narrative(price_data)
    return f"""{title}:

{narrative}

Use this narrative to understand price structure across timeframes. Focus on:
1. Which timeframe is showing the clearest trend or pattern?
2. Where do multiple timeframes show confluence (alignment)?
3. What is the next level of interest (support/resistance) given this structure?
4. Does the current market structure support a directional bias or suggest waiting?
"""
