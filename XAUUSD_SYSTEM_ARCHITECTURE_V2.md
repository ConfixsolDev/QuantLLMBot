# XAUUSD Quantitative Trading System — Complete Architecture V2

> **SOLE ACTIVE ARCHITECTURE DOCUMENT — DO NOT OVERRIDE OR REPLACE.**
> Improve this file in place, preserve its V2 identity, and record material
> revisions in version control. Any other design, audit, research, or flow
> document is supporting evidence only and cannot redefine the live architecture.

**Architecture authority:** V2

**Original date:** 2026-08-17 | **Confirmed active:** 2026-08-19

**Model selection:** the single `DEFAULT_QWEN_MODEL` constant in `apps/qwen_trade_software/backend/runtime_config.py`

**Broker:** MetaTrader 5 demo account | **Instrument:** XAUUSD (Gold)

---

## Authority and System Ownership

This is the only active system-architecture document. The system has three
owned parts:

1. **Evidence:** immutable observations under `model_training/tick_data/`.
2. **Trading doctrine:** the lean live prompt sources `store/core_skill.md` and
   `store/sop.md`; they define trading judgment but do not redefine component
   ownership or runtime flow.
3. **Live code:** `apps/qwen_trade_software/`; code owns validation, risk,
   execution, reconciliation, and safety invariants.

Training and curriculum process remains governed exclusively by
`model_training/CURRICULUM_AND_DATA_PREP.md`. Research reports and audits may
challenge this architecture with evidence, but a proposed change becomes active
only when this V2 document and the corresponding tested code are revised
together.

### Protected Qwen decision-authority boundary

Qwen is the system's sole discretionary trading brain. Every normal trade
judgment—including directional commitment, whether an opportunity is worth
taking, selection among supplied valid levels, contextual entry qualification,
and routine position-management judgment—must remain Qwen-led. No database,
graph, detector, indicator, scoring engine, agent, retrieval library, or other
tool may replace Qwen, silently originate a trade thesis, or promote its output
into a trade decision.

All other components exist to let Qwen reason with better evidence. Python and
the data services calculate, validate, organize, relate, retrieve, compress,
and explain deterministic facts. They supply Qwen with freshness-aware,
time-bounded, provenance-carrying context across price, market structure,
zones, sessions, instruments, decisions, and outcomes. They may enforce the
existing hard safety, broker, risk, geometry, closed-candle, and execution
invariants, but those controls are gates and circuit breakers—not a competing
discretionary trader. They may veto an unsafe action or protect capital under
the exact approved fallback rules; they may not create an ordinary entry or
take over routine trade management while Qwen is available.

This authority boundary is binding and protected. Research, code, an agent, or
a newly installed capability cannot reinterpret it. It may be changed only
after the human owner explicitly asks for and approves that architectural
change, this V2 document is updated in place, and corresponding behavior is
implemented and tested. Until then, every proposed subsystem must answer one
question: how does it provide Qwen with clearer, more complete, and more
context-aware evidence without becoming the decision maker?

### Directional-bias invariant

The strategy maintains one directional conclusion for each opportunity:
`buy`, `sell`, or `wait`. The model may inspect evidence on both sides to avoid
confirmation bias, but it must not output a dual-direction trade assessment.
Only the committed directional bias can produce an execution plan. `wait` is a
valid conclusion when location or closed-candle validation is absent.

Directional bias is hierarchical, not a vote requiring identical candle
direction on every timeframe. The owning timeframe defines the thesis;
counter-direction movement on M15/M5/M1 may be the pullback into its planned
zone. That pullback becomes contradiction only after accepted failure of the
named invalidation on its owning timeframe.

### Canonical four-phase trading lifecycle

These phases are sequential and have distinct owners. A later phase may not
silently redo an earlier phase's job.

1. **Build and cache context.** A fresh Qwen session reads the immutable
   D1/H4/H1 evidence, locates the parent auction, and produces one directional
   conclusion: `buy`, `sell`, or `wait`. The resulting context is cached for
   the session and refreshed only when its evidence epoch changes.
2. **Map and remember the target zone.** The reviewer converts the committed
   bias into one structurally identified zone and the runtime persists its
   lifecycle. A zone is a location to observe, never an order by itself. Its
   lifetime is distinct from an entry-trigger lifetime: it may remain armed
   through a later price revisit within a bounded session window.
3. **Qualify the entry at the zone.** Code requires price inside the zone, a
   completed M1 probe-and-failure response in the planned direction, and price
   at the plan's optimal zone edge. Direction, zone, target and structural
   invalidation must already be fixed before M1 can trigger. M5 is the local
   map and optional strength evidence, not a routine second confirmation that
   delays entry until the move is exhausted. BOS/CHoCH, liquidity sweep, FVG
   and Fibonacci/OTE location remain supporting confluence, not standalone
   triggers. Only then may the executor submit the order.
   Expiry of the short Qwen/M1 signal does not delete the mapped zone. The
   executor keeps it armed for up to 15 minutes by default, but requires the
   latest completed M1 candle to provide a fresh probe-and-failure response at
   the revisit. It cancels immediately if live price reaches structural
   invalidation or the target before entry, or if a completed M1 candle accepts
   through the zone. The bounded window also prevents an obsolete synchronous
   zone watcher from blocking newer plans indefinitely.
4. **Protect the accepted trade.** Entry uses the planned structural
   invalidation as the broker SL and sizes volume from the configured risk
   budget. After fill, the trade reviewer manages level-to-level using closed
   M5/M15 evidence: close immediately when the immutable idea is confirmed
   invalid, tighten SL only behind newly formed structure, and extend TP only
   after confirmed continuation. It must never widen the stop, increase entry
   risk, average, reverse, or use profit/points as an exit shortcut.

The runtime, rather than the model, enforces every safety invariant in phases
3 and 4. Qwen supplies contextual judgment and named-level decisions; broker
state and deterministic validation remain authoritative.

### Persistent market-intelligence subsystem

The live cognition layer uses selective event sourcing and materialized views.
Every completed XAUUSD or DXY candle used by cognition is recorded as an
immutable, provenance-tagged event. A deterministic reducer maintains one
current projection per `(symbol,timeframe)` across D1/H4/H1/M30/M15/M5/M1.
Projections contain active leg, direction, transition, named invalidation,
unresolved condition, last evidence ID, and content-derived structure epoch.
They are rebuildable caches: replaying the event ledger must reproduce them.

The entry prompt receives a bounded projection plus recent deltas. DXY has its
own structure stream and contributes a relationship classification. DXY may
calibrate confidence and patience but has no execution authority over gold.
XAUUSD structure, mapped location, and completed XAUUSD trigger remain
mandatory.

#### Optional Neo4j temporal relationship projection

Neo4j is an optional, instrument-neutral projection of the SQLite evidence
ledger. It organizes completed market events by instrument, timeframe, UTC
time bucket, session phase, evidence provenance, and chronological succession
so Python can assemble a smaller and more traceable packet for Qwen. Its
purpose is to become a sophisticated data-provision and relationship layer:
it connects candles, structure, zones, tests, sweeps, BOS/CHoCH/MSS,
acceptance, invalidation, sessions, cross-market context, Qwen decisions, and
trade outcomes into evidence paths that clearly explain the market to Qwen.
It may rank retrieval relevance and expose historically similar, reviewed
episodes, but every returned relationship remains context—not a signal or
trade command.

Neo4j is never the trading brain. It must not choose buy/sell/wait, invent a
level, approve an entry, choose or change risk, submit an order, manage a
position, or replace Qwen under any normal condition. It is not the numerical
source of truth, a discretionary market judge, or an execution dependency.
Qwen remains the sole discretionary judgment layer; SQLite and immutable
source evidence remain authoritative for replayable facts, while runtime and
broker controls retain their existing safety and execution responsibilities.

The projection is populated through a transactional SQLite outbox and a
separate `market_graph_worker.py` process. Appending an intelligence event and
enqueuing its graph projection occur in one SQLite transaction. The graph
worker performs idempotent, parameterized batch writes using stable external
IDs, records a projection watermark and bounded retry state, and can rebuild
the entire graph from the ledger. Neo4j unavailability may make graph context
stale or unavailable, but it must never stop MT5 collection, deterministic
structure updates, Qwen's baseline SQLite context, order execution, trade
protection, or broker reconciliation.

The graph stores compact `MarketEvent`, `Instrument`, `Timeframe`,
`TimeBucket`, `SessionPhase`, and `MarketEpisode` nodes plus provenance and ordering
relationships. Candle OHLCV arrays, tick history, indicators, statistical
results, and broker truth stay in SQLite or their existing ledgers. Parent
timeframe membership is represented through shared deterministic time buckets
rather than materializing every possible parent-to-child candle edge. This
keeps the model extensible to additional Forex pairs without embedding
XAUUSD-specific labels or Cypher.

Each newly recorded Qwen entry or management response also emits a bounded
`qwen_decision` market event containing its decision state, model, confidence,
episode/proposal reference, deduplicated evidence IDs, acknowledged epochs,
and prompt/response hashes. Full prompt and raw response text stay in the
existing immutable decision logs; Neo4j stores neither large prompts nor an
independent copy of model truth. Decisions join the relevant `MarketEpisode`
through stable proposal or position references so later retrieval can follow
evidence -> decision -> episode without scanning unrelated JSONL files.
Execution start, fill, close, and skip records emit the same bounded event form
and update episode lifecycle status and outcome references. High-frequency path
monitor samples remain in their existing numerical logs and are deliberately
excluded from Neo4j.

