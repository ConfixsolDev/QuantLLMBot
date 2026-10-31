# XAUUSD Quantitative Trading System — Architecture V3

> **THE ONE AND ONLY DOCUMENT.** Architecture, code layout, how to run
> everything and how changes are allowed. Improve this file in place; do not
> add other Markdown documents.
>
> **State on 2026-10-31: clean slate.** The codebase contains only the
> deterministic market-structure engine and the application that feeds it
> from MT5, stores everything in the database and shows it on the website.
> The previous Qwen trading system, its prompts, training material and tools
> were removed; they are recoverable from git tag `pre-clean-2026-10-31`.
> Qwen will be rebuilt from scratch on top of this (Part E).

| | |
|---|---|
| Version | **V3** — 2026-10-31 (V2: 2026-08-17) |
| Instrument / broker | XAUUSD (gold), MetaTrader 5 (demo); the application reads data only |
| Start | `Start-QuantLLM.bat` (repository root) → website http://127.0.0.1:8765/ |
| Database | existing PostgreSQL / TimescaleDB, schema `structure` (Part C2) |
| MT5 connection | `backend/config/mt5_connection.json` (Part D) |
| Structure config | `backend/structure_engine/config/xauusd_structure_v1.json` (Part B) |

**Contents** — Part A rules · Part B the structure engine · Part C the
application (database, service, website, launcher) · Part D MT5 connection ·
Part E rebuilding Qwen: lessons and recovery · Appendix history

---

## Part A — Rules

### A1. The three modules (target)

```
core          bar data, config, clock, event log, MT5 connection, database   (shared)
1 structure   closed M1 bars -> swings, trend, liquidity, zones, FVG, OB...   BUILT (Part B)
2 decision    structure snapshot -> Qwen -> BUY / SELL / NONE                 to be rebuilt
3 risk        sizing, limits, orders, position management, broker            to be rebuilt
runner        live = MT5 feed (+ MT5 broker later); test = recorded bars (+ simulated broker)
```

### A2. The five rules

1. **Modules talk through data only.** Module 1 never calls Qwen, a strategy
   or the broker and never issues BUY or SELL. It emits events and a snapshot.
2. **Testing and live use the same code.** Only the bar source changes.
3. **No hard-coded thresholds.** Every number lives in a versioned JSON
   config; unknown or missing keys fail at load time; every event carries the
   config hash.
4. **Closed candles only; no look-ahead; no repainting.** Every event has an
   `available_at` time, and the tests prove it.
5. **Forming and confirmed are separate.** A running session high or an
   unfinished candle is never presented as a confirmed fact.

Plus: **Python computes, the model judges.** Deterministic code measures
structure; a model (Qwen, later) adds judgement on top, never the other way.

### A3. How changes are made

Before editing: which module owns the problem, what exact evidence
reproduces it, which rule or test could break, which deterministic test fails
before and passes after, what would falsify the claim. A detector change is
made by a **new config version** where possible (`xauusd_structure_v2.json`)
and must keep `python -m pytest` green (engine + application tests) plus the
no-repaint, determinism and audit checks on real data. Comment code for the
next reader: a header per file (what it does, what feeds it, what it outputs)
and a "why" next to every threshold and tricky branch.

### A4. The owner's strategy: higher-timeframe level, M1 rejection

The setup the system is being built around (owner, 8 months of practice).
**Module 1 only DESCRIBES it**: it records every fact the rules need, with
no trade logic. Turning facts into BUY / SELL / NONE is Module 2's job.

Sources: Grimes, *The Art & Science of Technical Analysis*, ch. 7 "Multiple
Time Frame Analysis" (pp. 213–227, the main reference); Elder's Triple Screen;
Brooks on double tops. Institutional evidence on levels: Osler (2000), FRBNY
*Economic Policy Review* — published support/resistance levels beat random
levels (bounce 60.8 % vs 56.2 %), tested against 10,000 sets of arbitrary
levels with a bootstrap; Osler (2003), *Journal of Finance* — take-profit
orders cluster AT round numbers (reversals there) and stop-losses just BEYOND
them (acceleration once crossed). The same random-level control is used in B3c.

The rule numbers below were assigned here from the owner's summary of the
strategy (the original MTF-01…14 write-up is not in this repository; replace
the wording with it when available, keep the evidence columns).
"Gold 2026" = study B3c on 100,000 real XAUUSD M1 bars (2026-04-28 → 08-07):
a first look, one trending regime, to be re-run on the full history.

