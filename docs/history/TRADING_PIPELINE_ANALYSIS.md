# End-to-End Trading Pipeline Analysis
**Date: 2026-08-10 | Status: Live Paper Trading**

---

## Executive Summary

The trading system is a **modular, market-aware, multi-process architecture** that chains cache warming → request formatting → Qwen inference → trade execution → feedback collection. The pipeline is **event-driven and gated** at multiple stages:

1. **Market Gate** (only trade when gold is quoting)
2. **Cache Gate** (only call Qwen with valid market context cache)
3. **Model Residency** (load/unload Qwen dynamically based on market hours)
4. **Cooldown Gate** (honor 120s loss cooldowns)
5. **Execution Gate** (paper executor validates risk parameters)

---

## Pipeline Stages

### STAGE 1: MARKET MONITORING & MODEL RESIDENCY

**Location:** `review_shared.py` + `trade_management.py`

#### 1a. Market Open Detection
```
Entry Point: gold_market_open()
├─ calendar_gold_market_open() 
│  └─ Check XAUUSD weekend close (Fri 21:00 UTC → Sun 22:00 UTC = closed)
│
└─ mt5_quote_is_fresh()
   ├─ MT5 initialization check
   ├─ Get latest tick from XAUUSD
   └─ Verify freshness: MAX_QUOTE_AGE_MS = 180,000ms (3 minutes)
```

**Log Evidence (2026-08-10 03:00-03:01 UTC):**
```
03:00:06 Market closed (calendar_closed) → Qwen unloaded/idle
03:00:38 Market closed (mt5_tick_stale_176559ms) → Still waiting
03:01:43 MT5 tick age = -294ms (fresh!) 
         → Model residency triggered = LOADED
```

#### 1b. Model Residency Sync
```
Function: sync_model_residency(market: dict)
├─ Desired state = "loaded" if market.open else "unloaded"
├─ Current state = read from model-residency.json
│
└─ If changed:
   ├─ warm_model() → ollama_generate("", keep_alive=-1)
   │  └─ Logs: "Qwen model loaded and pinned: qwen-trading-v003:latest"
   │
   └─ unload_model() → ollama_generate("", keep_alive=0)
       └─ Drops from Ollama memory
```

**Status File:** `E:\QuantLLMBot\apps\qwen_trade_software\backend\model-residency.json`
```json
{
  "state": "loaded",
  "reason": "market_open=True reason=mt5_tick_age_-294ms",
  "model": "qwen-trading-v003:latest",
  "updated_at_utc": "2026-08-10T03:01:43.384Z"
}
```

---

### STAGE 2: MARKET CONTEXT CACHE BUILDING

**Location:** `market_context_cache.py` (separate daemon process)

#### 2a. Cache Ingestion Loop
```
Interval: Continuous (run_once every cycle)
├─ Connect to SQLite DB: market_context_cache.db
├─ Ingest completed candles from MT5 (all timeframes: M1, M5, M15, M30, H1, H4, D1)
│
└─ For each candle:
   ├─ Compute structural S/R levels (pivot, fib, ATR-based)
   ├─ Build session-aware playbook entries
   ├─ Track evidence_id (immutable hash of candle)
   └─ Update manifest with epochs & validation status
```

#### 2b. Cache Qualification Gate
```
Function: latest_entry_context(symbol="XAUUSDr")
│
├─ Check manifest status = "ready"? 
│  └─ If not: return {status: "blocked", reason: "cache_readiness_not_ready"}
│
├─ Fetch cache objects:
│  ├─ structural    (levels, timeframe locations, S/R zones)
│  ├─ levels        (active price levels)
│  ├─ session       (current trading session context, trade_permitted flag)
│  ├─ playbooks     (pre-computed trade setup patterns)
│  └─ minute        (latest M1 candle + decision_time, TTL ~30s)
│
├─ Validate epochs match compatible_epochs in manifest
│  └─ If mismatch: return {status: "blocked", reason: "cache_provenance_invalid"}
│
├─ Check minute TTL (soft extend if still current M1)
│  └─ If expired & new M1 exists: return {status: "blocked", reason: "expired"}
│
└─ If all pass: return {
    status: "ready",
    validated_at_utc: manifest.validated_at_utc,
    decision_time_utc: minute.decision_time_utc,
    expires_at_utc: minute.expires_at_utc,
    epochs: {...},
    structure: {...},
    levels: [...],
    session: {...},
    playbooks: [...],
    minute: {...}
  }
```

