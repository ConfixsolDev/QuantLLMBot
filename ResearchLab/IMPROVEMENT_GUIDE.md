<!-- document: QuantLLMBot improvement guide | version: 1.0 | audience: humans and LLM engineering agents -->
# QuantLLMBot Improvement Guide

## Purpose

This guide defines how improvements are proposed, tested, approved, and
released. It divides work into two independent sections:

1. **Code and architecture improvement** changes reliability, latency,
   observability, state handling, or validation without intentionally changing
   trading judgment.
2. **Strategy improvement** changes when the system enters, holds, protects,
   closes, or skips and therefore requires profitability research.

Do not hide a strategy change inside a refactor. Do not demand profitability
proof from a pure logging fix. Classify the work before editing.

This guide supplements `SYSTEM_TEXTBOOK.md`. Canonical trading knowledge and
model contracts remain in `store/core_skill.md` and `store/sop.md`. The full
profitability experiment protocol remains in `RESEARCH_LOOP.md`.

## Shared improvement loop

Every improvement follows the same evidence chain:

```text
observe -> reconcile -> classify -> hypothesize -> preregister
-> reproduce -> change one owned variable -> validate -> compare
-> paper soak -> human decision -> document -> release or reject
```

### Required proposal record

```text
Improvement ID:
Category: code_architecture | strategy
Observed problem:
Evidence IDs and version boundary:
Owning stage and files:
Mechanism or root-cause hypothesis:
One primary change:
Frozen behavior:
Primary pass metric:
Secondary diagnostics:
Regression and counter-case:
Abort condition:
Rollback method:
Human approval required at:
```

If the proposal cannot name one primary change, split it. If evidence spans
incompatible code or strategy versions, separate the cohorts before measuring.

# Section I: Code and Architecture Improvement

## Objective

Make the system more correct, reproducible, observable, restart-safe, and fast
without silently changing the market decision policy.

Examples include:

- preventing duplicate processes or proposals;
- indexing runtime state instead of scanning whole JSONL logs;
- repairing broker-deal reconciliation;
- preserving peak/giveback state after restart;
- reducing cache packet assembly time;
- detecting stale epochs or stale model decisions;
- separating entry and management services;
- improving deployment hash checks; and
- adding typed validation and deterministic fixtures.

## Architecture principles

### One owner per responsibility

- MT5 owns quotes, positions, and deals.
- Cache code owns data identity, epochs, and deterministic derived facts.
- Canonical Markdown owns trading knowledge and LLM instructions.
- Entry reviewer owns proposal formation.
- Runner owns fresh proposal consumption.
- Executor owns one fill and broker safety protection.
- Trade manager owns hold/protect/close decisions.
- Deterministic validators own permission to mutate execution state.
- Memory lifecycle owns evidence promotion.
- Unified runtime owns startup and supervision.

Duplicated ownership creates contradictory behavior. Move behavior to its owner
instead of adding another patch in a downstream layer.

### Events are immutable; current state is indexed

JSONL is the audit history. SQLite or bounded in-memory indexes are the live
state. A live loop must not repeatedly parse a growing full-history file.
Restart reconstruction should be explicit, bounded, idempotent, and tested.

### Stable contracts, replaceable implementations

Provider, cache, entry, management, execution, and learning layers exchange
typed objects. A provider/model can change only if it still satisfies the same
contract or the contract is deliberately versioned and tested.

### Fail closed at mutation boundaries

A diagnostic cache failure may report and continue refreshing. A stale or
invalid decision must not create, add to, protect, or close a position. Broker
safety protection remains available even when Qwen or the website fails.

### Observability before optimization

Every performance or correctness claim must be measurable. Record:

- snapshot, model-start, model-end, validation, order-send, and fill times;
- prompt tokens, output tokens, load, prompt-evaluation, and generation time;
- quote at snapshot, response, validation, and fill;
- cache epochs and evidence IDs;
- entry/management contract versions;
- source Git commit and deployed hashes;
- peak/giveback and every management action; and
- broker deal reconciliation.