| # | Rule (sell side; buys are the mirror) | Recorded by Module 1 | Gold 2026 says |
|---|---|---|---|
| MTF-01 | Work only at a higher-timeframe level (H1/H4 swing, session, day, week) | `level_created`, `htf_levels` in the snapshot | A level alone holds no better than a random nearby level (−2.5 pts) — location is necessary, not sufficient |
| MTF-02 | A touch is "get ready", never an entry | `level_test` | **Supported**: a touch without M1 rejection holds 40.5 % vs 47.5 % for random levels |
| MTF-03 | Enter only on a finished M1 rejection: poke beyond and close back inside, or an M1 double top | `level_rejection`, `level_pattern` | **Supported**: with rejection 54 % hold, without 40.5 % (engine: 51 % vs 35 %). Also true at random levels: it is a price-action fact, the level gives the place |
| MTF-04 | Best: poke past the level, close back, then the M1 double top | `level_pattern` (+ the earlier `level_rejection`; pattern tag `sweep`) | Promising, too few cases: 75 % vs 50 % random, n = 28 |
| MTF-05 | Do not fade a squeeze (tight range / rising lows into resistance) | `level_test.approach = squeeze` (+ detail) | **Inconclusive**: n = 59 (study) / 21 (engine), the two disagree in direction |
| MTF-06 | Fade a push: price driven into the level | `approach = push` | Not different from random (−2.3 pts) |
| MTF-07 | Each test weakens the level: 1st/2nd best, 3rd+ breaks more | `level_test.test_no`, `level_held`, `level_broken.tests` | **Partly contradicted**: the FIRST test is the weakest vs random (−9.4 pts; stops resting beyond fresh levels, cf. Osler 2003), the 2nd the strongest (+14 pts). The engine's merged levels show no difference. Re-test on full history |
| MTF-08 | Strongest with H1/H4 trending your way or ranging with price at the edge | `level_test.trend` (M15 / H1 / H4) | **Not supported** in this sample (with-trend −8 pts vs random); re-test |
| MTF-09 | H1/H4 trending against you: smaller target or skip | `trend` (as above) | Trade management — Module 2/3 |
| MTF-10 | Beware a stretched higher-timeframe move | `level_test.stretch_h1_atr` | No monotonic effect |
| MTF-11 | The trade must work at once: not moving within 1–3 bars or stalling at the level = out | `level_followthrough` (moved / stalled after 3 M1 bars) | **Strongly supported**: moved 79 % hold vs stalled 35 % (engine 74 % vs 35 %) |
| MTF-12 | One re-entry allowed straight after a stop-out | next `level_test` / `level_rejection` on the same level | Trade management — Module 2/3 |
| MTF-13 | M1 and H1 are 60× apart: read M5/M15 in between | M5/M15 swings, BOS/CHoCH, FVG (B2); `trend.M15` in `level_test` | Context, not tested here |
| MTF-14 | Stop at M1/M5 structure, target the next higher-timeframe level | M1/M5 swings; `htf_levels` sorted by distance in the snapshot | Trade management — Module 2/3 |

Sell checklist as Module 1 events (buys mirrored):
1. a resistance `level_created` (H1/H4 swing high, session/day/week high) above price;
2. `level_test` — note `test_no`, `approach`, `trend`, `stretch_h1_atr`;
3. `level_rejection` within 10 M1 bars of the touch (or a `level_pattern`);
4. `level_followthrough = moved` within 3 M1 bars — `stalled` means it is failing;
5. the outcome is recorded either way: `level_held` or `level_broken`.

These are hypotheses to test, not proven results: Brooks warns most double
tops fail, and B3c covers one 3-month regime only.

---

## Part B — Module 1: the Market Structure Engine

Package: `backend/structure_engine/` — standard library only, Python 3.10+. Status: **built, verified on synthetic ground
truth, and run end to end on real XAUUSD M1 history (B3b).** The
application (Part C) runs it live on MT5 bars and shows every marking on the
website. There is no Qwen and no trading in the codebase now.

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
| Close spikes | H1, H4 closes | the larger M1 move in the last 10 minutes before the close is ≥ 0.75 × H1 ATR (optional dollar floor); context: held vs rejected close, previous-candle sweep, session/prior-day levels swept (last 24 h), zone hit, H4 swing trend, volume ratio, session; outcome after 15/60/240 min: reversal (back beyond the spike start), continuation (beyond the extreme) or partial | `spikes.py` |

| VWAP + bands | from M1; events judged on M5 | volume-weighted typical price (h+l+c)/3 with MT5 tick volume, ±1σ / ±2σ bands; anchors: **day** (resets 17:00 New York), **week** (Sunday 17:00 NY), **session** (Asia / London / New York windows); `vwap_cross` = price changed side: an M5 close ≥ 0.5 ATR(M5) beyond VWAP on the other side from the last confirmed side (hysteresis: without it half the crosses were re-crossed within 15 min); `vwap_band_reject` = M5 candle trades beyond the 2σ band and closes back inside, once per episode (re-armed after a close back inside 1σ); events only after 30 M1 bars of the period | `vwap.py` |