Python owns all writes and allowlisted reads. The worker publishes a bounded,
atomically replaced graph-context snapshot and health file; the reviewer reads
that local snapshot instead of placing a Neo4j network call in the entry hot
path. Every graph record carries an external ID, UTC event time, evidence ID,
payload hash, schema version, and detector/source provenance. Session intervals
carry a versioned calendar identifier so daylight-saving or calendar changes
can be rebuilt rather than silently rewriting history.

Graph promotion is shadow-first. Initial success means complete idempotent
projection, deterministic replay, bounded retrieval, correct multi-symbol
isolation, lower evidence duplication, and acceptable projection lag. Better
trading performance remains a separate claim requiring counterfactual Qwen
replay and out-of-sample evaluation against the existing SQLite-only baseline.

Historical candle authority is convention-explicit. M1, M15, M30, and H1 retain
the maximum broker-available completed history with tick volume, real volume,
and spread metadata. H4 is not accepted directly from a broker: it is
deterministically aggregated from completed H1 candles on the 17:00
`America/New_York` Forex trading-day anchor, including DST transitions. H4
events carry `time_convention=new_york_1700_dst`, preventing incompatible broker
boundaries from silently coexisting.

The graph also maintains indexed `MarketLevel`, `LevelObservation`, and
`StructureSnapshot` projections from the authoritative deterministic context
cache. Levels retain symbol/timeframe, zone bounds, role, method, pattern, test
count, source evidence, first/last seen, and distinct-snapshot recurrence.
`evidence_confidence` is explicitly a Python-calculated data-quality score, not
a probability of profitable direction. Qwen consumes only the bounded latest
market-map snapshot and does not calculate or mutate graph state.

Temporal retrieval is bitemporal. Every market event is filtered by both
`event_time` (when it occurred) and `recorded_at` (when the system learned it),
so replay cannot see later backfills. Level facts live on immutable
`LevelObservation` snapshots and are selected as-of observation/valid time;
mutable `MarketLevel` nodes are indexes, not historical truth. All lower-frame
H4 containment uses versioned `new_york_1700_dst` buckets. Model selection stays
in runtime configuration: the graph supplies an evidence-bounded assessment
packet but never chooses, invokes, or replaces the decision model.

Qwen may identify a precise evidence gap and request only allowlisted,
read-only retrievals for completed candles, structure state/events, zones,
sessions, or DXY state. The application validates the phase-specific limits
defined below, audits every request and result, and returns neutral evidence.
Qwen never receives arbitrary SQL, Cypher, or database/broker write access.

#### Approved Neo4j market-memory and context contract

The graph worker must compile raw Neo4j relationships into one compact,
neutral, evidence-bounded packet; it must never pass the graph dump to Qwen.
The packet is ordered as: (1) market clock and sessions, (2) XAUUSD temporal
structure across D1/H4/H1/M30/M15/M5/M1, (3) three active zone positions,
(4) structure and tick-volume participation, (5) compressed DXY
cross-reference, and (6) conflicts, missing facts, and available RAG
questions. Its byte ceiling is configurable and must be measured during shadow
operation against the active model's context budget.

All XAUUSD timeframes remain visible because movement is temporal and
hierarchical rather than belonging to one isolated chart. D1/H4 describe the
parent driver, H1/M30/M15 describe development, and M5/M1 describe its local
expression and entry timing. Each row carries trend state, forming leg,
nearest location, acceptance/rejection state, participation evidence, evidence
freshness, and forming-candle time remaining and percent complete. Forming
candles are context only; only completed owning-timeframe candles may prove
structure. A rapid five-to-fifteen-minute move may therefore be explained as
the expression or completion of a higher-timeframe leg rather than mislabeled
as an M1-only event.

Session context separates the evolving current session from immutable closed
sessions. The current session carries time remaining and factual range,
location, acceptance/rejection, and participation state for Qwen to interpret
against D1/H4. The immediately previous session carries its completed bias,
high, low, range, participation profile, and final acceptance/rejection facts.
The previous two occurrences of the same named session contribute high, low,
and range only when relevant to repeated-price structure. Each completed
session receives one range/volatility-derived comparison tolerance at close;
that tolerance is locked and shared across timeframe comparisons. Exact-price
equality is never a market-structure rule.

Price zone is the primary context and memory anchor. Overlapping or nested
levels respected by multiple timeframes are consolidated into one price-area
zone with a core overlap, wider investigation band, contributing timeframes,
one highest owning timeframe, evidence by timeframe, and separate
owning-timeframe invalidations. The highest-timeframe validity dominates;
lower timeframes refine timing only. Coincident observations produced by one
market movement count as one episode, not multiple votes. Qwen receives
exactly three positions when available: the current or approaching focus zone,
nearest proven support below, and nearest proven resistance above. Ranking is
based on distance, highest owner, freshness, structural proof, session
relevance, participation, and room to the opposing zone. Zone history is a
neutral one-line sequence: formed, tests, latest response, current status, and
unresolved condition.

Volume fields are labeled as MT5 tick-volume participation proxies, never true
buy/sell volume. For the active zone and timeframe structure, the compiler may
provide bullish-candle average, bearish-candle average, their participation
ratio, current participation versus timeframe/session average, and whether
participation supports or contradicts the printed structure. Forming-candle
volume must be elapsed-time adjusted and cannot prove structure.

DXY uses the same temporal and participation vocabulary but is compressed to
four or five lines: D1/H4 driver, H1/M30/M15 path, M5/M1 immediate expression,
participation, and its neutral aligned/inverse/conflicting relationship to
XAUUSD. It is regenerated only when its evidence epoch changes and remains a
cross-reference without XAUUSD execution authority.

`OPTIONAL_NEO4J_RAG_EVIDENCE` is a separate block that Qwen may use or ignore.
Qwen selects only predefined question IDs: `ZONE_HISTORY`,
`RESOLVE_TIMEFRAME_CONFLICT`, `ACCEPTANCE_REJECTION_PROOF`,
`SIMILAR_MARKET_EPISODES`, `DXY_CROSS_REFERENCE`, and
`SESSION_STRUCTURE_HISTORY`. Requests carry question ID, symbol, as-of time,
focus-zone ID, and timeframes; both batch and sequential requests are allowed.
Combined uncached budgets are five questions during context warmup, four
during zone definition, and two during either trade decision or trade
management. Cached answers do not consume budget while the evidence epoch is
unchanged.

RAG responses always use the same non-directional fields: exact predefined
question, factual answer, supporting evidence, contradicting evidence,
unresolved facts, evidence IDs and timestamps, freshness, truncation, and
`execution_authority=false`. The broker must retrieve bullish and bearish
evidence symmetrically. It must not return a recommendation, preferred side,
confidence adjustment, or hidden decision relevance. Missing data returns
`insufficient_evidence`; Qwen decides whether to proceed, wait, hold, or exit.
The system logs the question, normalized failure reason, Qwen action and
rationale, alternative evidence, decision/trade reference, and later outcome.
Two occurrences of the same `question_id + missing evidence type + market
phase` fingerprint create an improvement candidate, never an automatic graph,
schema, strategy, or execution change.

Episodic retrieval starts from active price zone, structure, and regime and
returns a closest historical episode, a strong counterexample that resolved
differently, an alternative relevant path, and unresolved differences. It
does not produce a probability, automatic direction, or entry-context P&L
statistics. Semantic memory is likewise zone-relevant and consolidated: only
the single highest-relevance item matching the current zone, regime,
timeframe hierarchy, and structural condition may enter the packet.

Semantic memory lifecycle is `candidate -> probation -> established` or
`retired`. An agent may create and promote a candidate into seven-calendar-day
probation (approximately five trading days). During probation, simple unique
episode counts are used: if contradictory episodes equal or exceed supporting
episodes, the item automatically retires. Session is excluded from matching;
instrument, timeframe hierarchy, regime, and structural condition are used.
Nested multi-timeframe observations from one move count once. A retired item
may return as a new version with a fresh probation while preserving failure
history. Once an item survives probation it is human-locked: revision,
retirement, deletion, or reactivation requires explicit human supervision.
Lifecycle labels remain internal and do not bias Qwen.

This compiler and memory contract is promoted shadow-first. Until its packet
completeness, freshness, contradiction coverage, size, deterministic replay,
and usefulness are validated, SQLite remains Qwen's baseline context path.
Neo4j may become the primary context-memory provider only after that measured
promotion; even then Qwen remains the sole discretionary trading brain and
SQLite remains authoritative evidence.

Model qualification and evidence freshness are independent. Qualification
proves contract capability; it never suppresses projection refresh when a
structure epoch changes. Website and logs expose structure epochs, DXY and
relationship state, retrievals, prompt size, response latency, cited evidence,
acknowledged epochs, and the bounded raw JSON response.

#### Leakage-safe hourly structure supervision

Historical quality review runs once per completed XAUUSD H1 market hour and
reconstructs only facts knowable at that close across M1/M15/M30/H1/H4/D1.
It jointly records active levels and zones, confirmed structure, XAUUSD-DXY
relationship, parent-versus-child movement, and relative MT5 tick volume at
level interactions. Missing timeframe coverage and absent deterministic graph
labels are explicit defects; they must never be converted to a neutral view.

