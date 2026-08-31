# Changes Applied: 2026-08-25

## Summary of Changes

Three strategic changes made to increase daily trade volume to 50+:

### Change 1: Lower Confidence Threshold
- **File:** `entry_policy.py:50`
- **Changed:** `MIN_ENTRY_CONFIDENCE = 51` → `45`
- **Effect:** ~30-50% more proposals will pass confidence gate
- **Risk:** Lower individual trade quality, but acceptable per design

### Change 2: Increase Daily Cap
- **Files:** `reviewer.py:107` and `paper_runner.py:29`
- **Changed:** `DAILY_PAPER_CAP = 50` → `75`
- **Effect:** System can execute up to 75 trades/day (was hard-capped at 50)
- **Risk:** Exposure increases proportionally; monitor position sizing

### Change 3: Reduce Symmetry Surcharge
- **File:** `entry_policy.py:126`
- **Changed:** `SYMMETRY_CONFIDENCE_SURCHARGE = 10` → `5`
- **Effect:** On one-directional days, fewer proposals throttled; easier to maintain volume
- **Risk:** Allows slightly more directional drift, but still guarded at MAX_SHARE=0.75

---

## Expected Results for Tomorrow (2026-08-26)

### Conservative Estimate
- **Minimum increase:** +30-40% trade volume
- **Target range:** 50-75 trades/day (from previous <50)
- **P&L impact:** -5 to -15% per trade quality (lower threshold = noisier trades)

### Optimistic Estimate (if current Qwen output quality is high)
- **Upper range:** 60-90 trades/day
- **Quality remains acceptable:** If average proposal confidence was 48-52, you now catch them

### Tracking Metrics
1. **Trade count today:** Record and compare to previous days
2. **Confidence distribution:** Check if lower-confidence proposals are executing
3. **P&L per trade:** Monitor for degradation; if >20% worse, revert changes
4. **Symmetry**: Track buy/sell split; should be more balanced if one-sided day

---

## How to Monitor Tomorrow

### Quick Status Check (Every Hour)

```bash
# Count ready proposals today
grep -c '"status":"ready"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl

# Count by confidence ranges
grep '"confidence":' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  awk '{
    if ($1 < 45) below45++
    else if ($1 < 50) range45_50++
    else if ($1 < 55) range50_55++
    else if ($1 < 60) range55_60++
    else above60++
  } 
  END {
    print "Below 45:", below45
    print "45-49:", range45_50
    print "50-54:", range50_55
    print "55-59:", range55_60
    print "60+:", above60
  }'

# Current cap status
grep '"broker_positions_today"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | tail -1
```

### Detailed Analysis (Mid-Day)

```bash
# Reason codes distribution
grep '"reason_code":"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | \
  sed 's/.*"reason_code":"\([^"]*\)".*/\1/' | \
  sort | uniq -c | sort -rn | head -15

# Average confidence of ready proposals
grep '"status":"ready"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | \
  grep '"confidence":' | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  awk '{sum+=$1; count++} END {print "Average ready confidence:", sum/count; print "Count:", count}'

# Symmetry check (buy vs sell)
grep '"side":"buy"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | wc -l
grep '"side":"sell"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | wc -l
```

### Post-Market Retrospective (End of Day)

```bash
# Total ready proposals executed
grep '"status":"ready"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | wc -l

# Total wait decisions (rejected)
grep '"status":"wait"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | wc -l

# Full reason code breakdown
grep '"reason_code":"' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | \
  sed 's/.*"reason_code":"\([^"]*\)".*/\1/' | \
  sort | uniq -c | sort -rn

# Confidence statistics
grep '"confidence":' /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/reviews-2026-08-26.jsonl | \
  sed 's/.*"confidence":\([0-9]*\).*/\1/' | \
  awk 'BEGIN {min=999; max=0} 
       {sum+=$1; count++; if ($1<min) min=$1; if ($1>max) max=$1} 
       END {
         print "Count:", count
         print "Min:", min
         print "Max:", max
         print "Avg:", sum/count
       }'
```

---

## What to Expect in Logs

### Before (2026-08-24 and earlier)
```
reason_code distribution should show:
- obs:below_min_confidence: HIGH (because threshold was 51)
- Other codes: Lower frequency
```

### After (2026-08-26 onwards)
```
reason_code distribution should show:
- obs:below_min_confidence: MUCH LOWER (threshold now 45)
- side:symmetry_throttled: Slightly lower (surcharge reduced 10→5)
- side:invalidation_incoherent, side:blocking_trap: Unchanged (policy not affected)
- status:"ready": MORE FREQUENT (more proposals passing gates)
```

---

## Decision Tree: What to Do If Results Aren't Meeting Targets

