# Qwen Trade Software

This directory is the version-controlled source snapshot for the complete local
GoldFlow/Qwen demo-trading application.

## Components

- `backend/software_runtime.py` is the single startup and supervision entry
  point. It starts MT5 and Ollama when needed, verifies the IIS website, and
  supervises the reviewer, cache-context service, and demo paper runner.
- `backend/market_context_cache.py` maintains the SQLite/WAL candle and context
  hierarchy, builds the compact minute packet, runs deterministic/Qwen
  qualification gates, and publishes the readiness manifest. Its ready packet
  is the mandatory provenance source for entry Qwen; it still never places an
  order itself.
- `backend/reviewer.py` builds MT5 snapshots, requests Qwen reviews, records
  proposals, and serves the local dashboard API. Proposal context comes from
  cache-qualified D1 through M1 structure, sessions, playbooks, levels, volume,
  and exact evidence IDs. Prior execution outcomes and P&L are excluded.
- `backend/session_planner.py` runs the session-hierarchy planner (day plan,
  session plans, hourly updates, session verdicts). Writes `planner-state.json`
  and archives to `tick_data/`. Supervised by `software_runtime.py`.
- `backend/market_memory_worker.py` owns the immutable SQLite market-event
  ledger and deterministic per-symbol/timeframe projections.
- `backend/market_graph_worker.py` optionally projects that ledger into Neo4j
  through a transactional outbox. It publishes bounded temporal/session and
  cross-instrument context for Qwen but never participates in broker execution.
- `backend/trade_manager.py` is the separate single-position management layer.
  It preserves the exact peak/giveback path and prior decisions, then validates
  reached-level rejection or thesis invalidation from completed M1/M5 evidence.
- `backend/paper_runner.py` consumes only fresh validated proposals and holds a
  process-wide singleton lock so two runners cannot execute concurrently.
- `backend/paper_executor.py` enforces the MT5 demo-account lock, opens exactly
  one 0.50-lot position, and maintains the broker safety stop. It never adds,
  averages, or closes merely because of elapsed time or small gross profit.
- `planview/` is the sole local UI (Next.js GoldFlow Plan View: session
  hierarchy + chart). Dev: `npm run dev` on port 3000. Deploy:
  `backend/install-planview-iis.ps1` (IIS ports 8088 and 80).

### Dashboard API (reviewer.py :48632)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/snapshot` | GET | Merged entry + management dashboard |
| `/deal-sheet` | POST | Trigger entry Qwen decision |
| `/plan` | GET | Session planner state |
| `/candles?tf=M15&count=200` | GET | Chart OHLC from cache SQLite |
| `/plan/history?date=YYYY-MM-DD` | GET | Replay planner tick data for a day |

Set `QWEN_PLAN_GATING=1` to gate entries against the validated session plan
(default off until planner has run for a few days).

## Optional Neo4j market graph

The complete installation, security, verification, recovery, and extension
reference is [`NEO4J_OPERATIONS.md`](NEO4J_OPERATIONS.md).

Neo4j is disabled by default. Install/run a Neo4j 5.x or compatible Aura
database, install `backend/requirements.txt` into the live Python runtime, and
set these process environment variables before starting the unified runtime:

```powershell
$env:QWEN_NEO4J_ENABLED = "1"
$env:QWEN_NEO4J_URI = "bolt://127.0.0.1:7687"
$env:QWEN_NEO4J_USER = "neo4j"
$env:QWEN_NEO4J_PASSWORD = "<secret>"
$env:QWEN_NEO4J_DATABASE = "neo4j"
$env:QWEN_GRAPH_SYMBOLS = "XAUUSDr,DXY"
```

Additional Forex pairs are comma-separated in `QWEN_GRAPH_SYMBOLS`; graph
labels and queries do not contain gold-specific logic. The worker creates
constraints, backfills from `cache/market-intelligence.sqlite3`, performs
idempotent batched writes, and maintains:

- `cache/market-graph-health.json` — connection, projection lag, retries and
  dead-letter count.
- `cache/market-graph-context.json` — bounded local snapshot read by the
  reviewer, avoiding a Neo4j network call in the entry hot path.

If Neo4j is unavailable, SQLite collection, Qwen's baseline context, trade
execution, management and broker protection continue unchanged. Run one
diagnostic projection cycle with:

```powershell
C:\ProgramData\Miniconda3\python.exe backend\market_graph_worker.py --once
```

Runtime logs, proposal history, execution history, model files, lock files, and
Python caches are intentionally excluded from Git.

## Cache-context validation

The runtime database is
`C:\Users\HP\AppData\Local\QwenTradeReviewer\cache\market_context.sqlite3`.
It holds immutable completed candles, separate forming candles, versioned
derived objects, Qwen validation responses, readiness manifests, and latency
events. The dashboard snapshot exposes the latest readiness state under
`context_cache`.

Useful source-tree checks:

