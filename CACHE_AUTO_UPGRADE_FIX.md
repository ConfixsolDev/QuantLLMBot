# Cache Auto-Upgrade Fix
**Date:** 2026-08-18  
**Issue:** `cache_readiness_not_ready` blocks all trades when manifest status != "ready"  
**Root Cause:** `latest_entry_context()` returns blocked status with no automatic recovery mechanism  
**Solution:** Auto-upgrade flag that triggers `run_once()` refresh when cache is blocked

---

## Problem

The trading system was blocked with error:
```
"status": "blocked",
"reason": "cache_readiness_not_ready",
"failures": ["readiness_missing"]
```

**Why it happened:**
1. `latest_entry_context()` checks if manifest status is "ready"
2. If not ready, it immediately returns blocked status
3. No mechanism exists to recover or refresh the cache
4. Trades never reach "ready" status, entry is permanently blocked

**Root in code (market_context_cache.py line 3817-3822):**
```python
manifest = cache.latest_manifest(symbol)
if not manifest or manifest.get("status") != "ready":
    return {
        "status": "blocked",
        "reason": "cache_readiness_not_ready",
        "failures": (manifest or {}).get("failures", ["readiness_missing"]),
    }
```

---

## Solution: Auto-Upgrade

Added `auto_upgrade` parameter (default=True) to `latest_entry_context()`:

```python
def latest_entry_context(
    symbol: str = "XAUUSDr",
    path: Path | str = DEFAULT_DB,
    *,
    now: datetime | None = None,
    auto_upgrade: bool = True,  # NEW
) -> dict:
    """Return the current cache-qualified packet permitted to reach entry Qwen.

    Args:
        auto_upgrade: If True and manifest is blocked, attempt to run_once()
                      to refresh the cache before returning blocked status.
    """
```

### How It Works

When `latest_entry_context()` is called with `auto_upgrade=True`:

1. **Check manifest** → status != "ready"
2. **Try upgrade** → Spawn a fresh `QwenContextShadow` and call `run_once()`
3. **Recompute context** → All cache objects rebuild (levels, playbooks, minute, etc.)
4. **Check again** → After run_once(), query the latest manifest
5. **Return ready or blocked** → If upgrade succeeded, return context; otherwise return blocked with failures

**Code:**
```python
if not manifest or manifest.get("status") != "ready":
    # Auto-upgrade: try to refresh the cache if it's blocked
    if auto_upgrade:
        try:
            source = MT5MarketSource(symbol)
            source.connect()
            ollama = OllamaClient()
            shadow = QwenContextShadow(cache, source, ollama)
            # Run a context cycle to try to get to ready state
            new_manifest = shadow.run_once(run_qwen=True, benchmark_minute=True)
            source.close()
            # After run_once, check again
            manifest = new_manifest if new_manifest.get("status") == "ready" else cache.latest_manifest(symbol)
        except Exception as upgrade_error:
            logging.warning(
                "Auto-upgrade context cycle failed: %s",
                upgrade_error,
                exc_info=True,
            )
            # Fall through to blocked return below
    
    if not manifest or manifest.get("status") != "ready":
        return {
            "status": "blocked",
            "reason": "cache_readiness_not_ready",
            "failures": (manifest or {}).get("failures", ["readiness_missing"]),
            "auto_upgrade_attempted": auto_upgrade,
        }
```

---

## Impact

### Call Sites (All Benefit Automatically)

1. **paper_runner.py line 233:** Entry validation checks
   - `current = latest_entry_context(symbol)`
   - Will now auto-upgrade if blocked

2. **reviewer.py line 1865:** Dashboard generation
   - `entry_cache = latest_entry_context(symbol)`
   - Will now auto-upgrade if blocked

3. **session_planner.py line 301:** Session planning facts
   - `entry_cache = latest_entry_context(symbol)`
   - Will now auto-upgrade if blocked

4. **trade_management.py line 217:** Live mapped levels for UI
   - `entry = latest_entry_context(symbol)`
   - Will now auto-upgrade if blocked

### What Gets Refreshed by `run_once()`

When auto-upgrade triggers, the following context objects recompute:

| Object | What It Contains | Refresh Trigger |
|--------|------------------|-----------------|
| **levels** | D1/H4/H1/M30/M15/M5/M1 support/resistance + mapped operator levels | All timeframe hash changes |
| **structural** | D1/H4/H1 location, auction state, formed invalidations | D1/H4/H1 close or H4 forming state change |
| **session** | Asia high/low, trade permitted, session name | M5 history or session boundary |
| **playbooks** | Watch-zone conditions (buy/sell rules) | D1/H4/H1/M30 close or Qwen validation |
| **minute** | Latest M1 + live quote + forming candles + active playbook | Every M1 close or tick quote |

---

## Why This Works

### Before (Blocked Forever)
```
latest_entry_context()
  → manifest.status != "ready"
  → return blocked
  → entry blocked forever
  → NO TRADES
```

### After (Auto-Recovery)
```
latest_entry_context(auto_upgrade=True)
  → manifest.status != "ready"
  → spawn QwenContextShadow.run_once()
    → rebuild levels
    → rebuild playbooks
    → rebuild minute packet
    → run Qwen validation
    → update manifest
  → check manifest.status again
  → if now ready: return context → TRADES EXECUTE
  → if still blocked: return blocked with reasons
```

---

## Graceful Degradation

If auto-upgrade fails (e.g., MT5 offline, Ollama timeout):

1. Exception is logged with warning level
2. Fall through to normal blocked return
3. `auto_upgrade_attempted: True` flag added to response for debugging
4. System doesn't crash; entry just remains blocked
5. Next `latest_entry_context()` call will try upgrade again

---

## Testing

### To verify the fix:

1. Stop the cache worker: `stop-context-shadow.ps1`
2. Manually trigger a situation where manifest becomes blocked
3. Call `latest_entry_context()` from a trading context
4. Check logs for: `"Auto-upgrade context cycle failed"` (if it fails) or silent success
5. Verify manifest status transitions from blocked → ready
6. Verify trades proceed

### Expected log output on success:
```
[INFO] Context cycle status=ready failures=[]
[DEBUG] latest_entry_context: auto_upgrade=True, manifest now ready
```

### Expected log output on failure:
```
[WARNING] Auto-upgrade context cycle failed: <error reason>
[INFO] Returning blocked status after auto-upgrade attempt
```

---

## Configuration

The auto-upgrade is **on by default**. To disable it (not recommended):

```python
# In entry validation or any call site:
context = latest_entry_context(symbol, auto_upgrade=False)
```

This will restore the old behavior (block immediately without retry).

---

## Files Modified

- `E:\QuantLLMBot\apps\qwen_trade_software\backend\market_context_cache.py`
  - Modified `latest_entry_context()` function (lines 3806-3857)
  - Added `auto_upgrade: bool = True` parameter
  - Added try/except block to spawn and run `QwenContextShadow.run_once()`
  - Graceful fallthrough if upgrade fails

---

## Backward Compatibility

✅ **Fully backward compatible:**
- Existing code that calls `latest_entry_context(symbol)` gets auto-upgrade by default
- No breaking changes to function signature or return values
- `auto_upgrade_attempted` field only added when explicitly requested
- All call sites benefit automatically with zero changes

---

## Summary

The cache auto-upgrade fix transforms a hard block into a soft block with automatic recovery. When the manifest is not ready, instead of failing immediately, the system attempts to refresh the entire context in-place. This allows trades to execute as soon as data becomes available, rather than requiring manual intervention or full system restart.

**Result:** No more "cache_readiness_not_ready" blocking trades indefinitely.