### Scenario 1: Trade Count < 50/day Tomorrow
**Diagnosis:** Threshold reduction isn't enough

**Actions (pick one):**
1. Lower MIN_ENTRY_CONFIDENCE further: 45 → 40 (risky)
2. Widen invalidation gap: MAX_INVALIDATION_GAP = 4 → 5 (historical data shows this hurts)
3. Remove a blocking trap: Add `"fade_acceptance"` to advisory instead (risky)
4. Check if Qwen is running: Maybe it's hung or crashed

### Scenario 2: Trade Count 50-75/day, P&L Good
**Decision:** SUCCESS — Keep changes as-is

### Scenario 3: Trade Count 50-75/day, P&L Bad (losing money)
**Diagnosis:** Lower confidence threshold caught too many bad trades

**Actions (pick one, in order):**
1. Revert surcharge: 5 → 10 (less one-sided day volume, but higher quality)
2. Revert confidence: 45 → 48 (middle ground)
3. Revert both: Go back to 51 and investigate Qwen output quality

### Scenario 4: Trade Count > 75/day but hitting new cap
**Decision:** System is working; consider raising DAILY_PAPER_CAP to 100 or 125

### Scenario 5: Lots of new "reason_code" errors
**Diagnosis:** Policy invariant violated somewhere

**Action:** Check process logs for Python exceptions:
```bash
tail -50 /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/trade-management.log*
```

---

## Files Modified (for audit trail)

1. ✅ `entry_policy.py`
   - Line 50: MIN_ENTRY_CONFIDENCE 51 → 45
   - Line 126: SYMMETRY_CONFIDENCE_SURCHARGE 10 → 5

2. ✅ `reviewer.py`
   - Line 107: DAILY_PAPER_CAP 50 → 75
   - Line 108: MIN_ENTRY_CONFIDENCE 51 → 45

3. ✅ `paper_runner.py`
   - Line 29: DAILY_PAPER_CAP 50 → 75
   - Line 30: MIN_ENTRY_CONFIDENCE 51 → 45

---

## Revert Instructions (If Needed)

If tomorrow's results are unacceptable (losing >20% per trade, system instability), revert by changing:

```python
# entry_policy.py
MIN_ENTRY_CONFIDENCE = 51  # (from 45)
SYMMETRY_CONFIDENCE_SURCHARGE = 10  # (from 5)

# reviewer.py
DAILY_PAPER_CAP = 50  # (from 75)
MIN_ENTRY_CONFIDENCE = 51  # (from 45)

# paper_runner.py
DAILY_PAPER_CAP = 50  # (from 75)
MIN_ENTRY_CONFIDENCE = 51  # (from 45)
```

Then restart processes:
```bash
pkill -f "reviewer.py"
pkill -f "trade_management.py"
sleep 5
cd /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend
python3 reviewer.py &
python3 trade_management.py &
```

---

## Success Criteria for Tomorrow (2026-08-26)

### Minimum Success
- [ ] Trade count ≥ 50 (was <50 before)
- [ ] No Python exceptions in logs
- [ ] Reason code distribution shows lower "below_min_confidence" count

### Target Success
- [ ] Trade count 60-75
- [ ] P&L within -10% to -20% of historical average per trade
- [ ] Daily cap not hit (trades stopped at 75, not 75+)

### Optimal Success
- [ ] Trade count 70-80
- [ ] P&L within -5% to -10% of historical average per trade
- [ ] Symmetry balanced (buy/sell close to 50/50)
- [ ] No spikes in loss per trade

---

## Next Steps After Tomorrow

### If Success
Document the changes and consider:
1. Running replay against 2026-08-10 incident data to validate no regressions
2. Monitoring P&L trend over next 5 days
3. Gradually tightening confidence threshold back toward 48 if quality permits

### If Partial Success (volume good, quality degraded)
1. Find middle ground: MIN_ENTRY_CONFIDENCE = 47-48
2. Keep DAILY_PAPER_CAP = 75 and SYMMETRY_SURCHARGE = 5
3. Test for 2-3 more days

### If No Success
1. Check Qwen process status and logs
2. Investigate if model output quality has dropped
3. Review recent market conditions
4. Consider prompt/model tuning rather than policy changes

---

## Contact Points

**Questions about changes?** Review the TRADING_ARCHITECTURE_ANALYSIS.md for the full rationale.

**Need to adjust further?** Use IMMEDIATE_ACTIONS_TO_INCREASE_TRADES.md as reference for each parameter.

**Debugging logs?** Command templates above are copy-paste ready.

---

**Change applied:** 2026-08-25 at UTC
**Expected observation period:** 2026-08-26 (1 full trading day)
**Status:** Ready for testing
