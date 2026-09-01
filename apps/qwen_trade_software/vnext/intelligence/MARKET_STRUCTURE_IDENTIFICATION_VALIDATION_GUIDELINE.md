# Market Structure Identification and Validation Guideline

**Status:** Common V2 capability specification  
**Scope:** Every current and future strategy, symbol, and timeframe  
**Authority:** `XAUUSD_SYSTEM_ARCHITECTURE_V2.md`  
**Primary purpose:** Produce accurate, causal, replayable market facts. This document never creates a trade, direction, entry, stop, target, or management action.

### Authority and research-source hierarchy

1. `XAUUSD_SYSTEM_ARCHITECTURE_V2.md` is the sole architecture authority.
2. This guideline is the common market-structure validation specification under
   that architecture.
3. The approved repository corpus may justify a hypothesis under the evidence
   gate, with its disagreements and instrument limitations preserved.
4. `QuantLLM_vNext_Comprehensive_Architecture_Design_Freeze.docx` is R&D input
   only. It may suggest tests or challenger mechanisms but cannot override the
   architecture, this specification, or verified replay evidence.

When sources disagree, record the disagreement and test named alternatives.
Do not silently merge definitions into a new rule.

## 1. Core principle

Market structure is an observed sequence of price events, not a label attached
to the latest candle. The engine must identify the maximum useful structure that
can be proven from completed data and must expose uncertainty when a structure
is still forming, ambiguous, stale, or invalidated.

Accuracy means:

- no future information or forming-bar leakage;
- correct timeframe authority and parent/child provenance;
- deterministic repeatability from the same bars;
- explicit confirmation and invalidation conditions;
- lifecycle continuity as new bars arrive;
- separate supporting, contradicting, and missing evidence;
- durable event IDs and replayable state transitions.

There is no meaningful “maximum accuracy” claim without an out-of-sample replay
measurement. The capability should maximize **validated information**, not the
number of labels it emits.

## 2. Separation of responsibilities

### Common market-structure capability owns

- completed-bar normalization and causal frontiers;
- swings, pivots, impulses, pullbacks, ranges, compression, expansion,
  breakouts, retests, rejection, acceptance, and structural transitions;
- zones and their interaction/lifecycle state;
- volatility, spread, participation, and data-quality facts;
- parent/child timeframe relationships;
- evidence IDs, source bars, confirmation bars, timestamps, versions, and hashes;
- deterministic validation, contradiction detection, and replay metrics.

### Strategy code owns

- which structures are relevant to its setup;
- how a validated M15 location and M1 response become a candidate;
- direction, entry, invalidation, target, session, risk budget, and management.

An engine output such as `SUPPORT`, `BOS`, `RANGE`, or `TRANSITION_CONFIRMED`
is a fact. It is never an order instruction or an implicit approval.

## 3. Canonical evidence model

Every structure observation must carry:

- `structure_id` and immutable `event_id`;
- pair, timeframe, and algorithm/version;
- event type and lifecycle state;
- source bar IDs and confirming bar IDs;
- `observed_at_utc`, source time, and confirmation time;
- price/price range, direction if descriptive, and volatility context;
- parent structures and child structures where applicable;
- supporting evidence IDs, contradicting evidence IDs, and missing facts;
- confidence components (data quality, confirmation strength, freshness), not a
  single unexplained score;
- causal state hash and `strategy_eligible=false` unless a strategy explicitly
  consumes the fact through its own contract.

The same bars must produce the same IDs and output ordering. A later bar may
confirm, weaken, break, reclaim, or invalidate a structure, but may not rewrite
the prior observation.

## 4. Structure taxonomy

### 4.1 Swing and pivot primitives

- confirmed swing high/low;
- internal and external pivot;
- higher high/lower high/higher low/lower low;
- equal high/equal low and liquidity cluster;
- protected high/low and range boundary.

A pivot requires a defined lookback/reversal rule and a later confirming bar.
The source bar and confirmer must both be recorded. A transient wick is not a
confirmed break.

### 4.2 Movement and auction states

- impulse/displacement;
- pullback/retracement;
- continuation;
- range/balance;
- compression/coiling;
- expansion/volatility release;
- exhaustion/climax;
- transition warning and transition confirmed.

Each state needs mechanical predicates, minimum observations, and a clear
reversal condition. “Trend” is a derived state from a sequence of pivots, not
the sign of one candle.

### 4.3 Break and response structures

- break of structure (BOS);
- change of character (CHoCH/MSS);
- acceptance beyond a level;
- rejection/failure at a level;
- breakout retest;
- failed breakout and reclaim;
- continuation retest.

A break requires closed-bar acceptance beyond the authoritative level plus the
declared confirmation rule. A wick through a level is an interaction, not an
accepted break.

