# Regime-Aware Operational Architecture
**Date:** 2026-08-17  
**Principle:** ATR + displacement + level timeframe + candle close = one combined signal. Python computes, Qwen judges.

---

## The Problem (Proven by Today's Data)

9 executions, all sells, during a session that transitioned from **range** to **trend up**.

```
Trade 1-5 (05:41–06:20): Price oscillating 4392–4398 (6-pt range)
  → Guard closed all 5 on M5_PREVIOUS_LOW bounce-back
  → Lost the scalp profit ($467 left on the table)

Trade 6-7 (06:24–06:36): Range starting to break (4394–4400)
  → Guard closed on bounce-back again
  → Should have detected regime transition

Trade 8-9 (06:40–06:46): Genuine breakout, price to 4404
  → SELLS into uptrend → -$126, -$276
  → Should have detected trend, not entered short
```

ATR was returning `null` on every call (`mt5_not_connected: No IPC connection`). Even if it worked, ATR ratio alone would not have caught:
- The displacement candle that broke 4398 resistance at 06:30
- The difference between a wick through 4398 (range probe) and a body close through 4398 (acceptance/breakout)
- The M5 swing sequence shifting from mixed (range) to HH-HL (uptrend)

---

## What a 15-Year Trader Reads

A professional trader doesn't read ATR in isolation. They read **four signals as one combined picture**:

### Signal 1: Volatility State (ATR Ratio)
```
atr_ratio_3_51 < 0.6    → compressed, coiling before breakout
atr_ratio_3_51  0.6–1.0 → normal trading conditions
atr_ratio_3_51  1.0–1.5 → expanding, market in motion
atr_ratio_3_51 > 1.5    → displacement, institutional commitment
```

### Signal 2: Displacement (Candle Body vs ATR)
The size of a candle's body relative to the ATR baseline — this is the "sudden move at level" the system misses.
```
body / ATR_51 < 0.3  → noise, no commitment
body / ATR_51  0.3–0.8 → normal move
body / ATR_51  0.8–1.2 → strong move
body / ATR_51 > 1.2  → displacement (institutional order flow)
```

A displacement candle is not just "big ATR." It's a candle with a full body (>70% of range) that covers significant ground. The body ratio matters more than the absolute size because it shows commitment vs. indecision.

### Signal 3: Displacement Context (Where + How)
WHERE the displacement happened and HOW the candle closed relative to the level:
```
Displacement THROUGH H1 level (body closed beyond)
  → Acceptance. Breakout. Trend signal.

Displacement AT H1 level (wick through, body closed back inside)
  → Rejection. Range boundary defense.

Displacement WITH NO level nearby
  → Momentum continuation or exhaustion (depends on sequence)

No displacement at any level
  → Range continuation or balance
```

### Signal 4: Swing Sequence (Structure)
From live_mapped_levels fractal swings — the pattern of recent highs and lows:
```
HH → HL → HH → HL  = Uptrend (buy dips, hold longs through M5 noise)
LH → LL → LH → LL  = Downtrend (sell rallies, hold shorts through M5 noise)
HH → LL or LH → HL  = Mixed / Range (scalp at boundaries)
First LH after HH-HL = Potential trend exhaustion (take profit)
First HL after LH-LL = Potential reversal (take profit)
```

---

## Four Regimes

The combined signal produces one of four regimes. Each regime has its own management contract.

### RANGE
**Detection:** ATR ratio ≤ 1.0 + no displacement (body/ATR < 0.8) + mixed swing sequence + price between known M5/M15 levels.

**Entry behavior:**
- Sell at range top (M5/M15 resistance), buy at range bottom (M5/M15 support)
- Scalp target mode only — TP at the opposing M5 boundary
- M1 failure at zone is sufficient entry trigger

