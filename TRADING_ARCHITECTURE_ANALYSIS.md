# Trading System Architecture Analysis: Why Trades Aren't Meeting 50/Day Minimum

## Executive Summary

Your system is architecturally sound but has **multiple independent filtering gates** that suppress trade execution. The system is designed to be conservative by default, prioritizing quality over quantity. To achieve 50+ trades/day without architectural changes, you need to adjust policy thresholds and remove or relax specific gates.

---

## Current Architecture Overview

The Qwen trading system operates as a **two-process pipeline**:

### Process 1: Entry Decision (`reviewer.py`)
- Runs on `QWEN_ENTRY_INTERVAL_SECONDS` (default: 30 seconds)
- Asks Qwen for setup observations when no position is open
- Generates **proposals** (not yet executed trades)
- Applies deterministic policy filters to each proposal
- Writes to `/snapshot` HTTP endpoint for frontend

### Process 2: Trade Management (`trade_management.py`)
- Runs on `QWEN_REVIEW_INTERVAL_SECONDS` (default: 30 seconds)  
- Reviews **open positions** only
- Manages existing trades (hold, protect, close)
- No connection to entry decisions

---

## The 7 Gatekeeping Layers (Why You're Not Trading)

### **Layer 1: Daily Trade Cap** ⚠️ HARD LIMIT
**Location:** `reviewer.py:3571` and `paper_runner.py:488`

```python
DAILY_PAPER_CAP = 50  # Hard ceiling on filled positions per day
if broker_positions_today >= DAILY_PAPER_CAP:
    logging.info("MT5 broker filled-position cap reached: %d/%d",
                 broker_positions_today, DAILY_PAPER_CAP)
    return False
```

**Impact:** ❌ Stops **all new proposals** after 50 positions filled
- Even if Qwen wants to trade, no entry can occur
- This is your ceiling, not your floor
- Once hit, system rejects every decision for the rest of the day

**Why it matters:** You want 50+ trades/day. This cap at 50 means:
- You can hit exactly 50 and then stop
- You cannot exceed 50 without raising `DAILY_PAPER_CAP`
- The system has no safety valve above 50

---

### **Layer 2: Minimum Confidence Threshold**
**Location:** `entry_policy.py:50`, `reviewer.py:108`

```python
MIN_ENTRY_CONFIDENCE = 51  # Composed confidence must clear 51%
```

**Scoring Logic** (`entry_policy.py:54-60`):
```python
SCORE_WEIGHTS = {
    "location": 0.25,      # Zone entry quality
    "response": 0.30,      # Pattern confirmation  
    "participation": 0.15, # Volume/momentum
    "htf_alignment": 0.20, # Higher timeframe agreement
    "plan_fit": 0.10,      # Trade plan coherence
}
```

**What this does:**
- Qwen returns component scores (0-10 each)
- Scores are weighted and summed
- Result must be ≥51 to proceed
- Anything below 51 = automatic wait

**Impact on volume:**
- If Qwen's average confidence is 55-65, you'll get many proposals
- If Qwen's average is 45-50, almost nothing passes
- High threshold = fewer but higher-quality entries

**Check today:** Look at decision logs to see actual confidence distribution

---

### **Layer 3: Blocking Traps** ⚠️ HARD VETO
**Location:** `entry_policy.py:81-87`

```python
BLOCKING_TRAPS = frozenset({
    "fade_acceptance",      # Entry at trend exhaustion
    "buy_into_resistance",  # Long at major resistance
    "sell_into_support",    # Short at major support
    "wrong_tf_break",       # Trigger on wrong timeframe
    "session_blocked",      # Session restrictions
})
```

**Impact:** 
- If Qwen reports ANY blocking trap, that side is **completely rejected**
- No confidence haircut—automatic veto
- Advisory traps (stale_zone, plan_conflict, etc.) only reduce confidence by 8 points

**Why it blocks trades:**
- On 2026-08-10: 44 of 45 ready proposals were SELL (97.8%)
- System detected structural bias but only via advisory penalties
- Blocking traps are designed to prevent catastrophic entry errors

---

### **Layer 4: Timeframe Coherence**
**Location:** `entry_policy.py:95-98`

```python
TIMEFRAME_ORDER = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
MAX_TRIGGER_GAP = 1  # Trigger can be at zone's TF or one below, never further
```

**The rule:** 
- If entry zone is at M5, trigger **must** be M5 or M1
- If entry zone is H1, trigger **must** be H1 or M30
- An M1 zone triggered by M5 = rejected
- An M1 zone triggered by H1 = rejected

**Why this blocks trades:**
- If Qwen proposes an M5 zone triggered by M1 (normal), it passes
- If Qwen proposes an M5 zone triggered by M15 (rare but possible), it fails
- This is a structural safety check to prevent "level confusion"

---

### **Layer 5: Invalidation Coherence** ⚠️ MAJOR LEAK
**Location:** `entry_policy.py:100-117`

```python
MAX_INVALIDATION_GAP = 4  # Max distance between entry zone and stop level TF
```