### 4.4 Zones and levels

Zones must preserve bounds, width, birth bars, lifecycle, density, rejection
statistics, and every interaction. Interactions are classified at minimum as
`TOUCH`, `ACCEPTED`, `REJECTED`, `BROKEN`, or `RECLAIMED`.

The current `ZoneEngine` is an R&D baseline based on volatility-scaled body
clustering. It is useful as an inspectable starting point, not a final claim of
optimal zone detection. Future algorithms must be versioned and compared with
the same replay fixtures.

## 5. Lifecycle: how structure develops

Every structure follows an explicit state machine:

`CANDIDATE -> FORMING -> CONFIRMED -> ACTIVE -> TESTED -> BROKEN -> RECLAIMED -> INVALID`

Not every structure uses every state, but no implementation may silently jump
from an unconfirmed observation to a strategy-eligible fact.

For each new completed bar, the validator must answer:

1. What structure existed at the prior frontier?
2. What new bar changed, confirmed, contradicted, or left it unchanged?
3. Which parent/child structures are now aligned, pulling back, compressing, or
   transitioning?
4. Is the structure still fresh and actionable for a consuming strategy?
5. What exact event caused the transition?

A broken structure is not deleted. It remains in history and may become
`RECLAIMED` only through a new, independently evidenced acceptance sequence.

## 6. Timeframe hierarchy

Timeframe authority is explicit:

- D1/H4: broad location, regime, and major path;
- H2/H1: parent swing and directional context;
- M30/M15: executable location, zone, and structural objective;
- M5/M1: response, trigger timing, and local path only.

Lower-timeframe facts cannot break a higher-timeframe level by themselves.
M15 builds its own structure from completed M15 bars; M1 cannot be substituted
for an M15 close. Parent/child relationships must cite both timeframes and
remain `UNKNOWN` when either side lacks adequate evidence.

## 7. Validation layers

### Layer A — Data and causality

- timestamps are timezone-aware UTC;
- bars are complete and ordered with no future rows;
- duplicate, missing, overlapping, or out-of-order bars are reported;
- the frontier excludes forming bars unless explicitly labelled and never feeds
  strategy eligibility;
- source and confirmation bars are at or before the event frontier.

### Layer B — Geometry and invariants

- high >= open/close >= low;
- zone upper > lower;
- prices, ranges, and volatility are finite and positive where required;
- event IDs are content-derived and stable;
- lifecycle transitions are allowed by the versioned state machine;
- no structure is simultaneously confirmed and invalid without a transition.

### Layer C — Structural confirmation

- pivots have a confirmer;
- BOS has closed acceptance and a level reference;
- rejection has a touch/penetration and close-away response;
- retest follows a prior break and does not reuse the same evidence as both break
  and retest;
- trend/transition labels cite the pivot sequence that supports them;
- range boundaries have repeated tests or an explicitly declared minimum rule.

### Layer D — Cross-timeframe coherence

- parent and child timestamps are causally compatible;
- child movement is classified as continuation, pullback, compression, or
  transition relative to the parent;
- conflicting evidence is reported, not averaged away;
- no lower-timeframe label silently overrides higher-timeframe authority.

### Layer E — Replay validation

Run the detector over multiple complete sessions and regimes. Measure:

- confirmation precision and false-confirmation rate;
- detection delay from source event to confirmation;
- missed-event rate and duplicate-event rate;
- zone touch/rejection/break classification accuracy;
- lifecycle transition consistency;
- parent/child relationship accuracy;
- stability under small data corrections and restart/replay;
- downstream strategy eligibility errors and rejected references.

Metrics must be reported by symbol, timeframe, session, volatility regime, and
structure type. Do not optimize on the same period used to judge accuracy.

### Repeatable validation procedure

Use this sequence whenever market-structure validation is requested:

1. Freeze the symbol, timeframe, completed-bar frontier, detector version, rule
   series, parameters, and data-quality report before inspecting later bars.
2. State the exact hypothesis, affected fact path, expected benefit, possible
   harm, and falsification test required by the evidence gate.
3. Name the structure definition being tested. Distinct definitions such as a
   strict Grimes pivot, permissive Brooks swing, or directional-change swing
   remain separate challenger series with separate event namespaces.
4. Create or select positive, negative, boundary, and adversarial fixtures. Each
   fixture states its last knowable bar and expected verdict before execution.
5. Run deterministic detection, then independently recompute conformance from
   the cited source and confirmation bars. Never ask an LLM to repair geometry.
6. Label each observation `VALID`, `INVALID`, or `INSUFFICIENT_EVIDENCE`, cite
   the first broken causal link, and preserve contradictions and missing facts.