**Management behavior:**
- **Scalp guard (NEW):** Close when price REACHES the favorable M5 level with M1 still moving in the favorable direction. Don't wait for the bounce-back rejection.
- The current guard waits for M1 to close AGAINST → price bounces back → guard fires at worse price. In range, you TAKE the favorable level, you don't wait to be rejected from it.
- Ignore HTF targets. The range IS the trade — take 2-4 points per trip.
- Re-enter on return to the opposite boundary.

**What today would have looked like:**
```
Trade 1: Sell 4395, peak 4394.03, scalp TP at M5_LOW ~4394 → +$50
Trade 2: Sell 4394.77, peak 4392.58, scalp TP at M5_LOW ~4393 → +$90
Trade 3: Sell 4394.36, peak 4392.96, scalp TP at M5_LOW ~4393 → +$68
...
Total range scalp: ~$467 (vs actual -$21)
```

### TREND
**Detection:** ATR ratio > 1.0 OR recent displacement through a level + consistent swing sequence (HH-HL or LH-LL) + M5 acceptance beyond a prior level.

**Entry behavior:**
- Trade WITH the trend only (buy pullbacks in uptrend, sell rallies in downtrend)
- Starter/directional basket target mode
- Entry on pullback to broken level + hold (retest confirmation)

**Management behavior:**
- **Rejection guard only:** The current guard logic is correct for trend — close when M15+ level rejects.
- Thesis-timeframe matching: M5 levels are NOISE in a trend. Only M15+ levels matter for management.
- Hold through M5 counter-moves. A $2 pullback in a $15 trend move is not invalidation.
- Trail stop behind the last confirmed swing low (buy) or swing high (sell).

### BREAKOUT (Range → Trend transition)
**Detection:** ATR was ≤ 0.8 (compressed), now > 1.2 (expanding) + displacement candle closes through range boundary on M5+ + volume/participation spike.

**Entry behavior:**
- Enter on the breakout retest (pullback to broken level that holds)
- Starter basket mode — first target at M15 level, runner at H1 level
- Do NOT scalp the breakout

**Management behavior:**
- Trail stop behind the breakout level (now support/resistance flip)
- Hold for HTF target — the breakout is the beginning of a new trend leg
- If price returns inside the range within 2 M5 candles → false break, close immediately

### EXHAUSTION (Trend → Range transition)
**Detection:** ATR ratio was > 1.2, now declining below 1.0 + displacement failing at HTF level (wick through, body close back) + first counter-trend swing in the sequence (first LH after HH pattern, or first HL after LL pattern).

**Entry behavior:**
- Counter-trend scalp only (reversal_watch mode)
- Tight target — don't expect a full reversal
- Wait for M5 CHoCH before entry

**Management behavior:**
- Take profit at the first M5 level in the counter-trend direction
- Do NOT hold for HTF target — the trend is exhausting, not reversing yet
- If a new displacement re-establishes the trend direction → exit and reassess

---

## Regime Context Packet (What Qwen Receives)

On every management call, Python computes and supplies:

```json
{
  "regime_context": {
    "atr": {
      "atr_m1_51": 1.234,
      "atr_m1_3": 0.987,
      "atr_ratio_3_51": 0.80
    },
    "displacement": {
      "m5_body_atr_ratio": 0.45,
      "m1_body_atr_ratio": 0.32,
      "m5_body_pct": 0.65,
      "at_level": null,
      "through_or_rejected": null
    },
    "range": {
      "nearest_resistance_id": "M5_PREVIOUS_HIGH",
      "nearest_resistance_price": 4398.5,
      "nearest_support_id": "M5_PREVIOUS_LOW",
      "nearest_support_price": 4392.8,
      "width": 5.7,
      "width_atr_ratio": 4.6,
      "bounces_in_range": 4,
      "time_in_range_m5_candles": 9
    },
    "swing_sequence": {
      "m5": "mixed",
      "m15": "mixed",
      "last_m5_swing_high": 4398.2,
      "last_m5_swing_low": 4392.9,
      "swing_count_since_displacement": 4
    },
    "regime_hint": "range"
  }
}
```

