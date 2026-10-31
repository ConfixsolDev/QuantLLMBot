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
| 1 structure | `market/`, `structure/`, `regime/`, `intelligence/` (live, not causality-tested) **and** the new `backend/structure_engine/` (deterministic, tested, runs on recorded data) | `structure_engine` replaces the old detectors one at a time, each only after it passes Part B's tests and a back-test comparison on the same data |
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
offline replay and untouched walk-forward → frozen demo-account test → promote,
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
library only, Python 3.10+. Status: **built, verified on synthetic ground
truth, and run end to end on real XAUUSD M1 history (B3b).** It is not yet
wired into the Qwen decision path. The system trades only an MT5 demo
account, so no shadow lane is needed: experiments run on recorded data, and
`live` mode simply runs the same engine on MT5 bars and writes events.

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
then M1 patterns; close-spike outcomes whose horizon has passed are labelled;
(4) M1 is aggregated to M5…H1 on the UTC grid, and closed H1 candles to H4
on the **New York grid** (B2a); for every higher-timeframe candle that
closed with this minute: ATR, swings, close-spike detection (H1/H4), and on
zone timeframes, zone ageing and new zones. Every event's `available_at` is the close of the M1
bar that produced it (asserted in code).

Event kinds: `swing`, `zone_created`, `zone_tested`, `zone_broken`,
`zone_expired`, `session_level`, `prior_day_level`, `pattern_pending`,
`pattern_confirmed`, `pattern_invalidated`, `pattern_superseded`,
`close_spike`, `close_spike_outcome`, `prior_week_level`, `displacement`,
`bos`, `choch`, `equal_highs`, `equal_lows`, `liquidity_sweep`,
`false_break`, `liquidity_taken`, `fvg_created`, `fvg_mitigated`,
`fvg_filled`, `fvg_expired`, `order_block_created`, `order_block_tested`,
`order_block_broken`, `order_block_expired`, `range_formed`, `range_break`,
`range_expired`. Each carries
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

| Displacement | M5–H4 | body ≥ 1.2 × ATR and ≥ 60 % of the candle range (ATR as of before the candle) | `displacement.py` |
| BOS / CHoCH + trend state | M5–H4 | candle **close** beyond the latest unbroken swing in the trend direction = BOS; close beyond the **protected** swing (the pull-back low/high that launched the last BOS) = CHoCH, trend flips; wicks never count | `trend.py` |
| Liquidity pools | swings M15/H1/H4, equal highs/lows M15/H1, Asia/London/NY, prior day, **prior week** (Sunday 17:00 NY), range edges | a pool is active once known, for 72 h, and is used up by its first interaction | `liquidity.py`, `sessions.py` |
| Liquidity sweep | judged on M5 | wick beyond the level by ≥ 0.05 ATR, candle closes back inside | `liquidity.py` |
| False break / accepted break | judged on M5 | close beyond the level; a close back inside within 3 candles = false break, otherwise liquidity taken | `liquidity.py` |
| Equal highs / lows | M15, H1 | two or more swings within 0.15 ATR with nothing sticking out between them; pool at the most extreme | `liquidity.py` |
| Fair value gap | M5–H4 | 3-candle gap ≥ 0.25 ATR; OPEN → MITIGATED (touched) → FILLED / EXPIRED | `fvg.py` |
| Order block | M15–H4 | on BOS/CHoCH: last opposite candle at or before the leg origin, leg must contain displacement; FRESH → TESTED → BROKEN / EXPIRED | `order_blocks.py` |
| Range | M15, H1 | last 20 candles within 3 ATR, top and bottom each touched ≥ 3 times; edges become liquidity pools; ends with a close beyond an edge | `ranges.py` |
| Close spikes | H1, H4 closes | the larger M1 move in the last 10 minutes before the close is ≥ 0.75 × H1 ATR (optional dollar floor); context: held vs rejected close, previous-candle sweep, session/prior-day levels swept (last 24 h), zone hit, H4 swing trend, volume ratio, session; outcome after 15/60/240 min: reversal (back beyond the spike start), continuation (beyond the extreme) or partial | `spikes.py`, `studies/close_spikes.py` |

Every threshold above is a key in `config/xauusd_structure_v1.json`; the
numbers here are the shipped values, not code constants.

#### B2a. Candle grid: H4 is New York time