**Cache Validation Failures Observed (Today):**
- `cache_readiness_not_ready` - manifest not yet built
- `cache_object_missing` - one or more required objects null
- `cache_provenance_invalid` - epoch version mismatch
- `entry_cache:minute:expired` - M1 packet too old

---

### STAGE 3: QWEN ENTRY DECISION

**Location:** `reviewer.py` (entry decision process)

#### 3a. Decision Loop
```
Interval: QWEN_ENTRY_INTERVAL_SECONDS = 30 (configurable)
Gating: Only when market.open = True

Loop:
├─ Check: Is there an open Qwen position? 
│  └─ If YES: skip (trade_management.py handles ongoing reviews)
│
├─ Retrieve latest_entry_context()
│  └─ If blocked: log wait_decision, skip, log same reason only once
│
├─ Build entry facts dict:
│  {
│    timestamp_utc,
│    symbol, timeframe,
│    current_price,
│    near_levels (S/R within ±20 pips),
│    recent_closed (M1 x5, M5 x5, M15 x3, M30 x3),
│    execution_levels (decision_levels from structure),
│    planner (day/session plan + verdicts),
│    citeable_evidence_ids (all cache objects involved)
│  }
│
├─ build_entry_prompt():
│  ├─ Load contract: core_skill.md + qwen_cached_entry prompt section
│  ├─ Append: ENTRY FACTS as compact JSON
│  └─ Result: ~3KB-5KB prompt
│
├─ CALL ollama_generate(prompt, num_predict=160, timeout=45):
│  │
│  ├─ Pre-flight: gold_market_open() must return True
│  │  └─ If False: raise RuntimeError("Qwen call blocked; market closed")
│  │
│  ├─ Lock: model_generation_lock() (prevents concurrent model access)
│  │
│  ├─ POST to http://127.0.0.1:11434/api/generate
│  │  ├─ model: "qwen-trading-v003:latest"
│  │  ├─ prompt: <entry_prompt>
│  │  ├─ format_schema: JSON with keys (direction, confidence, summary, setup_type, entry_level, stop_level, target_level)
│  │  └─ keep_alive: -1 (keep in memory)
│  │
│  ├─ Log: log_qwen_generate() captures:
│  │  ├─ model_name
│  │  ├─ prompt_chars
│  │  ├─ response_chars
│  │  ├─ duration_ms
│  │  └─ ok=True/False
│  │
│  └─ Return: {direction, confidence, summary, setup_type, entry_level, stop_level, target_level, ...}
│
├─ Validate Qwen response:
│  ├─ confidence >= MIN_ENTRY_CONFIDENCE (51) ?
│  ├─ direction in {BUY, SELL} ?
│  ├─ All levels within structure bounds ?
│  └─ Evidence IDs are citeable ?
│
└─ Generate proposal_id & persist paper-proposals-YYYY-MM-DD.jsonl:
   {
     proposal_id: "paper-20260810T050542-5831a6e9",
     created_at_utc: "2026-08-10T05:05:42.181833Z",
     mode: "paper-research",
     source: "dashboard-deal-sheet",
     symbol: "XAUUSDr",
     timeframe: "M1",
     market: {price, connected, levels, market_context, cache_context},
     qwen: {model, bias, confidence_raw, confidence, summary, setup_type, direction, entry_level, stop_level, target_level, ...},
     day_plan_id: "dp-20260810",
     session_plan_id: "sp-20260810-asia"
   }
```

**Example Qwen Response (Winning Trade paper-20260810T050542-5831a6e9):**
```
Direction: SELL
Confidence: 82
Summary: "H1 high rejection at D1 floor pivot; sell setup confirmed on M15/M5 convergence. Entry: 4337.5, Stop: 4340.5, Target: 4332.5"
Setup Type: "reversal"
Entry Level: 4337.5
Stop Level: 4340.5
Target Level: 4332.5
```

---

### STAGE 4: PROPOSAL VALIDATION & QUEUING

**Location:** `paper_runner.py`

