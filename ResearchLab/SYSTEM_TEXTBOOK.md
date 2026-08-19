<!-- document: QuantLLMBot system textbook | version: 1.0 | audience: humans and LLM engineering agents -->
# QuantLLMBot System Textbook

## Purpose and authority

This book explains the complete QuantLLMBot research and MT5 demo-paper
software as one system. It is written so that a new human engineer or LLM agent
can understand the stages, data contracts, ownership boundaries, failure
behavior, and evidence trail before changing anything.

This document is descriptive and educational. It does not replace the two
human-owned normative sources:

1. `store/core_skill.md` defines market-structure knowledge.
2. `store/sop.md` defines model reasoning, output, management, and learning
   contracts.

When this textbook disagrees with either canonical file, the canonical file
wins. Python owns processing and validation. Trading knowledge belongs in the
fixed store. This workspace authorizes historical research and MT5 demo/paper
execution only; it does not authorize live trading.

## How an LLM should read this system

An LLM working on this repository must keep five ideas separate:

- **Facts:** immutable completed candles, current forming candles, ticks,
  broker deals, account state, and deterministic levels.
- **Interpretation:** an LLM's bounded reading of supplied facts.
- **Decision:** an entry or management object that satisfies a typed contract.
- **Validation:** deterministic checks that decide whether the object may
  influence execution.
- **Learning:** outcome analysis kept outside the next market snapshot and
  promoted only through evidence and human review.

Never treat model confidence alone as proof that a trade will win. A minimum
confidence of 51 is one deterministic coherence qualification, alongside an
explicit direction, valid provenance, current cache/session state, and usable
geometry. Never treat a cached model response as current market state. Never
infer live-trading permission from working demo execution.

Before changing a validation or freshness gate, read
`PROVEN_HARMFUL_CHANGES.md`. It records stricter-looking mechanisms that were
shown to suppress valid behavior and the companion controls that must remain.

## The complete system at a glance

```text
Windows login
  -> unified runtime
  -> MT5 + Ollama + IIS health
  -> market-data/cache process
  -> reviewer and entry-decision process
  -> proposal log
  -> proposal runner
  -> single-position demo executor
  -> stateful trade manager
  -> MT5 close or broker safety stop
  -> broker-deal reconciliation
  -> episode/audit/learning pipeline
  -> hypothesis, replay, walk-forward, paper approval
```

There are two connected but distinct lanes:

- **GoldFlow/Qwen demo lane:** the active local website and one-position MT5
  demo process under `apps/qwen_trade_software`.
- **ResearchLab lane:** historical replay, provider comparison, learning,
  memory lifecycle, and validation under `ResearchLab`.

The lanes may share doctrine and decision contracts, but neither may silently
invent a different strategy rule.

## Stage 0: source, deployment, and runtime identity

### Source of truth

Version-controlled source lives in `D:\QuantLLMBot`. The deployed Qwen backend
lives at:

```text
C:\Users\HP\AppData\Local\QwenTradeReviewer
```

The IIS website bundle lives at:

```text
C:\inetpub\GoldFlowDesk
```

Source and deployed hashes must match after a release. Runtime logs, model
weights, locks, SQLite cache state, and generated proposals are deployment
state and are not committed.

### Unified startup

`apps/qwen_trade_software/backend/software_runtime.py` is the single launcher.
It acquires a singleton, starts or verifies MT5 and Ollama, verifies IIS, then
supervises three child processes:

- `reviewer.py` for snapshots, Qwen entry decisions, trade management, and the
  dashboard API;
- `market_context_cache.py` for deterministic cache refresh and readiness; and
- `paper_runner.py` for proposal consumption and executor launch.

The runtime restarts failed children and records health in
`logs/software-runtime.log`. Starting the website is not what starts trading;
the unified runtime is the software process, while the website is its view.

### Hard boundary

The executor verifies an MT5 demo account. A non-demo account must be rejected.
All Qwen-owned positions use magic number `26072401` and the `QWEN_` comment
prefix so unrelated and manual positions cannot enter the management path.

## Stage 1: MT5 observation and normalization

MT5 is the market and broker source of truth. The system observes:

- bid, ask, spread, quote timestamp, and symbol metadata;
- D1, H4, H1, M30, M15, M5, and M1 candles;
- positions owned by the Qwen magic/comment identity; and
- opening and closing broker deals, commission, and swap.

Completed candles and forming candles are different objects. Position zero in
an MT5 rates request is forming and cannot support a completed-close claim.
Timestamps are normalized to UTC. OHLC geometry, alignment, chronology,
duplicates and candle geometry are checked before derived context is trusted.
Historical and rollover gaps do not block readiness; missing latest/forming
candles block only while the active weekday data session should be updating.

An LLM must never turn a forming wick into a completed breakout, acceptance,
rejection, or invalidation.

