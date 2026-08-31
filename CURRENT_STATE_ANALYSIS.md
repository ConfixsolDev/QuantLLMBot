# Trading Strategy Current State Analysis

**Date:** 2026-08-28  
**Status:** Reverting to stable/fallback-positive-proper-closing-20260821 branch baseline  
**Core Objective:** Add multi-timeframe + market structure level detection while preserving core trading behavior

---

## What's Currently Implemented (Core Strategy)

### 1. Market Structure Core (`market_structure.py`)
✅ **Present and Functional:**
- Single-timeframe structure analysis (fetches M5, M15, H1, H4 bars)
- Swing detection via `StructureTracker`
- Structural event detection (BOS/CHoCH/MSS) via `StructuralEventDetector`
- FVG (Fair Value Gap) detection via `FVGDetector`
- Order block detection via `OrderBlockDetector`
- OTE (Optimal Trade Entry) calculation via `OTECalculator`
- Liquidity pool mapping via `LiquidityMap`
- Compact context dict for Qwen (fits in 4K token budget)

**Current Processing Pipeline:**
1. Fetch candles for each timeframe independently
2. Update structure tracker for each timeframe
3. Detect structural events
4. Scan for FVGs
5. Detect order blocks
6. Calculate OTE zones
7. Update liquidity map
8. Build compact output (trends, events, FVGs, order blocks, OTE, liquidity)

✅ **ATR Calculation:** `market_atr.py` provides Wilder's ATR (14-period default)

---

### 2. Entry Policy & Decision (`entry_policy.py`)
✅ **Deterministic Policy (v2.0):**
- Receives Qwen observations (both LONG and SHORT sides)
- Composes confidence from components: location (25%), response (30%), participation (15%), HTF alignment (20%), plan fit (10%)
- Enforces known trap detection (fade_acceptance, buy_into_resistance, sell_into_support, etc.)
- Blocking vs. advisory traps with penalty scoring
- **MIN_ENTRY_CONFIDENCE = 51** (threshold)
- Timeframe coherence checking (M1 wick cannot trigger H4 zone)

✅ **Currently Missing:** 
- ❌ Session-aware entry filtering (time-of-day logic)
- ❌ Candle timing / session boundary awareness
- ❌ Multi-timeframe correlation scoring for combined signals

---

### 3. Trade Management (`trade_manager.py`, `trade_management.py`)
✅ **Present:**
- Qwen-based post-trade behavior management
- SL/TP management
- Multi-leg position handling (first leg + add-on logic)
- Adaptive locks and exit regimes

---

## What's Missing (What Needs Implementation)

### 1. **Multi-Timeframe Alignment Scoring**
Currently, each timeframe is analyzed independently in a loop. Need:
- **Cross-timeframe relationship scoring:** Do M5 and M15 agree on direction?
- **Cascade confirmation:** Is M5 aligned with M15 which is aligned with H1?
- **Signal strength multiplier:** Confidence increases when higher timeframes converge on the same structure

### 2. **Market Structure Level Classification by Timeframe**
Need to distinguish **level importance** by timeframe context:
- **M5 level:** Intrabar structure, micro-swings (tighter stops)
- **M15 level:** Session micro-trend, valid for 30-60min holds
- **H1 level:** Session trend, valid for multi-hour moves
- **H4 level:** Swing formation level, structural importance

Each timeframe should have a **market structure strength rating:**
- Strong: Multiple swing confirmations, OTE aligned, liquidity present
- Medium: Partial confirmation, some alignment
- Weak: Isolated structure, no multi-TF confirmation

### 3. **Session & Time-of-Day Entry Filters**
Currently missing from `entry_policy.py`:

**To Add:**
- Current time-of-day (UTC/broker time)
- Session type: Asian, London open, US open, US close, overnight
- Session rules:
  - Certain sessions may favor certain structure levels
  - Time-to-market-close reduces position horizon
  - Candle alignment within session boundaries

**Candle Timing Consideration:**
- Distance from session start/end
- Candle proximity to structural levels relative to current bar position
- Time-decay on stale structure zones

### 4. **Combined Entry Signal Quality**
Replace simple confidence scoring with **cascade qualification:**

```
Entry Quality = 
  Base Confidence (current)
  × Multi-TF Alignment Score (M5→M15→H1 agreement)
  × Level Strength Score (structure validation across timeframes)
  × Session Quality Score (time-of-day + candle timing)
  × ATR Multiplier (position sizing per volatility)
```

---

## Current Files That Need Enhancement

| File | Current Role | Enhancement Needed |
|------|------|------|
| `market_structure.py` | Compute structure per TF independently | Add cross-TF alignment scoring + level strength classification |
| `entry_policy.py` | Compose confidence from components | Add session filter + candle timing awareness + multi-TF multiplier |
| `entry_contract.py` | Qwen response schema | Extend to accept timeframe preference signals |
| `session_planner.py` | Session scheduling | Integrate time-of-day filter into policy checks |
| `market_graph/context_compiler.py` | Build Qwen input context | Add multi-TF alignment + level strength signals |

---

## Implementation Strategy

### Phase 1: Market Structure Level Classification
1. Extend `MarketAnalysisEngine` to score structure strength per timeframe
2. Add cross-TF alignment detection (M5 vs M15 vs H1 direction agreement)
3. Create `StructureStrengthScorer` class to rate confidence by timeframe importance

### Phase 2: Session & Timing Awareness
1. Add `SessionContext` class capturing current time, session type, candle position
2. Extend `entry_policy.py` to accept and apply session filters
3. Implement time-of-day decay on stale structure zones

### Phase 3: Combined Signal Quality
1. Integrate alignment scoring into confidence calculation
2. Add session quality multiplier to policy
3. Verify Qwen prompts receive timeframe preference signals

### Phase 4: Validation
1. Backtest with new multi-TF + level + session signals
2. Compare accuracy improvement vs. baseline
3. Reconcile with MT5 broker results per research loop protocol

---

## What's Preserved

✅ **Core Strategy (unchanged):**
- Market structure trading at key levels
- Proper SL/TP calculation
- Qwen-based trade manager for post-trade behavior
- Order block and FVG logic
- OTE zone detection
- Liquidity mapping

✅ **Research & Governance:**
- Frozen hypothesis testing protocol (RESEARCH_LOOP.md)
- Broker reconciliation requirements
- Evidence approval checkpoints
- Walk-forward validation gates

---

## Next Steps

1. **Review structure strength scoring logic** — Define what makes a level "strong" across timeframes
2. **Design multi-TF alignment scoring** — How much agreement is needed between M5 and M15 to boost confidence?
3. **Implement session context capture** — Integrate broker time + session type into decision flow
4. **Build combined signal multiplier** — Formula for blending all factors into final entry quality score
5. **Create test harness** — Run backtest comparing old vs. new accuracy metrics