```powershell
C:\ProgramData\Miniconda3\python.exe backend\market_context_cache.py --self-test
C:\ProgramData\Miniconda3\python.exe backend\market_context_cache.py --once --no-qwen --no-minute-benchmark
C:\ProgramData\Miniconda3\python.exe backend\market_context_cache.py --once --no-minute-benchmark
```

The first command is deterministic and offline. The second validates live MT5
data without model calls and is the mode supervised continuously by the unified
runtime. The third is the manual/off-hours uncapped Qwen shadow qualification;
it is not allowed to hold the shared model ahead of the existing paper
reviewer. A successful exact challenge stores a certificate bound to the
qualification-contract version and Qwen model digest. Deterministic refreshes
reuse that certificate while independently validating current data, levels,
sessions, playbooks, and minute deltas. A `blocked` result is intentional
whenever any hard provenance,
localization, playbook, residency, or compact-response gate fails; it never
silently enables execution.

## Qwen model download

Live trading uses `qwen-trading-v005:latest` in Ollama (`ollama create qwen-trading-v005 -f Modelfile` from the Colab GGUF export). Keep `qwen-trading-v004` installed if you need a rollback.

## Deployed locations

- Backend: `C:\Users\HP\AppData\Local\QwenTradeReviewer`
- Website: `C:\inetpub\GoldFlowPlanView` (http://127.0.0.1:8088/ and :80)

The Windows login entry invokes `backend/start-reviewer.ps1`, which launches
the unified `QwenTradeSoftware` runtime. The deployed files should be refreshed
from this source directory whenever a committed backend or website change is
released.

This application is restricted to historical research and MT5 demo/paper
execution. The executor must continue to refuse non-demo accounts.

Execution proposals have a total 60-second validity window measured from the
recorded Qwen result. The runner polls every 250 ms, and the executor continues
checking the same deadline until the first fill so an old plan cannot wait for
entry after its signal expires.

Entry and management are separate strategy phases. Entry Qwen selects one
position and records an immutable thesis, target, and invalidation. Once filled,
management Qwen reviews each newly completed M1 candle with completed M1/M5
evidence, current named levels, the executor's peak/giveback state, reached
levels, and recent management decisions. No new proposal is allowed while that
position remains open.

Qwen decision generation has no wall-clock cutoff on CPU and uses an
8,192-token context so the canonical doctrine and cache facts remain available with the
complete market facts. Only one generation can run at a time; automatic
refreshes return the current snapshot while a decision is in progress instead
of queuing overlapping model requests. The proposal timestamp is recorded after
generation, so the executor's 60-second signal-validity window starts from the
completed Qwen result.

The reviewer generates entry proposals from its own service loop whenever no
Qwen position is open. The website displays and can manually refresh decisions,
but an open browser is not required for automatic paper trading.

A decisive M5 impulse confirmed by at least three of the latest five M1 closes
may be traded as one position when M15/M30 location does not invalidate it.

The local Qwen objective is to select the stronger currently executable side,
not to default to waiting. A modest edge uses one position toward the nearest
meaningful opposing named level.
Immediate plans must bracket the current quote with named entry levels so they
can fill during the 60-second lifetime.

A ready entry requires Qwen confidence of at least 51 and an explicit buy or
sell bias that agrees with the normalized plan side. Confidence is used as a
coherence qualification, not as a promise of profit. The runner revalidates
the current cache readiness, UTC session permission, structural/playbook
epochs, and model identity immediately before sending the plan to the executor.

All components use the same `QWEN_` ownership prefix and a 100-filled-position
daily cap. The cap and dashboard statistics come from MT5 deal history for the
Qwen magic number; local JSONL logs are audit evidence, never trade-count truth.
Expired unfilled proposals do not consume the cap.

Inside a Qwen-approved entry range, execution records the lowest ask for a buy
or highest bid for a sell. It enters on the first bounded retracement from that
best quote or when the two-second observation completes. The observer cannot
change the range, direction, or 60-second proposal lifetime.

The executor records movement, target progress, live P&L, peak, drawdown, and
holding time, but it does not decide strategy exits. A named target is a review
location rather than an automatic fill. Every favorable named level reached by
the recorded execution or completed M1 path becomes a review location. Qwen
holds through confirmed
acceptance toward the next level, protects only after confirmed continuation,
and closes only after deterministic validation of a completed level response.
A pre-model confirmation guard immediately enforces a reached-level rejection
or immutable invalidation when completed M1 and M5 agree, so a slow or
contradictory `hold` cannot surrender the whole favorable path. P&L and elapsed
seconds alone cannot confirm a close.

Qwen's named stop level remains the structural invalidation reference, but it
is not used as a tight broker stop. Execution derives a 3-5 XAUUSD price-unit
stop distance from recent closed M1/M5 ranges and applies it to the one actual
fill. This emergency broker stop remains independent of Qwen so process or
model failure cannot leave an unprotected paper position.