## Engineering workflow

### 1. Reproduce

Use the smallest deterministic fixture that preserves the bug. For a runtime
incident, extract only the linked proposal, execution, position, reviews, and
deals. Keep UTC chronology. State which version produced the evidence.

### 2. Locate ownership

Examples:

- wrong candle completeness -> cache/ingestion;
- invented level accepted -> decision validation;
- duplicate order -> runner/executor ownership;
- good decision executed late -> latency/freshness boundary;
- correct peak forgotten -> position-thesis memory;
- dashboard number differs from broker -> reconciliation/view layer.

### 3. Define invariants

Write assertions before implementation. Typical invariants:

- one runtime, reviewer, runner, and Qwen position;
- one proposal processed at most once;
- one fill maps to one opening deal and one position lifecycle;
- no live-account execution;
- completed evidence never references a forming candle;
- no action after signal expiry;
- no stop widening during protection;
- no Qwen close without validated evidence; and
- source/deployment hashes match.

### 4. Implement minimally

Change the owning layer only. Preserve public schemas unless intentionally
versioning them. Avoid new runtime files when an existing indexed store or
event stream already owns the state. Never place trading doctrine in Python.

Before changing any entry, freshness, confidence, citation, cache-provenance,
or outcome-feedback gate, read `PROVEN_HARMFUL_CHANGES.md`. The proposal must
state which active rejected patterns were checked and why the implementation
does not recreate them functionally in another layer or prompt. Reopening a
rejected pattern requires its documented counter-evidence and explicit human
approval.

### 5. Test in layers

1. Pure unit/fixture test for the observed failure.
2. Contract/schema and invalid-input tests.
3. Restart/idempotence test for state changes.
4. Python compilation and static source checks.
5. `validation/validate_e2e.py`.
6. Shadow runtime or no-position health test.
7. Demo deployment only after confirming zero open positions.

### 6. Release safely

Record source hashes, deployed hashes, processes, ports, model residency, MT5
mode, open-position count, and E2E result. Commit only related files. Push the
reviewed branch. Keep rollback as a known prior commit and deployed-file set.

## Engineering acceptance gates

A code/architecture change passes only when:

- the original deterministic reproduction now passes;
- all existing E2E checks pass;
- no unrelated invariant changes;
- restart behavior is equivalent to uninterrupted behavior;
- malformed/stale inputs fail closed;
- runtime metrics demonstrate the claimed latency or resource improvement;
- source and deployment hashes match; and
- dashboard/audit outputs remain reconcilable to MT5.

Profitability is not the primary gate for a pure engineering repair, but the
repair must be checked for accidental strategy changes. If entry or exit counts
change, reclassify the affected part as strategy work.

## Architecture improvement queue

These are investigation candidates, not automatically approved changes:

1. **Active-session freshness:** ignore historical, rollover, and off-session
   gaps; treat only a stale latest/forming candle during the active weekday
   data session as missing data.
2. **Management concurrency:** allow the closed-candle confirmation guard to
   observe new evidence independently while a slow model generation is active.
3. **Indexed proposal/deal state:** eliminate remaining full-file scans in
   reviewer startup and recovery paths.
4. **Contract-version dashboard:** show source commit, SOP version, manager
   contract, model digest, and deployed hash on the website.
5. **Unified replay fixture library:** convert every material incident into a
   versioned no-look-ahead regression case.
6. **Broker reconciliation service:** continuously join proposal, execution,
   position, and deal IDs and flag orphans before research summaries run.

# Section II: Strategy Improvement

## Objective

Improve untouched broker-net expectancy through mature, explainable
market-structure behavior. A profitable day, high win rate, attractive chart,
or one repaired trade is hypothesis evidence—not proof.

Strategy work includes any change to:

- session permission or setup selection;
- level interpretation;
- entry direction, timing, or zone;
- target or invalidation selection;
- hold, protect, or close criteria;
- position size, stop geometry, or trade count; and
- model prompts containing market judgment.

