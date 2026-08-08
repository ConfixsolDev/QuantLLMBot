# Topic 7 — Trading in Trend

> **Sources read:** `brooks_trends` pp.15–29, 91–93, 130, 209–216, 241–244, 251–254, 281–285, 307–312, 321–327, 339–341, 351–353, 357–361, 391–395, 415–419, 463–466 · `brooks_ranges` pp.14–15, 21–22, 52–55 · `grimes_art_science` pp.21–23, 40, 58–59, 67–79, 171–186, 248–249, 301, 409 · `dalton_mind_over_markets` pp.43–47, 65–66, 69–75, 83–89 · `dalton_markets_momentum` pp.26, 54–55, 120–134 · `murphy_ta` pp.43, 76–78, 81, 86, 94–95, 193–199 · `elder_trading_room` pp.96–97, 138–147, 157, 182–184 · `carter_mastering` pp.114, 145, 154–155, 433–441, 457–462, 490 · `chan_algo_trading` pp.22–23, 38–39, 151–155, 163, 168–173
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1.2)

---

## ⚠️ Calibration note — read before using anything below

This topic contains the single largest gap in the corpus between **how confidently the books
assert** and **what has actually been measured**. Chan is the only author here who tested any of
it, and his results are the honest frame for everything that follows.

- **The sign of the trend/anti-trend relationship is not stable.** Chan measures correlations
  between a series' past returns and its future returns across a grid of look-back/hold pairs and
  finds coefficients from −0.014 to +0.41, with p-values that are frequently non-significant, on
  the *same instrument* (`chan_algo_trading pp.154–155`). His summary: financial series exhibit
  momentum at some horizons and mean reversion at others. There is no such thing as "this
  instrument trends"; there is only "this instrument trended at this horizon over this sample."
- **On that same series the Variance Ratio test failed to reject a random walk, and the Hurst
  exponent was 0.44 — i.e. mildly *anti*-persistent** (`chan_algo_trading p.154`). A momentum
  strategy was profitable on a series that a formal trending test says is not trending.
- **Statistical significance of a momentum backtest is not unique.** Chan runs three different
  null hypotheses on one momentum strategy and gets three different answers: reject at >99%
  (Gaussian), reject at only **88%** (simulated returns matched on mean/σ/skew/kurtosis), reject
  at ~100% (randomized entry dates) (`chan_algo_trading pp.38–39`). The middle result is the
  damning one: **1,166 of 10,000 random return series with matched kurtosis beat the strategy's
  actual return.** Roughly 12% of the time, a fat-tailed random series is enough. Chan's own
  conclusion: any high-kurtosis returns distribution is favourable to momentum, whether or not
  serial correlation exists (`chan_algo_trading p.39`).
- **Momentum edges decay on an unpredictable schedule.** Chan: the duration over which momentum
  persists gets progressively shorter as more traders catch on — post-earnings drift that used to
  last several days now barely lasts to the close — and there is no predictable schedule for
  shortening your holding period (`chan_algo_trading p.171`).
- **Momentum crashes are the characteristic tail risk.** Cross-sectional momentum in futures went
  from +18% APR / 1.37 Sharpe to −33% APR across 2008–09; the same strategy in stocks went +37%
  to −30%; the S&P DTI index sat in a −25.9% drawdown (`chan_algo_trading pp.163, 169`). After
  1929 a representative momentum strategy did not reach a new high-water mark for **over 30
  years** (`chan_algo_trading p.169`). Trend edges do not fail gently; they fail after crises,
  for years.
- **Data-snooping.** Chan: too many free parameters fitted to ephemeral patterns; and the moment
  you tweak a model because it failed out-of-sample, the out-of-sample data has become in-sample
  (`chan_algo_trading pp.22–23`). Every "if the trend is strong then X" rule below has an
  unstated free parameter in "strong."
- **The counterweight to the counterweight.** Chan also lists genuine structural pros: stop-losses
  and time-based exits are *logically consistent* with momentum (a reversed signal is itself a
  stop), so per-position downside is bounded, whereas mean reversion has unbounded downside per
  position (`chan_algo_trading pp.171–172`). This is the strongest honest argument for with-trend
  trading in the whole corpus, and it is a **risk-shape** argument, not a predictive one.

**Therefore:** nothing in this file is labelled `strong` on the basis of predictive edge.
`strong` is reserved for definitional/structural facts (what a spike is, what one-timeframing is,
what a stop beyond a swing low guarantees) and for claims where several independent authors agree
*and* the mechanism is mechanical. Brooks' repeated "about 80 percent," "60 to 70 percent," "70
percent or more likely" figures (`brooks_trends pp.309, 415`) are **assertions from screen
experience on the 5-minute Emini, not measurements**, and they are reported here as `weak` or
`untested` regardless of how confidently they are stated. Brooks himself concedes the baseline:
away from brief trend phases the directional probability of an equidistant move is about 50–50
(`brooks_ranges p.21`).

---

## Core concepts