### How `regime_hint` is computed (Python, deterministic):

```python
def compute_regime_hint(atr_ratio, displacement_ratio, swing_pattern,
                        prev_atr_ratio=None):
    """
    Simple threshold-based hint. Qwen can override with judgment.
    """
    if atr_ratio is None:
        return "unknown"

    # Breakout: was compressed, now expanding with displacement
    if (prev_atr_ratio and prev_atr_ratio < 0.8
            and atr_ratio > 1.2 and displacement_ratio > 1.0):
        return "breakout"

    # Exhaustion: was expanding, now compressing with failed displacement
    if (prev_atr_ratio and prev_atr_ratio > 1.2
            and atr_ratio < 1.0 and displacement_ratio < 0.5):
        return "exhaustion"

    # Trend: expanding or recent displacement + consistent swings
    if atr_ratio > 1.0 and swing_pattern in ("hh_hl", "lh_ll"):
        return "trend"
    if displacement_ratio > 1.0 and swing_pattern in ("hh_hl", "lh_ll"):
        return "trend"

    # Range: normal/compressed + mixed swings
    if atr_ratio <= 1.0 and swing_pattern == "mixed":
        return "range"

    # Default
    return "range" if swing_pattern == "mixed" else "trend"
```

### How Qwen learns regime (curriculum, not hard-coded):

Qwen receives the full `regime_context` and the Python `regime_hint`. Training examples teach Qwen to:

1. **Confirm the hint** when data supports it:
   - "ATR ratio 0.72, body/ATR 0.3, mixed swings, 4 bounces → range confirmed. Scalp at M5 boundaries."

2. **Override the hint** when context says otherwise:
   - "ATR ratio 0.95 (near threshold), BUT displacement candle just closed through M15 resistance with full body → this is breakout, not range. Hold."
   - "ATR ratio 1.1 (suggests trend), BUT swing sequence is mixed AND price is inside a 5-point M5 range → still range. Scalp."

3. **Read transitions** in real time:
   - "Was range for 9 M5 candles. Last M5: body/ATR 1.4, closed through range top with full body. ATR ratio jumped from 0.7 to 1.3. → Breakout. Stop scalping, hold for HTF target."

---

## Guard Behavior Per Regime

### Current guard (renamed: `rejection_guard`)
Used in: **TREND**, **BREAKOUT**

```
1. Check reached_favorable_level_refs (peak price crossed a level)
2. Filter candidates by thesis-timeframe (M15+ only for M15+ theses)
3. Check latest M1 closes AGAINST position direction
4. If M1 closes against AND M5 confirms rejection → close

This is CORRECT for trend: you want to hold through noise
and only close when structure rejects.
```

### New guard: `scalp_guard`
Used in: **RANGE**, **EXHAUSTION**

```
1. Check reached_favorable_level_refs
2. Filter for M5 levels (these ARE the targets in range)
3. Check if current price is AT or BEYOND the favorable M5 level
4. If price is at the favorable level AND M1 is still in the
   favorable direction (not yet bouncing back) → close for profit

Key difference: close BEFORE the bounce-back, not after.
The scalp guard takes profit AT the level. The rejection
guard waits for rejection FROM the level.
```

### Implementation in `confirmed_management_guard()`:

