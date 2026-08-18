# Complete Trading Flow: Cache → Zone → Entry → Trade

**Date:** 2026-08-18  
**System:** Qwen Trading (Paper Demo on MT5)  
**Architecture:** Multi-process event-driven trading pipeline

---

## Overview

The trading system flows through 5 distinct phases:

1. **CONTEXT CACHE** — `latest_entry_context()` provides ready/not-ready status + auto-upgrade
2. **ENTRY DECISION** — `reviewer.py` calls Qwen every 30s to decide side/zone/confidence
3. **ZONE VALIDATION** — Proposal is validated and written to disk
4. **EXECUTION POLLING** — `paper_runner.py` watches for ready proposals every 0.25s
5. **BROKER FILL** — `paper_executor.py` monitors ticks, fills order when price enters zone

---

## Phase 1: CONTEXT CACHE

**File:** `market_context_cache.py`  
**Function:** `latest_entry_context(symbol="XAUUSDr", auto_upgrade=True)`

### Flow

```
latest_entry_context(symbol)
├─ Load latest manifest from SQLite cache
├─ If manifest.status != "ready":
│  └─ auto_upgrade=True:
│     ├─ Spawn MT5MarketSource connection
│     ├─ Create QwenContextShadow(cache, source, ollama)
│     └─ Call shadow.run_once(run_qwen=True, benchmark_minute=True)
│        ├─ Rebuild levels (D1-M1 support/resistance)
│        ├─ Rebuild playbooks (watch zones)
│        ├─ Rebuild minute packet (latest M1 + quote)
│        └─ Return updated manifest
└─ Return entry_context dict with:
   ├─ status: "ready" | "blocked"
   ├─ structure: {H1/H4 locations, nearest zones}
   ├─ session: {session_name, trade_permitted}
   ├─ playbooks: [{level_id, buy_cond, sell_cond}]
   ├─ minute: {quote, closed_m1, forming_candles}
   └─ levels: [{level_id, timeframe, zone_low/high, role}]
```

### What "ready" Means

ALL of these must be true for `status="ready"`:

```python
flags = {
    "model_resident": model_on_gpu,
    "raw_data_valid": gate_a,  # all timeframes have data
    "structural_cache_valid": gate_b,  # levels/structure built
    "level_cache_valid": gate_b and has_levels,
    "playbooks_valid": gate_b and all_playbooks_have_conditions,
    "session_cache_valid": gate_b and session_data_ok,
    "minute_delta_valid": incremental_test_passed,
    "context_challenge_valid": qwen_qualification_passed,
}
status = "ready" if all(flags.values()) else "blocked"
```

If ANY flag is False, Qwen entry is blocked with a failure reason in the manifest.

---

## Phase 2: ENTRY DECISION

**File:** `reviewer.py`  
**Function:** `generate_automatic_deal_sheet()`  
**Cycle Time:** Every 30 seconds (QWEN_ENTRY_INTERVAL_SECONDS)

### Gating Checks (Lines 1885-1925)

```python
# Gate 1: Market open?
if not market.get("open"):
    review = {"status": "wait", "reason": "market_closed"}
    return

# Gate 2: Cache ready?
entry_cache = latest_entry_context(symbol)  # AUTO-UPGRADE HERE
if entry_cache.get("status") != "ready":
    review = {"status": "wait", "reason": entry_cache.get("reason")}
    return

# Gate 3: Session permitted?
if not entry_cache.get("session", {}).get("trade_permitted"):
    review = {"status": "wait", "reason": "off_session"}
    return

# Gate 4 (implicit): No position open
# (handled by paper_runner.py, not reviewer.py)

# All gates passed → call Qwen
facts = compact_entry_facts(entry_cache, decision_levels, planner_context, symbol)
prompt = build_entry_prompt(facts)
result = ollama_generate(prompt, format_schema=entry_decision_schema(...))
review = json.loads(result["response"])
```

### What Qwen Decides (Lines 1926-1959)

Qwen returns a JSON decision with schema:

```json
{
  "bias": "buy|sell|conditional",
  "confidence": 0-100,
  "summary": "...",
  "execution_plan": {
    "status": "ready|wait",
    "reason": "entry_trigger_matched|...",
    "side": "buy|sell",
    "entry_low": float,
    "entry_high": float,
    "stop_loss": float,
    "take_profit": float,
    "stop_level_id": "H1_PREVIOUS_LOW",
    "target_level_id": "D1_PREVIOUS_HIGH"
  },
  "invalidation": null,
  "evidence_ids": ["candle_id_1", "level_id_2"]
}
```

