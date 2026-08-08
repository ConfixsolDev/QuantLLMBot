# Topic 8 — Trading in Range

> **Sources read:** `brooks_ranges` pp.11, 15, 20, 30–31, 36, 39–42, 46–48, 53–54, 71, 81, 99, 109–110, 121, 127, 131, 133–161, 162–164, 168, 170, 174–178, 185, 194, 202, 204, 215, 218 · `brooks_trends` pp.14–15, 25, 28, 125, 250, 356–360, 390–395 · `dalton_mind_over_markets` pp.31–34, 39–51, 60, 83–96, 105–112, 185–191, 210–212, 265–266 · `dalton_markets_in_profile` pp.53–54, 69–71, 88–92, 100–103, 105–116, 122, 126–133, 153–155 · `dalton_markets_momentum` pp.20, 31–32, 92, 96–100, 174–180, 195 · `grimes_art_science` pp.36–37, 40–41, 43, 50–54, 59, 61, 114–116, 123–125, 130–137, 141–147, 152–153, 158–159, 162–163, 233–237, 315, 318, 387–388 · `murphy_ta` pp.107, 132–140, 142, 147–151 · `carter_mastering` pp.112–115, 145–146, 155, 481, 488–490 · `lien_fx_sessions` pp.61, 83–85, 108–120, 131, 145, 151, 168, 210
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1.2)

---

## ⚠️ Calibration note — read before using anything below

Three things about the evidence in this topic, stated honestly:

1. **The single most quantified claim in the corpus is a failure rate, not a success rate.** Brooks
   repeats, in four separate places, that roughly 80% of attempts to break out of a trading range
   fail (`brooks_ranges pp.71, 133, 138, 139`). This is an assertion from screen experience, not a
   published study — but it is the *structural* backbone of everything else here, and it is the one
   number every author in the corpus implicitly agrees with when they say "most breakouts fail"
   (`grimes_art_science p.163`). Treat the *direction* of the claim as strong and the *magnitude*
   as `moderate`.
2. **The interior of a range is the one place where every author agrees there is no edge.** Brooks
   says directional probability inside the middle of a range is about 50/50 with only untradeably
   brief fluctuations (`brooks_ranges p.136`). Grimes says ranges approximate random walks and that
   traders should confine involvement to the margins (`grimes_art_science p.131`). Dalton says
   trades that remain inside a balance area should be passed on (`dalton_markets_momentum p.98`).
   This is the closest thing to a consensus, mechanism-backed claim in the whole file, so it is the
   only place `strong` is used freely.
3. **Everything about *which way* a range will break is weak.** Brooks gives ~55% maximum for a
   with-trend break out of a tight range and says it is probably never higher than that
   (`brooks_ranges p.151`). Murphy asserts firm directional rules for triangles and rectangles
   (`murphy_ta pp.134–139, 147–150`); Grimes says he has tested those rules and does not find them
   reliable (`grimes_art_science pp.135–136`). Directional claims in this file are capped at
   `moderate` and mostly labelled `weak`.

Instrument context: XAUUSD spot, D1/H4/H1/M30/M15/M5/M1, sessions Asia 00–07 UTC, London 08–13,
overlap 13–16, NY 16–21. Spot gold has **no true volume** — only broker tick volume. Every
volume-based rule in Dalton, Murphy, Carter and Grimes is therefore degraded for this instrument
and is flagged as such in the Implementation section.

---

## Core concepts

