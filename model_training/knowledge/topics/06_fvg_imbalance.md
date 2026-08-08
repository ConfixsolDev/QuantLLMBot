# Topic 6 — Fair Value Gap / Imbalance, and the Gap Literature That Precedes It

> **Sources read:** `nison_candlesticks` p.135–147; `nison_beyond` p.102–112, 227;
> `murphy_ta` p.102–105; `brooks_ranges` p.30, 33, 38, 44, 52, 54, 59–64, 76–77;
> `brooks_trends` p.21, 59–60, 364; `brooks_reversals` p.342, 376, 384, 427–433;
> `dalton_mind_over_markets` p.45–47, 131–132, 176–178, 252–253;
> `dalton_markets_in_profile` p.104–107, 145–147, 165; `dalton_markets_momentum` p.127–129,
> 167–170, 248; `carter_mastering` p.128–135; `chan_algo_trading` p.111–114, 174–175;
> `couling_volume` p.11, 26, 37–38, 121, 125–127, 135–136; `grimes_art_science` p.31, 61,
> 112, 124, 162, 267; `person_pivots` p.94–96
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1 in its entirety)
>
> **Companion file:** `05_ict_concepts.md`. That file maps the whole ICT vocabulary onto the
> literature and states the general rules for handling untestable practitioner terms. This
> file does not repeat that mapping; it does one row of it — *fair value gap* — in full
> depth, because the gap literature is deep enough to deserve its own topic. Where 05 gives
> a one-line verdict, this file gives the evidence. Read 05 first for the epistemics; read
> this one for the mechanics.

---

## Framing: what this topic actually is

The modern practitioner definition of a **fair value gap** is a three-candle formation in
which candle 1's extreme and candle 3's opposing extreme do not overlap:

- bullish: `low[i] > high[i-2]`
- bearish: `high[i] < low[i-2]`

leaving a band of price that lies inside candle 2's range but outside the ranges of candles
1 and 3. The associated claim is that price tends to return to that band ("fill it",
"mitigate it") and that the band is therefore a place to enter.

**Three facts frame everything below.**

**1. The term is not in the corpus.** A case-insensitive scan of all 18 corpus files for
`fair value gap` and `FVG` returns **zero hits**. There is no primary ICT text on disk and
no rigorous published test of the FVG construct in either direction, so every FVG-specific
claim in this file carries `untested` or `weak`, with a named tick-archive measurement
attached.

**2. The three-candle structure itself is in the corpus, twice, under other names, and
neither author uses it the way the FVG claim does.** Brooks defines it precisely: when a strong bull trend bar is followed by a bar whose low
sits at or above the high of the bar preceding the trend bar, the untouched span between
them counts as a gap. He calls it a **micro measuring gap**, a *sign of strength* used to
**project a target**, not a zone to buy (`brooks_trends` p.21, 59–60; `brooks_ranges`
p.61). Dalton's profile equivalent is the **single print** or thin area, which he treats as
an **auction ending** that should act as support or resistance (`dalton_mind_over_markets`
p.132). Brooks himself makes the bridge explicit: intraday measuring gaps, where the market
moves quickly, are the thin areas between two distributions on a Market Profile
(`brooks_ranges` p.76). So the ancestry is real and it is respectable. The *direction of
the inference* is what the FVG claim inverts: both ancestors say the band is where price
**does not want to go back to**, and the FVG claim says it is where price **must** go back
to.

**3. The classical gap literature explicitly rejects the blanket fill claim.** Murphy
states outright that "gaps are always filled" is a myth — some should fill and others
should not, and which is which depends on the type and location of the gap (`murphy_ta`
p.102). Brooks says the saying "only rarely helps traders" and offers a devastating near-
null: after a gap up in a bull trend, price is only *slightly* more likely to come back
below the high of the bar before the gap than below the high of **any other bar in the
rally** (`brooks_ranges` p.59–60). That is a statement that the gap, as a location, is
close to uninformative. Nison, the most gap-friendly author in the corpus, still declines
to endorse the fill claim: he says he does not know whether it is true (`nison_candlesticks`
p.136).

There is one more fact, and it is the most important one for this bot. It gets its own
section.

---

## Core concepts

| Concept | Definition (one line, my words) | Sources (slug p.N) | Evidence |
|---|---|---|---|
| **True price gap** | A price band where **no trade occurred at all**, because the market had no opportunity in time to trade there. | `murphy_ta` p.102; `dalton_markets_in_profile` p.105; `person_pivots` p.94; `nison_beyond` p.102 | **strong** (definitional; four independent authors give the same definition) |
| **Window (Japanese)** | The same object as a Western gap, defined strictly on **shadows**: a rising window requires the prior bar's high to sit *below* the current bar's low, with no overlap. | `nison_candlesticks` p.135–136; `nison_beyond` p.102 | **strong** (definitional) |
| **Window as support / resistance** | The whole window is a zone; the far edge (bottom of a rising window, top of a falling one) is the last-ditch line; a *close* through it voids the prior trend. | `nison_candlesticks` p.135, 138; `nison_beyond` p.103–104 | **moderate** |
| **"Corrections stop at the window"** | Japanese maxim: a pullback should terminate inside the window rather than pass through it. Nison's operational version: only a **close** through the window counts as a break; an intrasession poke does not. | `nison_beyond` p.103–104; `nison_candlesticks` p.135 | **moderate** |
| **Breakaway gap** | A gap that completes a base or top and starts a move; occurs on heavy volume; **more often than not it does not fill**, and the heavier the volume after it, the less likely a fill. | `murphy_ta` p.102–103; `person_pivots` p.95; `brooks_ranges` p.61 | **moderate** |
| **Runaway / measuring gap** | A gap around the midpoint of a move; also usually not filled; its midpoint projects the remaining extent by doubling the distance already travelled. | `murphy_ta` p.103–104; `person_pivots` p.95; `brooks_ranges` p.61, 76 | **moderate** |
| **Exhaustion gap** | A gap near the end of a move; the tell is a **close back through it**, which converts the read from continuation to reversal. | `murphy_ta` p.104; `brooks_ranges` p.61, 63; `person_pivots` p.95 | **moderate** |
| **Common gap** | A small gap in no structural location; insignificant; **this** is the one that reliably fills. | `person_pivots` p.94 | **weak** (one author) |
| **Micro measuring gap (Brooks)** | The three-bar non-overlap around a strong trend bar. A sign of strength; used to **project** a measured move from the leg start through the gap midpoint. | `brooks_trends` p.21, 59–60; `brooks_ranges` p.61 | **moderate** |
| **Gap as an invisible trend bar** | Brooks's unification: a gap and a large trend bar are the same behaviour recorded under different session conventions. A gap opening is just a spike. | `brooks_ranges` p.60, 63; `brooks_reversals` p.429 | **strong** (structural) |
| **Single print / thin area (Dalton)** | Prices at which the auction spent almost no time, typically separating two distributions on the same day. The profile-based analogue of a gap. | `dalton_mind_over_markets` p.45–47, 132; `dalton_markets_momentum` p.127 | **moderate** |
| **Gap as excess** | Dalton: a gap is an extreme form of excess — an "invisible tail". Excess marks the **end** of an auction and should thereafter act as support/resistance. | `dalton_mind_over_markets` p.132, 253; `dalton_markets_in_profile` p.105–106 | **moderate** |
| **Return into single prints = change** | If price auctions back into the single prints and converts them to double prints, the newer distribution is **no longer accepted as value** — a fill is a *regime signal*, not a normal event. | `dalton_mind_over_markets` p.46–47 | **moderate** |
| **Unfilled gap as a "tell"** | A countertrend rally that stalls just short of filling a gap is a specific, tradeable rejection signal. | `dalton_markets_in_profile` p.145; `dalton_mind_over_markets` p.253; `grimes_art_science` p.112 | **weak** |
| **Three-session rule** | Some Japanese traders hold that a window unfilled after three sessions confirms continuation in the window's direction. Nison reports it and then explicitly distrusts the number three. | `nison_beyond` p.109–111 | **weak** (author reports and hedges it) |
| **Three windows** | Traditional Japanese view: three windows in a row means an overextended market. Nison's own revision: the number does not matter — the trend holds until the **last** window is closed. | `nison_candlesticks` p.141; `nison_beyond` p.111 | **weak** |
| **Tasuki gap** | A two-bar continuation pattern built on a window. Nison's mature verdict: **not worth remembering** — the window is what matters, not the candle colours after it. | `nison_candlesticks` p.143–145 | **weak** (author retracts his own pattern) |
| **Gapping play (high/low price)** | A congestion of small bodies near a recent extreme, resolved by a window in the trend direction; voided by a close back through that window. | `nison_candlesticks` p.145–147 | **weak** |
| **Effort vs result at a gap** | Wyckoff's third law applied to gaps: a gap on high volume is a genuine move; a gap on low volume is an anomaly and probably a trap. | `couling_volume` p.11, 37–38, 121, 125–127 | **weak** (asserted, never tested; and Grimes p.124 says he could not substantiate volume claims at all) |
| **Order-flow imbalance (the real one)** | Bid/ask size asymmetry and signed order flow — the microstructure quantity that actually induces momentum. It is **not** a chart shape and the bot cannot see it. | `chan_algo_trading` p.174; `grimes_art_science` p.31, 61, 162 | **strong** (mechanism) / **unavailable** (data) |
| **Fair value gap (FVG)** | Three-bar non-overlap treated as a zone price must return to. | *absent from corpus* | **untested** |