```python
def confirmed_management_guard(facts: dict, regime: str = "unknown") -> dict | None:
    """Route to the correct guard based on regime."""

    # Invalidation check is regime-independent — always close on invalidation
    invalidation_result = _check_invalidation(facts)
    if invalidation_result:
        return invalidation_result

    if regime in ("range", "exhaustion"):
        return _scalp_guard(facts)
    else:
        return _rejection_guard(facts)  # current logic


def _scalp_guard(facts: dict) -> dict | None:
    """Close when price reaches favorable M5 level while M1 is still favorable."""
    candles = facts.get("completed_candles", [])
    latest_m1 = _get_latest("M1", candles)
    if not latest_m1:
        return None

    side = facts["position"]["side"]
    reached = facts["trade_path"]["reached_favorable_level_refs"]

    # In range, M5 levels ARE the targets
    m5_candidates = [
        ref for ref in reached
        if ref in facts["level_references"]
        and "M5" in str(facts["level_references"][ref].get("level_id", "")).upper()
    ]

    if not m5_candidates:
        return None

    # Check if M1 is still in the FAVORABLE direction (not bouncing back yet)
    favorable_direction = (
        latest_m1.get("direction") == "up" if side == "buy"
        else latest_m1.get("direction") == "down"
    )

    # In scalp mode, we close WHILE favorable (take the money)
    # not AFTER adverse (lose the money)
    if favorable_direction:
        best = m5_candidates[0]  # furthest reached
        return {
            "action": "close",
            "thesis_state": "target_response",
            "decision_level_ref": best,
            "confirmation_type": "target_rejection_confirmed",
            "summary": f"Range scalp: TP at {best} while M1 favorable.",
            "close_confirmed": True,
            "regime": "range_scalp",
        }

    return None  # M1 already adverse — fall through to Qwen
```

---

## ATR Wiring Fix (Root Cause)

ATR returns `null` because `snapshot_atr()` calls `mt5.terminal_info()` from a process where MT5 is not connected.

```
Error: "mt5_not_connected:(-10004, 'No IPC connection')"
Bars: 0
```

**Root cause:** `snapshot_atr()` is called at Qwen request time (in reviewer.py or trade_management.py), but the MT5 connection may not be initialized in that thread/context. The `connect_mt5()` call happens in the main loop but `snapshot_atr()` may execute before connection or in a worker that hasn't called `mt5.initialize()`.

**Fix:** Call `connect_mt5()` inside `snapshot_atr()` before accessing MT5, or pass the M1 bars directly from the market_context_cache (which already has them) instead of making a separate MT5 call.

The better fix: **compute ATR from cached bars, not from a fresh MT5 call.** The market_context_cache already fetches and caches M1 bars. `atr_from_rates()` can consume those directly:

```python
def snapshot_atr_from_cache(m1_bars: list[dict], symbol: str = None) -> dict:
    """Compute ATR from already-cached M1 bars. No MT5 call needed."""
    if not m1_bars or len(m1_bars) < max(ATR_M1_PERIODS) + 1:
        return {"ok": False, "error": "insufficient_cached_bars", ...}
    computed = atr_from_rates(m1_bars, periods=ATR_M1_PERIODS)
    return {
        "ok": computed["atr_m1_51"] is not None,
        "atr_m1_51": computed["atr_m1_51"],
        "atr_m1_3": computed["atr_m1_3"],
        "atr_ratio_3_51": computed["atr_ratio_3_51"],
        ...
    }
```

---

## Displacement Detection (New: `displacement.py`)

Compute displacement metrics from closed candles. Lightweight, runs on every M1/M5 close.

```python
def candle_displacement(candle: dict, atr_slow: float) -> dict:
    """Measure a single candle's displacement relative to ATR baseline."""
    body = abs(candle["close"] - candle["open"])
    full_range = candle["high"] - candle["low"]
    body_pct = body / full_range if full_range > 0 else 0

    return {
        "body": round(body, 3),
        "range": round(full_range, 3),
        "body_pct": round(body_pct, 3),         # >0.7 = commitment
        "body_atr_ratio": round(body / atr_slow, 4) if atr_slow else None,
        "is_displacement": body_pct > 0.7 and (body / atr_slow > 0.8 if atr_slow else False),
        "direction": "up" if candle["close"] > candle["open"] else "down",
    }


def displacement_at_level(candle: dict, levels: dict, atr_slow: float) -> dict | None:
    """Check if a displacement candle interacted with a mapped level."""
    disp = candle_displacement(candle, atr_slow)
    if not disp["is_displacement"]:
        return None

    for level_id, price in levels.items():
        price = float(price)
        # Did the candle's range include this level?
        if candle["low"] <= price <= candle["high"]:
            # Did the body close through the level (acceptance) or reject?
            if disp["direction"] == "up":
                through = candle["close"] > price
            else:
                through = candle["close"] < price
            return {
                **disp,
                "level_id": level_id,
                "level_price": price,
                "through": through,  # True = acceptance, False = rejection
            }
    return None
```