Forward candles may be used only by a separate post-hoc supervision envelope
to measure later direction, MFE/MAE, failed breaks, and context the live system
failed to represent. Every such event is immutable and carries
`mode=posthoc_supervised`, `uses_forward_visibility=true`,
`execution_authority=false`, `eligible_for_live_context=false`, and
`eligible_for_training=false`. Its compact `supervised_analysis` property may
be projected to Neo4j for explanation and website observability, while the full
dimension payload remains in SQLite. Live graph queries and Qwen decision
packets must exclude this event type. Promotion into training or live context
requires a separate leakage review, deterministic evaluation, and an approved
in-place revision of this architecture.

### Modular market-structure provider boundary

Market structure is represented as zones and normalized events rather than
exact-price equalities. The native closed-candle engine remains the sole live
authority. External libraries plug into `market_structure_providers.py` behind
one instrument-neutral schema and initially run only as shadow evidence:

- SciPy prominence swings, scikit-learn DBSCAN zones, TA-Lib candle evidence,
  and Smart Money Concepts comparisons may inspect the same completed M5 bars.
- SMC Toolkit, Ruptures, Statsmodels Markov models, VectorBT replay, and Stock
  Indicators ZigZag are research/offline providers. ZigZag is explicitly
  repainting evidence and can never validate a live entry.
- Provider availability, errors, directional agreement, delay, and eventual
  trade outcomes are measured separately. Missing packages and provider errors
  fail closed inside the provider boundary and cannot stop an MT5 cycle.
- No provider may influence execution until walk-forward, cross-instrument,
  closed-candle evaluation demonstrates improvement over the native baseline.
  Promotion changes require tested code and an in-place revision of this V2
  architecture; package installation alone never grants authority.

The scientific package set is isolated in a supported Python research runtime
(`requirements-structure.txt`) because the current MT5 runtime uses Python
3.14. Research output must cross the boundary as normalized, timestamped
events; the live process does not inherit the research environment's dependency
or latency risk.

The live process publishes one immutable sample per completed M5 candle to
`structure-shadow-input-YYYY-MM-DD.jsonl`, containing the same closed bars and
a frozen native direction. A separate Python 3.12/3.13 worker owns all external
imports and records external consensus plus per-provider decisions. After three
later completed M5 bars, it labels both native and external calls against the
same ATR-normalized forward-price outcome and maintains a comparison summary.
Shadow output is excluded from Qwen prompts, validators, and execution state;
its JSONL ledger and summary state are observability and research artifacts
only. Missing-provider health is `no_providers_available`, never a successful
market-structure observation.

---

## Part 1 — Full Problem Audit

Every problem identified through forensic analysis of code, logs, trade data, and doctrine. Each problem has: observed evidence, root cause, severity, and which system component is affected.

---

### P01 — No Regime Detection (Range vs Trend)
**Component:** Management guard + Entry reviewer  
**Severity:** CRITICAL — largest single source of lost profit  
**Evidence:** 9 trades on 2026-08-17. Market ranged 4392-4398 for trades 1-7, then trended up to 4404 for trades 8-9. System treated all identically: entered sell with M15/M30/H1 trend targets in a 6-point range, then continued selling into an uptrend.  
**Root cause:** No mechanism exists to classify the current market regime. The guard, the entry reviewer, and the management prompt all lack regime context. The system uses the same management rules regardless of whether price is oscillating in a range or displacing through structure.  
**Impact:** Range scalp would have yielded +$467. Hold-to-target would have lost -$1,117. Guard limited damage to -$21 but missed the scalp. Last two sells into the uptrend lost -$403.

---

### P02 — ATR Wiring Broken (Returns Null on Every Call)
**Component:** `market_atr.py` → `io_performance_log.py` → Ollama generate path  
**Severity:** CRITICAL — blocks regime detection entirely  
**Evidence:** Every `qwen-decisions` log entry shows: `"atr": {"ok": false, "atr_m1_51": null, "atr_m1_3": null, "atr_ratio_3_51": null, "bars": 0, "error": "mt5_not_connected:(-10004, 'No IPC connection')"}`  
**Root cause:** `snapshot_atr()` is called inside `io_performance_log.record_io()` which wraps every Ollama generate call. It calls `mt5.terminal_info()` directly, but the MT5 connection was established in a different process/thread. The IPC connection is process-local — `mt5.initialize()` must be called in the same process that calls `mt5.copy_rates_from_pos()`.  
**Actual call chain:** `reviewer.py` or `trade_management.py` → `review_shared.ollama_generate()` → `io_performance_log.record_io()` → `snapshot_atr()` → `mt5.terminal_info()` → **FAILS** because `mt5.initialize()` was called in the management process, but ATR snapshot may execute before connection or in a context where MT5 isn't ready.  
**Fix path:** Compute ATR from already-cached M1 bars in `market_context_cache` instead of making a fresh MT5 call. The cache already has 180+ M1 bars — more than enough for the 51-period Wilder ATR.

---

### P03 — Guard Pre-empts Qwen on Every Management Cycle
**Component:** `trade_management.py` line 1174 → `trade_manager.py` → `confirmed_management_guard()`  
**Severity:** CRITICAL — the guard replaces Qwen instead of backing it up  
**Evidence:** All 8 closes on 2026-08-17 were `decided_by: deterministic_guard`. Qwen was never called for those positions because the guard fires FIRST (line 1174) and skips the Qwen call entirely (line 1180: `if guard_review: ... else: ollama_generate`). The guard made 100% of close decisions today.  
**Root cause:** The guard is designed as a PRE-EMPTION mechanism — it checks before Qwen and short-circuits the model call if it fires. This means Qwen never sees the position when the guard has an opinion, and the guard's opinion is based on simple mechanical rules (M5_PREVIOUS_LOW touched + M1 against = close) without any regime awareness, displacement reading, or contextual judgment.  
**Fix path:** Invert the relationship. Qwen ALWAYS runs. The guard becomes a TIMEOUT SAFETY NET — it only fires when Qwen fails to respond for N minutes (e.g., Ollama down, GPU timeout, inference stuck). The guard's mechanical rules are a last resort to protect capital when the model is unavailable, not the primary management brain.

**What this changes in code (line 1174-1207 of trade_management.py):**
```python
# BEFORE: guard pre-empts Qwen
guard_review = confirmed_management_guard(facts)
if guard_review:
    # Qwen NEVER runs
    parsed_review = guard_review
else:
    # Qwen runs only when guard didn't fire
    result = ollama_generate(prompt, ...)

# AFTER: Qwen always runs, guard is timeout fallback
try:
    result = ollama_generate(prompt, timeout=MANAGEMENT_TIMEOUT)
    parsed_review = json.loads(result["response"])
except (TimeoutError, OllamaError):
    # Qwen failed — guard steps in as safety net
    guard_review = confirmed_management_guard(facts)
    if guard_review:
        parsed_review = guard_review
    else:
        parsed_review = {"action": "hold", "summary": "Qwen timeout, guard found no exit signal."}
```

---

### P04 — Guard Closes on Bounce-Back, Not at Favorable Level
**Component:** `trade_manager.py` → `confirmed_management_guard()` at line 240  
**Severity:** HIGH — direct profit loss in ranging markets  
**Evidence:** Trade 5 (061458): peaked at 4392.775 (+$174), guard fired at 4395.968 (+$14) — 3.2 points and $160 given back. Guard waited for M1 to close AGAINST the position (the bounce-back) before firing.  
**Root cause:** The guard requires `latest_against` (M1 closes against position direction) before considering any close. This is correct for trend management but wrong for range scalping. However, per revised architecture (P03), this is now Qwen's problem to solve — the guard should NOT be making this timing decision at all.  
**Fix path:** Qwen receives regime_context (including range detection, ATR, displacement) and decides the correct close timing. In range: Qwen closes at the favorable level while M1 is still favorable. In trend: Qwen holds through M5 noise. The guard's bounce-back timing problem disappears because the guard no longer makes routine management decisions.

---

### P05 — No Displacement Detection
**Component:** Missing entirely from the system  
**Severity:** HIGH — critical for regime transition detection  
**Evidence:** At ~06:25 UTC, an M5 candle with body ~2.1 points closed through the range top (4398) with a full body. This was a displacement candle — institutional commitment breaking the range. The system had no way to detect this transition.  
**Root cause:** No code exists to measure candle body size relative to ATR, check body-to-range ratio (commitment), or determine whether a displacement interacted with a mapped level. The system tracks candle direction (up/down) but not the quality/strength of the move.  
**Fix path:** New `displacement.py` — compute body/ATR ratio, body percentage, displacement-at-level detection. Supply to both guard and Qwen.

---

### P06 — No Swing Sequence Tracking
**Component:** `live_mapped_levels.py` detects swings but doesn't classify the pattern  
**Severity:** MEDIUM-HIGH — needed for regime detection  
**Evidence:** The fractal swing detection in `live_mapped_levels.py` (`fractal_swings()`) finds individual swing highs and lows, but doesn't track whether the sequence is HH-HL (uptrend), LH-LL (downtrend), or mixed (range). This classification is fundamental to regime detection.  
**Root cause:** `live_mapped_levels.py` was built for zone detection and visit counting, not for directional sequence analysis. The swing data exists but isn't analyzed for pattern.  
**Fix path:** Add `classify_swing_sequence()` to `live_mapped_levels.py` — analyze the last 4-6 swings for HH/HL/LH/LL pattern.

---

