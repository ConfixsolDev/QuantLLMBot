# Plan View refactor — architecture assessment

Read before implementing. No code has been changed.

**Conclusion up front:** roughly 70% of the spec is re-presentation of data the
planner already emits, and can be built in the frontend alone — which means it
does not touch the freeze. The remaining 30% needs new backend computation, and
one part of the spec should be rejected on performance grounds.

---

## 1. What already exists

Three state files feed the screen. The planner is richer than the current UI
shows.

`planner-state.json`

| field | contents |
|---|---|
| `clock` | session, hour_of_session, hours_into_day, next_boundary_utc, trading_date_utc |
| `day_branches` | `bullish` / `bearish`, each with side, trigger_price, trigger_text, targets[], invalidation, evidence[], state, reason, confidence |
| `day_plan` | key_levels, bullish_scenario, bearish_scenario, expected_session_behaviour |
| `session_plan` | active_scenario, entry_zones[], confidence, price_sanity |
| `trade_idea_stack` | h4 / h1 / m15 ideas, each with side, zone, invalidation, target, status; plus layer_validation and revisions |
| `hourly_updates[]` | hour_ohlc, levels_touched[] (price, label, result), plan_status, confidence_delta, note, layer_validation |
| `session_verdicts[]` | scenario_outcome, planned_vs_actual, lesson_candidate |

`management-dashboard-state.json` — live price, change, positions, `levels`
(M1/M5/M15/M30/H1/H4/D1, each with id, price, role, respect_count), today's
stats, model_status.

`entry-dashboard-state.json` — the entry thesis: bias, confidence, summary,
invalidation, execution_plan, proposal_id.

**The `state` machine on each branch is the single most useful field on the
screen and is currently not surfaced as such:** `armed` / `likely` /
`confirmed` / `spent` / `invalidated`. That maps almost directly onto the
spec's `trade_status`.

## 2. Spec field → source mapping

### Buildable from existing data (frontend only)

| Spec section | Source |
|---|---|
| Market Brief · symbol, price, session, session_hour | `symbol`, `price`, `clock.session`, `clock.hour_of_session` |
| Market Brief · market_bias | `day_branches.callable_side` + branch `state` |
| Market Brief · trade_status | branch `state` → WAIT/READY/ENTER mapping |
| Market Brief · confirmation_status | `trade_idea_stack.layer_validation` |
| Right Now · waiting_for | branch `reason`, m15 idea `status` |
| Right Now · avoid | derived from location + confirmation (rules, not new data) |
| Primary Plan · everything | `day_branches.{bullish\|bearish}` — direction, thesis, trigger, invalidation, targets, evidence |
| Alternative Plan · everything | the opposite branch, gated on its `state` |
| What Would Change My Mind | branch `invalidation` + `evidence` + opposite branch trigger |
| Timeframe Narrative | `trade_idea_stack.{h4,h1,m15}` + `layer_validation` |
| Last Hour Review | `hourly_updates[-1]` — has ohlc, levels_touched, plan_status, confidence_delta, note |
| Confidence Explanation · factors | branch `evidence[]` (positive) + `layer_validation` failures (negative) |
| Do / Don't | rules over the above |
| Session Timeline | `clock` + `session_verdicts` |
| Execution Statistics | `execution_funnel` (already built) |
| Translation dictionary | pure frontend |

### Needs new backend computation

| Spec section | Missing | Effort |
|---|---|---|
| Price Location | nearest_support / nearest_resistance relative to live price; distances; `location_classification` | Small — `levels` already has every price; this is selection and arithmetic |
| Price Location · atr_distance | ATR not computed anywhere | Medium — needs a rates call |
| Market Condition Engine (13 labels) | displacement, acceptance/rejection, ATR state, volatility regime | **Large** — this is a new analytical component, not a rename |
| What Changed | previous planner snapshot is not persisted | Medium — needs a state history file + diff |
| Trader Commentary | no session-scoped event log | Medium — needs persistence |

