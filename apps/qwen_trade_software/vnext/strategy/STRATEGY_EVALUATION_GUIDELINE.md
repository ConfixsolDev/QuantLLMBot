# Strategy Evaluation Guideline — V2 M15-Zone / M1-Execution Strategies

**Status:** Research and evaluation contract; not an activation approval  
**Scope:** Every current and future strategy, evaluated one at a time  
**Authority:** The V2 strategy contract, `store/core_skill.md`, `store/sop.md`, and the trading-change evidence gate

This document is a practical guideline for evaluating, improving, and approving
the eight planned strategies one by one. It does not replace
`XAUUSD_SYSTEM_ARCHITECTURE_V2.md`, and it does not authorize live changes by
itself.

The governing principle is **conformance before optimization**. A strategy is
not allowed to optimize, learn from outcomes, or trade continuously until its
implementation demonstrably behaves exactly as its own definition says it
should behave.

## 0. Three-stage lifecycle for every strategy

### Stage 1 — Make it behave as defined

The strategy definition is the specification. The implementation, prompts,
candidate builder, risk geometry, execution adapter, and manager must be traced
against it line by line. This stage fixes broken wiring, missing evidence,
wrong timeframe use, stale references, incorrect units, and unsafe defaults.
No profitability claim is made here.

The stage is complete only when deterministic contract tests, fixture replays,
and an LLM conformance review agree that:

- every required input is present and causal;
- every declared rule has an executable owner;
- every forbidden behavior is rejected;
- entry, stop, target, expiry, and management match the definition;
- broker intent and durable audit records preserve the same decision;
- failure and missing-data paths fail closed.

### Stage 2 — Improve the defined strategy

Only after Stage 1 passes may hypotheses change entry selectivity, geometry,
management, targets, sessions, or risk. Each change requires the trading-change
evidence gate, a baseline, a falsifiable experiment, leakage-safe replay, and
an immutable new strategy version. A higher win rate alone is not an
improvement.

### Stage 3 — Trade and review weekly

After explicit activation approval, the strategy trades within its declared
scope. A weekly review evaluates execution fidelity, data quality, risk,
management, costs, and performance by regime. Weekly outcomes may create new
research hypotheses, but they may not silently rewrite the live contract.

## 0.1 LLM conformance validation

The LLM is a contract reviewer and evidence interpreter, not a substitute for
the strategy specification or replay engine. For each strategy version it
receives only a bounded package containing:

- the immutable strategy definition and management parameters;
- the relevant V2 architecture and doctrine excerpts;
- the exact candidate, risk, order, position, and management events;
- completed-bar evidence IDs and the causal state hash;
- validator results and any missing/contradicting facts.

It must return a structured conformance result:

`PASS | FAIL | INSUFFICIENT_EVIDENCE`

with rule IDs, cited evidence IDs, the first broken lifecycle link, and a
minimal repair description. It must not output an order, alter direction or
geometry, fill missing prices, or infer correctness from P&L. `PASS` means the
implementation followed the definition for the supplied case; it does not mean
the strategy is profitable.

The deterministic validator remains authoritative for schemas, timestamps,
timeframe roles, state hashes, prices, volume, broker protection, risk limits,
and lifecycle ordering. The LLM may explain and cross-check those facts, but it
cannot override a validator failure. This makes a broken strategy diagnosable
from one failing fixture rather than requiring a long period of user feedback.

## 0.2 Conformance checklist

Before any improvement experiment, generate a strategy conformance report with:

1. Definition-to-code ownership map.
2. Input and timeframe provenance map.
3. Entry rule trace: context → location → trigger → candidate.
4. Risk trace: invalidation → stop → target → cost-adjusted feasibility.
5. Management state trace: hold, protect, close, expiry, and emergency paths.
6. Broker trace: intent → submission → fill → position → close.
7. Missing-data, stale-state, rejection, and restart behavior.
8. Required audit events and fields for every decision.
9. Positive and negative fixtures proving both acceptance and rejection.
10. LLM result with exact rule/evidence citations.

