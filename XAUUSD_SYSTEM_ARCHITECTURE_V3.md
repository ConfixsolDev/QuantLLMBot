# XAUUSD Quantitative Trading System — Architecture V3

> **THE ONE AND ONLY DOCUMENT.** This file is the single source of truth for
> the architecture, the code layout, how to run things, and how changes are
> allowed. It replaces V2 and every former README, guide, audit and report.
> Those are kept in git history only (last present at commit `b7af6e2`).
> Improve this file in place; do not add new Markdown documents beside it.
>
> Two documents are deliberately *not* part of this file, because the system
> reads them as data: the live trading doctrine `store/core_skill.md` and
> `store/sop.md` (the Qwen prompt), and the training process
> `model_training/CURRICULUM_AND_DATA_PREP.md` (the curriculum).

| | |
|---|---|
| Version | **V3** — 2026-10-31 (V2: 2026-08-17, confirmed 2026-08-19) |
| Instrument / broker | XAUUSD (gold) on a MetaTrader 5 **demo** account |
| Model | the single `DEFAULT_QWEN_MODEL` constant in `apps/qwen_trade_software/backend/goldflow/core/runtime_config.py` (served by Ollama) |
| MT5 connection | `apps/qwen_trade_software/backend/config/mt5_connection.json` (Part D) |
| Structure engine config | `apps/qwen_trade_software/backend/structure_engine/config/xauusd_structure_v1.json` (Part B) |

**Contents**
Part A — Authority, the three-module architecture, rules, invariants, change control ·
Part B — Module 1: the deterministic Market Structure Engine ·
Part C — The live system today (decision + risk) ·
Part D — MT5 connection ·
Part E — Training ·
Part F — Operations and commands ·
Appendix — History

---

## Part A — Authority and architecture

### A1. Who owns what

The system has three owned parts. Nothing else may redefine them.

1. **Evidence** — immutable observations (`model_training/tick_data/`, broker
   deal history, the TimescaleDB candle store). Broker deals, never runner
   summaries, establish realised P&L.
2. **Trading doctrine** — `store/core_skill.md` and `store/sop.md`. They define
   trading judgement for Qwen. They do not define component ownership or
   runtime flow. They are extended, not rewritten, and only with human approval.
3. **Code** — `apps/qwen_trade_software/`. Code owns validation, risk,
   execution, reconciliation and every safety invariant.

A proposed change becomes active only when **this document and the tested
code are revised together** in the same change.

### A2. The three-module architecture (target)

```
core/            bar data, config, clock, event log, MT5 connection   (shared by all)
1. structure/    closed M1 bars -> zones, swings, liquidity, patterns     Part B
2. decision/     structure template -> Qwen -> BUY / SELL / NONE          Part C
3. risk/         sizing, limits, orders, position & trade management, broker   Part C
runner           live  = MT5 bar feed + MT5 broker
                 test  = recorded bars + simulated broker
```

Where the code is today and where it is going:

| Module | Today (`backend/goldflow/...` live code) | Target |
|---|---|---|
| core | `core/` (runtime_config, instrument_config, paths, mt5_connection, logging, TimescaleDB, build manifest, tick archive, candle clock) | same |
| 1 structure | `market/`, `structure/`, `regime/`, `intelligence/` (live, not causality-tested) **and** the new `backend/structure_engine/` (deterministic, tested, shadow) | `structure_engine` replaces the old detectors one at a time, each only after it passes Part B's tests and a shadow comparison |
| 2 decision | `decision/` (Qwen reviewer, prompts, entry gates), `planning/` (session planner) | consumes Module 1 events/snapshot only |
| 3 risk | `execution/` (paper runner + MT5 executor), `management/` (trade manager, profit protection) | unchanged behaviour; broker behind one interface |
| runner | `runtime/software_runtime.py` (supervisor) + `structure_engine/runner.py` (backtest/live/export) | one runner, two feeds |

### A3. The five rules

1. **Modules talk through data only.** Module 1 never calls Qwen, a strategy or
   the broker and never issues BUY or SELL. It emits events and a snapshot.
2. **Testing and live use the same code.** Only the bar source and the broker
   change. There is no "backtest version" of any detector.
