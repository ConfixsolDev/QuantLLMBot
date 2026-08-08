# Topic 4 — Relation Between Different Timeframes

> **Sources read:** `elder_trading_room` pp.96–97, 138–147, 155–158, 167–168 · `murphy_ta` pp.27–28, 43, 49, 64–66, 94–95, 182–183, 233, 332, 365–370, 385 · `grimes_art_science` pp.11–12, 28–29, 39–41, 68, 230–244 · `brooks_trends` pp.18, 87, 110, 135–137, 162, 199–202, 259–260, 272, 294, 308, 312, 335 · `brooks_ranges` pp.12, 20, 25, 30, 55 · `dalton_mind_over_markets` pp.31–39, 61, 71, 120–123, 152–159, 169–171, 201–204 · `carter_mastering` pp.56, 216, 268, 402–411, 460, 494, 502 · `chan_algo_trading` pp.140, 153–155 · `lien_fx_sessions` pp.83–88
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1.2)

---

## ⚠️ Calibration note read this before using anything below

Independent empirical work (outside this corpus) finds that the higher-to-lower timeframe
relationship is **well established for volatility** and **not established for direction**:

- **Volatility cascades down and is persistent.** How far price is likely to travel inside the
  next H1 is strongly conditioned by the H4/D1 volatility regime it sits in. This is the part of
  multi-timeframe analysis that survives testing. It licenses *sizing, stop distance, target
  distance and "is this move big or small for this context"* — nothing else. Grimes states the
  structural version of this: vertical distances scale roughly with the square root of the
  timeframe ratio, so a stop that works on M5 must be widened by about √6 to work on M30
  (`grimes_art_science p.29`). Lien's session range tables are the same fact in session form: the
  same instrument has systematically different range in Asia vs. London vs. the overlap
  (`lien_fx_sessions pp.83–88`).
- **Direction does not reliably cascade.** There is essentially no peer-reviewed validation of
  "the higher timeframe trend predicts the lower timeframe's directional edge." The corpus itself
  contains a quiet confirmation: Chan measures correlations between past returns over one horizon
  and future returns over another and finds coefficients mostly in the 0.03–0.26 range with
  p-values that are usually not significant, and notes that the *same* series shows momentum at
  some horizon pairs and mean reversion at others (`chan_algo_trading pp.153–155`). The sign of
  the cross-horizon relationship is not stable, which is exactly what a directional multi-timeframe
  filter assumes it is.
- **Therefore:** every directional multi-timeframe claim in this file is labelled `moderate` at
  most, never `strong`. `strong` is reserved for claims that are structural or definitional —
  facts about how bars are built out of smaller bars, what a not-yet-closed bar can and cannot
  contain, and arithmetic. The books assert directional edge with much more confidence than the
  evidence supports; that confidence is reported, not endorsed.

---

## Core concepts