### P07 — Stale Mapped Trade Levels
**Component:** `mapped_trade_levels.json` → `market_context_cache.py` → `trade_management.py`  
**Severity:** MEDIUM — context pollution, wastes model tokens  
**Evidence:** `mapped_trade_levels.json` mapped 2026-08-13 contains 11 levels from 4348.892 to 4406.446. Current price is ~4395-4398. Levels at 4349-4369 are 25-45 points below — completely irrelevant. They waste context tokens and can confuse the model.  
**Root cause:** No staleness filter or distance filter exists. Once mapped, levels persist until manually updated. The JSON has no `valid_until` field.  
**Fix path:** Distance filter in `_mapped_trade_level_prices()` — drop any level > 30 points from current price. Simple, self-maintaining, ~5 lines.

---

### P08 — confidence=0 with status=ready
**Component:** `reviewer.py` (entry reviewer) → Qwen model output  
**Severity:** MEDIUM — wastes execution cycles, potential bad fills  
**Evidence:** Model fires `invariant:ready_with_zero_confidence` repeatedly — says ready to trade with zero confidence. This generates proposals that either get blocked by MIN_ENTRY_CONFIDENCE=51 or, if the invariant check is bypassed, result in low-quality entries.  
**Root cause:** Training data calibration issue. The v1.9 SOP incident (documented in sop.md comments) shows that a prohibition-list format caused confidence collapse to zero. v1.10 restored the positive-instruction format, but confidence=0 with ready status persists in some conditions. Possibly: the model doesn't know how to express conviction on setups that are valid but unfamiliar (novel displacement patterns, regime transitions).  
**Fix path:** Curriculum fix — add training examples with calibrated confidence scores. Also: regime-aware confidence (confidence should reflect regime clarity, not just setup quality).

---

### P09 — H4 Theses Always Rejected (No Structural Brackets)
**Component:** `paper_executor.py` → `_refuse_htf_micro_bracket()` + `broker_bracket_from_plan()`  
**Severity:** MEDIUM — system generates H4 ideas but can never execute them  
**Evidence:** 14 `htf_thesis_micro_bracket` rejections on 2026-08-17 alone. Model keeps proposing H4 theses with invalidation points that require 10-20 point stops, but the bracket system can't accommodate them (fixed $3/$5 fallback is rejected for HTF).  
**Root cause:** Two-sided problem. (1) The model generates H4 theses without H4-scale invalidation (uses M15 structure for H4 ideas). (2) Even when structural brackets exist, the geometry rejects because the stop is too wide for fixed lot sizing.  
**Fix path:** Curriculum — teach Qwen that H4 thesis needs H4-scale stop behind the H4 swing that proves the idea wrong. If the model can't identify a clear H4 invalidation, it should skip, not propose.

---

### P10 — Dashboard Shows All Python Levels (Not Qwen-Qualified)
**Component:** `trade_management.py` → `chart_levels()` → frontend  
**Severity:** MEDIUM — operator confusion, noise  
**Evidence:** Dashboard shows 30+ levels including every M1/M5/M15/M30/H1/H4 PREVIOUS_HIGH/LOW, CURRENT_OPEN, pivots, live mapped levels, and operator-mapped levels. No distinction between levels Qwen actually used in a decision and levels Python computed mechanically.  
**Root cause:** `chart_levels()` merges everything and returns a flat dict. No tracking of which levels Qwen cited in entry or management decisions.  
**Fix path:** Track `decision_level_refs` — which level_ids Qwen cited. Dashboard separates qualified (Qwen-cited) from candidate (Python-detected). Frontend renders qualified prominently, candidates dimmed.

---

### P11 — No LTF Structural Confirmation Before Entry
**Component:** `paper_executor.py` → entry fill logic  
**Severity:** MEDIUM — entries fill on first tick inside zone  
**Status:** RESOLVED — 2026-08-19
**Evidence:** Once Qwen says "ready" and price enters `inside_zone`, the executor fills immediately. No requirement for a rejection candle, CHoCH, or any structural proof that the zone is holding.  
**Root cause:** The entry flow was Qwen direction → inside_zone price → fill; the doctrine's lower-timeframe failure test was not enforced in code.
**Resolution:** `m1_failure_at_zone()` is now a deterministic entry gate. After Qwen says ready and price reaches the optimal edge inside the approved zone, the executor requires a completed M1 probe that failed to close through the zone. M5 remains local-map and optional strength evidence rather than a routine delay.

---

### P12 — live_map Field Unknown to v004 Model
**Component:** `market_context_cache.py` → entry context → Qwen prompt  
**Severity:** LOW-MEDIUM — injected data the model can't interpret  
**Evidence:** `live_map` packet (from `live_mapped_levels.live_map_packet()`) is injected into the entry context, but v004 was never trained on this field. The model sees zone data with `near`, `double_top`, `double_bottom` but has no curriculum for interpreting it.  
**Root cause:** Feature was added to code before training data was updated. Standard feature-training gap.  
**Fix path:** Add live_map examples to curriculum (stage_05 and beyond). Until then, the data doesn't hurt (model ignores unknown fields in JSON) but wastes context tokens.

---

### P13 — Build Drift Active
**Component:** `build_manifest.py` → all processes  
**Severity:** LOW — measurement contamination  
**Evidence:** `build:drift :: running build 53ce2c385f74 differs from frozen 702bfeff3f84 in 9 place(s)`. Results cannot be pooled with frozen-build baseline.  
**Root cause:** 9 files modified without re-freezing the build hash. Expected during development but must be resolved before any performance measurement is meaningful.  
**Fix path:** Re-freeze after completing and validating each piece. Clear drift explicitly.

---

### P14 — reached_favorable_level_refs Uses Peak Tick Price, Not Closed Candle
**Component:** `trade_manager.py` → `build_management_facts()` lines 156-165  
**Severity:** LOW-MEDIUM — wick touches mark levels as "reached"  
**Evidence:** `reached_favorable` populates when `peak_price` (tick-level) crosses any level price. A wick that briefly touches a level and retracts still marks it as "reached" forever, even if no M1 candle ever closed beyond it.  
**Root cause:** `peak_price` comes from the execution monitor's tick-by-tick tracking. The comparison at line 159-163 is `entry < level <= peak_price` — pure price crossing, not candle close.  
**Nuance:** In RANGE mode with scalp_guard, this is actually fine — you want to TP when price REACHES the level (even intrabar). In TREND mode with rejection_guard, you want closed-candle confirmation. Another case where regime determines the correct behavior.  
**Fix path:** Regime-dependent: scalp_guard uses peak_price (current behavior). rejection_guard adds a closed-M1 requirement for `reached_favorable`.

---

### P15 — Entry Target Mode Not Informed by Regime
**Component:** `reviewer.py` → Qwen entry decision  
**Severity:** MEDIUM — entries aim for wrong targets  
**Status:** RESOLVED — 2026-08-20, with range-boundary consistency hardening  
**Evidence:** In the 4392-4398 range, all 9 entries had targets at 4387, 4382, 4376, 4369, 4364 — all below the range. These are HTF trend targets that were never going to be reached in a 6-point range.  
**Root cause:** Qwen picks targets from M15/H1/H4 structural levels because the entry prompt asks for `first_target` and `runner_target` without regime context. The model doesn't know "this is a range — target the M5 boundary, not the H1 level."  
**Fix path:** Supply regime_context in entry prompt. In range, Qwen should output `target_mode: scalp` with `first_target` at the opposing M5 boundary. Curriculum teaches this mapping.

**Resolution:** Runtime stamps the deterministic regime target mode and keeps a
valid structured `target_mode` authoritative over stale reason prose. The range
outer-edge veto is enforced only when `range_support` and `range_resistance`
were actually detected. A mixed-swing range hint with `range_detected=false`
and null boundaries cannot label a mapped-zone entry as
`range_middle_or_wrong_edge`; it records `range_edge_check=unavailable` and
leaves the mapped-zone plus closed-M1 failure gates authoritative. Replay of
2026-08-20 found 83 false range-edge blocks with missing boundaries and 46
`missing_target_mode` reasons whose structured mode was already `scalp`.

---

### P16 — Loss Cooldown Can't Fix Structural Defects
**Component:** `paper_runner.py` → `LOSS_COOLDOWN_SECONDS`  
**Severity:** LOW — already addressed (30min → 5min)  
**Evidence:** The Asia losses (-147, -162) were H4 thesis + $3 stop — a structural geometry mismatch. No cooldown duration fixes that; the entry should never have been taken. Cooldown was 30 minutes, blocking good follow-through. Now 5 minutes with bypass at confidence≥82 and R:R≥2.5.  
**Root cause:** Cooldown was treating symptoms (rapid re-entry after loss) instead of the disease (bad entry geometry). Already addressed by: (a) shortening cooldown, (b) `_refuse_htf_micro_bracket()`, (c) `inside_zone` only entry policy.  
**Status:** PARTIALLY FIXED. Entry policy and HTF rejection handle the structural side. Cooldown is now reasonable.

---

### P17 — Entry Policy Was Accepting favorable_outside
**Component:** `paper_executor.py` → `entry_price_allowed()`  
**Severity:** Was CRITICAL, now FIXED  
**Evidence:** Asia losses were fills at prices below the hunt zone. `favorable_outside` allowed execution when price was "better than the zone" but actually structurally wrong.  
**Status:** FIXED in current changeset. `entry_price_allowed()` now returns True only for `inside_zone`.

---