3. **No hard-coded thresholds.** Every number lives in a versioned JSON config.
   Unknown or missing keys fail at load time. Every event carries the config hash.
4. **Closed candles only; no look-ahead; no repainting.** Every event has an
   `available_at` time, and the test suite proves it.
5. **Forming and confirmed are separate.** A running session high, an
   unfinished H1 candle or a pattern awaiting its neckline break is never
   presented as a confirmed fact.

Also inherited from V2 and still binding: **Python computes, Qwen judges** —
deterministic code measures structure, regime and geometry; Qwen supplies
contextual judgement on top of it; the model is one component, not the system.

### A4. Non-negotiable invariants (live system)

- Historical research and MT5 **demo/paper only**. The executor refuses non-demo accounts.
- One Qwen position at a time. No baskets, add-ons, averaging or reversal.
- Entry and management have separate contracts.
- MT5 facts and code-owned levels are authoritative over model text.
- Completed and forming candles never share evidence semantics.
- No cached decision is reused for another snapshot.
- No fixed-dollar target, no time-only close, no exit because of small P&L.
- The broker safety stop stays independent of model availability.
- Every mutating management action requires deterministic validation.
- Current live price is rechecked after model inference.
- Recent wins/losses never decide the next direction (see PHC-003).
- Learning and doctrine changes require evidence and human review.
- Source, deployed hashes, model digest, prompt version, config hash and cache
  epochs must be traceable for every decision.

**Directional-bias invariant.** Each opportunity has one conclusion: `buy`,
`sell` or `wait`. Qwen may weigh both sides but must not output a two-sided
trade. Bias is hierarchical: the owning timeframe defines the thesis; a
counter-move on M15/M5/M1 may be the pullback into its zone, and becomes a
contradiction only after accepted failure of the named invalidation on its
owning timeframe. `wait` is valid when location or closed-candle validation is absent.

### A5. Proven-harmful changes — do not reintroduce

Changes that looked safer but were shown by replay or demo evidence to do
harm. Renaming one, moving it to another layer or expressing it in a prompt is
still reintroduction. Reopening needs preregistered evidence and explicit
human approval.

| ID | Rejected behaviour | Why it is harmful | Safe replacement |
|---|---|---|---|
| PHC-001 | After Qwen returns, require M1/M5 epochs or named-level IDs/prices to be **exactly** unchanged | CPU inference takes minutes; low-timeframe levels always rotate, so exact equality becomes a near-universal no-trade rule (proposal `paper-20260805T055843-3f41f811`, removed in `05c3fb7`) | Recheck stable structural/playbook epochs, cache readiness, session, model digest, live tick, entry-zone eligibility and the 60-s lifetime. A real H1/H4 structural change during inference **must** still expire the proposal (`paper-20260805T060621-c8536c12`) |
| PHC-002 | Every ready entry must cite **both** an M1 and an M5 candle | Citations list the facts actually used; a valid D1–M15 thesis closed +1403.70 without M1/M5 (`paper-20260805T021044-08c9dcd7`) | Citations must be non-empty and a subset of cache-owned evidence IDs |
| PHC-003 | Recent profit/loss as a direction or entry gate | Recency bias; non-reproducible decisions; P&L overrides closed market facts | Outcomes only in the separate research loop |

Companion controls that must remain whatever is relaxed: ready entries need
confidence 51–100 (coherence, not a profit promise); missing confidence is 0;
bias must be explicit and agree with plan side; citations non-empty and
cache-owned; readiness, UTC session/date, structural context and model
identity rechecked before entry; executor rechecks demo mode, current tick,
live entry range, geometry, one-position ownership and the 60-second deadline.

New register entries use: *pattern ID, status, rejected behaviour, evidence IDs
and version boundary, mechanism, safe replacement, protected counter-case,
regression invariant, reopening criteria, human approval.* One loss or one win
is never enough to add an entry.

### A6. How changes are made

**Before editing code, answer:** which module/stage owns the problem? Is it
fact, interpretation, decision, validation, execution or learning? What exact
evidence reproduces it? Engineering or strategy? Which invariant could break?
Which deterministic test fails before and passes after? Can it deploy with zero
open positions? What result would falsify the claim? Does A5 reject it?
If these cannot be answered, keep diagnosing; do not improvise a trading rule.

