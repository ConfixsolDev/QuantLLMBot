# QuantLLMBot Profitability Research Loop

This document defines the experimental process for improving the XAUUSD paper
strategy. It does not replace `store/core_skill.md` or `store/sop.md`, and it
does not authorize live trading. Trading doctrine remains in the fixed store;
this file controls how hypotheses are proposed, tested, rejected, and promoted.

## Objective

Promote only strategy versions that demonstrate repeatable positive broker-net
expectancy on data that was not used to design the change. A higher win rate,
one profitable day, or a favorable backtest is not sufficient by itself.

Broker-net result means realized MT5 profit plus commission and swap, grouped
by the complete basket. Spread and execution price are therefore included in
the observed result. Runner summaries must reconcile to MT5 deal history before
they are used as research evidence.

## Current evidence baseline

The local logs available through 2026-08-03 contain:

- 4,450 Qwen proposals from 2026-07-27 through 2026-08-03;
- 267 execution starts, 219 execution closures, and 96 closures with fills;
- 4,041 one-second execution-monitor events; and
- several incompatible exit regimes, including cash targets/stops, timed exits,
  adaptive locks, broker stops, structural targets, and price-distance stops.

These records are valuable for generating hypotheses, but they are not one
controlled profitability experiment. Logged basket P&L also differs from MT5
broker history when one leg closes at its broker stop before the runner records
the remaining basket. Historical claims must therefore be rebuilt from broker
deals and tagged by exact strategy version.

## The loop

### Human-approval checkpoints

The following checkpoints are mandatory. Passing a technical test does not
grant permission to pass the next checkpoint automatically.

1. **Evidence approval:** present broker reconciliation, exclusions, version
   boundaries, and the observed failure. Human confirms that the evidence is
   suitable for hypothesis generation.
2. **Hypothesis approval:** present the preregistration and identify the one
   independent variable. Human approves which hypothesis may enter offline
   testing. No production behavior changes before this approval.
3. **Offline-test approval:** present contract, replay, walk-forward, and
   robustness results, including failed variants. Human decides whether the
   challenger may enter shadow paper testing.
4. **Paper-test approval:** present frozen challenger results for the declared
   blocks and duration. Human chooses promote, retain, or reject.
5. **Doctrine/memory approval:** any proposed change to `core_skill.md`,
   `sop.md`, knowledge cards, or principles follows the existing human-owned
   memory lifecycle. A profitable experiment does not rewrite doctrine by
   itself.

Between checkpoints, an agent may inspect evidence, repair measurement,
prepare deterministic tests, and write reports. It may not infer approval for
the next strategy stage. Future agents and LLM-assisted development sessions
must read this document through the workspace `AGENTS.md` instructions. The
market-decision model does not receive raw research outcomes; it receives only
the approved canonical doctrine and closed market facts.

### 1. Reconcile and qualify the evidence

Build one chronological event table joining proposal, Qwen response, fill,
monitor, MT5 deal, and exit records by proposal, execution, position, and deal
IDs. Quarantine malformed, duplicate, orphaned, or version-unknown observations
from confirmatory statistics. Record the reason for every exclusion.

Required integrity checks:

- every filled leg has exactly one MT5 opening deal and a closing deal;
- basket net P&L equals MT5 profit + commission + swap;
- decision and fill timestamps are monotonic and use UTC;
- the market snapshot contains only facts available before the decision;
- model, prompt, code, configuration, and data hashes identify the version; and
- all tested variants, including failed variants, remain in the experiment
  ledger so selection bias can be measured.

### 2. Freeze a champion

An experiment starts from one immutable champion identified by Git commit,
deployed-file hashes, Ollama model digest, prompt/SOP/core-skill versions,
configuration hash, symbol, account mode, and experiment start time. Do not
change entry, exit, target, stop, bucket, prompt, or model behavior inside a
measurement block.

### 3. Observe and decompose the champion

Use a block of 40 completed decisions/events, matching the canonical SOP
learning block. A block is diagnostic, not proof of profitability. Decompose
results into:

- broker-net expectancy and profit factor;
- win rate, average win, average loss, and break-even win rate;
- favorable/adverse price excursion and profit-capture ratio;
- entry delay, spread, commission, slippage, and signal expiry;
- direction quality versus entry quality versus exit quality;
- one/two-bucket behavior and add-on contribution;
- session, volatility, direction, opportunity type, and exit-reason cohorts;
- Qwen confidence calibration; and
- concentration: contribution of the best/worst trade and day.

Do not send raw prior profits, losses, win rates, or prior directions into the
next market decision. Outcomes belong to the separate learning pipeline; using
them as directional input creates recency feedback and contaminates the test.