Any failed item is a Stage 1 defect, not a reason to tune parameters.

## 1. Textbook strategy contract

Every strategy must be explainable as one causal chain:

`higher-timeframe context -> M15 location -> M1 response -> entry -> structural invalidation -> cost-adjusted target -> managed exit`

Each link must be represented by completed, timestamped evidence. A model may
judge supplied evidence, but it may not invent a missing link.

### Required entry chain

1. **Context:** D1/H4/H2/H1 establish the active path, regime, and opposing case.
2. **Location:** price touches or enters a fresh/active M15 zone. The zone must
   be identified before the M1 trigger, not selected after the fact because it
   is nearest to price.
3. **Response:** a completed M1 probe-and-failure, reclaim, rejection, or
   breakout-retest occurs at that M15 zone. The event must be fresh and tied to
   the zone by evidence IDs.
4. **Geometry:** entry, stop, and target are derived from named structure and
   include spread/slippage feasibility. A fixed-distance fallback is allowed
   only when the contract explicitly records why structural geometry is absent.
5. **Arbitration:** Qwen approves the supplied candidate; it cannot repair
   missing evidence, change geometry, or change size.

## 2. Baseline audit of strategy 1

Current implementation: `vnext/strategy/xau_m15_m1_structure_scalper.py`.

What is already correct:

- M15 is declared as the setup/level timeframe and M1 as execution timing.
- D1/H4/H2/H1 context is supplied to arbitration.
- The strategy is isolated by ID, version, magic number, and trade class.
- Risk and broker boundaries are separate from strategy judgment.
- Broker protection is required and management never widens accepted risk.

Known gaps to resolve or explicitly falsify:

- `build_strategy_evidence()` chooses the latest M1 swing and the nearest
  eligible M15 zone, but does not require the swing to occur at that zone.
- A swing event is not yet a complete probe/rejection/reclaim sequence.
- The recorded invalidation structure is metadata; the executable risk path
  currently uses a fixed 3.0 price stop and 5.0 price target.
- Target selection needs a cost-adjusted room and opposing-structure check.
- Management expiry is anchored to clock-minute boundaries, which can close a
  trade 50–85 seconds after entry. This must be compared with an elapsed-time
  alternative in replay.
- Profit protection is ATR-triggered break-even-plus, not staged dollar
  protection or a structure trail.
- Management decisions, MFE, MAE, and stop modifications are not yet durable
  per-position audit events. This prevents reliable post-trade diagnosis.

## 3. Research hypotheses

These are hypotheses, not recommendations or activated rules.

### H1 — Zone-linked trigger

**Hypothesis:** Requiring M1 response evidence inside the selected M15 zone
reduces low-quality entries and improves cost-adjusted expectancy.

**Test:** Compare the current selector with a selector requiring zone overlap,
freshness, response direction, and one unused M1 episode. Keep risk, sessions,
and execution identical.

**Kill criteria:** Reject if expectancy, drawdown, or adverse excursion is not
better after at least 100 trades across five complete sessions/regimes.

### H2 — Structural geometry

**Hypothesis:** Stops beyond the named M15/M1 invalidation, with a volatility
and spread buffer, avoid both premature noise exits and arbitrary risk geometry.

**Test:** Replay structural stops against the current fixed 3.0 price stop with
the same entries and broker costs.

**Kill criteria:** Reject if cost-adjusted expectancy falls, risk tails expand
materially, or target feasibility deteriorates.

### H3 — Staged profit protection

**Hypothesis:** After net profit reaches a tested threshold, locking a smaller
positive amount reduces profit giveback without destroying continuation trades.

**Candidate experiment:** At net +$100, lock approximately +$50 net; then trail
only after a new completed M1 continuation structure. Calculate price levels
using broker economics, not a hard-coded XAU price conversion.

**Kill criteria:** Reject if average win, profit factor, or expectancy declines
after costs, even if win rate increases.

### H4 — Elapsed-time management

**Hypothesis:** A confirmation window measured from entry is less path-dependent
than the current next-minute clock expiry.