### Validation (Lines 1971-2039)

```python
provenance_failures = validate_entry_provenance(review, entry_cache)
# Check: are cited evidence_ids actually in the cache?

contradiction = entry_policy.check_legacy_contradiction(review)
# Check: status="ready" but confidence=0? (bug signal)

if not contradiction:
    contradiction = entry_policy.check_ready_reason_contradiction(review)
    # Check: reason reads as "invalidated" but status="ready"?

if provenance_failures or contradiction:
    review["execution_plan"]["status"] = "wait"
    review["execution_plan"]["reason"] = contradiction or "provenance_failed"
```

### Saving the Proposal (Lines 2091-2138)

If `execution_plan.status == "ready"`:

```python
proposal_id = new_proposal_id()  # UUID
append_qwen_decision(
    decision_type="entry",
    symbol=symbol,
    price=snapshot.get("price"),
    prompt_text=prompt_text,
    raw_response=raw_response,
    parsed=review,
    proposal_id=proposal_id,
)

# ENTRY_STATE_FILE is updated with:
entry_state = {
    "proposal_id": proposal_id,
    "execution_plan": {
        "status": "ready",
        "side": "buy|sell",
        "entry_low": float,
        "entry_high": float,
        "stop_loss": float,
        "take_profit": float,
    },
    ...
}
```

---

## Phase 3: ZONE VALIDATION

**File:** `reviewer.py`  
**Function:** `normalize_execution_plan()` + `validate_entry_against_plan()`

### Validation Steps (Lines 2023-2039)

```python
# 1. Normalize the plan (apply defaults, cap ranges)
review["execution_plan"] = normalize_execution_plan(
    review.get("execution_plan"),
    snapshot,
    entry_cache,
    bias=review.get("bias"),
    confidence=review.get("confidence"),
)

# 2. Check session plan gating (if enabled)
plan_failures = validate_entry_against_plan(review["execution_plan"], planner_context)
if plan_failures and review["execution_plan"].get("status") == "ready":
    review["execution_plan"]["status"] = "wait"
    review["execution_plan"]["reason"] = "plan_gating_rejected"

# 3. Check geometry (in paper_executor later)
if execution_plan["status"] == "ready" and execution_plan["side"] == "buy":
    assert execution_plan["entry_low"] < execution_plan["entry_high"]
    assert execution_plan["stop_loss"] < execution_plan["entry_low"]
    assert execution_plan["take_profit"] > execution_plan["entry_high"]
```

### Result

The proposal is written to `ENTRY_STATE_FILE` if and only if:

- ✅ `execution_plan.status == "ready"`
- ✅ All geometry checks pass
- ✅ Confidence ≥ 51
- ✅ All validation failures empty

**File:** `entry-proposals-YYYY-MM-DD.jsonl`

---

## Phase 4: EXECUTION POLLING

**File:** `paper_runner.py`  
**Function:** `run_loop()`  
**Cycle Time:** Every 0.25 seconds

### Polling Loop (Lines 413-517)

```python
while True:
    # 1. Check daily cap
    daily_completed = broker_filled_today()
    if daily_completed >= DAILY_PAPER_CAP:
        logging.info("Daily cap reached")
        time.sleep(60)
        continue

    # 2. Get latest ready proposal
    proposal = latest_ready_proposal()
    # (queries entry-proposals-*.jsonl for status="ready")
    if proposal is None:
        time.sleep(PROPOSAL_POLL_SECONDS)  # 0.25s
        continue

    # 3. Runtime validation
    runtime_failures = proposal_runtime_failures(proposal)
    if runtime_failures:
        skip_proposal(proposal["proposal_id"], "runtime_validation_failed")
        continue

    # 4. Check for open position
    if has_open_qwen_position():
        logging.info("Single-position gate blocked")
        time.sleep(1)
        continue

    # 5. Check cooldown
    remaining = cooldown_remaining_seconds()
    if remaining > 0:
        # Loss cooldown or win cooldown active
        if not loss_cooldown_bypass_ok(proposal):
            skip_proposal(proposal["proposal_id"], "cooldown_active")
            continue

    # 6. FORWARD TO EXECUTOR
    proposal_id = proposal["proposal_id"]
    logging.info("Starting validated proposal %s", proposal_id)
    try:
        result = paper_executor.run(arguments_for(proposal))
        logging.info("Completed %s, net_pnl=%s", proposal_id, result.get("net_pnl"))
        
        # Post-trade cooldown
        seconds, label = cooldown_for(result)
        if seconds:
            start_cooldown(seconds, label)
    except Exception:
        logging.exception("Paper proposal failed: %s", proposal_id)
        time.sleep(3)
```