---

## The XAUUSD problem — read this before anything else

**On continuously traded spot gold, a three-candle FVG is not a gap in the classical sense
at all. Trade *did* occur inside that band, on lower timeframes. The corpus is unanimous
on why this matters, and five independent authors say it.**

**1. A gap is defined by the *absence of trade*, not by a shape on a chart.** Murphy: price
gaps are areas where no trading has taken place (`murphy_ta` p.102). Dalton: a gap is
created when the market does not have the **opportunity — time —** to trade at certain
prices (`dalton_markets_in_profile` p.105). Person: an area left blank when the market
trades from one period to another beyond the previous period's range (`person_pivots`
p.94). Nison: a window requires the *shadows* not to overlap, and no matter how large the
space between the real bodies, **it is not a window unless the shadows are separated**
(`nison_candlesticks` p.136). By all four definitions, an M15 FVG on XAUUSD fails: the
middle bar traded continuously through that band, and an M1 chart of the same three bars
shows filled candles across it.

**2. Gaps of this kind essentially do not exist intraday on liquid instruments.** Nison,
writing about intraday charts, says windows are mostly formed between the last candle of
one day and the first of the next, because it is *unusual* for a 5-minute bar to gap from
its immediate predecessor (`nison_candlesticks` p.138). Brooks says the same in stronger
terms: on an intraday chart of anything genuinely liquid, a bar whose low clears the prior
bar's high is **rare** outside the session's first bar
(`brooks_ranges` p.60). Coulling gives the mechanism: with 24-hour electronic trading, the
open of one bar simply follows the close of the previous one, "until the market closes for
the weekend"; gap price action that was once the norm is now rare and largely confined to
equities (`couling_volume` p.26). Carter is blunt: on a 24-hour chart, traders **will not
see the gaps at all** — you must build a special session-restricted chart to see them
(`carter_mastering` p.128).

**3. A gap is therefore partly an artifact of sampling and liquidity, not a pure market
fact.** Brooks states this outright: if the volume were thin enough, there would be actual
gaps on every intraday chart wherever there is a series of trend bars — a gap and a trend
bar represent the same behaviour (`brooks_ranges` p.60, 63). Dalton makes the same point
from the profile side: his long-term profile records single prints in a gap region only
because it *assumes* some trade took place there, and he notes that one of his gaps was
"less evident" on the profile precisely because the market had actually traded in that
region days earlier (`dalton_mind_over_markets` p.176). He also warns that gap tells are
best read on **pit-session** bars, because the electronic contract ticks a tick or two
either side and erases them (`dalton_markets_in_profile` p.145).

**What this implies for the bot — five consequences.**

- **(a) The classical gap results do not transfer to the FVG.** Murphy's "breakaway gaps
  usually don't fill", Nison's "corrections stop at the window", Carter's fill percentages
  and Dalton's excess reading were all derived from **true no-trade gaps**. Applying them to
  a three-bar non-overlap on XAUUSD is an unlicensed extension. Any FVG rule inherits
  `untested`, not the ancestor's label.
- **(b) The only true gaps on XAUUSD are weekend gaps.** Gold closes roughly 21:00–22:00
  UTC Friday and reopens roughly 22:00 UTC Sunday. Chan names exactly this: most currency
  markets are closed from Friday 17:00 ET to Sunday 17:00 ET, "so that's a natural 'gap'"
  (`chan_algo_trading` p.175). Everything else on gold is a fast-trade band, not a gap.
  Occasionally a large scheduled release produces a near-gap on M1 with a handful of ticks
  inside — treat that as a thin area, not a gap.
- **(c) The right corpus analogue for an intraday FVG is Dalton's single print, not
  Murphy's gap.** A single print is precisely "trade occurred, but almost none". That is
  what an FVG on XAUUSD actually is. Use the single-print rules
  (`dalton_mind_over_markets` p.45–47, 132; `dalton_markets_momentum` p.127) and not the
  gap rules.
- **(d) An FVG's meaning is timeframe-relative and therefore has to be justified, not
  assumed.** The same band is a gap on M15 and a normal filled range on M1. Brooks's
  reduction — every trend bar is a gap under a broad enough definition (`brooks_ranges`
  p.60, 63) — means an M5 FVG carries no more information than "there was a strong M5 trend
  bar here". If the bot would not act on the trend bar, it must not act on the gap.
- **(e) The bot must never claim "no trade occurred" in narrative about an intraday FVG.**
  That statement is false on XAUUSD and it is the entire load-bearing premise of the retail
  FVG story.

---

## Does a gap actually get filled? What the corpus knows

This is the empirical heart of the topic. Ranked from most to least rigorous.

**1. Chan — the only backtests in the corpus, and they point in opposite directions by
instrument class.**
- *Stocks, mean reversion.* Buy stocks that gapped down more than 1 SD from the prior day's
  low **and** whose open is above the 20-day MA; exit at the close. Rule 2 is a momentum
  filter, and Chan explains why it matters: stocks that dropped "just a little" revert
  better than those that dropped "a lot", because large drops are news-driven and news-
  driven moves are less likely to revert (`chan_algo_trading` p.111). The mirror short-on-
  gap version returned 46% APR / 1.27 Sharpe over the same window (p.113). Chan notes his
  own live version *without* rule 2 suffered diminishing returns from 2009 (p.113).
- *Futures and currencies, momentum.* The **opposite** strategy — buy the gap up, short the
  gap down — "will sometimes work on futures and currencies". Best on Dow Jones STOXX 50
  futures: 13% APR, 1.4 Sharpe, 2004-07-16 to 2012-05-17. And on **GBPUSD**, defining close
  as 17:00 ET and open as 05:00 ET (London open): **7.2% APR, 1.3 Sharpe, 2007-07-23 to
  2012-02-20** (`chan_algo_trading` p.174–175). Mechanism: the extended no-trade period
  makes the open differ from the close, so stop orders at many prices trigger at once and
  cascade (p.175).
- **This is the single most decision-relevant result in the topic.** XAUUSD is a
  24-hour, currency-like, single-instrument market. On the closest tested analogue in the
  corpus, the weekend/session gap is a **momentum** signal, not a fade. Label **moderate** —
  it is one author, two instruments, one in-sample period, and gold is not GBPUSD.

