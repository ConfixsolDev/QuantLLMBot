# QuantLLM V2 Strategy Development Guide

This is the operating contract for creating, testing, promoting, and retiring
strategies in the clean-room V2 runtime. A strategy is an independent trading
unit: it owns its identity, alignment rules, candidate logic, risk policy,
execution metadata, lifecycle, and performance namespace. Shared market
intelligence may be reused, but one strategy must never silently borrow another
strategy's decision or risk state.

## 1. Required strategy identity

Every strategy must define:

- `strategy_id`: immutable machine identifier, for example `XAU_RECLAIM_V1`.
- `version`: semantic version of the rules and parameters.
- `pair` and `trade_class` (`HTF`, `SCALP`, or `MICRO`).
- A unique positive `magic_number` used on every broker order.
- A bounded `comment_prefix`; if omitted, V2 derives `QVN:<strategy_id>:<version>`.
- Evaluation cadence and candidate expiry.

The final V2 order boundary overwrites missing identity fields from the
candidate and rejects conflicting strategy IDs or magic numbers. MT5 comments
are limited to 31 characters. Performance attribution must use at least
`strategy_id`, `version`, `magic_number`, pair, direction, and order ID.

## 2. Strategy isolation contract

Each strategy must own these namespaces:

1. Candidate IDs and lifecycle state.
2. Alignment requirements across structure, MTF relationships, and temporal state.
3. Entry trigger, invalidation, target, and management policy.
4. Risk fraction, stop geometry, daily loss cap, and exposure cap.
5. Broker magic number and execution comment.
6. Statistics, outcomes, drawdown, MAE/MFE, and promotion status.

Strategies may read the immutable `PAIR_MARKET_STATE` and shared causal
intelligence. They may not mutate shared state, call the broker from strategy
logic, call the LLM directly, or use another strategy's statistics as their
own evidence.

## 3. Implementation shape

Create one module per strategy under the strategy implementation package. It
must provide a `StrategySpec` and a declarative `StrategyProgram` made of
facts-only rules. The program may produce a `CandidateIntent` or no candidate.
No candidate is a valid result when evidence is insufficient.

The spec must document:

- structural requirements and confirmed-event requirements;
- parent/child timeframe alignment and allowed conflict states;
- zone types, lifecycle states, acceptance-density threshold, and revisit rules;
- exact trigger and invalidation geometry;
- target-zone policy and minimum reward/risk;
- strategy-specific statistical qualification;
- risk and position-sizing policy;
- management and exit policy;
- model arbitration citations required for approval.

## 4. Development and R&D sequence

1. State the falsifiable hypothesis, expected edge, affected data path,
   expected benefit, possible harm, and kill criteria.
2. Define the strategy contract and unique broker identity.
3. Build the facts-only DSL rules; keep market interpretation deterministic.
4. Run historical causal replay with no future-bar access or look-ahead.
5. Test missing data, spread/slippage, duplicate events, restart, and broker
   rejection behavior.
6. Evaluate multiple regimes and instruments only where the strategy contract
   permits them.
7. Compare against a deterministic no-trade and simple baseline.
8. Calculate strategy-scoped expectancy, win rate, payoff, drawdown, MAE/MFE,
   sample size, and confidence/shrinkage-adjusted results.
9. Run demo acceptance with the real magic number and comment, while live
   order activation remains paused until all gates pass.
10. Promote only after review of evidence; otherwise keep the strategy in
    `RESEARCH`, `REJECTED`, or `RETIRED` state.

## 5. LLM and risk boundaries

The LLM is an evidence-constrained arbitrator only. It may return
`APPROVE`, `WAIT`, `VETO`, or `NO_TRADE`. It cannot create a candidate, change
the strategy's risk limits, change its magic number, or bypass citations and
state-hash checks. Deterministic risk must approve before OMS submission.

## 6. Performance and operations

All routine events and performance data belong in TimescaleDB. Neo4j stores
causal/provenance relationships. Redis stores disposable current context and
single-instance coordination. No routine strategy logs or state files are
permitted. Only bug diagnostics may use files.

Every order, fill, cancel, rejection, and exit must be attributable to one
strategy identity. Reports must support comparison by strategy ID/version,
magic number, comment, regime, session, and direction.

## 7. Promotion checklist

A strategy is ready for promotion only when its contract, identity, tests,
causal replay, leakage checks, multi-regime evidence, risk tests, broker
identity tests, restart/reconciliation tests, and Timescale performance
attribution have passed. A strategy that fails any gate must not be enabled by
configuration convenience or by an LLM response.