### Gate Checks

**Four gates must all pass:**

1. **Daily cap:** `broker_filled_today() < 100`
2. **Position availability:** No open Qwen position
3. **Proposal ready:** `latest_ready_proposal()` returns a proposal
4. **Runtime validation:** `proposal_runtime_failures()` returns empty list

If ANY gate blocks, the loop continues and tries again 0.25s later.

---

## Phase 5: BROKER FILL

**File:** `paper_executor.py`  
**Function:** `run(args)` → `_run(args)`  
**Execution:** Exclusive lock prevents parallel fills

### Arguments Passed (Lines 497-502)

```python
# From proposal:
result = paper_executor.run(arguments_for(proposal))
# arguments_for() creates Namespace with:
# - proposal_id: UUID
# - symbol: "XAUUSDr"
# - side: "buy" | "sell"
# - entry_low: float (zone low)
# - entry_high: float (zone high)
# - stop_loss: float (Qwen's SL)
# - take_profit: float (Qwen's TP)
# - volume: 0.5 (default)
# - signal_ttl_seconds: 60 (proposal expires in 60s)
```

### Entry Zone Monitoring (Lines 881-976)

```python
signal_deadline = time.monotonic() + signal_seconds_left  # +60 seconds

while True:
    # Check signal TTL
    if not fills and time.monotonic() >= signal_deadline:
        return {"reason": "signal_expired", "fills": []}

    # Get latest MT5 tick
    tick = mt5.symbol_info_tick(args.symbol)
    if tick is None or tick.time_msc <= 0:
        time.sleep(args.poll_ms / 1000)  # 0.25s
        continue

    # Tick age check
    age_ms = int(time.time() * 1000) - int(tick.time_msc)
    if age_ms > args.maximum_tick_age_ms:  # 3000ms = 3s
        time.sleep(args.poll_ms / 1000)
        continue

    # Extract price
    entry_quote = fill_price(tick, args.side)  # bid for buy, ask for sell

    # Check location
    location = entry_location(
        args.side,
        entry_quote,
        args.entry_low,
        args.entry_high,
        args.stop_loss,
    )
    # Returns: "inside_zone", "favorable_outside", "unfavorable_outside", "past_stop"

    # Check fill readiness
    currently_allowed, gate = entry_fill_ready(
        args.side,
        entry_quote,
        args.entry_low,
        args.entry_high,
        args.stop_loss,
        latest_closed_m1_bar(args.symbol),
    )
    # gate = "inside_zone_waiting_m1_failure" | "armed_m1_failure" | "favorable_outside"
    # currently_allowed = True only if BOTH:
    # - price is inside zone [entry_low, entry_high]
    # - latest completed M1 bar probed zone and failed to close beyond it

    # Track best price
    tracker_state = entry_tracker.observe(
        entry_quote,
        time.monotonic(),
        inside_range=currently_allowed,
        signal_seconds_left=max(0.0, signal_deadline - time.monotonic()),
        poll_seconds=args.poll_ms / 1000,
        location=location,
    )

    # FILL TRIGGER
    if not fills and tracker_state.get("enter"):
        logging.info(
            "entry_gate=%s filling inside zone [%.3f, %.3f]",
            gate,
            args.entry_low,
            args.entry_high,
        )
        try:
            order_result = submit_single_position(args, execution_id, tick)
        except GeometryRejection as e:
            logging.info("entry refused: %s", e.reason_code)
            return {"reason": e.reason_code, "fills": []}

        # Record the fill
        fill = {
            "price": float(order_result.price),
            "volume": args.volume,
            "stop_loss": args.stop_loss,
            "take_profit": args.take_profit,
            "entry_gate": gate,
            "deal": int(order_result.deal),
            "order": int(order_result.order),
        }
        fills.append(fill)
        logging.info("mt5_fill deal=%d order=%d price=%.3f", 
                     order_result.deal, order_result.order, order_result.price)

    # P&L tracking while filled
    if fills:
        live_positions = owned_positions(args.symbol, execution_id)
        pnl = sum(float(position.profit) for position in live_positions)
        peak_pnl = max(peak_pnl, pnl)
```

### Key Entry Gates (Lines 941-948)