| Concept | Definition (my words) | Sources | Evidence |
|---|---|---|---|
| Two-condition trend test | A trend does not exist because price went up. It exists when **both** (a) the prior trend's trend line — or the prior range's support/resistance — has been broken, and (b) the swings are now trending (higher highs *and* higher lows, or lower highs *and* lower lows). Absent either condition, there is no trend. | `brooks_trends p.309` | strong (definitional; it is a test, not a forecast) |
| Trend as divergence from value | Profile version of the same test: a trend is price diverging from value, visible as a series of value areas migrating in one direction over time. If value areas start overlapping or migrating against the move, the trend is balancing. | `dalton_mind_over_markets pp.71, 74` | moderate |
| One-timeframing | Mechanical trend test on a fixed bar interval: in an up-trend every successive 30-minute period's low is at or above the prior period's low. One-timeframing is over when price trades two ticks below the prior 30-minute bar's low. Dalton says shorter bars degrade the read. | `dalton_markets_momentum p.120` | strong (definitional and fully computable) |
| Trends are the minority state | Dalton: markets trend only 20–30% of the time; ~15% of *days* produce some type of trend, 85% are rotational. Brooks: ranges occur more often than strong trends, and the trending-range days are about twice as common as spike-and-channel days. | `dalton_mind_over_markets p.71`; `dalton_markets_momentum p.120`; `brooks_trends p.392` | moderate (three estimates, no shared measurement) |
| Directional probability baseline | Blind entry with symmetric target and stop wins ~50% of the time. During a strong trend it may reach 60–70%, but it cannot stay there — the market gravitates back to uncertainty at some measured-move-distant support/resistance. | `brooks_ranges p.21`; `brooks_trends p.16` | moderate for the 50% baseline (structural); weak for the 60–70% figure |
| Always-in | The position you would be holding if you were forced to be in the market at every moment. It is the output of "if I had to pick a side right now, would I be confident?" Brooks: it almost always requires a **spike** in the new direction before traders are confident. Most traders should trade only in the always-in direction. | `brooks_trends pp.15, 113–114, 323` | moderate |
| Always-in flip | A single strong opposite trend bar that reverses many prior closes and lows can flip it. The strongest holders hold pullbacks and exit only when they think the side has flipped; after a flip, with-trend pullback setups (H1/H2) in the old direction stop working. | `brooks_trends p.130` | weak (no objective bar count is given) |
| Spike phase | The impulse: consecutive trend bars, large bodies, little overlap, small tails, urgency. Functionally a breakaway gap. Ends at the first pause or pullback bar, by definition. A spike on one timeframe is a steep tight channel on a lower one. | `brooks_trends pp.276, 357–359` | strong (definitional) |
| Channel phase | The follow-through: less momentum, two-sided trading, overlapping bars, opposite-colour bars, constant appearance of reversing. Every trend is in either spike or channel mode at all times. A channel is a sloping trading range — and a bull channel is a bear flag. | `brooks_trends pp.358–361` | strong (definitional) |
| Spike and channel trend | The most common trend form: spike → brief pullback (gap test) → channel → channel breaks against the trend → market corrects to **the start of the channel** and tries to form a double-bottom flag there. Almost every bull spike-and-channel ends this way. | `brooks_trends pp.357–361` | moderate |
| Tight channel | Trend line and trend channel line close together; pullbacks last 1–3 bars. **The worst place to trade counter-trend** — pullbacks are too small to pay. Also a poor place to enter with-trend *late* on a stop, because the entry lands at the top of a weak channel with a far stop and low probability. | `brooks_trends pp.26, 251–254, 323–324` | moderate |
| Micro channel | The extreme tight channel: 2–10 bars, most touching both lines, zero or one to two tiny pullbacks. The more bars in it, the more likely the **first** break against it fails and becomes a with-trend H1/L1 entry. It is a sloping tight range and has a magnetic pull that limits breakouts to a bar or two. | `brooks_trends pp.281–284` | moderate |
| Broad channel / stairs | Three or more trending swings that look like a mildly sloping range. Every breakout to a new extreme is followed by a pullback back *through* the breakout point, so consecutive swings overlap. Two-way trading — the one trend type where counter-trend entries are legitimate. | `brooks_trends pp.463–464` | moderate |
| Shrinking stairs | Each new breakout extends less beyond the prior swing point than the one before. Waning momentum; frequently precedes a two-legged reversal and trend-line break. | `brooks_trends pp.25, 463–464` | weak |
| Trending trading range day | Range → breakout → second range, at a higher/lower level. Opening range about one third to one half of recent daily range; expect a breakout and roughly a doubling of the range. The pullback after the second range forms usually tests, and often re-enters, the first range. Most reversal days start as this. | `brooks_trends pp.391–394` | moderate |
| Trend from the open / small pullback trend | The strongest form: one extreme forms in the first few bars and holds all session; pullbacks stay tiny (Brooks: 10–30% of average daily range). Only ~20% of days. About two-thirds of small-pullback days produce one late pullback ~150–200% the size of all earlier ones, then resume. | `brooks_trends pp.415–418` | weak (specific percentages are unmeasured assertions) |
| Open-Drive | Dalton's early trend-day tell: the market opens and drives one way without returning through the opening range. Usually foreshadows a trend or normal-variation day; the extreme left behind usually holds all day. Return through the opening range = the read is void, exit. | `dalton_mind_over_markets pp.83–85` | moderate |
| Open-Rejection-Reverse | Opens, goes one way, meets opposite activity strong enough to push back through the opening range. Lower conviction; initial extreme holds less than half the time; **probability of a trend day is low** — expect two-sided trade. | `dalton_mind_over_markets pp.88–89` | moderate |
| Initiative vs responsive activity | Initiative buying = buying at or above the prior session's value area; responsive buying = buying *below* value. Initiative activity signals conviction; it is the location relative to prior value, not the direction of the move, that makes it initiative. | `dalton_mind_over_markets pp.65–66` | strong (definitional) |
| Impulse–retracement–impulse | Grimes' fundamental pattern, fractal at every scale. A trend is intact while each new setup leg shows momentum at least comparable to previous legs in the same direction, and while pullbacks show *no* strong counter-trend momentum. | `grimes_art_science pp.67–71, 172` | moderate |
| High/Low 1, 2, 3, 4 | Counting pullback attempts. In a bull flag, a bar whose high exceeds the prior bar's high is a High 1; after a subsequent lower high, the next bar to exceed the prior bar's high is a High 2; then High 3 (= wedge bull flag) and High 4. Mirror for Low 1–4 in bears. **H1/L1 is only valid inside a strong spike; H2/L2 is the standard channel entry.** | `brooks_trends pp.19–20, 321, 341` | moderate |
| Second entry | The second setup within a few bars based on the same logic as the first. Brooks: almost always more likely to work than the first, because the first attempt against strong momentum fails and its failure *is* the second signal. Corollary: **if the second entry offers a better price than the first, be suspicious — good fill, bad trade.** | `brooks_trends pp.23–24, 209–211` | moderate for reliability; weak for the "better price = trap" heuristic |
| Breakout pullback | A 1–5 bar pullback within a few bars of a breakout, taken as the resumption setup rather than the failure. Brooks calls the pullback after a flag breakout one of the most reliable setups in the book. | `brooks_trends p.15`; `brooks_ranges pp.54–55` | moderate |
| Moving-average gap bar / 20-gap-bar | A bar that does not touch the 20 EMA. The first pullback in a strong trend that produces one is usually followed by a test of the trend extreme. After 20+ consecutive bars without touching the MA, the eventual touch sets up a test of the extreme. | `brooks_trends pp.20–21, 309` | weak |
| Complex (two-legged) pullback | Pullback made of two distinct counter-trend legs — itself a complete impulse-retracement-impulse on the lower timeframe. Common in mature trends; kills traders who only model simple pullbacks; the two legs tend to be similar length (AB=CD), which gives a projectable second-leg terminus **and a clean stop below the whole structure**. | `grimes_art_science pp.182–186`; `brooks_trends pp.351–352` | moderate |
| Trend channel line overshoot | Price penetrates the line drawn on the far side of the trend. A fade signal only when it *reverses*, and better on the second penetration. Equivalent in practice to a wedge/three-push top. Brooks' tell: **if you find yourself repeatedly redrawing the trend channel line steeper, you are on the wrong side.** | `brooks_trends pp.27, 241–244` | moderate for the "keep redrawing" heuristic; weak for the fade edge |
| Measured move | Project the height of the completed structure from the breakout/pullback point. Variants: spike height projected from the channel start; AB=CD from the pullback low; range height doubled after a trending-trading-range breakout; micro measuring gap (non-overlap of the bars either side of a strong trend bar). Grimes: no mystical force — it is just "this market's typical swing size at its current volatility." | `brooks_trends pp.21, 357, 392`; `grimes_art_science pp.176–177` | moderate (as an *expectation zone*, not a level) |
| Climax / exhaustion | A move that has gone too far too fast and reverses. Brooks: an unusually large trend bar or two after a protracted trend is exhaustion, not a new leg, and typically starts a two-legged pullback of ~10 bars. Grimes: accelerated rate, large ranges, "free bars" fully outside the channel, many closes at the extreme, after ≥2 prior legs, at a new extreme for the timeframe. | `brooks_trends pp.15, 92, 417`; `grimes_art_science pp.71–79` | moderate |
| Climax rule of restraint | Grimes, explicitly: **do not enter pullbacks following a potential climax**, and a climax by itself is not enough to justify a counter-trend position — it is a reason to lighten or exit with-trend risk. Also: several consecutive bars closing on their absolute highs statistically indicates short-term exhaustion, not strength. | `grimes_art_science pp.40, 74, 76` | moderate |
| Trader's equation | Take the trade only when P(win)×reward exceeds P(loss)×risk. The unknowable term is P. Brooks' working convention: assume 50% when unsure, 60/40 when confident. Consequence: with a 2-point stop and 60% confidence, taking profit before +2 points loses money over time. | `brooks_trends pp.26, 325–326` | strong (arithmetic); the P inputs are weak |
| Scalp vs swing incompatibility | A scalper needs ~70%+ win rate, which almost nobody sustains. Swing trading wins under 50% of the time and depends on the large winners. The named killer is **starting with one plan and managing with the other** — scalping out of a swing, or holding a scalp because the last one ran. | `brooks_trends pp.24, 324–325` | moderate |
| Late/missed entry rule | If you look at the chart and conclude you would still be holding the swing portion, enter at market — but only the size you would still be holding, with the same trailing stop. Entering late with the original stop is arithmetically identical to still holding. | `brooks_trends p.213` | strong (arithmetic) |
| Triple screen | Elder: pick your working timeframe, immediately step up ~5× for a strategic long/short/stand-aside decision using trend-following tools, return to the working timeframe and use an oscillator to enter *with* the higher-timeframe trend, then fine-tune the order. A second-screen signal against the first screen may **close** a position, never open one. | `elder_trading_room pp.138–144` | moderate |
| SafeZone trailing stop | Elder: define noise in an uptrend as the part of each bar that pokes below the prior bar's low. Average those penetrations over a look-back, multiply by ~2, subtract from the prior bar's low. Ratchet one direction only. | `elder_trading_room pp.182–184` | strong (fully mechanical); its optimality is untested |
| Propulsion entry | Carter's practical trend-continuation template: require 8 EMA above 21 EMA, buy the pullback **to** the 8 EMA, stop at the 21 EMA or a fixed % of price (whichever is further), move stop to the 21 EMA once a "watermark" profit is reached, then trail the 21 EMA. Optionally require the same 8/21 alignment on the timeframe above. | `carter_mastering pp.440, 460` | moderate (rule is precise; edge untested) |
| Pivot behaviour distinguishes trend from chop | Carter: on a trending day price reaches a pivot, consolidates 15–20 minutes, and continues — so buy the first pullback **to the violated pivot**. On a choppy day price reaches the pivot, loiters, and drifts back — so fade it. The pivot reaction is itself the day-type classifier. | `carter_mastering pp.145, 154` | moderate |