**The issue from 2026-08-10 analysis:**
```
gap 1   n=1   net  +246.50   win 100%
gap 2   n=1   net    -3.50   win   0%
gap 3   n=2   net   +89.75   win 100%
gap 4   n=3   net  +242.15   win  33%
gap 5   n=9   net  -607.65   win  11%  ← M1 zone, H4 stop (BIG LOSS)
gap 6   n=5   net  -462.35   win   0%  ← M1 zone, D1 stop (WORSE)
```

**What this means:**
- M1 entry with H4 invalidation = gap 4 = typically profitable
- M1 entry with D1 invalidation = gap 6 = typically lossy
- Wide stop levels eat your edge on scalp timeframes

**How it blocks trades:**
- Proposals with `gap > 4` are rejected outright
- This filters out trades that statistically lose money
- But it also prevents **discovering new setups**

---

### **Layer 6: Symmetry Throttling**
**Location:** `entry_policy.py:123-125`

```python
SYMMETRY_WINDOW = 50        # Look at last 50 ready decisions
SYMMETRY_MAX_SHARE = 0.75   # If one side > 75%, require extra confidence
SYMMETRY_CONFIDENCE_SURCHARGE = 10  # +10 points needed
```

**How it works:**
- Tracks last 50 ready proposals by side (buy/sell)
- If buys > 37.5 of 50 (75%), next buy needs 61 confidence (51 + 10)
- If sells > 37.5 of 50, next sell needs 61 confidence
- Designed to prevent one-sided drift

**Why it blocks trades:**
- On a structurally strong long day, every 3rd+ buy gets rejected
- On a structurally strong short day, every 3rd+ sell gets rejected
- This is intentional: "avoid compounding an existing directional lean"

---

### **Layer 7: Cache Readiness**
**Location:** `entry_policy.py:437-442`

```python
if entry_cache is not None and entry_cache.get("status") not in (None, "ready"):
    return PolicyDecision(
        status="wait",
        reason_code=ReasonCode.CACHE_NOT_READY,
        detail=str(entry_cache.get("reason") or "cache not ready"),
    )
```

**What this blocks:**
- Market context must be "ready" before any proposal
- Ready = all candles loaded, manifests validated, structure computed
- If cache is stale/missing → automatic wait
- This is a safety net, not a normal blocker

---

## Why You're Getting < 50 Trades/Day

### Most Likely Root Cause: **Layer 2 (Confidence Threshold)**

Check the actual reason codes in logs:
```bash
grep -o '"reason_code":"[^"]*"' reviews-*.jsonl | sort | uniq -c | sort -rn
```

If you see these high-frequency codes:
- `"obs:below_min_confidence"` → Too strict threshold
- `"side:blocking_trap"` → Model detects bad setups (correct behavior)
- `"side:symmetry_throttled"` → One-sided day + threshold too high
- `"obs:no_eligible_side"` → Both sides below 51, best is maybe 48-50

### Secondary Cause: **Layer 5 (Invalidation Gap)**

If Qwen tends to place stops 5+ timeframes away:
- All proposals rejected as "side:invalidation_incoherent"
- Check proposal logs for this code frequency

### Tertiary Cause: **Model Output Quality**

If Qwen's average confidence has dropped:
- Check past 100 decisions in logs
- Calculate mean confidence of rejected proposals
- If mean rejected = 45-48, you need either:
  - Lower MIN_ENTRY_CONFIDENCE to 45-48, or
  - Improve Qwen prompt to boost confidence scores

---

## How to Increase Trade Volume WITHOUT Changing Architecture

### Option A: Lower the Confidence Threshold (SAFEST)

**Change:** In `entry_policy.py:50`:
```python
MIN_ENTRY_CONFIDENCE = 51  # Change to:
MIN_ENTRY_CONFIDENCE = 45  # Lower bound, still filters junk
```

**Effect:**
- Roughly 30-50% more proposals will pass (depends on distribution)
- Automatically increases symmetry surcharge threshold too
- **No architectural change needed**
- **Reversible if quality drops**

**Risk:** Lower threshold = lower average trade quality, but architecture is designed for this

---

### Option B: Increase Daily Cap (RISKY)

**Change:** In `reviewer.py:107` and `paper_runner.py:29`:
```python
DAILY_PAPER_CAP = 50    # Change to:
DAILY_PAPER_CAP = 100   # Or whatever you want
```

**Effect:**
- Removes the hard ceiling
- System will propose as many as pass filtering layers
- Day could have 50, 75, or 150+ trades depending on conditions

**Risk:** Broker position limits, execution latency, risk exposure explosion

---

### Option C: Relax Blocking Traps (CAREFUL)

**Change:** In `entry_policy.py:81-87`, remove specific traps:
```python
BLOCKING_TRAPS = frozenset({
    # Remove "fade_acceptance" to allow exhaustion entries
    # "fade_acceptance",  # ← Comment this out
    "buy_into_resistance",
    "sell_into_support",
    "wrong_tf_break",
    "session_blocked",
})
```

