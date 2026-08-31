# Multi-Timeframe + Market Structure Level Implementation Roadmap

**Goal:** Integrate timeframe-based market structure classification + session-aware filtering to achieve better entry accuracy.

---

## Module 1: Structure Strength Scoring

### New File: `market_structure_strength.py`

```python
"""Classify market structure strength by timeframe and correlation level."""

from dataclasses import dataclass
from typing import Literal

TimeframeLevel = Literal["M5", "M15", "H1", "H4"]
StructureStrength = Literal["strong", "medium", "weak"]

@dataclass
class StructureStrengthScore:
    timeframe: TimeframeLevel
    strength: StructureStrength
    confidence: float  # 0-100
    swing_count: int  # Number of valid swings at this TF
    fvg_active: bool  # Any FVGs present
    order_block_active: bool  # Any OBs present
    ote_in_zone: bool  # Price in OTE zone
    liquidity_present: bool  # Liquidity pools active
    
@dataclass
class MultiTimeframeAlignment:
    primary_tf: TimeframeLevel  # Where trade executes (usually M5)
    confirmation_tfs: list[TimeframeLevel]  # Supporting timeframes
    alignment_score: float  # 0-100: M5→M15→H1 direction agreement
    cascade_confirmed: bool  # Does it cascade cleanly? (↑M5→M15→H1 or ↓M5→M15→H1)
    conflict_tfs: list[TimeframeLevel]  # TFs that disagree on direction

class StructureStrengthScorer:
    """Score market structure quality and multi-TF alignment."""
    
    def score_timeframe_strength(
        self,
        tf: TimeframeLevel,
        tracker_snap: dict,  # From StructureTracker.snapshot()
        fvg_state: dict,
        ob_state: dict,
        ote_state: dict,
        liquidity_state: dict,
        current_price: float
    ) -> StructureStrengthScore:
        """
        Rate structure quality at one timeframe.
        
        Inputs:
        - Swing detection (clean + confirmed)
        - FVG presence and fill status
        - Order block presence and test count
        - OTE zone and price position
        - Liquidity pool strength
        
        Output: Strength classification + confidence 0-100
        
        Factors:
        - Minimum 2 swings for "strong" (impulse + correction)
        - Active (unfilled) FVG = +15 pts
        - Order block with ≥1 test = +10 pts
        - Price in OTE zone = +20 pts
        - Liquidity pool nearby (within 50 pips) = +15 pts
        - Multiple factors = compound bonus
        """
        pass
    
    def align_timeframes(
        self,
        scores: dict[TimeframeLevel, StructureStrengthScore],
        direction: str  # "bullish" or "bearish" at M5
    ) -> MultiTimeframeAlignment:
        """
        Check if higher timeframes confirm M5 direction.
        
        Rules:
        1. M5 provides entry trigger
        2. M15 must agree on direction (or be neutral)
        3. H1 confirmation is bonus, not required
        4. H4 is structural context, used for stop placement
        
        Returns alignment score and any conflicts.
        """
        pass
```

---

## Module 2: Session & Time Context

### New File: `session_context.py`

```python
"""Capture current session context and time-based entry rules."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SessionType = Literal[
    "asian_morning",
    "london_open", 
    "london_close",
    "us_morning",
    "us_afternoon",
    "us_close",
    "overnight"
]

@dataclass
class CandlePosition:
    """Where are we within the current bar?"""
    bar_age_seconds: float  # Elapsed seconds since bar open
    bar_total_seconds: float  # Total bar duration (60 for M1, 300 for M5, etc)
    pct_through_bar: float  # 0.0 to 1.0
    is_bar_young: bool  # < 10% through bar (early candle)
    is_bar_old: bool  # > 80% through bar (late candle)
    close_in_seconds: float  # Seconds until bar closes

@dataclass
class SessionContext:
    utc_time: datetime
    broker_time: datetime
    session_type: SessionType
    seconds_to_session_end: float
    time_zone: str  # "UTC", "UK", "US/ET"
    candle_pos: CandlePosition
    
    # Qualitative filters
    is_high_impact_news_upcoming: bool = False
    is_volatile_session: bool = False
    session_strength: Literal["opening", "midday", "closing"] = "midday"

class SessionContextBuilder:
    """Determine current session and time context."""
    
    def build(self, utc_time: datetime, broker_tz: str) -> SessionContext:
        """
        Determine:
        1. Current session (Asian/London/US/Overnight)
        2. Time to session end
        3. Candle position within current bar
        4. Session quality (opening = volatile, midday = normal, closing = tight)
        
        Session Rules (UTC times, adjust for broker):
        - Asian: 21:00-06:00 UTC
        - London: 08:00-16:30 UTC (overlap 08:00-12:00 with US)
        - US: 13:30-21:00 UTC
        - Overnight: 16:30-21:00 + 21:00-08:00 (illiquid)
        """
        pass
    
    def get_session_entry_quality(self, ctx: SessionContext) -> float:
        """
        Apply time-based discount to entry confidence.
        
        Factors:
        - Overlapping sessions (London/US open) = +10% quality
        - Asian session = -15% (lower liquidity for gold)
        - Closing hour = -20% (large moves, wide stops)
        - Overnight = blocked entirely
        - Near news release = blocked
        
        Returns multiplier 0.0 to 1.2
        """
        pass
```

---

## Module 3: Enhanced Entry Policy

### Modifications to `entry_policy.py`