**Test:** Compare elapsed windows (for example 60/90/120 seconds) while
preserving the original early-failure rule and all entry decisions.

**Kill criteria:** Reject if it increases MAE or produces a worse cost-adjusted
expectancy across sessions.

## 4. Replay dataset and measurements

Each replay row must include:

- broker symbol, UTC entry/exit, direction, volume, spread, tick value, and
  commission;
- the M15 zone ID, bounds, lifecycle, touch distance, and freshness;
- M1 trigger type, trigger bar ID, response sequence, and distance from zone;
- context/regime/session evidence IDs and state hash;
- structural invalidation price, target price, and fixed-fallback reason;
- tick or completed-bar path sufficient to calculate MFE, MAE, time-to-MFE,
  time-to-MAE, and threshold crossings;
- every management decision, stop modification, close request, broker result,
  and final exit reason.

Report at minimum:

- net expectancy per trade after all costs;
- win rate, average win, average loss, payoff ratio, profit factor;
- maximum drawdown and loss streak;
- MFE/MAE distributions and profit-giveback ratio;
- time-to-confirmation, time-to-protection, and time-in-trade;
- results by session, volatility regime, direction, and zone type;
- rejected/cancelled candidates and the reason each was rejected.

Do not tune on one trade, one day, gross P&L, or a post-change profit run.

## 5. Promotion gates

A candidate rule may move from research to demo shadow only when:

1. the hypothesis, affected path, expected benefit, harm, and falsification test
   are recorded;
2. the replay is leakage-safe and spans at least 100 trades and five complete
   sessions/regimes;
3. broker costs, spread, slippage, and symbol economics are included;
4. baseline and candidate results are reported side by side;
5. focused unit tests and replay tests pass;
6. the new strategy version and parameters are immutable and auditable;
7. explicit activation approval is given after the evidence review.

If these conditions are not met, the change remains a research hypothesis and
must not be activated in the live or demo execution worker.

## 6. Per-strategy review template

For each of the eight strategies, complete the following before implementation:

- Strategy ID/version and instrument scope
- Context timeframes and setup timeframe
- Zone definition, freshness, and invalidation
- Exact execution trigger and evidence sequence
- Entry expiry and cancellation rules
- Stop source, target source, and cost model
- Management states and protection transitions
- Known failure modes and observability events
- Baseline dataset and replay acceptance metrics
- Hypotheses tested, results, contradictions, and decision

The first strategy review should begin by fixing the evidence linkage and
management audit trail, then replaying H1–H4 independently. No combined tuning
should be promoted until each component has a separate attribution result.

## 7. Weekly per-strategy review

Run one review for each active strategy every week. Keep the strategy versions
separate; never pool their results into one score.

The weekly packet must include:

- contract-conformance PASS/FAIL count and all unresolved defects;
- candidate and order funnel, including rejected and expired candidates;
- broker fills, slippage, spread, commissions, and reconciliation exceptions;
- MFE/MAE, time-to-confirmation, time-to-protection, giveback, and exit reasons;
- expectancy, payoff ratio, drawdown, loss streak, and sample size;
- breakdown by session, volatility/regime, direction, zone type, and setup;
- incidents, data gaps, stale evidence, and missing audit events;
- hypotheses opened, closed, or awaiting the minimum sample.

Weekly review decisions are limited to: continue unchanged, pause for a
Stage-1 conformance defect, collect more evidence, or open a Stage-2 research
hypothesis. Parameter changes require a new version and the same promotion
gates as any other behavior change.

## 8. External research notes

Stop rules are regime-dependent: academic work finds that stop-loss overlays
can add value when returns exhibit momentum, but can reduce expected return
under random-walk-like behavior. See Kaminski and Lo, *When Do Stop-Loss Rules
Stop Losses?* <https://www.sciencedirect.com/science/article/pii/S138641811300030X>.

Dollar thresholds must be converted through the broker's current symbol and
volume economics. MetaTrader documents `OrderCalcProfit` for estimating the
account-currency result of a specified operation:
<https://www.mql5.com/en/docs/trading/ordercalcprofit>.