7. Replay incrementally at every completed-bar frontier and after restart. The
   prior event history must remain immutable; later evidence creates a new
   transition rather than editing an earlier state.
8. Score against a versioned, human-reviewed oracle set and report confusion
   counts, abstentions, delay, duplicates, misses, and disagreement by regime.
9. Compare the challenger with the current baseline on untouched periods. A
   detector is not improved when it merely emits more labels or looks cleaner.
10. Promote, retain in research, or veto. Activation and strategy consumption
    remain out of scope unless separately authorized and release-gated.

Human annotation must be blind to subsequent trade P&L. Ambiguous examples are
kept as `INSUFFICIENT_EVIDENCE`, not forced into the nearest class. Outcome
statistics may test downstream usefulness later, but they do not establish
whether an earlier structural fact was causally valid.

## 8. LLM validation protocol

The LLM receives a bounded structure packet containing the algorithm version,
completed bars, event sequence, source/confirmation IDs, lifecycle history,
parent/child relations, contradictions, and deterministic validator results.

It returns only:

`VALID | INVALID | INSUFFICIENT_EVIDENCE`

with:

- the rule IDs evaluated;
- supporting and contradicting evidence IDs;
- the first missing or broken causal link;
- whether the structure is strategy-eligible;
- a minimal repair suggestion for the detector or evidence packet.

The LLM must not:

- invent a price, bar, level, timestamp, or structure;
- turn a wick into a close-based break;
- call a structure “confirmed” when required evidence is missing;
- choose buy/sell or create a candidate;
- replace deterministic geometry or lifecycle validation;
- use subsequent price outcomes to validate an earlier frontier.

The deterministic validator is authoritative. The LLM is a bounded reviewer
that improves diagnosis and coverage, not a hidden signal generator.

## 8.1 Probability and level-quality policy

Probability is an empirical estimate of a defined future event, not a visual
confidence score. The capability may publish probability metadata only when it
can name:

- the event being predicted (for example, “M15 support holds through the next
  three completed M1 bars”);
- the observation frontier and the future evaluation horizon;
- the structure/zone features available at that frontier;
- the outcome label and its censoring rule;
- the sample count, regime/session slice, and calibration method;
- uncertainty bounds and a `probability_status` of `CALIBRATED`, `SHADOW`, or
  `INSUFFICIENT_SAMPLE`.

Use leakage-safe historical labels with time-ordered train/calibration/test
splits. Apply smoothing for sparse level types, report a base rate, and measure
reliability (calibration error), discrimination, and stability by timeframe and
regime. A probability is not strategy-eligible merely because it is high.

Until the detector has sufficient out-of-sample labels, publish components such
as confirmation strength, freshness, interaction count, and parent/child
agreement as facts, not a fabricated probability. Strategies may use a
calibrated probability only when their own definition explicitly permits it and
the release gate records the minimum sample and kill criteria.

The LLM may explain why a level's evidence is strong or weak, but it must not
invent a probability, convert confidence language into a numeric edge, or use
future outcomes while reviewing the original decision frontier.

## 9. Strategy-consumption contract

Before a strategy may consume a structure, it must declare:

- allowed structure types and timeframes;
- minimum lifecycle state (`CONFIRMED`, `ACTIVE`, or `TESTED`);
- freshness limit and re-use policy;
- required supporting/contradicting evidence;
- parent/child coherence requirements;
- what invalidates the setup;
- the exact fields passed into the strategy packet.

The common capability rejects stale, unresolved, cross-timeframe, or
future-dated references. The strategy then decides whether the valid fact is
relevant to its own setup.

## 10. Test and fixture library

Maintain positive and negative fixtures for:

- clean swing confirmation;
- wick-only false break;
- accepted break and valid retest;
- failed breakout and reclaim;
- range with repeated tests;
- compression-to-expansion transition;
- higher-timeframe/child-timeframe conflict;
- missing bar, duplicate bar, forming bar, and stale evidence;
- restart/replay producing identical event IDs;
- invalid lifecycle transition and contradictory evidence.

Every fixture must state the frontier and expected output. Include adversarial
cases designed to expose look-ahead, nearest-zone selection, duplicate events,
and accidental strategy conclusions.

## 11. Release gates for market-structure capability

A detector version is eligible for strategy use only when:

1. causal and geometry validators pass;
2. deterministic replay is repeatable;
3. positive and negative fixtures pass;
4. metrics are reported across multiple sessions and regimes;
5. known limitations and contradictions are documented;
6. event persistence, IDs, and restart recovery are verified;
7. the LLM conformance review cites the same evidence packet;
8. the consuming strategy declares the structure contract explicitly.

Changing detection logic requires a new algorithm version and a comparison
report. A strategy must not silently consume a new detector version.