```python
# Add imports
from session_context import SessionContext, SessionContextBuilder
from market_structure_strength import StructureStrengthScorer, MultiTimeframeAlignment

# Add to SCORE_WEIGHTS
SCORE_WEIGHTS: dict[str, float] = {
    "location": 0.20,  # Reduced
    "response": 0.25,  # Reduced
    "participation": 0.12,
    "htf_alignment": 0.25,  # Increased (now includes multi-TF logic)
    "plan_fit": 0.08,
    "multi_tf_alignment": 0.10,  # NEW: Cross-timeframe confirmation
}

# Add session filter
def apply_session_filter(
    policy_decision: PolicyDecision,
    session_ctx: SessionContext,
    structure_alignment: MultiTimeframeAlignment
) -> PolicyDecision:
    """
    Post-process policy decision based on session/time context.
    
    Logic:
    1. If overnight session → BLOCK (return_code = "session_blocked")
    2. If closing hour + weak alignment → reduce confidence by 20%
    3. If strong multi-TF alignment + London/US overlap → boost by 10%
    4. If early candle (< 10% through) + weak signal → wait
    5. If late candle (> 80% through) + weak signal → block (reentry next bar)
    """
    pass

def score_multi_timeframe_component(
    alignment: MultiTimeframeAlignment,
    primary_tf_strength: float  # From StructureStrengthScorer
) -> float:
    """
    New component: Multi-timeframe confirmation score (0-10).
    
    Scoring:
    - Cascade confirmed (M5→M15→H1 agreement) = 9-10
    - M5 + M15 agreement = 7-8
    - M5 only (no conflict) = 5-6
    - TF conflict (M5 vs M15 disagree) = 2-3 or BLOCK
    
    This multiplies with structure strength rating.
    """
    pass
```

---

## Module 4: Market Structure Integration

### Modifications to `market_structure.py`

```python
# Add to _compute_impl()

def _compute_impl(engine: MarketAnalysisEngine, current_price: float) -> dict:
    # ... existing code ...
    
    # NEW: Score structure strength per timeframe
    strength_scorer = StructureStrengthScorer()
    strength_scores = {}
    for tf in ("M5", "M15", "H1", "H4"):
        if tf in candle_data:
            fvg_state = engine.fvg_detector.get_state(tf)
            ob_state = engine.ob_detector.get_state(tf)
            ote_state = engine.ote_calculator.get_state(tf)
            liq_state = engine.liquidity_map.get_state(tf)
            tf_snap = structure_snap.get(tf, {})
            
            strength_scores[tf] = strength_scorer.score_timeframe_strength(
                tf, tf_snap, fvg_state, ob_state, ote_state, liq_state, current_price
            )
    
    # NEW: Check multi-TF alignment
    primary_direction = engine.tracker.trend_for("M5")
    alignment = strength_scorer.align_timeframes(strength_scores, primary_direction)
    
    # Extend output dict
    output = _build_compact_context(engine, structure_snap, current_price)
    output["structure_strength_scores"] = {
        tf: asdict(score) for tf, score in strength_scores.items()
    }
    output["multi_tf_alignment"] = asdict(alignment)
    
    return output
```

---

## Module 5: Qwen Prompt Enhancement

### Modifications to `context_compiler.py` (or entry prompt)

Add to Qwen's facts packet:

```json
{
    "market_context": {
        "structure_strength": {
            "M5": {"strength": "strong", "confidence": 85, "swing_count": 3},
            "M15": {"strength": "medium", "confidence": 65, "swing_count": 2},
            "H1": {"strength": "weak", "confidence": 40, "swing_count": 1}
        },
        "multi_timeframe_alignment": {
            "primary_tf": "M5",
            "cascade_confirmed": true,
            "alignment_score": 82,
            "conflicts": []
        },
        "session_context": {
            "session_type": "london_open",
            "time_to_session_end": 18000,  # seconds
            "candle_position": "young",  # or "old"
            "session_quality": 1.10
        }
    }
}
```

---

## Implementation Order

1. **Phase 1a:** `market_structure_strength.py` (scoring logic)
2. **Phase 1b:** `session_context.py` (time awareness)
3. **Phase 2:** Integrate into `market_structure.py` output
4. **Phase 3:** Modify `entry_policy.py` to use new signals
5. **Phase 4:** Update Qwen prompt (context_compiler.py) to receive signals
6. **Phase 5:** Backtest & validate

---

## Testing Checkpoints

| Checkpoint | What to Verify | Pass Criteria |
|---|---|---|
| **Unit: Strength Scorer** | Does it correctly rate swings, FVGs, OBs? | 90%+ accuracy vs manual audit |
| **Unit: Alignment** | Multi-TF agreement detection | Matches historical cascade patterns |
| **Integration: market_structure.py** | New fields in output dict | Schema validation passes |
| **Integration: entry_policy.py** | Session filter applied | Correctly blocks/reduces overnight |
| **Backtest: Accuracy** | Multi-TF vs single-TF comparison | ≥10% improvement in Sharpe or win rate |
| **Walk-forward: Live** | Paper trading with new signals | 3×40-event blocks profitable + stable |

---

## Preserved Behavior

✅ Core structure trading logic (swings, FVGs, OBs, OTE) is untouched  
✅ Qwen-based trade manager continues managing post-trade  
✅ SL/TP calculation unchanged  
✅ Research governance & hypothesis testing protocol unchanged