**Engineering gate** (a repair): the reproduction now passes; all tests pass;
no unrelated invariant changes; restart behaves like uninterrupted running;
malformed/stale input fails closed; source and deployed hashes match. If entry
or exit counts change, it is strategy work, not a repair.

**Strategy gate** (a behaviour change), with a human checkpoint at each step:
evidence approval → one falsifiable hypothesis with one independent variable →
offline replay and untouched walk-forward → frozen shadow/demo test → promote,
retain or reject. Duration gates: one session = plumbing only; one 40-event
block = may generate a hypothesis; three non-overlapping 40-event blocks with
the frozen version = confirmation; ≥20 trading days and ≥200 decisions = paper
soak. Pass only with positive untouched broker-net expectancy not dependent on
one trade or day, robustness to costs, and broker/ledger reconciliation. A
failed primary metric rejects the hypothesis; it is not reworded afterwards.

**Rules of engagement:** one piece at a time; foundation (log-only) before
behaviour; closed candles only; log everything; measure against the frozen
baseline and revert if worse.

---

## Part B — Module 1: the Market Structure Engine

Package: `apps/qwen_trade_software/backend/structure_engine/` — standard
library only, Python 3.10+. Status: **built and verified on synthetic ground
truth; running on real XAUUSD history is the next step.** It is not yet wired
into live decisions (shadow only, per A2).

### B1. What it does

```
closed M1 bar ──► StructureEngine.push(bar) ──► list[Event]   (confirmed facts, known now)
                                  │
                                  └──► snapshot()   top zones, swings, levels,
                                                    pending patterns, forming state
```

```python
from structure_engine import StructureEngine, load_config, load_m1
engine = StructureEngine(load_config())
for bar in load_m1("XAUUSD_M1.csv"):   # columns: time, open, high, low, close, tick_volume
    events = engine.push(bar)          # same call live and in testing
state = engine.snapshot()
```

Inside one `push`: (1) existing zones meet the new bar (tested/broken);
(2) session and day levels update, finished ones are confirmed; (3) M1 swings,
then M1 patterns; (4) M1 is aggregated to M5…H4 and, for every higher-timeframe
candle that closed with this minute: ATR, swings, and on zone timeframes,
zone ageing and new zones. Every event's `available_at` is the close of the M1
bar that produced it (asserted in code).