## 12. Current V2 baseline and next work

The current V2 baseline provides:

- causal permissive swing confirmation in `intelligence/structure/engine.py`,
  explicitly namespaced as `BROOKS_PERMISSIVE_REVERSAL_V1` rather than silently
  conflated with the strict pivot series;
- content-derived source/confirmation bar evidence IDs, explicit confirmation
  provenance, algorithm/rule version, lifecycle state, and
  `strategy_eligible=false` on every swing event;
- deterministic conformance validation in
  `intelligence/structure/validation.py` for homogeneous series, unique and
  adjacent bars, causal frontier, replay equivalence, and event provenance;
- volatility-scaled zone discovery and interaction tracking in
  `intelligence/zones/engine.py`;
- explicit parent/child relationship classification;
- immutable `PAIR_MARKET_STATE_V1` with structural events, zones, and hashes.

The next capability improvements should be implemented in this order:

1. add lifecycle-aware BOS/CHoCH, acceptance, rejection, and retest events;
2. persist structure transitions and contradictions as immutable events;
3. add conformance validators and adversarial fixtures;
4. add MFE-independent structure quality metrics and replay reports;
5. expose only validated facts to strategy packets;
6. review each strategy weekly without allowing outcomes to rewrite structure
   history.

Before any strategy consumes multi-level probability, add independently causal
structure detection for M15, M30, H1, H2, H4, and D1. The current baseline's
M1-only swing detector and last-bar timeframe direction are not sufficient for
that capability.

## 13. One-minute structure R&D matrix

These patterns are research candidates for M1 execution around an independently
validated higher-timeframe level. None is a standalone signal and none is
approved for live trading without the replay gates above.

### Double top / double bottom

**Definition:** two confirmed same-side pivots within a declared volatility
tolerance, separated by a minimum/maximum bar distance, followed by a close
through the intervening neckline. The second pivot alone is not a signal.

**Required evidence:** both pivot confirmations, price-distance tolerance,
neckline ID, neckline-break close, and the M15 parent zone or level.

**Preliminary diagnostic:** a simple 30-day XAUUSDr M1 probe produced 1,320
double-top candidates and 1,390 double-bottom candidates. Under a deliberately
simple one-range target/stop rule and before spread/slippage, target-before-stop
was approximately 62% for tops and 58% for bottoms among resolved signals. This
is not a profitability result: signals overlap, the detector is not yet
lifecycle-aware, and costs/regime/session conditioning were not included.

### Initial level touch / first response

**Definition:** the first post-creation touch of a fresh M15 zone, followed by a
completed M1 rejection or reclaim in the zone's direction. Do not enter merely
because price is near a level.

**Required evidence:** zone birth, first-touch timestamp, penetration,
close-away response, response bar ID, and invalidation beyond the zone.

**Current limitation:** `ZoneEngine` defines interaction classification, but
`VNextEngine.compose_state()` currently discovers zones without publishing a
causal interaction history. This pattern cannot be evaluated honestly until
those interactions are persisted and replayable.

### Breakout-retest / failed-break reclaim

**Definition:** a closed-bar acceptance beyond an M15 level, followed by a
bounded retest that holds (continuation) or fails back through the level
(reclaim/reversal).

**Required evidence:** pre-break level, acceptance close, retest event, hold or
failure close, and parent-timeframe context. A wick-only excursion is excluded.

### Sweep-and-reclaim

**Definition:** price trades beyond a prior equal high/low or range boundary,
then a completed M1 close returns inside the level with a rejection extreme.

**Required evidence:** prior liquidity cluster, sweep range, reclaim close,
spread/volatility context, and M15 location. This is especially sensitive to
spread and news conditions.

### Compression-to-expansion

**Definition:** a measurable contraction in M1 ranges/dispersion near an M15
level followed by a closed-bar expansion and acceptance in one direction.

**Required evidence:** compression window, volatility baseline, expansion
threshold, acceptance close, and higher-timeframe alignment. Do not classify a
single large candle as a complete pattern.

### Continuation pullback

**Definition:** an already confirmed parent-direction BOS/impulse, followed by a
pullback into the broken level or M15 zone and a fresh M1 continuation response.

**Required evidence:** parent BOS, level/retest identity, pullback containment,
continuation close, and invalidation below/above the retest structure.

## 13.1 Pattern comparison protocol

For each candidate pattern, compare the same entry, stop, target, and cost model
across identical M1 bars. Report resolved target-before-stop, expectancy after
costs, MFE/MAE, time-to-resolution, false-confirmation rate, and results by
parent level type, session, direction, and volatility regime. Use disjoint
episodes so one price movement cannot count as many independent successes.