| Concept | Definition (my words) | Sources | Evidence |
|---|---|---|---|
| Analysis timeframe vs. timing timeframe | Two different jobs. The analysis (higher) timeframe answers *which side, or none*; the timing (lower) timeframe answers *where exactly to get in and out*. Being right on side and wrong on timing still loses in a leveraged instrument. | `murphy_ta pp.27–28, 182–183, 365–370`; `elder_trading_room p.138` | moderate |
| Triple Screen | Elder's method: pick your favourite chart, call it *intermediate*, immediately step up one order of magnitude for a strategic long/short/stand-aside decision, come back to the intermediate chart and use an oscillator to enter *against the short-term wave but with the long-term tide*, then fine-tune the actual order on the intermediate or a shorter chart. | `elder_trading_room pp.138–147` | moderate |
| Factor of five | Elder's rule for spacing timeframes: each chart is about 5× the next one down (≈5 weeks/month, 5 days/week, ~5 hours in a session). Rounding is fine; it is a craft, not arithmetic. | `elder_trading_room pp.96–97, 140` | weak (the *spacing principle* is moderate; the specific number 5 is one author's convention) |
| Ratio 3–5 (Grimes' version) | Neighbouring charts should be related by a factor of roughly 3 to 5 — close enough that the lower chart explains what happened inside the higher bar, far enough that it is not a near-duplicate. A 20-min chart next to a 30-min chart adds nothing; a 1-min next to a 30-min throws away structure. | `grimes_art_science pp.28–29` | moderate |
| Screen-one primacy | The strategic decision is made *before* looking at the faster chart, precisely so the faster chart cannot colour it. Elder tells you not to peek at the dailies while judging the weekly. | `elder_trading_room p.141` | moderate |
| Stand aside is a position | If the analysis timeframe is not clearly bullish or bearish, "no trade" is the correct output of screen one, not a prompt to drop a timeframe and find a signal. | `elder_trading_room p.141` | moderate |
| Screen two never reverses screen one | An oscillator sell signal while the higher chart is up may be used to *take profit on longs*, never to go short. The lower timeframe can close a position; it cannot open one against the higher timeframe. | `elder_trading_room pp.143–144` | moderate |
| Dow's three trends (tide / wave / ripple) | Primary = tide, secondary/intermediate = the waves that make up the tide, minor = ripples on the waves. Each trend is a portion of the next larger one and is itself made of smaller ones. | `murphy_ta pp.43, 64–66` | strong (definitional); directional use of it: moderate |
| The trend of a shorter cycle is set by the longer one | Murphy's explicit statement of the multi-timeframe premise: establish the direction of the next longer cycle, then trade the shorter one in that direction. | `murphy_ta p.332` | moderate |
| Top-down order of operations | Begin wide and telescopic, end narrow and microscopic: monthly/weekly for perspective, daily for the decision, intraday last for precision. Long-term charts are for forecasting, explicitly *not* for timing. | `murphy_ta pp.182–183, 368, 385` | moderate |
| Fractal nesting | Every bar is literally composed of the smaller bars inside it. One H4 = 4 H1 = 16 M15 = 48 M5 = 240 M1. A swing high on your chart is just "the high of the prior bar" on some higher chart; the high of the prior bar on your chart is a swing high on some lower chart. Three M5 bars that reverse are a M15 reversal bar when the third one closes on the M15 boundary. | `brooks_ranges pp.12, 25, 30`; `brooks_trends pp.18, 136–137`; `grimes_art_science p.68` | strong |
| Reading inside the bar | From one bar's OHLC you can infer the *likely* lower-timeframe story but never the certain one — many different M1 paths produce the same H4 candle. Large bars usually contain lower-timeframe trends; small bars with mid-range opens and closes usually contain lower-timeframe ranges. | `grimes_art_science pp.39–41` | strong for the ambiguity claim; moderate for the trend/range inference |
| Developing (unclosed) higher-timeframe bar | The forming H4 bar's *open, high-so-far, low-so-far, range-so-far and elapsed fraction* are hard facts assembled from closed M15/M5 bars. Its *close* — and therefore its body, its colour, whether it is a trend bar or a doji, and whether any level "held on a closing basis" — does not exist yet and cannot be assumed. | `brooks_trends pp.199–202`; `elder_trading_room p.157`; `grimes_art_science pp.39–41` | strong |
| Bar-close discipline | Acting on a bar's shape before it closes is a specific, named way to lose: a perfect reversal bar can collapse in its final seconds. Elder's version is the "on close only" stop — exit only if the bar *closes* beyond the level. | `brooks_trends pp.199–202`; `elder_trading_room p.157` | strong (structural — the close is unknown until it is known) |
| Trend/range inversion across timeframes | Most trends are parts of ranges on a higher chart; most ranges are flags/pullbacks on a higher chart. A trading range on H4 is a pullback on D1. | `brooks_trends pp.87, 110, 308` | strong (definitional) |
| Sharp lower-timeframe trends live inside higher-timeframe ranges | When the higher chart is bracketing, expect *clean, strong* trends on the lower chart running between the bracket edges. This is the opposite of the naive "HTF range → LTF chop" expectation. | `grimes_art_science pp.241–242, 244` | moderate |
| Dominant timeframe / control | Do not assume the higher chart always matters more. Control passes between timeframes; part of the analytical job is deciding which structure is currently in charge. | `grimes_art_science pp.231–232, 244` | moderate |
| Countertrend lower-timeframe legs abort | Legs on the lower chart that run against a trending higher chart tend to be weaker and to end abruptly — and where they end is typically the ideal with-trend entry on the higher chart. | `grimes_art_science pp.232, 244` | moderate |
| Higher-timeframe overextension as a veto | A lower-timeframe setup taken while the higher chart is stretched far beyond its channel/band has a different risk profile: far higher chance of a violent failure. Skip it, or size and stop it differently — but do not ignore it. | `grimes_art_science pp.233, 237` | moderate |
| Initial balance / base | The early-session range is the day's base. Narrow base → easier to knock over → higher odds of range extension. Wide base → the extremes are more likely to hold for the day. | `dalton_mind_over_markets pp.31, 39` | moderate |
| Other-timeframe participant | The trader whose horizon spans more than one day. Locals/short-term flow builds the base; only other-timeframe participation produces range extension and real directional movement. | `dalton_mind_over_markets pp.33, 37` | moderate |
| Timeframe transition | Control changes intraday between one-timeframe (trending) and two-timeframe (rotational) conditions. Three cases: no transition; one→two (a probe beyond a reference attracts nothing and the market reverts to rotation); two→one (price breaks a reference and is *accepted*, producing a trend). | `dalton_mind_over_markets pp.120–123` | moderate |
| Time gives the signal, structure confirms | Acceptance is measured in time spent at price, not in price alone. Waiting for tails and range extension to confirm control means entering late; they are by-products of the auctions that already happened. | `dalton_mind_over_markets pp.121–122` | moderate |
| Brackets within brackets | There is no objectively correct bracket. Bracket definition is a function of *your* timeframe; six overlapping days is a bracket to a swing trader and part of one bracket edge to a long-term trader. You must declare which bracket you are trading. | `dalton_mind_over_markets pp.152–153` | strong (definitional) |
| Markets bracket most of the time | Roughly 70–80% of the time markets are in a bracket, not a trend. A permanent higher-timeframe *trend* filter is therefore mis-specified most of the time. | `dalton_mind_over_markets pp.71, 152` | moderate |
| Retracement bands from the higher timeframe | The higher timeframe sets how deep a lower-timeframe pullback should be allowed to go: minimum ~33–38%, typical ~50%, maximum ~62–66% of the prior leg. Past two-thirds, odds shift from "pullback" to "reversal / full retracement". For timing, the 40–60% zone is the practical buy/sell band. | `murphy_ta pp.43, 94–95, 366` | moderate |
| Correction ≠ price decline | Dalton's counterpoint: a correction is *counteraction*, not necessarily lower prices. Old longs can take profit into new initiative buying, producing a sideways or even higher-closing "correction". Absence of a price retracement is not absence of a correction. | `dalton_mind_over_markets pp.170–171` | moderate |
| Timeframe cherry-picking | Given enough candidate higher timeframes you can always find one on which your setup looks perfect. This makes unconstrained "check the higher timeframe" a bias generator, not a filter. | `brooks_trends pp.135, 272` | strong (logical/selection-bias argument) |
| Multi-timeframe is not always present | Sometimes there is simply no meaningful cross-timeframe consideration. If you have to work hard to see it, it is not there. | `grimes_art_science p.244` | moderate |

---

## Distilled rules

Timeframe ladder used throughout (each step is a factor of 3–6, per `elder_trading_room p.140` and
`grimes_art_science pp.28–29`):
`D1 → H4 → H1 → M15 → M5 → M1` (ratios 6, 4, 4, 3, 5). M30 sits between H1 and M15 and is used
only as a *timing* chart paired with an H4 or D1 analysis chart (6:1 and 48:1) — never paired with
H1 (2:1, redundant).

1. **Declare the pair before you look.** For every decision, name one analysis timeframe and one
   timing timeframe from the ladder, with a ratio between 3 and 6. Log both. If a decision cannot
   name its pair, it is not a decision. (`elder_trading_room p.140`; `grimes_art_science p.28`)
2. **Form the higher-timeframe read from closed higher-timeframe bars only, before consulting the
   timing chart.** Do not let the M5 picture enter the H4 read. (`elder_trading_room p.141`)
3. **Emit `stand_aside` when the analysis timeframe is not clearly directional.** Do not respond to
   an ambiguous H4 by dropping to M5 and finding something. (`elder_trading_room p.141`)
4. **Never open a position against the analysis timeframe on a timing-timeframe signal.** A
   counter-signal on the timing chart may only reduce or close an existing position.
   (`elder_trading_room pp.143–144`)
5. **Never infer higher-timeframe bias from lower-timeframe momentum.** M1/M5 impulse is not
   evidence about the H4 close. Inside one H4 bar there are 48 M5 bars; strong three-bar bursts in
   *both* directions occur many times within a single H4 bar of either colour, so their base rate
   as an H4-direction signal is near-zero. (`elder_trading_room pp.139–140`; `brooks_trends p.135`;
   `chan_algo_trading pp.153–155`)
6. **Any rule keyed to a higher-timeframe close must wait for that bar to close.** "H4 closed below
   support" is only computable at the H4 boundary. Until then the correct state is `pending`, not a
   guess. (`brooks_trends pp.199–202`; `elder_trading_room p.157`)
7. **You may use the developing higher-timeframe bar's high, low, range-so-far and elapsed
   fraction**, because those are assembled from *closed* lower-timeframe bars and cannot change
   retroactively. Label them `developing_*` so they can never be confused with closed values.
   (`grimes_art_science pp.39–41`)
8. **A break on a lower timeframe is not a break of a higher-timeframe level.** Only a close of a
   bar on the timeframe that *defines* the level counts as a break of it. M1 trading through an
   M15-defined level while the M15 bar closes back inside is a failed probe, not a break.
   (`brooks_ranges p.30`; `dalton_mind_over_markets pp.121–122`)
9. **Require acceptance, not just penetration, before promoting a lower-timeframe move into a
   higher-timeframe thesis change.** Operational form: N consecutive closes of the timing bar
   beyond the reference *plus* elapsed time at the new prices. Time gives the signal; structure
   confirms. (`dalton_mind_over_markets pp.121–123`)
10. **When the analysis timeframe is ranging, expect and trade clean trends on the timing
    timeframe between the range edges — and expect them to stop at those edges.** Do not convert
    such a trend into a higher-timeframe trend thesis. (`grimes_art_science pp.241–242, 244`;
    `dalton_mind_over_markets pp.158–159`)
11. **Take the timing-timeframe entry against the wave and with the tide:** in an up analysis
    timeframe, enter on timing-timeframe weakness (pullback into the mean / oversold), not on
    timing-timeframe strength. Buying dips beats buying crests. (`elder_trading_room pp.143, 157`)
12. **Bound the pullback you are willing to buy by the higher timeframe's prior leg:** entry zone
    38–62% (practical 40–60%), invalidation beyond ~66%. Beyond two-thirds, reclassify from
    "pullback in the higher trend" to "possible reversal", and stop treating the higher timeframe
    as directional. (`murphy_ta pp.94–95, 366`)
13. **Do not require a price retracement to call a correction complete.** A sideways H4 sequence
    that holds value while momentum resets is a valid correction. Test the *quality of the
    counter-move*, not just its depth. (`dalton_mind_over_markets pp.170–171`)
14. **Measure the session's initial balance and compare it to the recent average.** Narrow base →
    raise the prior on range extension and on a directional day; wide base → raise the prior that
    the session extremes hold. (`dalton_mind_over_markets pp.31, 39`)
15. **Veto, do not reverse, on higher-timeframe overextension.** If the analysis timeframe is far
    outside its channel/band, do not take the with-trend timing entry at normal size; either skip
    or halve size and tighten the exit. (`grimes_art_science pp.233, 237`)
16. **Cap the number of timeframes at three, fixed in advance.** Adding charts until one agrees is
    selection bias, not analysis; you can always find a higher timeframe that endorses your view.
    (`elder_trading_room p.97`; `brooks_trends pp.135, 272`)
17. **Never introduce a timeframe you do not normally consult while a position is open.** Grimes
    treats the urge as a discipline-failure warning; treat it as a hard block.
    (`grimes_art_science p.29`)
18. **Scale risk parameters by √(ratio) when moving a rule between timeframes.** A stop calibrated
    on M5 needs roughly √6 ≈ 2.4× the distance on M30. Do not port a stop distance across
    timeframes unchanged. (`grimes_art_science p.29`)
19. **When analysis and timing timeframes conflict and neither is dominant, output `wait`.**
    Resolve only by (a) the analysis bar closing and confirming, or (b) a documented timeframe
    transition with acceptance. (`dalton_mind_over_markets pp.122–123`; `grimes_art_science p.244`)
20. **State explicitly which timeframe's structure is in control, and re-evaluate it every closed
    analysis bar.** Do not hard-code "H4 always wins". (`grimes_art_science pp.231–232`)

---

## Worked examples

All examples are XAUUSD, H4 bars anchored at 00 UTC (bars: 00–04, 04–08, 08–12, 12–16, 16–20,
20–24), sessions Asia 00–07, London 08–13, overlap 13–16, NY 16–21 UTC.

### 1 — Canonical Triple Screen long (H4 analysis / M15 timing)
- **Setup:** Last closed H4 bar closed above a rising H4 EMA and made a higher high and higher low
  vs. the prior H4 (screen one = bullish). Price now pulls back on M15 into the H4 EMA region; the
  M15 oscillator has fallen to its lower reference band and the last closed M15 bar closed up.
- **Decision:** OPEN long on the close of that M15 bar. Stop below the M15 swing low that formed
  the pullback.
- **Invalidation:** M15 close below the pullback low; or the next H4 closes below the prior H4 low
  (screen one flips → flatten regardless of the M15 picture).
- **Why:** Screens one and two — strategic side from the higher chart, tactical entry against the
  minor wave. (`elder_trading_room pp.141–144`)
- **Evidence:** `moderate` (directional multi-timeframe filter)

### 2 — SKIP: timing signal opposes the analysis timeframe
- **Setup:** Same bullish H4 as example 1. M5 prints three strong bear bars into the London open
  and the M5 oscillator crosses down.
- **Decision:** SKIP the short. The signal is only usable to reduce or exit an existing long.
- **Invalidation:** n/a — this is a non-trade. The *rule* would be wrong if H4-aligned entries were
  shown to have no better outcome than H4-opposed ones over a large sample.
- **Why:** Screen two may take profits but may not initiate against screen one; and countertrend
  lower-timeframe legs against a trending higher timeframe tend to abort at exactly the point that
  is the good with-trend entry. (`elder_trading_room pp.143–144`; `grimes_art_science pp.232, 244`)
- **Evidence:** `moderate`

### 3 — WAIT: developing H4 bar, level "broken" but not closed
- **Setup:** 09:40 UTC. The 08–12 H4 bar is 40% elapsed. Price has traded 3 USD below a D1 support
  level; on M5 the last four bars closed below it. The developing H4 currently shows a body below
  support.
- **Decision:** WAIT. Do not record "H4 closed below D1 support". Permissible state: `developing_h4
  low < support`, `h4_close = pending`.
- **Invalidation of the wait:** the 12:00 UTC H4 close. If it closes below support → break
  confirmed; if it closes back above → the excursion was a failed probe and becomes evidence for
  the *opposite* side.
- **Why:** A forming bar's close does not exist; reversal bars routinely collapse in their final
  seconds, and a bar that looked like a decisive break for most of its life can close back inside.
  (`brooks_trends pp.199–202`; `elder_trading_room p.157`)
- **Evidence:** `strong` (structural — no lookahead is possible on an unclosed bar)

### 4 — Break hierarchy: M1 cannot break an M15 level
- **Setup:** M15 range high at 2412.0 has held three times. On M1, price prints 2412.4 and two M1
  bars close above 2412.0; the M15 bar containing them closes at 2411.2.
- **Decision:** SKIP the breakout long. Record a *failed probe* at the M15 level, which strengthens
  it. Consider the responsive short only if the higher-timeframe context is a bracket.
- **Invalidation:** an M15 *close* above 2412.0 followed by an M15 bar that holds above it.
- **Why:** the high of the prior bar on your chart is a swing high on a lower chart; a lower chart
  making a new high is by construction *not* a break of a higher chart's level. Dalton's version:
  a probe beyond a known reference that attracts no new activity returns the market to two-timeframe
  trade. (`brooks_ranges p.30`; `dalton_mind_over_markets pp.122–123`)
- **Evidence:** `strong` (definitional)

### 5 — H4 bracket, clean M15 trend between the edges
- **Setup:** The last 6 H4 bars overlap heavily between 2380 and 2402 — an H4 bracket. Price is at
  2381 at the London open, and M15 turns up with successive higher lows.
- **Decision:** OPEN long from the lower bracket area, target the middle-to-upper bracket area, and
  plan to exit near 2402. Do **not** promote the M15 uptrend to "H4 is now bullish".
- **Invalidation:** M15 acceptance below 2380 (two M15 closes below plus 30+ minutes spent there) →
  this is a candidate bracket→trend transition, exit and re-read.
- **Why:** trades in a bracket are placed responsively near the extremes and are poor in the
  middle; and some of the cleanest lower-timeframe trends occur inside higher-timeframe
  consolidation. (`dalton_mind_over_markets pp.158–159`; `grimes_art_science pp.241–242, 244`)
- **Evidence:** `moderate`

### 6 — Retracement depth as a higher-timeframe budget
- **Setup:** D1 rallied 2350 → 2410 (60 USD leg). Price pulls back into London and is now at 2381
  (48% of the leg). H1 shows a two-legged pullback and the last closed H1 closed up off the low.
- **Decision:** OPEN long. Entry zone was pre-defined as 2373–2390 (38–62% of the leg); invalidation
  below 2370 (~66%).
- **Invalidation:** H1 close below 2370. Past two-thirds, reclassify: the odds now favour a full
  retracement of the leg rather than a resumption, so the D1 "up" read is withdrawn, not defended.
- **Why:** Murphy's retracement bands set what depth the higher timeframe tolerates before its own
  trend classification changes. (`murphy_ta pp.94–95, 366`)
- **Evidence:** `moderate`

### 7 — FAILURE CASE: with-trend entry into higher-timeframe overextension
- **Setup:** H4 is in a strong uptrend and the last closed H4 is a large bull trend bar far above
  the H4 channel/upper band. On M15 a tight bull flag forms — textbook continuation.
- **Decision (what most systems do):** buy the M15 flag breakout. **What happens:** the breakout
  runs a few bars, then reverses hard and takes out the flag low and more.
- **Correct decision:** SKIP, or take it at reduced size with an exit at the first sign of failure.
- **Invalidation of the skip:** an H4 bar that closes back inside its band while holding the flag
  low — overextension resolved, setup becomes tradable again.
- **Why the books say it fails:** Grimes' explicit teaching — a lower-timeframe setup taken while
  the higher timeframe is drastically overextended has a materially higher probability of dramatic
  failure and reversal; the correct responses are skip / tighter risk / quick exit, and the one
  unacceptable response is ignoring the higher timeframe's message. Brooks' version: a breakout
  above the top of an extended channel is usually climactic and unsustainable, and after such a
  failed breakout expect at least two legs down lasting at least ten bars.
  (`grimes_art_science pp.233, 237`; `brooks_trends pp.259–260`)
- **Evidence:** `moderate`

### 8 — Narrow initial balance at the London open
- **Setup:** Asia (00–07 UTC) produced a range of 4.5 USD against a 20-day average Asia range of
  9 USD — a narrow base. The 08:00–09:00 UTC hour extends the range 3 USD above the Asia high on
  rising participation.
- **Decision:** OPEN long with the range extension; stop back inside the Asia box.
- **Invalidation:** price returning inside the Asia box and spending time there — the extension was
  a probe, not other-timeframe entry.
- **Why:** the narrower the base, the easier it is to knock over, so a narrow initial balance raises
  the odds of range extension; and range extension beyond the initial balance is by definition the
  footprint of the other-timeframe participant, not of local flow.
  (`dalton_mind_over_markets pp.31–33, 39`)
- **Evidence:** `moderate` (Dalton's mechanism is well-argued but the specific XAUUSD threshold is
  `untested` and must be calibrated)

### 9 — Timeframe transition: two-timeframe → one-timeframe
- **Setup:** Price has rotated for five H1 bars around a prior-day value area. In the 13:00–16:00
  UTC overlap, price closes three consecutive M15 bars above the prior-day high, then spends 45
  minutes building value above it rather than falling straight back.
- **Decision:** OPEN long *and* upgrade the analysis timeframe read from "H1 bracket" to "H1
  trending up"; switch strategy from responsive (fade edges) to initiative (buy pullbacks, hold).
- **Invalidation:** price re-entering and being accepted back inside the prior-day range → the
  transition failed; revert to bracket rules immediately.
- **Why:** Dalton's category-3 transition — a break through a known reference *that is accepted*
  produces a trend; and the strategy itself must change as the market moves between bracket and
  trend. Time provides the signal, structure confirms.
  (`dalton_mind_over_markets pp.71, 122–123`)
- **Evidence:** `moderate`

### 10 — Failed transition: one-timeframe → two-timeframe (probe rejected)
- **Setup:** NY session. Price extends 4 USD above the London high on one fast M5 impulse, then the
  next three M15 bars all close back inside the London range.
- **Decision:** SKIP long continuation; if already long from below, exit. Optionally fade back
  toward the range middle.
- **Invalidation:** a subsequent M15 close above the extension high with time spent there.
- **Why:** a price probe beyond a known reference point that does not attract new activity causes
  the market to return to two-timeframe (rotational) trade — the definition of Dalton's category-2
  transition. (`dalton_mind_over_markets pp.122–123`)
- **Evidence:** `moderate`

### 11 — Fractal composition read on a large H4 bar
- **Setup:** The 08–12 UTC H4 bar closed as a large bull bar with open near the low and close near
  the high, range 2.1× the 20-bar average H4 range.
- **Decision:** Treat the *content* of that bar as an M15/M5 trend, not a range: expect that inside
  it, pullbacks were shallow and one-directional. Consequence: pullback entries on the next H4 are
  more likely to be shallow (single-bar) rather than complex, so a pullback entry must be planned
  as "buy the first shallow M15 pullback", not "wait for a deep two-legged one".
- **Invalidation:** the next H4 bar overlapping the prior one heavily and closing mid-range —
  content has become rotational, revert to expecting complex pullbacks.
- **Why:** large bars relative to recent bars most likely contain lower-timeframe trends,
  especially when open and close are near opposite ends; small mid-closing bars contain ranges.
  Also, one- or two-bar pullbacks on the higher chart are complete complex pullbacks on the lower
  chart. (`grimes_art_science pp.40–41`)
- **Evidence:** `strong` for the composition claim (a bar *is* its constituents); `moderate` for the
  forward inference about the next bar's pullback depth

### 12 — WAIT: the analysis timeframe has not closed and the conflict is unresolved
- **Setup:** 23:30 UTC. The 20–24 UTC H4 is 87% elapsed. D1 read is bearish (last closed D1 made a
  lower low and closed near the low). M5 has run 5 USD higher in 25 minutes on thin liquidity.
- **Decision:** WAIT. No entry either way.
- **Invalidation of the wait:** the 00:00 UTC H4/D1 close. If the D1 closes strongly against the
  bearish read, re-derive the read from that closed bar.
- **Why:** two independent reasons. (a) A fast lower-timeframe move in the tail of a higher-timeframe
  bar is precisely the trap Brooks describes — the shape at 87% elapsed is not the shape at the
  close. (b) Elder's whole point about conflicting timeframes: the answer is to step *back*, not to
  get closer to the market. (`brooks_trends pp.199–202`; `elder_trading_room pp.139–140`)
- **Evidence:** `strong` (the unclosed-bar half); `moderate` (the conflict-resolution half)

### 13 — Carter-style intraday alignment stack
- **Setup:** Trading M15. The two next-higher charts in the stack (H1 and H4) both show the same
  directional signal (momentum/trigger on the buy side); M15 itself now fires long.
- **Decision:** OPEN long on the close of the M15 signal bar.
- **Invalidation:** either higher chart flipping on its own close, or the M15 stop.
- **Why:** Carter's multi-timeframe analysis rule set — trade only when the timeframe you trade and
  the next two higher timeframes agree, on 24-hour charts so overnight activity is included.
  (`carter_mastering pp.402, 410–411`)
- **Evidence:** `moderate` at best. Note the cost the books do not price: requiring three
  timeframes to agree cuts sample size sharply and concentrates entries in the late-middle of moves.
  Treat the "next *two*" specifically as `weak` — it is one author's parameter with no test.

### 14 — Correction without retracement (Dalton's counterexample to rule 12)
- **Setup:** D1 rallied hard. The following two H4 bars overlap the top of the impulse, hold their
  value, and close near their highs; the pullback never reaches even the 33% band.
- **Decision:** Do **not** wait for the 38–62% zone. Treat sideways-holding-value as the correction
  and take a with-trend entry on an M15 pullback within the H4 range.
- **Invalidation:** H4 closing below the impulse bar's midpoint — value is failing, not holding.
- **Why:** correction means counteraction, not necessarily lower prices; if a correction occurs and
  the market still establishes higher value, the underlying condition is strong. This directly
  qualifies Murphy's retracement expectation. (`dalton_mind_over_markets pp.170–171`;
  contrast `murphy_ta pp.94–95`)