### P18 — HTF Micro Brackets
**Component:** `paper_executor.py` → `_refuse_htf_micro_bracket()`  
**Severity:** Was CRITICAL, now FIXED  
**Evidence:** H4 thesis with $3 fixed stop → structural mismatch → -147, -162 losses.  
**Status:** FIXED in current changeset. H1/H4/D1 timeframes reject fixed micro brackets entirely.

---

### P19 — No Range Detection Infrastructure
**Component:** Missing entirely  
**Severity:** HIGH — prerequisite for regime-aware management  
**Evidence:** No code identifies when price is oscillating between two known levels. The system can detect individual levels (via pivot math and fractal swings) but never asks "is price bouncing between these two levels?"  
**Root cause:** Range detection requires combining: M5 swing highs/lows + clustering + bounce counting + width vs ATR. The pieces exist (swings in live_mapped_levels, ATR in market_atr) but were never combined.  
**Fix path:** New `range_detector.py` or extension to `live_mapped_levels.py` — identify range boundaries, count bounces, measure width vs ATR.

---

### P20 — No Transition Detection (Range↔Trend)
**Component:** Missing entirely  
**Severity:** HIGH — transitions are where money is made or lost  
**Evidence:** The 06:25 displacement candle that broke the range top was a range→trend transition. Trades 8-9 entered sell into the new uptrend. No mechanism flagged the transition.  
**Root cause:** Detecting transitions requires temporal change detection: "ATR was X, now it's Y" + "displacement just occurred at a boundary" + "swing pattern just changed." This is a state machine, not a snapshot.  
**Fix path:** Track `prev_regime` and `prev_atr_ratio`. When regime_hint changes, flag transition. Supply `regime_transition` field in context. Qwen learns to handle transitions explicitly.

---

## Part 2 — Solution Architecture

### 2.1 System Flow (Current → Target)

```
CURRENT FLOW:
┌────────────┐     ┌────────────┐     ┌───────────┐     ┌──────────────┐
│ Session     │────▶│ Entry      │────▶│ Executor  │────▶│ Management   │
│ Planner     │     │ Reviewer   │     │           │     │              │
│             │     │ (Qwen)     │     │ inside_   │     │ Guard OR     │
│ H4/H1/D1   │     │ 30s cycle  │     │ zone fill │     │ Qwen 30s     │
│ direction   │     │            │     │           │     │ cycle        │
└────────────┘     └────────────┘     └───────────┘     └──────────────┘
       │                 │                  │                   │
       │            No regime          No rejection       Guard fires on
       │            context            gate               ANY level with
       │                               No regime         M5_PREVIOUS_LOW
       │                               target mode       for all theses
       ▼                 ▼                  ▼                   ▼
  WORKS FINE        ENTERS WRONG      FILLS ON           CLOSES AT
                    TARGET MODE       FIRST TOUCH        WRONG TIME

TARGET FLOW:
┌────────────┐     ┌────────────┐     ┌───────────┐     ┌──────────────┐
│ Session     │────▶│ REGIME     │────▶│ Entry     │────▶│ Executor     │──▶│ Management │
│ Planner     │     │ DETECTOR   │     │ Reviewer  │     │              │   │            │
│             │     │ (Python)   │     │ (Qwen +   │     │ inside_zone  │   │ Regime-    │
│ H4/H1/D1   │     │            │     │ regime)   │     │ + M1 reject  │   │ routed     │
│ direction   │     │ ATR+disp+  │     │           │     │ + regime     │   │ guard      │
│             │     │ swing+range│     │ Regime-   │     │ target mode  │   │ + Qwen     │
└────────────┘     └────────────┘     │ aware     │     └──────────────┘   │ + regime   │
                         │            │ targets   │                        │ context    │
                         │            └───────────┘                        └────────────┘
                         │
                    Produces:
                    - regime_hint
                    - regime_context packet
                    - displacement data
                    - swing sequence
                    - range boundaries
```

### 2.2 New Components

#### Component A: `regime_engine.py` (NEW — ~200 lines)

Central regime computation. Runs on every M1 close. Consumes data from ATR, displacement, swings, and range detection. Produces the `regime_context` packet that feeds both the guard and Qwen.

```python
"""Regime detection engine — the combined signal.

ATR ratio alone tells volatility state.
Displacement tells commitment at levels.
Swing sequence tells directional structure.
Range detection tells oscillation boundaries.

A pro trader reads all four as one signal. This module combines them.
Python produces the hint. Qwen judges whether the hint is right.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class RegimeContext:
    """Immutable regime snapshot for one review cycle."""
    # ATR
    atr_m1_51: float | None
    atr_m1_3: float | None
    atr_ratio_3_51: float | None

    # Displacement (latest M5 candle)
    m5_body_atr_ratio: float | None     # body / ATR_51
    m5_body_pct: float | None           # body / range (commitment)
    displacement_at_level: str | None   # level_id if displacement at a level
    displacement_through: bool | None   # True=acceptance, False=rejection

    # Swing sequence
    m5_swing_pattern: str               # "hh_hl" | "lh_ll" | "mixed" | "insufficient"
    m15_swing_pattern: str

    # Range (if detected)
    range_detected: bool
    range_resistance: float | None
    range_support: float | None
    range_width: float | None
    range_width_atr: float | None
    range_bounces: int

    # Regime
    regime_hint: str                    # "range" | "trend" | "breakout" | "exhaustion" | "unknown"
    prev_regime_hint: str | None        # previous cycle's hint
    regime_transition: bool             # True if regime just changed


def compute_regime(
    atr_m1_51: float | None,
    atr_m1_3: float | None,
    m5_candle: dict | None,
    m5_swings: list[dict],
    m15_swings: list[dict],
    current_price: float,
    levels: dict[str, float],
    prev_regime: str | None = None,
    prev_atr_ratio: float | None = None,
) -> RegimeContext:
    """Compute regime from combined signals. Called every M1 close."""

    # --- ATR ---
    atr_ratio = None
    if atr_m1_51 and atr_m1_3 and atr_m1_51 > 0:
        atr_ratio = round(atr_m1_3 / atr_m1_51, 4)

    # --- Displacement ---
    m5_body_atr = None
    m5_body_pct = None
    disp_level = None
    disp_through = None
    if m5_candle and atr_m1_51 and atr_m1_51 > 0:
        body = abs(m5_candle["close"] - m5_candle["open"])
        rng = m5_candle["high"] - m5_candle["low"]
        m5_body_atr = round(body / atr_m1_51, 4)
        m5_body_pct = round(body / rng, 4) if rng > 0 else 0

        # Did displacement interact with a level?
        if m5_body_pct > 0.65 and m5_body_atr > 0.8:
            direction = "up" if m5_candle["close"] > m5_candle["open"] else "down"
            for lid, price in levels.items():
                if m5_candle["low"] <= price <= m5_candle["high"]:
                    disp_level = lid
                    disp_through = (
                        m5_candle["close"] > price if direction == "up"
                        else m5_candle["close"] < price
                    )
                    break

    # --- Swing sequence ---
    m5_pattern = _classify_swings(m5_swings)
    m15_pattern = _classify_swings(m15_swings)

    # --- Range detection ---
    range_info = _detect_range(m5_swings, current_price, atr_m1_51)

    # --- Regime hint ---
    hint = _compute_hint(
        atr_ratio, m5_body_atr, m5_pattern, range_info,
        disp_through, prev_atr_ratio, prev_regime,
    )
    transition = prev_regime is not None and hint != prev_regime

    return RegimeContext(
        atr_m1_51=atr_m1_51,
        atr_m1_3=atr_m1_3,
        atr_ratio_3_51=atr_ratio,
        m5_body_atr_ratio=m5_body_atr,
        m5_body_pct=m5_body_pct,
        displacement_at_level=disp_level,
        displacement_through=disp_through,
        m5_swing_pattern=m5_pattern,
        m15_swing_pattern=m15_pattern,
        range_detected=range_info is not None,
        range_resistance=range_info["resistance"] if range_info else None,
        range_support=range_info["support"] if range_info else None,
        range_width=range_info["width"] if range_info else None,
        range_width_atr=range_info["width_atr"] if range_info else None,
        range_bounces=range_info["bounces"] if range_info else 0,
        regime_hint=hint,
        prev_regime_hint=prev_regime,
        regime_transition=transition,
    )


def _classify_swings(swings: list[dict], lookback: int = 6) -> str:
    recent = swings[-lookback:] if len(swings) >= lookback else swings
    if len(recent) < 4:
        return "insufficient"
    highs = [s for s in recent if s.get("type") == "high"]
    lows = [s for s in recent if s.get("type") == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"
    hh = highs[-1]["price"] > highs[-2]["price"]
    hl = lows[-1]["price"] > lows[-2]["price"]
    if hh and hl:
        return "hh_hl"
    if not hh and not hl:
        return "lh_ll"
    return "mixed"


def _detect_range(
    m5_swings: list[dict],
    current_price: float,
    atr_slow: float | None,
    min_bounces: int = 3,
) -> dict | None:
    if len(m5_swings) < 4 or not atr_slow or atr_slow <= 0:
        return None
    recent_highs = [s["price"] for s in m5_swings[-8:] if s.get("type") == "high"]
    recent_lows = [s["price"] for s in m5_swings[-8:] if s.get("type") == "low"]
    if len(recent_highs) < 2 or len(recent_lows) < 2:
        return None
    resistance = sum(recent_highs) / len(recent_highs)
    support = sum(recent_lows) / len(recent_lows)
    width = resistance - support
    if width <= 0:
        return None
    width_atr = width / atr_slow
    bounces = len(recent_highs) + len(recent_lows)
    inside = support - atr_slow <= current_price <= resistance + atr_slow
    if bounces >= min_bounces and 2.0 < width_atr < 12.0 and inside:
        return {
            "resistance": round(resistance, 3),
            "support": round(support, 3),
            "width": round(width, 3),
            "width_atr": round(width_atr, 2),
            "bounces": bounces,
        }
    return None


def _compute_hint(
    atr_ratio: float | None,
    displacement_ratio: float | None,
    swing_pattern: str,
    range_info: dict | None,
    displacement_through: bool | None,
    prev_atr_ratio: float | None,
    prev_regime: str | None,
) -> str:
    if atr_ratio is None:
        return "unknown"

    # Breakout: was compressed, now expanding with displacement through a level
    if (prev_atr_ratio is not None and prev_atr_ratio < 0.8
            and atr_ratio > 1.2
            and displacement_ratio is not None and displacement_ratio > 1.0
            and displacement_through is True):
        return "breakout"

    # Exhaustion: was expanding, now compressing, displacement rejected at level
    if (prev_atr_ratio is not None and prev_atr_ratio > 1.2
            and atr_ratio < 1.0
            and displacement_through is False):
        return "exhaustion"

    # Trend: expanding or recent displacement + consistent directional swings
    if swing_pattern in ("hh_hl", "lh_ll"):
        if atr_ratio > 1.0:
            return "trend"
        if displacement_ratio is not None and displacement_ratio > 1.0:
            return "trend"

    # Range: price inside detected range + mixed swings
    if range_info is not None and swing_pattern == "mixed":
        return "range"

    # Fallback: use swings
    if swing_pattern == "mixed":
        return "range"
    if swing_pattern in ("hh_hl", "lh_ll"):
        return "trend"

    return "unknown"
```