## Stage 2: external market-memory cache

`market_context_cache.py` stores explicit context in SQLite/WAL. Model residency
keeps weights loaded; it does not preserve reliable market memory. The external
cache is the memory.

The cache is hierarchical:

- **L0 raw:** normalized completed/forming candles and tick facts.
- **L1 structure:** D1/H4/H1 location, parent auction, swings, zones, and
  unresolved conflict.
- **L2 levels:** deterministic named levels and their source evidence.
- **L3 playbooks:** two-sided H4 zone conditions with immutable identifiers,
  targets, and invalidations.
- **L4 day/session:** UTC session, Asia range, M30/M15/M5 path, and volume
  context.
- **L5 minute:** the newest completed M1, forming parent candles, nearby zones,
  and active playbook delta.
- **L6 position thesis:** immutable entry plan plus fills, reached levels,
  peak/giveback path, prior management, and exit evidence.

Every derived object carries a schema version, cache epoch, source interval,
source hash, evidence IDs, producer version, and expiry/invalidation state.
Replacing context creates a new epoch; it does not mutate the evidence identity
used by an older decision.

The governing implementation and gate definitions are in the sole active
architecture, `../XAUUSD_SYSTEM_ARCHITECTURE_V2.md`.

## Stage 3: context warm-up and qualification

Warm-up prepares understanding before minute decisions. It is not a trade.

1. Load the required D1/H4/H1 history.
2. Validate raw chronology and completed/forming separation.
3. Build deterministic levels.
4. Ask Qwen for bounded structural interpretation.
5. Load current-day M30/M15/M5 and current-H1 M1 context.
6. Build UTC session and Asia-range facts.
7. Create two-sided H4 playbook interpretations without allowing Qwen to
   change code-owned prices or identities.
8. Challenge Qwen on exact epochs, locations, levels, candle identities,
   session facts, both directional paths, and bounded data requests.
9. Publish a readiness manifest.

Readiness is a conjunction of hard gates. One failed raw-data, provenance,
level, session, playbook, minute-delta, model-residency, or context-challenge
gate makes the manifest `blocked`. There is no confidence average that can hide
a failed gate.

The cache process remains operationally separate from execution, but its ready
packet is now the mandatory entry input. Entry Qwen must acknowledge the exact
structure, level, session, playbook, and minute epochs and cite only supplied
evidence IDs. A blocked, expired, or mismatched cache produces wait.

## Stage 4: compact minute context

After warm-up, the model does not need eight weeks of raw candles every minute.
The minute packet carries only the current delta plus references to validated
longer-horizon cache objects.

A normal packet contains:

- compatible cache epochs;
- current quote and age;
- latest completed M1 with evidence ID;
- forming M5/M15/M30/H1/H4 facts clearly marked as forming;
- relative volume facts;
- nearby named levels and distances;
- active playbook identity and missing evidence; and
- the open-position thesis reference when applicable.

The packet is small for latency and attention quality, not because context is
discarded. Long context remains addressable through stable cache references.
Qwen may ask for one bounded additional data packet through the typed request
contract.

## Stage 5: entry analysis

Entry selection and position management are separate problems.

When no Qwen position is open, `reviewer.py` builds an entry snapshot from:

- D1/H4/H1 structure and location;
- M30/M15 path;
- M5 local map;
- M1 timing candles;
- deterministic chart levels and respect counts;
- session context;
- volume/participation facts.

Recent wins and losses are excluded from the next entry snapshot. They remain
research evidence, not directional input.

Qwen returns a structured entry plan. Normalization requires named entry bounds,
direction, structural invalidation, structural target, reason, and one 0.50-lot
position. Basket count is forced to one. Add-ons, averaging, and simultaneous
Qwen positions are disabled.

The entry model decides **whether and where to enter**. It does not decide how
an already-open trade should react to later candles.

## Stage 6: entry validation and proposal creation

A model response is not an order. The reviewer normalizes it and creates an
immutable JSONL proposal only when its contract is usable. A ready proposal
requires confidence 51-100, an explicit buy or sell bias, and agreement between
that bias and the normalized plan side. This qualifies logical coherence; it
does not convert confidence into a guarantee or reject a valid trade because a
previous trade lost.

Important proposal fields include:

- proposal ID and completed-Qwen timestamp;
- symbol, timeframe, quote, and market snapshot;
- normalized direction and one-position execution plan;
- named entry, invalidation, and target references;
- model name, raw response, confidence, and summary; and
- human feedback and execution fields reserved for later evidence.

The proposal timestamp is recorded after model generation. Its 60-second
validity therefore begins when the model result exists, not when generation
started.

## Stage 7: proposal runner and signal expiry

`paper_runner.py` polls validated proposals every 250 milliseconds. It checks:

- the proposal has not already been processed;
- the decision is fresh;
- Qwen confidence and direction provenance still agree;
- the cache is currently ready and its structural/playbook/model identity is
  unchanged;
- the same UTC trading date and permitted session are still active;
- no Qwen position is open;
- the MT5 deal-history filled-position cap is not exceeded; and
- only one runner owns the process lock.

It then launches `paper_executor.py` with one position and the remaining signal
lifetime. If price never reaches the named entry zone inside the total
60-second lifetime, the proposal closes as `signal_expired` without a fill and
does not consume the filled-trade cap.

## Stage 8: single-position demo execution

The executor repeats the demo-account lock, proposal identity, symbol, side,
volume, entry-zone, and freshness checks. It refuses more than one position.

When the executable bid/ask enters the entry zone, the executor observes that
range briefly. For a buy it records the lowest ask; for a sell it records the
highest bid. It enters on a small retracement from the best quote, when the
bounded observation window completes, or immediately before signal expiry if
price remains inside the approved range. The range, side, and original
60-second lifetime never change. The broker receives a safety stop derived
from recent closed M1/M5 range and constrained to a 3-5 XAUUSD price-unit
distance. This safety stop protects against process/model failure; it is not
the complete management strategy.

The executor does not:

- open a basket;
- add to a winner or loser;
- average a losing thesis;
- close after a fixed number of seconds;
- close merely because gross P&L becomes positive; or
- place an automatic hard target at the model's named target.

Once filled, it emits one-second monitor events containing executable mark,
entry, current and peak favorable movement, giveback, adverse movement, gross
P&L, peak P&L, drawdown, structural target progress, stop progress, and holding
time. These events are the exact trade-path memory used by management.

## Stage 9: stateful trade management

`trade_manager.py` receives exactly one already-open position. It never creates
an entry, add-on, reversal, or basket.

The management packet contains:

- immutable entry thesis, target, and invalidation;
- current position and broker stop;
- current executable movement and gross P&L;
- recorded peak price, peak movement, peak P&L, and price giveback;
- favorable named levels reached by execution or completed M1 path;
- up to three previous management decisions;
- nearby current M5-or-higher reaction levels; and
- three completed M1 and two completed M5 candles with exact evidence IDs.

The model may return only `hold`, `protect`, or `close`.

### Hold

Hold means adverse exit confirmation is incomplete or continuation remains
valid. A hold cannot claim that target rejection, thesis invalidation, or an
adverse momentum reversal is already confirmed. If it does, validation blocks
the contradiction.

### Protect

Protect means completed M1 and M5 accepted beyond a supplied favorable level.
Protection may only tighten the existing stop at a valid named level. It cannot
widen the stop, increase volume, or protect a losing position.

### Close

Close requires:

- exactly one supplied decision level;
- the latest completed M1 candle;
- a completed M5 confirmation candle;
- at least two exact evidence IDs;
- a tested level;
- an M1 close against the position; and
- current live price still on the confirmed adverse side when the order is
  sent.

Target touch alone is not a close. A reached M5-or-higher level becomes a review
location. Rejection is confirmed when a completed M5 tests and closes back
through the level and the latest completed M1 counter-closes through it.

Immutable thesis invalidation is confirmed when the latest completed M1 and M5
both close beyond the invalidation against the position.

### Pre-model confirmation guard

Qwen on the CPU can take longer than one M1 candle. Therefore deterministic
validation checks the same human-owned M1/M5 confirmation contract before a
new slow model call. If a reached-level rejection or immutable invalidation is
already confirmed, the guard issues the validated close immediately. This is
not a dollar-profit shortcut; it is enforcement of the same structural rule
when a stale or contradictory `hold` would surrender the trade path.

## Stage 10: closure and broker reconciliation

A position can close through:

- validated `QWEN_MGR_CLOSE` management;
- the independent broker safety stop;
- broker stop-out or another broker-side terminal event; or
- an explicitly identified operational failure path.

The authoritative result comes from MT5 deals, not a dashboard estimate. The
closure event records fill, exit, gross profit, commission, swap, broker-net
profit, peak favorable movement, giveback, adverse movement, hold time, and
close reason.

For research, always reconcile:

```text
broker net = MT5 profit + commission + swap
```

An unfilled expired proposal is not a losing trade. A partial or orphan record
is not valid profitability evidence until matched to the complete broker
position lifecycle.

## Stage 11: dashboard and observability

The local dashboard API is served at `http://127.0.0.1:48632/snapshot`. IIS
serves the GoldFlow website on port 80. The dashboard is a view of runtime state,
not the execution authority.

Important deployment logs are:

```text
logs/software-runtime.log
logs/reviewer.log
logs/market-context-cache.log
logs/paper-runner.log
logs/paper-proposals.jsonl
logs/paper-executions.jsonl
logs/reviews-YYYY-MM-DD.jsonl
```