---

## Distilled rules

1. **Do not declare a trend from direction alone.** Require both Brooks conditions on the decision
   timeframe: a break of the prior trend line / prior range boundary, *and* trending swings in the
   new direction. If only one is present, treat the market as a range and do not use any rule below.
   (`brooks_trends p.309`)
2. **Add Dalton's mechanical confirmation on H1 or M30:** in an up-trend, require that each closed
   bar's low is at or above the prior bar's low. Declare one-timeframing over when a bar closes
   having traded below the prior bar's low by more than a defined noise tick. Do not use bars
   shorter than M30 for this test. (`dalton_markets_momentum p.120`)
3. **Classify the trend before choosing an entry method.** Compute channel width (trend-line to
   trend-channel-line distance, in ATR) and pullback depth. Tight/micro → with-trend only, no
   fades. Broad/stairs → two-sided permitted. Trending trading range → with-trend into the
   measured move, then switch to range logic. (`brooks_trends pp.253, 393, 463`)
4. **Never take a counter-trend entry in a tight or micro channel.** The pullbacks do not travel
   far enough for the trade to pay, regardless of how overdone it looks.
   (`brooks_trends pp.253, 360`)
5. **Also do not take a late with-trend *stop* entry near the far side of a tight channel.** That
   is a low-probability entry with a distant structural stop. Either wait for a pullback to the
   20 EMA, or enter with reduced size on the pullback side. (`brooks_trends pp.323–324`)
6. **In the spike phase, take the first pullback (H1/L1); in the channel phase, require the second
   (H2/L2).** An H1 is only a buy inside a strong bull spike and only if there has been no buy
   climax. Do not use the label "Low 1" as a short signal inside a strong bull trend — that count
   belongs to ranges and bear trends. (`brooks_trends pp.321, 341`)
7. **Prefer second entries to first entries after strong opposite momentum.** If the preceding 4+
   bars are strong trend bars against your intended direction, do not take the first signal; wait
   until the trend shows a bar or two of renewed movement, then take the second attempt. If no second entry forms,
   take nothing. (`brooks_trends pp.209–211`)
8. **Reject a second entry that offers a better price than the first** unless there is independent
   confirmation. Good fills on second signals are a trap tell. (`brooks_trends p.209`)
9. **Treat the breakout pullback as the primary breakout entry, not the breakout itself.** Entering
   on the breakout of a range is a low-probability trade; entering on the 1–5 bar pullback that
   holds above/below the breakout point is one of the most reliable setups.
   (`brooks_trends p.393`; `brooks_ranges pp.54–55`)
10. **Require a genuine impulse leg before calling any pullback tradable.** The leg that set up the
    pullback must show momentum at least comparable to prior legs in the same direction, and must
    not have produced momentum divergence. (`grimes_art_science pp.71, 172`)
11. **Abort the with-trend thesis the moment sharp counter-trend momentum appears on a pullback.**
    A pullback that breaks the established trend geometry and produces a new momentum extreme
    against the trend means the trend is broken until further notice — stop looking for with-trend
    entries. (`grimes_art_science p.70`)
12. **Do not enter a pullback that follows a potential climax.** Require either (a) a subsequent
    complex/two-legged consolidation that works off the overextension, or (b) a fresh impulse leg,
    before re-arming with-trend entries. (`grimes_art_science pp.74, 184`)
13. **Detect climax mechanically:** ≥2 prior legs in the same direction, a new extreme for the
    timeframe, accelerating slope, bar ranges well above recent average, one or more "free bars"
    entirely outside the volatility channel, and several closes at the bar extreme.
    (`grimes_art_science pp.76, 40`)
14. **Use the 20 EMA pullback as the highest-quality standard entry** in a channel: H2 (or L2) with
    a with-trend signal bar occurring at the moving average, and not close to the far side of the
    channel. Accept that this setup is infrequent, and accept missing trends rather than degrading
    the filter. (`brooks_trends pp.254, 321`)
15. **Add Carter's moving-average version as an alternative, fully-specified entry:** 8 EMA above
    21 EMA on the decision timeframe (optionally also on the timeframe above), buy the pullback to
    the 8 EMA, stop at the 21 EMA or a volatility floor, whichever is further.
    (`carter_mastering pp.440, 460`)
16. **After a breakout on a trending-trading-range day, set the first target at the measured move
    (range height projected from the breakout) and switch to range logic on arrival.** Take profit
    into strength rather than waiting for a swing-low stop to be hit, because in a forming upper
    range those stops usually get hit. (`brooks_trends pp.393–394`)
17. **Set the stop by structure, not by preference:** one tick beyond the signal-bar extreme for a
    standard pullback entry; beyond the whole two-legged structure for a complex pullback; beyond
    the start of the spike for a spike-phase entry (and reduce size proportionally so the currency
    risk is unchanged). (`brooks_trends pp.323, 325`; `grimes_art_science p.186`)
18. **Do not place the stop exactly where everyone else places it.** Offset it beyond the obvious
    level by a small randomized amount, and size down to keep currency risk constant.
    (`grimes_art_science p.175`)
19. **Trail by structure, one direction only.** Each time a new trend extreme prints, move the stop
    to just beyond the most recent higher low (bull) / lower high (bear). Never loosen a stop.
    (`brooks_trends pp.326–327`; `elder_trading_room pp.145, 183`)
20. **Do not move to breakeven early in a tight channel or a small-pullback trend.** Pullbacks in
    those regimes routinely reach breakeven and then resume; a breakeven stop converts a winner
    into a missed trend. Trail below swing lows instead. (`brooks_trends p.416`)
21. **Implement the trailing stop with a noise filter, not a fixed distance.** Elder's SafeZone:
    average the downside penetrations of the prior bar's low over the last N bars, multiply by ~2,
    subtract from the prior bar's low, ratchet up only. (`elder_trading_room pp.183–184`)