The first implementation priority is not the pattern with the highest
preliminary hit rate. It is the pattern with the clearest causal definition,
lowest ambiguity, and complete evidence path. Based on the current audit, the
order is: first-touch response after interaction persistence, breakout-retest,
double-top/bottom neckline break, sweep-reclaim, continuation pullback, then
compression-expansion. This ordering is a research priority, not a trading
recommendation.

## 13.2 Probability promotion rule for patterns

After enough labelled, non-overlapping episodes, estimate each pattern's
conditional probability separately for each parent-level and regime slice. Use
time-ordered calibration/test periods and publish the base rate, sample size,
uncertainty, and calibration error. A high double-top rate in one 30-day sample
must not be generalized to XAUUSD, another session, or another strategy.

## 13. R&D intake from the non-authoritative design-freeze document

The design-freeze Word document was reviewed on 2026-09-01 as a guideline only.
Its useful proposals are converted into the following bounded research status:

- **Adopted as validation principles:** separate observed, confirmed, effective,
  and invalidated times; preserve per-event provenance; represent break
  penetration, provisional close, acceptance, failure, and reclaim as one
  lifecycle; replay every frontier; promote only after out-of-sample shadow
  comparison.
- **Already consistent with V2:** common structure remains strategy-agnostic;
  timeframes retain independent state; LLMs review supplied facts but do not
  calculate swings, BOS/CHoCH, or geometry.
- **Challenger research only:** a directional-change swing that tracks an
  extreme until a context-conditioned reversal threshold is met. It must be
  versioned separately from strict and permissive adjacent-bar pivot series and
  must beat them on causal replay metrics before promotion.
- **Deferred pending XAUUSD evidence:** context-conditioned thresholds,
  statistical swing-importance classes, percentile displacement, equal-high/low
  clustering, and consequence-based internal/major/external authority.
- **Leakage constraint:** later excursion, reactions, BOS consequence, or parent
  propagation may append a later authority update; they may never backfill the
  authority or eligibility known at the original confirmation frontier.
- **Not a truth metric:** improved zone-conditioned returns or trade outcomes
  can test downstream usefulness, but cannot validate the historical correctness
  of a structure label. Primary validation remains causal classification against
  a versioned oracle and deterministic replay.

No production structure, strategy behavior, or architecture authority is
changed by this R&D intake.

## 14. External R&D synthesis and source audit

This section records the 2026-09-01 paper, official-documentation, and source
implementation audit. External code is comparative evidence only; it is never
copied into V2 or treated as proof of detection quality.

### 14.1 Primary research findings

- Lo, Mamaysky, and Wang formalize classical chart patterns from sequences of
  smoothed local extrema and demonstrate that objective definitions can be
  statistically evaluated. Their daily US-equity results do not establish
  intraday XAUUSD accuracy.
- Wan and Si compile formal specifications for 53 chart patterns and show why
  unambiguous definitions must precede classification. Segmentation choice and
  cross-market transfer remain material limitations.
- Aloud, Tsang, Olsen, and Dupuis define directional-change events as fixed
  reversals from running extrema in intrinsic time. This supports a causal,
  multi-threshold swing challenger, not an assumed universal threshold.
- Chung and Bellotti find that discovered support/resistance bounce behaviour
  depends on prior interactions and decays over time, including results on
  EURUSD and Brent. This directly supports time-varying zone lifecycle tests and
  matched shuffled-return controls.
- Osler finds that published FX support/resistance levels predict trend
  interruptions and documents clustering of take-profit and stop-loss orders.
  This supports testing zones and rapid post-break movement; it does not prove
  that every equal high, wick, or round number is a liquidity sweep.
- Adams and MacKay provide causal Bayesian online change-point inference. This
  is a statistically grounded challenger for transition/regime warnings, but it
  does not map automatically to the practitioner term CHoCH.
- Sullivan, Timmermann, and White, Hansen, and Bailey et al. show why testing
  many rule variants creates false discoveries. Detector selection must record
  every attempted definition and use untouched time blocks; choosing the best
  of many thresholds from the evaluation set is prohibited.

### 14.2 Maintained implementation audit

- QuantConnect LEAN's `PivotPointsHighLow` uses a rolling window of
  `2*k+1`, emits only after the right-side bars arrive, and explicitly separates
  strict from relaxed inequalities. This is a sound reference for honest
  confirmation lag and named rule series.
- LEAN's `ZigZag` tracks a running extreme and changes direction after a
  sensitivity threshold plus minimum trend length. Its developing extreme may
  update; V2 may compare it only if confirmed events are separated from mutable
  working state.
