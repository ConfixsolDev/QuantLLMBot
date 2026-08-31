# Immediate Actions to Increase Trade Volume to 50+ Trades/Day

## 🎯 Quick Diagnosis (5 minutes)

Run this command to see why proposals are failing:

```bash
cd /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs

# Count rejection reasons from last 7 days
for f in reviews-2026-08-{18..25}.jsonl; do
  [ -f "$f" ] && grep -o '"reason_code":"[^"]*"' "$f"
done | sed 's/.*"\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn | head -20
```

**Read the top 5 reason codes. One of them is your bottleneck.**

---

## 🔧 The 3-Minute Fix

If top reason code is **`obs:below_min_confidence`**, do this:

### File 1: `entry_policy.py`

**Location:** `E:\QuantLLMBot\apps\qwen_trade_software\backend\entry_policy.py:50`

**Current:**
```python
MIN_ENTRY_CONFIDENCE = 51
```

**Change to:**
```python
MIN_ENTRY_CONFIDENCE = 45
```

**Save and restart the entry process.**

**Expected result:** ~30-50% more trades within next cycle

---

## ⚡ If That Doesn't Work: Try These (In Order)

### Issue: Daily cap being hit
**Symptom:** "MT5 broker filled-position cap reached" in logs

**File:** `reviewer.py:107` and `paper_runner.py:29`

**Current:**
```python
DAILY_PAPER_CAP = 50
```

**Change to:**
```python
DAILY_PAPER_CAP = 100  # Or 75 if you want to be conservative
```

---

### Issue: Symmetry throttling blocking trades
**Symptom:** High count of `side:symmetry_throttled` in reason codes

**File:** `entry_policy.py:125`

**Current:**
```python
SYMMETRY_CONFIDENCE_SURCHARGE = 10
```

**Change to:**
```python
SYMMETRY_CONFIDENCE_SURCHARGE = 5  # Make it easier to pass on one-sided days
```

---

### Issue: Invalidation gap rejecting trades
**Symptom:** High count of `side:invalidation_incoherent` in reason codes

**File:** `entry_policy.py:117`

**Current:**
```python
MAX_INVALIDATION_GAP = 4
```

**Change to:**
```python
MAX_INVALIDATION_GAP = 5  # Allow M1 entries with wider stops
```

⚠️ **WARNING:** 2026-08-10 data shows gap 5-6 has worse P&L. Use only if other options fail.

---

## 📊 Monitoring Changes

After you make a change, check these every 30 minutes:

```bash
# Live trade count today
tail -100 /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-*.jsonl | \
  grep '"status":"ready"' | wc -l

# Current confidence distribution
tail -500 /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-*.jsonl | \
  grep '"confidence":' | sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  sort -n | tail -20
```

---

## ❌ Do NOT Do This

- ❌ Modify component weights in `SCORE_WEIGHTS` — requires retrain
- ❌ Remove all blocking traps — you'll get garbage trades
- ❌ Lower MIN_ENTRY_CONFIDENCE below 40 — statistical cliff
- ❌ Set DAILY_PAPER_CAP to 1000 — broker position limits
- ❌ Change multiple settings at once — can't tell what worked

---

## ✅ Safest Change (Recommended)

**Step 1:** Lower confidence threshold
```python
MIN_ENTRY_CONFIDENCE = 45  # From 51
```

**Step 2:** Monitor for 2-3 hours
- If trades ≥50/day AND P&L positive → DONE
- If trades <50/day → proceed to Step 3
- If P&L negative → revert to 51

**Step 3:** Reduce symmetry surcharge
```python
SYMMETRY_CONFIDENCE_SURCHARGE = 5  # From 10
```

**Step 4:** Monitor 2-3 more hours
- If now ≥50/day → DONE
- If still below 50 → increase daily cap (Step 5)

**Step 5:** Increase daily cap (if needed)
```python
DAILY_PAPER_CAP = 75
```

**This sequence ensures you know what worked.**

---

## 🚨 If No Reason Code Stands Out

If all reason codes are roughly equal and low-frequency, the issue is:

**The market condition or Qwen output quality is below threshold.**

Check:
```bash
# Are we even getting Qwen responses?
grep -c '"confidence":' logs/reviews-2026-08-25.jsonl

# What's the average confidence?
grep '"confidence":' logs/reviews-2026-08-25.jsonl | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count}'

# Are there any "ready" proposals?
grep -c '"status":"ready"' logs/reviews-2026-08-25.jsonl
```

If average confidence < 45 and no ready proposals → Qwen is not confident today.
**You cannot trade what the model won't propose.**

---

## 🔍 Deep Dive: Check Entry Policy Rejects

For each reason code, here's what's actually happening:

```python
obs:malformed           # Qwen returned invalid JSON
obs:missing_side        # Qwen forgot buy OR sell side
obs:bad_scores          # Scores out of 0-10 range
obs:unknown_trap        # Qwen reported unknown trap type
obs:epoch_mismatch      # Timing mismatch between components
obs:no_evidence         # No completed candles to analyze
obs:below_min_confidence# Confidence < 51 (lowest-frequency SHOULD be this)
side:no_zone            # Side has no entry zone defined
side:no_invalidation    # Side has no stop level
side:no_closed_response # Side missing closed candle confirmation
side:blocking_trap      # Side hit fade_acceptance, buy_into_resistance, etc.
side:timeframe_incoherent# Trigger TF too far from zone TF
side:invalidation_incoherent# Stop TF too far from zone TF (gap > 4)
side:timeframe_incoherent# Trigger more than 1 step below zone
side:symmetry_throttled # One side >75% of last 50, needs higher confidence
```

**If you see contract violations (obs:*), there's a Qwen output problem.**
**If you see side:* codes, there's a structural problem.**
**If you see below_min_confidence, adjust threshold.**

---

## 🎬 Before & After Checklist

### Before Change
- [ ] Note current time and restart count
- [ ] Run diagnostic bash command above
- [ ] Write down top 3 reason codes and their counts
- [ ] Record average confidence of proposals
- [ ] Note trade count so far today

### Make ONE Change
- [ ] Edit exactly one value
- [ ] Save file
- [ ] Restart affected process (reviewer.py)
- [ ] Wait 2-3 minutes for new proposals

### After Change
- [ ] Run diagnostic command again
- [ ] Did reason code distribution change?
- [ ] Did trade count increase?
- [ ] Check last 10 proposals: are they lower quality?

### Revert if Needed
- [ ] Edit back to original value
- [ ] Save
- [ ] Restart
- [ ] Confirm rollback worked

---

## Process Restart Commands

After editing config files:

```bash
# Kill entry process
pkill -f "python.*reviewer.py"

# Kill trade management process  
pkill -f "python.*trade_management.py"

# Wait 5 seconds
sleep 5

# Restart (from app directory)
cd /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend
python3 reviewer.py &
python3 trade_management.py &
```

Monitor logs to confirm restart:
```bash
tail -f logs/reviewer.log logs/trade-management.log
```

---

## The 30-Second Summary

Your system has **7 filtering gates**. You're not trading 50+/day because one or more gates are too strict.

**Most likely culprit:** `MIN_ENTRY_CONFIDENCE = 51` is too high for current market conditions.

**Fastest fix:** Change to `45` and watch trade volume increase.

**Safest approach:** Lower one setting at a time, monitor, revert if P&L suffers.

**Do not:** Change multiple settings, or remove safety gates entirely.

That's it. The architecture is already designed for high-volume trading. You just need to tell it to be less conservative.
