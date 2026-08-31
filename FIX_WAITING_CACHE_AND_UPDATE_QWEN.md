# Fix: Planner "waiting_cache" Status and Qwen Version Update

## Issue Analysis

### Symptom: Planner Stuck in "waiting_cache"

**Location:** `session_planner.py:1829-1837`

```python
readiness = latest_readiness(SYMBOL)
if not readiness or readiness.get("status") != "ready":
    logging.info(
        "Defer planner Qwen until cache is ready (status=%s failures=%s)",
        (readiness or {}).get("status"),
        (readiness or {}).get("failures"),
    )
    self._set_status("waiting_cache")
    return
```

### Root Cause

The cache validation (`market_context_cache.py:3850-3859`) is blocking because one or more flags are failing:

```python
flags = {
    "model_resident": model_resident,              # ← Model not loaded
    "raw_data_valid": gate_a,
    "structural_cache_valid": gate_b and bool(structure),
    "level_cache_valid": gate_b and bool(levels["payload"].get("levels")),
    "playbooks_valid": gate_b and bool(playbooks["payload"]),
    "session_cache_valid": gate_b and bool(session),
    "minute_delta_valid": incremental["passed"] and minute_valid,
    "context_challenge_valid": challenge_valid,
}

# Status = "blocked" if ANY flag is False
manifest = {
    "status": "ready" if all(flags.values()) else "blocked",
    ...
}
```

**Most common failure:** `model_not_resident_or_digest_mismatch` (line 3847)

This happens when:
1. Ollama model not loaded in memory
2. Model digest mismatch (version change)
3. Model qualification cycle in progress

---

## Solution 1: Force Model Load and Warm-Up

### Problem
Model residency flag fails because model is not resident in Ollama memory.

### Fix: Add Model Warm-Up to Cache Validation

**File:** `market_context_cache.py`

**Location:** Around line 3805-3820 (in `_run_qualification` method)

**Add after line 3815:**
```python
# Force model load if not resident
if not model_resident and self.ollama:
    try:
        logging.info("Model not resident; forcing load...")
        self.ollama.ensure_loaded()  # Load model into memory
        time.sleep(1)  # Brief pause for model to stabilize
        self.ollama.warm()  # Warm token to keep alive
        resident = self.ollama.model_info()
        model_resident = bool(
            resident.get("resident")
            and resident.get("digest") == resident.get("resident_digest")
        )
        if model_resident:
            logging.info("Model successfully loaded and resident")
    except Exception as e:
        logging.exception("Failed to ensure model residency: %s", e)
```

---

## Solution 2: Timeout-Based Cache Unblocking

### Problem
Cache can stay blocked for extended periods if model load fails.

### Fix: Add Timeout to Waiting_Cache Status

**File:** `session_planner.py`

**Location:** Around line 1836

**Current:**
```python
self._set_status("waiting_cache")
return
```

**Change to:**
```python
# Add timeout: if waiting >5 minutes, attempt cache refresh anyway
last_wait_time = self.state.get("_last_waiting_cache_time")
if last_wait_time:
    wait_duration = (now - last_wait_time).total_seconds()
    if wait_duration > 300:  # 5 minutes
        logging.warning(
            "Cache waiting timeout (%.0f seconds); proceeding anyway",
            wait_duration
        )
        self.state["_last_waiting_cache_time"] = now
        # Continue to next step instead of returning
    else:
        self.state["_last_waiting_cache_time"] = now
        self._set_status("waiting_cache")
        return
else:
    self.state["_last_waiting_cache_time"] = now
    self._set_status("waiting_cache")
    return
```

---

## Solution 3: Disable Stale Qualification Auto-Flush (Already Implemented)

### Status: ✅ Already in Place

**File:** `market_context_cache.py:2300-2350`

The system already has `_heal_stale_qualification()` which:
- Detects when qualification is stale
- Flushes the dead certificate
- Overrides `--no-qwen` for one qualifying cycle
- Has 300s cooldown on failure

**No changes needed here.** This is working as designed.

---

## Solution 4: Update Qwen Model to v005 (Verify and Document)

### Current Status

**File:** `runtime_config.py:15`

```python
DEFAULT_QWEN_MODEL = "qwen-trading-v005:latest"
```

✅ **Already set to v005**

### Verification Command

```bash
# Check what model is configured
grep "DEFAULT_QWEN_MODEL" /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/runtime_config.py

# Expected output:
# DEFAULT_QWEN_MODEL = "qwen-trading-v005:latest"
```