- **Evidence:** `moderate`

---

## Learning outcome

After this topic the model must, for any decision, (1) name its analysis timeframe and its timing
timeframe from the ladder with a ratio between 3 and 6, and refuse to decide if it cannot; (2)
compute and report the higher-timeframe read from *closed* higher-timeframe bars only, and mark
every quantity derived from a still-forming higher-timeframe bar as `developing_*`, never using a
developing bar's implied close, body or colour; (3) refuse to open a position against its stated
analysis timeframe on a timing-timeframe signal, and refuse to revise its analysis-timeframe read
on the basis of lower-timeframe momentum, emitting `wait` or `stand_aside` instead; and (4)
distinguish "the higher timeframe is trending" from "the higher timeframe is bracketing" and switch
between with-trend continuation logic and responsive edge-fading logic accordingly, promoting a
lower-timeframe break to a higher-timeframe thesis change only after acceptance (closes plus time)
beyond a named reference.

---

## Implementation

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `tf_pair` | `{analysis, timing}` chosen from `D1→H4→H1→M15→M5→M1`; assert ratio ∈ [3,6] | meta | Reject M15/M1 (15:1) and H1/M30 (2:1). M30 only pairs with H4 or D1. |
| `htf_bias` | On the **last closed** analysis bar: sign of (close − EMA) AND sign of EMA slope over last N bars; `flat` if they disagree | analysis TF | `flat` must route to `stand_aside`, not to a lower timeframe. |
| `htf_structure` | `trend` if last 3 closed analysis bars make higher highs+higher lows (or lower/lower); `bracket` if ≥4 of last 6 bars overlap ≥60% with the composite range | analysis TF | Drives which rule set applies (continuation vs. responsive). |
| `developing_high/low/range` | max/min/extent over all **closed** timing bars since the analysis bar's open, unioned with the analysis bar's open | timing TF → analysis bar | Safe: composed only of closed bars. Must be named `developing_*`. |
| `developing_elapsed_pct` | (now − analysis_bar_open_time) / analysis_bar_duration | session clock | Use as a caution multiplier: block new entries when >80% elapsed and the timing move opposes `htf_bias`. |
| `htf_close` | Only defined at the analysis bar boundary | analysis TF | Before that, value is `pending`. Any rule referencing it must return `pending`. |
| `bar_composition` | count and OHLC of timing bars inside each analysis bar (H4: 4×H1 / 16×M15 / 48×M5 / 240×M1) | both | Definitional; use for "was the content trending or rotational" (body/range ratio, directional-bar fraction). |
| `content_character` | analysis bar range ÷ 20-bar mean range; |body| ÷ range; open/close position in range | analysis TF | Large + open/close at opposite ends ⇒ contained a trend; small + mid-range open/close ⇒ contained a range (`grimes_art_science pp.40–41`). |
| `level_break_confirmed` | close of a bar **on the timeframe that defined the level** beyond the level | level's own TF | Never confirm a level break from a lower timeframe. |
| `acceptance` | ≥N consecutive timing closes beyond the reference AND ≥T minutes elapsed beyond it | timing TF + clock | N and T must be fit per session; Dalton gives the concept, not the numbers. Start N=2 (M15), T=30min. |
| `retracement_pct` | (extreme − current) ÷ (extreme − leg_origin) on the analysis TF's most recent completed leg | analysis TF | Bands: 33–38 min, 50 typical, 62–66 max (`murphy_ta pp.94–95`). |
| `retracement_regime` | `pullback` if ≤66%, `reversal_risk` if >66% | analysis TF | At >66%, withdraw the directional read rather than defending it. |
| `initial_balance` | high/low of Asia window 00:00–07:00 UTC; and separately first 60 min of London (08:00–09:00) | M5/M15 aggregated | Two IBs because XAUUSD is 24h: the classic "first hour" analogue is the London open, not 00:00. |
| `ib_width_ratio` | IB range ÷ 20-day mean IB range for that window | daily | <0.7 ⇒ narrow base, raise range-extension prior; >1.3 ⇒ wide base, raise "extremes hold" prior. Thresholds are `untested` for XAUUSD — calibrate. |
| `range_extension` | signed distance traded beyond the IB, and which session period it occurred in | M5 + clock | Dalton's marker of other-timeframe participation. |
| `session_id` | Asia 00–07, London 08–13, Overlap 13–16, NY 16–21 UTC | clock | Needed for volatility normalisation (`lien_fx_sessions pp.83–88`). |
| `vol_scale` | expected range for timing TF = analysis TF ATR × √(timing/analysis duration ratio) | both | Grimes' √ratio rule (`p.29`). This is the volatility-cascade channel — the empirically supported one. |
| `stop_distance` | ATR of the *timing* TF × k, floored by `vol_scale` | timing TF | Never port a stop distance across timeframes unchanged. |
| `conflict_flag` | `htf_bias` and timing-TF direction disagree | both | Routes to `wait` unless `acceptance` is true. |
| `dominant_tf` | the timeframe whose most recent structural reference price is currently reacting to | derived | Heuristic only; log it so it can be audited. Grimes gives no formula. |
| **⚠ H4/D1 bar anchoring** | broker server timezone determines where H4 and D1 bars start | — | **Flag:** "H4 close" is a chart convention, not a market event. A 00-UTC-anchored H4 and a 17:00-NY-anchored D1 disagree about the same price history. Fix one convention and never mix. |
| **⚠ DST** | London/NY session boundaries in UTC shift twice a year | clock | Session windows in the brief are fixed UTC; real session behaviour shifts by an hour. Flag as a known approximation. |
| **⚠ Volume** | Market Profile / TPO concepts (Dalton) need volume-at-price | — | Spot XAUUSD gives tick volume, not traded volume. TPO-style value areas are approximable from M5 time-at-price but are **not** Dalton's volume profile. Do not claim otherwise. |
| **⚠ Oscillator continuity** | Elder's MACD-Histogram / Force Index on intraday bars | — | Elder himself warns that gaps between trading days distort intraday indicators (`p.156`); XAUUSD's weekend gap and daily rollover break indicator continuity on H4/D1. |

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Elder:** for a day trader the weekly trend is essentially meaningless and even the daily is of limited value; use two, at most three timeframes, because looking at more causes "paralysis from analysis" (`elder_trading_room pp.97, 157`). | **Carter:** drill down monthly → weekly → daily → 60m → 15m → 5m; and require the traded timeframe *plus the next two higher* to agree before entering (`carter_mastering pp.410, 502`). **Murphy:** analysis must *begin* with monthly and weekly charts (`murphy_ta p.368`). | Adopt Elder's cap of **three** timeframes, fixed in advance and logged. Use D1 only as a coarse regime/volatility input (ATR, prior-day levels), never as a third directional vote. Carter's "next two higher must agree" is a `weak` parameter and is not implemented as a hard gate; if tested at all, test it as an optional size multiplier, since it demonstrably shrinks the sample. |
| **Elder / Murphy / Carter:** the higher timeframe is authoritative — establish the longer trend first, then trade the shorter one only in that direction (`elder_trading_room p.140`; `murphy_ta p.332`; `carter_mastering p.216`). | **Grimes:** explicitly rejects the assumption that higher timeframes are always more important; control passes between timeframes and identifying *which* timeframe is dominant is the analytical task; furthermore some of the best, cleanest trends occur *inside* higher-timeframe ranges (`grimes_art_science pp.231–232, 241–242, 244`). | Grimes wins, because his position is the one compatible with the empirical picture (no validated directional cascade). Implement `htf_structure` first: if the analysis timeframe is **trending**, use the Elder filter (rules 4, 11). If it is **bracketing**, explicitly suspend the directional filter and switch to responsive edge logic (rule 10). Never run a directional HTF filter unconditionally. |
| **Elder / Carter:** multi-timeframe analysis is the core edge; adding the time dimension gives an advantage over traders who look at one chart (`elder_trading_room p.97`). | **Brooks:** trades essentially one chart; says he cannot process multiple timeframes and indicators in the time available and finds careful single-chart reading more profitable; and warns that pundits who claim to combine timeframes are really price-action traders retro-fitting confirmation (`brooks_ranges p.20`). He also notes that if you look at *all possible* higher timeframes you can always find one that makes your setup look perfect (`brooks_trends pp.135, 272`). | Brooks' selection-bias point is logically decisive and is enforced as rules 16 and 17: the timeframe pair is declared **before** the read, and no additional timeframe may be consulted afterwards. Brooks' preference for one chart is not adopted (the bot has no latency constraint), but his objection is what makes the constraint non-negotiable. |
| **Murphy:** intermediate corrections retrace roughly one-third to two-thirds, most often about half, of the prior move; beyond two-thirds expect a full retracement (`murphy_ta pp.43, 94–95`). | **Dalton:** a correction is *counteraction*, not necessarily lower prices — an up auction can correct sideways or even with higher closes while old longs liquidate into new initiative buying, and if value still builds higher the market is strong (`dalton_mind_over_markets pp.170–171`). | Use Murphy's bands as the **risk boundary** (beyond 66% the directional read is withdrawn) and Dalton's rule as the **entry trigger** (do not *require* a 38% pullback before acting). Concretely: entry may occur on any with-trend timing setup once the analysis-timeframe momentum has reset, whether or not price retraced; invalidation is still keyed to the 66% level. Example 14 encodes this. |
| **Murphy / Elder:** the market's default state worth trading is a trend; the higher timeframe's job is to tell you which trend to follow. | **Dalton:** markets bracket roughly 70–80% of the time, and trend-following systems get repeatedly triggered and stalled inside brackets; strategy must change dramatically between the two regimes (`dalton_mind_over_markets p.71`). | Treat "trending" as the *exception* the bot must prove, not the default it assumes. `htf_structure` must return `bracket` unless the trend test passes. This inverts the burden of proof relative to Elder/Murphy and is the single most consequential resolution in this file. |
| **Murphy:** long-term charts are for forecasting and are explicitly *not* suitable for timing entries and exits (`murphy_ta pp.182–183`). | **Elder's screen three:** entry orders can be placed off the higher-timeframe structure itself (e.g. buy a tick above the previous *day's* high when the weekly is up and the daily is down) (`elder_trading_room p.146`). | No real conflict once "timing" is defined precisely: Elder's order is *derived from* a higher-timeframe reference but *triggered by* lower-timeframe price. Implement all triggers on the timing timeframe; higher-timeframe levels may only supply the price, never the moment. |