M1, M5, M15, M30 and H1 candles use the UTC grid; brokers' whole-hour
offsets do not move them. **H4 is built from closed H1 candles and opens at
02, 06, 10, 14, 18 and 22 New York time**, the grid that starts at the 18:00 NY
gold session open (config `alignment`, `clock.py`). In UTC that is
22/02/06/10/14/18 in US summer and 23/03/07/11/15/19 in winter; the US
daylight-saving rule is built in (standard library only), and the switch
happens on Sunday 02:00 NY while gold is closed. Close spikes on H4 therefore
measure the New York H4 closes traders watch.

### B3. Measured accuracy (synthetic ground truth, 20 seeds, 2026-10-31)

| Detector | Precision | Recall | Notes |
|---|---|---|---|
| Swings, all six timeframes | 100 % | 100 % | streaming == independent offline reference (32,219 swings) |
| Zones H4 / H1 / M30 | 100 % | 100 % | 115 planted each; 85/85 weak-departure look-alikes rejected |
| Double/triple tops & bottoms | 100 % | 100 % | 139 planted; 101/101 shallow-neckline and mismatched-peak look-alikes rejected |
| No-repaint, determinism, invariants | PASS | | prefix replays reproduce the full run exactly |
| Zone ranking | — | — | built, **not yet validated** (needs forward usefulness on real data) |
| New York H4 grid, close spikes | tests | | EDT/EST boundaries, H4 = its four H1 candles exactly, spike detection, labels and no-repaint |
| BOS/CHoCH, order blocks, displacement, FVG lifecycle | hand-built scenario | | exact expected events: BOS up 105 (with displacement, protected 101.9) → BOS up 109 → CHoCH down 106.9; bullish OB 101.9–102.6 and bearish OB 108.1–109.8; FVG 104.6–106.8 created → mitigated → filled |
| Sweep / false break / accepted break | hand-built scenario | | sweep of 103.0, false break of 105.6, 107.8 taken; one fate per pool |
| Equal highs, ranges, trading week | scenarios | | EQH 103.0/103.05; range 99–101 formed then broken up; week starts Sunday 21:00 UTC (summer) / 22:00 UTC (winter) |
| FVG | offline reference | 100 % | streaming gaps identical to an independent offline scan, all five timeframes |
| Whole structure layer | no-repaint + invariants | PASS | on scenarios and random walks (40 tests in total) |

**Read these numbers honestly.** They prove the code implements its
definitions, including the hard near-miss cases. They do not prove the
definitions are useful on real gold. Pattern precision started at ~17 % and
reached 100 % through three definition changes found on synthetic data — a
prior-move requirement, depth relative to that move, and measuring in M5 ATR
instead of M1 ATR — plus a triple-trough rule and a supersede fix. All were
then confirmed on 15 seeds not used while making them, but the synthetic
generator was written by the same author, so real-data review (B4 steps 4–5)
is the real test.

### B3b. First run on real XAUUSD (2026-10-31)

Data: `model_training/datasets/raw/candles/XAUUSDr/M1` — 100,000 MT5 M1 bars
(true UTC, with tick volume) from 2026-04-28 19:45 to 2026-08-07 20:44 UTC.
The export stopped at exactly 100,000 bars, which is MT5's "Max bars in
chart" limit; raise it to Unlimited before exporting more history.

* Runs in about 4.5 seconds with the full structure layer (~22,000 bars/s).
* On this real data: **no-repaint PASS**, **deterministic PASS**, **0
  invariant violations** over all 48,812 events (re-checked after the
  structure layer was added).
* Structure layer on the same 3.3 months:

  | | M5 | M15 | M30 | H1 | H4 |
  |---|---|---|---|---|---|
  | BOS | 1407 | 499 | 237 | 125 | 25 |
  | CHoCH | 470 | 141 | 78 | 41 | 9 |
  | Displacement | 1233 | 427 | 202 | 111 | 34 |
  | FVG | 2056 | 690 | 346 | 171 | 51 |
  | Order blocks | – | 237 | 121 | 70 | 16 |
  | Equal highs / lows | – | 154 / 120 | – | 35 / 25 | – |
  | Ranges | – | 44 | – | 5 | – |

  Liquidity (judged on M5): 765 sweeps — of which **330 (43 %) failed**
  (a close beyond the level within 3 candles) — 339 false breaks, 360
  accepted breaks; 14 prior-week levels.