**2. Carter — the most detailed fill statistics, but self-collected and for index
futures.** He fades opening gaps on multi-item markets (ES, YM, SPY, DIA) and conditions
the entire trade on premarket volume in a basket of large-cap names measured at 09:20 ET:
under 30k shares each → roughly **85%** chance of same-day fill; around 50k → roughly
**60%** fill, but the gap **midpoint** still gets hit about 85% of the time; over 70k →
about **30%**, a professional breakaway gap, and he stands aside (`carter_mastering`
p.129). Raw fill rates by weekday show **Monday lowest**, because most breakaway gaps occur
on Mondays; he passes on Mondays entirely, and on monthly expiration Friday and the first
trading day of the month, where fill rates run 55–60% (p.130). He requires a **minimum gap
size** — 10 YM or 1 ES point — and passes below it (p.130). Crucially, he separates
markets: **single-item markets (bonds, currencies, grains, individual stocks) fill "at some
point, but not necessarily the same day" and make poor candidates**; multi-item indices
fill well, partly because their components disagree with each other and partly as a self-
fulfilling convention among fund managers who dislike messy charts (p.128). **XAUUSD is a
single-item market by his own taxonomy.** Label **weak**: one author, no published
methodology, index futures, 2005–2011 era.

**3. Brooks — the near-null, stated as a probability.** After a gap up in a bull trend,
when the correction finally comes, price is only *slightly* more likely to trade below the
high of the bar before the gap than below the high of any other bar in the rally
(`brooks_ranges` p.60). His preferred restatement of the folk saying is **"all prior prices
get tested"** — which is true, but says nothing special about gaps (p.59–60). What survives
is a weaker and more honest claim: gaps are **magnets**, and the closer price gets to a
magnet the more likely it reaches it, so the gap is worth watching as a *target management*
object, not as a signal (p.60). Separately: after a large gap opening, the odds that price
travels a full average daily range in the gap's direction **before** closing the gap are
"probably 60 percent or better" (`brooks_reversals` p.432–433), and a large gap up is
roughly 50% bull channel / 20% trading range / 30% bear trend (p.428). Label **moderate**
for the magnet framing, **weak** for the specific percentages (author-reported guidelines,
Emini, and he says outright that computer testing has too many free variables, p.428).

**4. Murphy and Person — classification determines fill expectation.** Breakaway gaps: more
often than not **not** filled, and the heavier the volume after the gap the *less* likely a
fill (`murphy_ta` p.102–103). Runaway gaps: also often not filled, and a close back below
one in an uptrend is a negative sign (p.103). Exhaustion gaps: the close back through the
gap is the giveaway, i.e. these *do* fill and the fill is the signal (p.104). Person adds
the fourth class: **common** gaps, small and structurally meaningless, are the ones that
routinely fill (`person_pivots` p.94), and gaps in illiquid markets should simply be
ignored (p.94). Label **moderate** — two independent authors, consistent, untested.

**5. Nison — a window is expected to hold, not to fill.** A rising window is support, a
falling window is resistance; the correction is supposed to *stop* there
(`nison_candlesticks` p.135; `nison_beyond` p.103). He says explicitly that he does not
know whether the Western "all gaps fill" belief is true, and only uses it operationally: an
attempt to fill is a place to look for an entry **in the window's direction**
(`nison_candlesticks` p.136). Label **moderate**.

**6. Grimes — an unfilled gap is diagnostic of trend strength.** He lists "are there gaps up
that do not fill on a daily chart?" as a check on how easily a market is going up, alongside
the intraday version: are price levels being skipped because large orders clear many levels
in the book (`grimes_art_science` p.112)? He also notes that gaps beyond clean levels "tend
to be opening gaps that do not reverse" (p.124) — while elsewhere observing that most
equity gaps *are* reversed (p.267). Both are true because they are conditioned on different
things; see Contradictions. Label **weak** individually, **moderate** as a conditioning
principle.

**Synthesis.** Nobody in the corpus supports an unconditional fill claim, everybody
supports a **conditional** one, and the conditions that recur across independent authors
are: **size** (Carter, Person), **volume/effort** (Murphy, Carter, Coulling, Chan's rule 2),
**location in the move** (Murphy, Person, Brooks), and **instrument class** (Carter, Chan).
Those four are the design of the bot's gap classifier.

**Does an unfilled gap mean strength?** Yes, on a weak-to-moderate basis, and this is the
most consistent cross-author statement in the topic. Murphy (heavier post-gap volume →
less likely to fill → stronger, p.103), Brooks (three-bar gaps often get tested but not
filled, "evidence that the buyers are strong", p.61; and an unfilled gap on a retest is "a
sign that the bears were strong", p.64), Grimes (p.112), Dalton (the gold example below,
`dalton_mind_over_markets` p.253), Nison's reported three-session rule (`nison_beyond`
p.109). **Label: moderate.** Note carefully that this is the *opposite* trade to the FVG
entry: it says do not wait for the fill, trade with the trend.

**The gold worked example the corpus actually contains.** Dalton, on gold around 23 November
2012: a gap extending up to 1761.3 was left behind; the 23 November high of 1754.7 failed to
fill it; long-term sellers stayed in control and the unfilled gap defined the top of the
trading range, with opportunistic sellers working against short-covering momentum buyers.
An inside day followed the failed fill attempt, and the plan was to go with the downside
break of that balance (`dalton_mind_over_markets` p.252–253). This is the only gold-specific
gap analysis in the corpus and it is a **failed-fill continuation**, not a fill.

---

## Distilled rules

All computable from closed bars plus a UTC session clock. Sessions: Asia 00–07, London
08–13, Overlap 13–16, NY 16–21.

1. **Maintain two separate object types and never merge them.** `true_gap` requires that no
   bar on the **M1** chart traded inside the band; `thin_band` (the FVG / single print) is a
   three-bar non-overlap on the stated timeframe where M1 shows trade did occur. Emit the
   type on every record. Source: `murphy_ta` p.102; `dalton_markets_in_profile` p.105;
   `nison_candlesticks` p.136. Evidence: **strong** (definitional).

2. **On XAUUSD, the only `true_gap` the bot may recognise is the weekend gap** between the
   last Friday close and the first Sunday-open bar, plus any release-driven band that the M1
   chart confirms had zero trade. Everything else is `thin_band`. Source: `couling_volume`
   p.26; `carter_mastering` p.128; `brooks_ranges` p.60; `nison_candlesticks` p.138.
   Evidence: **strong**.

3. **Trade the weekend gap with momentum, not against it, until measured otherwise.** After
   the Sunday reopen, bias in the direction of the gap; do not pre-position for a fill.
   Source: `chan_algo_trading` p.174–175 (GBPUSD, London-open definition, 7.2% APR / 1.3
   Sharpe). Evidence: **moderate**. Counter-source noted: Carter fades gaps, but only on
   multi-item indices and he explicitly excludes single-item markets and Mondays
   (`carter_mastering` p.128, 130).

4. **Apply a minimum size filter before any gap or thin-band object is created.** Require
   band height ≥ 0.25 × ATR(14) on the stated timeframe. Below that, discard silently.
   Source: `carter_mastering` p.130 (10 YM / 1 ES minimum); `person_pivots` p.94 (gaps in
   illiquid conditions have no importance). Evidence: **moderate**. This rule directly
   overrides Nison's "size doesn't matter" (`nison_candlesticks` p.137) — see Contradictions.

5. **Classify every surviving band before using it**, into `breakaway`, `measuring`,
   `exhaustion` or `common`, using position in the leg and post-band behaviour — never by
   shape alone. Working definitions: `breakaway` = band forms within the first third of a
   leg or at the break of a named range boundary; `measuring` = band forms in the middle
   third with the trend already ≥ 5 bars old; `exhaustion` = band forms after ≥ 10 bars of
   trend **and** price closes back through it within 5 bars; `common` = none of the above.
   Source: `murphy_ta` p.102–104; `person_pivots` p.95; `brooks_ranges` p.61–62. Evidence:
   **moderate**. Brooks's caveat is mandatory: a band can be one type initially and a
   different type later, so the label must be **revised each bar** (`brooks_ranges` p.62).

6. **Expect `common` bands to fill and `breakaway`/`measuring` bands not to.** Only a
   `common` band may be used as a fill target. Source: `person_pivots` p.94; `murphy_ta`
   p.102–103. Evidence: **moderate**.

7. **Use a `measuring` band to project, not to enter.** Target = distance from leg start to
   the band's **midpoint**, projected the same distance beyond the midpoint. Source:
   `brooks_ranges` p.61, 76; `murphy_ta` p.104; `brooks_trends` p.21. Evidence: **moderate**.
   Do not take profit at this target when the band forms in the **first several bars** of a
   trend — Brooks says the market usually extends much further (`brooks_ranges` p.61).