## Keep entry and management experiments separate

An entry experiment asks:

- Was price at a meaningful location?
- Was the side supported by fresh rejection or acceptance?
- Was the entry late or directly into opposition?
- Was there structural room to the next level?
- Did session and participation support the setup?

A management experiment asks:

- Did the original thesis remain valid after entry?
- Which favorable levels were reached?
- Was continuation accepted or rejected?
- How much of maximum favorable excursion was captured?
- Was invalidation recognized before the broker safety stop?
- Did the model hold, protect, or close with valid evidence?

Do not change entry and exit behavior in one basic experiment. Otherwise a
better result cannot be attributed.

## Strategy evidence table

For every eligible decision, preserve:

```text
decision/proposal/execution/position/deal IDs
Git, model, prompt, SOP, core-skill, and configuration versions
closed snapshot and evidence IDs
session and volatility regime
entry plan and actual fill
spread, commission, swap, and slippage
maximum favorable and adverse price excursion
levels approached, reached, accepted, rejected, or invalidated
each hold/protect/close decision with response latency
exit reason and broker-net result
counterfactual result only from data available at that time
```

Exclude or quarantine version-unknown, orphaned, duplicate, malformed, or
unreconciled observations from confirmatory statistics.

## Metrics that matter

Primary profitability metrics:

- broker-net expectancy per eligible proposal and per filled trade;
- total broker-net result;
- profit factor;
- average win, average loss, and payoff ratio;
- break-even win rate versus observed win rate; and
- uncertainty across non-overlapping blocks.

Entry diagnostics:

- fill rate and signal-expiry rate;
- direction correctness at fixed horizons;
- entry delay and price drift;
- distance to opposing level;
- MAE before first favorable progress; and
- session/setup cohort performance.

Management diagnostics:

- maximum favorable excursion (MFE);
- maximum adverse excursion (MAE);
- captured price movement;
- profit-capture ratio: realized favorable movement divided by MFE;
- peak-to-exit giveback;
- time from level test to confirmed management action;
- invalidation-to-exit delay;
- fraction of exits by reached-level rejection, invalidation, Qwen close,
  broker safety stop, and operational failure; and
- counterfactual value of hold/protect/close at the same closed evidence point.

Never optimize win rate alone. A system with many small wins and a few full
stops can have negative expectancy.

## Strategy hypothesis template

```text
Hypothesis ID:
Entry or management:
Observation and evidence IDs:
Structural mechanism:
One strategy variable changed:
Champion behavior frozen:
Development interval:
Untouched interval:
Primary metric and minimum useful effect:
Secondary diagnostics:
Expected session/regime scope:
Counter-case:
Pass condition:
Fail condition:
Abort/safety condition:
```

The mechanism must be structural and observable from closed facts. “Ask Qwen
to make more profit” is not a hypothesis.

## Ordered strategy testing

### 1. Incident replay

Convert the motivating trade or skip into a closed-data fixture. Confirm that
the champion reproduces the behavior and the challenger changes only the
registered variable. An incident replay proves plumbing, not general edge.

### 2. Historical deterministic replay

Use chronological ticks/candles, realistic spread, commission, latency, signal
expiry, entry-zone fill logic, and the same validation path as paper execution.
No future candle, final daily high/low, or later model result may enter an
earlier decision.

### 3. Development and untouched walk-forward

Tune only on the declared development interval. Freeze the challenger before
the untouched interval. Do not repair the rule after seeing untouched results;
register a new hypothesis instead.

### 4. Robustness

Perturb spread, latency, entry price, session start, and nearby thresholds.
Test more than one volatility and directional regime. Reject improvements that
exist only at one exact value or depend on one trade/day.

### 5. Shadow comparison

Champion and challenger receive the same closed snapshot. Only the champion
executes. Record both decisions, latencies, evidence, and counterfactual
management actions without mixing account state.

### 6. Frozen demo-paper confirmation