#### Component B: ATR from Cache (Fix for P02)

Replace the broken `snapshot_atr()` MT5 call with cache-based computation:

```python
# In market_context_cache.py or a new atr_cache.py

def snapshot_atr_from_cache(
    m1_bars: list[dict],
    symbol: str | None = None,
) -> dict:
    """Compute ATR from already-cached M1 bars. No MT5 call needed.

    m1_bars: list of dicts with 'high', 'low', 'close' keys,
             ordered oldest→newest, from the market_context_cache.
    """
    from market_atr import atr_from_rates, ATR_M1_PERIODS

    out = {
        "timeframe": "M1",
        "periods": list(ATR_M1_PERIODS),
        "symbol": symbol,
        "ok": False,
        "atr_m1_51": None,
        "atr_m1_3": None,
        "atr_ratio_3_51": None,
        "bars": len(m1_bars),
        "source": "cache",  # distinguishes from MT5 direct
        "error": None,
    }
    need = max(ATR_M1_PERIODS) + 1
    if len(m1_bars) < need:
        out["error"] = f"insufficient_cached_bars:{len(m1_bars)}<{need}"
        return out

    computed = atr_from_rates(m1_bars, periods=ATR_M1_PERIODS)
    out.update({
        "atr_m1_51": computed.get("atr_m1_51"),
        "atr_m1_3": computed.get("atr_m1_3"),
        "atr_ratio_3_51": computed.get("atr_ratio_3_51"),
        "bars": computed.get("bars", len(m1_bars)),
        "last_closed_time_utc": computed.get("last_closed_time_utc"),
        "ok": computed.get("atr_m1_51") is not None,
    })
    return out
```

**Wiring change in `io_performance_log.py`:**
```python
# BEFORE (line 220):
atr_snapshot = snapshot_atr()

# AFTER:
from market_context_cache import get_cached_m1_bars
m1_bars = get_cached_m1_bars(symbol)  # returns list from cache, no MT5 call
if m1_bars:
    atr_snapshot = snapshot_atr_from_cache(m1_bars, symbol)
else:
    atr_snapshot = {"ok": False, "error": "no_cached_m1_bars"}
```

#### Component C: Displacement Detection (Fix for P05)

```python
# displacement.py — ~80 lines

def candle_displacement(
    candle: dict,
    atr_slow: float | None,
) -> dict:
    """Measure a single candle's displacement relative to ATR baseline."""
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    body = abs(c - o)
    full_range = h - l
    body_pct = body / full_range if full_range > 0 else 0.0
    body_atr = body / atr_slow if atr_slow and atr_slow > 0 else None

    return {
        "body": round(body, 3),
        "range": round(full_range, 3),
        "body_pct": round(body_pct, 3),
        "body_atr_ratio": round(body_atr, 4) if body_atr else None,
        "is_displacement": (
            body_pct > 0.65
            and body_atr is not None
            and body_atr > 0.8
        ),
        "direction": "up" if c > o else "down",
    }


def displacement_at_level(
    candle: dict,
    levels: dict[str, float],
    atr_slow: float | None,
) -> dict | None:
    """Check if a displacement candle interacted with a mapped level."""
    disp = candle_displacement(candle, atr_slow)
    if not disp["is_displacement"]:
        return None

    for level_id, price in levels.items():
        price = float(price)
        if candle["low"] <= price <= candle["high"]:
            through = (
                candle["close"] > price if disp["direction"] == "up"
                else candle["close"] < price
            )
            return {
                **disp,
                "level_id": level_id,
                "level_price": price,
                "through": through,
            }
    return None
```

#### Component D: Guard as Timeout Safety Net (Fix for P03, P04)

**Design principle:** Qwen owns ALL trade management decisions. The guard is a circuit breaker that protects capital when Qwen is unavailable.

The guard fires ONLY when:
1. **Hard invalidation** — M1+M5 both closed beyond planned_invalidation (always active, even if Qwen is responsive — this is a stop-loss, not a management decision)
2. **Qwen timeout** — Ollama failed to respond for N consecutive management cycles (model down, GPU crashed, inference stuck)

Everything else — noise levels, M5_PREVIOUS_LOW, regime-aware timing, scalp vs hold — is Qwen's job. Qwen receives the full regime_context and makes the judgment call.

```python
# In trade_manager.py — guard becomes minimal safety net

# How many consecutive failed Qwen cycles before guard takes over
GUARD_TIMEOUT_CYCLES = 3  # 3 × 30s = 90 seconds without Qwen

def safety_guard(facts: dict) -> dict | None:
    """Hard stop-loss only. Fires regardless of Qwen availability."""
    candles = facts.get("completed_candles", [])
    by_id = {r.get("evidence_id"): r for r in candles}
    m1_id = facts.get("latest_completed_m1")
    m5_id = facts.get("latest_completed_m5")
    m1 = by_id.get(m1_id)
    m5 = by_id.get(m5_id)
    if not m1 or not m5:
        return None

    side = facts["position"]["side"]
    inv = facts.get("level_references", {}).get("planned_invalidation")
    if inv and _closed_beyond(m1, float(inv["price"]), side, False) \
           and _closed_beyond(m5, float(inv["price"]), side, False):
        return {
            "action": "close",
            "thesis_state": "invalidated",
            "decision_level_ref": "planned_invalidation",
            "confirmation_type": "thesis_invalidation_confirmed",
            "confirmation_evidence_ids": [m1_id, m5_id],
            "close_confirmed": True,
            "summary": "Hard invalidation: M1+M5 closed beyond stop.",
        }
    return None


def timeout_guard(facts: dict) -> dict | None:
    """Emergency close when Qwen has been unresponsive for too long.

    This is the LAST RESORT — it uses the old mechanical logic
    (reached level + M1 against + M5 confirms) because that's
    better than no management at all when the model is down.
    """
    # Uses the existing confirmed_management_guard logic
    # but only fires after GUARD_TIMEOUT_CYCLES consecutive
    # Qwen failures. Tracked in the management loop.
    return _legacy_confirmed_guard(facts)
```

**New management loop flow (trade_management.py line 1174+):**
```python
    # Step 1: Hard invalidation — always check, even before Qwen
    hard_stop = safety_guard(facts)
    if hard_stop:
        parsed_review = hard_stop
        model_used = "safety_guard_invalidation"
    else:
        # Step 2: Qwen manages the position (ALWAYS attempted)
        try:
            prompt = build_management_prompt(facts, STORE_ROOT, regime_context)
            result = ollama_generate(
                prompt, timeout=None, num_predict=512, num_ctx=4096,
                format_schema=management_schema(facts),
            )
            raw_review = json.loads(result["response"])
            parsed_review, failures = validate_management_decision(raw_review, facts)
            CONSECUTIVE_QWEN_FAILURES[position.ticket] = 0  # reset on success
            model_used = MODEL

        except Exception as exc:
            # Step 3: Qwen failed — count consecutive failures
            ticket = position.ticket
            CONSECUTIVE_QWEN_FAILURES[ticket] = CONSECUTIVE_QWEN_FAILURES.get(ticket, 0) + 1
            failures_count = CONSECUTIVE_QWEN_FAILURES[ticket]

            if failures_count >= GUARD_TIMEOUT_CYCLES:
                # Qwen has been down for 90+ seconds — guard takes over
                guard_review = timeout_guard(facts)
                if guard_review:
                    parsed_review = guard_review
                    model_used = "timeout_guard"
                    logging.warning(
                        "Timeout guard activated: %d consecutive Qwen failures, ticket=%s",
                        failures_count, ticket,
                    )
                else:
                    parsed_review = {"action": "hold", "summary": f"Qwen down {failures_count} cycles, guard found no exit."}
                    model_used = "timeout_guard_hold"
            else:
                # Qwen failed but not long enough for guard — hold
                parsed_review = {"action": "hold", "summary": f"Qwen unavailable ({failures_count}/{GUARD_TIMEOUT_CYCLES}), holding."}
                model_used = "qwen_unavailable_hold"
                logging.warning("Qwen failure %d/%d for ticket=%s: %s", failures_count, GUARD_TIMEOUT_CYCLES, ticket, exc)
```

