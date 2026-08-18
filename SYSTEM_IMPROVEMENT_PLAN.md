# Full System Improvement Plan
**Date:** 2026-08-17  
**Branch:** `feat/decision-layer-stage1-2`  
**Principle:** Refine the existing doctrine, never replace it. One piece at a time, validated before the next.

---

## Current Architecture (what exists today)

```
┌──────────────────────────────────────────────────────────────────────┐
│  SESSION PLANNER                                                      │
│  Reads H4/H1/D1 completed candles → day plan + session plan           │
│  Qwen call: direction bias, key levels, session read                  │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ bias + session context
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  ENTRY REVIEWER (reviewer.py) — every 30s                             │
│  Builds compact_entry_facts: M1/M5/M15 candles, nearby levels,        │
│  live_map, session, playbook, volume                                  │
│  Qwen call → status: ready/wait/skip, direction, zone, confidence     │
│  Output: paper proposal                                               │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ proposal (side, zone, confidence, SL/TP)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  PAPER EXECUTOR (paper_executor.py)                                   │
│  Waits for price inside_zone (since 2026-08-13 fix)                   │
│  Places bracket: structural when possible, fixed $3/$5 fallback       │
│  HTF (H1/H4/D1) rejects fixed micro brackets entirely                │
│  Fills on MT5 demo account                                           │
└──────────────────────────────┬───────────────────────────────────────┘
                               │ open position
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  TRADE MANAGEMENT (trade_management.py) — every 30s                   │
│  1. Deterministic guard (confirmed_management_guard):                  │
│     - Checks reached_favorable_level_refs                             │
│     - M1 direction against position → if latest M1 closes against     │
│       AND M5 confirms at a reached level → close                      │
│  2. Qwen management call (if guard doesn't fire):                     │
│     - 4 exit conditions: invalidation, flip, arithmetic, time         │
│     - hold/protect/close decision                                     │
│  3. Rebracket: nearest PREVIOUS_HIGH/LOW behind/ahead of entry        │
└──────────────────────────────────────────────────────────────────────┘
```

### What works
- **Direction identification:** Qwen's HTF read is correct. Today's sells were right.
- **Level detection:** live_mapped_levels.py fractal swings, operator-mapped shelves, pivot/ATR levels
- **Entry zone gating:** inside_zone enforcement prevents favorable_outside fills
- **HTF micro bracket rejection:** H1/H4/D1 no longer get $3/$5 stops
- **Core skill doctrine:** context → hunt → arm is well-defined in core_skill.md

### What's broken
1. **Management guard fires on noise levels** — M5_PREVIOUS_LOW is a mechanical label, not structural. Both trades today closed on it.
2. **No LTF structural confirmation before entry** — executor fills on zone touch, doesn't wait for CHoCH/BOS on M1/M5
3. **Dashboard shows all Python-detected levels** — no distinction between Qwen-qualified and raw computed
4. **ATR not reaching model calls** — wired but returning None everywhere
5. **confidence=0 proposals executing** — model can't express conviction on valid setups
6. **H4 proposals have no structural brackets** — model keeps generating, guard keeps rejecting
7. **Stale mapped_trade_levels.json** — 4 days old, polluting context with irrelevant levels
8. **live_map field unknown to v004** — injected into context but model never trained on it

---

## Target Architecture (what we're building toward)