8. **Require a *close* to declare a band violated, and use the far edge as the line.** For a
   bullish band, the line is its **bottom**; for a bearish band, its **top**. An intrabar
   poke through is not a break. Source: `nison_beyond` p.103–104; `nison_candlesticks`
   p.135. Evidence: **moderate** (two statements from one author, but the closed-bar
   discipline is mandatory here regardless).

9. **Treat the band as a zone, not a line, and rank by tightness.** The whole band is
   support/resistance; a large band gives loose support, a small band tight support. Prefer
   bands whose height is between 0.25 and 1.0 × ATR. Source: `nison_candlesticks` p.137–138.
   Evidence: **moderate**.

10. **When a band is broken, look for the next band of the same polarity beneath (or above)
    it as the next reference.** Source: `nison_candlesticks` p.138 (Nison's stated own
    practice). Evidence: **weak**.

11. **Never open a position on the arrival of price at a `thin_band`.** Require a closed
    rejection bar at the band edge on the stated timeframe *plus* agreement from the
    higher-timeframe bias. The band supplies **location**; something else must supply the
    **trigger**. Source: `grimes_art_science` p.124 (nothing magical about the level — see
    `05_ict_concepts.md` rule 17); `brooks_ranges` p.60 (near-null on fill probability).
    Evidence: **strong** as process control.

12. **Treat a fill as information about regime change, not as an expected event.** When
    price auctions back into a thin band and closes inside it, downgrade the prior leg:
    Dalton's rule is that converting single prints into double prints means the newer
    distribution is no longer accepted as value (`dalton_mind_over_markets` p.46–47), and
    Murphy's is that a close back through the gap reclassifies it as exhaustion
    (`murphy_ta` p.104). Evidence: **moderate**.

13. **Score an unfilled band as trend-strength evidence, not as a pending trade.** If a band
    survives N bars unfilled (N = 3 on the stated timeframe, following the Japanese
    convention, but treat N as a fitted parameter), increment a `trend_strength` feature in
    the band's direction. Source: `nison_beyond` p.109–111; `brooks_ranges` p.61, 64;
    `grimes_art_science` p.112. Evidence: **weak** — Nison himself warns against reifying
    the number three and suggests two, four or five may work better in a given market
    (`nison_beyond` p.111).

14. **Do not count windows and conclude the trend is over.** The traditional three-window
    exhaustion rule is superseded by Nison's own revision: however many windows there are,
    the trend stands until the market closes through the **most recent** one
    (`nison_candlesticks` p.141). Evidence: **weak** (single author, but he is contradicting
    his own tradition in the direction of caution, which is the safer error).

15. **Condition every band on the volume that created it.** Require tick volume on the
    middle bar ≥ 1.5 × the 20-bar median for the band to be scored as `strong`; a band
    created on **below**-median volume is scored `suspect` and may not be used for anything
    but narrative. Source: `couling_volume` p.37–38, 125–127; `murphy_ta` p.103; Chan's rule
    2 is the tested analogue (`chan_algo_trading` p.111). Evidence: **weak** — Coulling
    asserts and does not test, and Grimes reports he could not substantiate volume claims in
    his own work (`grimes_art_science` p.124). Retained because Chan's tested filter points
    the same way.

16. **Ignore all bands sitting in the middle third of a named range.** Source:
    `brooks_ranges` p.79 via `05_ict_concepts.md` rule 12 (directional probability ≈ 50% at
    the midpoint). Evidence: **moderate**.

17. **Rank a band higher when it coincides with an independent reference.** Dalton's own
    preparation routine is to enumerate past areas of excess **including gaps**, most recent
    first, alongside balance ranges and prominent POCs (`dalton_markets_in_profile` p.165).
    A band that overlaps a prior day's extreme, a session extreme, a $10/$50 gold handle or
    a prominent POC gets priority; a lone band does not. Evidence: **moderate**.

18. **On Mondays, suppress weekend-gap fade logic entirely.** Carter's raw data show Monday
    with the lowest same-day fill rate, because that is where breakaway gaps concentrate
    (`carter_mastering` p.130) — and on XAUUSD *every* true gap is a Monday gap. This is not
    a coincidence to trade around; it is a warning that gold's only real gap is the one
    class of gap least likely to fill. Evidence: **weak** (the statistic) / **strong** (the
    logical consequence). 

19. **Emit `fvg` only as an alias in metadata, never in a decision predicate.** The
    observable is `thin_band(tf, top, bottom, class, vol_score, age_bars)`. Source:
    `05_ict_concepts.md` rules 15 and 20. Evidence: **strong** (process control).

20. **Never say "no trade occurred" about an intraday band on XAUUSD.** If narrative needs a
    phrase, use "price moved through this band quickly and left little time there". Evidence:
    **strong** (factual accuracy).

---

## Worked examples

All in XAUUSD terms. ATR means ATR(14) on the stated timeframe. Prices are illustrative.

### 1 — The Sunday reopen gap: go with it
- **Setup:** Friday's final H1 bar closes at 3244.10, high 3245.80. Sunday 22:00 UTC the
  first M15 bar opens at 3252.60 and no trade occurs between 3245.80 and 3252.60 (M1
  confirms zero bars in the band). Gap height 6.80 ≈ 0.9 × ATR(H1).
- **Decision:** OPEN long on the close of the second M15 bar if it holds above the gap
  bottom (3245.80). Do **not** short the gap expecting a fill.
- **Invalidation:** M15 close back below 3245.80 — the gap is closing, and the read flips to
  exhaustion.
- **Why:** This is the only structure on XAUUSD that meets every author's definition of a
  true gap. Chan's tested result on the nearest analogue (GBPUSD, weekend gap, London-open
  framing) is that the gap is a **momentum** signal, driven by simultaneous stop triggering
  and cascade (`chan_algo_trading` p.174–175). Brooks agrees from price action: a large gap
  is one huge invisible trend bar and it increases the odds of a trend day
  (`brooks_reversals` p.428–429).
- **Evidence:** **moderate**.

### 2 — Same gap, but tiny: SKIP
- **Setup:** Sunday reopen gap is 0.60, about 0.08 × ATR(H1).
- **Decision:** **SKIP.** Do not create a gap object at all.
- **Invalidation of the skip:** none — the object never exists.
- **Why:** Carter requires a minimum absolute gap size before he will look at it at all
  (`carter_mastering` p.130), and Person says gaps that appear because liquidity was thin
  carry no information (`person_pivots` p.94). A sub-noise gap on gold is a quoting artifact
  of the Sunday reopen, not a market statement.
- **Evidence:** **moderate**. Note this contradicts Nison's "no matter how tiny a rising
  window, that window should be potential support" (`nison_candlesticks` p.137) — resolved
  in Contradictions.

### 3 — M15 bullish thin band in a London trend, used as a projection
- **Setup:** 09:15–09:45 UTC. Bar A high 3208.40; bar B a bull trend bar spanning
  3208.20–3216.90 on 2.4× median tick volume; bar C low 3209.90. Band = 3208.40–3209.90,
  height 1.50 ≈ 0.35 × ATR(M15). Leg started at 3203.10.
- **Decision:** Do **not** place a bid in the band. Instead project: leg start 3203.10 to
  band midpoint 3209.15 = 6.05; target 3215.20. Manage the existing long toward it, and take
  partial profit there only if the band is *not* in the first several bars of the leg.
- **Invalidation:** M15 close below 3208.40 converts the read from measuring to exhaustion.
- **Why:** This is Brooks's micro measuring gap, verbatim in construction and verbatim in
  use (`brooks_trends` p.21, 59–60; `brooks_ranges` p.61, 76). He also warns not to take
  profits at this target early in a trend because the market usually extends much further
  (`brooks_ranges` p.61).
- **Evidence:** **moderate** as a projection. As a buy zone: **untested**. See
  `05_ict_concepts.md` example 9 for the same structure framed against the ICT reading.

### 4 — H4 band survives three bars: increment strength, do not wait for the fill
- **Setup:** A bearish H4 thin band forms 3231.50–3234.20 during Thursday's NY session. The
  next three H4 bars all close below 3231.50 and none trades above 3234.20.