22. **Decide scalp or runner before entry and never swap mid-trade.** If the plan was a runner, do
    not take the scalp profit; if the plan was a scalp, take it. Most losses attributed to bad
    entries are actually plan-switching. (`brooks_trends pp.324–325`)
23. **Do not take profit before the trade has travelled at least 1R** unless you can justify a
    probability near 80%. With a 60% estimate and a 1R stop, a sub-1R target is negative
    expectancy. (`brooks_trends pp.325–326`)
24. **Scale in with the trend (pressing), not against it, unless the total risk is pre-computed.**
    If scaling against the position, the size of every tranche must be planned in advance so that
    total currency risk equals a normal single trade. Default for this bot: **do not average
    down.** (`brooks_trends p.322`)
25. **Enter late rather than skip a confirmed trend — but only at swing size.** If the always-in
    read is unambiguous and you would still be holding a runner, enter at market with the runner's
    size and the runner's trailing stop, not with full initial size.
    (`brooks_trends p.213`)
26. **Stop trading a trend when any of these fire:** measured-move target reached with weakening
    structure; climax signature; trend-channel-line overshoot followed by a reversal bar; a break
    of the channel followed by a lower high (bull) that fails to reclaim; one-timeframing ceasing
    early in the session; or value areas ceasing to migrate.
    (`brooks_trends pp.242, 358, 393`; `dalton_markets_momentum pp.123, 134`; `dalton_mind_over_markets p.74`)
27. **After a channel breaks against the trend, do not enter on the breakout.** Wait for the
    pullback to a lower high (after a bull channel break) and enter there; and expect the
    correction to run to the *start of the channel*, where a double-bottom flag often forms.
    (`brooks_trends pp.358, 361`)
28. **Never fade a one-timeframing session.** Dalton's stated single largest error of short-term
    traders. Explicitly forbid the "revenge fade" after missing a trend leg.
    (`dalton_markets_momentum pp.54–55, 122`)
29. **Do not wait for lagging confirmation on a potential trend day.** Dalton: waiting for
    confirmation is exactly how traders miss the 15% of days that pay. Use closed structure and
    location (Open-Drive, initiative activity relative to prior value) instead.
    (`dalton_markets_momentum p.26`; `dalton_mind_over_markets pp.83–85`)
30. **Apply Elder's screen-one veto:** if the analysis timeframe is not clearly trending, "stand
    aside" is the correct output — do not drop a timeframe to manufacture a signal. A lower
    timeframe signal against the analysis timeframe may only close a position.
    (`elder_trading_room pp.141, 144`)
31. **Cap position risk at 2% of equity, and skip the trade if the structural stop implies more.**
    Do not tighten the stop to make the trade fit. (`elder_trading_room p.145`)
32. **Stop for the session after two consecutive losses in the same trend playbook.**
    (`carter_mastering p.155`)
33. **Never open a new with-trend position in the last portion of the session that cannot reach
    its first target.** Carter's version: no new positions after a fixed cutoff, existing positions
    managed to a hard flat time. (`carter_mastering pp.154–155`)
34. **Do not enter in the seconds around a scheduled release.** Brooks: machines process the data
    within a second and hold a decisive edge; wait one to two closed bars for the always-in read
    to resolve, then enter with it. (`brooks_trends p.418`)
35. **Recompute the trend classification after every closed decision bar.** Trend type is not a
    label assigned once per session; spike→channel→range transitions are the normal life cycle.
    (`brooks_trends pp.276, 358`)

---

## Worked examples

All examples are XAUUSD. "Decision bar" = the last **closed** bar on the stated timeframe;
execution is at the next bar's open. Session times are UTC.

### 1. Spike-and-channel London trend — first pullback in the spike
| | |
|---|---|
| **Setup** | 08:00–08:30 UTC: four consecutive M15 bull bars, each body >60% of range, tails small, consecutive lows at or above the prior bar's close, price breaks the Asia session high. Fifth M15 bar closes with a low below the fourth bar's low (first pullback bar). H4 swing structure already showed a higher high and higher low. |
| **Decision** | **Open long** on the next M15 open, i.e. a High 1 in a bull spike. |
| **Invalidation** | A closed M15 below the pullback bar's low. Reduce size so that currency risk equals a normal trade despite the wide stop (Brooks: in the spike phase the stop belongs beyond the start of the spike). |
| **Why** | Spike phase; H1 is a valid entry only inside a strong spike and only absent a buy climax. Two-condition trend test satisfied on H4. |
| **Evidence** | moderate (`brooks_trends pp.276, 321, 357`) |

### 2. Channel phase — the standard H2 at the moving average
| | |
|---|---|
| **Setup** | 13:00–15:00 overlap. Bull channel on M15: overlapping bars, several bear bodies, pullbacks lasting 3–6 bars, channel width ≈ 2.5× ATR(14). Price falls to the 20 EMA; a bar makes a higher high (H1), a later bar makes a lower high, then a bar closes above the prior bar's high with a bull body — H2. The H2 entry sits in the lower half of the channel, not near the trend channel line. |
| **Decision** | **Open long** next bar open. Target 1 = prior swing high; target 2 = AB=CD measured move from the pullback low. |
| **Invalidation** | Closed M15 below the H2 signal bar's low, offset a few ticks beyond the obvious level. |
| **Why** | Brooks names H2-at-the-MA-not-near-the-top the most reliable channel buy; Grimes' conservative and MMO targets. |
| **Evidence** | moderate (`brooks_trends pp.254, 321`; `grimes_art_science pp.176–177`) |

### 3. Tight channel — SKIP the fade, and SKIP the late chase
| | |
|---|---|
| **Setup** | M5 bear channel through London: 14 bars, most touching both the trend line and the trend channel line, no pullback larger than 3 bars, price 4 ATR below the 20 EMA. Two bull reversal bars have printed and both failed within one bar. |
| **Decision** | **SKIP both directions.** No short (the entry sits at the bottom of a micro channel with a far stop and low probability of reaching 1R before a pullback); no long (pullbacks in a micro channel do not travel far enough to pay, and the "reversal bar" quality is exactly the trap Brooks describes). |
| **Invalidation of the skip** | A closed M5 back above the micro-channel trend line followed by a *second* attempt that holds — i.e. wait for a second signal, not the first. |
| **Why** | Micro channel: the more bars in it, the more likely the first break against it fails; and a tight channel is simultaneously the worst counter-trend venue and a bad late with-trend venue. |
| **Evidence** | moderate (`brooks_trends pp.253, 282–284, 323`) |

### 4. Broad channel / stairs — the one place two-sided trading is licensed
| | |
|---|---|
| **Setup** | H1 bear stairs across two sessions: three successive breakouts to new lows, each followed by a rally that goes back **above** the prior breakout point but stays below the prior swing high. Last two breakouts extended ~$6 and ~$5.50 beyond the previous swing low; rallies have been ~$5–6. |
| **Decision** | **Open short** on a rally of $4–5 into the bear trend line (with-trend, primary), and permit a **counter-trend long scalp** at ~$4–5 below the most recent swing low, near the trend channel line, sized smaller and targeted at the trend line. |
| **Invalidation** | For the short: an H1 close above the most recent swing high. For the long scalp: a close $1.5 beyond the projected breakout extension — i.e. the "stairs" measurement failing. |
| **Why** | Stairs = broad channel with genuine two-way trade; Brooks explicitly describes traders measuring how far breakouts run and fading subsequent ones by that distance. This licence does **not** transfer to tight channels. |
| **Evidence** | moderate for the structure, weak for the fade distances (`brooks_trends pp.463–465`) |