- Freqtrade's lookahead analysis reruns sliced histories and compares outputs
  with the full-data baseline. V2 should implement the stronger prefix property:
  results from the first `n` bars must equal all full-replay events knowable by
  frontier `n`.
- TA-Lib provides many reproducible candlestick functions but not a complete
  causal market-structure lifecycle. Candlestick coverage cannot be reported as
  BOS, regime, range, or classical-structure coverage.
- The community `market-structure-engine` repository documents useful prefix,
  one-break-per-level, and batch/stream parity tests. Its BOS/CHoCH definitions
  remain implementation examples without independent empirical authority.
- The community `smart-money-concepts` implementation uses centered future
  windows (`shift` with negative offsets) for swings, future scans for broken or
  mitigated indices, and whole-data extrema for liquidity width. Those results
  are retrospective annotations unless re-emitted at their true later
  confirmation frontier. They are not admissible as a live causal oracle.

### 14.3 Current V2 implementation audit

The current code is an early baseline, not a full market-structure engine:

- only `permissive_swing` is detected in the structure package;
- strict, directional-change, and higher-order pivot series are absent;
- HH/HL/LH/LL, regime, protected swing, scale, BOS/CHoCH, acceptance,
  rejection, sweep, retest, range, compression, displacement, FVG, order-block,
  and classical-pattern detectors are absent;
- the zone engine has baseline clustering and interaction states, but no
  matched-control, decay, cross-broker, or oracle qualification;
- the MTF classifier can classify supplied states but the runtime currently
  feeds latest-candle direction and a latest-swing direction, not validated
  per-timeframe structure states;
- candidate replay proves frontier filtering and candidate coverage only. It
  does not measure structure precision, recall, abstention, detection delay, or
  lifecycle consistency;
- no catalog entry is `VALIDATED`, `SHADOW`, or `FROZEN` as of this audit.

The common runtime's latest-candle/latest-swing direction shortcut is a P0
architecture-conformance blocker for a future structure freeze. Removing or
replacing it may affect strategy behaviour, so it is recorded here and must be
handled as a separately evidence-gated change rather than hidden inside this
R&D documentation pass.

## 15. Rating method

The machine-readable authority for these ratings is
`intelligence/structure/catalog.py`, version `MARKET_STRUCTURE_CATALOG_V1`.
Ratings assess detection readiness, never profitability.

- **Evidence grade (E0-E4):** E0 no support; E1 practitioner/community naming;
  E2 formal or corpus definition with limited empirical support; E3 primary
  formal/empirical support with transfer limits; E4 multiple directly relevant
  empirical routes.
- **Causal-detectability grade (D0-D4):** D0 undefined; D1 substantially
  retrospective/subjective; D2 operationalizable with major ambiguity; D3
  deterministic but parameter-sensitive; D4 deterministic from completed data
  with explicit confirmation.
- **Implementation grade (I0-I4):** I0 absent; I1 placeholder or partial state;
  I2 baseline code and focused tests; I3 causal detector plus adversarial and
  oracle replay; I4 multi-period, multi-regime, restart, correction, and shadow
  qualification.
- **Stage:** `RESEARCH`, `SPECIFIED`, `BASELINE_IMPLEMENTED`, `VALIDATED`,
  `SHADOW`, or `FROZEN`. A structure cannot skip a stage.

## 16. Complete structure qualification register

### 16.1 Foundations

- **Strict first-order pivot** (`strict_pivot`) — E3/D4/I0; `SPECIFIED`.
  Clear completed-bar definition; separate implementation is absent.
- **Permissive adjacent-bar swing** (`permissive_swing`) — E2/D4/I2;
  `BASELINE_IMPLEMENTED`. Provenance and validators exist; oracle replay does not.
- **Directional-change swing** (`directional_change_swing`) — E3/D3/I0;
  `RESEARCH`. Strong challenger; XAUUSD thresholds remain unqualified.
- **Recursive higher-order pivot** (`higher_order_pivot`) — E2/D3/I0;
  `SPECIFIED`. Variable confirmation lag and non-alternation must be preserved.
- **HH/HL/LH/LL sequence** (`swing_sequence`) — E3/D4/I0; `SPECIFIED`.
  Deterministic only after one named swing series is selected.
- **Equal-high/equal-low cluster** (`equal_extreme_cluster`) — E2/D3/I0;
  `SPECIFIED`. This is a volatility/tick-size zone, not literal equality.
- **Protected/meaningful swing** (`protected_swing`) — E1/D2/I0; `RESEARCH`.
  No agreed causal definition currently qualifies it.
- **Internal/major/external scale** (`structure_scale`) — E2/D2/I0;
  `RESEARCH`. Later consequences may append authority but cannot rewrite history.

### 16.2 Movement and auction state