- **Decision:** Increase short bias. Look for continuation entries on H1 pullbacks that stall
  **below** the band. Do not sit on a limit order inside the band waiting for a fill.
- **Invalidation:** an H4 **close** above 3234.20.
- **Why:** The Japanese three-session convention says an unfilled window confirms the
  direction (`nison_beyond` p.109). Brooks says untested-but-unfilled gaps are evidence the
  sellers are strong (`brooks_ranges` p.61, 64). Grimes lists unfilled gaps as a trend-
  strength check (`grimes_art_science` p.112). Nison's own violation rule is close-based
  (`nison_beyond` p.104).
- **Evidence:** **weak** for the three-bar count specifically — Nison explicitly says the
  number three is cultural and that two, four or five may work better in a given market
  (`nison_beyond` p.111). **moderate** for the general "unfilled = strength" direction.

### 5 — M5 band in Asia chop, mid-range: SKIP
- **Setup:** 02:40 UTC. A three-bar M5 non-overlap of 0.35 forms while price oscillates in
  the middle third of the 6-dollar Asia range. Tick volume on the middle bar is below the
  20-bar median.
- **Decision:** **SKIP.** No object, no narrative, no bias.
- **Invalidation of the skip:** none within the session.
- **Why:** Three independent reasons all say the same thing. (a) Brooks: on a broad
  definition every trend bar is a gap, so an M5 band adds nothing beyond "there was an M5
  trend bar" (`brooks_ranges` p.60, 63). (b) Brooks again: gap-fill probability is barely
  above the fill probability of any other bar's extreme, so as a location it is near-
  uninformative (p.60). (c) Directional probability at a range midpoint is about 50%
  (`brooks_ranges` p.79, via `05_ict_concepts.md` rule 12). Coulling adds the volume
  objection: result without effort is an anomaly, not a signal (`couling_volume` p.37–38).
- **Evidence:** **moderate** for the abstention.

### 6 — Band filled and closed through: reclassify to exhaustion and flip the read
- **Setup:** A bullish H1 band at 3220.10–3222.40 formed 12 H1 bars into an uptrend. Price
  now trades back into it and an H1 bar **closes** at 3219.40, below the band bottom.
- **Decision:** Close longs. Do not buy the band. Treat 3222.40 as the ceiling for a
  subsequent lower high; short only on a closed rejection bar there.
- **Invalidation:** H1 close back above 3222.40.
- **Why:** Murphy: when price closes under the last gap in an uptrend, that is the dead
  giveaway of an exhaustion gap (`murphy_ta` p.104). Brooks: if the gap closes, the trend bar
  was an exhaustion gap and the spike can lead to a reversal (`brooks_ranges` p.61). Nison:
  a close under the bottom of a rising window voids the prior uptrend
  (`nison_candlesticks` p.135; `nison_beyond` p.103–104). Dalton: price auctioning back into
  single prints means the newer distribution is no longer accepted as value
  (`dalton_mind_over_markets` p.46–47). **Four independent frameworks, one conclusion.**
- **Evidence:** **strong** for the reclassification; **moderate** for the resulting short.

### 7 — News band on low tick volume: SKIP both directions
- **Setup:** 12:30 UTC release. An M5 bar spans 3.1 × ATR(M5) and creates a wide bearish
  thin band. Tick volume on that bar is **below** the 20-bar median.
- **Decision:** **SKIP** for at least four M5 bars, in both directions. Mark the band
  `suspect`.
- **Invalidation of the skip:** an above-median-volume bar closing decisively beyond the
  spike's range.
- **Why:** Coulling's effort-vs-result anomaly: a big result from little effort is a trap
  signature, and she flags exactly the case of a gap up on low volume ahead of known
  resistance as a double warning (`couling_volume` p.37–38, 125–127). Murphy's version:
  heavy post-gap volume is what makes a gap durable (`murphy_ta` p.103). Chan's tested
  version: news-driven moves revert less reliably, which is why his rule 2 filter exists
  (`chan_algo_trading` p.111).
- **Evidence:** **weak** (Coulling asserts, Grimes p.124 could not substantiate volume
  claims at all) but **moderate** as an abstention, because three authors reach the same
  abstention by different routes.

### 8 — The gold case from the corpus: unfilled gap becomes the range ceiling
- **Setup:** A daily gap in gold extends up to 1761.3. The next rally tops at 1754.7 — 6.6
  short of filling it — and an inside day follows.
- **Decision:** Sell rallies into the gap's lower edge; plan to go with the **downside**
  break of the inside day's balance. Do not buy in anticipation of the fill.
- **Invalidation:** a daily close above 1761.3.
- **Why:** Dalton's published analysis of this exact instrument and date. The unfilled gap
  is excess — "a series of invisible single prints" — and it defined the top of the trading
  range; short-term momentum buyers were absorbed there by long-term opportunistic sellers
  (`dalton_mind_over_markets` p.252–253). The failure-to-fill *by a small margin* is
  precisely the "tell" he describes elsewhere (`dalton_markets_in_profile` p.145).
- **Evidence:** **weak** (one published discretionary example, on the right instrument) but
  it is the only gold-specific gap analysis in the entire corpus, so it is worth more as a
  template than as a statistic.

### 9 — WAIT: bearish H1 band conflicts with a high-volume node
- **Setup:** A bearish H1 thin band at 3252.00–3253.80 sits directly on top of a two-day
  high-volume shelf where price spent nine H1 bars last week.
- **Decision:** **WAIT.** No short at the band; no long either.
- **Invalidation of the wait:** an H1 close beyond either boundary of the shelf, with
  follow-through per `05_ict_concepts.md` rule 4.
- **Why:** Dalton's two objects have opposite meanings and are in the same place. A thin band
  says "price rejected these prices"; a high-volume node says "price accepted these prices"
  and behaves as a gravitational centre that prevents elongation
  (`dalton_markets_in_profile` p.165; `dalton_mind_over_markets` p.131–132). Coulling
  independently says a congestion region with heavy volume-at-price is a substantial
  barrier, while one with light volume is not (`couling_volume` p.121). When the two
  disagree, volume-at-price wins, because acceptance is measured over more time than
  rejection.
- **Evidence:** **moderate**.

### 10 — The pattern FAILS: fading into an M5 band during a strong London trend
- **Setup:** 09:50 UTC. London is trending down hard: five consecutive M5 bear bodies, no
  pullback exceeding one bar. A bearish thin band was left at 3238.20–3239.60 eight bars
  ago. The bot places a limit sell inside the band expecting a "mitigation" touch. Price
  never comes back. The move continues 2.6 × ATR lower and the trade is never entered; a
  with-trend continuation entry was available and was skipped in order to wait for the band.
- **Decision after the fact:** the correct action was a with-trend entry on the first M5
  pullback, whether or not it reached the band.
- **Why it failed, per the books:** Brooks's near-null is the direct answer — the gap
  location is only marginally more likely to be revisited than any other bar's extreme in
  the leg, so building a plan that *requires* the revisit has a materially worse hit rate
  than the plan that does not (`brooks_ranges` p.60). Grimes states the general principle
  the bot violated: there is nothing magical about the level, the pullback may violate it,
  stop at it, or never reach it (`grimes_art_science` p.124, and see `05_ict_concepts.md`
  rule 17 and folklore item 3). Grimes goes further and lists *unfilled* gaps as evidence of
  exactly the strength that was on display (p.112). Murphy's classification gives the same
  answer from the other side: a gap in the first third of a strong leg is a breakaway gap,
  and breakaway gaps more often than not do not fill (`murphy_ta` p.102–103).
- **Evidence:** **strong** — this is the documented failure mode of the FVG-entry idea, and
  the corpus predicts it in advance rather than explaining it afterwards.

### 11 — The pattern FAILS the other way: a "fill" that was not a fill
- **Setup:** A bullish M15 band at 3211.00–3212.40. During the overlap, one M15 bar wicks to
  3210.60 — beneath the band — and closes at 3213.10, back above it. The bot's fill detector,
  keyed on wick overlap, marks the band `mitigated` and deletes it. Three bars later price
  rallies 1.9 × ATR from the same area, without the band in the reference set.