---

## Gaps

Things this topic needs that no book in the corpus supplies:

1. **Any statistical estimate of directional cross-timeframe edge for XAUUSD.** Every author asserts
   the filter works; none reports a hit-rate, an expectancy differential between HTF-aligned and
   HTF-opposed entries, or a sample size. Chan is the only quantitative voice and his cross-horizon
   correlations are small and mostly insignificant (`chan_algo_trading pp.153–155`) — and he is
   measuring bond futures, not gold. **This must be measured before rule 4 is trusted.**
2. **Threshold values.** "Narrow" initial balance, "acceptance" (how many closes, how many minutes),
   "clearly trending", "far outside the band" — every one of these is qualitative in the books.
   Dalton's one number (a bracket extreme is tested 3–5 times on average, `p.159`) is an unsourced
   assertion. All thresholds in the Implementation table are placeholders.
3. **24-hour instrument mapping.** Every author writes for a session-based market with an opening
   bell. Dalton's initial balance, Elder's opening-range breakout, Murphy's intraday pivot time
   windows and Carter's 390-minute-session charts all presuppose a daily open. XAUUSD trades
   ~23h/day across three overlapping sessions. Nothing in the corpus tells you which of Asia open,
   London open or NY open is the "real" initial balance for gold, or whether there are three of
   them.