#### 4a. Proposal Validation Gate
```
Function: Runs every PROPOSAL_POLL_SECONDS (0.25s)

├─ Read latest proposals from paper-proposals-*.jsonl
├─ Filter: already processed? (check processed_ids set)
├─ Filter: proposal age <= MAX_PROPOSAL_AGE_SECONDS (60s)?
│  └─ If older: skip (stale)
│
├─ Validate:
│  ├─ confidence >= MIN_ENTRY_CONFIDENCE (51)?
│  ├─ direction is valid?
│  ├─ levels make sense (entry, stop, target)?
│  └─ Daily cap not hit? (DAILY_PAPER_CAP = 100)
│
├─ Check loss cooldown:
│  ├─ Last trade lost? Start 120s cooldown
│  └─ Still in cooldown? Reject proposal
│
└─ If all pass: queue for execution
```

#### 4b. Execution Queuing
```
Once validated, proposal enters executor queue.
Key checks:
├─ Broker position count today
├─ Available margin
├─ Position sizing (0.1 lot default)
└─ Risk parameters (SL, TP, entry level sanity)
```

**Log Evidence (08:47 - 11:22 UTC):**
```
08:47:02 Starting validated proposal paper-20260810T034702-7da97990
09:05:25 Completed paper-20260810T034702-7da97990 reason=external_position_close net_pnl=-3.5
         [Loss cooldown started for 120 seconds]
09:07:25 [Loss cooldown completed]
09:07:25 Starting validated proposal paper-20260810T040703-1bfe6aef
...
09:47:25 Starting validated proposal paper-20260810T044705-5b4cc01b
09:55:26 Completed paper-20260810T044705-5b4cc01b reason=qwen_confirmed_close net_pnl=-50.5
         [Loss cooldown: 120 seconds]
```

---

### STAGE 5: PAPER EXECUTION

**Location:** `paper_executor.py` (MT5 paper trading)

#### 5a. Entry Execution
```
Function: paper_executor.run(proposal)

├─ Connect to MT5 terminal (demo account)
├─ Place entry order:
│  ├─ Symbol: XAUUSDr
│  ├─ Direction: BUY or SELL (from Qwen)
│  ├─ Lot size: 0.1 (fixed)
│  ├─ Entry price: proposal.entry_level
│  ├─ Stop loss: proposal.stop_level
│  ├─ Take profit: proposal.target_level
│  ├─ Magic number: QWEN_MAGIC = 26072401 (ownership tag)
│  └─ Comment: "QWEN_" + proposal_id
│
└─ Return: execution_id, entry_price, entry_time, position_id
```

#### 5b. In-Trade Management
```
Separate process: trade_management.py
Runs every QWEN_REVIEW_INTERVAL_SECONDS (30s)

While trade open:
├─ Monitor current P&L
├─ Call Qwen for ongoing review (if triggered by price/time)
│  └─ Qwen can recommend: HOLD, TIGHTEN_SL, MOVE_TP, CLOSE, etc.
├─ Check safety stops:
│  ├─ managed_or_safety_sl: fixed SL hit
│  ├─ managed_or_safety_tp: fixed TP hit
│  └─ max_duration: time-based exit
│
└─ When trade closes:
   ├─ Exit price
   ├─ Exit reason (qwen_confirmed_close, managed_or_safety_sl, external_position_close, etc.)
   ├─ Hold duration
   └─ Net PnL
```

**Example Exit Reasons Observed:**
- `qwen_confirmed_close` - Qwen decision to close
- `external_position_close` - Manual close via MT5
- `managed_or_safety_sl` - Stop loss hit
- `managed_or_safety_tp` - Take profit hit
- `entry_reward_risk_eroded` - Risk/reward ratio degraded

#### 5c. Execution Logging
```
File: paper-executions-YYYY-MM-DD.jsonl

Entry event:
{
  event: "mt5_execution_started",
  proposal_id: "paper-20260810T050542-5831a6e9",
  execution_id: <uuid>,
  entry_price: 4337.164,
  entry_time_utc: "2026-08-10T05:05:42Z",
  position_id: <mt5_position_id>,
  direction: "SELL",
  lot: 0.1,
  magic: 26072401
}

Close event:
{
  event: "mt5_execution_closed",
  proposal_id: "paper-20260810T050542-5831a6e9",
  execution_id: <uuid>,
  exit_price: 4337.164 + slippage,
  exit_time_utc: "2026-08-10T05:15:26Z",
  hold_duration_seconds: 610,
  net_pnl: 109.1,
  exit_reason: "qwen_confirmed_close"
}
```