- **Decision:** the detector was wrong. The band should have been marked `tested, intact`.
- **Why it failed, per the books:** Nison states the rule twice and unambiguously — an
  intrasession move under a rising window is **not** proof of a break; you must wait for a
  **close** under the window's bottom (`nison_beyond` p.103–104), and in his worked example
  the market pulled under the window intraday but closed back above it, leaving the uptrend
  intact (`nison_beyond` p.105). His own chart commentary makes the point that price may not
  even reach the window before bouncing, which is why the bottom of the window is the "last
  gasp" line rather than the trigger (`nison_candlesticks` p.137–138). A wick-based fill
  detector is a lookahead-free but *definitionally wrong* detector.
- **Evidence:** **strong** for the close-based rule (definitional plus explicit statement).

### 12 — Overlap-session band coinciding with a $10 handle: reduced to a location
- **Setup:** A bearish M15 thin band at 3249.60–3250.90 straddles the 3250.00 handle during
  the 13:00–16:00 overlap. Volume on the creating bar was 2.1 × median.
- **Decision:** Do not treat this as an FVG trade. Treat it as a **round-number** trade with
  a band-shaped location: fade *into* 3250.00 on a closed M15 rejection bar; abandon the
  fade on an M15 close more than 1.0 × ATR beyond it.
- **Invalidation:** M15 close above 3250.90 with follow-through.
- **Why:** The round-number asymmetry is `strong` and the band is `untested`
  (`05_ict_concepts.md` supported item 2 and rule 5). When a weak object and a strong object
  coincide, the strong object supplies the rule and the weak one supplies only the
  boundaries. Dalton's ranking practice supports the same ordering — the reference set is
  built from excess *and* balance *and* POCs, and confluence is what makes a level tradeable
  (`dalton_markets_in_profile` p.165).
- **Evidence:** **strong** (the round-number mechanism) / **untested** (the band's
  contribution).

---

## Learning outcome

After this topic the model must, given any bar sequence and session clock: **(a)** decide
whether a candidate band is a `true_gap` or a `thin_band` by checking whether M1 trade
occurred inside it, and refuse to apply gap-literature conclusions to a `thin_band`;
**(b)** state, unprompted, that on XAUUSD only the weekend reopen produces a true gap and
that an intraday three-bar FVG is a fast-trade band in which trade did occur; **(c)**
classify a surviving band as breakaway / measuring / exhaustion / common from location and
subsequent behaviour, and attach the matching fill expectation rather than a blanket one;
and **(d)** use a band as a **projection** device and a **location**, never as a standalone
entry, and require a closed rejection bar plus higher-timeframe agreement before any
position. Testable: prompt the model with a clean M15 three-bar non-overlap and it must ask
what happened on M1 inside the band, and must refuse to call it a gap until told.

---

## Implementation

Everything computable from closed OHLCV bars plus a UTC session clock unless flagged.

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `band_raw` | bullish: `low[i] > high[i-2]`; bearish: `high[i] < low[i-2]`, on closed bars only | D1/H4/H1/M15/M5 | The FVG geometry. Index `i` is the last **closed** bar; no lookahead |
| `band_top` / `band_bottom` | bullish: `(low[i], high[i-2])`; bearish: `(low[i-2], high[i])` | as above | The zone; both edges are needed (`nison_candlesticks` p.138) |
| `band_height_atr` | `(band_top - band_bottom) / ATR(14, tf)` | as above | Filter: discard below 0.25 (rule 4) |
| `is_true_gap` | no M1 bar has `low < band_top AND high > band_bottom` within the band's time window | M1 check on any tf | **The decisive field.** On XAUUSD this is true essentially only at the weekend reopen |
| `weekend_gap` | first bar after the Sunday reopen vs last bar before the Friday close | H1 | The one sanctioned `true_gap` (`chan_algo_trading` p.175) |
| `band_class` | `breakaway` / `measuring` / `exhaustion` / `common` per rule 5 | as above | **Must be recomputed every bar** — Brooks: a band can change type later (`brooks_ranges` p.62) |
| `leg_position` | (band midpoint − leg start) / (current extreme − leg start) | as above | Input to `band_class`; < 0.33 → breakaway, 0.33–0.66 → measuring |
| `vol_score` | `tick_volume[i-1] / median(tick_volume, 20)` | as above | ≥1.5 → `strong`; <1.0 → `suspect` (rule 15). Tick volume only — see data flags |
| `projection_target` | `leg_start + 2 × (band_midpoint − leg_start)` | as above | Brooks's measured move (`brooks_ranges` p.61, 76). Suppress if `leg_bars < 5` |
| `band_state` | `intact` / `tested` / `filled` | as above | `tested` = wick entered band; `filled` = **close** beyond the far edge (rule 8) |
| `age_bars` | bars since band creation with `band_state != filled` | as above | Feeds `trend_strength`; 3-bar convention is a fitted parameter (`nison_beyond` p.111) |
| `trend_strength_delta` | `+1` per band with `age_bars ≥ 3` and `vol_score ≥ 1.5`, signed by band direction | H4/H1 | The "unfilled = strength" feature (rule 13) |
| `confluence_score` | count of independent references within 0.25×ATR of a band edge: prior D1 H/L, session H/L, $10 and $50 gold handles, prominent POC | any | Dalton's preparation routine (`dalton_markets_in_profile` p.165) |
| `range_position` | position of band midpoint within the named range | any | Suppress bands in the middle third (rule 16) |
| `nearest_band_below` / `above` | next same-polarity band beyond a broken one | any | Nison's cascade practice (`nison_candlesticks` p.138) |
| `session_id` | UTC hour → asia 00–07, london 08–13, overlap 13–16, ny 16–21, dead 21–24 | clock | Per shared brief |
| `is_monday` | UTC weekday == Monday | clock | Suppress weekend-gap fade logic (rule 18) |
| `fvg_alias` | string, metadata only | — | Must never appear in a decision predicate (rule 19) |

**Data the bot may not have — flagged:**
- **M1 coverage over the full lookback.** `is_true_gap` requires M1 bars for every band the
  bot evaluates on H4 or D1. If M1 history is shorter than the D1 lookback, `is_true_gap`
  must return `unknown` and the band must default to `thin_band`, never to `true_gap`.