### 5. Trending trading range day — take profit at the measured move, then flip logic
| | |
|---|---|
| **Setup** | Asia + early London build a range of ~$9 while ADR(20) is ~$24 (≈37% of ADR). At 13:10 UTC price breaks the range high on two M15 bull bars and pulls back to hold above the breakout point. |
| **Decision** | **Open long** on the breakout pullback. **First target = range high + $9** (measured move). On arrival, if momentum has weakened (overlapping bars, bear bodies, tails at highs), take profit into strength rather than trailing a swing-low stop. |
| **Invalidation** | Closed M15 back inside the original range below the breakout point. |
| **Why** | Brooks: opening range one third to one half of recent daily range → expect a breakout and roughly a doubling of the day's range, then a second range. Trailing under swing lows in a forming second range gets stopped out. |
| **Evidence** | moderate (`brooks_trends pp.391–394`) |

### 6. Trend day recognised early via Open-Drive + initiative location
| | |
|---|---|
| **Setup** | London open 08:00. Price opens **above** the prior session's value area and drives up for the first three M30 bars without trading back through the first bar's range. Each M30 low is at or above the prior M30 low (one-timeframing up). |
| **Decision** | **Open long** at the first M15 pause/pullback rather than waiting for further confirmation. Plan for a runner; do not scalp out. |
| **Invalidation** | Price trades back through the opening M30 range → the Open-Drive read is void, exit. Separately, one-timeframing ceasing before mid-session materially raises the odds the day turns rotational — tighten and stop adding. |
| **Why** | Open-Drive is Dalton's strongest opening type; opening above prior value makes the buying initiative; waiting for confirmation is exactly how trend days are missed. |
| **Evidence** | moderate (`dalton_mind_over_markets pp.65–66, 83–85`; `dalton_markets_momentum pp.26, 122, 134`) |

### 7. WAIT — strong opposite momentum, take the second signal only
| | |
|---|---|
| **Setup** | H4 always-in short. On M15, five consecutive bear trend bars into a session low, then a bull reversal bar with a long lower tail forms right at an H1 support level. This is a first counter-trend signal against strong momentum — and simultaneously, the with-trend short entry below it looks late. |
| **Decision** | **WAIT.** Do not buy the first reversal bar (too much bear momentum to fade). Do not short at the low either. Let the bear trend resume for a bar or two; if a *second* bull attempt forms and holds, that is the tradable long; if instead the bears resume and produce an L2 at the 20 EMA, that is the tradable short. |
| **Invalidation** | Neither second signal appears within ~10 bars → no trade at all (Brooks: waiting for a second entry that never came is what averted the loss). |
| **Why** | Second-entry principle; "before taking a counter-trend trade it is always better to see evidence in the preceding bars that the other side could move more than a couple of ticks beyond the prior bar." |
| **Evidence** | moderate (`brooks_trends pp.209–211`) |

### 8. WAIT/SKIP — climax signature vetoes an otherwise perfect pullback
| | |
|---|---|
| **Setup** | Three completed up legs on H1. The third leg accelerates: bar ranges 2.5× the 20-bar average, two bars close entirely above the upper volatility channel ("free bars"), four consecutive closes within 10% of the bar high, new high of the month. Price then pulls back three bars to the 20 EMA and prints a clean bull signal bar — textbook H2. |
| **Decision** | **SKIP the H2.** The climax signature vetoes it. Do **not** short either — a climax alone is not a counter-trend entry. Re-arm with-trend entries only after either a complex two-legged consolidation holds, or a fresh impulse leg prints. |
| **Invalidation of the skip** | A two-legged consolidation that holds above the first leg's terminus, followed by a with-trend trigger — that is a legitimate re-entry. |
| **Why** | Grimes states both halves explicitly: do not enter pullbacks after a potential climax; and complex consolidations can rehabilitate an area where simple pullbacks must be avoided. |
| **Evidence** | moderate (`grimes_art_science pp.74, 76, 184–185`) |

### 9. FAILURE — the H2 that fails, and why the book says so
| | |
|---|---|
| **Setup** | H4 bull. On M15 a High 2 triggers at the 20 EMA. Two bars later price closes below the H2 signal bar low and the stop is hit. **Then** a third push down forms a wedge shape and reverses up with a strong bull bar. |
| **Decision after the loss** | This is the *expected* failure mode, not a broken method: Brooks describes traders who take the H2 at half size precisely because it may fail and evolve into a **High 3 / wedge bull flag**, which is a stronger second signal. Correct action: **re-enter at full size on the H3 trigger.** |
| **Invalidation** | If the H3 also fails, or if the move down produced a new momentum extreme against the trend, the trend premise is dead — stand aside; Grimes: assume the trend is broken until further notice. |
| **Why the first entry failed** | The H2 was a first-of-its-kind signal at that price; the market had not yet exhausted sellers. The failed H2 *is* the setup for the H3. Also: sizing half on a questionable signal and full on the confirmed second signal is the corpus's explicit prescription. |
| **Evidence** | moderate (`brooks_trends pp.327, 341`; `grimes_art_science p.70`) |

### 10. FAILURE — the breakout-pullback that becomes a failed breakout
| | |
|---|---|
| **Setup** | NY session. Price breaks the London high on one M15 bull bar, then a pullback holds above the breakout point — apparently a breakout pullback long. It triggers. Within three bars price closes back below the breakout point, and then below the pullback low. |
| **What went wrong** | Brooks' own framing: whether you call the move a "pullback" or a "failed breakout" is a *prior*, not an observation — the identical price structure supports both readings and the label is chosen by context. The context that was missing: the breakout bar was a single bar with a large tail into a tight range, and the range had a magnetic pull that tends to drag breakouts back. Roughly 80% of breakout attempts from a range fail, on Brooks' own (unmeasured) estimate. |
| **Correct handling** | Take the loss at the structural stop; then look for the *failed failure* — if price re-crosses back above the breakout point within a few bars, that is a second signal and a more reliable long than the first. |
| **Evidence** | weak for the 80% figure, moderate for the failed-failure logic (`brooks_trends pp.15, 17–18, 309, 393`) |

### 11. Late entry into a confirmed trend — size, not skip
| | |
|---|---|
| **Setup** | You have no position. M15 shows nine of the last twelve bars as bull trend bars, price is 3 ATR above the 20 EMA, no climax signature (bars are not oversized, no free bars). Had you taken the original entry three hours ago you would still be holding a runner. |
| **Decision** | **Open long at market at the next open**, but only the size you would still be holding as a runner, with the runner's trailing stop (structure-based, e.g. below the most recent higher low). |
| **Invalidation** | The same trailing stop you would already be using. |
| **Why** | Brooks: entering late while using the original stop is arithmetically identical to holding the runner. There is no accounting difference between "house money" and new money. |
| **Evidence** | strong for the arithmetic, moderate for the entry (`brooks_trends p.213`) |

### 12. Carter's pivot/propulsion hybrid on a trending session
| | |
|---|---|
| **Setup** | Daily 8 EMA above 21 EMA on XAUUSD. During London, price penetrates the daily pivot to the upside and travels at least 25% of the distance toward R1. It then retraces to the pivot. |
| **Decision** | **Open long** just above the pivot. First target R1, second target R2, scaling half at each. Initial stop: 21 EMA on the working timeframe, or a volatility floor, whichever is further. Once the first target is hit, move the stop to just below the entry pivot. |
| **Invalidation** | A closed bar below the pivot by more than the "just in front of" offset, or a rejection at R3 (Carter always fades moves to R3/S3). |
| **Why** | The pivot reaction is Carter's own trend/chop classifier: on trending days price consolidates at a pivot and continues; on choppy days it drifts back. |
| **Evidence** | moderate (`carter_mastering pp.145, 154–155, 440`) |