* **Cross-verification (2026-10-31).**
  - Numeric: `verification/audit.py` rebuilt every candle from the raw M1 file
    with independent code (New York H4 via the `zoneinfo` tz database) and
    re-checked all 9,423 BOS/CHoCH, sweep, false/accepted break, failed-sweep,
    FVG and order-block events: **0 disagreements**.
  - Visual: Claude reviewed trend, liquidity, order-block, FVG and
    range/equal-level charts. Definitions held on every chart checked. The
    review found and fixed three real problems:
    1. *Late BOS*: 30 % of BOS events were on levels price had already closed
       beyond earlier (an older swing behind the one reported was never
       retired). Fixed: one close now retires every level it closes beyond;
       BOS events fell from 3,049 to 2,293, all remaining ones first breaks.
    2. *Weekend "FVGs"*: Friday-close → Sunday-open jumps were counted as fair
       value gaps. Fixed: the three candles must be consecutive.
    3. *Sweeps that were really breaks*: a wick-and-close-back candle followed
       at once by a close through the level. Now reported as `sweep_failed`.
    Open tuning questions for the owner's review (config only): M5 swing
    strength 2 → 3; a small reclaim buffer (e.g. 0.1 ATR) so a false break
    needs a real close back, not a tick back; zones remain sparse.
* Claude's first look at the per-layer review charts: BOS/CHoCH lines, order
  blocks (last opposite candle before the impulse), FVG lifecycles and
  sweep / false-break / taken labels matched the candles in every sampled
  chart; M5 trend events are frequent (strength-2 swings) — the review
  decides whether M5 should use strength 3.
* Events: 27,770 swings, 40 zones created (99 tests, 16 broken, 22 expired),
  71 confirmed patterns out of 259 pending, 219 session levels, 87 prior-day
  levels, 89 close spikes.
* Close spikes: median size $16.1 (range $10.1–40.1), the size you described.
  After 60 minutes: 16 % reversal, 37 % continuation, 47 % partial; after 240
  minutes: 24 / 38 / 38. Spikes whose candle closed **held** reversed within
  60 min only 7 % of the time; spikes that left a **rejection** wick reversed
  36 % (n = 28, still an anecdote). Most groups are under 30 events — the
  10-year export is needed before any of these are rates.
* First visual review (M5/M15 charts from `review.py`, judged by Claude, not
  yet spot-checked by the owner):
  - swings and HH/HL/LH/LL labels match the charts; on M5, strength 2 marks
    every minor wiggle (consider 3 in a v2 config);
  - session levels (Asia/London/New York, day) are drawn where they should be;
  - confirmed double tops/bottoms in the sampled charts were visually valid;
  - **zones are sparse**: 40 in 3.3 months, usually far from price, almost
    never retested in the samples. The base/departure thresholds are probably
    too strict for real gold; candidate for v2 after a proper review.
* The older files in `candles/XAUUSDr/H4/*_H4_NY.csv` are labelled New York
  but their candles start at 00/04/08 UTC — they are UTC-aligned, not the NY
  grid above. Do not use them as H4 truth.

Artifacts of this run (not committed, git-ignored): `_archive/structure_runs/real_2026-04_08/`
— `events.jsonl`, `summary.json`, `close_spike_study.txt/json`,
`close_spikes.csv`, and `review_m15/` + `review_m5/` (open `index.html`, judge
rows in `review_template.csv`).

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
| Timeframes | M1–H4 | Kronos generates **M1, M30, H1 and H4** candles, each from its own history (the relationships between them are what we study) |
| Status | **running on real data now** | designed, not built yet |

Kronos enhances detection, never replaces the definitions. Scenario frequency
is not a probability until calibrated on out-of-sample data.

Design for B (agreed 2026-10-31):

* Kronos (`NeoQuasar/Kronos-small` / `-base`, context 512, PyTorch, GPU) runs
  in its own package and Python environment; Module 1 stays standard-library.
  Distinct paths come from `predict_batch` on N copies of the context with
  `sample_count=1` (the `sample_count` argument averages, it does not return paths).
* Forecasts per timeframe: M1, M30, H1, H4, each 2–3 candles ahead from its
  own closed-candle history. Independent forecasts will not add up
  (three M1 hours ≠ the forecast H1); that disagreement is measured, not forced.