- **Impulse/displacement** (`impulse`) — E2/D3/I0; `SPECIFIED`.
  Conditional closed-bar percentiles require XAUUSD calibration.
- **Pullback/retracement** (`pullback`) — E2/D3/I0; `SPECIFIED`.
  It is a parent-relative geometric fact, not a continuation forecast.
- **Structural continuation** (`continuation`) — E2/D3/I0; `SPECIFIED`.
  Requires a parent state and independently accepted new progress.
- **Up/down/range/transition/unknown regime** (`trend_regime`) — E3/D2/I0;
  `SPECIFIED`. Current latest-bar direction is not this detector.
- **Range/balance** (`range_balance`) — E2/D2/I0; `SPECIFIED`.
  Requires repeated boundary evidence plus central acceptance.
- **Compression/coiling** (`compression`) — E2/D3/I0; `SPECIFIED`.
  A multivariate contraction definition is feasible but uncalibrated.
- **Expansion/volatility release** (`expansion`) — E2/D3/I0; `SPECIFIED`.
  Must cite prior compression or an explicit baseline distribution.
- **Exhaustion/climax** (`exhaustion`) — E1/D2/I0; `RESEARCH`.
  Confirmation must be a later failure event, never hindsight from reversal size.

### 16.3 Break and response lifecycle

- **Level penetration/wick interaction** (`level_penetration`) — E3/D4/I1;
  `BASELINE_IMPLEMENTED`. Zone interaction code exists; structural provenance is incomplete.
- **Provisional close break** (`provisional_break`) — E3/D4/I0; `SPECIFIED`.
  One completed close outside a cited authoritative zone.
- **Accepted/confirmed break** (`accepted_break`) — E3/D3/I0; `SPECIFIED`.
  Acceptance must be declared for the level's owning timeframe.
- **Break of structure** (`bos`) — E1/D3/I0; `SPECIFIED`.
  The break can be formalized, but BOS has no primary empirical standard.
- **CHoCH/MSS transition** (`choch_mss`) — E1/D2/I0; `RESEARCH`.
  One counter-swing cross is not sufficient evidence of regime transition.
- **Rejection/liquidity sweep** (`rejection_sweep`) — E2/D3/I0; `SPECIFIED`.
  Order clustering supports testing, not an institutional-motive assertion.
- **Failed break and reclaim** (`failed_break_reclaim`) — E3/D4/I0;
  `SPECIFIED`. The return and re-acceptance sequence is causally testable.
- **Breakout retest** (`breakout_retest`) — E2/D3/I0; `SPECIFIED`.
  It must use evidence later than and independent of the original break.
- **Continuation retest** (`continuation_retest`) — E2/D3/I0; `SPECIFIED`.
  It is a retest subtype and has no independent trade authority.

### 16.4 Zones and imbalance

- **Support/resistance zone** (`support_resistance_zone`) — E4/D3/I2;
  `BASELINE_IMPLEMENTED`. Matched controls, decay, and oracle replay are missing.
- **Support/resistance role reversal** (`role_reversal`) — E3/D3/I1;
  `BASELINE_IMPLEMENTED`. A generic `RECLAIMED` state is not full qualification.
- **Three-candle fair-value gap** (`fvg`) — E1/D4/I0; `SPECIFIED`.
  Geometry is clear after the third bar; structural significance is unsupported.
- **Order-block/impulse-origin candidate** (`order_block`) — E1/D2/I0;
  `RESEARCH`. OHLCV cannot prove institutional orders; use neutral origin-zone wording.

### 16.5 Classical structures

- **Double top/bottom** (`double_top_bottom`) — E3/D3/I0; `SPECIFIED`.
  Formal extrema geometry exists; XAUUSD intraday validation is absent.
- **Triple top/bottom** (`triple_top_bottom`) — E2/D3/I0; `SPECIFIED`.
  Formal shape exists but is sensitive to tolerance and segmentation.
- **Head-and-shoulders/inverse** (`head_shoulders`) — E3/D3/I0;
  `SPECIFIED`. Completion requires a causal neckline break after five-extrema geometry.
- **Ascending/descending/symmetric triangle** (`triangle`) — E3/D2/I0;
  `SPECIFIED`. Segmentation and trendline tolerance dominate disagreement.
- **Flag/pennant** (`flag_pennant`) — E2/D2/I0; `RESEARCH`.
  Pole, consolidation, duration, and breakout must all be made objective.
- **Price channel** (`channel`) — E2/D3/I0; `SPECIFIED`.
  Robust line fitting is feasible; implementation and oracle are absent.

Current coverage is therefore four of 35 catalog entries with any implementation
work, zero of 35 validated, and zero of 35 frozen. This is an honest baseline,
not a quality failure to conceal.

