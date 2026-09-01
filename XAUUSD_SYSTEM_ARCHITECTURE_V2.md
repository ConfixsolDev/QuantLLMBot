# XAUUSD Quantitative Trading System — Architecture V2

> **SOLE ACTIVE ARCHITECTURE DOCUMENT — DO NOT OVERRIDE OR REPLACE.**
> Improve this file in place and preserve its V2 identity. Supporting audits,
> research, READMEs, prompts, and implementation notes cannot redefine it.

**Architecture authority:** V2

**Original date:** 2026-08-17

**vNext contract reset:** 2026-08-31

**Broker scope:** MetaTrader 5 demo/paper execution

**Initial instrument:** XAUUSD, with broker-symbol mapping owned by configuration

## 1. Purpose and scope

This document defines only the clean vNext system contract under
`apps/qwen_trade_software/vnext/`. It defines component ownership, common
interfaces, lifecycle ordering, persistence authority, safety invariants,
recovery, observability, and activation gates.

It does not define a trading strategy. Entry setups, directional logic,
timeframe choices, zone eligibility, triggers, session filters, regime
playbooks, invalidation selection, target selection, entry expiry, trade-class
management, and strategy risk budgets belong to versioned strategy packages.

The first strategy is implemented by
`vnext/strategy/xau_m15_m1_structure_scalper.py`. Its human/model doctrine is
owned by `store/core_skill.md` and `store/sop.md`. Those sources may define how
the strategy judges a trade, but they may not redefine system ownership,
persistence, broker safety, or lifecycle ordering.

Training, curriculum, and dataset preparation remain governed exclusively by
`model_training/CURRICULUM_AND_DATA_PREP.md`.

### 1.1 Current activation status

vNext is the only target architecture. Production execution is paused.
`deploy/Start-QuantLLMVNext.ps1` currently performs storage and broker
preflight only; it does not start a vNext service loop. Retired implementations
are quarantined outside the active application tree and must never run beside
an activated vNext decision or execution worker.

No component is production-ready merely because its module or unit tests
exist. Activation requires the end-to-end gates in section 13.

## 2. Binding responsibility boundary

### 2.1 Common system responsibilities

The common vNext system owns tasks that must be identical and non-discretionary
across strategies:

- canonical UTC time and one causal evidence frontier;
- broker-symbol normalization and immutable closed-market observations;
- deterministic timeframe aggregation and provenance;
- neutral calculation of indicators, structure observations, zones, sessions,
  spread, volatility, and cross-market facts;
- immutable event persistence and replay;
- bounded context assembly without trade preference;
- strategy registration, isolation, scheduling, leases, and lifecycle order;
- model transport, schema validation, timeouts, and fail-closed handling;
- account, broker, data-quality, exposure, and hard risk enforcement;
- order validation, idempotent submission, broker-result normalization, fill
  reconciliation, and position ownership;
- immutable audit events, metrics, recovery, and operational health.

These components may calculate facts, reject malformed or unsafe actions, and
enforce a strategy's declared immutable contract. They may not originate or
silently repair a trading decision.

### 2.2 Strategy responsibilities

Each versioned strategy owns every rule that determines whether, when, where,
or why an entry may exist, including:

- eligible instrument and broker-symbol mapping requirement;
- context, setup, and execution timeframes;
- allowed market structures, zone types, regimes, and sessions;
- directional thesis and how both sides are compared;
- candidate eligibility and opportunity selection;
- entry trigger and all confirmation or response requirements;
- entry price or entry-zone selection;
- invalidation and stop reference selection;
- target selection, target-space requirements, and reward/risk requirements;
- news, spread, volatility, and timing rules used for entry selection;
- candidate cadence, freshness, re-arm, expiry, and cancellation rules;
- strategy risk budget within system/account caps;
- trade-class-specific management, protection, and exit policy;
- statistical qualification and replay acceptance criteria;
- the bounded Qwen prompt/doctrine used by that strategy.

The strategy must declare these rules through its immutable definition,
candidate contract, management policy, and versioned doctrine. A common module
may execute or validate a declared rule, but the rule and its parameters remain
strategy-owned.

### 2.3 Prohibited ownership leakage

Common intelligence, aggregation, narration, graph, risk, OMS, and broker code
must not:

- pick buy or sell from the latest candle or swing;
- select an entry zone because it is recent, close, or highly scored;
- turn a detected support/resistance fact into an entry;
- impose a particular timeframe, pattern, confirmation, target, or expiry;
- substitute missing strategy geometry;
- optimize or tune a strategy from outcomes;
- create a candidate when the registered strategy did not request one;
- change a strategy decision because another strategy disagrees;
- use P&L, win rate, or future evidence to influence an entry unless the
  strategy contract explicitly permits a leakage-safe statistic.

Any generic helper that currently performs one of these actions is strategy
code in the wrong package and is non-conforming until moved behind the strategy
boundary.

## 3. Decision authority

Architecture does not prescribe one universal trading brain. It provides a
safe strategy boundary that can host a deterministic strategy, a Qwen-led
strategy, or a hybrid, provided the strategy declares that authority and passes
the evidence gate.

For the currently registered XAUUSD strategy, Qwen remains the discretionary
judge described by `store/core_skill.md` and `store/sop.md`. Common Python may
prepare neutral evidence and enforce safety, but may not choose its direction,
entry, invalidation, target, or routine management action.

Qwen has no direct database, graph, Redis, filesystem, process, or broker write
access. It receives a bounded immutable package and returns a schema-validated
strategy response. A model failure, timeout, malformed response, stale state
hash, or invented reference is a no-trade result.

## 4. Canonical contracts

All live contracts are versioned, immutable after creation, serializable, and
bound to one UTC evidence frontier. IDs and hashes are content-derived or
idempotent within their namespace.

### 4.1 `PAIR_MARKET_STATE_V1`

`vnext.market.state.PairMarketState` is the neutral common evidence contract.
It may contain:

- pair and broker symbol;
- frontier and data-quality state;
- completed and explicitly labelled forming bars;
- neutral structure events and zone observations;
- indicators and participation facts;
- timeframe and cross-instrument relationships;
- active-level facts and graph evidence references;
- strategy-scoped evidence only in a namespaced extension produced by that
  strategy, never by the common state composer.

It must reject future-dated or frontier-inconsistent evidence. It must not
contain a common `direction`, `entry`, `stop`, `target`, `candidate`, or
`approve` conclusion.

### 4.2 `STRATEGY_DEFINITION_V1`

A strategy definition carries at minimum:

- immutable strategy ID and semantic version;
- pair/instrument scope and unique magic number;
- bounded MT5 comment and trade class;
- required fact-contract versions;
- evaluation cadence and candidate expiry policy;
- strategy entry-policy reference;
- risk-policy reference and account-cap namespace;
- management-policy reference;
- statistical/replay qualification requirements;
- narrator and model-contract reference when used.

Changing an entry or management rule requires a new strategy version. Runtime
configuration may enable or disable a version but may not mutate it.

### 4.3 `TRADE_CANDIDATE_V1`

Only a registered strategy may create a candidate. A candidate carries:

- candidate ID, strategy identity/version, pair, trade class, and magic;
- strategy-selected direction and entry trigger/reference;
- strategy-selected entry zone, invalidation, and target references;
- creation/frontier time, expiry, and strategy state hash;
- exact evidence IDs and contract versions;
- statistics and narrator snapshot references when required;
- lifecycle state and an immutable candidate hash.

References must resolve to the same causal state used to create the candidate.
An unresolved, stale, incomplete, cross-strategy, or future-dated candidate is
rejected; common runtime never fills in missing trading geometry.

### 4.4 `QWEN_ARBITRATION_V1`

When a strategy uses Qwen, the shared gateway transports exactly one bounded
strategy package. The response cites the candidate and state hash, follows the
strategy-owned response schema, and cannot alter candidate geometry or risk.
The gateway owns transport only; it does not generate candidates, rank
opportunities, or interpret the market.

### 4.5 `RISK_REQUEST_V1` and `RISK_DECISION_V1`

The strategy supplies its requested risk policy and complete executable
geometry. Common risk code enforces:

- positive account equity and valid point/tick value;
- configured strategy budget within global and daily caps;
- stop-side and target-side geometry;
- real stop distance and cost-adjusted exposure;
- strategy, symbol, and account exposure caps;
- broker volume minimum, maximum, and step;
- spread/slippage policy declared by the strategy;
- data, storage, clock, and broker health;
- demo-account restriction;
- no increase to already accepted position risk.

The result includes approved risk amount, normalized volume, rejected reasons,
and the exact inputs/hash. Risk code may veto but never choose market direction,
entry, stop, or target.

### 4.6 `ORDER_INTENT_V1`