4. **The bar-anchoring problem.** No book acknowledges that "the H4 closed below support" depends
   entirely on where the broker starts its H4 bars. Since a large part of this topic is built on
   higher-timeframe closes, and the corpus treats those closes as market facts rather than charting
   conventions, this is a real hole. Related: no guidance on whether to prefer non-standard
   anchoring (Elder's 25-minute-chart argument for using uncommon parameters, `p.156`, is
   suggestive but is asserted, not tested).
5. **Weekend and rollover discontinuity.** XAUUSD's weekend gap sits inside every weekly-scale
   analysis and breaks EMA/MACD continuity on H4 and D1. Elder notes gaps distort intraday
   indicators (`p.156`) but offers no handling.
6. **How to weight conflicting timeframes when both are strong.** Grimes says identify the dominant
   timeframe but gives no procedure — he explicitly calls it a blend of art and science
   (`grimes_art_science p.243`). The bot needs a decision rule and the corpus does not contain one;
   the current fallback (`wait`) is a safe default, not an answer.
7. **Volatility-conditional sizing.** The corpus gives the √ratio scaling rule (Grimes) and session
   range tables (Lien) but never joins them into a rule for sizing an XAUUSD position from
   higher-timeframe volatility state. Since volatility is the channel that *is* empirically
   supported, this is the highest-value gap to close.
