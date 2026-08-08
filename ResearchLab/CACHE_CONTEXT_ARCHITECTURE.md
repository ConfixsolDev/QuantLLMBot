# Qwen Market Cache and Context-Validation Architecture

Status: execution-integrated implementation v3 (qualified 2026-08-04). The cache,
deterministic gates, Qwen validation, readiness manifest, and compact-minute
packet are implemented and all readiness gates pass. Entry Qwen now receives
only a ready, provenance-matched cache packet; a blocked cache deterministically
produces wait and cannot create an executable proposal. This does
not authorize a production strategy change and does not replace the
human-owned doctrine in `store/core_skill.md` or `store/sop.md`.

Implementation: `apps/qwen_trade_software/backend/market_context_cache.py`.
The unified runtime supervises its deterministic cache-update mode as a
separate context process consumed by the reviewer. Heavy Qwen qualification is manual/off-hours because
CPU warm-up must not hold the shared model lock ahead of the execution
champion. A successful challenge creates a certificate bound to the prompt and
validator contract version plus exact model digest. Volatile candle epochs use
that certificate while deterministic gates continue to validate current data.
Its SQLite database is runtime state outside the fixed eight-file research
store.

## Verified checkpoint (2026-08-04)

- Live MT5 demo ingestion passed for D1/H4/H1/M30/M15/M5/M1, with forming
  candles held separately from immutable completed candles.
- Gate A, Gate B, the incremental/restart fixture, and the compact minute
  response validator passed.
- The current compact minute packet measured 2,425 bytes, approximately 606
  tokens.
- The second consecutive ready refresh measured 4.9 ms ingestion and 1.6 ms
  minute assembly. These are observations, not latency guarantees.
- Ollama prompt-prefix reuse was observed: minute prompt evaluation fell from
  56.56 seconds on the context-switch call to 0.24 seconds on the immediately
  repeated call.
- On the current CPU-only host, the latest warmed Qwen minute latency was 37.33
  seconds: prompt evaluation was 0.24 seconds and output generation was 36.75
  seconds. Cache design removes repeated context work but cannot remove CPU
  token-generation time.
- Qwen passed exact D1/H4/H1 location, H4 state, nearest-zone and evidence
  localization, session/Asia facts, three playbook identities, completed versus
  forming H1 localization, deterministic invalidations, bounded data-request
  behavior, and the compact minute response test.
- Level identity, target, and invalidation wiring is code-owned. Qwen supplies
  bounded semantic response conditions keyed by immutable playbook IDs; it
  cannot rewrite geometry. Generic semantic tokens are bound to the expected
  level only when they contain no competing supplied level.
- Consecutive deterministic-only refreshes published `ready` with every flag
  true and no failures, proving that new candle epochs do not trigger another
  heavyweight qualification call.

## Research basis