### Reject

**`llm_explanation_contract` — do not add narrative model calls.** The system
runs one shared Ollama instance behind `model_generation_lock`. Entry decisions
take ~28s on GPU against a 60s proposal TTL; on CPU this morning they took
190–455s and produced 4 fills from 106 proposals. Adding narrative generation to
that queue directly competes with the decisions that make money.

If narrative is wanted later it must be a separate small model, or run strictly
off the critical path on a timer. Not in the same lock.

## 3. Three contradictions to fix by construction

The current screen disagrees with itself in three places. A rewrite that carries
these forward inherits the bug; the new ViewModel should make them impossible.

1. **"2 trades closed · net +232.50"** beside a funnel showing `Filled 1`. Logs
   for that day show 1 close at +116.25. Two components compute the same number
   from different sources.
2. **"BUY — all timeframes agree (H4)"** while D1, H1 and M15 each render
   `NO LEAN`. The headline claims agreement that the panels deny.
3. **Both branches showing `TARGET REACHED`** directly above an hour validation
   reading `invalidated · match: no · confidence delta −29`.

**Rule for the new model: one number, one owner.** Every displayed value is
computed once in the ViewModel builder and passed down. No component derives a
figure a sibling also derives.

## 4. Two additions the spec omits

- **Build and freeze badge.** The system was frozen at `702bfeff3f84`. Nothing
  on screen says which build is running or whether it has drifted.
- **Decision latency.** Had "last decision: 455s" been visible this morning, the
  CPU fallback would have been obvious immediately instead of being found in a
  log hours later. One number, high value.

## 5. Proposed component hierarchy

```
PlanView
├── HeaderBar            symbol · price · session · build · latency · model
├── MarketBrief          bias | trade status | location | confirmation   (4 fields, one row)
├── RightNowCard         action + reason + waiting_for[] + avoid[]       (amber when WAIT)
├── PrimaryPlanCard      dominant styling
├── AlternativePlanCard  muted until its activation condition fires
├── PriceLocationStrip   support ── price ── resistance, with distances
├── WhatWouldChangeMyMind
├── PlanChart            entry zone as a band; invalidation styled apart from targets
├── TimeframeNarrative   D1 Context · H4 Structure · H1 Setup · M15 Trigger + combined line
├── LastHourReview
├── ConfidencePanel      qualitative label primary, score secondary
├── DoDontCard
├── SessionTimeline
├── ExecutionFunnelPanel  (exists)
└── TechnicalDetails      collapsed; every current raw state preserved
```

Supporting frontend modules: `lib/translate.ts` (the enum dictionary),
`lib/viewModel.ts` (single builder), `lib/priceLocation.ts`.

## 6. Recommended scope and order

**Stage A — frontend only, no backend change, freeze untouched.**
Translation dictionary, ViewModel builder, Market Brief, Right Now,
Primary/Alternative Plan, Timeframe Narrative, Last Hour Review, Do/Don't,
Confidence, debug collapsed, and the three contradictions fixed. This is most of
the spec's value and carries no trading risk.

**Stage B — small backend addition.** Price Location (nearest levels,
distances, classification) computed in the planner where the levels already
live. Moves `build_id`; batch it with the GPU restart already outstanding.

**Stage C — state history.** Persist planner snapshots, add the diff service,
build What Changed and Trader Commentary.

**Stage D — defer.** Market Condition Engine and the LLM narrative layer.

## 7. Risk notes

- `planview` is **not** among the 17 modules in the build manifest, so Stage A
  cannot affect `build_id` or the freeze.
- Stage B touches `session_planner.py`, which **is** tracked. It resets the
  10-trade acceptance sample.
- Nothing in Stages A–C changes decision authority. The deterministic planner
  remains the only source of bias, levels, triggers and readiness, per the
  spec's core principle.