Event kinds: `swing`, `zone_created`, `zone_tested`, `zone_broken`,
`zone_expired`, `session_level`, `prior_day_level`, `pattern_pending`,
`pattern_confirmed`, `pattern_invalidated`, `pattern_superseded`. Each carries
`id` (deterministic), `kind`, `tf`, `time` (the structure's own anchor),
`available_at`, `config_hash`, `data`.

### B2. Detectors and their definitions

All distances are in ATR units (Wilder, period 14 by default) so one config
works at any price or volatility. Full definitions with diagrams are in each
file's header comment.

| Detector | Timeframes | Definition in one line | File |
|---|---|---|---|
| Swings (HH/HL/LH/LL/EH/EL) | M1–H4 | candle strictly beyond the k before, not exceeded by the k after; known when candle c+k closes | `swings.py` |
| Supply/demand zones | H4, H1, M30 | 1–3 small base candles (range ≤ 0.8 ATR) then a 1–3-candle one-way departure (first body ≥ 0.8 ATR, travels ≥ 2.0 ATR beyond the base); lifecycle FRESH → TESTED → BROKEN / EXPIRED | `zones.py` |
| Zone ranking (top 9) | H4/H1/M30 | weighted 0–1 features: freshness, departure, base, volume, room, nesting, liquidity, timeframe | `scoring.py` |
| Session & prior-day high/low | M1 | Asia 00–07, London 07–13, New York 13–21 UTC; running = forming, finished = confirmed event | `sessions.py` |
| Double/triple tops & bottoms | M1 (measured in M5 ATR) | peaks within 0.35 ATR, 5–120 bars apart, nothing pokes above them, neckline depth ≥ 1.5 ATR **and** ≥ 30 % of the prior move, prior move ≥ 4 ATR in 30 bars; confirmed by a close beyond the neckline within 60 bars; tags: sweep, volume spike, exhaustion | `patterns.py` |

Every threshold above is a key in `config/xauusd_structure_v1.json`; the
numbers here are the shipped values, not code constants.

### B3. Measured accuracy (synthetic ground truth, 20 seeds, 2026-10-31)

| Detector | Precision | Recall | Notes |
|---|---|---|---|
| Swings, all six timeframes | 100 % | 100 % | streaming == independent offline reference (32,219 swings) |
| Zones H4 / H1 / M30 | 100 % | 100 % | 115 planted each; 85/85 weak-departure look-alikes rejected |
| Double/triple tops & bottoms | 100 % | 100 % | 139 planted; 101/101 shallow-neckline and mismatched-peak look-alikes rejected |
| No-repaint, determinism, invariants | PASS | | prefix replays reproduce the full run exactly |
| Zone ranking | — | — | built, **not yet validated** (needs forward usefulness on real data) |

**Read these numbers honestly.** They prove the code implements its
definitions, including the hard near-miss cases. They do not prove the
definitions are useful on real gold. Pattern precision started at ~17 % and
reached 100 % through three definition changes found on synthetic data — a
prior-move requirement, depth relative to that move, and measuring in M5 ATR
instead of M1 ATR — plus a triple-trough rule and a supersede fix. All were
then confirmed on 15 seeds not used while making them, but the synthetic
generator was written by the same author, so real-data review (B4 steps 4–5)
is the real test.

### B4. How accuracy is verified

1. **Synthetic ground truth** (`verification/synthetic.py`): seeded series
   with planted structures and planted near-miss negatives → exact precision,
   recall and localisation error per detector (`verification/matching.py`).
2. **No-repaint test** (`verification/causality.py`): for random cut points,
   running on data up to the cut must reproduce exactly the full run's events
   with `available_at` ≤ cut.
3. **Determinism and invariants**: same input → same event fingerprint; zone
   and pattern geometry always valid; nothing known before its structure closed.
4. **Point-in-time review on real XAUUSD**: replay real M1 history bar by bar;
   at sampled moments save the snapshot, a chart with detections drawn and the
   later candles; Claude marks each detection correct / wrong / missed with a
   reason. To reduce anchoring, review in two passes: mark structures on a
   clean chart first, then compare with the engine's.
5. **Human spot-check**: the owner re-checks 10–20 % of Claude's reviews to
   measure how far that review can be trusted as the answer key.
6. **Forward usefulness** (separate from accuracy): first-retest hold rate per
   zone-score bucket; pattern hit-target-before-stop rate per tag signature.

Metrics: precision, recall, F1, time and price error, false-alert rate, early
detection time, completion and invalidation rates, multi-timeframe consistency.

### B5. Two experiments on identical data

| | A — Deterministic | B — Kronos-enhanced |
|---|---|---|
| Detectors | rule-based, closed candles | the same detectors, unchanged |
| Extra | — | Kronos forecasts 2–3 candles (M1/M5/M15); detectors run on the forecast paths |
| Output | confirmed and forming structure | plus *scenario frequency* (% of paths), emitted under its own `scenario_*` event kinds, never mixed with confirmed events |
| Status | **testing now** | after A is verified on real data |

Kronos enhances detection, never replaces the definitions. Scenario frequency
is not a probability until calibrated on out-of-sample data.

### B6. Layout

```
structure_engine/
  config/xauusd_structure_v1.json   every threshold (strictly validated)
  config.py        strict loader, schema, config hash
  bars.py          Bar model, CSV/TSV/JSONL/MT5-export loader, M1 -> M5..H4 aggregation
  atr.py           streaming Wilder ATR
  events.py        Event record, deterministic ids, stream fingerprint
  swings.py        causal swings
  zones.py         supply/demand zones + lifecycle
  sessions.py      session / prior-day levels (forming vs confirmed)
  patterns.py      M1 double/triple tops & bottoms
  scoring.py       zone ranking (top N)
  engine.py        the single streaming engine (live == test)
  feeds.py         RecordedFeed, MT5Feed, MT5 history export
  runner.py        CLI: backtest | live | export
  verification/    synthetic.py, reference.py, matching.py, causality.py, synthetic_accuracy.py
  tests/           pytest suite (21 tests)
```

### B7. Run it

From `apps/qwen_trade_software/backend`:

```bash
python -m structure_engine.verification.synthetic_accuracy --seeds 5      # accuracy report
python -m pytest structure_engine/tests -q                                # test suite

python -m structure_engine.runner export   --from 2016-01-01 --out data/XAUUSD_M1.csv   # needs MT5 (Part D)
python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --out runs/bt
python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --from 2024-01-01 --to 2024-02-01 --snapshot-every 60
python -m structure_engine.runner live     --out runs/live                # shadow: writes events, trades nothing
```

Back-test output folder: `events.jsonl`, `snapshots.jsonl`, `final_snapshot.json`,
`summary.json` (bars, time range, gaps, event counts, config hash, speed).
Speed is about 40,000 M1 bars/second, so ten years (~3.6 M bars) take roughly
1.5 minutes. Files exported by MT5's own "Export Bars" are in broker time:
add `--broker-time`.

### B8. Next steps

1. Export the 10-year XAUUSD M1 history on the trading PC and run the
   back-test end to end.
2. Point-in-time review on real data (B4 steps 4–5); tune thresholds only
   through new config versions (`xauusd_structure_v2.json`), never in code.
3. Add BOS/CHoCH, equal highs/lows, standalone liquidity sweeps, FVG, order
   blocks, head and shoulders, candle patterns, VWAP, previous-week levels,
   trend and channels, each with the same three test layers. External
   libraries (smartmoneyconcepts, TA-Lib, SciPy) only as reference checks, and
   only after passing the no-repaint test.
4. Experiment B: Kronos adapter in shadow mode, then compare A against B.
5. Modules 2 and 3 consume Module 1 events; old `goldflow/structure`
   detectors are retired one by one after a shadow comparison.

---

## Part C — The live system today (decision + risk)

### C1. Code layout

All live logic is the `goldflow` package in `apps/qwen_trade_software/backend/`.
Runtime state, logs, caches and data files stay in `backend/` itself
(`goldflow.core.paths.APP_DIR`), so moving code never moves data.

| Package | Responsibility |
|---|---|
| `goldflow/core/` | config (`runtime_config`, `instrument_config`), `paths`, `mt5_connection`, logging, TimescaleDB access, build manifest, tick archive, candle clock, configuration ledger |
| `goldflow/market/` | candle/context cache (`market_context_cache`), market runtime, ATR, news blackout, memory worker, qualification gate |
| `goldflow/intelligence/` | persistent market-intelligence event ledger, projections, retrieval broker, DXY |
| `goldflow/structure/` | current live detectors: structure, FVG, order blocks, liquidity, OTE, zones, qualified/mapped levels, shadow providers |
| `goldflow/regime/` | regime engine and regime policy |
| `goldflow/planning/` | session planner, plan branches/ladder, idea lifecycle, approach tracker |
| `goldflow/decision/` | entry Qwen reviewer + dashboard API, prompt composer, entry policy/safety/gates, trade geometry |
| `goldflow/execution/` | paper runner and MT5 demo executor |
| `goldflow/management/` | trade manager, trade management loop, management policy, profit protection |
| `goldflow/runtime/` | `software_runtime` process supervisor |

`backend/*.py` files (`reviewer.py`, `paper_runner.py`, `software_runtime.py`,
`market_context_cache.py`, `market_memory_worker.py`, `session_planner.py`,
`trade_management.py`, `profit_protection.py`, `paper_executor.py`,
`cache_qualification_gate.py`) are **launch shims**: kept at their historical
paths so the supervisor, `.ps1` scripts and scheduled tasks work unchanged.
Each only runs `goldflow.<package>.<module>` as `__main__`. Never put logic in a
shim. Inside the package import absolutely: `from goldflow.core import runtime_config`.
`backend/tools/` holds operator scripts; `backend/tests/` the live-code tests;
`planview/` the Next.js UI.

### C2. Processes

`software_runtime.py` is the single startup and supervision entry point
(launched at Windows login by `backend/start-reviewer.ps1`). It starts MT5 and
Ollama if needed, verifies the website, and supervises these children:

| Process | Role |
|---|---|
| `market_context_cache.py` | TimescaleDB candle/context hierarchy, compact minute packet, deterministic/Qwen qualification gates, readiness manifest. Its ready packet is the mandatory provenance source for entry Qwen. Never places orders. |
| `market_memory_worker.py` | feeds the market-intelligence event ledger |
| `reviewer.py` | builds MT5 snapshots, requests entry decisions from Qwen, records proposals, serves the dashboard API on :48632 |
| `session_planner.py` | day plan, session plans, hourly updates, session verdicts (`planner-state.json`) |
| `paper_runner.py` | consumes only fresh validated proposals; process-wide singleton lock |
| `trade_management.py`, `profit_protection.py` | manage the open position (split out of the reviewer) |

Dashboard API (`reviewer`, port 48632): `GET /snapshot`, `POST /deal-sheet`,
`GET /plan`, `GET /candles?tf=M15&count=200`, `GET /plan/history?date=YYYY-MM-DD`.
`QWEN_PLAN_GATING=1` gates entries against the validated session plan (off by default).
UI: `planview/` (dev `npm run dev` :3000; deployed to IIS :8088 and :80 by
`backend/install-planview-iis.ps1`). Deployed backend:
`C:\Users\HP\AppData\Local\QwenTradeReviewer`; website `C:\inetpub\GoldFlowPlanView`.

### C3. The four-phase trading lifecycle

Phases are sequential with distinct owners; a later phase may not silently
redo an earlier one's job.

1. **Build and cache context.** A fresh Qwen session reads immutable D1/H4/H1
   evidence, locates the parent auction and concludes `buy`, `sell` or `wait`.
   Cached for the session; refreshed only when its evidence epoch changes.
2. **Map and remember the target zone.** The reviewer converts the bias into
   one structurally identified zone; the runtime persists its lifecycle. A
   zone is a location to observe, never an order. It may stay armed through a
   later revisit within a bounded session window.
3. **Qualify the entry at the zone.** Code requires price inside the zone, a
   completed M1 probe-and-failure in the planned direction, and price at the
   plan's optimal zone edge. Direction, zone, target and structural
   invalidation are fixed before M1 can trigger. M5 is the local map, not a
   routine second confirmation. BOS/CHoCH, sweeps, FVG and OTE are confluence,
   not standalone triggers. After the short Qwen/M1 signal expires the
   executor keeps the zone armed up to 15 minutes but needs a fresh completed-M1
   probe-and-failure at the revisit; it cancels at once if price reaches
   invalidation or target first, or an M1 candle accepts through the zone.
4. **Protect the accepted trade.** Entry uses the planned structural
   invalidation as the reference and sizes from the risk budget. After fill,
   management works level to level on closed M5/M15 evidence: close when the
   immutable idea is confirmed invalid, tighten only behind newly formed
   structure, extend TP only after confirmed continuation. Never widen the
   stop, add risk, average, reverse, or exit on profit/points alone.

The runtime, not the model, enforces every safety invariant in phases 3 and 4.

### C4. Entry, execution and management rules (as implemented)

- A ready entry needs confidence ≥ 51 and an explicit buy/sell bias agreeing
  with the plan side. The runner rechecks cache readiness, UTC session,
  structural/playbook epochs and model identity immediately before execution.
- A proposal is valid for **60 seconds** from the recorded Qwen result; the
  runner polls every 250 ms and the executor checks the same deadline until fill.
- Qwen generation has no wall-clock cutoff on CPU, uses an 8,192-token context,
  and only one generation runs at a time.
- Inside the approved entry range the executor tracks the best quote and enters
  on the first bounded retracement or after a two-second observation.
- One 0.50-lot position; the executor maintains an emergency broker stop of
  3–5 price units derived from recent closed M1/M5 ranges, independent of Qwen.
- Daily cap: 100 filled positions, counted from MT5 deal history for the Qwen
  magic number (`QWEN_` ownership prefix); JSONL logs are audit evidence only.
- Management reviews each newly completed M1 candle with M1/M5 evidence,
  named levels, peak/giveback state and reached levels. A pre-model
  confirmation guard enforces a reached-level rejection or invalidation when
  completed M1 and M5 agree. P&L and elapsed time alone never confirm a close.

### C5. Market intelligence and context cache

Every completed XAUUSD or DXY candle used by cognition is an immutable,
provenance-tagged event. A deterministic reducer keeps one projection per
(symbol, timeframe) across D1…M1 — active leg, direction, transition, named
invalidation, unresolved condition, last evidence ID, structure epoch — and
replaying the ledger must reproduce it. The entry prompt receives a bounded
projection plus recent deltas. DXY may calibrate confidence and patience but
has no execution authority over gold. Qwen may request at most two
allowlisted, read-only retrievals per decision; it never gets SQL or write
access. Model qualification proves contract capability and never suppresses
projection refresh when a structure epoch changes.

**Storage (since 2026-09-10).** All SQL persistence uses TimescaleDB only, in
the `fallback_positive` schema: completed/forming candles, ticks, cache
objects, readiness, Qwen validations, latency, intelligence events,
projections, retrieval audits. There is no SQLite fallback; a missing
`QWEN_TIMESCALE_DSN` fails closed before trading services become ready. Local
JSON/JSONL logs and health files remain as inspectable evidence.

### C6. External structure providers (shadow only)

External libraries plug into `goldflow/structure/market_structure_providers.py`
behind one schema and run as shadow evidence only: SciPy prominence swings,
scikit-learn DBSCAN zones, TA-Lib candles, Smart Money Concepts (live-shadow);
SMC Toolkit, Ruptures, Statsmodels, VectorBT, Stock Indicators ZigZag
(offline; ZigZag repaints and can never validate an entry). They live in a
separate Python 3.12/3.13 environment (`requirements-structure.txt`) because
the MT5 runtime uses Python 3.14. The live process writes one immutable sample
per completed M5 candle to `structure-shadow-input-YYYY-MM-DD.jsonl`; after
three more M5 bars both native and external calls are labelled against the
same ATR-normalised outcome. Shadow output never reaches prompts, validators
or execution. No provider gains authority without walk-forward evidence and a
revision of this document.

### C7. Build identity

`goldflow/core/build_manifest.py` hashes every decision-path module
(`goldflow/...` relative paths) and the runtime tunables into a `build_id`;
`frozen-build.json` records the frozen build. Results from different build ids
must not be pooled. **The 2026-10-31 restructure changed every path, so
re-freeze once before the next paper run:** `python tools/freeze_build.py`.

---

## Part D — MT5 connection

Every service — the live system and the structure engine's live feed and
export — reaches MT5 through **one** module, `goldflow/core/mt5_connection.py`,
configured by **one** file.

1. Copy `backend/config/mt5_connection.example.json` to
   `backend/config/mt5_connection.json` (git-ignored, per machine).
2. Edit the properties:

| Key | Meaning | Default |
|---|---|---|
| `terminal_path` | full path to `terminal64.exe` of the MT5 install to use | `C:\Program Files\MetaTrader 5\terminal64.exe` |
| `login` | account number to pin (`null` = whatever the terminal is logged into) | `null` |
| `server` | broker server name exactly as in MT5's login dialog | `null` |
| `password_env` | **name** of the environment variable holding the password | `QWEN_MT5_PASSWORD` |
| `timeout_ms` | how long MT5 may take to start/attach | `60000` |
| `portable` | MT5 portable mode | `false` |
| `fallback_attach_any` | if attaching at the path fails, attach to any running terminal (only when no `login` is pinned) | `true` |
| `require_demo` | refuse non-demo accounts in `ensure_demo()` | `true` |
| `broker_symbol` | the broker's exact gold symbol (XAUUSD, XAUUSDr, XAUUSD.m, GOLD…) | `XAUUSDr` |
| `server_time` | broker clock for bar times: `"ny_close"` (UTC+2 winter / UTC+3 US summer), `"utc"`, or a fixed number of hours | `"ny_close"` |

3. The password is **never** written in the file or git. To log in from
   Python, set it in the environment (`setx QWEN_MT5_PASSWORD "..."` on
   Windows, then open a new terminal). Leave it unset to use the terminal's
   saved login, which is how the system has always run.
4. One-off overrides without editing the file: `QWEN_MT5_TERMINAL`,
   `QWEN_MT5_LOGIN`, `QWEN_MT5_SERVER`, `QWEN_MT5_SYMBOL`.
   (`QWEN_PRIMARY_SYMBOL` still overrides the analysed symbol for the live system.)
5. Check the connection: `python -m goldflow.core.mt5_connection` from
   `backend/` prints the effective settings (no password), connects, and
   reports login, server, demo status and whether the symbol exists.

Unknown keys, or a `password` key, make loading fail, so a typo cannot
silently connect to the wrong account. With a pinned `login`, a connection to
any other account is refused. Live trading code additionally refuses non-demo
accounts.

---

## Part E — Training

The curriculum, data preparation and training process are governed only by
`model_training/CURRICULUM_AND_DATA_PREP.md`. New curriculum/data utilities go
only in `model_training/python_utilities_for_models/`. The Colab fine-tuning
pipeline is `scripts/` (`00_quickstart` → `01_preprocess` → `02_finetune` →
`03_evaluate`, `Train_Qwen14B_Colab.ipynb`, deps in `scripts/requirements.txt`);
`QuantLLMBot_training.zip` is the tracked curriculum bundle Colab pulls.
The live model is whatever `DEFAULT_QWEN_MODEL` names (currently
`qwen-trading-v004:latest` in code; the former README mentioned v005 — confirm
on the PC with `ollama list` and update the constant, not this line).

---

## Part F — Operations

All commands from `apps/qwen_trade_software/backend` unless noted.

| Task | Command |
|---|---|
| Live-code tests | `python -m pytest tests -q` (needs `QWEN_TIMESCALE_DSN` for the DB-backed tests) |
| Structure-engine tests | `python -m pytest structure_engine/tests -q` |
| Structure accuracy report | `python -m structure_engine.verification.synthetic_accuracy --seeds 5` |
| Check MT5 connection | `python -m goldflow.core.mt5_connection` |
| Restart everything | `Restart-QwenTradeSoftware.bat` (repo root) → `backend/restart-software.ps1` |
| Context cache self-test (offline) | `python market_context_cache.py --self-test` |
| Cache once, no model | `python market_context_cache.py --once --no-qwen --no-minute-benchmark` |
| Re-freeze build | `python tools/freeze_build.py` |
| Reconcile with broker | `python tools/reconcile_broker_truth.py` |
| Strategy report | `python tools/strategy_report.py` |

Repository hygiene: scratch scripts, back-test output and archived material go
in the git-ignored `_archive/` (or `runs/`), never the repo root. Runtime logs,
proposal/execution history, model files, lock files and caches are not committed.

---

## Appendix — History

**V2 (2026-08-17)** was written around a forensic audit of live demo trading
and fixed these problems in phases (full text in git history):
P01 no regime detection · P02 ATR wiring returned null · P03 guard pre-empted
Qwen every cycle · P04 guard closed on bounce-back · P05 no displacement
detection · P06 no swing-sequence tracking · P07 stale mapped levels ·
P08 confidence 0 with status ready · P09 H4 theses always rejected ·
P10 dashboard showed unqualified levels · P11 no LTF confirmation before entry ·
P12 `live_map` unknown to v004 · P13 build drift · P14 reached levels used peak
tick, not closed candle · P15 target mode ignored regime · P16 loss cooldown
cannot fix structural defects · P17 entry policy accepted `favorable_outside` ·
P18 HTF micro brackets · P19 no range detection · P20 no range↔trend transition
detection · P21 closed response missed by stale playbook.

**2026-09-10** TimescaleDB-only storage (C5).

**2026-10-31 — V3**
- Repository cleaned; all other docs folded into this one.
- Live backend reorganised into the `goldflow` package with launch shims (C1).
- One MT5 connection module and settings file (Part D); the broker symbol was
  previously hard-coded in 14 places.
- Module 1 deterministic Market Structure Engine added with its verification
  suite (Part B).