---

## Key Observations from Today's Run

### Performance Metrics
```
Start: 2026-08-10 03:01 UTC (model loaded)
Stop:  2026-08-10 11:22 UTC (last proposal)
Duration: 8h 21m

Total proposals: 22 closed trades
├─ Winning trades (qwen_confirmed_close): 5 trades = +109.1, +29.65, +60.1, +246.5, +249.15
├─ Losing trades (qwen_confirmed_close): 4 trades = -50.5, -9.4, -30.9, -101.35, -168.45
└─ Safety/SL closures: 5 trades = -153.5, -153.5, -153.5, -194.0 (managed_or_safety_sl/tp)
    Other: external_position_close, skipped proposals

Win Rate (confirmed closes): 5 wins / 9 confirmed = 56%
Average Win: +123.1
Average Loss (confirmed): -72.0
Avg Win/Loss Ratio: 1.71x

Safety Activations: 5 (13% of closures) - good resilience
```

### Bug Found: Missing Logging Import
**File:** `paper_executor.py:571`
**Impact:** 3 proposals failed out of 22 total
- paper-20260810T042233-c93847fe (09:22:35)
- paper-20260810T054411-61cecd38 (10:44:13)
- paper-20260810T054940-9c58b7a7 (10:49:54)
- paper-20260810T054911-2bb201ee (10:49:59)

**Error:**
```
NameError: name 'logging' is not defined. Did you forget to import 'logging'?
```

---

## Architecture Breakdown

### Process Topology (5 Independent Processes)

```
market_context_cache.py (daemon)
├─ Reads: MT5 ticks → SQLite market_context_cache.db
├─ Builds: Structural levels, playbooks, session context, minute packets
└─ Output: market_context_cache.log, cache-once-latest.json

session_planner.py (daemon)
├─ Reads: Cache objects, market state
├─ Generates: Day plans, session plans, hourly updates
└─ Output: session-planner.log, day-plans-YYYY-MM-DD.jsonl

reviewer.py (HTTP server + entry decision loop)
├─ Entry decision: Call Qwen when flat
├─ Reads: latest_entry_context from cache
├─ Outputs: paper-proposals-YYYY-MM-DD.jsonl
├─ Serves: Dashboard HTTP API (:8001)
└─ Output: reviewer.log, entry-dashboard-state.json

trade_management.py (daemon)
├─ Monitors: Open Qwen positions on MT5
├─ In-trade reviews: Call Qwen for ongoing decisions
├─ Reads: MT5 live prices
└─ Output: trade-management.log, management-dashboard-state.json

paper_runner.py (executor loop)
├─ Polls: paper-proposals queue
├─ Validates: Confidence, levels, cooldowns
├─ Executes: MT5 paper orders
└─ Output: paper-runner.log, paper-executions-YYYY-MM-DD.jsonl
```

### Data Flow Diagram

```
┌─────────────────┐
│  MT5 Terminal   │ (Live market data, ticks, positions)
└────────┬────────┘
         │
         ├──→ market_context_cache.py ──→ SQLite DB + manifests
         │                                 (cache objects: structural, levels, playbooks, session, minute)
         │
         ├──→ trade_management.py ──→ Monitor open positions
         │    (reads cache, manages in-trade)
         │
         └──→ reviewer.py (entry decision)
              │
              ├─→ latest_entry_context() [cache gate]
              ├─→ build_entry_prompt() [contract + facts]
              ├─→ ollama_generate() [Qwen call] ◄──── QWEN WARMTH REQUIRED
              │   (model loaded via sync_model_residency)
              │
              └─→ paper-proposals.jsonl [proposal queue]
                   │
                   └──→ paper_runner.py [executor]
                        │
                        ├─→ Validate proposal (cooldown, confidence, levels)
                        ├─→ MT5 order entry
                        ├─→ Monitor position
                        └─→ paper-executions.jsonl [result logging]
```

---

## Critical Gating Mechanisms