**Why this is better:**
- Qwen sees ALL levels including M5 noise and decides what matters in context
- Qwen receives regime_context and knows range vs trend
- Qwen can close at favorable level (scalp) or hold through noise (trend) based on judgment
- The guard only fires on hard invalidation (always) or total model failure (timeout)
- No more "guard closed 8/8 trades on M5_PREVIOUS_LOW while Qwen sat idle"

### 2.3 Data Flow Diagram

```
                    ┌─────────────────────┐
                    │   MT5 (MetaTrader)   │
                    │   XAUUSD tick data   │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │ market_context_cache │
                    │ M1-H4 bars cached   │
                    │ levels computed      │
                    │ entry context built  │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼───────┐  ┌────▼────┐  ┌────────▼────────┐
    │ ATR from cache  │  │ Fractal │  │ Displacement    │
    │ atr_m1_51/3     │  │ Swings  │  │ body/ATR ratio  │
    │ atr_ratio       │  │ Sequence│  │ at-level check  │
    └─────────┬───────┘  └────┬────┘  └────────┬────────┘
              │               │                │
              └───────────────┼────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   REGIME ENGINE   │
                    │                   │
                    │ range / trend /   │
                    │ breakout /        │
                    │ exhaustion        │
                    │                   │
                    │ regime_context    │
                    │ packet            │
                    └────────┬──────────┘
                             │
              ┌──────────────┼──────────────┐
              │                             │
    ┌─────────▼──────────┐       ┌──────────▼──────────┐
    │   ENTRY PATH       │       │   MANAGEMENT PATH   │
    │                    │       │                      │
    │ Qwen + regime →    │       │ Guard (regime-       │
    │ target_mode:       │       │ routed):             │
    │   range → scalp    │       │   range → scalp_    │
    │   trend → basket   │       │          guard      │
    │   breakout → hold  │       │   trend → rejection │
    │   exhaustion →     │       │          _guard     │
    │          scalp     │       │                      │
    │                    │       │ Qwen management +    │
    │ Entry gate:        │       │ regime_context       │
    │   inside_zone +    │       │                      │
    │   m1_failure_at_   │       │ regime_assessment    │
    │   zone (rejection) │       │ from Qwen (can       │
    │                    │       │ override hint)       │
    └────────────────────┘       └──────────────────────┘
```

---

## Part 3 — Problem → Solution Mapping

| # | Problem | Solution | New Code | Files Changed | Lines Est. |
|---|---------|----------|----------|---------------|------------|
| P01 | No regime detection | `regime_engine.py` — combined ATR+displacement+swings+range | New file | — | ~200 |
| P02 | ATR wiring broken | `snapshot_atr_from_cache()` — compute from cached bars | New function | `io_performance_log.py`, `market_context_cache.py` | ~40 |
| P03 | Guard fires on wrong levels | Thesis-timeframe matching in `_rejection_guard()` | Refactor | `trade_manager.py` | ~30 |
| P04 | Guard closes on bounce-back | `_scalp_guard()` — TP while M1 favorable | New function | `trade_manager.py` | ~40 |
| P05 | No displacement detection | `displacement.py` — body/ATR, at-level check | New file | — | ~80 |
| P06 | No swing sequence tracking | `classify_swing_sequence()` in `live_mapped_levels.py` | New function | `live_mapped_levels.py` | ~25 |
| P07 | Stale mapped levels | Distance filter in `_mapped_trade_level_prices()` | Edit | `trade_management.py` | ~5 |
| P08 | confidence=0 + ready | Curriculum: calibrated confidence examples | Training data | `stage_05_live_contract.jsonl` | ~20 examples |
| P09 | H4 always rejected | Curriculum: H4-scale invalidation examples | Training data | `stage_05_live_contract.jsonl` | ~15 examples |
| P10 | Dashboard shows all levels | Track `decision_level_refs`, separate qualified/candidate | Edit | `trade_management.py`, frontend | ~50 |
| P11 | No LTF confirmation gate | Wire `m1_failure_at_zone()` as entry gate | Edit | `paper_executor.py` or `reviewer.py` | ~20 |
| P12 | live_map unknown to model | Curriculum: live_map interpretation examples | Training data | `stage_05_live_contract.jsonl` | ~10 examples |
| P13 | Build drift | Re-freeze after validation | Script | `build_manifest.py` | ~2 |
| P14 | reached_favorable uses tick price | Regime-dependent: scalp uses ticks, trend uses closed candle | Edit | `trade_manager.py` | ~15 |
| P15 | Entry target mode not regime-aware | Supply regime_context in entry prompt, curriculum | Edit + training | `reviewer.py`, curriculum | ~30 + examples |
| P16 | Loss cooldown structural | Already partially fixed (5min + HTF rejection) | — | — | Done |
| P17 | favorable_outside entry | Already fixed (inside_zone only) | — | — | Done |
| P18 | HTF micro brackets | Already fixed (_refuse_htf_micro_bracket) | — | — | Done |
| P19 | No range detection | `_detect_range()` in `regime_engine.py` | New function | — | ~40 |
| P20 | No transition detection | `prev_regime` tracking + `regime_transition` flag | In regime_engine | `regime_engine.py`, `trade_management.py` | ~15 |

**Total new code:** ~500 lines Python + ~45 training examples  
**Files changed:** 7 existing + 2 new  
**Files added:** `regime_engine.py`, `displacement.py`

---

## Part 4 — Implementation Sequence

### Phase 1: Foundation (Aug 17-20) — Pure Computation, No Behavior Change

**Goal:** Get ATR working, add displacement and swing detection, compute regime_hint. Nothing changes in actual trading behavior yet — all new outputs are logged for observation.

```
Step 1.1: ATR from cache (P02)
  - Add get_cached_m1_bars() to market_context_cache.py
  - Add snapshot_atr_from_cache() (uses existing atr_from_rates)
  - Change io_performance_log.py line 220 to use cache-based ATR
  - Verify: logs show non-null ATR values on every Qwen call
  - Test: unit test with mock bars, assert ATR values match expected

Step 1.2: Displacement detection (P05)
  - Create displacement.py (~80 lines)
  - candle_displacement() — body/ATR, body_pct, direction
  - displacement_at_level() — check against mapped levels
  - Test: unit test with known candles + ATR + levels

Step 1.3: Swing sequence (P06)
  - Add classify_swing_sequence() to live_mapped_levels.py (~25 lines)
  - Consumes existing fractal_swings() output
  - Test: unit test with known swing sequences

Step 1.4: Range detection (P19)
  - Add _detect_range() to regime_engine.py
  - Consumes M5 swings + current_price + ATR
  - Test: unit test with today's swing data, assert range detected

Step 1.5: Regime engine (P01)
  - Create regime_engine.py (~200 lines)
  - compute_regime() combines all signals → RegimeContext
  - Wire into trade_management.py review cycle — LOG ONLY
  - Verify: regime_hint appears in management logs
  - Test: unit test with today's data:
    - Trades 1-5 period → "range"
    - Trade 6 period → "breakout"
    - Trades 8-9 period → "trend"

Step 1.6: Stale levels cleanup (P07)
  - Add distance filter to _mapped_trade_level_prices() — 5 lines
  - Verify: loaded levels drop from 11 to 3-4 near price
```

**Validation gate:** ATR values non-null, regime_hint logged, no trading behavior changed. Paper trade 2 sessions to collect regime_hint accuracy data before proceeding.

---

### Phase 2: Guard Upgrade (Aug 20-22) — First Behavior Change

**Goal:** Guard routes on regime_hint. Scalp guard takes profit in ranges. Rejection guard holds in trends with thesis-timeframe matching.

```
Step 2.1: Split guard (P03, P04)
  - Refactor confirmed_management_guard() into:
    _invalidation_guard() — always runs, regime-independent
    _scalp_guard() — range/exhaustion: TP at M5 while favorable
    _rejection_guard() — trend/breakout: thesis-TF matching
  - Guard receives regime_hint from regime_engine
  - Test: replay today's 8 guard fires through new code:
    - Trades 1-5: scalp_guard should fire earlier (at favorable level)
    - Trades 6-7: check transition behavior
    - Trades 8-9: rejection_guard should NOT fire on M5

Step 2.2: reached_favorable regime-dependent (P14)
  - scalp_guard: uses peak_price (current behavior, correct for range)
  - rejection_guard: adds closed-M1 requirement for reached_favorable
  - Test: wick-only touches should not trigger rejection_guard

Step 2.3: regime_context in management facts (P20)
  - Add regime_context to build_management_facts() output
  - Management prompt includes regime_context for Qwen
  - regime_transition flag when regime changes between cycles
```

**Validation gate:** Paper trade 2-3 sessions. Measure:
- Do scalp_guard exits capture more profit than old guard in ranges?
- Do rejection_guard holds survive through M5 noise in trends?
- Do regime transitions get flagged correctly?

---