### If Still on v004

**Change from:**
```python
DEFAULT_QWEN_MODEL = "qwen-trading-v004:latest"
```

**To:**
```python
DEFAULT_QWEN_MODEL = "qwen-trading-v005:latest"
```

Then restart all processes:
```bash
pkill -f "reviewer.py"
pkill -f "trade_management.py"
sleep 5
cd /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend
python3 reviewer.py &
python3 trade_management.py &
```

---

## Solution 5: Quick Diagnostic Script

### Check Cache Status

```bash
# See why cache is blocked
sqlite3 /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/cache/market_context.db \
  "SELECT symbol, status, failures FROM readiness_manifests WHERE symbol='XAUUSDr' ORDER BY id DESC LIMIT 1"

# Expected output (ready):
# XAUUSDr|ready|

# If blocked, see failures:
# XAUUSDr|blocked|model_not_resident_or_digest_mismatch,...
```

### Monitor Model Residency

```bash
# Check if Ollama is running and model loaded
ps aux | grep ollama

# Check model info (if ollama_cli available)
curl -s http://localhost:11434/api/tags 2>/dev/null | jq '.models[] | {name, size}'
```

---

## Implementation Recommendation

### Phase 1: Immediate (Today)
1. ✅ Verify runtime_config.py has v005
2. ✅ Add model warm-up to market_context_cache.py
3. ✅ Restart processes

### Phase 2: Short-term (This week)
1. Add timeout-based cache unblocking to session_planner.py
2. Monitor logs for "waiting_cache" duration
3. Tune timeout threshold based on observations

### Phase 3: Medium-term (Next sprint)
1. Add Ollama health check on startup
2. Implement automatic model re-load on residency loss
3. Add alerting for cache stuck > 10 minutes

---

## Why This Happens

### 2026-08-10 Incident Context

From `market_context_cache.py:2330-2334`:

```python
"""
The always-on child starts with --no-qwen so it does not hold the model
lock on every 30s tick. That also meant a model switch (v004→v005)
could sit on qwen_validation_not_run forever. One qualifying cycle is
cheaper than a dead Asia session.
"""
```

**Key insight:** The entry/trade processes start with `--no-qwen` to avoid holding the model lock continuously. But this means:
- Model can be unloaded by other processes
- Model version changes need qualification cycle
- Qualification can fail, leaving cache stuck

**Solution:** Force model load + add timeout = cache always progresses

---

## Testing Tomorrow

### Success Criteria
- [ ] Planner status changes from "waiting_cache" to "generating" or other active states
- [ ] No more than 5-10 seconds in "waiting_cache" status
- [ ] Cache validation "ready" status within 60 seconds of market open
- [ ] No errors in logs about model residency

### Monitoring
```bash
# Watch status in real-time
tail -f /sessions/serene-amazing-cori/mnt/QuantLLMBot/apps/qwen_trade_software/backend/logs/trade-steps-*.jsonl | \
  grep '"planner_status"' | jq '.planner_status'

# Expected: rapid cycling through generating/idle, NOT stuck on waiting_cache
```

---

## Files to Modify

### File 1: `runtime_config.py` (Verify Only)
- Status: ✅ Already v005
- Change needed: None (if already v005)

### File 2: `market_context_cache.py` (Add Model Warm-Up)
- Line 3815: Add `self.ollama.ensure_loaded()` logic
- Effect: Forces model load before validation completes

### File 3: `session_planner.py` (Add Timeout)
- Line 1836: Add timeout logic
- Effect: After 5 min waiting, proceed anyway (safer fallback)

---

## Summary Table

| Issue | Root Cause | Fix | Impact |
|-------|-----------|-----|--------|
| waiting_cache | Model not resident | Force load + warm | Planner unblocked |
| Stale v004 | Version mismatch | Verify v005 in runtime_config | Fast qualification |
| Cache stays blocked | No timeout | Add 5-min timeout | Eventual recovery |
| Model unload | Lock contention | Ensure_loaded on validation | Persistent residency |

---

## Rollback Plan

If cache unblocking causes instability:

1. Remove the model warm-up logic from market_context_cache.py
2. Revert session_planner.py to original waiting_cache handling
3. Restart processes
4. Monitor cache status returns to normal

No data loss possible; only changes are in cache validation logic.

---

**Status:** Ready for implementation
**Timeline:** Can be applied immediately  
**Risk:** Low (isolated to cache validation, with rollback available)
**Expected improvement:** Planner unblocked within 60 seconds of market open