The strategy/execution adapter converts one risk-approved candidate into an
order intent. Common OMS verifies that pair, direction, entry, stop, target,
volume, candidate ID, strategy ID/version, magic, comment, state hash, and
expiry exactly match the approved candidate and risk decision. Conflicting or
missing identity/geometry is rejected rather than overwritten.

## 5. Generic lifecycle

Every strategy instance follows the same ordered lifecycle:

1. `INACTIVE`
2. `ELIGIBLE`
3. `WATCHING`
4. `ARMED`
5. `TRIGGERED`
6. `CANDIDATE_CREATED`
7. `STRATEGY_APPROVED`
8. `RISK_APPROVED`
9. `ORDER_PENDING`
10. `POSITION_ACTIVE`
11. `CLOSED`

Terminal branches include `REJECTED`, `INVALIDATED`, `EXPIRED`, and
`CANCELLED`. No model, strategy, recovery process, or broker adapter may skip
required transitions. Each transition is persisted before its downstream side
effect. Restart reconstructs lifecycle from TimescaleDB and broker truth.

The lifecycle is generic. Conditions for entering `ELIGIBLE`, `ARMED`,
`TRIGGERED`, or strategy approval are entry rules and therefore belong to the
strategy.

## 6. Market-data and intelligence boundary

### 6.1 Causal frontier

All inputs use timezone-aware UTC timestamps. Structural and entry decisions
use only completed observations unless the strategy explicitly declares a
forming-data rule that has passed the evidence gate. Forming data must always
be labelled and cannot masquerade as completed evidence.

The common time frontier rejects any event learned after the decision's as-of
time. Historical replay filters by both event time and recorded/known time.

### 6.2 Neutral deterministic intelligence

Common intelligence may detect and publish observations such as swings, zones,
acceptance, rejection, displacement, volatility, indicators, sessions,
participation, and multi-timeframe relationships. Outputs carry method,
version, source evidence IDs, timestamps, freshness, and unresolved conditions.

These are facts, not candidates. Labels such as support, resistance, bullish,
bearish, trend, range, or breakout do not grant entry authority.

### 6.3 Narration and retrieval

Narration compresses supplied facts without adding prices, evidence, direction,
or action. Retrieval is allowlisted, read-only, bounded, as-of-time filtered,
and returns supporting, contradicting, missing, and freshness information.
Neither narration nor retrieval may emit a recommendation or hidden score used
as an entry gate.

## 7. Persistence and projections

### 7.1 TimescaleDB

PostgreSQL with TimescaleDB is the sole durable authority for vNext numerical
facts, immutable events, lifecycle state, model decisions, risk decisions,
orders, submissions, fills, reconciliations, and operational audit records.
There is no SQLite, JSONL, or file-backed live fallback.

Each durable write is parameterized and idempotent. A conflicting reuse of an
event, candidate, or order ID is a hard error. The event and lifecycle write
must commit before any dependent cache, projection, model call, or broker side
effect.

### 7.2 Redis

Redis is disposable working memory and coordination only. It may hold bounded
context, locks, leases, scheduling state, and cache projections with TTLs. It
is never replay, risk, order, position, or broker truth. Redis loss requires
rebuild from TimescaleDB and cannot authorize an action.

### 7.3 Neo4j

Neo4j is an asynchronous causal/provenance projection of committed TimescaleDB
events. It is populated by an idempotent outbox/worker with a durable watermark,
retry state, and rebuild path. It is not written synchronously on the entry or
order path.

Neo4j may improve bounded context but is never numerical, lifecycle, risk,
order, or broker truth. Graph unavailability or lag marks graph context stale
or unavailable; it cannot create an entry. Whether a strategy may continue
without optional graph context is a declared strategy fact requirement, not a
graph decision.

## 8. Strategy isolation and scheduling

Each enabled strategy has independent:

- immutable ID/version and magic number;
- candidate and lifecycle namespace;
- evaluation cadence and due time;
- model request and timeout budget;
- risk and exposure namespace;
- orders, positions, performance, and replay statistics;
- management policy and worker state.

Shared market facts are read-only. Strategies do not share decisions,
candidates, risk state, positions, or performance priors.

The scheduler selects due strategies but never runs their market logic. A slow
or failed strategy must not change another strategy's due time. Execution may
be serialized for GPU, broker, or account safety, but scheduling state remains
independent and durable. A distributed lease prevents multiple active vNext
service owners.

## 9. Execution, OMS, and broker truth