| HTF levels (strategy A4) | levels: H1/H4 swings + session/day/week; tests on M1; breaks on M5 | a level is registered only while price is on the right side of it; levels within 0.3 ATR(M15) merge (sources = confluence; the outermost price until the first test). **Test** = M1 extreme within 0.10 ATR after price was ≥ 1.0 ATR away and ≥ 15 min after the previous test, numbered 1, 2, 3…, with approach (push / squeeze / drift over 20 M1 bars), stretch (H1 ATR over 24 h) and M15/H1/H4 trend; **rejection** = within 10 M1 bars, poke ≥ 0.05 ATR beyond and close back inside, with no M5 close beyond the level since the touch; **follow-through** = 3 M1 bars later moved ≥ 0.5 ATR away or stalled; **held** = 1.0 ATR away; **broken** = M5 close 0.3 ATR beyond (level retired); **expired** after 120 h (never during a test); **level_pattern** = confirmed M1 double/triple top/bottom with peaks within 0.5 ATR of a level tested in the last hour | `levels.py` |

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
* First visual review (M5/M15 review charts — tool since replaced by the website — judged by Claude, not
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

Artifacts of these runs (not committed): `_archive/structure_runs/` on the
trading PC (events, summaries, review chart packs, audit). The review-chart
and study tools that produced them were removed in the clean-up; the live
website (Part C) now shows the same markings.

### B3c. Level-reaction study: does the A4 strategy hold on gold? (2026-11-01)

`python -m studies.level_reaction --m1 <M1 folder>` (or `--db --from 2016-01-01`).
Written separately from `levels.py` (own touch / hold / break code), so it is
also an independent cross-check of the engine; section 8 of its report asks
the same questions of the engine's own events.

Method (an event study, as used for support/resistance by Osler 2000):
every H1/H4 swing, session, prior-day level and $50 round number is followed
on M1. A test is a touch within 0.10 ATR(M15) after price had been ≥ 1 ATR
away; it HELD if price then got 1 ATR away before an M5 close 0.3 ATR beyond
the level, else it BROKE. Features are measured at the touch (causal);
outcomes use the future. **Control:** random levels 0.5–3 ATR from each real
level, at least 1 ATR from any real level, tracked with identical rules.
Robustness: re-run with M1 vs M5 break closes, 0.6/0.6 ATR hold/break,
controls with 0 / 0.5 / 1 ATR clearance — the conclusions below held in all.

Result on 100,000 M1 bars (2026-04-28 → 08-07; 1,758 real tests, 2,530
control tests; Wilson 95 % intervals in the report):

* **A level by itself is not an edge**: 48.3 % hold vs 50.8 % random.
  Only prior-day levels lean positive (+2.7 pts, inside the noise).
* **What separates outcomes is M1 behaviour at the level**: with a
  poke-and-reclaim 54 %, without 40.5 %; and after the rejection, **moved
  within 3 bars 79 % vs stalled 35 %** — the biggest and most stable split.
* Test number: 1st test weakest vs random (−9.4), 2nd strongest (+14).
* Squeeze, trend alignment, stretch: no reliable effect at this sample size.
* Round $50 numbers: no edge here (Osler's round-number effect is for FX
  order flow; not added as levels).

What this means for Module 1: it must record the M1 facts at the level
(test, rejection, follow-through, outcome) precisely — that is what
`levels.py` does — and keep the weak/unproven ones (approach, stretch, trend)
as descriptive fields, never as filters. Caveats: one strongly trending
3-month regime, overlapping samples (intervals are optimistic), many splits
compared (some "effects" will be chance). **Re-run on the full history before
any of it is used for trading decisions.**

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

### B5. Kronos and XGBoost (evaluated, not in the codebase)

On 2026-10-31 a comparison lab tested structure-only vs structure + Kronos vs
XGBoost on top (walk-forward, Brier score, bootstrap control). On 3.3 months
of data nothing beat the historical base rate and XGBoost overfitted. The
owner chose to go **without Kronos**; Kronos would come back only if it
clearly beats structure-only and a random-forecast control on the full
multi-year history. The lab code is in git history (tag
`pre-clean-2026-10-31`, `apps/qwen_trade_software/backend/research_lab/`).
Recommended role for XGBoost if revived: a shallow, walk-forward meta-model
turning the structure snapshot into calibrated probabilities — never part of
detection.

### B6. Layout

```
backend/structure_engine/
  config/xauusd_structure_v1.json   every threshold (strictly validated)
  config.py        strict loader, schema, config hash
  bars.py          Bar model, CSV/TSV/JSONL/MT5-export loader, M1 -> M5..H4 aggregation
  clock.py         candle grids: UTC, the New York H4 grid, the trading week
  atr.py           streaming Wilder ATR
  events.py        Event record, deterministic ids, stream fingerprint
  swings.py        causal swings
  trend.py         trend state, BOS, CHoCH
  displacement.py  strong-candle test
  liquidity.py     liquidity pools; sweeps, failed sweeps, false and accepted breaks; equal highs/lows
  fvg.py           fair value gaps + lifecycle
  order_blocks.py  order blocks + lifecycle
  ranges.py        consolidation ranges
  zones.py         supply/demand zones + lifecycle
  scoring.py       zone ranking (top N)
  sessions.py      session / day / week levels (forming vs confirmed)
  patterns.py      M1 double/triple tops & bottoms
  spikes.py        close spikes into H1/H4 closes + outcome labels
  vwap.py          day / week / session VWAP with bands; crosses and band rejects
  levels.py        HTF levels for strategy A4: tests, M1 rejections, follow-through, held / broken
  engine.py        the single streaming engine (live == test)
  feeds.py         RecordedFeed (files / folders of M1 bars)
  runner.py        back-test CLI
  verification/    synthetic.py, reference.py, matching.py, causality.py,
                   synthetic_accuracy.py, audit.py
  tests/           pytest suite
```

### B7. Run it (from `backend/`)

```bash
python -m pytest structure_engine/tests -q                                   # engine tests
python -m structure_engine.verification.synthetic_accuracy --seeds 5          # planted-structure accuracy
python -m structure_engine.runner --m1 <M1 folder or files> --out runs/bt      # back-test to files
python -m structure_engine.verification.audit --m1 <M1 folder> --events runs/bt/events.jsonl   # independent re-check
python -m studies.level_reaction --m1 <M1 folder>                              # level study B3c (or --db)
```

About 22,000 M1 bars per second with the full structure layer: ten years
(~3.6 M bars) replay in under 3 minutes.

### B8. Next steps

1. Load the full XAUUSD M1 history into the database
   (`python -m quantllm import-mt5 --from 2016-01-01`), then review the
   markings on the website.
2. Point-in-time review on real data (B4 steps 4–5); tune thresholds only
   through new config versions (`xauusd_structure_v2.json`), never in code.
3. Done 2026-10-31: BOS/CHoCH, equal highs/lows, liquidity sweeps, false and
   accepted breaks, FVG, order blocks, displacement, ranges, previous-week
   levels, VWAP (day / week / session), HTF levels with tests / M1 rejection /
   follow-through (A4). Still open: head and shoulders, candle patterns,
   channels, role reversal (a broken resistance becoming support).
   External libraries (smartmoneyconcepts, TA-Lib, SciPy) only as reference
   checks, and only after passing the no-repaint test.
4. Rebuild Qwen (Module 2) from scratch on top of the structure snapshot,
   then risk/execution (Module 3).

### B9. Roadmap — Module 1 first

Owner's rule (2026-10-31): **market structure must be right and trusted
before anything else is built on it.**

1. **Data:** load the full XAUUSD M1 history into the database
   (`python -m quantllm import-mt5 --from 2016-01-01`).
2. **Review on the website — Replay page (C4b):** one month, day by day:
   play the day, mark every detection ✓ / ✗, add what was missed, run the
   automatic checks; the monthly scorecard gives precision and recall per kind.
3. **Tune by config only:** a new `xauusd_structure_v2.json`; rerun the tests,
   the audit and the review; repeat until the gate passes.
4. **Gate:** the owner accepts the structure; no-repaint, determinism and the
   independent audit pass on the full history.
5. Then: Qwen rebuilt from scratch (Module 2, reads the structure snapshot) →
   Module 3 (simulated broker for tests, MT5 demo live) → demo soak.

---

---

## Part C — The application

```
MT5 terminal ──closed M1──► quantllm service ──► PostgreSQL/TimescaleDB (schema "structure")
   (history + live)            │  StructureEngine (Part B), same code as tests
                               └─ HTTP :8765 ──► website (web/, served by the service)
```

### C1. Code

```
Start-QuantLLM.bat          one-click start (repository root)
requirements.txt            backend Python packages (psycopg, MetaTrader5, pytest)
backend/
  structure_engine/         Part B
  studies/                  research scripts (not used by the app): level_reaction.py (B3c),
                            trade_geometry.py (F3c)
  strategy/ qwen/ trading/  Part F: strategies, the Qwen model, execution
  quantllm/
    settings.py             database / API / history settings (config/app.json + environment)
    mt5_connection.py       the one MT5 module (Part D)
    database.py             tables, idempotent candle import, event store
    market_feed.py          MT5 history, MT5 live polling (closed bars only), CSV files
    overlays.py             engine events -> chart drawings
    replay.py               Replay page: one day's engine run, point-in-time chart, automatic checks
    service.py              the running service + HTTP API + website files
    __main__.py             CLI: serve | check | import-csv | import-mt5
    tests/                  database, fake-MT5 polling, service + API tests
  config/                   mt5_connection.example.json, app.example.json
web/                        Next.js website (static export, built once)
  src/app/page.tsx          status bar, timeframe + layer switches, chart, side panel
  src/app/replay/page.tsx   Replay & verify: day player, check sheet, day checks, month scorecard
  src/components/StructureChart.tsx   candles + every marking
  src/components/SidePanel.tsx        what the engine thinks right now
  src/lib/api.ts            API client and types
```

### C2. Database (your existing PostgreSQL / TimescaleDB)

Connection string in the environment variable `QUANTLLM_DB_DSN` (the
existing `QWEN_TIMESCALE_DSN` also works). Schema `structure` (change with
`QUANTLLM_DB_SCHEMA`); the old `fallback_positive` schema is not touched.

| Table | Content |
|---|---|
| `m1_candles` | every CLOSED M1 bar: symbol, time (UTC open), OHLC, tick volume; primary key (symbol, time); a hypertable when TimescaleDB is installed |
| `events` | every structure event of the current engine run (id, kind, timeframe, time, available_at, config hash, data as JSONB); rebuilt at each start so it always matches the running engine |
| `reviews` | your verdicts from the Replay page: event id (or `missed-…`), day, kind, timeframe, time, verdict `correct` / `wrong` / `missed`, note — never rebuilt (event ids are deterministic, so verdicts stay attached while the config is unchanged) |
| `service_state` | small facts such as the last replay window and config hash |

Higher timeframes are never stored: the engine rebuilds them from M1 the
same way every time (H4 on the New York grid).

### C3. The service — `python -m quantllm serve` (from `backend/`)

1. API and website up at once on http://127.0.0.1:8765/.
2. **History:** copies every closed M1 bar the database is missing from MT5,
   back to `history_days` (default 365).
3. **Replay:** pushes the last `replay_days` (default 60) of stored bars
   through a fresh engine and rebuilds the `events` table (progress shown on
   the website).
4. **Live:** every 2 s, new closed M1 bars from MT5 are stored and pushed
   through the same engine. Without MT5 the service keeps running on stored
   data and retries every 30 s. `--no-mt5` runs from the database only.

Other commands: `python -m quantllm check` (database + MT5),
`python -m quantllm import-csv <files or folders>` (load existing M1 CSVs,
e.g. `model_training/datasets/raw/candles/XAUUSDr/M1`),
`python -m quantllm import-mt5 --from 2016-01-01` (full history; set MT5
Tools → Options → Charts → Max bars in chart to Unlimited first).
Optional settings: copy `backend/config/app.example.json` to `app.json`.

API (JSON): `GET /api/health` (state, progress, last bar, counts),
`GET /api/chart?tf=M15&bars=300` (closed candles, forming candle, overlays:
BOS/CHoCH lines, zone/OB/FVG/range boxes with life spans, liquidity / spike /
pattern markers, session levels, swings), `GET /api/snapshot` (trend per
timeframe, liquidity pools and recent liquidity events, zones, order blocks,
gaps, sessions, pending patterns, VWAPs). Chart overlays also carry
`curves` (VWAP + bands per anchor for each candle).

Replay API: `GET /api/replay/days`, `GET /api/replay/day?date=YYYY-MM-DD`
(detections + verdicts), `GET /api/replay/chart?date=&tf=&t=&bars=` (the chart
as the engine knew it at time t, plus `future` candles),
`GET /api/replay/checks?date=` (automatic checks),
`GET /api/reviews/summary?from=&to=` (scorecard), `POST /api/reviews`,
`POST /api/reviews/delete`.

### C4. The website

One page at http://127.0.0.1:8765/: status (live / importing / replaying /
offline, MT5 and database state), timeframe buttons M1–H4, layer switches
(BOS/CHoCH, liquidity, zones, order blocks, FVG, ranges, session levels,
swings, spikes & patterns), the chart with every marking, and a side panel:
trend per timeframe with the protected level, what just happened at
liquidity, nearest pools, ranked zones, order blocks and gaps near price,
session ranges. It refreshes every 5 seconds. Everything drawn comes from
`/api/chart`, so the page can never show something the engine did not say.
Layer "HTF levels" draws every higher-timeframe level (pink; thicker = two or
more sources) with its test count ("H1 sw high + LONDON high ×2") until it
breaks; markers R1, R2… = M1 rejection on test n, R1+ / R1- once the 3-bar
follow-through is known, LDT / LDB = an M1 double top/bottom formed at the
level. The side panel lists the nearest levels and the latest level events.