| Concept | Definition (my words) | Sources | Evidence |
|---|---|---|---|
| Trading range (broad definition) | Any region of the chart where trade is two-sided. It can be a single doji bar or hundreds of bars. It does not have to be flat; a slightly sloped one is still a range, and a steeply sloped one is a channel. The useful consequence of the broad definition is that once you name a region "two-sided", you are licensed to look for setups in *both* directions. | `brooks_ranges p.133` | strong (definitional) |
| Uncertainty as the diagnostic | The subjective marker of a range is that you are unsure and no trade looks better than ~55% likely. The marker of a trend is urgency — you want in and are hoping for a pullback that does not come. Uncertainty is not noise about the market; it *is* the market state. | `brooks_ranges pp.133, 136` | moderate |
| Range checklist (observable) | Overlapping bars (many overlapping ≥50% of the prior bar), prominent tails, many dojis, frequent direction changes, flat moving average, stops run repeatedly with strong trend bars that reverse on the next bar, few runs of 3–4 consecutive same-direction trend bars, most bars in the vertical middle third of the screen. | `brooks_ranges p.133` | strong (these are literal, computable bar facts) |
| Directional probability ≈ 50% in the middle | Inside the middle of a range the probability of the next X ticks being up vs. down is about even, with fluctuations too small and too brief to trade. Probability only becomes lopsided near the extremes. | `brooks_ranges p.136` | strong (multi-author: `grimes_art_science p.131`, `dalton_markets_momentum p.98`) |
| 80% breakout-failure rule | About four out of five attempts to break out of the top or bottom of a trading range fail and get pulled back inside. Consequently entering *on* a range breakout is a low-probability trade, and the profitable posture is to bet against breakout attempts until one demonstrably succeeds. | `brooks_ranges pp.71, 133, 138, 139`; `brooks_trends p.393` | moderate (assertion, but four independent restatements and one corroborating author) |
| ...but the eventual break is usually with-trend | Any *one* breakout has ~20% odds; the odds that the range eventually resolves in the direction of the trend that preceded it are ~60%. These are not contradictory — they describe different questions. | `brooks_ranges p.135` | moderate |
| Magnet + vacuum effect | The top and bottom of a range exert increasing pull as price approaches: institutions who intend to fade the extreme step aside while waiting for a better price, which removes resistance and *accelerates* price into the extreme, often producing one or two large trend bars right at the boundary — immediately before the reversal. The strong bar at the edge is evidence *for* the fade, not against it. | `brooks_ranges pp.135, 138, 139` | moderate (mechanism is plausible and the bar signature is observable) |
| The trading range dilemma | Because breakouts mostly fail, your profit target inside a range must be small; but shrinking reward while keeping risk constant demands a very high win rate; and high certainty cannot exist inside a range, since uncertainty is its definition. This is a genuine mathematical trap, not a skill problem. | `brooks_ranges pp.138, 178` | strong (arithmetic) |
| Buy low, sell high, scalp | The correct default inside a range is small-target two-sided scalping from the edges, not swinging. Swing only when a strong setup sits at the *far* edge relative to the preceding trend (strong buy at range bottom in a bull context; strong sell at range top in a bear context). | `brooks_ranges pp.134, 138` | moderate |
| The middle is where accounts die | Two overlapping conditions — middle third of the session's clock and middle third of the session's range — produce overlapping bars, big tails and repeated tiny failed breakouts. Brooks states that a trader who is not yet profitable should simply not trade in that intersection, and that this change alone can flip a loser into a winner. | `brooks_ranges pp.137, 141–142` | strong (multi-author agreement on the no-edge claim; the "flip a loser to winner" part is `weak`) |
| Range middle as magnet | On a range day the midpoint of the day's range gets tested repeatedly, including after a break to a new extreme, and such days usually close near the middle. The middle is therefore a *target* for fades from the edges — not an entry zone. | `brooks_ranges p.140` | moderate |
| Tight trading range | A range whose swings are too small to trade: as a rule of thumb, when recent average daily range has been 10–15 points, any range ≤3 points tall is tight (≈20–25% of ADR), and 4–5 points can behave tight if the bars are large. In a tight range, stop-entry strategies are mathematically losing; almost all viable entries are limit entries; the tighter the range, the fewer trades you should take, and in a truly tight one you should rarely take any. | `brooks_ranges pp.15, 138, 151` | strong (Brooks is explicit and repeats it; the specific 3-point threshold is `weak`) |
| Barbwire | A specific, dangerous species of tight range: three or more largely overlapping bars where at least one is a doji, usually with prominent tails and often relatively *large* bars. Overlap test: if more than half the height of the middle bar sits inside the ranges of the bars before and after it, call the three bars barbwire. | `brooks_ranges pp.11, 153` | strong (definitional and fully computable) |
| Why barbwire is lethal | Large bars mean emotion; small bodies mean whoever moved price got pushed back by the close; heavy overlap means nobody is in control. Both bulls and bears see value *inside* it, so it is an agreement zone, so most breakouts from it fail. It typically produces both a failed low-2 and a failed high-2 before a real break. Brooks documents a sequence of ten consecutive losing stop-entry scalps inside one barbwire pattern. | `brooks_ranges pp.153, 157` | moderate |
| Barbwire cardinal rule | Never enter on the breakout of barbwire. Wait for a trend bar to break out, expect *that* bar to fail, and trade the failure back into the pattern. Fading small bars at the extremes is acceptable; buying its high or selling its low is not. | `brooks_ranges pp.48, 154, 159` | moderate |
| Barbwire location bias | Barbwire tends to break *away* from the 20-bar moving average: forming above it favours an upside break, below it favours a downside break; straddling it gives no bias. More generally, trading ranges tend to break away from the MA, especially when adjacent to it. | `brooks_ranges pp.137, 153` | weak (one author; MA-relative, so sensitive to MA choice) |
| Final flag | A range (especially a tight one or barbwire) that forms late in a trend, breaks out with-trend, and then fails — the breakout reverses back into the range and usually through to the other side, producing at least a two-legged correction and sometimes a reversal. All horizontal ranges are magnets and can become final flags. | `brooks_ranges pp.41, 48, 81, 153, 162` | moderate |
| Trading range vs. trending trading range | A *trading range* is horizontal, two-sided, and resolves by breakout. A *trending trading range* is two or more ranges separated by a breakout — on the daily bar it looks like a trend day (opens near one end, closes near the other), but internally it is range-after-range. Recognition signature: opening range about one-third to one-half of recent average daily range, a breakout after one to two hours, then a second range roughly a measured move away. | `brooks_trends pp.28, 391–392`; `brooks_ranges p.137` | moderate |
| Trending trading range mechanics | Expect a pullback into the earlier range after the second range starts; expect a test of the breakout gap; do not trail stops beyond swing points (they get hit); take profits into the measured-move area rather than exiting on weakness; be ready for a late-day reversal back through one of the ranges — most reversal days begin as trending trading range days. About a third of the time the initial break extends slightly, reverses, extends slightly the other way, and the day just ends as a quiet range day. | `brooks_trends pp.393–395` | moderate |
| Range as pullback on the higher timeframe | Every trading range on your chart is a pullback or flag on some higher chart; a range that lasts long enough has simply lost its short-term predictive power. This is why ranges are continuation patterns by default and why "reversal patterns" (double tops, head-and-shoulders) are all ranges that occasionally fail to continue. | `brooks_ranges pp.133–134, 137`; `grimes_art_science pp.131–132, 163` | strong (definitional across two authors) |
| Sharp lower-timeframe trends live inside ranges | Inside a higher-timeframe box you should expect *clean* lower-timeframe trends running edge to edge, not chop. Grimes calls this a little-known fact; it is why M5 looks trendy while H4 is dead. | `grimes_art_science pp.133–134` | moderate |
| Balance area (Dalton) | Overlapping value across consecutive sessions. Dalton's floor is **two sessions of overlapping value**; the longer balance persists, the better the chance its eventual resolution matters. Balance is scale-free — the same rules apply to overlapping 30-minute bars, weeks, or months. | `dalton_markets_momentum pp.96, 179–180` | moderate |
| Value area | The price band containing roughly 70% of the session's trade (approximately one standard deviation). It is the market's most recent agreed assessment of value, and it is the reference against which the next session's open is judged. | `dalton_mind_over_markets p.34` | strong (definitional) |
| Balance-trading guidelines (Dalton's three) | (1) Pass on trades that stay inside a balance area — chop high, opportunity low; time spent inside merely tightens and further defines the balance. (2) Go with any breakout from balance, then monitor for continuation. (3) Fade any breakout that fails; the destination is then the *opposite* extreme of the balance. | `dalton_markets_momentum pp.98, 180` | moderate (author's stated personal guidelines, explicitly not "rules") |
| What a failed balance breakout implies | It is a signal that change has occurred. Dalton names the pattern "breakout failure" and treats the rejection as excess — the moment that marks the end of one auction and the start of the next — and as the best trade location available in a bracket. Trading, in his framing, is about change, and excess is where change is visible. | `dalton_mind_over_markets pp.265–266`; `dalton_markets_momentum p.98` | moderate |
| Gravitational pull of a developed distribution | To auction away from a fully formed value area, the move needs *force* (volume). Without force, expect price to be pulled back to the established distribution. Conversely, a breakout on rising participation is more likely to establish a new value area. | `dalton_markets_in_profile pp.92, 130–131` | moderate (mechanism sound; unmeasurable in spot gold without real volume) |
| Balance areas as market memory | Previous balance areas act like elevator stops on a subsequent decline or advance — they may not halt it, but they usually pause it long enough to exit or reassess. A market that falls with no prior balance beneath it has no structural support, and a short-term short can turn into a much larger move. | `dalton_markets_in_profile p.153` | moderate |
| Fade the extremes, go with breakouts | Dalton's two balance-area trades: fade an auction that reaches a bracket extreme *and fails to continue* (especially when it "hangs" there and the bids or offers simply dry up), and go with a breakout from balance. He explicitly says he will fade a balance extreme when participation does not support the price advertisement there. | `dalton_markets_in_profile pp.127, 153` | moderate |
| Tighter balance near an extreme precedes the break | When the smaller balance areas inside a bracket start clustering near one extreme of the bracket, the market is coming into progressively tighter balance — commonly the final stage before the transition from bracket to trend. Grimes has the identical pattern: a tight consolidation holding against one edge of a larger range indicates pressure building against that edge and usually precedes its failure. | `dalton_markets_in_profile p.101`; `grimes_art_science pp.135, 141–142` | moderate (two independent authors, same claim) |
| Initial balance | The range set in the first hour of a session by short-term participants looking for a two-sided price. It is the day's base. A narrow base is easily upset — higher odds of range extension and a directional day; a wide base is more likely to contain the session's extremes. | `dalton_mind_over_markets pp.31–32, 39` | moderate |
| Range extension | Any trade beyond the initial balance. It signifies that a longer-timeframe participant has entered; short-term liquidity providers do not produce it. Range extension on *both* sides of the initial balance is the signature of a balanced (Neutral) session. | `dalton_mind_over_markets pp.33, 48`; `dalton_markets_in_profile p.69` | moderate |
| Day types that mean "the range is the day" | **Nontrend day** — narrow initial balance, no range extension at all, no other-timeframe presence; typically ahead of a scheduled event or a holiday. **Normal day** — wide initial balance set early, extremes then hold for the session. **Neutral day** — medium base, range extension on *both* sides, control genuinely even; closing mid-range confirms balance, closing on an extreme hands the session to that side. **Nonconviction day** — structurally looks like a normal/neutral day in hindsight but offered no usable reference points at the time; the trap is that the finished chart *looks* full of opportunities. | `dalton_mind_over_markets pp.39–43, 47–51, 211–212` | moderate |
| Markets to stay out of | Dalton's explicit list includes nontrend days, nonconviction days, long-term nontrend markets and news-driven markets. His test: the harder you have to look for the trade, the lower its quality. | `dalton_mind_over_markets pp.210–212` | moderate |
| Open-auction in range | Opening inside the prior session's range and rotating around the open means sentiment has not changed and no longer-timeframe participant is present with conviction. Consequence: **any extreme formed early has a low probability of holding.** Correct play is to wait for the session to build its extremes and value, then trade the value-area extremes — and to stand aside entirely if a nontrend session develops. | `dalton_mind_over_markets pp.90, 95–96` | moderate |
| Open-auction out of range | Opening *outside* the prior range and then rotating looks like the same non-conviction, but is the opposite: the market sits out of balance, and a forceful move either way becomes much more likely. This is the setup that most often produces a double-distribution trend day. | `dalton_mind_over_markets pp.90–93` | moderate |
| Open-within-value acceptance ⇒ range estimate | If the market opens inside the prior value area and is accepted there (roughly an hour of two-sided trade), it is in balance and today's range will rarely exceed yesterday's. Practical estimate: identify whichever early extreme looks most likely to hold, project the prior session's range length from it, allow ±10%, and revise as extremes are confirmed or erased. | `dalton_mind_over_markets pp.95–96` | moderate |
| Value-Area Rule | If the market opens outside the prior value area, the far edge of that value area tends to hold. **But** if price is *accepted* back inside (repeated time spent there, not a wick), there is a good chance it auctions all the way through the value area to the other side. Qualifiers Dalton attaches: the closer the open to value the higher the odds; narrow value areas (low participation) are traversed more easily than wide ones; and the larger auction's direction matters. Without those qualifiers he says the trade is barely better than a coin flip. | `dalton_mind_over_markets pp.189–191` | moderate (Dalton's own honesty about the unconditional version is the reason this is not `strong`) |
| Brackets are the normal state | Dalton estimates markets bracket in excess of 75% of the time; Brooks says the chart is in a trading range most of the time, and that most of the bars on any chart are inside ranges. A permanently trend-following posture is therefore mis-specified most of the time. | `dalton_markets_in_profile p.101`; `brooks_ranges pp.137, 139` | moderate |
| Potential support/resistance, as zones | Grimes's discipline: always attach the word *potential*, and draw the level with a crayon rather than a pen. Real markets stop at random levels often enough that many "levels" are artifacts of pattern-seeking. Also plan for the third outcome — the level produces *no* reaction at all and price goes straight through. | `grimes_art_science pp.114–116, 130` | strong (methodological; multi-author — Dalton uses "reference points", Brooks uses "areas") |
| Range expansion ≠ breakout | A violation of a range boundary does not invalidate the range. Often the range has simply *expanded* or shifted to a new level, and now trades between wider bounds. Do not naively treat every break of a boundary as a breakout. | `grimes_art_science pp.134, 163` | strong (structural; matches Brooks's 80% failure claim from the other side) |
| Mean reversion vs. range expansion | Grimes's two-force model: markets alternate between mean reversion and range expansion, and this alternation *is* the trend/range cycle. Mean reversion works where the market is overextended relative to a calibrated band or channel, especially after a climax; it does **not** work as a standing posture. He is explicit that with-trend trades generally offer better expected value, that habitual faders get steamrollered, and that the effective fade traders wait for genuine emotional extremes on their timeframe and then pounce. | `grimes_art_science pp.162, 233, 387–388` | moderate |
| Higher-timeframe mean reversion as a veto | A lower-timeframe setup taken while the higher chart is stretched far past its band is a different animal — it fails immediately and collapses under higher-timeframe mean reversion. The most valuable use of this is not finding trades but *removing* them. | `grimes_art_science pp.233–237` | moderate |
| Converging ranges (triangles) | Grimes collapses symmetrical/ascending/descending/wedge/pennant into one thing: volatility compression, which puts you in breakout mode. He reports that the traditional directional and target rules are not reliable in his testing, and reduces his own handling to a single rule: **do not fade the first breakout from a converging range.** The one partial exception he grants is the ascending triangle (higher lows into flat resistance), which shows weakening rejection at the level. | `grimes_art_science pp.135–136` | moderate |
| Expanding ranges | Widening swings in both directions mean the market is confused. Grimes's rule is to have no position: risk is hard to define, and these formations usually burn their stored energy and resolve into a directionless low-volatility range rather than a strong move. | `grimes_art_science p.137` | weak (one author, explicitly personal) |
| Spike-then-reverse-spike ⇒ triangle | A large sharp move followed by a similar move the other way signals participants processing a shock. The normal consequence is a period of consolidation, usually a converging triangle — and it is one of the most reliable ways to accumulate multiple losses, because the price movement attracts traders just in time for the random oscillation. | `grimes_art_science p.136`; `brooks_ranges p.137` | moderate (both authors describe it) |
| Springs and upthrusts | A quick probe below support that is immediately rebid (spring), or above resistance that is immediately sold (upthrust). Short-lived excursions beyond a well-defined range boundary are evidence that large traders are positioning, and often precede a good breakout — in the *opposite* direction to the probe. | `grimes_art_science pp.124–125, 142` | moderate |
| Murphy: the rectangle | A sideways pause between two horizontal lines; a consolidation that usually resolves in the direction of the prior trend. Completion requires a *decisive close* outside a boundary. Target = the height of the range projected from the breakout point. After an upside break the old top becomes support; after a downside break the old bottom becomes a ceiling. Classical duration is one to three months on daily charts. | `murphy_ta pp.147–150` | moderate for the continuation bias; `weak` for the specific target rule |
| Murphy: the symmetrical triangle | Continuation pattern needing four reversal points (two touches per converging line). Time rule: the break should come between roughly two-thirds and three-quarters of the horizontal distance from base to apex; beyond three-quarters the pattern loses potency and price drifts to the apex. Break confirmed by a *close* outside the line, not an intraday poke; the apex then acts as support/resistance. | `murphy_ta pp.133–136` | weak (Grimes reports these rules do not hold up; keep as prior, not signal) |
| Murphy: ascending / descending triangle | Ascending (flat top, rising lows) is bullish; descending (flat bottom, falling highs) is bearish; the symmetrical is directionally neutral. This is the one classical triangle claim Grimes partly corroborates. | `murphy_ta pp.136–139`; `grimes_art_science p.136` | moderate (two authors, one partial) |
| Murphy: trade the swings, but know the exit | Murphy explicitly endorses buying dips and selling rallies inside a rectangle because risk at the boundaries is small and well defined — with the caveat that on a genuine breakout you not only exit the last (losing) fade immediately but may reverse. He also warns that trend-following systems perform very poorly in these periods and that oscillators lose usefulness the moment the break occurs. | `murphy_ta pp.149–150` | moderate |
| Carter: identifying a range day early | The practical problem is that most traders do not realise the day is choppy until it is half over — they find out from their losing trades. His early tell is participation in the first half hour: on the ES, if most of the first six 5-minute bars are at or below ~25,000 contracts, expect a narrow-range choppy session; well above that, expect a session with real trends. He then switches *strategy family*, not just parameters: on choppy days he places resting orders to fade pivot levels; on trend days he waits for price to move *through* a pivot and buys the first pullback to it. | `carter_mastering pp.112–114, 145` | moderate for the behaviour switch; `weak` for the 25,000 threshold (instrument-specific, and gold has no real volume) |
| Carter: pivot behaviour as a range/trend classifier | On a trending day price reaches a pivot, consolidates 15–20 minutes, and continues. On a choppy day price reaches the pivot, loiters, and drifts back where it came from. Also: R2/S2 usually turns out to be the day's extreme under normal volatility; R3/S3 is rare. | `carter_mastering pp.145–146` | weak (one author; regime-dependent — he notes it broke down when VIX hit 40) |
| Lien: the session range as a balance area | Asian-session ranges are systematically the narrowest of the day for most pairs, and the archetypal FX pattern is channel/range trade during the Asian session followed by a breakout in London or the US session — very often triggered by a scheduled release. The completed Asian range therefore functions as the balance area that the London session either accepts, sweeps, or breaks. | `lien_fx_sessions pp.83–85, 151` | moderate (structural for session volatility; directional use is `weak`) |
| Lien: regime classification before trade selection | Classify the environment on the daily chart *first*, even when trading a 5-minute chart. Her range markers: ADX(14) below 20 (and falling), contracting short-term volatility / narrow, horizontal Bollinger bands, and options risk reversals flipping around zero. Trying to fade tops in a trend, or buy breakouts in a range, is her named failure mode. | `lien_fx_sessions pp.108–109, 115–116` | moderate (ADX/BB are standard but weakly tested; risk reversals unavailable for retail XAUUSD) |

---

## Distilled rules

**A. Recognise the state before choosing a playbook**

1. **Classify the H1/H4 state on every closed bar before looking for any setup.** Declare `range`
   only if, over the last N≥10 bars, (a) ≥60% of bars overlap the prior bar by ≥50% of its range,
   (b) the total high-low span of those bars is <60% of ADR(14), and (c) there is no run of ≥3
   consecutive same-direction trend bars. These are Brooks's own checklist items rendered numeric
   (`brooks_ranges p.133`).
2. **Declare `tight range` when the span is ≤25% of ADR(14).** In a tight range, disable all
   stop-entry logic — Brooks states plainly that entering on stops in a range this small is a losing
   strategy (`brooks_ranges pp.138, 151`). Reduce trade count as the range tightens; in the tightest
   ones, take nothing.
3. **Declare `barbwire` when three or more consecutive bars largely overlap and at least one has a
   body ≤10% of its range, using the middle-bar test:** more than half the middle bar's height lies
   inside the ranges of both neighbours (`brooks_ranges pp.11, 153`). Barbwire is a hard veto on
   breakout entries.
4. **Declare `balance` when two or more consecutive sessions have overlapping value areas** (or, if
   value cannot be computed, overlapping H4 bodies). This is Dalton's stated short-term minimum
   (`dalton_markets_momentum p.96`). Record balance_high and balance_low as the union of those
   sessions' extremes.
5. **Never label a range from a single timeframe.** A range on M5 that is a clean pullback on H1 is a
   *pullback* — trade it with-trend only. A range on H4 that is one bar on D1 is a *balance*. Ask
   which chart the structure belongs to before applying range rules (`brooks_ranges pp.133–134, 137`;
   `grimes_art_science pp.131–132`).

**B. Where to trade and where not to**

6. **Only take range trades in the outer thirds.** Skip everything while price is in the central
   35–65% of the box. This is the single highest-conviction rule in the topic
   (`brooks_ranges pp.136–138`; `grimes_art_science p.131`; `dalton_markets_momentum p.98`).
7. **Add a time filter to the location filter.** If it is both the middle of the session's clock and
   the middle of the session's range, take nothing that is not a perfect setup at an extreme
   (`brooks_ranges pp.137, 141–142`). For XAUUSD map this to roughly 03:00–06:00 UTC inside Asia and
   10:30–12:30 UTC inside London.
8. **Require room to the target.** Do not enter a range fade unless the distance from entry to the
   opposite half of the box is at least 2× the stop distance. Brooks's worked arithmetic: in a
   10-tick range, buying 6 ticks off the low leaves nothing to make (`brooks_ranges p.138`).
9. **At the extremes, prefer limit entries to stop entries.** Fading a range with stop orders means
   entering exactly where the institutions are exiting; the tighter the range, the more true this is
   (`brooks_ranges pp.109, 138`).
10. **Prefer second entries at the boundary.** A second attempt (a low-2 at the top, a high-2 at the
    bottom) is Brooks's best range setup; signal-bar quality matters *less* in ranges than in trends,
    and a short setup at the top with a bull-bodied signal bar is normal (`brooks_ranges p.138`).
11. **Do not fade into a tight channel.** If the leg approaching the boundary is a micro channel
    (10 bars, no pullback), wait for the channel to break and then fade the pullback — momentum is
    too strong for a direct fade (`brooks_ranges p.138`).
12. **Treat a large trend bar arriving at a boundary as evidence for the fade, not against it** —
    provided the bar is at a boundary and not in the middle. This is the vacuum effect
    (`brooks_ranges pp.135, 139`). But only experienced logic fades the *close* of that bar; the
    default is to wait for the reversal back inside.
13. **Take profit at the middle or the opposite edge, never "hold for the breakout."** Brooks:
    never overstay a range trade hoping a breakout finally works (`brooks_ranges p.139`).
14. **Never martingale inside a range.** Doubling after losses is precisely the behaviour that a
    tight range punishes with four-plus consecutive losers (`brooks_ranges p.139`).

**C. Balance-area procedure (Dalton)**

15. **Inside balance: pass.** Time spent inside merely tightens the balance and defines it better
    (`dalton_markets_momentum p.98`).
16. **On a breakout from balance: go with it, then immediately begin monitoring for continuation.**
    Continuation, not the breakout bar, is what makes the trade (`dalton_markets_momentum pp.98, 180`;
    `dalton_markets_in_profile p.101`).
17. **On a breakout that fails: reverse, and target the opposite extreme of the balance.** This is
    the highest-quality trade location a bracket offers, because the failure is the visible moment of
    change (`dalton_markets_momentum p.98`; `dalton_mind_over_markets pp.265–266`).
18. **Judge the session's opening against the prior session's value area, not its close.** Open
    inside prior value and accepted there (≈1 hour of two-sided trade) → balance, low risk and low
    opportunity, and today's range will rarely exceed yesterday's. Open outside the prior range →
    out of balance, high risk and high opportunity, and be ready for a directional day
    (`dalton_mind_over_markets pp.90–96`).
19. **When the open is an in-range rotation, distrust the first extremes.** Early highs and lows
    formed by low-conviction rotation have a low probability of holding; wait for the session to build
    its extremes and then trade *those* (`dalton_mind_over_markets p.90`).
20. **Value-Area Rule, with its qualifiers attached.** If price re-enters the prior value area from
    outside and is *accepted* (repeated closes inside, not a wick), expect it to traverse the whole
    value area. Raise conviction when the open was close to value and the value area is narrow; lower
    it when the market opened far away or the value area is wide (`dalton_mind_over_markets pp.189–191`).
21. **When the smaller balances start clustering at one edge of the bigger balance, stop fading that
    edge.** Pressure is building against it (`dalton_markets_in_profile p.101`;
    `grimes_art_science pp.135, 141–142`).

**D. Knowing the range has ended**

22. **Require acceptance, not penetration.** A boundary is broken only when price *closes* outside it
    on the decision timeframe and then holds outside for a defined number of bars. A wick beyond the
    boundary, or a single close that is immediately reclaimed, is range expansion, not a breakout
    (`grimes_art_science pp.134, 163`; `murphy_ta p.134`; `dalton_mind_over_markets p.189`).
23. **Score the breakout bar and its follow-through against Brooks's strength list before switching
    playbooks.** Strong: large body, small tails, close on the extreme, follow-through bar of at
    least average body size, first pullback delayed three or more bars, pullback does not reach the
    breakout point, several levels cleared at once. Weak: small body with a large opposing tail, next
    bar is an opposing reversal or inside bar, only one level cleared and only by a tick, pullback
    reaches breakeven (`brooks_ranges pp.39–40`).
24. **Escalate: `range` → `breakout pending` → `trend` requires two closed-bar events, not one** —
    an accepted close outside the boundary, *and* a subsequent pullback that holds above (below) the
    boundary. Until both occur, stay in range mode.
25. **The first breakout from a converging range is the one you must not fade.** Volatility
    compression puts you in breakout mode regardless of what direction rules say
    (`grimes_art_science p.136`).
26. **After a genuine breakout, expect a new range, not an infinite trend** — particularly on a
    trending trading range day, where the second range forms near the measured-move projection of the
    first (`brooks_trends pp.392–393`). Switch back to range rules on arrival.
27. **When the market has just started trending, delete the range playbook entirely.** Failing to
    recognise and accept a trend day is, in Dalton's words, among the most costly errors available,
    and can give back several days of profit in one session (`dalton_mind_over_markets p.45`). Brooks's
    version: high-1/low-1 and bar-count entries are valid in the *spike* phase of a trend and are
    losing strategies in a range — and the same setup names mean opposite things in the two states
    (`brooks_ranges pp.109, 138–139`). Concretely: if the last 10 bars contain a one-timeframe
    sequence (each bar's low above the prior bar's low for a rally), stop fading.

**E. Sessions and XAUUSD specifics**

28. **Build the Asia box from completed 00:00–06:59 UTC bars and freeze it at 07:00.** London then
    resolves it into exactly one of four states — held inside, swept and reclaimed, rejected at an
    edge, or accepted outside — and the state is declared on M5 closes, not on wicks
    (`lien_fx_sessions pp.83–85, 151`).
29. **Treat an Asia box narrower than ~35% of ADR(14) as a compressed balance and expect London
    expansion; treat an Asia box wider than ~70% of ADR(14) as a session that already spent its
    range** and downweight London breakout expectations (Dalton's narrow-base/wide-base logic applied
    to sessions, `dalton_mind_over_markets p.39`).
30. **Classify the environment on D1 before trading M5.** ADX(14) below 20 and falling, plus a
    contracting/horizontal Bollinger band width on D1, is Lien's range regime; do not run fade logic
    when it is absent (`lien_fx_sessions pp.108–109, 115–116`).
31. **Suspend range logic across scheduled high-impact releases.** Nontrend structure forms *because*
    participants are waiting for information; the balance breaks when the information arrives
    (`dalton_mind_over_markets pp.47, 211`; `lien_fx_sessions p.151`).
32. **Reduce size, do not just widen stops, when the H4 is balanced and the M5 is barbwire.** The
    correct response to an unreadable interior is fewer trades, not bigger ones
    (`brooks_ranges pp.138, 151, 157`).

---

## Worked examples

All examples are XAUUSD, decisions taken on closed bars only, times in UTC.

| # | Setup (observable state) | Decision | Invalidation | Why (concept) | Evidence |
|---|---|---|---|---|---|
| 1 | Asia 00:00–07:00 built a 6.4-point box (ADR14 = 21, so 30% of ADR). London opens 08:00 inside the box. By 10:15 price has printed five M15 bars that each overlap the prior by >50%, price sits at 52% of box height, and the M15 20-EMA is flat. | **SKIP.** No order until price reaches the outer third of the box or the box is broken with acceptance. | N/A — this is a non-trade. It is "wrong" only if it is applied while a one-timeframe sequence is already running (rule 27). | Middle of the range + middle of the session clock. Directional probability is ~50% with no tradable fluctuation. | strong (`brooks_ranges pp.136–138, 141–142`; `grimes_art_science p.131`) |
| 2 | Two consecutive D1 sessions with overlapping value; balance_high 2412, balance_low 2396. During London, M5 pushes to 2411.6, prints a 3.1-point bear trend bar closing at 2408.4 back inside, and the next M5 bar closes lower. | **OPEN SHORT** on the close of the second M5 bar. Stop above 2412 + spread buffer. First target = balance midpoint 2404; runner to 2396. | An M5 close back above 2412 that then holds for two bars (acceptance) — that is a breakout, not a failed one. | Dalton's guideline 3: fade the failed breakout from balance, destination = opposite extreme. Reinforced by Brooks's magnet/vacuum effect — the strong bar at the edge is the setup, not the warning. | moderate (`dalton_markets_momentum p.98`; `brooks_ranges pp.135, 139`) |
| 3 | H4 has been in a 3-session balance. At 08:05 an M15 bar closes 4 points above balance_high on a large body with a tiny upper tail; the next two M15 bars both close higher with average-or-larger bodies; the first pullback comes only on the fourth bar and does not reach the balance_high level. | **OPEN LONG** on the pullback that holds above balance_high — i.e. on the close of the first M15 bar that makes a higher low above the old boundary. Switch the whole engine to trend rules. | Any M15 close back below balance_high. That converts this into example 2 in the opposite direction. | Dalton guideline 2 (go with the breakout, monitor continuation) gated by Brooks's strength checklist: delayed first pullback, pullback that does not reach the breakout point, no opposing reversal bar. | moderate (`dalton_markets_momentum p.98`; `brooks_ranges pp.39–40`) |
| 4 | Same balance breakout as #3, but the M15 breakout bar has a small body with a long upper tail, the very next M15 bar is a bear bar closing near its low with a body about the size of recent bodies, and the pullback reaches the breakout price within two bars. | **SKIP the long, then look to SHORT** the failure back inside on the next M15 close below balance_high. | A recovery close back above the breakout bar's high. | This is Brooks's failed-breakout signature list, item for item. The failure is the trade; the breakout was not. | moderate (`brooks_ranges pp.39–40, 133`) |
| 5 | Midday London, 10:40. On M5: four consecutive bars each overlapping the prior by more than half, two of them dojis with long tails on both ends, bars relatively large, and the cluster sits directly on the M5 20-EMA in the middle of the day's range. | **SKIP — hard veto on all stop entries.** No orders until the pattern resolves. | N/A. | This is barbwire by the literal definition, in its most typical location. Brooks documents ten consecutive losing stop-entry scalps in exactly this configuration. | strong (`brooks_ranges pp.11, 153–154, 157`) |
| 6 | Continuation of #5: an M5 bull trend bar finally closes above the barbwire's high. | **DO NOT BUY THE BREAKOUT.** Wait. If the *next* M5 bar closes back inside the barbwire, **SHORT** on that close, targeting the low of the pattern. If instead two further bars close outside with expanding bodies, stand down and re-evaluate in trend mode. | Two consecutive M5 closes outside the pattern with increasing bodies. | The cardinal barbwire rule: never enter on the breakout; wait for the trend bar to break out and then trade its failure. Barbwire commonly produces both a failed low-2 and a failed high-2 before a real break. | moderate (`brooks_ranges pp.48, 154, 159`) |
| 7 | Asia box 2396–2404 (8 points). London opens 08:00 at 2403.8 — inside the box, upper third. Price rotates above and below the open through 09:30 with no M5 close outside the box, no sequence of same-direction closes. | **WAIT — do not treat the 08:00–09:00 high as the session high.** Let London build its own extremes, then trade *those* edges. Stand aside entirely if no extreme forms by mid-session. | An M5 close outside the Asia box that holds for two further bars — that changes the regime. | Dalton's open-auction-in-range: sentiment unchanged, no conviction, and any extreme formed early has a low probability of holding. The natural mistake is to sell the first push down as if a longer-timeframe seller had arrived. | moderate (`dalton_mind_over_markets pp.90, 95–96`) |
| 8 | **Contrast case.** London opens at 08:00 at 2416, which is 12 points *above* yesterday's high, then rotates sideways around 2416 for the first hour with no direction. | **DO NOT apply range rules.** Treat this as out-of-balance: reduce or remove fade orders, widen expected range, and be prepared for a sustained directional move in either direction once it starts. | Price returning inside yesterday's range and being accepted there — then it is back in balance. | Same *structure* as #7 (rotation around the open), opposite *implication*, because the location relative to prior balance differs. This is Dalton's most useful single distinction and the classic setup for a double-distribution trend day. | moderate (`dalton_mind_over_markets pp.90–93`) |
| 9 | Yesterday: D1 session with a wide initial balance, range extension on *both* sides, close near the middle of the range, total range 0.7× ADR(14). Today opens inside yesterday's value and is accepted there for the first hour. | **Trade the day as a range: fade the extremes only, no breakout orders, size down.** Range estimate: project yesterday's range length from whichever early extreme is holding, ±10%. | Range extension beyond the projected estimate accompanied by a strong bar and delayed pullback — then re-classify. | Neutral-day structure plus open-within-value acceptance: both other-timeframe participants present, balance confirmed, low risk and low opportunity. | moderate (`dalton_mind_over_markets pp.47–48, 95–96`) |
| 10 | The first two hours of the London+overlap block produce a range 1/3 the size of ADR(14). At 11:00 an H1 bar breaks the top of it convincingly and price runs to a measured move ≈ 2× the initial range height by 13:30, where bars begin to overlap again. | **Take profit on the long into the measured-move area. Do NOT trail below swing lows. Then switch to range rules for the upper box, and be alert for a pullback that tests back into the lower range late in the session.** | Continued expansion with three or more successive ranges forming — at that point treat the session as a genuine trend day and trade with-trend only. | Trending trading range day: opening range 1/3–1/2 ADR, one breakout, second range near the measured move, pullback into the earlier range, trailing stops in this structure get hit. | moderate (`brooks_trends pp.391–394`) |
| 11 | **Failure case.** Well-defined H4 box, 4 sessions, boundaries 2380/2398. Price closes on M15 below 2380, holds below for three bars — a textbook accepted breakout by rule 22 — so a short is opened. Within six bars price is back above 2380 and grinding higher; the "boundary" is now behaving like the middle of a wider 2372/2398 range. | **Exit on the M15 close back above 2380.** Re-map the box to 2372/2398 and resume range rules with the new boundaries. Do not re-short the old boundary. | — (this example *is* the invalidation firing) | Grimes's range expansion: violation of support does not invalidate the range; often the range has simply expanded or shifted level. Brooks's version is that ~80% of these attempts fail, and Dalton's is that responsive participants can return price forcefully through the level. The correct response is re-mapping, not revenge. | strong (`grimes_art_science pp.134, 163`; `brooks_ranges p.133`; `dalton_mind_over_markets p.191`) |
| 12 | On H4, price has held a flat resistance at 2415 four times while each intervening low has been higher (2392, 2399, 2405). Rejections at 2415 are getting shallower — the last one lasted two bars. | **Stop fading 2415. Place the breakout order instead, and do not take short setups against the level.** | A decisive H4 close back below the rising lower boundary — that breaks the ascending structure. | Ascending triangle: higher lows into fixed resistance = strengthening buyers and weakening rejection. This is the one classical triangle claim both Murphy and Grimes endorse, and it is identical to Grimes's "tight consolidation holding against one edge" and Dalton's "balances clustering at one extreme". | moderate (`murphy_ta pp.136–139`; `grimes_art_science pp.135–136, 141–142`; `dalton_markets_in_profile p.101`) |
| 13 | Price makes a violent 14-point rally in 40 minutes on a headline, then an equally violent 13-point drop over the next hour, ending near where it started. M5 bars are now large, overlapping, and directionless. | **SKIP for a defined cooling-off window.** No fades, no breakouts, until either the M5 bar-range percentile drops back to normal or a clean boundary forms and is tested twice. | A converging structure that then produces a first breakout — at which point rule 25 applies (do not fade it). | Spike-and-reverse-spike leads to a consolidation, usually a converging triangle, and this is a documented account-killer precisely because the big move attracts traders into the subsequent randomness. | moderate (`grimes_art_science p.136`; `brooks_ranges p.137`) |
| 14 | D1 ADX(14) = 15 and falling; D1 Bollinger width in the bottom quartile of its 100-day distribution; the last three D1 sessions have overlapping bodies. Asia builds a 5-point box; London opens inside it. | **Enable range mode for the session: fades at box edges only, targets at the box midpoint, no breakout entries before 13:00, size reduced.** | An M5 close outside the box that holds for two bars, or D1 ADX crossing back above 20. | Lien's regime classification: ADX<20 falling + contracting volatility = range regime, and her named failure mode is buying breakouts in exactly this environment. Combined with Dalton's balance definition (multi-session overlapping value). | moderate (`lien_fx_sessions pp.108–109, 115–116`; `dalton_markets_momentum p.96`) |
| 15 | Asia 00:00–07:00 was almost featureless: 3.1-point range (15% of ADR14), no M5 bar with a body larger than 0.4 points, and a scheduled US CPI release is due at 12:30. | **SKIP the Asia session entirely; do not fade the Asia box edges during London before 12:30; wait for the release and then re-map.** | N/A. | This is a nontrend structure: narrow base, no range extension, participants balancing ahead of information. Dalton lists nontrend days and news-influenced markets among the four situations to stay out of. Brooks's narrow-base corollary: expect the eventual expansion to be sharp. | moderate (`dalton_mind_over_markets pp.47, 210–212`; `brooks_trends p.395`) |

---

## Learning outcome

After this topic the model must be able to (1) classify any closed-bar window on H4/H1/M15 into
`trend`, `range`, `tight range`, `barbwire`, or `balance` using only bar geometry, session clock and
ADR, and state which classification it used; (2) refuse to open a position while price sits in the
central third of a range or while barbwire is active, and say which rule caused the refusal;
(3) execute the three-branch balance procedure — pass inside, go with an *accepted* breakout, reverse
a *failed* one toward the opposite extreme — where "accepted" and "failed" are defined by closed-bar
acceptance tests and not by wicks; and (4) detect the two conditions that revoke the entire range
playbook — an accepted boundary break with confirmed follow-through, and an active one-timeframe
sequence — and switch to trend behaviour without waiting for a range-style confirmation that will
never come.

---

## Implementation

Everything below is computable from closed OHLCV bars plus a session clock unless flagged.

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `adr14` | Mean of (High−Low) over the last 14 completed D1 bars | D1 | The denominator for every "how big is this range" test. |
| `asia_box_high` / `asia_box_low` | Max high / min low of all M5 bars with 00:00 ≤ t < 07:00 UTC | M5 → session | Freeze at 07:00. Also store close-based variants (max/min of M5 *closes*) for a stricter break test. |
| `london_box`, `ny_box` | Same construction for 08:00–13:00 and 16:00–21:00 | M5 → session | Overlap 13:00–16:00 treated as its own window. |
| `box_position` | (close − box_low) / (box_high − box_low) | any | Mid-zone veto when 0.35 ≤ value ≤ 0.65. |
| `box_width_ratio` | (box_high − box_low) / `adr14` | any | <0.25 → tight; 0.25–0.60 → range; >0.70 → session has spent its range. |
| `overlap_frac(i)` | overlap(bar i, bar i−1) / range(bar i−1) | M5/M15/H1 | Core Brooks primitive. |
| `range_state` | `range` if ≥60% of last 10 bars have `overlap_frac` ≥0.5 AND `box_width_ratio` <0.60 AND no run of ≥3 same-direction trend bars | H1/M15 | Recompute on every bar close. |
| `is_barbwire` | ≥3 consecutive bars where each `overlap_frac` ≥0.5, ≥1 bar has body/range ≤0.10, AND middle bar has >50% of its height inside min(high of neighbours)…max(low of neighbours) | M5/M15 | Hard veto flag on all stop entries while true. |
| `is_tight_range` | `box_width_ratio` <0.25 sustained ≥8 bars | M15/H1 | Disables stop entries; caps position size. |
| `balance_flag`, `balance_high`, `balance_low` | ≥2 consecutive sessions whose value areas (or, fallback, H4 real bodies) overlap; boundaries = union of those sessions' extremes | D1/session | Dalton's 2-session minimum. Widen with each additional overlapping session. |
| `value_area_high` / `value_area_low` | Volume-weighted band containing ~70% of the session's traded volume around the POC | M5 → session | ⚠️ **Spot XAUUSD has no true volume — only broker tick volume.** Use tick volume as a proxy and label every VA-derived signal as degraded. A TPO/time-based value area (70% of the time-at-price distribution) is a defensible pure-price alternative and should be computed in parallel for comparison. |
| `initial_balance_high/low` | High/low of the first 60 minutes of each session window | M5 → session | Dalton's base. |
| `ib_width_ratio` | IB width / `adr14` | session | <0.20 narrow base (expect extension); >0.45 wide base (extremes likelier to hold). |
| `range_extension` | +1 if any close beyond IB high, −1 if beyond IB low, 0 if neither; both → Neutral | session | Both-sided extension = balance confirmation. |
| `day_type` | Rules: no extension + narrow IB → `nontrend`; wide IB + extremes hold → `normal`; one-sided extension → `normal_variation`; two-sided extension → `neutral` (+`neutral_extreme` if close in outer 15% of range); one-timeframe sequence throughout → `trend` | session, evaluated progressively | Emit a *provisional* label each hour with a confidence; final label at session close. Provisional labels are the actionable ones. |
| `open_location` | One of: inside prior VA / outside prior VA but inside prior range / outside prior range | session open | Drives rules 18–19. Computed from the prior completed session only. |
| `open_accepted` | True if ≥12 consecutive M5 bars (1h) close within the prior VA after the open | M5 | Dalton's acceptance ≈ one hour of two-sided trade. |
| `va_rule_active` | open_location = outside VA AND price later returns and prints ≥3 consecutive closes inside VA | M5 | Then target the far side of the VA. Downweight if prior VA width > 0.5×`adr14`. |
| `boundary_break` | First close beyond `box_high`/`box_low` on the decision timeframe | M5/M15 | *Not* a breakout by itself. |
| `boundary_accepted` | `boundary_break` AND next 2 bars also close beyond, AND no close back inside | M5/M15 | This is the acceptance gate for rule 22. |
| `breakout_failed` | `boundary_break` followed by a close back inside within 3 bars | M5/M15 | Triggers the fade-to-opposite-extreme branch. |
| `range_expanded` | `breakout_failed` occurring ≥2 times at the same boundary within 20 bars, OR price holds beyond the boundary without trending | M15/H1 | Re-map the box to the new extremes rather than repeat the trade. See worked example 11. |
| `breakout_strength` | Count of Brooks strength items satisfied minus failure items (body/range ratio, tail asymmetry, follow-through body size, bars until first pullback, whether pullback reaches breakout price, number of prior swing levels cleared) | M5/M15 | Score, not boolean. Gate trend-switch on score ≥ threshold. |
| `one_timeframe_up/down` | ≥3 consecutive bars where each low ≥ prior low (up) or each high ≤ prior high (down) | M15/H1 | Revokes range logic (rule 27). Dalton's one-timeframing test. |
| `spike_reverse_spike` | Two opposing moves within a rolling window, each ≥1.5× the 20-bar mean bar range, net displacement <25% of their sum | M5 | Triggers a cooling-off veto. |
| `converging_range` | Successive swing highs lower AND successive swing lows higher over ≥4 pivots | M15/H1 | Sets breakout-mode: never fade the first break. |
| `ascending_triangle` | ≥3 touches of a flat resistance zone (within 0.15×ATR) with strictly rising intervening lows | H1/H4 | Removes fade orders at that resistance. |
| `adx14_d1`, `bb_width_pct_d1` | Standard ADX(14); Bollinger(20,2) width as a percentile of its own 100-day history | D1 | Lien's regime gate: ADX <20 and falling + BB width in bottom quartile → range regime. |
| `session_atr_profile` | Mean (High−Low) per hour-of-day over 60 days | H1 | Replaces Lien's static pip table with a gold-specific one. Needed for the "narrow for this hour" judgement. |
| `event_window` | Minutes to/from scheduled high-impact releases | clock | ⚠️ **Requires an economic calendar feed the bot may not have.** Without it, rule 31 cannot be enforced and nontrend structure will be mistaken for tradable balance. |
| — | Carter's 25,000-contract ES volume test | — | ⚠️ **Not portable.** Requires real futures volume on a different instrument. If XAUUSD futures (GC) data is available, an analogous first-six-bars participation test could be built and *tested*; do not assume the threshold transfers. |
| — | Options risk reversals / implied vol (Lien) | — | ⚠️ **Not available** for retail XAUUSD. Drop that leg of her range test; ADX + BB width alone. |
| — | $TICK breadth (Carter) | — | ⚠️ **Does not exist** for a single instrument. No substitute. |

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Dalton:** "Go with any breakout from balance" — he says he is willing to take nearly any breakout from balance, and that the fail case is handled afterwards by monitoring continuation (`dalton_markets_momentum pp.98, 180`; `dalton_markets_in_profile p.127`). | **Brooks:** entering on a breakout of any trading range is a low-probability trade; ~80% of attempts fail; you should generally not buy trading-range breakouts at all, because surviving the failed attempts requires a stop so wide that few will accept it (`brooks_ranges pp.71, 135, 138`; `brooks_trends p.393`). | This is the sharpest real disagreement in the topic, and it is partly a **timeframe** disagreement: Dalton's balance is multi-session (≥2 days of overlapping value) and his breakouts are D1-scale; Brooks's ranges are intraday M5 structures where the same "breakout" is one bar. Resolve by **scale-gating**: take with-breakout entries only when the balance being broken spans ≥2 sessions *and* `breakout_strength` clears its threshold *and* the boundary is accepted (rule 22). Below that scale, default to Brooks — fade the attempts. Additionally, Dalton's own guideline 3 (fade the failure) is the safety net he attaches to guideline 2; implement guidelines 2 and 3 as one paired state machine, never guideline 2 alone. |
| **Murphy:** consolidation patterns carry directional and target rules — symmetrical triangles break between two-thirds and three-quarters of the way to the apex, ascending triangles are bullish, rectangles project their own height from the breakout point (`murphy_ta pp.133–139, 147–150`). | **Grimes:** he has looked at those rules and has not found them effective or reliable; he collapses every converging formation into one thing (volatility compression) and reduces his handling to "do not fade the first breakout" (`grimes_art_science pp.135–136`). | Trust the **structural** part of Murphy (a consolidation is usually a continuation; a break must be confirmed by a *close*; the old boundary tends to reverse role) and discard the **predictive** part (apex timing, pattern-specific direction, measured targets as entry logic). Keep Murphy's height-projection only as a *profit-taking reference*, never as an entry reason. The single exception both authors support — the ascending/descending triangle — stays, and is implemented as `ascending_triangle` above. |
| **Brooks:** the correct default inside a range is active two-sided scalping — buy low, sell high, fade the extremes, scale in, take many small trades (`brooks_ranges pp.134, 138–139`). | **Grimes:** price action inside ranges approximates a random walk; most traders are well advised to avoid trading within them and to limit involvement to the margins; he also warns that lower participation in ranges creates a real danger of outsized adverse spikes (`grimes_art_science pp.131, 137`). | They agree about the *interior* and disagree about the *frequency of edge trades*. Adopt Grimes's default (low activity) with Brooks's *selection criteria* (edges only, second entries, limit entries, room to target). Practically: allow range fades but cap trades per session and require the outer-third + room-to-target + second-entry conditions simultaneously. Brooks's own arithmetic supports the conservative reading — his trading-range dilemma says the scalping he describes needs a win rate that a range by definition cannot supply (`brooks_ranges p.138`). |
| **Lien:** currencies rarely spend much time in tight trading ranges and tend to develop strong trends; her archetype is Asia range → London/US breakout (`lien_fx_sessions p.151`). | **Dalton:** markets bracket in excess of 75% of the time (`dalton_markets_in_profile p.101`). **Brooks:** the chart is in a trading range most of the time and most bars on any chart sit inside ranges (`brooks_ranges pp.137, 139`). | Both are true at different scales and Lien is describing an *intraday session pattern*, not a regime frequency. Resolve by scale: at D1/H4, assume balance is the default state (Dalton/Brooks) and require evidence for trend. Within a session, allow Lien's Asia-compresses/London-expands prior as a *volatility* expectation only — never as a directional one, and never as a reason to pre-position for a breakout. |
| **Dalton:** openly hostile to moving averages — they treat all prices as equal and ignore where volume actually traded, which can be actively misleading (`dalton_markets_in_profile pp.129–131`). | **Brooks:** the 20-bar EMA is load-bearing — barbwire location relative to it predicts break direction, ranges tend to break away from it, and MA-adjacent overlap is what makes barbwire dangerous (`brooks_ranges pp.137, 153, 157`). | Use the EMA as a *descriptive* feature (flatness → range confirmation; distance from EMA → overextension), never as the sole reason for a directional bet. Brooks's MA-direction bias for barbwire is single-author and MA-parameter-sensitive: label it `weak` and use it only to break ties, never to authorise a trade. Where a volume or TPO-based value area is computable, prefer it as the "where is value" reference, per Dalton. |
| **Carter:** the range/trend character of a session can be called from participation in the first thirty minutes, and this should switch your entire strategy family (`carter_mastering pp.112–114, 145`). | **Dalton:** day type only becomes knowable as the initial balance forms and range extension either appears or does not — and even then, a *nonconviction* day looks like a normal day in hindsight while offering no usable references at the time (`dalton_mind_over_markets pp.39–51, 211–212`). **Brooks:** most days are not clearly readable until well after the first hour, and the first reversal usually does not arrive until after the first hour (`brooks_ranges p.137`). | Carter's instinct (decide early, switch strategy family) is right; his instrument-specific threshold is not portable and gold has no real volume. Implement Carter's *behaviour* with Dalton's *evidence*: emit a provisional day-type label each hour with an explicit confidence, act on it only when confidence clears a threshold, and treat "nonconviction" as an explicit output class that maps to no-trade rather than forcing a positive classification. |

---

## Gaps

Things this topic needs that no book in the corpus supplies:

- **No statistical validation of the 80% figure — or of any of them.** Brooks's 80% breakout-failure
  rate, his 60% eventual-with-trend resolution, his ~55% ceiling on tight-range direction, and his
  70–80% directional probability during spikes are all asserted from experience, with no sample,
  period, instrument list, or definition of "breakout attempt". Dalton's one genuine study
  (`dalton_mind_over_markets pp.185–189`) covers Treasury bonds over roughly a year in 1986–87 and he
  explicitly cautions against generalising it. **This corpus contains no test of any range-trading
  rule on gold, on FX, or on any instrument after 1990.** All of it needs re-measurement on XAUUSD.
- **No operational definition of "the range".** Every author uses ranges whose boundaries are drawn
  by eye and admits it (Dalton: no hard definition of intermediate-term; Grimes: use a crayon;
  Brooks: it depends on your timeframe). Nobody gives an algorithm for boundary selection, and
  boundary selection dominates every downstream statistic. This is the largest single gap.
- **No treatment of spot-gold microstructure.** No real volume, broker-specific tick volume, variable
  spreads that widen exactly at session boundaries and around releases, and a 23-hour session with a
  daily break — none of which any of these authors contemplated. Every volume-conditioned rule
  (Dalton's value area and "force", Murphy's volume confirmation, Carter's threshold, Grimes's
  breakout volatility) is unverifiable here without substitution.
- **No expectancy model for range fading.** Brooks names the trading-range dilemma precisely but
  resolves it with judgement rather than numbers. Nobody gives the win rate required at a given
  reward/risk in a given range width, nor how that varies with distance from the boundary. This is
  straightforwardly measurable and completely absent.
- **No guidance on how many range trades per session is too many.** All authors warn about
  overtrading in chop; none quantifies the limit.
- **Nothing on overnight/weekend gaps into or out of a balance area** beyond Dalton's brief gap
  guidelines (`dalton_markets_momentum pp.98–99`) — which are explicitly non-numeric ("fairly
  quickly" is undefined by the author's own admission).
- **No correlation or cross-asset conditioning.** Gold's ranges are conditioned by DXY, real yields
  and risk appetite; nothing in the corpus addresses whether a range in one instrument is
  informative about another. Chan is the only quantitative author present and he does not cover it.
- **No treatment of algorithmic participation in modern ranges.** Brooks gestures at it (institutions
  running opposing programs, HFT scalping tight ranges — `brooks_ranges pp.135, 151, 154`) but the
  most recent book here is 2013.

---

## JSONL seeds

```json
{"principle_id":"range_middle_no_trade","topic":"range_trading","lesson":"Inside a trading range the probability of the next X points being up or down is approximately even; edge exists only near the boundaries.","practice":"Compute box_position = (close - box_low)/(box_high - box_low) on each closed bar; refuse every entry while 0.35 <= box_position <= 0.65.","guardrail":"This veto is suspended only when a one-timeframe sequence or an accepted boundary break has already revoked range mode; it is never suspended because a setup looks good.","evidence_label":"strong"}
{"principle_id":"range_breakout_attempts_mostly_fail","topic":"range_trading","lesson":"Roughly four out of five attempts to break a trading range boundary fail and are pulled back inside, so the default posture at a boundary is to bet against the attempt, not with it.","practice":"Do not enter on a first close beyond a boundary; wait either for acceptance (two further closes beyond, none back inside) to go with it, or for a close back inside within three bars to fade it.","guardrail":"The magnitude 80% is one author's estimate and untested on XAUUSD; the direction of the claim is reliable, the number is not. Never size as if 80% were measured.","evidence_label":"moderate"}
{"principle_id":"dalton_balance_state_machine","topic":"range_trading","lesson":"A balance area has exactly three actionable states: inside (pass), breakout accepted (go with it and monitor continuation), breakout failed (reverse toward the opposite extreme).","practice":"Define balance as two or more consecutive sessions with overlapping value; implement the three branches as one state machine so that going with a breakout automatically arms the failure-reversal branch.","guardrail":"Never implement the 'go with the breakout' branch without the failure branch attached; the author presents them as a pair, and the breakout branch alone is the losing half.","evidence_label":"moderate"}
{"principle_id":"barbwire_no_stop_entries","topic":"range_trading","lesson":"Three or more heavily overlapping bars with at least one doji, especially at the moving average in the middle of the session range, is a structure in which stop-entry trading loses repeatedly.","practice":"Flag barbwire when each of three consecutive bars overlaps its neighbour by >=50% and at least one has body/range <=0.10; while the flag is true, disable all stop entries and take at most a fade of a small bar at the pattern's extreme.","guardrail":"If a trend bar does break out of barbwire, do not take that breakout; wait for it to fail and trade the failure back into the pattern.","evidence_label":"strong"}
{"principle_id":"acceptance_not_penetration","topic":"range_trading","lesson":"A boundary is broken only when price closes beyond it and holds beyond it; a wick through the level, or a single close immediately reclaimed, is range expansion rather than a breakout.","practice":"Require boundary_accepted = first close beyond the boundary plus two further closes beyond with none back inside, all on the decision timeframe, before switching out of range mode.","guardrail":"When a boundary is violated twice without trending, re-map the range to the new extremes and resume range rules there rather than re-taking the same trade.","evidence_label":"strong"}
{"principle_id":"open_location_vs_prior_value","topic":"range_trading","lesson":"The same sideways rotation after the open means opposite things depending on where the open sits: inside prior value it signals no conviction and unreliable early extremes; outside the prior range it signals imbalance and high potential for a directional move.","practice":"Classify each session open as inside prior value area, outside value but inside range, or outside range, using only the prior completed session; enable range fading only in the first case and only after roughly an hour of acceptance.","guardrail":"When the open is in-range, do not treat the first hour's high or low as the session extreme; wait for the session to build its own extremes before fading them.","evidence_label":"moderate"}
{"principle_id":"trend_revokes_range_playbook","topic":"range_trading","lesson":"Applying range logic to a market that has just started trending is among the most expensive available errors and can erase several sessions of profit in one.","practice":"Track one-timeframing on M15/H1 (three or more consecutive bars each holding above the prior bar's low for a rally, or below the prior bar's high for a decline); while it is active, cancel all fade orders and take with-direction setups only.","guardrail":"Setup names carry opposite meaning in the two states: first and second pullback entries are valid in a trend's spike phase and are losing entries in a range. Never carry a setup across a state change without re-evaluating it.","evidence_label":"moderate"}
{"principle_id":"tight_range_reduce_activity","topic":"range_trading","lesson":"The tighter the range relative to average daily range, the fewer trades should be taken; below roughly a quarter of ADR, stop-entry strategies are mathematically losing because reward shrinks while risk and noise do not.","practice":"Compute box_width_ratio = box height / ADR(14); below 0.25 disable stop entries and cap the session's trade count; require limit entries at the extremes only.","guardrail":"Do not compensate for a tight range by increasing size or by widening targets into the expected breakout; the correct response to an unreadable interior is fewer trades.","evidence_label":"strong"}
{"principle_id":"asia_box_as_london_balance","topic":"range_trading","lesson":"The completed Asian session range functions as the balance area that London either holds inside, sweeps and reclaims, rejects at an edge, or accepts outside; the archetypal FX pattern is Asian compression followed by London or US expansion.","practice":"Freeze the Asia box from 00:00-06:59 UTC M5 bars at 07:00 and classify London into one of the four states on M5 closes; treat an Asia box narrower than about 35% of ADR(14) as compressed and expect expansion, without pre-positioning for a direction.","guardrail":"This prior is about volatility, not direction. Never open a position in anticipation of the break; and suspend it entirely across scheduled high-impact releases, when narrow structure exists because participants are waiting rather than balanced.","evidence_label":"moderate"}
{"principle_id":"failed_balance_breakout_is_the_signal","topic":"range_trading","lesson":"A breakout from balance that is rejected marks the moment change becomes visible and offers the best trade location a bracket provides; the destination is the opposite extreme of the balance.","practice":"On a close back inside the balance within three bars of a boundary break, open in the reversal direction with the stop beyond the rejected extreme, first target the balance midpoint and runner to the far boundary; monitor continuation and exit on re-acceptance beyond the broken boundary.","guardrail":"Guard against wishful holding: if price re-accepts beyond the original boundary, the failure thesis is dead and the position must be closed rather than averaged.","evidence_label":"moderate"}
{"principle_id":"consolidation_pattern_rules_are_priors_not_signals","topic":"range_trading","lesson":"Classical rules for triangles and rectangles - apex timing, pattern-specific direction, height projections - are not reliable enough to trade on; the durable content is that consolidations are usually continuations, that a break needs a closing confirmation, and that a broken boundary tends to reverse role.","practice":"Use height projections only as profit-taking references, never as entry reasons; treat every converging range identically as volatility compression that puts the engine in breakout mode.","guardrail":"Never fade the first breakout from a converging range. The one directional exception with two-author support is higher lows into flat resistance (or lower highs into flat support), which removes fade orders at that level rather than authorising a breakout entry.","evidence_label":"moderate"}
```