8. **Regime-change detection latency.** Dalton's timeframe transition is the corpus's best answer,
   but it is described post-hoc from completed profiles. Nothing quantifies how long after a real
   bracket→trend transition the acceptance test fires, or how often it fires falsely.

---

## JSONL seeds

```json
{"principle_id":"tf_001_declare_the_pair","topic":"timeframe_relations","lesson":"Every decision names one analysis timeframe and one timing timeframe from D1/H4/H1/M15/M5/M1, related by a factor of 3 to 6; the higher chart decides side or no-side, the lower chart decides the moment.","practice":"Before any read, emit {analysis_tf, timing_tf}; assert the ratio is in [3,6]; refuse to produce a decision if the pair is missing.","guardrail":"Never consult a timeframe that was not declared before the read, and never add a timeframe while a position is open.","evidence_label":"moderate"}
{"principle_id":"tf_002_closed_bars_only","topic":"timeframe_relations","lesson":"A higher-timeframe bar's close, body, colour and 'did it close beyond the level' do not exist until that bar closes; only its open, high-so-far, low-so-far and range-so-far are computable, because those are built from closed lower-timeframe bars.","practice":"Expose developing_high, developing_low, developing_range and developing_elapsed_pct from closed M15/M5 bars; return 'pending' for any rule keyed to the higher-timeframe close.","guardrail":"Never infer, extrapolate or assume a forming bar's close; a bar that looks decisive at 87% elapsed routinely closes the other way.","evidence_label":"strong"}
{"principle_id":"tf_003_no_upward_inference","topic":"timeframe_relations","lesson":"Lower-timeframe momentum is not evidence about higher-timeframe direction; 48 M5 bars fit inside one H4, so multi-bar bursts in both directions occur inside H4 bars of either colour.","practice":"Derive htf_bias solely from closed analysis-timeframe bars; treat timing-timeframe momentum as an entry-timing input only.","guardrail":"Never revise the analysis-timeframe read because of an M1/M5 move; if they conflict, emit wait.","evidence_label":"moderate"}
{"principle_id":"tf_004_break_hierarchy","topic":"timeframe_relations","lesson":"A level is broken only when a bar closes beyond it on the timeframe that defined the level; a lower timeframe trading through it is a probe, and a rejected probe strengthens the level.","practice":"Tag every level with the timeframe that defined it and confirm breaks only from that timeframe's closes; record rejected probes as evidence for the opposite side.","guardrail":"Never let M1 or M5 action mark an M15, H1, H4 or D1 level as broken.","evidence_label":"strong"}
{"principle_id":"tf_005_structure_before_filter","topic":"timeframe_relations","lesson":"Classify the analysis timeframe as trending or bracketing before applying any directional filter; markets bracket most of the time, and inside a higher-timeframe bracket the lower timeframe produces clean trends that stop at the bracket edges.","practice":"Compute htf_structure first; if trend, use with-trend continuation logic; if bracket, suspend the directional filter and trade responsively toward the middle from the edges.","guardrail":"Never run a permanent higher-timeframe trend filter; trending is the exception the bot must prove, not the default.","evidence_label":"moderate"}
{"principle_id":"tf_006_acceptance_not_penetration","topic":"timeframe_relations","lesson":"Promote a lower-timeframe break into a higher-timeframe thesis change only after acceptance: consecutive closes beyond a named reference plus time spent there. Time gives the signal, structure confirms.","practice":"Require N consecutive timing-timeframe closes beyond the reference and T minutes elapsed before flipping htf_structure or htf_bias; log the reference that was accepted.","guardrail":"A single fast excursion beyond a reference that returns inside is a failed probe and must flip the read toward the opposite side, not toward the breakout side.","evidence_label":"moderate"}
{"principle_id":"tf_007_retracement_budget","topic":"timeframe_relations","lesson":"The higher timeframe sets how deep a pullback may go before the read changes: 38-62 percent is the working entry zone, and beyond about 66 percent the classification moves from pullback to possible reversal.","practice":"Compute retracement_pct against the analysis timeframe's most recent completed leg; place entries in the 38-62 band and invalidation beyond 66; withdraw the directional read past 66 rather than defending it.","guardrail":"Do not require a price retracement before entering: a sideways higher-timeframe correction that holds value is a valid reset, so absence of retracement is not absence of correction.","evidence_label":"moderate"}
{"principle_id":"tf_008_lower_never_reverses_higher","topic":"timeframe_relations","lesson":"A timing-timeframe signal against the analysis timeframe may reduce or close a position but may never open one; countertrend lower-timeframe legs against a trending higher timeframe tend to abort where the with-trend entry is best.","practice":"Route counter-signals to exit/scale-out logic only; when the analysis timeframe is flat or ambiguous, emit stand_aside rather than seeking a signal on a faster chart.","guardrail":"Standing aside is a valid output; never resolve an ambiguous higher timeframe by dropping to a lower one.","evidence_label":"moderate"}
{"principle_id":"tf_009_volatility_not_direction","topic":"timeframe_relations","lesson":"The higher timeframe reliably conditions how far price travels, not which way it travels; vertical distances scale roughly with the square root of the timeframe ratio.","practice":"Derive stop distance, target distance and position size from analysis-timeframe volatility scaled by sqrt(duration ratio) and by session; derive direction only from the structural read, and label it moderate confidence.","guardrail":"Never present a multi-timeframe directional alignment as high-confidence evidence; the volatility cascade is supported, the directional cascade is not.","evidence_label":"strong"}
{"principle_id":"tf_010_no_timeframe_shopping","topic":"timeframe_relations","lesson":"Given enough candidate higher timeframes, one can always be found that endorses any setup, so an unconstrained higher-timeframe check is a bias generator rather than a filter.","practice":"Fix at most three timeframes in advance for a given strategy and log them with every decision, so that post-hoc timeframe selection is detectable in review.","guardrail":"Wanting to look at an unusual timeframe while holding a losing position is a discipline failure signal; block it rather than acting on it.","evidence_label":"strong"}
```