Only the OMS/execution boundary may call MT5 order methods. Before submission
it rechecks candidate/risk hashes, expiry, current broker quote, account type,
symbol metadata, volume step, stop constraints, exposure, and strategy
ownership.

Submission is idempotent and durably reserved before the broker call. An
ambiguous timeout or process crash enters reconciliation; it is never blindly
retried. Broker acceptance is not treated as a fill. Orders support explicit
acknowledged, partial-fill, fill, rejection, cancellation, replacement,
expiration, and failure states.

MT5 is authoritative for current account, order, deal, and position truth.
TimescaleDB is authoritative for the system's intent and audit history.
Reconciliation records and resolves differences without adopting manual,
retired, foreign-magic, or other-strategy positions.

The system must refuse non-demo accounts unless a future explicitly approved
architecture revision changes that restriction.

## 10. Position management and protection

The common system enforces only universal invariants:

- every accepted position is associated with one candidate and strategy;
- broker protection is present and reconciled;
- stop changes never widen accepted risk;
- volume is never increased after entry;
- no averaging, silent reversal, or cross-strategy adoption;
- only the owning strategy may request discretionary management;
- emergency action is limited to an explicitly approved, versioned safety
  policy and is fully audited.

All other management behavior—including early failure, break-even, trailing,
partial reduction, target extension/reduction, time exits, structure exits,
and model review cadence—is strategy-owned.

## 11. Recovery and operational safety

Startup is fail-closed and performs, in order:

1. acquire the single-instance vNext lease;
2. verify TimescaleDB schema and durable access;
3. verify Redis and rebuild disposable state;
4. verify graph connectivity/status without treating graph as broker truth;
5. initialize MT5 and verify demo account, symbol, clock, and permissions;
6. snapshot broker orders, deals, and positions;
7. reconcile broker truth with TimescaleDB intents and lifecycle;
8. block on unresolved submission, ownership, or position ambiguity;
9. load registered strategy versions and validate unique magic numbers;
10. start data, projection, strategy, management, and reconciliation workers;
11. mark execution enabled only after all mandatory health gates pass.

Shutdown stops new candidates first, then drains/persists work, releases leases,
and leaves broker protection intact. Restart never deletes or resets durable
state to make a gate pass.

## 12. Observability and evidence

Every operationally relevant action emits an immutable TimescaleDB event with
component, strategy namespace when applicable, frontier, duration, result,
normalized failure reason, and causal references. Required event families
include data ingestion, state composition, strategy transition, candidate,
model request/response, risk, order intent/submission/result, fill, management,
reconciliation, recovery, projection lag, and health.

Metrics distinguish component health from content availability. Logs may be
human-readable diagnostics, but routine file logs are not durable authority.
Secrets, full credentials, and unrestricted prompts/responses are never placed
in graph or Redis.

The local V2 operations web surface is observability-only. It binds to
localhost, reads committed TimescaleDB events, performs bounded read-only
connectivity probes for the model host, Redis, and Neo4j, and infers MT5 health
only from the freshness of durable broker-truth snapshots. It exposes no
mutation endpoint, cannot acquire a runtime lease, and cannot call MT5. This
preserves the hypothesis that the retired legacy UI's useful market, planning,
history, and trade-ledger views can be rebuilt on V2 evidence without changing
strategy or execution semantics. Reproducible supporting evidence is the
active V2 ledger plus the retired UI's ink/slate/gold information hierarchy;
contradicting evidence is that V2 does not yet persist a complete fill-to-close
trade journal, so the web surface must label its trade view as broker attempts
rather than completed trades or P&L. The hypothesis is falsified by any state
write, legacy-data dependency, direct broker call, invented market conclusion,
or failure to reject non-read HTTP methods.

For charting only, the web surface merges canonical completed candles from the
TimescaleDB `completed_candles` table with the fresher completed-bar projection
already published by the V2 cycle in TTL-bound Redis working memory. Redis may
refresh the display but never becomes durable history or trading authority.
The chart must expose missing/stale timeframes, must never construct or label a
forming candle as closed, and cannot feed data back into strategy evaluation.
The connected MT5 data adapter may publish one TTL-bound, display-only forming
candle for D1/H4/H1/M30/M15 into a Redis namespace separate from canonical
market state. Forming bars are visually distinct, carry their sample time, are
`strategy_eligible=false`, exclude M1, and are never persisted as expectations,
completed evidence, or inputs to candidate, risk, execution, or management.
Failure or staleness of this projection removes the forming candle from the
page without affecting the closed-bar cycle.