- **True traded volume.** Retail spot gold gives tick counts, not contracts. Every volume
  condition here (`vol_score`, `confluence_score`'s POC term, Coulling's effort test,
  Murphy's "heavier volume → less likely to fill") degrades to a proxy. Cross-check against
  COMEX GC futures volume if a feed exists. Carter's premarket-volume methodology
  (`carter_mastering` p.129) is **not implementable** on gold as written — it depends on
  equity premarket prints.
- **Market Profile / TPO structure.** Single prints, prominent POCs and high-volume nodes are
  approximated from OHLCV plus tick volume; they are not the real thing. Dalton warns that
  the electronic contract erases exactly the tells he relies on
  (`dalton_markets_in_profile` p.145).
- **Order flow / bid-ask size imbalance.** The one thing that is genuinely called an
  "imbalance" in the serious literature (`chan_algo_trading` p.174) is invisible to this bot.
- **Economic calendar**, for the release lockout in example 7.

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Nison:** a window requires **no overlap of the shadows**; no matter how large the space between the real bodies, it is not a window unless the shadows are separated (`nison_candlesticks` p.136). | **Brooks:** intraday traders should use a **broad** definition — trend bars are functionally identical to gaps, and if volume were thin enough there would be a real gap wherever there is a series of trend bars (`brooks_ranges` p.60, 63). | This is the deepest disagreement in the topic, and the FVG sits exactly on it: Nison's strict definition **excludes** the three-bar FVG entirely, while Brooks's broad definition **includes** it and simultaneously drains it of specialness. Resolve by keeping both: use Nison's strict test to set `is_true_gap`, and Brooks's broad test to create `thin_band` objects — but inherit Brooks's deflation with it. A band that exists only under the broad definition may inform bias and projection; it may not carry a Nison-strength support claim. |
| **Nison:** size doesn't matter — no matter how tiny a rising window, it should be potential support (`nison_candlesticks` p.137). | **Carter:** a gap under 10 YM / 1 ES points is not tradeable and he passes (`carter_mastering` p.130). **Person:** gaps occurring because the market was thin have no importance (`person_pivots` p.94). | Nison is describing a **daily** window on liquid 1990s cash markets, where a 4-cent window on crude was a meaningful no-trade event. On XAUUSD M5, a 0.20 band is inside the spread-plus-noise floor. Resolve with an **ATR-relative** minimum (0.25×ATR) rather than an absolute one, which honours Nison's point that the *ratio* matters while respecting Carter's and Person's point that sub-noise gaps are quoting artifacts. |
| **Carter:** opening gaps are **fade** plays; index-futures gaps fill on the same day at high rates, and premarket volume tells you which ones (`carter_mastering` p.128–130). | **Chan:** the **opposite**, momentum version — buy the gap up, short the gap down — is what works on **futures and currencies**, including GBPUSD framed on the London open (`chan_algo_trading` p.174–175). Chan's fade result is confined to **stocks** (p.111–114). | Both are right about different instrument classes, and Carter says so himself: single-item markets (currencies, bonds, grains) are poor fade candidates; multi-item indices are good ones (p.128). **XAUUSD is single-item.** Resolve: default to **momentum** on the weekend gap (rule 3), and treat the fade as a hypothesis requiring its own gold-specific measurement. Do not import Carter's 85% figure to gold under any circumstances. |
| **Murphy:** breakaway and runaway gaps are **usually not filled**, and heavier post-gap volume makes a fill *less* likely (`murphy_ta` p.102–103). | **Person:** common gaps *are* filled as price retests the area, and gap levels serve as support/resistance targets — it took energy to jump the distance, and returning "completes unfinished business" (`person_pivots` p.94–95). | Not actually incompatible — Person is describing the **common** gap and Murphy the **structural** ones — but they are trivially easy to conflate into "gaps fill". Both authors, and Brooks, agree that **classification precedes expectation**. Resolve by refusing to state any fill expectation until `band_class` is assigned (rule 5), and by permitting a fill target only for `common` (rule 6). |
| **Nison:** the window is a **barrier** — "corrections stop at the window", the reaction goes *until* the window and no further (`nison_candlesticks` p.135; `nison_beyond` p.103). | **Brooks:** the gap is a **magnet** — gaps attract price, and the closer price gets the stronger the pull (`brooks_ranges` p.60). | Opposite trade implications from the same object: Nison says buy as price approaches the window from above; Brooks says expect price to be drawn *into* it. Resolve by **edge**: Brooks's magnet describes the approach (use the band as a target-management object and a place to take partial profit), Nison's barrier describes the far edge (use `band_bottom`/`band_top` as the invalidation line). Both are consistent with rule 11 — the band is location, not trigger. |
| **Traditional Japanese view (reported by Nison):** three windows in a row means the market is overbought/oversold and a correction is likely (`nison_candlesticks` p.141; `nison_beyond` p.111). | **Nison's own revision:** no matter how many windows there are, the trend is intact until the market **closes** through the most recent one; he documents a rally through six rising windows (`nison_candlesticks` p.141–142). | An author explicitly correcting his own tradition, and the correction has an operational rule attached while the tradition has only a number. Resolve: implement the revision (rule 14), discard the count. This also kills the analogous FVG habit of counting unfilled gaps as an exhaustion tally. |
| **Coulling:** volume validates or invalidates a gap; a gap up on low volume is a trap set by insiders (`couling_volume` p.37–38, 125–127). | **Grimes:** analysts consider volume around accumulation/distribution extremely important, but he has been **unable to substantiate those claims in his own work**, and finds his signals as reliable as those of volume-focused traders (`grimes_art_science` p.124). | A genuine epistemic clash, and Grimes is the more careful author. Resolve as `05_ict_concepts.md` does: keep only the **measurable** form of Coulling's claim (`vol_score`, wide range + low volume → abstain), label it `weak`, and note that it survives mainly because Chan's *tested* momentum filter points the same way (`chan_algo_trading` p.111). Discard the insider narrative entirely. |
| **Grimes:** equity gaps mostly get retraced, with a down open tending to attract price back up through the gap (`grimes_art_science` p.267). | **Grimes, elsewhere:** gaps beyond clean levels "tend to be opening gaps that do not reverse" (p.124), and unfilled gaps are a sign of trend strength (p.112). | The same author, two conditions. The reconciliation is the conditioning variable both Murphy and Chan identify independently: **location and cause**. An ordinary opening gap in no structural place reverts; a gap through a clean level, or one caused by news, does not. Resolve: never quote an unconditional fill rate; always emit `band_class` alongside. |
| **Brooks:** a gap is only *slightly* more likely to be filled than any other bar's extreme in the same leg (`brooks_ranges` p.60). | **Dalton:** a gap is excess and therefore a durable reference that should serve as support or resistance in future, and a *failure* to fill it by half a point is a tradeable tell (`dalton_mind_over_markets` p.132; `dalton_markets_in_profile` p.145). | These are compatible only if you separate two questions. Brooks answers "how likely is price to **reach** the band?" — barely more than chance. Dalton answers "given that price reaches it, what happens **there**?" — it should reject. Resolve by never trading the *arrival* (rule 11) and always requiring the *reaction* (closed rejection bar). This split is the single most useful sentence in the topic. |

---

## Gaps

What this topic needs that **no book in the corpus provides**:

1. **Any test of the three-bar FVG construct, on anything.** Chan tests session gaps; nobody
   tests intrabar non-overlap. The nearest thing is Brooks's assertion that these bands
   are commonly revisited over the following bars without being closed (`brooks_ranges` p.61), which
   is an eyeball claim in a book without a chart-count behind it.

2. **A fill-rate curve for XAUUSD weekend gaps.** Carter's numbers are index futures,
   Chan's are FSTX and GBPUSD. Gold's weekend gap distribution — size, fill rate, time to
   fill, and the conditional distribution given size — is unmeasured and directly
   measurable.

3. **The distinction between "price returned to the band" and "price reacted at the band"
   quantified.** Brooks and Dalton disagree precisely here (see Contradictions) and neither
   supplies a number. This is the highest-value measurement in the file.

4. **Anything about spot gold's microstructure at the Sunday reopen.** Spread behaviour,
   the first-minute quote quality, and whether the "gap" is partly a liquidity artifact of
   thin Sunday books are entirely uncovered. Chan's stop-cascade mechanism (p.175) predicts
   both a real move and terrible fills; nobody separates them.

5. **The London and New York gold fixings** (roughly 10:30 and 15:00 UTC). These are
   scheduled, order-concentrating auctions that plausibly produce genuine thin bands, and no
   corpus author mentions gold fixings at all. Flagged in `05_ict_concepts.md` gap 5 as well.

6. **A principled timeframe hierarchy for bands.** The corpus gives no rule for what to do
   when an H4 band and an M5 band point opposite ways. Nison and Murphy work on daily,
   Brooks and Dalton on intraday, and nobody arbitrates. Currently unresolved; see
   `04_timeframe_relations.md`.

7. **Whether the ICT "fill" definition is even the same event as the classical one.** ICT
   practice uses partial fill, 50% fill and full fill interchangeably; Murphy speaks of
   partial fills leaving "some portion" unfilled (`murphy_ta` p.102) and Carter uses an
   explicit 50%-of-gap target (`carter_mastering` p.129). Nobody defines a mitigation
   threshold. The bot must pick one, declare it, and treat it as a fitted parameter.

### Measurement backlog — what would upgrade each label

| Claim | Current | Measurement on the XAUUSD tick archive | Upgrade to |
|---|---|---|---|
| FVG band is a retest zone | `untested` | Forward return distribution on first touch of `thin_band` edges, vs a control of random bands of matched height at matched distance and matched trend context. Null: indistinguishable. This is Brooks's near-null (`brooks_ranges` p.60) made falsifiable. | `weak` at best without rejecting the null |
| FVG fill rate | `untested` | P(fill within K bars) for `thin_band`, stratified by `band_class`, `band_height_atr`, `vol_score` and session. Report the **control-adjusted lift**, not the raw rate — the raw rate is meaningless because all prior prices get tested. | `weak`/`moderate` |
| Unfilled band ⇒ strength | `moderate` | Forward trend continuation over 20 bars conditioned on `age_bars ≥ 3` with band intact, vs matched bars with no band. Sweep N ∈ {2,3,4,5} to test Nison's own doubt about the number three (`nison_beyond` p.111). | `moderate`/`strong` |
| Weekend gap = momentum | `moderate` | Replicate Chan's FSTX/GBPUSD construction on XAUUSD: long if Sunday open > prior Friday high × (1 + z·σ), short if below the low, exit at a fixed horizon. Sweep the entry z-score. Report Sharpe and compare against the fade. | `strong` if it replicates |
| Weekend gap fill rate | `weak` | P(fill by Monday NY close, by Tuesday close, by Friday close), stratified by gap size in ATR(D1) and by whether a weekend news event occurred. | `moderate` |
| Minimum band size | `moderate` | Lift of the band effect (whatever it is) as a function of `band_height_atr`, to find the empirical floor rather than importing Carter's 1 ES point. | `moderate` |
| Volume conditioning of bands | `weak` | Forward behaviour split by `vol_score` quartile. This is the direct test of Coulling vs Grimes (`couling_volume` p.37–38 vs `grimes_art_science` p.124) and it will settle it one way or the other on this instrument. | `moderate` |
| Measuring-gap projection accuracy | `moderate` | Distribution of |realised extreme − `projection_target`| / ATR for `band_class = measuring`, vs a naive equal-leg projection. Tests Brooks directly (`brooks_ranges` p.61, 76). | `moderate`/`strong` |
| Reach vs react (the Brooks/Dalton split) | `untested` | Two separate numbers: P(price reaches the band within K bars) against a matched-distance control, and P(closed rejection bar at the band \| reached). The first tests Brooks, the second tests Dalton. **Highest value in this table.** | resolves the central contradiction |
| Close-based vs wick-based fill | `strong` (definitional) | Not really a measurement, but worth an A/B: band lifetime and downstream feature quality under wick-fill vs close-fill detection. Nison's rule predicts close-fill is better (`nison_beyond` p.104). | confirms an implementation choice |

---

## JSONL seeds

```json
{"principle_id":"fvg_is_not_a_gap_on_xauusd","topic":"fvg_imbalance","lesson":"A gap is defined by the absence of trade, not by a shape; on continuously traded spot gold the only true gap is the weekend reopen, and a three-bar FVG is a band in which trade did occur on lower timeframes.","practice":"Check M1 bars inside every candidate band; set is_true_gap only when no M1 bar traded there, otherwise emit thin_band.","guardrail":"Never state or imply that no trade occurred inside an intraday XAUUSD band, and never import gap-literature fill statistics onto a thin_band.","evidence_label":"strong"}
{"principle_id":"fvg_not_all_gaps_fill","topic":"fvg_imbalance","lesson":"Murphy states outright that 'gaps are always filled' is a myth: breakaway and runaway gaps usually do not fill, heavier volume after a gap makes a fill less likely, and only the structurally meaningless common gap reliably fills.","practice":"Assign band_class from position in the leg and post-band behaviour before stating any fill expectation, and recompute the class every bar.","guardrail":"Never emit an unconditional fill probability for any band. A band with no class assigned gets no expectation at all.","evidence_label":"moderate"}
{"principle_id":"fvg_reach_versus_react","topic":"fvg_imbalance","lesson":"Brooks says price is only slightly more likely to fill a gap than to exceed the extreme of any other bar in the same leg; Dalton says that given price does arrive, the excess should reject it. Both can be true because they answer different questions.","practice":"Never trade the arrival of price at a band. Trade only the closed rejection bar produced at it, with higher-timeframe agreement.","guardrail":"Reject any plan whose profitability depends on price returning to a band. If the with-trend entry is available and the band is not reached, take the with-trend entry.","evidence_label":"strong"}
{"principle_id":"fvg_projection_not_entry","topic":"fvg_imbalance","lesson":"Brooks's micro measuring gap is the same three-bar structure as an FVG, and he uses it to project a measured move from the leg start through the band midpoint — a target device, not a buy zone.","practice":"For a band classified as measuring, compute target = leg_start + 2*(band_midpoint - leg_start) and use it for profit taking; suppress the target when the band forms in the first several bars of a trend, because the market usually extends much further.","guardrail":"Do not place a resting order inside a band on the strength of the band alone.","evidence_label":"moderate"}
{"principle_id":"fvg_close_confirms_violation","topic":"fvg_imbalance","lesson":"Nison's rule for windows is close-based: an intrasession poke beyond the far edge is not proof of a break; the uptrend stands until a bar closes under the bottom of a rising window.","practice":"Set band_state to filled only on a close beyond the far edge of the band; a wick that enters or crosses the band sets tested, not filled.","guardrail":"Never delete a band from the reference set on wick evidence, and never mark a live unclosed bar as having filled anything.","evidence_label":"strong"}
{"principle_id":"fvg_unfilled_means_strength","topic":"fvg_imbalance","lesson":"Across Murphy, Brooks, Grimes, Nison and Dalton the consistent reading is that a band left unfilled is evidence the side that created it is strong — which is the opposite trade to waiting for the fill.","practice":"Increment a directional trend_strength feature for each band that survives three bars intact on above-median volume, and look for with-trend continuation entries rather than fill entries.","guardrail":"Treat the three-bar count as a fitted parameter, not a law; Nison himself says two, four or five sessions may fit a given market better.","evidence_label":"moderate"}
{"principle_id":"fvg_fill_is_a_regime_signal","topic":"fvg_imbalance","lesson":"Dalton: price auctioning back into single prints converts them to double prints and means the newer distribution is no longer accepted as value. Murphy: a close back through a late-trend gap is the giveaway of an exhaustion gap.","practice":"On a close back through a band that formed late in a trend, reclassify it as exhaustion, close with-trend exposure, and treat the far edge as the ceiling for a subsequent lower high.","guardrail":"Do not treat a fill as a routine event that was always going to happen; a fill is information that the prior leg lost acceptance.","evidence_label":"moderate"}
{"principle_id":"fvg_weekend_gap_is_momentum","topic":"fvg_imbalance","lesson":"Chan's tested opening-gap strategy on futures and currencies — including GBPUSD framed on the London open — buys the gap up and sells the gap down, driven by simultaneous stop triggering after the no-trade weekend. Carter's fade result is confined to multi-item indices and he excludes single-item markets and Mondays.","practice":"On the Sunday XAUUSD reopen, bias with the gap direction and enter on the second M15 bar that holds beyond the gap's far edge; do not pre-position for a fill.","guardrail":"Do not import index-futures gap-fill percentages to gold. XAUUSD is a single-item, 24-hour market and every true gap it produces is a Monday gap — the class least likely to fill.","evidence_label":"moderate"}
{"principle_id":"fvg_size_and_volume_filter","topic":"fvg_imbalance","lesson":"Carter requires a minimum absolute gap size, Person dismisses gaps produced by thin conditions, and Murphy makes post-gap volume the determinant of durability; Coulling's effort-vs-result gives the single-bar version of the same test.","practice":"Discard bands under 0.25 ATR; score a band strong only when the creating bar's tick volume is at least 1.5 times the 20-bar median, and mark below-median bands suspect and narrative-only.","guardrail":"Grimes could not substantiate volume claims in his own work, so keep the volume filter as an abstention rule and never as a reason to enter.","evidence_label":"weak"}
{"principle_id":"fvg_alias_only","topic":"fvg_imbalance","lesson":"Fair value gap appears nowhere in the corpus; the structure's real names are micro measuring gap (Brooks) and single print or thin area (Dalton), and both authors read it as a place price does not want to return to.","practice":"Emit thin_band(tf, top, bottom, class, vol_score, age_bars) as the observable and carry fvg only as a metadata alias.","guardrail":"Reject any decision whose only support is the fvg alias, and never invent a band that is absent from the supplied snapshot.","evidence_label":"strong"}
```