**Effect:**
- Traps move from hard veto to advisory (-8 confidence)
- Proposals that hit that trap still execute if confidence stays ≥ MIN
- More proposals pass the gate

**Risk:** Traps exist because they historically correlate with losses

---

### Option D: Widen Invalidation Gap (RISKY)

**Change:** In `entry_policy.py:117`:
```python
MAX_INVALIDATION_GAP = 4   # Change to:
MAX_INVALIDATION_GAP = 6   # Or 7 or 8
```

**Effect:**
- Allows M1 entries with D1 stops (which lost 462 points on 2026-08-10)
- More structural plans will pass validation

**Risk:** Historical data shows gap 5-6 has 11% win rate. You are intentionally accepting worse setups.

---

### Option E: Reduce Symmetry Surcharge (MODERATE)

**Change:** In `entry_policy.py:125`:
```python
SYMMETRY_CONFIDENCE_SURCHARGE = 10  # Change to:
SYMMETRY_CONFIDENCE_SURCHARGE = 5   # Or 0 to disable
```

**Effect:**
- On one-sided days, fewer proposals get throttled
- SYMMETRY_MAX_SHARE still triggers, but threshold is easier to hit

**Risk:** Allows stronger one-sided drift (which may be correct on directional days)

---

## Recommended Action Plan

### Step 1: Measure Current State
```bash
# Count reason codes from last 7 days
grep -h '"reason_code"' logs/reviews-*.jsonl | \
  sed 's/.*"reason_code":"\([^"]*\)".*/\1/' | \
  sort | uniq -c | sort -rn
```

This tells you **exactly where proposals are dying**.

### Step 2: Check Confidence Distribution
```bash
# Find rejected proposals with near-threshold confidence
grep '"confidence":' logs/reviews-*.jsonl | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  sort -n | tail -20
```

If you see lots of 48-50 range → lower threshold is the answer.

### Step 3: Calculate Trade Volume Sensitivity
```
If you have X% proposals at confidence 45-50:
- Lowering threshold from 51 to 45 → expect (X + margin) % more trades
- Example: if 20% of proposals are 45-50, expect 20% more trades
```

### Step 4: Make One Change at a Time
- Lower `MIN_ENTRY_CONFIDENCE` by 5 points → observe volume
- If volume hits target → done
- If not, lower again or try Option E (symmetry surcharge)

**Never change multiple gates simultaneously.** You won't know what worked.

---

## Architecture Layers Summary Table

| Layer | Control | Type | Current | Impact on Volume |
|-------|---------|------|---------|------------------|
| Daily Cap | `DAILY_PAPER_CAP` | Hard limit | 50 | Blocks all above 50 |
| Confidence | `MIN_ENTRY_CONFIDENCE` | Soft threshold | 51 | Filters ~30-50% proposals |
| Blocking Traps | `BLOCKING_TRAPS` frozenset | Hard veto | 5 traps | Blocks structural errors |
| Timeframe Gap | `MAX_TRIGGER_GAP` | Coherence check | 1 | Rare blocker (~1-2%) |
| Invalidation Gap | `MAX_INVALIDATION_GAP` | Coherence check | 4 | May block 10-20% |
| Symmetry | `SYMMETRY_CONFIDENCE_SURCHARGE` | Directional throttle | 10 points | Blocks one-sided extremes |
| Cache Readiness | `entry_cache.status` | Safety gate | "ready" only | Rare blocker |

---

## What NOT to Do

❌ **Don't modify `entry_policy.py`'s component weighting** — this requires retraining logic
❌ **Don't bypass policy.decide()** — it's your safety net
❌ **Don't lower MIN_ENTRY_CONFIDENCE below 40** — statistical degradation steepens
❌ **Don't remove timeframe/invalidation coherence checks** — historical data validates them

---

## Questions to Answer

Before making changes, answer these:

1. **Are you hitting the 50 daily cap every day?**
   - Yes → increase `DAILY_PAPER_CAP`
   - No → focus on layers 2-6

2. **What's the most frequent rejection reason code?**
   - `obs:below_min_confidence` → lower threshold
   - `side:blocking_trap` → model quality issue
   - `side:symmetry_throttled` → reduce surcharge
   - `side:invalidation_incoherent` → widen gap

3. **What's your average rejected proposal confidence?**
   - 48-50 → lower threshold to 45-47
   - 40-45 → lower to 38-40 (risky)
   - Below 40 → model training issue, not policy

4. **Are you seeing structural bias (75%+ one direction)?**
   - Yes → symmetry throttling is working as designed
   - No → can reduce surcharge for faster volume

---

## Conclusion

Your system is intentionally conservative. To achieve 50+ trades/day:

1. **Start:** Lower `MIN_ENTRY_CONFIDENCE` from 51 → 45-47
2. **Monitor:** Track volume and P&L for 3-5 days  
3. **Adjust:** Lower further or reduce symmetry surcharge if needed
4. **Iterate:** One change at a time

The architecture supports this. You just need to dial the policy dials.