Every diagnosis should join records by proposal ID, execution ID, position
ticket, order/deal ID, model/contract version, and UTC time. Repeatedly reading
entire logs in the live loop is prohibited; incremental caches or indexed state
must serve runtime needs.

## Stage 12: historical replay and provider lane

The ResearchLab lane replays closed historical data without look-ahead:

- `runners/backtest.py` is the historical runner.
- `runners/regular_paper.py` is the regular paper path.
- `engine/provider_gateway.py` is the shared provider boundary.
- `engine/decision_validation.py` is the shared decision contract.
- `deepseek_cached.py` handles provider transport, stable prefixes, card
  selection, and role-specific analysis.

Backtest and regular paper must use the same provider gateway, schema, geometry,
and validation rules. A replay model may see only facts closed at its decision
time. Latency, spread, commission, entry-zone expiry, and fill behavior must be
represented when a result is used as evidence for the demo system.

## Stage 13: episodes, learning, and memory promotion

The fixed store contains exactly eight active files:

```text
core_skill.md
sop.md
knowledge_cards.json
principles_registry.json
review_queue.json
episodes.jsonl
audit_log.jsonl
run_state.json
```

Every win, loss, and skip is an episode. Learning summaries operate in blocks
of 40 events. A block may produce hypotheses or memory proposals; it cannot
silently rewrite doctrine.

The memory lifecycle must:

1. parse evidence identities;
2. detect duplicates and contradictions;
3. preserve side-neutral structural language;
4. require repeated evidence across date/regime blocks;
5. queue uncertain or doctrine-changing proposals for human review; and
6. record every promotion, rejection, contradiction, and status change in the
   audit trail.

Prior outcomes are research evidence. They must not be injected into a market
snapshot in a way that creates recency-based direction bias.

## Stage 14: validation and release

`validation/validate_e2e.py` is the structural gate. It checks the fixed store,
registered files, prompt sections, context-cache self-test, single-position
manager replay, entry/management separation, no removed timer/add-on behavior,
provider budgets, geometry, sessions, news guards, memory evidence parsing,
and compilation of active modules.

A normal release sequence is:

1. inspect `git status --short` and preserve user changes;
2. reproduce the observed issue from logs or a deterministic fixture;
3. change the smallest owned layer;
4. add or update a regression test;
5. run targeted self-tests and Python compilation;
6. run the complete E2E validator;
7. confirm zero open positions before replacing deployed execution files;
8. compare source/deployed hashes;
9. restart the unified runtime;
10. verify MT5, Qwen, website, dashboard, and child-process health;
11. commit and push with the exact evidence and limitations recorded.

## End-to-end example

1. A completed M1 arrives from MT5.
2. Cache ingestion stores it once and advances the minute epoch.
3. Deterministic checks validate chronology and evidence identity.
4. With no open position, the reviewer builds an entry snapshot.
5. Qwen returns a one-position plan.
6. Normalization and geometry checks create an immutable proposal.
7. The runner consumes it inside 60 seconds.
8. Bid/ask reaches the entry zone and the executor opens one demo position with
   a broker safety stop.
9. The executor records peak/giveback every second.
10. The manager receives the immutable thesis, trade path, reached levels,
    prior decisions, and closed M1/M5 evidence.
11. Continuation is held, confirmed acceptance may protect, and confirmed
    rejection or invalidation closes.
12. MT5 deals establish the broker-net outcome.
13. The event enters the separate learning and research loop.

## Non-negotiable invariants

- Historical and demo/paper only; no inferred live authority.
- One Qwen position at a time; no basket or add-on.
- Entry and management have separate contracts.
- MT5 facts and code-owned levels are authoritative.
- Completed and forming candles never share evidence semantics.
- No cached decision is reused for another snapshot.
- No fixed-dollar target or time-only close.
- Broker safety protection remains independent of model availability.
- Every mutating management action requires deterministic validation.
- Current live price is rechecked after model inference.
- Broker deals, not runner summaries, establish realized P&L.
- Learning changes require evidence and human review.
- Source, deployed hashes, model digest, prompt version, and cache epochs must be
  traceable.

## LLM pre-change checklist

Before proposing or editing code, answer:

1. Which stage owns the problem?
2. Is this fact, interpretation, decision, validation, execution, or learning?
3. Which canonical contract applies?
4. What exact evidence reproduces the issue?
5. Is the requested change engineering behavior or strategy doctrine?
6. What invariant could it break?
7. What deterministic regression test will fail before and pass after?
8. Does historical and regular paper behavior remain aligned?
9. Can deployment occur with zero open positions?
10. What result would falsify the improvement claim?
11. Does `PROVEN_HARMFUL_CHANGES.md` reject this mechanism or an equivalent?

If these questions cannot be answered, continue diagnosis; do not improvise a
trading rule.