```
┌──────────────────────────────────────────────────────────────────────┐
│  SESSION PLANNER (unchanged)                                          │
│  Direction + key levels + session read                                 │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 1: DIRECTION (Qwen entry reviewer — unchanged core)             │
│  HTF auction read → bias (buy/sell), confidence, hunt zone            │
│  Output: direction + named zone + invalidation                        │
│  This is what Qwen already does well. Don't touch.                    │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 2: ZONE QUALIFICATION (refinement layer)                        │
│  While price approaches the hunt zone:                                │
│  - Count zone tests (already in live_mapped_levels.count_visits)      │
│  - Track noise: intrabar probes vs closed-candle decisions            │
│  - List confirmations needed: CHoCH on M1/M5, FVG left behind,       │
│    closed rejection candle                                            │
│  - Qwen sees zone test count + noise count + confirmation list        │
│  Output: zone status (untested / first_test / noise / confirmed)      │
│                                                                       │
│  KEY RULE: A level is only "confirmed broken" by a CLOSED candle      │
│  on that level's own timeframe. A wick/shadow is a probe, not a       │
│  decision. (Grimes, Brooks — already in the knowledge base)           │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  STEP 3: ENTRY CONFIRMATION (the missing piece)                       │
│  Price is inside the zone. Now wait for LTF structural proof:         │
│                                                                       │
│  A) CHoCH + FVG (primary):                                           │
│     - M1/M5 breaks counter-trend structure (CHoCH)                    │
│     - Break leaves an FVG (gap between candles)                       │
│     - Entry on FVG mitigation in discount/premium of CHoCH leg        │
│     - SL behind CHoCH swing point (tight, structural)                 │
│                                                                       │
│  B) BOS continuation:                                                 │
│     - HTF BOS already established                                     │
│     - Pullback takes minor liquidity (inducement)                     │
│     - LTF BOS in trend direction confirms continuation                │
│     - Enter on retest of BOS level                                    │
│                                                                       │
│  C) Liquidity sweep + rejection:                                      │
│     - Price pierces PDH/PDL or session high/low                       │
│     - Closes back inside on M5 (false break)                          │
│     - Entry on return to the OB that caused the sweep                 │
│                                                                       │
│  D) M1 failure at mapped zone (already built):                        │
│     - m1_failure_at_zone() in live_mapped_levels.py                   │
│     - Completed M1 probes zone, fails to close beyond                 │
│     - This IS a basic CHoCH signal, just named differently            │
│                                                                       │
│  IMPLEMENTATION: Python detects the patterns mechanically (fractal     │
│  math). Qwen judges "is this confirmation meaningful given HTF         │
│  context?" Same model call, richer context.                           │
│                                                                       │
│  Output: armed entry with structural SL (CHoCH swing) and             │
│  structural TP (next opposing HTF level)                              │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  EXECUTOR (refined)                                                   │
│  Receives armed entry with:                                           │
│  - Confirmation type (CHoCH/BOS/sweep/m1_failure)                     │
│  - Structural SL from confirmation swing point                        │
│  - Structural TP from HTF level                                       │
│  - Entry price from FVG mitigation or retest level                    │
│  Places bracket directly from confirmation geometry                   │
└──────────────────────────────┬───────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│  TRADE MANAGEMENT (refined)                                           │
│                                                                       │
│  Deterministic guard changes:                                         │
│  - CLOSED CANDLE ONLY: no action on intrabar touch/probe              │
│  - THESIS-TIMEFRAME MATCH: M5 levels don't invalidate M15+ theses    │
│  - QWEN-QUALIFIED LEVELS: guard only fires on levels Qwen has cited   │
│    in an entry or management decision, not raw Python labels          │
│  - Noise tracking: count probes at a level without closing through;   │
│    3+ probes without close = noise, not invalidation                  │
│                                                                       │
│  Qwen management changes:                                             │
│  - Sees confirmation_type from entry (knows HOW the trade was armed)  │
│  - Sees zone test count and probe/noise count                         │
│  - 4 exit conditions unchanged (invalidation/flip/arithmetic/time)    │
│  - But invalidation now requires closed candle on the level's own TF  │
│                                                                       │
│  Dashboard changes:                                                   │
│  - Only shows Qwen-qualified levels (cited in a decision)             │
│  - Shows confirmation type and noise count per zone                   │
│  - Separates "candidate levels" from "active levels"                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Pieces (ordered, one at a time)

### Piece 1 — Management: closed candle, not touch
**Files:** `trade_manager.py`, `trade_management.py`  
**What changes:**
- `confirmed_management_guard` already checks `_closed_beyond` for M1 and M5 — that part is correct
- BUT `reached_favorable_level_refs` populates from peak price vs level price (line 159-163 in trade_manager.py) — this is a **price-crossed check**, not a closed-candle check. If peak_price ever traded past a level, it's marked as "reached" forever, even if it was a wick
- Fix: `reached_favorable` should require a closed M1 (minimum) that settled beyond the level, not just peak tick price
- The guard then only fires on levels where a closed candle confirmed the reach

**What this fixes:** Today's two trades. The M5_PREVIOUS_LOW was "reached" by a wick/tick, the guard saw M1 close direction was "against" the position, fired close. With closed-candle reach requirement, wick touches don't count.

**Validates by:** Run paper trades for 2-3 sessions. Trades should survive through intermediate wick probes and only close when a candle actually closes through the management level.

---

### Piece 2 — Thesis-timeframe matching in management
**Files:** `trade_manager.py`  
**What changes:**
- `_reaction_level` currently accepts ANY level with HIGH/LOW/PIVOT/R/S markers from M5 through D1
- Add: if the entry thesis is built on M15/M30/H1 structure, only M15+ levels qualify as management exit triggers
- M5/M1 levels are noise in the path for an M15+ thesis — they're entry-granularity, not management-granularity
- The entry plan already carries `structure_timeframe` — use it to filter which levels the guard considers

**What this fixes:** Management closing M15 thesis trades on M5_PREVIOUS_LOW. The guard would only consider M15_PREVIOUS_LOW or higher as valid exit triggers for that thesis.

**Validates by:** Review the management log. M15+ thesis trades should show "hold" through M5 levels and only react to M15+ structure.

---

### Piece 3 — Qwen-qualified levels on dashboard
**Files:** `trade_management.py` (chart_levels), frontend  
**What changes:**
- Track which level_ids Qwen has cited in entry decisions (from `active_level`, `decision_level_ref`, `confirmation_evidence_ids`)
- Dashboard endpoint separates levels into: `qualified` (Qwen-cited) vs `candidate` (Python-detected)
- Frontend renders qualified levels prominently, candidates dimmed or hidden
- Live mapped levels (from live_mapped_levels.py) show their test_count and pattern (double_top etc.)

**What this fixes:** Dashboard noise. Operator sees what Qwen actually used, not 30+ mechanical labels.

**Validates by:** Visual inspection — dashboard should show 5-8 meaningful levels, not 30.

---

### Piece 4 — ATR wiring fix
**Files:** `review_shared.py` (ollama_generate), `market_atr.py`  
**What changes:**
- ATR snapshot is computed but logs show `atr_m1_51=None` on every call
- Trace the wiring: `snapshot_atr()` → where it's called → how it reaches the generate call → why it's None
- Likely: the snapshot is taken but not injected into the generate result dict, or the MT5 connection isn't ready when it's called

**What this fixes:** Regime awareness. Model sees whether volatility is compressed/normal/expanded.

**Validates by:** Log output shows non-None ATR values on every model call.

---

### Piece 5 — Stale mapped_trade_levels.json cleanup
**Files:** `market_context_cache.py` (_mapped_trade_levels), `trade_management.py` (_mapped_trade_level_prices)  
**What changes:**
- Add distance filter: drop any operator-mapped level whose zone midpoint is > 30 points from current price
- Or add `valid_until_utc` to the JSON format and respect it in the loader
- Distance filter is simpler and self-maintaining (5 lines)

**What this fixes:** Context pollution. Levels from Aug 13 at 4349-4369 are 25-45 points below current price (~4395). They waste context tokens and confuse the model.

**Validates by:** Count of loaded operator levels drops from 11 to 3-4 near price.

---

### Piece 6 — M1 rejection gate on entry (existing code, new wiring)
**Files:** `paper_executor.py` or `reviewer.py`  
**What changes:**
- `m1_failure_at_zone()` already exists in `live_mapped_levels.py`
- Wire it into the entry path: after Qwen says "ready" and price is `inside_zone`, also require that a completed M1 has shown rejection at the zone
- This is the simplest form of the CHoCH confirmation — the market probed the zone and failed to close beyond it
- Already described in core_skill.md [entry-process] step 3: "Arm — price inside the band, then closed M5 (preferred) / M1 timing"

**What this fixes:** Entries that fill on the first tick inside the zone without any price rejection evidence. The system waits for the market to show its hand.

**Validates by:** Paper trades should show a brief delay between "inside zone" and "fill", with the fill occurring after a rejection candle. Some setups will expire without filling — that's correct.

---

### Piece 7 — CHoCH/BOS/FVG detection engine (design + build)
**Files:** New file: `confirmation_engine.py`  
**What changes:**
- Mechanical detection of structural patterns on M1/M5 closed candles:
  - **CHoCH:** First break of counter-trend swing structure (lower low in uptrend / higher high in downtrend)
  - **BOS:** Continuation break of trend structure (higher high in uptrend / lower low in downtrend)
  - **FVG:** Gap between candle[i-2].low and candle[i].high (bearish) or candle[i-2].high and candle[i].low (bullish) where candle[i-1] doesn't fill the gap
  - **Liquidity sweep:** Wick beyond PDH/PDL/session high/low + close back inside
- These are pure fractal/candle math — Python detects them mechanically
- Output is injected into the entry context so Qwen can judge: "is this CHoCH meaningful?"
- Qwen's judgment remains the gate — Python proposes, Qwen disposes

**Implementation approach:**
- Use the same fractal_swings() logic from live_mapped_levels.py but on M1/M5 with wing=1-2
- Track swing sequence: HH-HL (uptrend) vs LH-LL (downtrend)
- CHoCH = first swing break against the sequence
- FVG = simple gap check on 3 consecutive candles
- Sweep = wick beyond a known level + close inside

**What this fixes:** The missing "Step 3" in the entry process. Qwen says where, confirmation engine says when.

**Validates by:** Paper trades should show entries timed to structural confirmation rather than raw zone touch. Tighter SL (behind CHoCH swing), better R:R.

---

### Piece 8 — Curriculum: teach Qwen the confirmation vocabulary
**Files:** `store/core_skill.md`, `model_training/knowledge/stage_05_live_contract.jsonl`  
**What changes:**
- Add to core_skill.md: CHoCH, BOS, FVG as confirmation types in the entry-process section
- Add training examples where Qwen reasons about:
  - "M5 CHoCH at resistance zone → sell confirmed"
  - "M1 FVG left at premium of CHoCH leg → limit entry"
  - "Liquidity sweep of Asia high + close back inside → reversal"
- Add examples where Qwen correctly WAITS: "CHoCH not yet formed, hold missing_fact"
- Update management curriculum: thesis-timeframe matching, closed-candle-only exits

**What this fixes:** Model alignment. Qwen learns to express and reason about the confirmation step rather than Python making the judgment.

**Validates by:** Curriculum eval — model correctly identifies CHoCH/BOS/FVG in test examples and uses them in entry/management decisions.

---

### Piece 9 — Confidence calibration
**Files:** Curriculum, `reviewer.py` (invariant check)  
**What changes:**
- Today: `invariant:ready_with_zero_confidence` fires repeatedly — model says ready but confidence=0
- Investigate: is the confidence field miscalibrated in training data? Does the model not know how to express conviction on sell setups?
- Add curriculum examples with calibrated confidence: "clear rejection at mapped resistance with M5 CHoCH → confidence 72" vs "zone reached but no rejection yet → confidence 0, wait"
- Consider: should confidence=0 with status=ready be blocked from generating proposals?

**What this fixes:** Wasteful proposals and potential bad fills on zero-conviction entries.

**Validates by:** confidence=0 + status=ready invariant stops firing. Model expresses 50-80 confidence on valid setups.

---

### Piece 10 — H4 curriculum: structural brackets required
**Files:** Curriculum  
**What changes:**
- Model keeps generating H4 theses with tight/missing invalidation → geometry rejects every time
- Add training examples showing H4 theses with wide structural invalidation (10-20 points, not 3)
- Teach: "H4 thesis needs H4-scale stop behind the H4 swing that proves the idea wrong"
- If the model can't identify a clear H4 invalidation, it should skip, not propose with no structure

**What this fixes:** The generate-then-reject loop. Model either produces viable H4 proposals or doesn't propose.

**Validates by:** H4 rejection rate drops. Proposals that do appear have structural brackets that pass geometry.

---

## Sequencing (Revised 2026-08-17 — regime detection is the foundation)

**Why revised:** Dry run of today's 9 trades proved Piece 2 (thesis-timeframe matching) would have made things WORSE in a ranging market (-$1,117 vs guard's -$21). The market was ranging for trades 1-5, transitioning for trades 6-7, and trending up for trades 8-9. The system needs regime detection BEFORE guard changes. See REGIME_AWARE_ARCHITECTURE.md for full design.

```
FOUNDATION (Week 1, Aug 17-20):
  Piece 0A: ATR wiring fix — compute from cached M1 bars, not fresh MT5 call
            Root cause: mt5_not_connected in snapshot_atr() → bars=0, all nulls
  Piece 0B: Displacement detection — candle body/ATR ratio at mapped levels
  Piece 0C: Swing sequence classification — extend live_mapped_levels.py
  Piece 0D: Range detection — identify oscillation between M5 boundaries
  Piece 0E: Regime hint computation — combine 0A-0D into range/trend/breakout/exhaustion
  Piece 0F: regime_context packet — wire into management facts for Qwen
  → All deterministic Python computation, no behavior change, testable in isolation