The candle ladder may persist a strategy-scoped, non-authoritative continuation
baseline at each newly observed completed M15 boundary. The expectation event
must be written before its target M15 close, identify the exact closed-candle
basis for D1/H4/H1/M30/M15, and use deterministic identity and content. When
the target M15 candle closes, a separate immutable outcome event compares its
directional contribution with every previously frozen timeframe expectation;
it never rewrites the expectation or changes candidate, target, risk, order, or
management behavior. These events are observability evidence, not forecasts or
trade authority, and are `training_eligible=false` until human review and the
curation process in `model_training/CURRICULUM_AND_DATA_PREP.md` explicitly
promote them. The proposed benefit is a causal history for measuring whether
timeframe continuation was useful; the principal harm is leakage or accidental
use as strategy authority. The design is falsified by an expectation created
after its target close, a non-idempotent replay, mutable outcomes, automatic
training inclusion, or any effect on trading decisions.

Replay must reproduce market state, strategy inputs, lifecycle, arbitration,
risk, and order intent from the same as-of frontier without broker side effects.
Outcome analysis is separate from decision evidence and cannot leak into the
past.

## 13. Activation and change gates

### 13.1 Required activation evidence

vNext remains paused until all of the following pass:

- one documented service entrypoint starts and supervises the complete vNext
  worker set; preflight-only scripts do not satisfy this;
- root and application-directory test commands collect consistently;
- all unit, contract, integration, recovery, and replay tests pass;
- required runtime dependencies are pinned and installable;
- TimescaleDB, Redis, Neo4j projection/outbox, and MT5 demo integration pass;
- strategy lifecycle is durably wired into the service loop;
- the shared scheduler is wired for every enabled strategy;
- candidate creation occurs only inside registered strategy code;
- risk produces broker-normalized volume and binds exact geometry;
- OMS rejects any order that differs from candidate or risk approval;
- ambiguous submission and partial-fill recovery are exercised;
- strategy management is wired and broker modifications are reconciled;
- retired decision/execution workers are proved stopped before vNext enables;
- leakage-safe replay covers multiple complete days and relevant regimes;
- cutover and rollback procedures preserve broker protection and durable state.

### 13.2 Change classification

Software-correctness, security, observability, packaging, and data-integrity
fixes may proceed from reproducible code/test evidence when they preserve
trading semantics.

Any change to entry, direction, setup, timeframe, zone, trigger, session,
regime, invalidation, target, risk budget, exit, management, or protection
behavior is a strategy/behavior change and must pass
`.cursor/rules/trading-change-evidence-gate.mdc`. It receives a new strategy or
contract version when semantics change.

Architecture changes update this document and tested common code together.
Strategy changes update the versioned strategy package and its doctrine; they
do not add strategy rules to this architecture.

## 14. Current implementation conformance

The repository contains a safe no-order debug worker, an explicit opt-in
demo-only worker, V2 state composition, strategy-owned M15/M1 candidate
selection, broker-normalized risk geometry, exact OMS intent validation,
cached-calendar entry gating, and a common deterministic management
orchestrator driven by strategy-owned profiles. A localhost-only, read-only V2
web dashboard projects committed operational events without broker or runtime
write access. The demo worker reconciles and
manages only the registered strategy's exact magic-number namespace. It is not
started by default. The root V2 suite is runnable through `pytest.ini`. The
following activation gaps remain as of 2026-08-31:

- the deployment preflight intentionally starts no order-enabled worker;
  `deploy/Start-QuantLLMVNext-Demo.ps1` requires a separate explicit switch
  and is limited to this demo-only, single-strategy worker;
- `MultiStrategyScheduler`, durable lifecycle transition persistence, and a
  supervised multi-strategy production service are not yet composed;
- live fill-to-position reconciliation and restart recovery are not yet wired
  from MT5 broker truth into the durable position lifecycle;
- broker management actions are wired in the opt-in demo worker, but no
  running-service endurance test has yet exercised broker modifications,
  closures, and restart recovery end to end;
- graph projection is synchronous in the persistence write path rather than an
  asynchronous TimescaleDB outbox worker;
- the 62-day replay verifies causal candidate-pipeline coverage, but does not
  yet replay contemporaneous Qwen management decisions, execution costs, fills,
  or realized outcomes; it therefore cannot establish expectancy.

These are fail-closed gaps, not permission to work around the contract. They
must be corrected and verified before production activation.