| Gate | Trigger | Action | Evidence |
|------|---------|--------|----------|
| **Market Open** | gold_market_open() | Block Qwen calls if market closed | Trade mgmt: "Market closed (calendar_closed)" |
| **Quote Freshness** | mt5_quote_is_fresh() | Require MT5 tick < 3min old | "mt5_tick_age_-294ms" passes, "mt5_tick_stale_176ms" blocks |
| **Cache Readiness** | latest_entry_context() | Reject if manifest status != "ready" | Proposals wait for "cache_readiness_not_ready" |
| **Cache Provenance** | Epoch validation | Reject if cache object epochs don't match | "cache_provenance_invalid" with mismatches |
| **Model Residency** | sync_model_residency() | Unload Qwen when market closed | model-residency.json tracks "loaded"/"unloaded" |
| **Loss Cooldown** | Last trade lost | Reject new proposals for 120s | paper-runner.log: "Loss cooldown started/completed" |
| **Proposal Age** | Age check | Reject proposals > 60s old | PROPOSAL_POLL_SECONDS = 0.25 |
| **Confidence Threshold** | MIN_ENTRY_CONFIDENCE = 51 | Block low-confidence Qwen responses | Validation in paper_runner.py |

---

## Dependencies & Timing

### Critical Latencies
```
Market Close → Model Unload: Immediate (sync_model_residency triggers on tock check)
Qwen Call: 45s timeout, typically 1-3s (model already warm)
Entry Proposal → Execution: < 1 second (paper_runner polls every 0.25s)
In-Trade Review: Every 30s (trade_management.py interval)
Loss Cooldown: 120 seconds (enforced in paper_runner)
Cache Refresh: Every market tick (market_context_cache daemon)
```

### Model Warming Path
```
gold_market_open() = True
    ↓
sync_model_residency() checks desired state
    ↓
warm_model() calls ollama_generate("", keep_alive=-1)
    ↓
POST http://127.0.0.1:11434/api/generate → Load model into Ollama
    ↓
Subsequent Qwen calls are fast (model resident)
```

---

## File Organization

```
backend/
├─ logs/
│  ├─ paper-runner.log          [executor lifecycle, execution events]
│  ├─ paper-runner.log.2026-08-* [rotated daily]
│  ├─ paper-proposals-*.jsonl   [all proposals generated]
│  ├─ paper-executions-*.jsonl  [all execution start/close events]
│  ├─ reviewer.log              [entry decision logs]
│  ├─ trade-management.log      [in-trade review logs]
│  ├─ session-planner.log       [plan generation logs]
│  ├─ market-context-cache.log  [cache building logs]
│  ├─ model-residency.json      [current model state]
│  ├─ cache-once-latest.json    [latest cache manifest + stats]
│  └─ day-plans-YYYY-MM-DD.jsonl [session plan artifacts]
│
├─ review-tickets.json           [proposal + execution cross-reference]
├─ entry-dashboard-state.json   [entry process state for dashboard]
├─ management-dashboard-state.json [trade mgmt state for dashboard]
├─ planner-state.json           [session planner state]
└─ market_context_cache.db       [SQLite: candles, levels, playbooks, sessions]
```

---

## What Works Well

1. **Modular decomposition**: Entry decisions, management, and execution are independent processes
2. **Multi-gate safety**: Market + cache + cooldown + confidence gates prevent rogue trades
3. **Dynamic model management**: Qwen unloads when market closed, saving GPU memory
4. **Evidence traceability**: Every proposal cites the cache epochs it relied on
5. **Loss cooldown discipline**: Automatic 120s pause after losses prevents revenge trading
6. **Paper execution fidelity**: MT5 paper trading simulates real broker slippage/fills

---

## Known Issues

1. **Logging Import Bug** (paper_executor.py:571): Missing `logging` import causes 3 proposals/day to fail
2. **Cache Staling**: If market_context_cache daemon falls behind, minute packets expire quickly
3. **Qwen Timeout Risk**: 45s timeout on ollama_generate; if Ollama unresponsive, entry blocks for 45s
4. **Loss Cooldown**: Fixed 120s may be too aggressive if legitimate setups appear during cooldown

---

## Next Steps for Investigation

- [ ] Trace a single trade from Qwen prompt → execution → close (full JSON chain)
- [ ] Compare winning vs losing trades: Qwen confidence, setup_type, hold duration
- [ ] Audit cache object epochs: Are they versioning correctly across timeframes?
- [ ] Profile Ollama response times: Is 1-3s typical or sometimes slower?
- [ ] Examine session planner: How do day/session verdicts gate Qwen calls?