## 17. Longitudinal evaluation and freeze protocol

Every detector evaluation is recorded as immutable `STRUCTURE_EVALUATION_V1`
using `intelligence/structure/evaluation.py`. Production persistence belongs in
TimescaleDB; JSON/CSV files must not become live truth.

Each record fixes detector version, oracle version, broker/data identity,
symbol, timeframe, period, session, regime, counts, abstentions, detection
delays, duplicates, prefix violations, event-ID instability, and lifecycle
violations. Report at least:

- precision, recall, F1, and `INSUFFICIENT_EVIDENCE` rate;
- source-to-confirmation delay in bars and seconds;
- duplicate and missed-event counts;
- prefix, restart, and event-ID stability;
- lifecycle-transition consistency;
- correction sensitivity and cross-broker agreement;
- results by month, session, volatility regime, timeframe, and structure type.

### 17.1 Oracle construction

1. Select complete XAUUSD periods before detector tuning, including trend,
   range, compression, expansion, news, rollover, and missing-data cases.
2. Two reviewers independently label exact source, confirmer, state, and first
   invalidation frontier without seeing later trade outcomes.
3. Disagreements are adjudicated or retained as `INSUFFICIENT_EVIDENCE`.
4. Freeze the oracle version and hash before detector comparison.
5. Keep discovery, calibration, validation, and final holdout periods separate.

### 17.2 Required temporal tests

- **Prefix test:** each frontier's output equals the subset knowable then from a
  full replay; no event may move backward in time.
- **Restart test:** replay from persisted history produces identical IDs,
  ordering, state, and contradictions.
- **Correction test:** small broker corrections create versioned replacements or
  contradictions, never silent history edits.
- **Boundary test:** sessions, weekends, rollover, missing bars, duplicates, and
  higher-timeframe closes do not create synthetic structures.
- **Drift test:** monthly metrics and detection rates are compared with the
  frozen reference distribution; deterioration triggers review, not auto-tuning.

### 17.3 Freeze gates

A structure may become `FROZEN` only when all of these are true:

1. its definition, dependencies, lifecycle, invalidation, and abstention cases
   are versioned;
2. deterministic and adversarial fixtures pass;
3. causal prefix, restart, correction, and ID-stability tests have zero failures;
4. a blinded XAUUSD oracle report covers multiple complete days, sessions, and
   relevant regimes on untouched data;
5. precision, recall, delay, and abstention acceptance bounds were declared
   before the final holdout and are met in every required slice;
6. materially different definitions were compared with data-snooping controls;
7. limitations and contradicting evidence are recorded;
8. shadow output remains stable before any strategy declares a consumption contract.

There is no global “everything is awesome” switch. Freeze foundations first,
then break lifecycle, then auction states, then optional classical structures.
Strategies may depend only on the exact frozen detector versions they declare.

## 18. Source register

- **R1:** [Lo, Mamaysky & Wang — Foundations of Technical Analysis](https://www.nber.org/papers/w7613)
- **R2:** [Wan & Si — A formal approach to chart patterns classification](https://doi.org/10.1016/j.ins.2017.05.028)
- **R3:** [Aloud et al. — Directional-Change Events](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1973471)
- **R4:** [Chung & Bellotti — Evidence and Behaviour of Support and Resistance](https://arxiv.org/abs/2101.07410)
- **R5:** [Osler — Currency Orders and Exchange Rate Dynamics](https://doi.org/10.1111/1540-6261.00588)
- **R6:** [Adams & MacKay — Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
- **R7:** [Sullivan, Timmermann & White — Data Snooping and Technical Rules](https://www.fmg.ac.uk/publications/discussion-papers/data-snooping-technical-trading-rule-performance-and-bootstrap)
- **R8:** [Hansen — Test for Superior Predictive Ability](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569)
- **R9:** [Bailey et al. — Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
- **G1:** [QuantConnect LEAN PivotPointsHighLow source](https://github.com/QuantConnect/Lean/blob/master/Indicators/PivotPointsHighLow.cs)
- **G2:** [QuantConnect LEAN ZigZag source](https://github.com/QuantConnect/Lean/blob/master/Indicators/ZigZag.cs)
- **G3:** [Freqtrade lookahead-analysis source documentation](https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md)
- **G4:** [TA-Lib official core](https://github.com/TA-Lib/ta-lib)
- **G5:** [Community market-structure-engine](https://github.com/kayasolomon/market-structure-engine)
- **G6:** [Community smart-money-concepts source](https://github.com/joshyattridge/smart-money-concepts/blob/master/smartmoneyconcepts/smc.py)

Internet and repository observations are dated 2026-09-01. Their future changes
do not silently alter this catalog; a new audit must update the catalog version.