---

## Swing Sequence Detection (Extension to `live_mapped_levels.py`)

Add swing pattern classification to the existing fractal swing detection:

```python
def classify_swing_sequence(swings: list[dict], lookback: int = 6) -> str:
    """Classify recent swing pattern as hh_hl / lh_ll / mixed."""
    recent = swings[-lookback:] if len(swings) >= lookback else swings
    if len(recent) < 4:
        return "insufficient"

    highs = [s for s in recent if s["type"] == "high"]
    lows = [s for s in recent if s["type"] == "low"]

    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"

    # Check last two highs and last two lows
    hh = highs[-1]["price"] > highs[-2]["price"]  # higher high
    hl = lows[-1]["price"] > lows[-2]["price"]     # higher low

    if hh and hl:
        return "hh_hl"   # uptrend
    elif not hh and not hl:
        return "lh_ll"   # downtrend
    else:
        return "mixed"   # range or transition
```

---

## Range Detection (New: `range_detector.py`)

```python
def detect_range(
    m5_swings: list[dict],
    current_price: float,
    atr_slow: float | None,
    min_bounces: int = 3,
) -> dict | None:
    """Detect if price is oscillating in a defined range."""
    if len(m5_swings) < 4 or atr_slow is None:
        return None

    recent_highs = [s["price"] for s in m5_swings[-8:] if s["type"] == "high"]
    recent_lows = [s["price"] for s in m5_swings[-8:] if s["type"] == "low"]

    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return None

    # Range boundaries: cluster of recent highs and lows
    resistance = sum(recent_highs) / len(recent_highs)
    support = sum(recent_lows) / len(recent_lows)
    width = resistance - support

    if width <= 0:
        return None

    width_atr = width / atr_slow
    bounces = len(recent_highs) + len(recent_lows)
    inside = support <= current_price <= resistance

    if bounces >= min_bounces and 2.0 < width_atr < 12.0 and inside:
        return {
            "resistance": round(resistance, 3),
            "support": round(support, 3),
            "width": round(width, 3),
            "width_atr_ratio": round(width_atr, 2),
            "bounces": bounces,
            "price_inside": inside,
        }
    return None
```

---

## Updated Management Flow

```
┌───────────────────────────────────────────────────────────────┐
│  REGIME DETECTION (every M1 close, before guard or Qwen)      │
│                                                               │
│  Inputs:                                                      │
│    - ATR snapshot from cached M1 bars (no MT5 call)           │
│    - Latest M5 candle displacement vs ATR_51                  │
│    - Displacement at level check (nearest mapped level)       │
│    - M5 swing sequence from live_mapped_levels                │
│    - Range detection from M5 swings                           │
│                                                               │
│  Output: regime_hint (range / trend / breakout / exhaustion)  │
│          + full regime_context packet for Qwen                │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│  DETERMINISTIC GUARD (runs BEFORE Qwen call)                  │
│                                                               │
│  Step 1: Invalidation check (regime-independent)              │
│    → M1+M5 closed beyond planned_invalidation → CLOSE         │
│                                                               │
│  Step 2: Regime-routed guard                                  │
│    if regime == "range" or "exhaustion":                       │
│      → scalp_guard: TP at favorable M5 level while M1        │
│        is still in favorable direction (take the money)       │
│    else:                                                      │
│      → rejection_guard: close only when M1+M5 confirm        │
│        rejection at a thesis-timeframe-matched level          │
│        (M15+ levels only for M15+ theses)                    │
│                                                               │
│  If guard fires → close, skip Qwen call                       │
│  If guard doesn't fire → proceed to Qwen                      │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│  QWEN MANAGEMENT CALL (with regime_context)                   │
│                                                               │
│  Qwen receives:                                               │
│    - All current management facts (unchanged)                 │
│    - regime_context packet (NEW)                              │
│    - regime_hint from Python (NEW)                            │
│                                                               │
│  Qwen outputs:                                                │
│    - Standard management decision (hold/protect/close)        │
│    - regime_assessment (NEW): Qwen's own regime read          │
│    - If regime_assessment differs from regime_hint,           │
│      Qwen explains why in summary                            │
│                                                               │
│  Qwen is trained to:                                          │
│    - Confirm or override the Python regime_hint               │
│    - In range: prefer close at favorable level                │
│    - In trend: prefer hold through M5 noise                   │
│    - At transitions: flag regime change in summary            │
└───────────────────────────────────────────────────────────────┘
```