```python
def entry_fill_ready(
    side: str,
    entry_quote: float,
    entry_low: float,
    entry_high: float,
    stop_loss: float,
    latest_m1: dict,
) -> tuple[bool, str]:
    """
    True only if BOTH:
    1. Price is inside zone
    2. M1 rejection confirmed
    """
    
    # Gate 1: Price inside zone?
    if not inside_entry_zone(entry_quote, entry_low, entry_high):
        return False, "outside_zone"

    # Gate 2: M1 failure at zone?
    if latest_m1 is None:
        return False, "inside_zone_waiting_m1_failure"

    # For buy: zone is [entry_low, entry_high]
    # M1 fails if: open/close both below entry_high
    if side == "buy":
        if latest_m1["close"] < entry_high and latest_m1["open"] < entry_high:
            return True, "armed_m1_failure"
    elif side == "sell":
        if latest_m1["close"] > entry_low and latest_m1["open"] > entry_low:
            return True, "armed_m1_failure"

    return False, "inside_zone_waiting_m1_failure"
```

---

## The Complete Gate Chain

For a trade to execute, ALL gates must pass in sequence:

```
PHASE 1: CACHE GATE
├─ latest_entry_context(auto_upgrade=True)
├─ manifest.status == "ready"
└─ ✅ Returns entry_context

PHASE 2: ENTRY DECISION GATE
├─ Market.open == True
├─ entry_cache.status == "ready"
├─ session.trade_permitted == True
├─ Qwen.execution_plan.status == "ready"
├─ confidence >= 51
└─ ✅ Proposal written to disk

PHASE 3: EXECUTION POLLING GATE
├─ Daily cap < 100 fills
├─ No open Qwen position
├─ latest_ready_proposal() found
├─ runtime_failures == []
└─ ✅ Forwarded to executor

PHASE 4: ENTRY ZONE GATE
├─ signal_deadline not expired (60s TTL)
├─ price inside [entry_low, entry_high]
├─ M1 bar probed zone and FAILED
└─ ✅ Order submitted to MT5

PHASE 5: TRADE MANAGEMENT GATE
├─ Position filled
├─ SL and TP set
├─ trade_management.py monitors (30s cycle)
├─ Exit on: invalidation/flip/arithmetic/time
└─ Position closed
```

If any gate blocks, the system doesn't error—it waits and retries.

---

## Timing & Latency

```
∆t=0s     reviewer.py checks cache (every 30s)
          ↓
∆t=~1s    Qwen decision (17s on GPU, <1s on hot cache)
          ↓
∆t=~2s    proposal written to disk
          ↓
∆t=~2s    paper_runner polls (every 0.25s)
          ↓
∆t=~2.1s  executor starts (within 0.25s of ready)
          ↓
∆t=~2-15s executor waits for price entry zone
          signal expires at ∆t=62s
          ↓
∆t=2-62s  price inside zone → M1 fails at zone
          ↓
∆t=~62s   ORDER SUBMITTED
```

**Total latency from decision to fill:** 0-60 seconds depending on when price enters the zone.

---

## Code Ownership

| Component | File | Process | Cycle |
|-----------|------|---------|-------|
| **Cache** | `market_context_cache.py` | Background (daemon) | ~30s refresh |
| **Entry Decision** | `reviewer.py` | Entry process | ~30s polling |
| **Execution** | `paper_executor.py` | Paper runner | Per proposal |
| **Management** | `trade_management.py` | Management process | ~30s per position |
| **Session Planning** | `session_planner.py` | Background (daemon) | ~1h refresh |

---

## Status Codes

All status values seen during this flow:

```
Cache Status:
  "ready"           → Manifest passed all 8 flags
  "blocked"         → At least one flag failed

Entry Status:
  "ready"           → Qwen ready + all validations passed
  "wait"            → Qwen wait, or validation failed

Execution Status:
  "mt5_execution_started"    → Order submitted to MT5
  "mt5_fill"                 → Order filled
  "mt5_execution_closed"     → Position closed by management
  "mt5_execution_skipped"    → Never submitted (expired, geometry rejected)
```

---

## Summary

The trading system is a **5-phase gated pipeline**:

1. **Cache** ensures all data is current and valid (auto-upgrades on failure)
2. **Entry Decision** asks Qwen for side/zone/confidence every 30 seconds
3. **Proposal** is validated and saved if ready
4. **Runner** polls for ready proposals and forwards to executor
5. **Executor** monitors ticks, enters zone when M1 rejection confirmed, submits order

No phase skips its gates—if any gate blocks, the system waits and retries rather than erroring or forcing a bad trade. The auto-upgrade mechanism ensures the cache never stays blocked indefinitely.