* Scored against what actually happened: direction hit rate, interval
  coverage, sample-based CRPS, level-touch Brier score, cross-timeframe
  agreement, and — for close spikes — P(reversal) Brier score against the
  running base rate from the spike study. Kronos earns a place only by beating
  a no-skill bootstrap forecaster and those base rates.
* Higher timeframe drives, lower timeframe signals or manipulates: measured
  through close spikes (B2) and, next, lower-timeframe breaks that come before
  the higher-timeframe confirmation (lead time in minutes).

#### B5a. The comparison lab (`backend/research_lab/`, built 2026-10-31)

Three stages, so the expensive Kronos part runs once on the trading PC and
everything else runs anywhere:

| Stage | Command (from `apps/qwen_trade_software/backend`) | Where |
|---|---|---|
| 0 dataset | `python -m research_lab.dataset --m1 <M1 folder> --out lab_runs/real` | anywhere, seconds |
| 1 forecasts | `python -m research_lab.forecast --m1 <M1 folder> --decisions lab_runs/real/decisions.jsonl --forecaster kronos --device dml --kronos-repo C:\Kronos --out lab_runs/real/forecasts_kronos.jsonl` (resumable; `--limit 50` to test) | trading PC, `kronos-dml` env |
| 1b yardstick | same with `--forecaster bootstrap --out .../forecasts_bootstrap.jsonl` | anywhere, seconds |
| 2 compare | `python -m research_lab.compare --decisions lab_runs/real/decisions.jsonl --forecasts kronos=... --forecasts bootstrap=... --out lab_runs/real/report.json` | anywhere |

* Decision points: every H1 close (1,530 in the 3.3 months of data).
* Without Kronos = 63 deterministic structure features (trend/BOS/CHoCH per
  timeframe, protected-level distance, liquidity above/below and what just
  happened there, FVG/OB/zone distances, ranges, session, momentum, spike).
* With Kronos = the same plus Kronos path summaries on M1, M30, H1, H4.
* Labels: direction after 1 h and 4 h; ±1 ATR(H1) first-touch within 4 h;
  spike reversal after 60 min. Walk-forward; training only on labels already
  known; paired bootstrap of the Brier difference decides "better".
* Contenders: base rate, each forecaster alone, XGBoost on structure,
  XGBoost on structure + Kronos, XGBoost on structure + bootstrap (control).

**First result (3.3 months, bootstrap only — Kronos not yet run):** nothing
beat the base rate. XGBoost on structure features was *worse* than the base
rate (Brier skill −6 % to −14 %): ~600 training rows and 63 features are too
few, so it learns noise. This is the expected small-sample outcome, not a
verdict on the features; the 10-year export (~60,000 H1 decisions) is needed
before any model comparison means something.

**Where XGBoost belongs (recommendation):** not in detection — structure
definitions stay deterministic and reviewable. Its place is a calibrated,
walk-forward *meta-model* that turns the structure snapshot (and, if it
earns it, Kronos features) into probabilities for well-defined outcomes,
plus an ablation tool: with vs without Kronos, with a bootstrap control.
Keep it shallow (depth 3), few features, retrained on known labels only, and
accept it only if it beats the base rate out of sample with a clear interval.

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
  clock.py         candle grids: UTC, and the New York H4 grid (US DST built in)
  spikes.py        close spikes into H1/H4 closes + outcome labels
  displacement.py  strong-candle test (building block)
  trend.py         trend state, BOS, CHoCH
  liquidity.py     liquidity pools; sweeps, false breaks, accepted breaks; equal highs/lows
  fvg.py           fair value gaps + lifecycle
  order_blocks.py  order blocks + lifecycle
  ranges.py        consolidation ranges
  engine.py        the single streaming engine (live == test)
  feeds.py         RecordedFeed, MT5Feed, MT5 history export
  runner.py        CLI: backtest | live | export (files or whole folders)
  review.py        point-in-time review charts (HTML/SVG) + review template
  studies/         close_spikes.py: base rates from a back-test's events
  verification/    synthetic.py, reference.py, matching.py, causality.py, synthetic_accuracy.py,
                   audit.py (independent re-check of every event against raw candles)
  tests/           pytest suite (42 tests)
```

### B7. Run it

From `apps/qwen_trade_software/backend`:

```bash
python -m structure_engine.verification.synthetic_accuracy --seeds 5      # accuracy report
python -m pytest structure_engine/tests -q                                # test suite