---

## Entry Flow Changes

The regime also affects entry decisions:

```
RANGE regime:
  - target_mode: scalp ONLY
  - entry zone: M5 boundaries (top for sell, bottom for buy)
  - SL: opposite M5 boundary + small buffer
  - TP: nearest M5 level in favorable direction
  - Re-entry: allowed on return to opposite boundary
  - M1 failure at zone is sufficient trigger

TREND regime:
  - target_mode: starter_basket or directional_basket
  - entry zone: pullback to broken level (retest)
  - SL: behind last confirmed swing point
  - TP: next HTF level (M15/H1)
  - CHoCH/BOS confirmation preferred

BREAKOUT regime:
  - target_mode: starter_basket
  - entry zone: breakout retest (pullback to broken range boundary)
  - SL: inside the old range
  - TP: next HTF level
  - Must wait for retest hold, not chase the break

EXHAUSTION regime:
  - target_mode: scalp (counter-trend)
  - entry zone: HTF level where displacement failed
  - SL: beyond the exhaustion wick
  - TP: nearest M5 level in counter-trend direction
  - Requires M5 CHoCH before entry
```

---

## What This Changes in the Improvement Plan

The original 10-piece plan needs restructuring. Regime detection is not Piece 11 — it's the FOUNDATION that Pieces 1-2 depend on.

### New Sequencing:

```
FOUNDATION (Week 1, Aug 17-20):
  Piece 0A: ATR wiring fix (compute from cache, not MT5 call)
  Piece 0B: Displacement detection (new file, ~80 lines)
  Piece 0C: Swing sequence classification (extend live_mapped_levels)
  Piece 0D: Range detection (new file, ~60 lines)
  Piece 0E: Regime hint computation (combine 0A-0D, ~40 lines)
  Piece 0F: regime_context packet assembly (wire into management facts)
  → All deterministic, no model changes, testable in isolation

GUARD UPGRADE (Week 1, Aug 20-22):
  Piece 1: Split guard into scalp_guard + rejection_guard
  Piece 2: Thesis-timeframe matching in rejection_guard (TREND only)
  Piece 3: scalp_guard TP logic (close at favorable level, not after bounce)
  → Guard now routes based on regime_hint

CONTEXT + DASHBOARD (Week 2, Aug 24-27):
  Piece 4: regime_context injected into Qwen management prompt
  Piece 5: Qwen-qualified levels on dashboard (with regime indicator)
  Piece 6: Stale mapped_trade_levels.json cleanup

ENTRY REFINEMENT (Week 2, Aug 27-29):
  Piece 7: M1 rejection gate on entry (existing code, new wiring)
  Piece 8: Entry target_mode informed by regime (scalp in range, basket in trend)

CURRICULUM (Week 3, Aug 31 - Sep 5):
  Piece 9: Teach Qwen regime vocabulary + management per regime
  Piece 10: CHoCH/BOS/FVG detection + curriculum
  Piece 11: Confidence calibration (regime-aware)
  Piece 12: H4 curriculum (structural brackets)

FREEZE + TEST (Week 3, Sep 5):
  Re-freeze build, clear drift, full paper test with regime detection
```