### 13. SKIP — the corpus's own tests disagree
| | |
|---|---|
| **Setup** | H1 shows nine higher highs and higher lows; a with-trend pullback setup triggers. But the H4 volatility regime has collapsed (ATR at a 60-day low), the "trend" consists of bars whose bodies are under 25% of range, no bar has broken a prior trend line by more than noise, and the D1 value areas over the last four sessions overlap almost completely. |
| **Decision** | **SKIP.** The two-condition test fails (no trend-line break of significance); Dalton's value-migration test fails (overlapping value areas = balancing, not trending). |
| **Why this matters** | This is the exact configuration Chan's data describes: a series that looks momentum-ish at one horizon while a formal trending test (Hurst 0.44, VR failing to reject random walk) says otherwise. Swing-counting alone is the weakest of all the trend tests and is the one most likely to be curve-fit noise. |
| **Evidence** | strong for the veto's construction (it is a conjunction of definitional tests); the underlying skepticism is `chan_algo_trading pp.154–155` and `dalton_mind_over_markets p.74` |

---

## Learning outcome

After this topic the model must, on any closed bar, (1) **output a trend verdict of
`none / spike / tight-channel / broad-channel / trending-range / exhausted` on a named timeframe**,
justified by the two-condition Brooks test plus a one-timeframing check, rather than by direction
alone; (2) **select the entry method that the classification licenses and refuse the ones it
forbids** — specifically refusing counter-trend entries in tight and micro channels, refusing
late with-trend stop entries at the far side of a tight channel, refusing any pullback entry that
follows a climax signature, and refusing first entries against strong opposite momentum in favour
of second entries; (3) **place the stop by structure and trail it one-directionally with a
noise-scaled filter**, and size so that the currency risk is constant regardless of stop distance;
and (4) **name the exit condition that will end the trend trade before entering it** — measured
move, climax, channel break with lower high, or cessation of one-timeframing. The model must
additionally be able to state, when asked why a with-trend rule is only labelled `moderate`, the
specific Chan results that cap it.

---

## Implementation

