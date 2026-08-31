# Prompt Redesign: From Raw Data to Narrative Reasoning

**Date:** 2026-08-28  
**Status:** Design & R&D Complete → Ready for Implementation  
**Motivation:** Qwen prompt bloat (44-65 KB actual vs 7-8 KB target). LLMs reason better from narrative than raw math.

## Problem Statement

Current prompt includes 192+ raw candlesticks (96 bars × 7 timeframes) with OHLC arrays at ~150 bytes each. This is **mathematical data** (suited for calculation), not **reasoning input** (suited for LLM interpretation).

- **Current average:** 44 KB
- **Current max:** 64 KB  
- **Target:** 8-10 KB
- **Bloat factor:** 5-8x

## Solution: Chart Narrative Composer

Replace raw arrays with trader-language descriptions. Instead of:
```json
{"open": 4605.2, "high": 4612.1, "low": 4598.3, "close": 4610.5}
```

Send:
```
H1: Uptrend with HH at 4612, HL at 4600. Current pullback to 4605 testing 60% fib.
    Confluence: Order block 4600-4610 + H4 resistance + FVG above. 
    Watch: rejection at 4610 for continuation vs. break below 4600 for reversal.
```

## Implementation Roadmap

### Phase 1: Core Infrastructure (DONE)
- ✅ Created `chart_narrative_composer.py` with:
  - `describe_timeframe()` — converts candles → narrative
  - `compose_market_narrative()` — multi-TF story
  - `prompt_section_market_narrative()` — ready-to-insert prompt section

### Phase 2: Integration (NEXT)
**File:** `reviewer.py` → `compact_entry_facts()` (line 864)

**Changes:**
1. Import `chart_narrative_composer`
2. Add narrative section to the prompt before sending to Qwen
3. Remove or drastically reduce raw candlestick arrays

**Pseudocode:**
```python
# Near line 920-935 (current raw candle section)
# BEFORE: raw_candles = {...}
# AFTER:
if True:  # Enable narrative mode
    narrative = chart_narrative_composer.compose_market_narrative({
        "H4": entry_cache.get("H4_candles"),
        "H1": entry_cache.get("H1_candles"),
        "M15": entry_cache.get("M15_candles"),
        # etc
    })
    packet["market_narrative"] = narrative
    # Skip or minimize raw "recent" and "forming" arrays
else:
    # Fall back to old raw-data path for compatibility
    recent = {}
    for timeframe, keep in (("M1", 3), ("M5", 3), ...):
        ...
```

### Phase 3: Validation
**Metrics to track:**
1. Prompt size (should drop to 10-15 KB)
2. Qwen response quality (ready rate, confidence distribution)
3. Trade accuracy (win rate, avg P&L)
4. Token usage per decision

**Regression test:**
- Re-run today's 229 proposals through new prompt builder
- Compare prompt sizes
- Compare Qwen outputs (bias, confidence, reason text)

### Phase 4: Tuning (Post-implementation)
- Adjust narrative verbosity based on Qwen's reasoning quality
- Add confluence scoring if it improves entry quality
- Collect feedback on which narrative patterns work best

## Architecture Notes

**Why this works:**
1. **Reduces dimensionality:** 192 numbers → 1 story
2. **Aligns with model strength:** LLMs are text reasoners, not calculators
3. **Enables real-time updates:** Easy to describe "price just rejected at 4610" instead of rebuilding arrays
4. **Improves interpretability:** Qwen's reason field will make more sense (it's based on narrative, not data)

**What stays unchanged:**
- Levels (still structured data, needed for zone references)
- Playbooks (still structured, small)
- Session info (still structured, small)
- Regime context (still structured, small)

**What gets replaced:**
- 96-bar history per TF → narrative description
- OHLC arrays → trend + pattern summary
- Raw volume/ticks → confluence notes

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Qwen loses precision on exact price levels | Keep nearby_levels + H1/H4 reference levels structured |
| Narrative misses edge cases | Fallback: can always add "special_case_raw_data" field for outliers |
| Integration breaks entry flow | Phase 3 regression test catches this early |
| Different prompt = different edge cases | Track response distribution week-over-week |

## Success Criteria

1. ✅ Prompt size drops below 15 KB (from 44 KB average)
2. ✅ Ready rate stays same or improves
3. ✅ Confidence distribution unchanged
4. ✅ Win rate stable or improves
5. ✅ No increase in directional contradictions (the bug we just fixed)

## Files Modified

- `chart_narrative_composer.py` — NEW
- `reviewer.py` — `compact_entry_facts()` (line 864)
- `build_manifest.py` — Will pick up prompt_composer.py change automatically

## Timeline

- **Implementation:** 2-3 hours (wire into reviewer.py)
- **Validation:** 6-24 hours (collect test results)
- **Tuning:** 1-2 weeks (optimize narrative patterns)

## Next Step

Once user confirms proceed, wire `chart_narrative_composer` into line ~920 of `compact_entry_facts()`.