### 4. Write one falsifiable hypothesis

Every proposed change must be registered before seeing its test results:

```text
Hypothesis ID:
Observation and evidence IDs:
Mechanism:
One independent variable to change:
Frozen control behavior:
Primary metric:
Secondary diagnostics:
Expected effect and minimum useful effect:
Development interval:
Untouched test interval:
Pass, fail, and abort conditions:
Known counter-case:
```

A hypothesis must name a causal mechanism, not merely “make more profit.” Only
one behavioral variable changes per basic experiment. Compound changes require
a factorial/challenger design that can attribute the effect of each component.

### 5. Test in ordered stages

1. **Contract tests:** schema, geometry, ownership, accounting, and no-lookahead
   tests must pass.
2. **Deterministic replay:** replay historical ticks with the same code path,
   recorded latency, spread, commission, and fill rules.
3. **Development window:** estimate/tune only on the declared development data.
4. **Walk-forward test:** freeze the variant, move forward chronologically, and
   evaluate on an untouched interval. Never retune on that interval.
5. **Robustness:** perturb spread, latency, entry price, start time, and the
   proposed parameter. A genuine effect should not exist at one precise value.
6. **Shadow paper:** champion and challenger receive the same closed snapshot;
   only the champion executes. Compare counterfactual decisions without mixing
   account state.
7. **Challenger paper:** after offline gates pass, run the frozen challenger on
   the demo account for confirmatory blocks.

### 6. Duration and evidence gates

Duration is evidence-driven; elapsed days alone are not enough.

- **Smoke gate:** one session verifies plumbing only; it cannot establish edge.
- **Discovery gate:** one complete 40-event block may generate a hypothesis.
- **Confirmation gate:** at least three non-overlapping 40-event blocks (120
  events) with the exact frozen version, including more than one session and
  volatility condition.
- **Paper-soak gate:** at least 20 trading days and 200 completed eligible
  decisions, whichever takes longer, without changing the candidate.

These are project gates, not universal statistical constants. If uncertainty
remains wide, testing continues. A candidate passes profitability review only
when:

- aggregate untouched broker-net expectancy is positive;
- its uncertainty interval and block results show that profit is not dependent
  on one trade or one day;
- profit factor and average-win/average-loss geometry improve by the registered
  minimum useful effect versus the champion;
- at least two of three confirmation blocks are profitable and the aggregate is
  profitable;
- costs and moderate execution perturbations do not remove the advantage; and
- broker and research-ledger P&L reconcile exactly.

Failure of the primary metric rejects the hypothesis. A favorable secondary
metric cannot rescue it. A failed hypothesis is retained as research evidence
and is not silently reworded after results are known.

### 7. Promote, retain, or reject

Produce a comparison report with the preregistration, exclusions, all tested
variants, broker-net results, uncertainty, regime cohorts, failure cases, and
reproduction command. Human review then selects exactly one outcome:

- **promote** challenger to the next paper stage;
- **retain** champion and collect more evidence; or
- **reject** challenger and record why.

Permanent learned principles still follow the existing memory lifecycle and
human-review process. One experiment never rewrites canonical doctrine.

## First registered research queue

These are candidate hypotheses, not approved changes:

1. **Exit truncation:** the profitable-time cap truncates favorable movement
   while 3-5-unit stops leave the loss distribution unchanged. Test removal of
   only the profitable-time cap against the frozen champion.
2. **Premature add-on:** adding the second 0.5-lot leg after only 0.10 favorable
   movement increases losing-basket magnitude without a proportional increase
   in broker-net expectancy. Test one bucket versus the existing add-on rule.
3. **Target-horizon mismatch:** far structural targets combined with short
   adaptive exits produce inconsistent holding geometry. Test a deterministic
   target-room qualification while leaving direction logic unchanged.
4. **Decision contamination:** supplying recent outcome history to Qwen changes
   direction/selectivity through recency rather than current market structure.
   Run a paired shadow test with and without outcome context.
5. **Accounting defect:** runner closure records understate multi-leg broker-stop
   losses. Correct reconciliation before using runner P&L for any hypothesis.

Only hypothesis 5 is a measurement repair and may precede profitability tests.
The behavioral hypotheses must be tested separately in the order selected by
human review.

## Registered investigation A3-2026-08-03

### Evidence approval packet

Source of truth: MT5 XAUUSDr deal history for magic `26072401`, grouped by the
opening execution comment and complete position lifecycle. Period: 2026-08-03
UTC. This packet describes one day and generates hypotheses; it does not prove
a general effect.

Broker-net basket results:

- 12 completed baskets: 7 wins and 5 losses;
- net result: -552.35;
- average win: +49.13;
- average loss: -179.25;
- profit factor: 0.384; and
- break-even win rate implied by the observed average payoff: about 78.5%,
  versus the observed 58.3%.

The three dominant losses were:

| Basket | Side/legs | Favorable price result | Broker-net result |
|---|---:|---:|---:|
| `QWEN_ec950a85` | sell / 2 | -2.519 | -258.90 |
| `QWEN_417c8be4` | buy / 2 | -3.405 | -347.50 |
| `QWEN_ff54ebc8` | sell / 1 | -5.000 | -253.50 |

The six earlier winners captured only 0.266-1.296 favorable price units and
netted +19.65 to +122.65. This is direct evidence of payoff asymmetry: routine
winners were realized at substantially smaller price movement than full-stop
losers. Two losing baskets also carried two 0.5-lot legs, so the add-on may
have amplified the left tail. The one-leg five-unit stop demonstrates that
bucket count is not the only cause.

The runner log understated stopped multi-leg losses because it recorded the
remaining live basket after one broker-side closure. For example, the runner's
partial loss did not equal the complete MT5 basket. All primary metrics for
this investigation therefore use broker deals.

### Candidate hypothesis A3-H1: marginal add-on expectancy

```text
Hypothesis ID: A3-H1
Observation: two of the three dominant losses carried two 0.5-lot legs.
Mechanism: the second leg is added after only 0.10 favorable price movement,
           before continuation is established, increasing stop-loss exposure
           more than it contributes to profitable baskets.
Independent variable: maximum executed legs, one versus current add-on rule.
Frozen control: direction, entry zone, first-leg volume, stop calculation,
                target, exit logic, prompt, model, TTL, and market data.
Primary metric: broker-net expectancy per eligible proposal.
Secondary metrics: second-leg marginal expectancy, average loss, average win,
                   profit factor, fill rate, and favorable/adverse excursion.
Minimum useful effect: positive untouched expectancy and at least 20% better
                       profit factor than the champion without relying on one
                       trade or day.
Development data: declared historical interval ending before the untouched
                  test interval; exact boundary recorded before replay.
Untouched test: chronological walk-forward interval plus three 40-event paper
                confirmation blocks after offline approval.
Pass: primary and duration gates in this protocol are satisfied.
Fail: untouched expectancy is non-positive or improvement is concentrated in
      one trade/day.
Counter-case: a valid positive-direction add-on may create the runner profit
              that pays for wide stops; forcing one leg could reduce winners
              proportionally and leave expectancy unchanged.
```

Status: **awaiting evidence and hypothesis approval**. No behavior change is
authorized by this registration.

### Candidate hypothesis A3-H2: winner truncation

The profitable-time cap and adaptive profit lock may realize winners before
they can offset the unchanged 3-5-unit loss distribution. This remains a
separate hypothesis. It must not be combined with A3-H1 in a basic experiment,
because changing both bucket count and exit duration would prevent causal
attribution.

## Research references and videos

- [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/)
  describes repeatable test, evaluation, verification, validation, uncertainty,
  benchmarking, monitoring, and documented change management.
- [Federal Reserve model-validation guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm)
  covers conceptual soundness, benchmarking, outcomes analysis, backtesting,
  monitoring, and recalibration.
- [MetaTrader 5 strategy-testing documentation](https://www.mql5.com/en/docs/runtime/testing)
  explains testing rule implementation and historical profitability in the MT5
  Strategy Tester.
- [Bailey et al., The Probability of Backtest Overfitting](https://scholarworks.wmich.edu/math_pubs/42/)
  explains why ordinary holdouts and selecting from many backtests can produce
  misleading winners.
- [López de Prado video library](https://www.quantresearch.org/Videos.htm)
  includes “How easy is it to overfit a backtest?” and Cornell lectures on
  financial-machine-learning validation.
- [NIST AI RMF explainer video](https://www.nist.gov/video/introduction-nist-ai-risk-management-framework-ai-rmf-10-explainer-video)
  introduces the lifecycle framework.
- [NIST measurement probes webinar](https://www.nist.gov/video/nist-information-technology-laboratory-ai-webinar-series-building-measurement-probes-agentic)
  shows how to build traceability and evaluation probes into agentic systems.
- [Official MetaTrader 5 testing help and video](https://www.metatrader5.com/en/terminal/help/algotrading/testing)
  demonstrates strategy testing and visual verification.
- [MIT OpenCourseWare finance lecture videos](https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/resources/lecture-videos/)
  provide supporting quantitative-finance foundations.