GUARD UPGRADE (Week 1, Aug 20-22):
  Piece 1: Split guard into scalp_guard + rejection_guard, routed by regime_hint
  Piece 2: scalp_guard — TP at favorable M5 level WHILE M1 favorable (range)
  Piece 3: rejection_guard — thesis-timeframe matching, M15+ levels only (trend)
  Piece 4: Stale mapped_trade_levels.json cleanup (distance filter)
  → Guard behavior now adapts to market regime

CONTEXT + DASHBOARD (Week 2, Aug 24-27):
  Piece 5: regime_context injected into Qwen management prompt
  Piece 6: Qwen-qualified levels on dashboard (with regime indicator)
  Piece 7: M1 rejection gate on entry (existing code, new wiring)
  Piece 8: Entry target_mode informed by regime (scalp in range, basket in trend)

CURRICULUM (Week 3, Aug 31 - Sep 5):
  Piece 9: Teach Qwen regime vocabulary (range/trend/breakout/exhaustion)
  Piece 10: CHoCH/BOS/FVG detection engine + curriculum
  Piece 11: Confidence calibration (regime-aware)
  Piece 12: H4 curriculum (structural brackets)

FREEZE + TEST (Sep 5):
  Re-freeze build, clear drift, full paper test with regime detection
  48-72h live validation before any further changes

After Week 3:
  Live account testing with all pieces validated
  Collect 2 weeks of live data
  Review and tune
```

---

## Rules for the work

1. **One piece at a time.** Don't start piece N+1 until piece N is validated on paper trades.
2. **No doctrine change.** Every piece refines the existing flow. Qwen decides direction and zone. Confirmation refines when. Management refines exit. Nothing overrides Qwen's read.
3. **Python detects, Qwen judges.** Mechanical pattern detection (CHoCH, FVG, fractal swings) is code. Whether the pattern is meaningful in context is Qwen's call.
4. **Closed candles only.** No system component reacts to intrabar ticks, wicks, or shadows as structural decisions. A probe is not a decision. A close is a decision.
5. **Measure everything.** Every piece adds logging. Every change is scored against the 2-week paper baseline before going live.

---

## What does NOT change

- Qwen's HTF direction read (working)
- The 3-part system architecture: tick data → skill → code (working)
- Session awareness and news exclusion (working)
- Entry zone identification via live_mapped_levels (working)
- The 4 management exit conditions: invalidation/flip/arithmetic/time (working, need better gating)
- Fixed R:R research profile for curriculum (working)
- Operator-mapped levels concept (working, needs staleness filter)