Everything below is computable from closed OHLCV bars plus a UTC session clock. Fields flagged
**[GAP]** need data or judgement the bot may not have.

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `atr` | ATR(14) | each TF | Baseline unit for every distance below; never use fixed dollar amounts. |
| `ema20`, `ema8`, `ema21` | Standard EMAs on closes | M5–H4 | Brooks uses 20 EMA; Carter uses 8/21. Compute all three. |
| `swing_high[i]`, `swing_low[i]` | Bar whose high ≥ neighbours' highs (resp. low ≤) — confirmed only when the bar *after* it has closed | each TF | One-bar lag is unavoidable and correct; no lookahead. |
| `trending_swings` | Last two confirmed swing highs rising AND last two confirmed swing lows rising (bull); mirror for bear | H1/H4 | Half of the Brooks two-condition test (`brooks_trends p.309`). |
| `trendline_break` | Line through the last two confirmed swing lows (bull) extended forward; break = a **close** beyond it, plus a filter | H1/H4 | Murphy's filters: price filter (a % of price) or two-day/two-bar rule (`murphy_ta p.81`). Use a filter of 0.25×ATR or 2 closed bars. |
| `trend_exists` | `trendline_break_of_prior_structure AND trending_swings` | H1/H4 | If false, all with-trend rules are disabled. |
| `one_tf_up` / `one_tf_down` | Every closed bar's low ≥ prior bar's low (up) / high ≤ prior high (down), over the last N bars | M30 or H1 only | Dalton says shorter bars degrade the read (`dalton_markets_momentum p.120`). Break threshold = 1 tick-noise unit, not 0. |
| `one_tf_ceased_at` | Index of first bar violating `one_tf_*` | M30 | Early cessation (first third of session) → raise odds of rotation, stop adding. |
| `spike_flag` | ≥3 consecutive bars, same direction, body ≥ 0.6×range, consecutive-bar overlap ≤ 0.25×range | M5/M15 | Definition of the spike phase (`brooks_trends pp.276, 307–308`). |
| `channel_width_atr` | (trend channel line − trend line) at the current bar, ÷ ATR | M15/H1 | **The single most important classifier.** < ~1.5 ATR ⇒ tight; > ~3 ATR ⇒ broad. Thresholds are a free parameter — flag as fitted. |
| `micro_channel_len` | Count of consecutive bars each touching (within 0.1×ATR of) both the trend line and the trend channel line | M5/M15 | ≥5 ⇒ expect the first opposite break to fail (`brooks_trends p.282`). |
| `max_pullback_pct_adr` | Largest retracement since the trend began ÷ ADR(20) | M5/M15 on the session | ≤0.3 ⇒ small-pullback trend; watch for one late pullback ~1.5–2× the prior max (`brooks_trends p.417`). |
| `high_low_count` | Running H1/H2/H3/H4 and L1/L2/L3/L4 counters, reset on each new trend extreme | M5/M15 | Reset logic must be explicit; the counts are only meaningful inside a flag or near a range boundary. |
| `second_entry_flag` | True when the current signal shares the same logic as a signal that triggered and failed within the last ~5 bars | M5/M15 | Drives rule 7. |
| `ma_gap_bar` | Bar whose high (bull pullback) is below the 20 EMA, or low above it | M5/M15 | Also count `consecutive_bars_not_touching_ema20`; ≥20 arms the 20-gap-bar setup. |
| `breakout_point` | Price of the level that was broken | any | Retain; the breakout-pullback test is "did the pullback hold above/below it". |
| `mmo_target` | Pullback-terminus + (length of the preceding impulse leg) | M15/H1 | Grimes AB=CD (`grimes_art_science pp.176–177`). Treat as a **zone** of ±0.25×ATR, not a level. |
| `range_mm_target` | Range high + range height (bull) after a trending-trading-range breakout | M15 | (`brooks_trends p.392`) |
| `climax_score` | Count of: ≥2 prior legs; new N-bar extreme; bar range ≥ 2×avg(20); ≥1 "free bar" fully outside a 2.25×ATR Keltner band around EMA20; ≥3 closes within 10% of bar extreme; slope acceleration | M15/H1/H4 | Score ≥4 ⇒ climax veto on all with-trend pullback entries (`grimes_art_science pp.71–79`). |
| `counter_momentum_break` | A pullback bar/leg producing a momentum extreme (e.g. MACD-fast or ROC) beyond anything seen in the trend's prior pullbacks | M15/H1 | Fires rule 11 — trend assumed broken (`grimes_art_science p.70`). |
| `tcl_overshoot` | Close or high beyond the trend channel line, followed by a closed reversal bar back inside | M15/H1 | Count overshoots; second overshoot ranks higher (`brooks_trends p.241`). |
| `tcl_redraw_count` | Number of times the trend channel line has had to be re-fitted steeper in the current trend | M15/H1 | Brooks' self-diagnostic: ≥2 redraws ⇒ suppress all counter-trend intent (`brooks_trends p.244`). |
| `always_in` | `+1` after a spike + trending swings up with no counter-momentum break; `-1` mirror; `0` otherwise | H1 driving M15 | **Judgement-heavy.** Implement as a hysteresis state machine requiring a spike to flip, per `brooks_trends p.15`; log every flip for audit. |
| `session` | Asia 00–07, London 08–13, Overlap 13–16, NY 16–21 UTC | clock | Used for: session-relative range, no-new-entry cutoff, and which "open" to test for Open-Drive. |
| `session_open_drive` | For the chosen session open: first 3 closed M30 bars all one-timeframing and price never trades back through bar 1's range | M30 | **[GAP]** Which session open counts as "the open" for gold is not answered by any corpus source. |
| `initiative_flag` | Current price vs prior session's value area (or, as a proxy, prior session's 70% volume/TPO band) | D1 context | Buying at/above prior value = initiative (`dalton_mind_over_markets p.65`). **[GAP]** needs volume-at-price; a TPO proxy from M30 bars is acceptable but not identical. |
| `value_migration` | Sign of the change in the last 3 sessions' value-area midpoints | D1 | Overlapping/reversing ⇒ balancing, veto trend rules (`dalton_mind_over_markets p.74`). |
| `stop_structural` | Signal-bar extreme (simple pullback) / whole two-leg structure (complex pullback) / spike origin (spike entry), offset by a small randomized jitter | entry TF | (`brooks_trends p.325`; `grimes_art_science pp.175, 186`) |
| `stop_safezone` | mean(downside penetrations of prior bar's low over last N bars) × 2, subtracted from prior bar's low; ratchet up only | entry TF | Elder (`elder_trading_room pp.183–184`). Use as the **trailing** stop once 1R is reached. |
| `position_size` | risk_budget ÷ (entry − stop) | — | Cap risk_budget at 2% of equity; if the structural stop implies more, **skip** (`elder_trading_room p.145`). |
| `plan_type` | `scalp` or `runner`, fixed at entry, immutable | — | Enforced in code; changing it mid-trade is a logged violation (`brooks_trends pp.324–325`). |
| `min_target_R` | 1.0 unless a probability estimate ≥0.8 is justified | — | Below 1R the trader's equation is negative at 60% (`brooks_trends p.326`). |
| `session_loss_stop` | 2 consecutive losses in the trend playbook ⇒ disable playbook for the session | clock | (`carter_mastering p.155`) |
| `news_blackout` | No entry within ±N minutes of a scheduled release; resume after 1–2 closed bars | clock | **[GAP]** requires an economic calendar feed the bot may not have (`brooks_trends p.418`). |
| `spread_cost_check` | Expected edge in ATR units must exceed (spread + swap) by a margin | — | **[GAP]** Grimes names "economically significant" as distinct from statistically significant (`grimes_art_science p.409`) but no corpus source computes it for spot gold. |

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Grimes:** trend-continuation trades are high-probability precisely because he claims a **verifiable statistical edge** exists for continuation (`grimes_art_science p.59`), and pullback continuation is among "the most reliable statistical tendencies in the market" (`p.77`). He presents no test. | **Chan:** on a single instrument, cross-horizon return correlations range from −0.014 to +0.41 with mostly non-significant p-values; the Hurst exponent is 0.44 and the Variance Ratio test *fails to reject a random walk*; and 12% of random return series matched only on kurtosis beat the momentum strategy's actual return (`chan_algo_trading pp.39, 154–155`). | Grimes' claim is treated as **unverified**. With-trend rules are capped at `moderate` and are gated behind *conjunctions* of definitional tests (trend-line break + trending swings + one-timeframing + value migration), not behind a single "the trend is up" reading. The bot logs, per trade, which conditions were true, so the base rate can eventually be measured on XAUUSD rather than assumed. |
| **Brooks:** counter-trend trading is "a losing strategy for most traders"; in a trend, successful traders are only long-or-flat / short-or-flat; beginners seeing a channel should trade with the trend only (`brooks_trends pp.15, 254, 323`). | **Brooks, same book:** on a stairs/broad-channel day traders can and should look for entries in both directions and scale into fades at measured distances (`p.463`); on a trending-trading-range day, fade big trend bars near the measured-move target (`p.393`); and a channel can be traded both ways when swings are broad (`p.254`). | Not an author-vs-author dispute but an unlabelled conditional, and the bot must make it explicit: **counter-trend permission is a function of `channel_width_atr` and pullback depth, not of conviction.** Fades are enabled only when channel width > ~3 ATR *and* the last two pullbacks each exceeded 1 ATR *and* price is within the measured-move target zone. In every other regime, fades are hard-disabled. |
| **Elder:** the analysis timeframe decides side, then you wait for the working-timeframe oscillator to fall before buying — "buying dips is safer than buying the crests of waves"; a signal against the analysis timeframe may only close a position (`elder_trading_room pp.143–144`). | **Brooks:** in the strongest trends the with-trend signal bars are *weak*, the good-looking bars are counter-trend, and you may have to enter at market without a setup; once four or more consecutive trend bars print, buy at least a small position at market instead of waiting for a pullback (`brooks_trends pp.214, 339–340`). **Dalton** independently: waiting for confirmation is how you miss trend days (`dalton_markets_momentum p.26`). | Split by regime. In `channel` mode, Elder's rule applies: wait for the pullback, never chase. In `spike` mode with `always_in` unambiguous and `climax_score` low, permit a **market entry at runner size with a runner's stop** (rule 25), which is Brooks' late-entry arithmetic rather than a chase. Never permit full-size market entry. |
| **Murphy:** retracements fall in predictable percentage bands — minimum ~33%, typical 50%, maximum ~66%; beyond two-thirds the odds favour a reversal rather than a retracement, and price then usually retraces the whole prior move (`murphy_ta pp.94–95`). | **Brooks:** the pullback after a spike can fall *below the bottom of the spike* and still be a pullback; the standard correction in a spike-and-channel goes to the **start of the channel**, which is a structural location with no fixed percentage; and a trading range that lasts many bars is simply a flag on a higher timeframe (`brooks_trends pp.358–361`). | Structure wins, percentage informs sizing. Compute both: use the structural level (breakout point, channel start, prior swing, MA) as the decision location; use the 38–62% band only as a **prior for where to expect the pullback to terminate**, i.e. to pre-position limit orders and to size the stop. A retracement beyond 66% is not an automatic reversal call — it must also produce `counter_momentum_break`. |
| **Grimes:** put stops *farther* from the pattern, never where everyone else puts them, and add a random jitter — because a tight stop's higher hit probability makes it a larger loss in expected-value terms; the tight-stop trader and the wide-stop trader have approximately the same expected payoff, but the tight-stop trader pays more in transaction costs and risks not being in the move (`grimes_art_science pp.175, 181`). | **Brooks:** stop is one tick below the signal bar's low, which in his examples is a specific and fairly tight distance (`brooks_trends p.325`). **Carter:** stops are fixed percentages of price — 4% for stocks, ¼% on a 60-minute index chart (`carter_mastering p.440`). | Use the **structural** stop (Brooks' location) but push it beyond the obvious level by a jittered offset (Grimes' correction), then size down so currency risk is unchanged — which is exactly the trade-off Grimes says is EV-neutral but cost-favourable. Carter's fixed percentages are used only as a **floor** (never stop tighter than X×ATR), never as the primary rule, because a percentage of price is not a percentage of volatility. |
| **Dalton:** markets trend only 20–30% of the time; ~15% of days show a trend (`dalton_mind_over_markets p.71`; `dalton_markets_momentum p.120`). | **Brooks:** every day has at least one spike-and-channel swing, and every trend is in either spike or channel mode at all times (`brooks_trends pp.358, 392`). | These are not in conflict once the timeframe is named — they are in conflict as *stated*, and the bot must never inherit an unscoped "the market is trending." Every trend verdict carries the timeframe it was computed on, and rules that consume it must declare which timeframe they require. Dalton's numbers apply to the D1/session scale; Brooks' to M5/M15. |

---

## Gaps

1. **No measured base rate for anything here, on any instrument.** Brooks' "80% of reversal
   attempts fail," "80% of breakouts fail," "60–70% during a trend," "70% or more likely" figures
   (`brooks_trends pp.309, 415`) are screen-experience assertions on RTH 5-minute Emini in
   2009–2011. Nothing in the corpus tests them. The bot must treat every one as a hypothesis to
   be measured on its own XAUUSD logs, not as a prior to trade on.
2. **Nothing addresses a 23-hour market.** The entire trend-day literature — Dalton's initial
   balance, open types, and one-timeframing; Brooks' trend-from-the-open, opening range, and gap
   patterns; Carter's 9:45/10:00/15:30 clock — assumes a single pit session with a real open and
   close. Gold has three plausible "opens" (Asia, London, NY) and no meaningful daily gap on most
   days. No source tells us which to use, or whether the "open forms one extreme in ~50% of days"
   statistic survives translation.
3. **No treatment of scheduled macro events for gold.** Brooks says machines have a decisive edge
   at the release and to wait a bar or two (`brooks_trends p.418`); nobody specifies how long,
   how the always-in read should be treated across the release, or whether a trend established
   pre-release survives it. CPI/FOMC/NFP are the dominant intraday trend generators in gold and
   the corpus is silent.
4. **No cross-market confirmation.** Gold's trend is largely a function of DXY and real yields.
   Murphy has intermarket material elsewhere, but nothing in the sources read here tells a trend
   trader in XAUUSD how to use a correlated instrument to confirm or veto a trend read.
5. **No net-of-cost analysis.** Grimes names the distinction between statistical and *economic*
   significance (`grimes_art_science p.409`) and then never computes it. Chan explicitly notes he
   omitted transaction costs from his example backtests (`chan_algo_trading p.15`). Nobody tells
   us whether a with-trend M5 pullback edge on spot gold survives spread plus swap. This is the
   most important missing number in the whole topic.
6. **`always_in` has no mechanical definition.** Brooks defines it by introspection ("if you were
   forced to pick a side, would you be confident?") and says a flip requires a strong bar that
   reverses "many" prior closes and lows (`brooks_trends pp.15, 130`). No bar count, no body-size
   threshold, no reversal-depth rule. Any implementation is a fitted parameter and must be flagged.
7. **Channel-width thresholds are invented.** The tight/broad distinction is the single most
   consequential classifier in this topic and no source gives a number for it. The 1.5/3 ATR
   thresholds above are the distiller's construction, not the corpus's.
8. **Nothing on regime detection for trend-edge decay.** Chan documents that momentum edges vanish
   for years after crises and that holding periods must shorten on an unpredictable schedule
   (`chan_algo_trading pp.169, 171`) — but gives no method for detecting when it has happened,
   other than watching the equity curve. The bot needs a live edge-decay monitor and the corpus
   supplies no design for one.
9. **No guidance on how many concurrent trend positions is coherent.** Elder's 2% rule is
   per-trade; nothing here addresses correlated with-trend exposure across timeframes on the same
   instrument, which is the realistic failure mode of a bot that trades M5, M15 and H1 pullbacks
   in the same direction simultaneously.

---

## JSONL seeds

```json
{"principle_id":"trend_two_condition_test","topic":"trend_trading","lesson":"A trend exists only when the prior trend line or range boundary has been broken AND the swings are now trending; direction alone is not a trend.","practice":"Before enabling any with-trend rule, evaluate both conditions on the named analysis timeframe and record which one is failing when the verdict is 'none'.","guardrail":"If either condition is absent, classify as range and disable all with-trend entries — do not drop a timeframe to find one.","evidence_label":"strong"}
{"principle_id":"trend_classify_before_entering","topic":"trend_trading","lesson":"The trend type — spike, tight channel, broad channel, trending trading range — determines which entries are legal, not just how confident to be.","practice":"Compute channel width in ATR and recent pullback depth on every closed decision bar, and select the entry method the classification licenses.","guardrail":"Never carry a classification across bars without recomputing; spike to channel to range is the normal life cycle.","evidence_label":"moderate"}
{"principle_id":"tight_channel_no_fade_no_chase","topic":"trend_trading","lesson":"A tight or micro channel is simultaneously the worst place to trade counter-trend and a bad place to enter with-trend late at the far side of the channel.","practice":"In tight channels take only pullback entries in the lower half (bull) or upper half (bear) of the channel, at or near the 20 EMA.","guardrail":"Hard-disable counter-trend orders whenever channel width is below the tight threshold, regardless of how overextended price looks.","evidence_label":"moderate"}
{"principle_id":"second_entry_with_trend","topic":"trend_trading","lesson":"After strong momentum against the intended direction, the first signal is a trap and the failure of that first signal is the real setup.","practice":"When the preceding four or more bars are strong trend bars against the trade, skip the first signal, wait for the move to resume a bar or two, and take only the second attempt.","guardrail":"If the second entry offers a better price than the first, treat it as a trap and stand aside; if no second entry forms, take no trade at all.","evidence_label":"moderate"}
{"principle_id":"climax_vetoes_pullback","topic":"trend_trading","lesson":"A pullback that follows a climax signature is not a with-trend entry, and the climax by itself is not a counter-trend entry either.","practice":"Score climax from leg count, new extreme, bar range versus average, free bars outside the volatility channel, and closes at bar extremes; veto with-trend pullbacks when the score is high.","guardrail":"Re-arm with-trend entries only after a two-legged consolidation holds or a fresh impulse leg prints — never immediately.","evidence_label":"moderate"}
{"principle_id":"no_fade_one_timeframing","topic":"trend_trading","lesson":"Fading a one-timeframing session is the single most costly recurring error identified in the profile literature, and the revenge fade after missing a leg is its worst form.","practice":"While each M30 bar's low holds at or above the prior bar's low, take only long setups; mirror for down sessions.","guardrail":"Block any counter-trend order while one-timeframing is intact, and log an attempted counter-trend order as a discipline violation.","evidence_label":"moderate"}
{"principle_id":"structural_stop_one_way_trail","topic":"trend_trading","lesson":"The stop belongs at the structural invalidation, offset from the obvious level, and moves in one direction only.","practice":"Place the initial stop beyond the signal bar, the whole two-legged pullback, or the spike origin as appropriate, with a small jitter, then trail using a noise-scaled ratchet once one unit of risk is earned.","guardrail":"Never tighten a stop to make an oversized trade fit the risk budget — skip the trade instead; never move to breakeven early in a tight channel or small-pullback trend.","evidence_label":"strong"}
{"principle_id":"plan_type_immutable","topic":"trend_trading","lesson":"Deciding scalp versus runner after entry destroys the expectancy of both; scalping needs a win rate almost nobody sustains, and swing trading needs the large winners it gives up.","practice":"Fix plan type at entry, enforce it in code, and require reward of at least one unit of risk before any profit is taken.","guardrail":"Taking profit below one unit of risk requires a justified probability estimate near 0.8, which by default is not available.","evidence_label":"moderate"}
{"principle_id":"late_entry_at_runner_size","topic":"trend_trading","lesson":"Missing the entry is not a reason to skip a confirmed trend, nor a licence to enter at full size — entering late with the runner's stop is arithmetically identical to still holding the runner.","practice":"When the trend read is unambiguous and no climax is present, enter at market with only the size that would still be open, using the trailing stop that position would carry.","guardrail":"Never enter late at full initial size, and never enter late while the climax score is elevated.","evidence_label":"strong"}
{"principle_id":"trend_edge_is_conditional_and_decays","topic":"trend_trading","lesson":"Trend-following edges are horizon-specific, unstable in sign, capable of being reproduced by fat-tailed randomness, and prone to multi-year collapse after crises.","practice":"Log every with-trend trade with the conditions that authorised it, and monitor realised expectancy per condition set so decay is detected in the data rather than assumed away.","guardrail":"Never label a with-trend directional claim 'strong'; if realised expectancy for a condition set turns negative over a meaningful sample, disable that set rather than retuning it.","evidence_label":"strong"}
```