### Phase 3: Entry Refinement (Aug 24-27) — Second Behavior Change

**Goal:** Entries are regime-aware. Targets match the regime. M1 rejection gate prevents zone-touch fills.

```
Step 3.1: M1 rejection gate (P11)
  - Wire m1_failure_at_zone() into entry path
  - After inside_zone: require completed M1 that probed zone and failed
  - Test: entries should show brief delay between zone touch and fill

Step 3.2: Entry target_mode from regime (P15)
  - Supply regime_context in entry prompt
  - Range → target_mode: scalp, first_target at opposing M5 boundary
  - Trend → target_mode: starter_basket or directional_basket
  - Breakout → target_mode: starter_basket, hold for HTF
  - Exhaustion → target_mode: scalp (counter-trend)

Step 3.3: Dashboard qualified levels (P10)
  - Track which level_ids Qwen cited in decisions
  - Separate qualified (cited) from candidate (computed)
  - Frontend renders qualified prominently
```

**Validation gate:** Paper trade 3 sessions. Measure:
- Are scalp targets being hit in ranges?
- Are basket targets being reached in trends?
- Does M1 rejection gate improve entry quality (fewer immediate adverse moves)?

Step 3.1a: Shared zone-response measurement
  - `structure_response.py` evaluates every completed M1 against the current
    execution-level ladder before model qualification.
  - Zones remain intervals; probe, sweep, close-back, and acceptance use the
    zone edges rather than exact-price equality.
  - Excursion and close-return distances are reported in ATR-normalized units,
    while instrument point size supplies the minimum width for line levels.
  - The resulting `structural_responses` packet is instrument-neutral and is
    authoritative over stale playbook `missing_evidence` text.
  - Qwen still judges context and trade quality; Python establishes what the
    completed candle objectively printed.
  - Regression fixture: XAUUSD 2026-08-19 16:16 UTC must classify the sweep of
    4498.867/4499.153 and close at 4497.674 as a confirmed sell response.

---

### Phase 4: Curriculum (Aug 31 - Sep 5) — Model Alignment

**Goal:** Qwen learns regime vocabulary, confirmation patterns, confidence calibration, and H4 geometry.

```
Step 4.1: Regime vocabulary (P01 curriculum)
  - Add to core_skill.md: regime section describing range/trend/breakout/exhaustion
  - Training examples: Qwen reads regime_context and adjusts management
  - Examples where Qwen overrides Python regime_hint with context

Step 4.2: CHoCH/BOS/FVG detection engine (P11 enhancement)
  - Create confirmation_engine.py
  - Mechanical detection of CHoCH, BOS, FVG, liquidity sweep on M1/M5
  - Inject into entry context for Qwen judgment
  - Curriculum: Qwen interprets confirmations

Step 4.3: Confidence calibration (P08)
  - Training examples with calibrated scores
  - Regime-aware: "range with clear boundaries → 70" vs "unclear regime → 40"
  - confidence=0 + ready should not occur after training

Step 4.4: H4 curriculum (P09)
  - Examples with H4-scale invalidation (10-20 points, not 3)
  - "H4 thesis needs H4-scale stop or skip"
  - Reduce H4 rejection rate

Step 4.5: live_map interpretation (P12)
  - Training examples where model reads live_map zones
  - Double_top/bottom detection examples
```

**Validation gate:** Curriculum eval before live deployment. Model correctly:
- Identifies regime from regime_context
- Adjusts management per regime
- Expresses calibrated confidence
- Produces viable H4 proposals or skips
- Interprets CHoCH/FVG confirmations

---

### Phase 5: Freeze + Live (Sep 5+) — Production

```
Step 5.1: Re-freeze build (P13)
  - Commit all changes
  - New build hash frozen
  - Clear drift alarm

Step 5.2: Live validation
  - 48-72h paper trading with full system
  - Compare against pre-change baseline
  - Measure: regime detection accuracy, guard behavior, entry quality

Step 5.3: Live account transition
  - 2 weeks live data collection
  - Review and tune thresholds
  - Curriculum refresh based on live results
```

---

## Part 5 — Verification Matrix

Every problem has a testable success criterion:

| # | Problem | Success Criterion | How to Measure |
|---|---------|-------------------|----------------|
| P01 | No regime detection | regime_hint matches manual chart reading in >80% of M5 intervals | Replay 1 week of M5 bars, manual label vs code label |
| P02 | ATR broken | Non-null ATR values on 100% of Qwen calls | grep ATR logs for ok:true vs ok:false |
| P03 | Wrong guard levels | M15+ thesis trades never closed on M5 levels (trend mode) | Filter guard closes by thesis TF and level TF |
| P04 | Bounce-back close | In detected ranges, guard TP captures >60% of peak move | Compare guard close price vs peak price per trade |
| P05 | No displacement | Displacement candle correctly flagged within 1 M1 close of manual identification | Manual review of 20 displacement events |
| P06 | No swing sequence | Swing pattern matches manual reading in >85% of checks | Replay M5 swings, compare classification |
| P07 | Stale levels | <5 operator-mapped levels loaded (down from 11) | Count loaded levels in log |
| P08 | confidence=0 + ready | invariant:ready_with_zero_confidence fires <5% of ready decisions | Count invariant fires / total ready decisions |
| P09 | H4 rejected | htf_thesis_micro_bracket rejection rate drops >50% | Count rejections before vs after |
| P10 | Dashboard noise | Dashboard shows <10 qualified levels (down from 30+) | Visual check |
| P11 | No LTF confirmation | Entry quality improves: <30% of entries show immediate adverse move >$1 | Measure adverse move in first 60s post-fill |
| P14 | Tick-based reached | In trend mode, wick-only touches don't trigger rejection guard | Replay guard behavior on wick touches |
| P15 | Wrong target mode | Range entries have first_target at M5 boundary, not H1 | Check target levels in proposals |
| P19 | No range detection | Range detected when price bounces 3+ times between M5 levels | Replay known ranging sessions |
| P20 | No transitions | Breakout detected within 2 M5 candles of range boundary break | Replay known breakout events |
| P21 | Closed response missed by stale playbook | 100% of replayed probe-and-close fixtures appear in `structural_responses` on the next decision | Replay identical normalized fixtures for XAUUSD and a non-gold price scale |

---

## Part 6 — Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Regime detection false positives | HIGH | Log-only phase first. Regime_hint is a hint — guard can ignore when evidence is weak. Qwen can override. |
| Scalp guard exits too early in trend | MEDIUM | Only fires when regime_hint = "range". Requires range detection (bounces + width). Falls through to Qwen if unsure. |
| ATR cache bars stale | LOW | Cache refreshes every M1 close. ATR uses 51 bars (~51 min). Staleness < 1 min is harmless. |
| Regime transition lag | MEDIUM | Breakout detection requires displacement (body/ATR > 0.8) which is a lagging indicator by 1 candle. Acceptable — better late than wrong. |
| Displacement threshold too aggressive/conservative | MEDIUM | Start with body_pct > 0.65 and body_atr > 0.8. Tune from paper trade data. Log all displacement candidates for threshold analysis. |
| Two guards create edge cases | HIGH | Both paths have invalidation check first (regime-independent). Unknown regime falls through to Qwen. Both guards log their regime + reason for audit. |
| Curriculum doesn't stick in 7B model | MEDIUM | Qwen 7B has limited capacity. Keep regime vocabulary simple (4 states). Don't teach complex conditional logic — Python handles complexity, Qwen judges quality. |
| Build drift accumulates further | LOW | Freeze after Phase 1 (foundation). Freeze again after Phase 2 (guard). Two intermediate freezes, not one at the end. |
| Mechanical zone response overrules context | HIGH | Detector reports printed structure only; Qwen retains directional/context judgment and executor retains risk/geometry gates. |

---

## Part 7 — Rules of Engagement

1. **One piece at a time.** Each step is validated before starting the next. No multi-step changes without intermediate paper testing.

2. **Foundation before behavior.** Phase 1 adds computation and logging only — no trading behavior changes. Phase 2 changes guard behavior. Phase 3 changes entry behavior. Phase 4 changes model behavior. Each layer is validated before building the next.

3. **Python computes, Qwen judges.** Regime detection, displacement, swing classification, range detection — all deterministic Python. Whether the regime assessment is correct in context is Qwen's judgment. The guard uses the Python hint; Qwen can override.

4. **Closed candles only.** No system component makes structural decisions from intrabar data. Exception: scalp_guard can use peak_price for TP timing in range (taking profit at a reached level is timing, not a structural decision).

5. **Log everything.** Every new component logs its output. Every regime transition is logged. Every guard decision logs which guard ran and why. Every displacement is logged. This data feeds the next iteration.

6. **No doctrine change.** core_skill.md and sop.md are extended (regime section added) but not rewritten. The 3-step entry process (context → hunt → arm) stays. The 4 exit conditions (invalidation/flip/arithmetic/time) stay. Regime detection is a new layer that informs existing decisions, not a replacement.

7. **Measure against baseline.** Every phase compares against the pre-change paper trade results. If a phase makes things worse, revert and investigate before proceeding.

8. **Qwen is the sole discretionary brain, not the whole implementation.** The guard, executor, regime engine, level detection, SQLite, Neo4j, and retrieval services are deterministic support components. They compute facts, provide context, enforce approved safety, and execute validated instructions; they do not compete with Qwen for normal trade judgment. Qwen receives their mechanically sound evidence and remains the main driver for entries and routine management.