The architecture follows hierarchical external memory rather than relying on
an LLM's hidden conversation state, consistent with the memory hierarchy in
[MemGPT](https://arxiv.org/abs/2310.08560). Exact provenance and separate
faithfulness/context checks follow the evaluation concerns described by
[RAGAS](https://arxiv.org/abs/2309.15217). Raw bars remain outside the prompt
because long-context retrieval can degrade when relevant facts are buried in
the middle, as shown in
[Lost in the Middle](https://arxiv.org/abs/2307.03172).

The runtime uses [SQLite WAL](https://www.sqlite.org/wal.html) for local
one-writer/multiple-reader access, the official Ollama
[`keep_alive` and timing fields](https://docs.ollama.com/api/generate), and MT5's
documented rule that bar position zero is the current forming bar
([copy_rates_from_pos](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py)).

## Outcome

The model performs one deep structural warm-up, proves that it can retrieve and
apply that context, and then receives a small incremental packet after each
completed M1 candle. The model weights remain resident in RAM/VRAM. Raw market
history, derived structure, level playbooks, session state, live deltas, and
position theses are separate versioned cache layers.

The application never relies on hidden LLM memory. Every decision records the
exact cache epochs and evidence IDs supplied to Qwen, so the decision can be
replayed without future data.

## Design principles

1. MT5 candles and ticks are the raw source of truth.
2. Completed and forming candles are never mixed.
3. Raw history is stored once and updated incrementally.
4. Deterministic calculations create levels and session facts.
5. Qwen interprets supplied facts; it does not invent or recompute them.
6. Long-term analysis is refreshed on structural events, not every minute.
7. The live packet contains deltas and references, not eight weeks of raw data.
8. Qwen may request bounded additional evidence through a typed contract.
9. A deterministic validator, not Qwen confidence, controls readiness.
10. No entry decision is valid without cache provenance and freshness checks.

## Runtime storage

Use one SQLite database in WAL mode at the deployed runtime location:

```text
C:\Users\<user>\AppData\Local\QwenTradeReviewer\cache\market_context.sqlite3
```

The database is runtime state and is excluded from Git. It is not added to the
fixed eight-file `ResearchLab/store`. JSONL remains the immutable audit stream,
but trading services no longer scan complete JSONL files for live state.

SQLite provides atomic updates, indexed timestamp queries, crash recovery, and
one-writer/multiple-reader operation without adding a separate service. The
hot current state is also held in memory and rebuilt from SQLite after restart.

## Cache layers

### L0: raw market cache

Stores normalized MT5 observations:

- eight complete weeks of D1 and H4 candles;
- two complete weeks of H1 candles;
- current UTC day of M30 and M15 candles;
- completed M5 candles from the active session/day boundary;
- completed M1 candles for at least the current H1 candle;
- the current forming M1/M5/M15/M30/H1/H4/D1 state; and
- sampled tick facts: bid, ask, spread, timestamp, and tick flags.

Completed-candle key:

```text
(symbol, timeframe, open_time_utc)
```

Required candle fields:

```text
open, high, low, close, tick_volume, spread, real_volume,
open_time_utc, close_time_utc, is_complete, source, ingested_at_utc
```

Completed rows are immutable. Forming rows live in a separate table and are
upserted until the timeframe closes, then promoted atomically to completed.

### L1: structural cache

Generated after raw-history validation. It contains compact interpretations
with evidence references:

```text
D1/H4/H1 location and auction state
completed parent swings
accepted/rejected zones
current H4 path and unfinished movement
nearest upper/lower structural zones
historical response summaries
unresolved structural conflicts
source candle IDs and source hash
```

It refreshes at startup, after every completed H4 candle, after a completed D1
candle, or when its source data is repaired. H1 completion updates the H1
subsection without rebuilding unrelated D1/H4 history.

### L2: deterministic level cache

Contains the existing cheat-sheet levels plus their provenance:

```text
level_id, timeframe, zone_low, zone_high, role, source_candle_ids,
calculation_method, created_at_utc, valid_from_utc, invalidated_at_utc
```

Levels are zones. The deterministic engine calculates them from completed
candles; Qwen assigns conditional interpretation only after a visible response.

### L3: H4 level-playbook cache

At every new H4 candle, Qwen receives validated structural/level caches and
prepares a two-sided playbook for each nearby important zone:

```json
{
  "playbook_id": "H4-20260803T1200Z-L03",
  "level_id": "H4_ZONE_03",
  "approach_state": "below_approaching",
  "buy_condition": "accepted close and held retest",
  "sell_condition": "failed test and close back inside",
  "buy_invalidation": 4063.2,
  "sell_invalidation": 4066.1,
  "lower_target_id": "M30_ZONE_02",
  "upper_target_id": "H4_ZONE_04",
  "missing_evidence": ["closed response at zone"],
  "evidence_ids": ["candle:H4:...", "level:H4_ZONE_03"],
  "status": "watch",
  "expires_at_utc": "next H4 close"
}
```

The playbook is a plan, not an order. It changes status through deterministic
events: approaching, testing, rejected, accepted, invalidated, or expired.

### L4: day and session cache

Contains:

- UTC trading date and current session;
- session start/end and time remaining;
- Asia high, low, close path, and completed bias description;
- completed M5 candles since the relevant session boundary;
- today's completed M15/M30 candles;
- current day relation to structural zones; and
- relative tick-volume facts by timeframe.

It updates on M5/M15/M30 close and session transition. Session statistics are
calculated in code, never inferred from the model clock.

### L5: live minute cache

Updated after each completed M1 candle and on material tick events. It contains
only what changed:

```text
latest completed M1 OHLC and tick volume
forming M1 state
forming M5/M15/M30/H1/H4 state
current bid/ask/spread and quote age
distance/status for at most three nearby active zones
active playbook ID and missing evidence
volume change versus completed-candle baselines
position thesis reference when a Qwen basket is open
```

The decision packet is assembled from this layer plus short references to L1,
L3, and L4. Raw long history is not retransmitted every minute.

### L6: position-thesis cache

Created from the validated entry decision and tied to exact position tickets:

```text
decision_id, playbook_id, direction, entry evidence, fill prices,
structural invalidation, targets, normal-oscillation description,
continuation condition, exit condition, next review event,
peak/adverse movement, cache epochs, and rule version
```

Qwen reviews the thesis on a completed M1 candle or named structural event.
Deterministic broker protection remains available between model calls.

## Cache epoch and provenance contract

Every derived cache object contains:

```json
{
  "schema_version": 1,
  "cache_type": "structural",
  "cache_epoch": "structural-XAUUSDr-20260803T120000Z-v1",
  "symbol": "XAUUSDr",
  "created_at_utc": "...",
  "valid_as_of_utc": "...",
  "source_start_utc": "...",
  "source_end_utc": "...",
  "source_hash": "sha256:...",
  "producer_version": "git:<commit>",
  "model_digest": "ollama:<digest>",
  "expires_at_utc": "...",
  "invalidated_at_utc": null,
  "invalidation_reason": null,
  "evidence_ids": []
}
```

Every Qwen request, response, proposal, fill, management decision, and closure
records the relevant epoch IDs. Cache replacement creates a new epoch; it never
silently mutates the evidence identity used by an earlier decision.

## Warm-up pipeline

Warm-up is a separate supervised process from minute decisions:

1. Start MT5 and Ollama; confirm demo account and symbol.
2. Load and pin `qwen-trading-v002:latest` with `keep_alive=-1`.
3. Fetch only missing L0 candle ranges from MT5.
4. Validate chronology, completeness, timeframe alignment, and closed status.
5. Build deterministic levels and session facts.
6. Run Qwen structural analysis over eight-week D1/H4 and two-week H1 context.
7. Run a separate session/day analysis over validated lower-timeframe context.
8. Build the H4 two-sided playbooks.
9. Run context-awareness validation against exact evidence IDs.
10. Publish one readiness manifest. Minute decisions remain disabled until the
    manifest is `ready`.

Warm-up does not train or alter LoRA weights. It creates explicit runtime
context. A restart rebuilds hot memory from SQLite, verifies hashes/freshness,
and recomputes only expired layers.

## Context-awareness validation system

“Fully context aware” cannot mean that Qwen states “I understand.” Operational
readiness means every hard data and evidence test passes.

### Gate A: raw-data integrity

- required lookback exists for each timeframe;
- no missing or duplicate completed candle keys;
- OHLC geometry is valid;
- timestamps are UTC and align to timeframe boundaries;
- forming candles are excluded from completed-history claims;
- latest quote/candle ages are within declared limits; and
- source hashes reproduce.

Any failure blocks readiness and produces a typed repair request.

### Gate B: derived-cache integrity

- every level cites existing completed candles;
- deterministic calculations reproduce exactly;
- structural cache source range/hash matches L0;
- playbook prices reference supplied levels;
- buy/sell geometry is valid;
- session facts match deterministic UTC boundaries; and
- all epochs are current and mutually compatible.

### Gate C: Qwen context challenge

After warm-up, Qwen receives a compact challenge and must return:

```text
cache epochs acknowledged
current D1/H4/H1 location
current H4 open and state
current session and Asia-range relation
nearest valid upper and lower zones
active playbook IDs
best conditional buy path
best conditional sell path
one unresolved fact
evidence IDs for every assertion
```

The validator checks IDs, prices, session, and states against the cache. Free
text confidence cannot compensate for a mismatch. Unsupported evidence,
missing sides, invented IDs, or stale epochs fail the gate.

### Gate D: counterfactual retrieval tests

The validator asks bounded questions whose answers are already in the cache:

- identify the source candle for a selected H4 level;
- distinguish the completed H1 candle from the forming H1 candle;
- locate price relative to the Asia high/low;
- state what would invalidate one buy and one sell playbook; and
- request the correct additional evidence when a supplied fact is omitted.

These tests verify retrieval and use, not prediction accuracy.

### Gate E: incremental-cache tests

- applying one new M1 candle changes only the expected live/session fields;
- replaying the same candle is idempotent;
- an M5 close rolls forming data into completed data exactly once;
- an H4 close expires the old playbooks and creates a new epoch;
- restart/rebuild produces identical hashes; and
- the minute path performs no full-history or full-JSONL scan.

### Readiness manifest

```json
{
  "status": "ready|blocked",
  "model_resident": true,
  "raw_data_valid": true,
  "structural_cache_valid": true,
  "level_cache_valid": true,
  "playbooks_valid": true,
  "session_cache_valid": true,
  "minute_delta_valid": true,
  "context_challenge_valid": true,
  "compatible_epochs": [],
  "validated_at_utc": "...",
  "failures": []
}
```

All boolean gates must be true. There is no average score that can hide one
failed hard requirement.

## Compact minute-decision protocol

Target: normally no more than 800 input tokens after the stable decision
contract. The exact budget is measured during replay and may be reduced only
if required evidence remains complete.

Example packet:

```json
{
  "decision_time_utc": "2026-08-03T13:16:00Z",
  "epochs": {
    "structure": "S-1200-v1",
    "session": "NYO-1300-v4",
    "playbook": "PB-1200-v1",
    "minute": "M1-1315-v1"
  },
  "quote": {"bid": 4043.86, "ask": 4043.94, "age_ms": 180},
  "closed_m1": {
    "id": "M1-1315",
    "o": 4044.44, "h": 4045.21, "l": 4043.31, "c": 4043.87,
    "tick_volume": 812
  },
  "forming": {
    "M5": {"o": 4042.14, "h": 4045.85, "l": 4041.37, "now": 4043.87},
    "M15": {"o": 4047.63, "h": 4053.82, "l": 4040.84, "now": 4043.87},
    "H1": {"o": 4047.63, "h": 4053.82, "l": 4040.84, "now": 4043.87},
    "H4": {"o": 4062.49, "h": 4064.80, "l": 4040.84, "now": 4043.87}
  },
  "volume": {"M1_ratio": 1.18, "M5_ratio": 1.42},
  "nearby_levels": [
    {"id": "M15_LOW", "price": 4043.16, "distance": -0.71, "state": "testing"},
    {"id": "M5_LOW", "price": 4040.84, "distance": -3.03, "state": "below"}
  ],
  "playbook": {
    "id": "PB-L03", "status": "testing",
    "buy_missing": "M1 rejection close",
    "sell_missing": "M5 accepted close below zone"
  },
  "position": null
}
```

The packet does not contain prior P&L, win rate, or directional outcome history.
Those remain in the separate research-learning loop.

## Qwen response and additional-data request

Normal response:

```json
{
  "action": "open|wait|skip|request_data",
  "direction": "buy|sell|none",
  "playbook_id": "PB-L03",
  "observed_trigger": "...",
  "invalidation_level_id": "...",
  "target_level_id": "...",
  "confidence": 0,
  "evidence_ids": [],
  "data_requests": []
}
```

Bounded request example:

```json
{
  "action": "request_data",
  "data_requests": [{
    "timeframe": "M1",
    "completed_bars": 20,
    "fields": ["ohlc", "tick_volume"],
    "reason": "compare two tests at active H4 zone"
  }]
}
```

Allowed timeframes, maximum bars, fields, and one additional round per decision
are enforced in code. A request cannot bypass freshness, session, or geometry
validation. The supplied evidence is attached to the same decision ID.

## Model residency

The current `keep_alive=-1` behavior is retained:

1. warm the model once during software startup;
2. verify the expected model digest;
3. keep weights resident indefinitely;
4. monitor Ollama residency and CPU/GPU allocation;
5. block minute decisions if the model was evicted or changed;
6. warm and rerun context validation after Ollama/model restart.

Do not send an empty generation every minute merely to simulate market memory.
Model residency avoids weight reload; the external cache provides market
memory. On an RTX 3090, validation should require the model to be fully GPU
resident before latency benchmarking.

## Latency instrumentation and budgets

Every minute cycle records:

```text
snapshot time
cache update duration
validation duration
prompt assembly duration and token count
Qwen load/prompt/evaluation durations
response validation duration
price at snapshot and response
price drift during inference
first-fill latency
```

Initial engineering targets for the minute path:

- incremental cache update: <= 50 ms;
- deterministic validation: <= 50 ms;
- packet assembly: <= 20 ms;
- no full-history/JSONL scan;
- post-Qwen response validation: <= 100 ms; and
- Qwen inference: benchmarked separately on current hardware and RTX 3090.

Inference is not declared acceptable from a hardware estimate. Replay measures
whether price drift during the complete snapshot-to-fill interval remains
compatible with the scalp entry geometry.

## Failure behavior

The minute decision is blocked when:

- a required cache layer is stale, missing, incompatible, or invalid;
- the latest expected candle or forming candle is missing during the active
  weekday data session. Historical discontinuities, rollover pauses, and
  off-session gaps are recorded but do not block readiness;
- model digest or cache epoch differs from the readiness manifest;
- Qwen cites nonexistent evidence;
- quote age or price drift exceeds the tested scalp tolerance;
- an additional-data request cannot be fulfilled; or
- model residency is lost.

The system reports the exact blocking gate and continues repairing/refreshing
context. It does not replace missing evidence with a generic trade.

## Implementation and promotion state

1. **Design approval:** completed by explicit user instruction.
2. **Cache implementation:** L0-L5 and incremental fixtures implemented;
   ready structure, session, playbook, level, and minute epochs feed entry Qwen.
3. **Validation implementation:** Gates A-E and the readiness manifest are
   implemented and passed against live MT5 demo data and the local Qwen model.
4. **Warm-up shadow:** deterministic refresh is active through the unified
   runtime; uncapped Qwen requalification is manual/off-hours after a model or
   contract change. Unchanged hashes and the qualification certificate are
   reused; failures remain retained in SQLite.
5. **Minute-packet execution input:** implemented with exact epoch
   acknowledgement and bounded evidence validation before a plan can be ready.
6. **Broker truth:** the daily filled-position cap is read from MT5 deals, never
   inferred from local proposal/execution logs.
7. **Paper scope:** integrated execution remains restricted to the verified MT5
   demo account; profitability still requires preregistered research.