After human approval, allow the challenger to execute on MT5 demo without
changing it inside a measurement block. Use the project evidence gates from
`RESEARCH_LOOP.md`: one 40-event block for discovery, at least three
non-overlapping blocks for confirmation, and the declared paper-soak duration
before a profitability claim.

## Entry improvement checklist

For each entry hypothesis test:

1. Identify H4/H1 location before M30/M15 path.
2. Identify the active M5-or-higher zone and its freshness.
3. Compare acceptance, rejection, and unfinished retracement.
4. Use M1 only for timing an already-grounded plan.
5. Check session permission and Asia-range relationship.
6. Confirm structural room to the next opposing level.
7. Reject a late chase or entry directly into respected opposition.
8. Record the exact invalidation and target level known at entry.
9. Keep one position and fixed experiment sizing unless size itself is the
   registered variable.

## Management improvement checklist

For each management hypothesis test:

1. Preserve the immutable entry thesis.
2. Preserve peak price, MFE, MAE, giveback, and reached levels across calls and
   restarts.
3. Separate a target touch from a confirmed target response.
4. Hold through confirmed acceptance toward the next named level.
5. Protect only after completed continuation acceptance and never widen risk.
6. Close reached-level rejection only with completed M1/M5 evidence.
7. Close immutable invalidation when completed M1/M5 accept beyond it.
8. Revalidate current live price before executing a delayed decision.
9. Measure capture ratio and confirmation delay, not only final P&L.
10. Keep broker safety protection independent of model availability.

## Learning and promotion

After every 40-event block:

1. reconcile outcomes to broker deals;
2. separate entry, direction, fill, and exit causes;
3. identify repeated structural conditions, not unconditional sides;
4. record contradictions and counter-cases;
5. create bounded hypotheses or memory proposals;
6. retain failed hypotheses to measure selection bias; and
7. require human review before doctrine or permanent memory changes.

A learned principle should read like:

```text
When [observable structural condition], prefer [bounded structural action]
until [explicit invalidation], except when [counter-case].
```

It must not read like “buy after losses,” “sell because today is bearish,” or
another outcome-contaminated directional command.

## Strategy acceptance gates

A challenger advances only when:

- the exact registered primary metric improves on untouched data;
- aggregate broker-net expectancy is positive;
- improvement is not concentrated in one trade, day, or session;
- at least two of three confirmation blocks are profitable and aggregate
  confirmation is profitable;
- costs and reasonable latency/spread perturbations do not erase the effect;
- entry and management attribution is clear;
- broker and research-ledger results reconcile; and
- the human chooses promote rather than retain or reject.

If the primary metric fails, reject the hypothesis. A favorable secondary
chart or win-rate metric cannot rescue it.

## Example: converting an incident into research

Observation: a one-position buy reached a favorable structural area and later
closed at the broker safety stop.

Incorrect reaction:

```text
Always close when profit reaches $200.
```

Researchable reaction:

```text
Hypothesis: preserving reached-level and peak/giveback state, then enforcing a
completed M1/M5 rejection at the furthest reached M5-or-higher level, improves
broker-net capture ratio without materially truncating accepted continuation.
```

The incident may become a regression fixture. Profitability promotion still
requires untouched replay and frozen paper evidence.

## LLM improvement decision tree

```text
Did market behavior intentionally change?
  no -> code/architecture section
  yes -> strategy section

Is the evidence reconciled and versioned?
  no -> repair evidence first
  yes -> write one falsifiable hypothesis

Can one deterministic fixture reproduce it?
  no -> continue diagnosis
  yes -> change the owning layer and add the fixture

Did all contracts and E2E tests pass?
  no -> do not deploy
  yes -> follow the appropriate engineering or strategy evidence gate
```

## Definition of a complete improvement

An improvement is complete only when the repository contains:

- a precise observation and version boundary;
- a classified hypothesis;
- a regression or research fixture;
- the smallest owned change;
- validation results;
- measured limitations and counter-cases;
- deployment/rollback information when applicable;
- broker reconciliation for outcome claims; and
- a human decision to promote, retain, or reject when strategy is affected.