### Why this order:

1. **Foundation first:** Without working ATR + displacement + swings, the guard can't route correctly. These are all pure Python computation — no model changes, no risk.

2. **Guard upgrade second:** Once regime detection works, split the guard and test. Paper trade for 2 sessions to verify scalp_guard takes profit in ranges and rejection_guard holds in trends.

3. **Model changes last:** Qwen doesn't need regime_context until the guard is proven. Then curriculum teaches Qwen to read regime and make better hold/close decisions in ambiguous situations the guard doesn't catch.

---

## Dry Run: Would This Design Have Fixed Today?

### Trades 1-5 (Range period, 4392-4398):

**ATR (if working):** ~1.2 (M1 ATR_51), ratio ~0.8 (normal, not expanding)
**Displacement:** No M5 candle had body/ATR > 0.8 during this period
**Swings:** M5 swings mixed — HH at 4398, LL at 4393, then HH at 4397, HL at 4393
**Range:** Width 5 points, width/ATR ~4.2, 4+ bounces → **RANGE detected**

**Guard route:** scalp_guard
**Result:** Close WHILE M1 is favorable at M5_PREVIOUS_LOW → TP at ~4393-4394
**Expected P&L:** ~$50-90 per trade, ~$300 total

vs actual: -$21 (guard closed on bounce-back at worse prices)

### Trade 6 (06:24, transition period):

**ATR:** Ratio starting to climb (0.8 → 1.0)
**Displacement:** M5 candle at 06:25 has body 2.1 pts, body/ATR = 1.75 → DISPLACEMENT
**At level:** Through M5_PREVIOUS_HIGH 4398 with body close at 4400.1 → THROUGH
**Swings:** New HH at 4400 breaks the range top

**Regime transition:** range → breakout
**Guard route:** rejection_guard (don't scalp the breakout)
**Entry decision:** This is a SELL against a breakout → should NOT have entered

### Trades 8-9 (Trend up to 4404):

**ATR:** Ratio > 1.3 (expanding)
**Displacement:** M5 body 3.5 pts through 4400 → strong displacement
**Swings:** HH-HL established (4404 high, 4397 hold)
**Regime:** TREND UP

**Entry decision:** No sells in an uptrend. Qwen should wait for pullback buy.
**Result:** Avoided -$126 and -$276

### Total design improvement for today:
```
Actual:   -$21 (guard saved from -$1,117, but missed $467 scalp profit)
Proposed: ~+$300 scalp + $0 avoided losses = ~+$300
Delta:    +$321 improvement
```

---

## Key Design Principles

1. **Python detects, Qwen judges.** Regime detection is deterministic computation. Qwen reads the computed signal and can override when context demands it.

2. **Guard routes on regime, Qwen refines.** The guard is fast (no model call) and handles the common case. Qwen handles ambiguity and transitions.

3. **No new hard-coded thresholds that can't be tuned.** The ATR ratio boundaries (0.6, 1.0, 1.5) and displacement threshold (0.8) are starting points. Curriculum teaches Qwen the ranges, and the Python thresholds can be tuned from paper trade results.

4. **Regime is continuous, not binary.** The system tracks regime_hint but also supplies all raw values. Qwen can see "ratio 0.95, almost trend but still ranging" and make a judgment call.

5. **Transitions are first-class.** Breakout and exhaustion are not just labels — they have their own management contracts. The system explicitly handles range→trend and trend→range, which is where most money is made or lost.

6. **One piece at a time.** Foundation pieces (0A-0F) are pure computation with no behavior change. Guard changes (1-3) are the first behavior change. Model changes come last.