python -m structure_engine.runner export   --from 2016-01-01 --out data/XAUUSD_M1.csv   # needs MT5 (Part D)
python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --out runs/bt
python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --from 2024-01-01 --to 2024-02-01 --snapshot-every 60
python -m structure_engine.runner live     --out runs/live                # same engine on MT5 bars; writes events, places no orders
python -m structure_engine.runner backtest --m1 ../../../model_training/datasets/raw/candles/XAUUSDr/M1 --out runs/real
python -m structure_engine.studies.close_spikes runs/real/events.jsonl --json runs/real/spikes.json --csv runs/real/spikes.csv
python -m structure_engine.review --m1 ../../../model_training/datasets/raw/candles/XAUUSDr/M1 --out runs/review --samples 16 --tf M15
python -m structure_engine.review --m1 <M1 folder> --out runs/review_trend --tf M15 --layers swings,trend,ob   # one structure family at a time
#   layers: swings, levels, zones, patterns, spikes, trend, liquidity, eq, fvg, ob, ranges
python -m structure_engine.verification.audit --m1 <M1 folder> --events runs/real/events.jsonl   # independent numeric re-check
```

Back-test output folder: `events.jsonl`, `snapshots.jsonl`, `final_snapshot.json`,
`summary.json` (bars, time range, gaps, event counts, config hash, speed).
Speed is about 40,000 M1 bars/second, so ten years (~3.6 M bars) take roughly
1.5 minutes. Files exported by MT5's own "Export Bars" are in broker time:
add `--broker-time`.

### B8. Next steps

1. Raise MT5 "Max bars in chart" to Unlimited, export the full XAUUSD M1
   history (`runner export`) and rerun the back-test, spike study and review.
2. Point-in-time review on real data (B4 steps 4–5); tune thresholds only
   through new config versions (`xauusd_structure_v2.json`), never in code.
3. Done 2026-10-31: BOS/CHoCH, equal highs/lows, liquidity sweeps, false and
   accepted breaks, FVG, order blocks, displacement, ranges, previous-week
   levels. Still open: head and shoulders, candle patterns, VWAP, channels.
   External libraries (smartmoneyconcepts, TA-Lib, SciPy) only as reference
   checks, and only after passing the no-repaint test.
4. Experiment B: Kronos forecasts on M1, M30, H1 and H4 on the same
   back-test data, compared against A (B5).
5. Modules 2 and 3 consume Module 1 events; old `goldflow/structure`
   detectors are retired one by one after a back-test comparison.

### B9. Roadmap — Module 1 first

Owner's rule (2026-10-31): **market structure must be right and trusted
before anything else is built on it.** Kronos (B5), Qwen decisions (Module 2)
and risk (Module 3) wait for the gate below.

1. **Data:** export the full XAUUSD M1 history (MT5 max bars = unlimited).
2. **Review on real gold:** per-layer review packs (trend, liquidity, FVG,
   order blocks, ranges/equal levels, zones, patterns); Claude marks every
   detection correct / wrong / missed; the owner re-checks 10–20 %.
3. **Tune by config only:** a new `xauusd_structure_v2.json`; rerun the tests
   and the review; repeat until the gate passes.
4. **Gate:** the owner accepts the reviewed precision/recall per structure;
   no-repaint, determinism and invariants pass on the full history.
5. Then: Kronos experiment B → Module 2 (Qwen reads the structure snapshot)
   → Module 3 (simulated broker for tests, MT5 demo live) → demo soak (A6).

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
- Same day, later: H4 on the New York grid (built from H1), close-spike
  detector and study, point-in-time review charts, and the first end-to-end
  run on real XAUUSD M1 (B3b). Kronos experiment B designed (B5).
- Later the same day: the market-structure layer — displacement, BOS/CHoCH,
  liquidity pools with sweeps / false breaks / accepted breaks, equal
  highs/lows, FVG, order blocks, ranges, prior-week levels — with scenario
  tests, an FVG reference and real-data checks; per-layer review charts;
  roadmap B9 (Module 1 first).
- Later still: independent audit and three fixes from cross-verification;
  `research_lab` comparison (structure vs + Kronos vs XGBoost, walk-forward),
  first run with the bootstrap yardstick (B5a).