Layer "VWAP" draws the day (yellow), week (magenta) and session (blue) VWAP
with dashed ±1σ / ±2σ bands; band rejects show as small squares (VD / VW / VS).

### C4b. Replay & verify (http://127.0.0.1:8765/replay/)

For checking the deterministic code day by day before trusting it.

* **Day player:** pick a UTC day (any day with stored M1 bars); the engine
  runs from 10 days before (warm-up) to 6 h after. Step ◀ ▶ one chart candle
  (arrow keys), play/pause (space, 0.5–8×), or drag the slider. The chart
  shows only what the engine knew at the cursor (`available_at` ≤ cursor);
  later candles are faded behind the amber line — what happened next.
* **Check sheet:** every detection of the day in plain words, filterable by
  family. Click = jump to it. ✓ / ✗ stores a verdict (click again to clear),
  with a note. "Missed" adds what the engine should have marked at the cursor.
* **Day checks:** invariants, determinism (second run identical),
  no-repaint (runs stopped at 25 / 50 / 75 % of the day reproduce the full
  run up to that point), independent audit — about 2 s per day.
* **Month:** runs the day checks for every day of the month and shows the
  scorecard of your verdicts: precision = ✓ / (✓ + ✗), recall = ✓ / (✓ + missed).

Development: `cd web && npm run dev` with `NEXT_PUBLIC_API_BASE=http://127.0.0.1:8765`.

### C5. Start and test

* Restart (after an update, or if anything looks stale): double-click
  `Restart-QuantLLM.bat`. It stops every running copy (console windows,
  anything on port 8765, any `quantllm serve`) and starts again. A second copy
  can no longer start silently next to an old one: the server refuses a port
  that is in use (on Windows the default socket option let both bind, and the
  old process kept answering — found 2026-10-31).
* Start: double-click `Start-QuantLLM.bat`. It checks the database variable,
  installs missing Python packages, builds the website once (needs Node.js),
  opens the browser and runs the service.
* Tests (from `backend/`): `python -m pytest structure_engine/tests quantllm/tests strategy/tests qwen/tests trading/tests -q` (80 tests).
  The database tests use `QUANTLLM_TEST_DSN` (schema `quantllm_test`) or the
  `pgserver` package; they never touch the real schema.
* Verified 2026-10-31 on 100,000 real XAUUSD M1 bars in PostgreSQL 16:
  CSV import 1.3 s (re-import adds 0), replay 5 s, 47,662 events stored once
  each, API and website files served, overlays snapped onto real candles.

---

## Part D — MT5 connection

The application reaches MT5 through **one** module,
`backend/quantllm/mt5_connection.py`, configured by **one** file.

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
| `server_time` | broker clock for bar times: `"auto"` (read from the broker's daily 17:00 New York break; checked before every import), `"ny_close"` (UTC+2 winter / UTC+3 US summer), `"utc"`, or a fixed number of hours. A rule the data contradicts stops the import | `"auto"` |

3. The password is **never** written in the file or git. To log in from
   Python, set it in the environment (`setx QWEN_MT5_PASSWORD "..."` on
   Windows, then open a new terminal). Leave it unset to use the terminal's
   saved login, which is how the system has always run.
4. One-off overrides without editing the file: `QWEN_MT5_TERMINAL`,
   `QWEN_MT5_LOGIN`, `QWEN_MT5_SERVER`, `QWEN_MT5_SYMBOL`.
5. Check the connection: `python -m quantllm.mt5_connection` (or
   `python -m quantllm check`) from `backend/` prints the effective settings
   (no password), connects, and reports login, server, demo status and
   whether the symbol exists.

Unknown keys, or a `password` key, make loading fail, so a typo cannot
silently connect to the wrong account. With a pinned `login`, a connection to
any other account is refused. The application only reads market data; it
places no orders.

---

---

## Part E — Rebuilding Qwen: lessons and recovery

Everything removed on 2026-10-31 is in git: tag **`pre-clean-2026-10-31`**
(`git show pre-clean-2026-10-31:<path>`, or check it out on a separate
branch). That includes the old live system (`apps/qwen_trade_software/`),
training curriculum and utilities (`model_training/`), the Colab pipeline
(`scripts/`), the trading doctrine (`store/core_skill.md`, `store/sop.md`),
the comparison lab and all former documents.

Lessons from the old system that a rebuild should keep:

### E1. Invariants that protected the old live system

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

### E2. Proven-harmful changes — do not reintroduce

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

### E3. The four-phase trading lifecycle (old design, for reference)

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

### E4. Entry, execution and management rules of the old system

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

## Part F — Decision and trading: strategy, Qwen, execution

Owner's decisions (2026-11-01): one strategy at a time; Qwen only CHOOSES
among code-built candidates (or waits) and never sets a price; position size
= % of balance per stop distance; demo account only; no daily loss limit and
risk per trade may be 10 % or more during the demo learning phase; results
are judged in R so position size does not distort them; Qwen runs on the GPU
and the prompt stays under 6 KB.

```
structure engine events ──► strategy/runner ──► asks (a level test = a plan)
                                │                  └► strategy/template: doctrine + outlook + candidates
                                │                     + evidence (E-ids), <= 6 KB ──► qwen/decider
                                │                     ──► qwen/contract check ──► journal "decisions"
                                ├─► intents (approved plan + M1 rejection) ──► trading/executor ──► broker
                                └─► closes (rejection stalled)             ──► trading/executor
trading/executor.sync ──► finished trades: net, R multiple, close reason ──► journal "trades"
```

### F1. Code

```
backend/strategy/            Module 2a — strategies as data
  library/htf_level_m1_rejection.v1.json   rules (for code) + doctrine (for Qwen) + answer format
  model.py       strict loader; id@vN#hash identifies a strategy in every record
  outlook.py     compact market outlook from the engine snapshot + one-line event texts
  candidates.py  plan (on level_test) and trigger (on level_rejection): all prices from code
  runner.py      follows the event stream: asks / intents / closes / ended
  template.py    the prompt; refuses (PromptTooLarge) rather than silently cutting
  __main__.py    python -m strategy list | show | preview --m1 <bars> --date D [--save p.json]
backend/qwen/                Module 2b — the model
  client.py      Ollama or OpenAI-compatible server (LM Studio, llama.cpp, vLLM); stdlib only
  contract.py    answer rules: decision = candidate id or wait; confidence >= 51 to trade;
                 >= 1 citation, every citation an evidence id of this prompt
  decider.py     QwenDecider (lane B) and take_all (lane A, the baseline)
  __main__.py    python -m qwen ping | ask p.json
backend/trading/             Module 3 — execution
  intent.py      TradeIntent: the only object crossing from decision to execution
  settings.py    config/trading.json (mode off | paper | demo, risk_pct, magic ...)
  risk.py        lots = balance x risk% / ((|entry - stop| + spread + slippage) x value per unit),
                 rounded down; below the minimum lot = no trade (the stop is never moved)
  broker.py      MT5Broker (demo) and PaperBroker; lessons of the old executor kept
                 (stop + target sent with the order, magic number, IOC, exit-deal settle wait,
                 incomplete P&L never reported as zero)
  executor.py    demo -> not expired -> one position -> price in range -> stop/target sides
                 -> size -> order; close for strategy reasons; sync -> result in R
  journal.py     tables decisions / trades / refusals (schema "structure")
  pipeline.py    the bar-by-bar loop, the same for replay and live
  backtest.py    python -m trading.backtest --m1 <bars> | --db --from D [--lane all|qwen]
  verify.py      system checks on every decision and trade of a run (F3c)
backend/config/qwen.example.json, trading.example.json   copy to qwen.json / trading.json
```

The service (Part C) builds the pipeline when `trading.json` mode is
`paper` or `demo`; only live bars go through it, never the history replay.
`GET /api/trading` shows the mode, counters, recent decisions and trades.

### F2. The strategy as code sees it (htf_level_m1_rejection v1)

* **Plan** on every `level_test` that passes the rules (side, session, test
  number, approach): sell at resistance / buy at support; planned stop =
  level + 0.4 ATR(M15); target = the nearest opposite HTF level at least
  0.5 ATR away (else 2 R); R:R >= 1. Valid for the test window (10 + 3 + 1 bars).
* **Trigger** on the `level_rejection` of the same level and test, only if
  Qwen approved: stop = rejection candle extreme + 0.1 ATR (at least 0.3 ATR
  from the close), entry range = close +- 0.3 ATR, valid 3 M1 bars, R:R re-checked.
* **Close** at market when the rejection's `level_followthrough` is "stalled".
* Broker stop and target always travel with the order.

### F3. First baseline (lane A = take every candidate, paper broker)

`python -m trading.backtest --m1 <Apr-Aug 2026> --from 2026-05-01` (97,054
bars): 633 prompts, max 3,769 bytes (budget 6,000); 282 trades; win 22.7 %;
**average +0.11 R**, total +30.9 R, **max drawdown -25.9 R**. Closed by stop
175 (-0.90 R avg), by "stalled" 85 (0.00 R), by target 22 (+8.6 R). By test:
1st test -0.14 R (195 trades), 2nd +0.71 R (62), 3rd+ +0.58 R (25).
At 10 % risk per trade a 26 R drawdown empties the account (paper balance
10,000 -> 330): judge the strategy in R, and expect demo resets.
This is the yardstick: Qwen (lane B) must beat it on the same days.

### F3b. The template (v2) and the Qwen test dataset (2026-11-01)

Template v1 was read "as Qwen" on real prompts before any use; problems found:
positional arrays (["up", 4069.0]) a reader must guess; R:R 12–21 that looks
irresistible but comes from a tiny planned stop; evidence that repeated the
candidate and wasted space on session-VWAP touches; ages like "6157m"; and the
decision taken at the level TOUCH, before the most informative fact (the M1
rejection itself) existed. v2 (strategy file `htf_level_m1_rejection.v2.json`,
v1 retired unused; superseded by v3, F3c):

* Qwen is asked AT the M1 rejection (`rules.decision_point = "rejection"`);
  an approval enters at once (GPU latency is seconds).
* Named fields with a FIELDS legend in the system message; `market` (now,
  session + minutes in, ATR, M15 range vs ATR, day high/low, trend + protected
  level per TF, ranges price is in, VWAPs in sd, nearby levels with
  "beyond" when price is past one), `candidates` (level + history of earlier
  tests, approach, stretch, rejection quality: poke / wick / close-back /
  volume, the exact trade from code, obstacles between entry and target),
  curated `evidence` with readable ages.
* Two levels hit by one candle with the same trade are offered once.
* Qwen may cite evidence ids AND candidate facts (C1.rejection ...).
* Size: median 4.7 KB, max 4.9 KB of the 6 KB budget.

`python -m strategy.dataset --m1 <bars> | --db --from D --to D --out <dir>`
writes every prompt the live system would send (system.txt + prompts.jsonl,
byte-exact) and a separate answer key labels.jsonl (result in R, exit, best /
worst excursion, follow-through, level outcome). First dataset: 2026-05-01 →
08-08, 331 prompts, `data/qwen_dataset/2026-05-01_2026-08-08/` (not in git).

Blind check (Claude answering 12 random prompts as Qwen, labels hidden until
after): the template was readable and decisions could be argued from it —
4 takes, 8 waits — but **all 12 candidates lost or went flat, including the
ones whose rejection moved and whose level HELD**. Over the whole set,
"moved and held" candidates still hit the stop 72 % of the time: the stop
(rejection extreme + 0.1 ATR, min 0.3 ATR) is inside normal re-test noise.
Trade geometry, not only selection, decides results. A first scan of stop /
target / management variants on these 3 months found no robust winner (the
best, break-even at +1 R, averaged +0.16 R, inside the noise of 331 trades).
Decision for the owner: freeze the trade geometry on the full year of data
before collecting Qwen answers.

### F3c. Strategy v3: stop at least 1.2 ATR (owner's rule, 2026-11-01)

Owner: "gold's noise is always high — the stop must be at least 1 to 1.2 ATR",
or behind the next higher-timeframe level. `htf_level_m1_rejection.v3.json`:

* stop = beyond the rejection candle (+0.1 ATR) and **at least 1.2 ATR(M15)**
  from the entry (`stop_mode: "atr"`). Option `stop_mode:
  "beyond_higher_level"`: just beyond the nearest H4 / day / week level beyond
  the traded level, if within `max_stop_atr` (3) — built and tested, not the
  default (see below);
* target = **1.5 R** of the real risk (`target: "r_multiple"`);
* **no early "stalled" exit** — the trade ends at its stop or target;
* doctrine rewritten: Qwen's one question is "will this level hold?".

What the data said (May–Aug 2026, every candidate, `python -m
studies.trade_geometry`): with 1.2 ATR the outcome is decided by the level —
held ≈ +0.7 R, broken ≈ −0.6 R, about half and half — so selection (Qwen)
is what matters. A stop behind the next higher level averaged −0.004 R vs
+0.04 R for 1.2 ATR: the wider stop pushes the 1.5 R target out of reach.
Re-run the study on the full year before changing the default.

`trading/verify.py` checks that the system behaves exactly as specified on
every decision and trade (prompt budget, nothing trades without a "take",
stop >= 1.2 ATR on the right side, target = 1.5 R, risk money <= budget,
filled inside the entry window, one position at a time, complete P&L, exits
at the stop / target price, no early close). `python -m trading.backtest`
prints "system checks: ALL PASS" — May–Aug 2026: 246 trades, all pass.

### F4. Running it

1. `python -m qwen ping` — server reachable, model present (config/qwen.json).
2. `python -m strategy preview --m1 <bars> --date D --save p.json`, then
   `python -m qwen ask p.json` — one real prompt and Qwen's raw answer.
3. `python -m trading.backtest --db --from <day> --lane qwen` vs `--lane all`.
4. `config/trading.json` mode `paper` (live bars, simulated broker), later
   `demo` (MT5 demo account). A live account is refused in settings and executor.

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
- **Clean slate (2026-10-31, end of day):** removed the old Qwen system,
  training material, research lab and all other documents (tag
  `pre-clean-2026-10-31`); added the `quantllm` application — database
  (schema `structure`), MT5 history + live feed, service with HTTP API, the
  website rebuilt as a live structure chart, and `Start-QuantLLM.bat`.
- **Strategy A4 and HTF levels (2026-11-01):** the owner's
  higher-timeframe-level / M1-rejection strategy written down with sources
  (A4); level-reaction study with a random-level control on real gold (B3c);
  `levels.py` records level tests, M1 rejections, follow-through, held/broken
  and M1 patterns at levels; chart layer, side panel, Replay check sheet.
- **Part F (2026-11-01):** strategy / qwen / trading packages: versioned
  strategy files, deterministic candidates, 6 KB prompt with evidence ids,
  Qwen client + answer contract, risk sizing, MT5 + paper brokers, executor,
  journal tables, bar-by-bar pipeline, backtest lanes; first take-all baseline.
- **Expert replay review of real October days (2026-11-01):** the multi-
  timeframe narrative held up (e.g. 30 Oct: M5 CHoCH down → M15/M30/H1 BOS →
  H4 BOS; a false break of 3979 followed by an M5 CHoCH up; a failed sweep of
  3965 followed by the H1 level break). Fixed from the review: (1) during the
  28 Oct FOMC spike one H1 level was "tested" 7 times in 15 minutes — tests
  now need 15 min between them; (2) an M1 poke back after an M5 close beyond
  the level was called a rejection — it is a retest, no longer counted; (3) a
  follow-through "moved 0.0 ATR" when the rejection candle itself held the
  level; (4) the same swing on M15 and H1 was listed twice in sweeps; (5)
  Replay drew FVGs filled days earlier as open bands across the chart;
  (6) the Replay chart did not follow the cursor.
- **Broker clock (2026-11-01):** the 10-day check on real October data found
  every stored bar 3 hours early: the broker (XAUUSDr) reports UTC but
  `server_time` defaulted to "ny_close". Sessions, the New York H4 grid and
  the 17:00 NY trading day were all shifted. Now `server_time: "auto"` reads
  the broker clock from gold's daily 17:00 New York break, `connect_mt5`
  refuses to import when a configured rule contradicts the data, the service
  warns at start when stored bars are not UTC, the Replay day checks include
  "Clock", and `python -m quantllm reimport-mt5 --from <day> --yes` repairs the
  stored history. Logs are also written to `logs/quantllm.log`.
- **10-day check (2026-11-01):** day-by-day replay of the last 10 trading days
  (invariants, determinism, no-repaint, audit, point-in-time charts, level
  lifecycles — all pass). Fixed: expired HTF levels were drawn as still alive
  on Replay (new `level_expired` event); VWAP crosses whipsawed (0.5 ATR
  hysteresis: 35 → 14 a day, re-cross within 15 min 50 % → 12 %); band
  rejects repeated every candle of one poke (one per episode: 42 → 15 a day);
  two band rejects in one candle shared an id; a restarted service could share
  port 8765 with the old one (`Restart-QuantLLM.bat`, exclusive port); the
  console logged "live" every 2 s.
- **VWAP and Replay (2026-10-31, night):** day / week / session VWAP with
  bands, crosses and band rejects (B2); Replay & verify page with check sheet,
  automatic day checks and monthly scorecard; `reviews` table (C2, C4b).

