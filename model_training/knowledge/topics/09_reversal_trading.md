# Topic 9 — Reversal Trading

> **Sources read:** `brooks_reversals` p.112, 118–121, 123–138, 153–158, 173, 195–198,
> 230–233, 257–260, 265–269, 300–301, 409–411, 555–569; `brooks_ranges` p.12, 20–21,
> 29–31, 33–34, 114–115; `brooks_trends` (climax/always-in cross-references via
> `brooks_reversals` restatements); `grimes_art_science` p.57–60, 74, 81, 85–86, 151–160,
> 167–171, 185–189, 204; `murphy_ta` p.99–102, 104–105, 107–112, 121–127;
> `nison_candlesticks` p.24, 42–43, 49–50, 58, 61–62, 69–70, 84–85;
> `dalton_mind_over_markets` p.16, 34, 66; `dalton_markets_in_profile` p.92, 101, 103, 105;
> `douglas_zone` p.46, 84–86; `elder_trading_room` p.18, 70, 100–101, 146, 199;
> `carter_mastering` p.55, 114, 490; `couling_volume` p.22
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1.3 in its entirety)

---

## Framing: this file is a permission gate, not a playbook

Every other topic in this curriculum teaches the model how to find a trade. This one is
written the other way round. Counter-trend entry is the single worst risk profile in the
whole corpus, and the books say so in unusually blunt language:

- Brooks: in a trend, roughly **80 % of attempts to reverse it fail** and become flags, and
  the trend then resumes (`brooks_reversals` p.558, restated at p.561). He tells the reader
  there are **no reliable counter-trend patterns**, and that a non-profitable trader should
  never take one absent a strong break of a significant trend line plus a credible
  always-in reversal signal (p.561). He goes further: because 80 % fail, the *default* read
  of any top should be "start of a bull flag" and of any bottom "start of a bear flag"
  (p.561).
- Grimes: an established trend is a powerful force, and **absent a lot of work, time and
  contrary pressure the best bet at any moment is continuation** (`grimes_art_science`
  p.154). The most dramatic account-ending losses in trading come from fading trends and
  adding to those positions (p.60, p.85).
- Elder: beginners love trading against trends and **get impaled on a price spike that fails
  to reverse**; professionals get away with it only because they will abandon the position at the first hint
  of trouble (`elder_trading_room` p.18).
- Carter: it is fine to miss moves; chasing every move is the mark of an amateur
  (`carter_mastering` p.55). His pivot rules explicitly permit fading only on choppy days
  and require with-trend pullback entries on trend days (p.490).
- Douglas: the whole impulse to call the turn is the need to be right, and **the degree to
  which you need to know what happens next is the degree to which you will fail**
  (`douglas_zone` p.85–86).

So the corpus was mined at least as hard for the conditions that **forbid** a reversal trade
as for those that permit one. The forbid-list (Rules 1–12) comes first, deliberately.

One more framing point that the v1 draft got right and that the full book confirms: the
usual result of a successful reversal is **not** an opposite trend. It is a trading range.
Brooks: markets have inertia, most reversals fail, and when one succeeds a range is more
likely than an opposite trend because a range represents less change (`brooks_reversals`
p.137). Grimes reaches the same conclusion: once a trend ends, a range is the single most probable
next state (p.154), and ranges that hold near the old trend extreme are more likely **continuation**
patterns on the higher timeframe (p.153). The bot must therefore size and target reversal
trades for a range, and treat the full flip as a bonus.

---

## Core concepts

| Concept | Definition (one line, my words) | Sources (slug p.N) | Evidence |
|---|---|---|---|
| **Major trend reversal (MTR)** | A four-part sequence: a visible trend, a counter-move strong enough to break the trend line (and usually the MA), a test back at the old extreme that fails, and enough follow-through for consensus that direction has changed. | `brooks_reversals` p.124 | **strong** (definitional) |
| **Prior trend requirement** | A reversal pattern with no prior trend to reverse is not a reversal pattern; the formation is suspect. | `murphy_ta` p.107; `brooks_reversals` p.124 | **strong** |
| **Trend-line break as precondition** | The break does not reverse anything; it is the first evidence that counter-trend traders are strong enough that you may *begin* to look. Trade with-trend until the test of the extreme resolves. | `brooks_reversals` p.129, p.567; `murphy_ta` p.107–108 | **strong** |
| **Test of the extreme** | After the trend-line break the old trend resumes and retests its extreme; the retest may overshoot (higher high / lower low), match it, or undershoot (lower high / higher low). Brooks: all three are the same behaviour, all are variations of a double top/bottom. | `brooks_reversals` p.127–128, p.136 | **strong** |
| **Second reversal / second entry** | The reversal signal that follows the test — the *second* attempt within a few bars using the same logic. Preferred over the first because the first flushed one side out. | `brooks_reversals` p.118–120, p.196, p.568; `brooks_ranges` p.21; `grimes_art_science` p.170 | **strong** |
| **Trend → climax → range → opposite trend** | The normal path. A trend rarely turns on a dime; it goes two-sided, forms a range, and only then resolves. A V reversal without a trend-channel-line overshoot is rare enough that Brooks says not to plan for it. | `brooks_reversals` p.129, p.133–134, p.137; `grimes_art_science` p.151–154; `murphy_ta` p.107; `nison_candlesticks` p.42 | **strong** |
| **Climax (broad definition)** | Any unsustainable behaviour — one outsized trend bar, a run of them, a parabolic leg. Most climaxes are followed by a trading range, not an opposite spike, and the trend often resumes. | `brooks_reversals` p.153 | **moderate** |
| **Buying/selling climax & vacuum** | Strong bulls stop selling and strong bears stop shorting because both expect a slightly better price; the absence of opposing orders sucks price to a level where both act at once, producing the spike and then the reversal. | `brooks_reversals` p.155–156; `grimes_art_science` p.155; `murphy_ta` p.100–101 | **moderate** |
| **Exhaustion vs measuring** | The same outsized bar is either a breakout that measures a further leg or an exhaustion that ends the leg. Which one it is is only knowable from what the *next* bars do. | `brooks_reversals` p.154, p.173; `murphy_ta` p.104 | **moderate** |
| **Consecutive climaxes** | Three climactic pushes in one direction without a real correction raise the odds (Brooks says 60 %+) of a two-legged, ~10-bar correction; the third is usually the most dramatic and often parabolic. | `brooks_reversals` p.173, p.195; `grimes_art_science` p.81 | **moderate** |
| **Final flag** | The last flag before a trend ends: mostly horizontal, heavy two-sided evidence (overlapping bars, opposite-colour bodies, prominent tails), in a trend already dozens of bars old. Its breakout fails and reverses. Brooks notes a final flag is itself a variation of a double top/bottom. | `brooks_reversals` p.128, p.230–233 | **moderate** |
| **Wedge / three-push** | Three pushes in one direction then a reversal signal. Shape (wedge, triangle, expanding, triple top, H&S) does not matter — they trade the same. A wedge *reversal* is counter-trend and needs a second signal; a wedge *flag* is with-trend and does not. | `brooks_reversals` p.195–196; `grimes_art_science` p.81 | **moderate** |
| **Double top / bottom** | Two tests of the same area after a prior trend. Murphy: not complete until the middle trough/peak is broken on a closing basis; the term is greatly overused and most candidates become something else. Brooks: exactness is irrelevant, all tests of an extreme are double-top variants. | `murphy_ta` p.121–126; `brooks_reversals` p.127–128 | **moderate** |
| **Micro double top/bottom** | The same structure compressed to 2–5 bars. Brooks: most tradable reversals on any chart begin with one, and most traders will not take a reversal without one. It is definitionally a failed high 1/high 2 (or low 1/low 2). | `brooks_reversals` p.128 | **moderate** |
| **Double top/bottom pullback** | Double test, then a deeper pullback that forms a lower high (or higher low) — i.e. a three-push structure where the third push lacked the strength to make a new extreme. One of the more reliable reversal shapes when the signal bars are strong. | `brooks_reversals` p.257–259; `brooks_ranges` p.12 | **moderate** |
| **Failed breakout / failure test** | Price closes beyond a level, attracts no follow-through, and closes back inside. Grimes's working rule: no more than two or three bars outside the level, then strong momentum back. This is the most common reversal trigger in the whole corpus. | `grimes_art_science` p.167–168; `brooks_ranges` p.30; `brooks_reversals` p.153, p.265–266; `murphy_ta` p.126 | **strong** |
| **Last gasp / upthrust** | A failure test at the old extreme *preceded by enough consolidation that another leg looked likely*. The pattern draws its power from the failure of that expectation. Grimes calls it, in the right context, extremely reliable. | `grimes_art_science` p.158–159 | **moderate** |
| **Failed failure** | The fade of a failed breakout itself fails and the original breakout resumes — which makes the whole thing a breakout pullback, i.e. a *with-trend* second signal, and therefore more reliable than the fade was. | `brooks_ranges` p.12; `brooks_reversals` p.265–266, p.561 | **strong** |
| **Excess / tail** | An auction that ends with a rejected extreme (long tail, gap) has finished; one that ends flat has not. Dalton: excess is a dramatic high/low on low volume that opposing participants immediately and aggressively auction away from. A tail must be confirmed by rejection in a later period. | `dalton_markets_in_profile` p.103, p.105; `dalton_mind_over_markets` p.16, p.34 | **moderate** |
| **Responsive activity at value extremes** | Buying is only "responsive" because price is *below value*; selling is only responsive because price is *above value*. Price finding buyers on the way down is not, by itself, responsive activity. | `dalton_mind_over_markets` p.66 | **moderate** |
| **Trend termination ≠ trend reversal** | Grimes's framing: the win condition for a counter-trend trade is that the trend *stopped*. Anything more is a bonus. Expectations must be set accordingly. | `grimes_art_science` p.59 | **strong** (as a discipline) |
| **The Anti** | Grimes's safest reversal entry: require a termination pattern, then a change-of-character move against the old trend, then enter the *first pullback* after that move rather than at the extreme. | `grimes_art_science` p.187–188 | **moderate** |
| **Reversal candle at an extreme** | Nison: candles are unexcelled at *early* signals but give no price targets, and "reversal pattern" is a misnomer — the signal says the prior trend should change, not that it will reverse. | `nison_candlesticks` p.24, p.42, p.58 | **moderate** |
| **Classical reversal patterns** | H&S, triple/double tops, key reversal day, island reversal. Murphy's own preconditions: a prior trend, a trend-line break, size proportional to consequence, and volume confirmation — which is exactly the part XAUUSD spot cannot supply honestly. | `murphy_ta` p.99–102, p.104–105, p.107–112 | **moderate** (patterns) / **weak** (as standalone triggers) |

### The hard problem: is this a reversal, or a deep pullback?

This is the single hardest discrimination in the topic and the corpus gives real, computable
help. Note first that Brooks says the two are *not* distinguishable in the moment — they are
distinguishable only by what happens at three specific decision points.

**Decision point 1 — how far did the counter-move go?**
If the counter-move failed to break the trend line, there is no reversal to discuss; the
trend is intact and only with-trend setups are valid (`brooks_reversals` p.129). A break that cannot even carry price back to the moving average has not shown the force a
reversal requires, so no reversal search should begin yet (p.136). The strongest
breaks have momentum, carry well past the MA, and take out swing points of the prior trend
(p.121). Grimes's parallel statement: a **change of character** is a counter-trend swing
distinctly larger than any recent with-trend swing (`grimes_art_science` p.160, p.187).

**Decision point 2 — what happened at the break of the prior swing?**
When a bull-trend pullback breaks a prior swing low, Brooks says there are exactly three
readings (`brooks_reversals` p.135):
1. Strong continuation below the swing low → new selling dominates → the pullback is likely
   the start of something bigger, possibly a reversal.
2. Sideways drift below it → shorts took profit, bulls bought weakly → a trading range.
3. Sharp reversal back up → strong buyers were waiting under the swing low → **this was a
   deep pullback, not a reversal**, and the market will likely go test the bull high.
Mirror for bear trends. Notice that this test is fully computable from closed bars: measure
follow-through in the N bars after the swing break.

**Decision point 3 — what is the *momentum of the test rally* back to the old extreme?**
This is the discriminator Brooks emphasises most (`brooks_reversals` p.136–137). If the
rally back to the old high is a tight, steep channel with little bar overlap, no pullbacks,
and it runs well past the old high before pausing, the **bull trend has resumed** despite the
earlier trend-line break — the sell-off was a deep pullback. If instead the rally has many
overlapping bars, several bear bodies, two or three clear pullbacks, a wedge shape, and a
slope visibly shallower than both the original trend and the sell-off, the odds favour a
lower high or a marginal higher high and another attempt down. Brooks adds a hard veto: if
the overshoot of the old extreme goes too far in too tight a channel, **stop looking for the
reversal, reset, and wait for another trend-line break and another test** (p.136).

**Two corroborating discriminators from other authors.**
Grimes: after a suspected termination, the presence of *strong momentum beyond the previous
trend extreme is an undeniable sign the trend is continuing*; the tests in genuine
terminations are marked by springs and upthrusts, i.e. failures (`grimes_art_science` p.153).
Dalton: at the old extreme, ask whether the activity is initiative or responsive — responsive
selling above value is a turn signal; initiative buying above value is not
(`dalton_mind_over_markets` p.66).

**And one honest admission.** Brooks tells the reader that agreement about a reversal often
does not arrive until dozens of bars later, and that the move may be a broad channel for 50+
bars that turns out to have been a large trading range all along (`brooks_reversals` p.125).
The bot should not pretend to more certainty than the literature has.

---

## Distilled rules

### A. Conditions that FORBID a reversal trade

1. **Do not take a counter-trend entry while the trend line is unbroken.** In a trend with no
   trend-line break and no trend-channel-line overshoot reversal, take every with-trend
   setup and let counter-trend scalps go. (`brooks_reversals` p.121, p.129)
2. **Do not take a reversal if the counter-move failed to reach the moving average.** A break
   too weak to reach the 20-EMA on the owning timeframe is too weak to reverse the trend.
   (`brooks_reversals` p.136)
3. **Do not take a reversal with no prior trend to reverse.** A double-top shape inside a
   range is a range fade, not a reversal, and must be labelled and sized as one.
   (`murphy_ta` p.107)
4. **Do not fade a parabolic expansion.** If price is accelerating through successively
   steeper trend lines and printing bars entirely outside the volatility envelope, stand
   aside. Grimes: there is a real possibility of a career-ending loss on a single trade here,
   and the hard rule is to limit risk with iron discipline, never add.
   (`grimes_art_science` p.155–156, p.60)
5. **Never add to a losing counter-trend position, and never widen its stop.** The stop on a
   failure test or Anti goes just beyond the extreme of the probe and is respected without
   exception. (`grimes_art_science` p.168, p.188)
6. **Do not take a reversal at the same level twice without new structure.** If a fade of a
   failed breakout is itself reversed, the trade is over and the read has flipped: the setup
   is now a with-trend breakout pullback (a failed failure). Trade that, or stand aside.
   (`brooks_ranges` p.12; `brooks_reversals` p.561)
7. **Do not use a doji or a one-bar range as a reversal signal bar.** Buying above a one-bar
   trading range or selling below one is the standard losing entry.
   (`brooks_reversals` p.565)
8. **Do not enter a reversal on the earliest signal (the channel break) as a default.** It is
   a low-probability style; the standard is to let the counter-breakout show its strength and
   enter on the pullback. If the counter-breakout is weak, flip and look for the with-trend
   entry as the reversal attempt fails. (`brooks_reversals` p.129–130)
9. **Do not take a reversal in a session regime that forbids it.** Trend day → with-trend
   pullbacks only; fade only on choppy/balanced days. (`carter_mastering` p.114, p.490)
10. **Do not take a counter-trend trade if you are not taking the with-trend trades.** If the
    system has skipped the with-trend entries in this trend, it has no standing to take the
    counter-trend one. (`brooks_reversals` p.565)
11. **Recent-loss lockout.** Brooks's operational filter: if the account lost money last
    month, take no reversals at all; and if 7 of the last 10 bars are mostly on one side of
    the moving average, do not look for entries against that side.
    (`brooks_reversals` p.569)
12. **Do not enter a with-trend pullback after a suspected climax either.** Grimes forbids
    both directions here: after a potential climax, do not buy the pullback and do not assume
    a counter-trend position — the climax is a warning to reduce with-trend exposure, not a
    trade. (`grimes_art_science` p.74)

### B. Conditions that PERMIT a reversal trade

13. **Require the full MTR sequence before labelling anything `major_reversal`:** (i) a trend
    on the timeframe in front of you; (ii) a counter-move that breaks the trend line and
    convincingly clears the moving average; (iii) a test of the old extreme that fails —
    higher high, exact double, or lower high, all equivalent; (iv) follow-through.
    (`brooks_reversals` p.124)
14. **Require excess.** Brooks's point: a market cannot recognise
    'far enough' in advance, but it always recognises 'too far' after the fact; only an
    overshoot halts an established drift
    (`brooks_reversals` p.561). Dalton's computable version: a rejected extreme with a tail,
    or a gap, with an immediate aggressive auction back the other way
    (`dalton_markets_in_profile` p.103, p.105).
15. **Prefer the second entry.** When in doubt, wait for the second signal within a few bars
    that uses the same logic. Grimes states this even harder: after a failure-test stop-out,
    if price closes back inside the level on the same or next bar, that re-entry is
    "virtually obligatory" — so budget the risk of both entries as one trade.
    (`brooks_reversals` p.568; `grimes_art_science` p.170)
16. **Use the failure test as the standard trigger.** Short entry: price trades above a
    defined resistance, prints no more than 2–3 bars outside it, then **closes back below**;
    enter on that close; stop just beyond the extreme of the probe. Mirror for longs.
    (`grimes_art_science` p.167–168)
17. **Prefer failure tests that follow enough consolidation to make continuation look
    likely** (the last-gasp/upthrust context). The pattern's power comes from the failure of
    a well-founded expectation. (`grimes_art_science` p.158–159)
18. **Prefer the Anti to the extreme.** Rather than entering at the high, require: a
    termination pattern, then a change-of-character thrust against the old trend, then enter
    the *first pullback* after that thrust, stop beyond the old trend extreme.
    (`grimes_art_science` p.187–188)
19. **Require a micro double top/bottom at the trigger timeframe.** A probe of the level, a
    failed close, and a second failed attempt within a few bars. Brooks: most tradable
    reversals on any chart begin with one. (`brooks_reversals` p.128)
20. **Treat all shapes at the extreme as one family.** Higher high, exact double top, lower
    high, H&S right shoulder, wedge third push, triple top, final-flag breakout — same
    behaviour, same trade, same invalidation. Do not spend inference on classification.
    (`brooks_reversals` p.127–128, p.195, p.257–258)
21. **Count pushes.** Three climactic pushes without a real correction raise the odds of a
    ~10-bar, two-legged correction to roughly 60 %+; after more than three legs, the
    probability of pullback failure rises with each additional leg.
    (`brooks_reversals` p.195; `grimes_art_science` p.151)
22. **Require candle confirmation, not the candle alone.** A hanging man or shooting star at
    an extreme is a warning; Nison requires a close beyond it in the new direction before
    acting, and treats a single-session shooting star as *not* a major reversal signal. A
    dark-cloud cover that fails to close past the midpoint of the prior body needs further
    confirmation. (`nison_candlesticks` p.49–50, p.61–62, p.84–85)
23. **Location first.** A reversal signal is only tradable at a level that already mattered:
    prior swing extreme, prior-day high/low, session extreme, measured-move target, trend
    channel line, round number. Absent location, the signal is noise.
    (`brooks_reversals` p.121, p.157; `dalton_markets_in_profile` p.92)

### C. Management and expectation rules

24. **Default the target to a range, not an opposite trend.** Plan the first target at the
    start of the reversal pattern / mid-range, take a substantial partial there, and only
    then hold a runner for the flip. (`grimes_art_science` p.153, p.188;
    `brooks_reversals` p.137)
25. **Demand immediate payoff.** A working failure test moves sharply away from the level and
    is profitable within one to three bars. Consolidation near the level is a precursor of a
    loss — reduce or exit. (`grimes_art_science` p.169–170)
26. **Size reversal trades smaller than with-trend trades.** Grimes recommends smaller size
    and risk on failure tests specifically because of the re-entry obligation and the gap
    risk; Elder makes readiness to exit instantly the whole justification for professionals
    trading counter-trend. (`grimes_art_science` p.168; `elder_trading_room` p.18)
27. **Accept the arithmetic.** Brooks's own numbers: an average reversal setup is ~40 %
    profitable swing / 30 % small loss / 30 % small profit; the best setups reach 60 %.
    Reversal trades are therefore only justified when reward is a multiple of risk — never
    as scalps with reward ≤ risk. (`brooks_reversals` p.138, p.566)
28. **Convert to with-trend on invalidation rather than reversing the position.** Brooks
    advises exiting and re-entering rather than flipping, because flipping in-place is
    behaviourally hard and usually done badly. (`brooks_reversals` p.561)
29. **If a pullback "feels" like it has gone too far, suspect that the trend has already
    reversed** — that discomfort is Brooks's named tell for mislabelling a reversal as a
    pullback. Re-run the regime classification rather than adding to the with-trend position.
    (`brooks_reversals` p.558)
30. **Log the counterfactual.** Every time the reversal setup is skipped under Rules 1–12,
    record what it did, so the forbid-list can be measured rather than believed.

### D. XAUUSD session rules

31. **Prefer reversal attempts in the first 1–2 hours of the London and NY sessions.** Brooks:
    the extreme of the day forms within the first five bars on ~50 % of days and within the
    first hour or two on ~90 %, and the day's high usually comes from some kind of double top
    (the low from a double bottom). Wait for that double before taking a swing.
    (`brooks_reversals` p.300–301, p.409–411)
32. **Downgrade reversals in the Asia session and in the mid-session lull.** The middle of the
    session is the most common home of tight ranges — the worst environment for stop entries,
    and where fading the extremes of a tight range is a losing habit.
    (`brooks_reversals` p.301)
33. **Treat the 13–16 UTC overlap as high-vacuum.** Institutional order imbalance produces
    the opening-reversal mechanism Brooks describes: a sharp move to a level with no opposing
    orders, then an abrupt reversal that becomes the session extreme. Require the failed
    close back through the level; do not fade the spike in progress.
    (`brooks_reversals` p.409–410)

---

## Worked examples

All examples are XAUUSD, decisions made on **closed bars only**. "Level" means a
pre-identified HTF reference (prior-day extreme, session extreme, prior swing, round number).

| # | Setup (observable state at decision time) | Decision | Invalidation | Why (concept) | Evidence |
|---|---|---|---|---|---|
| **1. Textbook MTR short** | H4 bull trend 40+ bars. A bear leg closes below the H4 bull trend line and closes ~1.5 ATR below the H4 20-EMA, taking out the last higher low. Market then rallies for 14 H4 bars to within 0.3 ATR of the old high; the rally has 6 overlapping bars, 3 bear bodies, two clear pullbacks and a shallower slope than the original trend. M15 prints a probe above the old high and closes back below it; the next M15 attempt fails again (second entry). | **Open short** on the close of the second failed M15 bar. Risk to above the higher of the two probes. First target = start of the test rally; runner for the H4 range low. | Any H4 close above the probe high, or an M15 close above the probe high with body > 1 ATR. | Brooks MTR steps 1–4 + weak-momentum test + micro double top | **moderate** |
| **2. Trend line unbroken — SKIP** | H1 strong bear trend, tight bear channel. Price reaches a D1 support shelf and prints a large bull reversal bar with a long lower tail on M15. No H1 bull trend-line break has occurred; the counter-move has not reached the H1 20-EMA. | **Skip.** Do not buy. Continue to look only for bear-flag shorts. Optionally take partial profit on existing shorts. | n/a — this is a non-trade. If a subsequent rally breaks the H1 trend line *and* clears the EMA, restart the sequence from step 2. | Rules 1, 2; Brooks p.129, p.136: the trend-line break is the precondition, and a break too weak to reach the MA cannot reverse the trend. Grimes p.74: a climax alone does not justify a counter-trend position. | **strong** |
| **3. Parabolic expansion — SKIP** | London session: XAUUSD accelerates upward through three successively steeper M15 trend lines; the last five M15 bars close entirely outside the upper Keltner band; range per bar is 3× the 20-bar average. A shooting star prints at a round number. | **Skip both directions.** No short (parabolic), and no with-trend long (Rule 12 forbids buying the pullback after a suspected climax). Flatten any with-trend runners. | n/a. Re-engage only after a defined consolidation and a change-of-character thrust (Anti setup). | Grimes p.155–156 (career-ending loss risk), p.74 (do not enter pullbacks after a climax); Nison p.84–85 (a single-session shooting star is not a major reversal signal) | **strong** |
| **4. Failure test at prior-day high** | NY session. Price extends above the prior-day high, spends two M30 bars above it with no expansion of range, then closes back below the prior-day high on the third. | **Open short** on that close. Stop just above the highest tick of the excursion. Take 50 % at 1R; hold the rest for the prior-day midpoint. | Any M30 close back above the prior-day high; or a third M30 bar consolidating *at* the level without the trade going 1R in favour. | Grimes failure test template p.167–170: no more than 2–3 bars outside, immediate payoff required, consolidation near the level is the failure signature. | **moderate** |
| **5. Failure test that FAILS — the failed failure** | Continuing #4: the short triggers, then the next M30 bar closes back above the prior-day high with a large bull body. | **Exit the short immediately; do not reverse in place. Then look to buy the first M30 pullback** that holds above the prior-day high. | A close back below the prior-day high on the long side. | Brooks failed failure, `brooks_ranges` p.12: the failed failure *is* a breakout pullback and therefore a second signal in the with-trend direction. Rule 6, Rule 28. | **strong** |
| **6. Failure test stop-out then immediate re-entry** | Variant of #4: the short is stopped out by one tick above the excursion high, and the *same or next* M30 bar closes back below the prior-day high again. | **Re-enter short** on that close, at reduced size, with the combined risk of both entries no larger than one normal trade. | A second close above the level, or failure to reach 1R within three bars. | Grimes p.170: the second entry after a failure-test stop-out is a higher-time-frame failure and is "virtually obligatory"; budget for both. | **moderate** |
| **7. Wedge / three-push top with second signal** | H1: three pushes up into a D1 resistance shelf, each push smaller, the trend line steeper than the trend channel line. Third push overshoots the channel line and closes back inside. First bear signal triggers and fails within two bars; a second bear signal forms four bars later at a lower high. | **Open short on the second signal only.** Skip the first. First target = the bottom of the wedge (start of the pattern); second = measured move of the wedge height. | H1 close above the third push high. | Brooks p.195–196: a wedge *reversal* is counter-trend and therefore needs a second signal, unlike a wedge *flag*. Targets are the pattern start then the measured move. | **moderate** |
| **8. Final flag reversal, sized as a scalp** | H1 bull trend, 50+ bars. A mostly horizontal 8-bar flag forms with heavily overlapping bars, three bear bodies and prominent upper tails. Price breaks above the flag for two bars, then an M15 close takes it back inside the flag. | **Open short, but size and target for a two-legged ~10-bar correction, not for a trend flip.** Take the majority off at the flag low. | H1 close above the flag breakout high (the flag has failed to be final; treat as breakout pullback with trend). | Brooks final flags p.230–233: the flag is a variation of a double top; the failed breakout of it reverses, but the usual result is a correction/range, and the pattern "does not reliably lead to a trend reversal". | **moderate** |
| **9. Deep pullback misread as reversal — SKIP the short** | H4 bull trend. A sharp M30 sell-off breaks a prior H1 swing low and closes 0.8 ATR below it. Two bars later price is back above that swing low with a large bull body, and the following four bars are a tight, steep rally with almost no overlap that carries past the old high. | **Skip / do not short. If already short, exit.** The correct read is a deep pullback in an ongoing bull trend; if anything, look for the with-trend long on the first small pullback. | Return below the swing low with follow-through would reopen the bear case. | Brooks p.135 (three readings of a swing break — the sharp reversal up means strong buyers were waiting) and p.136–137 (a tight steep test channel means the trend has resumed). Grimes p.153: strong momentum beyond the extreme is an undeniable sign of continuation. | **strong** |
| **10. Double top that is not yet a double top — WAIT** | Price backs off a prior swing high on the first attempt, printing a bearish engulfing on M15. The intervening trough has not been broken. | **Wait.** Do not short. Mark the trough as the trigger level; act only on a close below it, or on a genuine failure test on a *second* approach to the high. | A close above the swing high (upside continuation) cancels the watch. | Murphy p.121–126: the reversal is not complete until the middle trough is violated on a closing basis; the term "double top" is greatly overused and most candidates become something else. Brooks p.130: most new highs are followed by profit taking, not reversal. | **strong** |
| **11. Opening reversal in the London/NY overlap** | 13:00–14:00 UTC. Price gaps/spikes to a round number 20 minutes into the overlap on an unusually large M5 bar, then prints an M5 close back below the round number, then a second M5 lower high that also closes below it. | **Open short** on the second failed close. Stop above the spike high. Note Brooks's probability framing: this class of trade is roughly 40–50 % to reach a swing target once a double top has formed, and is justified by reward, not by hit rate. | An M5 close above the spike high, or price consolidating *at* the round number for more than three bars. | Brooks opening reversals p.409–411 (day extreme within the first hour or two on ~90 % of days; the extreme usually comes from a double top); vacuum mechanism p.155–156, p.409. | **moderate** |
| **12. H&S completion with no volume evidence — DOWNGRADE, do not skip** | D1 XAUUSD prints a head-and-shoulders top: prior uptrend present, the fall from the head broke the D1 bull trend line, the right shoulder is a lower high, and price now closes below the neckline. Volume confirmation is unavailable (spot gold has only tick volume). | **Open short at reduced size**, treating the pattern as `moderate` rather than `strong`, with the trend-line break and the lower high — not the pattern name — as the actual reason. Target the pattern-height projection but bank most of it at the first prior support. | A close back above the neckline (Murphy's return move should not recross it decisively), or a close above the right shoulder. | Murphy p.107–112: H&S requires a prior trend, is confirmed by a *closing* neckline break, and its volume confirmation is a stated requirement he cannot waive. Brooks p.125–126 supplies the same trade without needing the label. Gap: tick volume is not the volume Murphy means. | **moderate** |
| **13. Range fade mislabelled as reversal — relabel** | Asia session. Price is inside a 6-hour balance area and reverses off the range top with a clean bearish engulfing. No prior trend exists on H4. | **Trade it if range-fade rules permit, but label it `range_fade`, not `reversal`.** Size and target as a range trade to the mid/opposite edge. Do not carry a "trend has reversed" state into later decisions. | Acceptance above the range top (two closes beyond, holding). | Murphy p.107 (no prior trend → no reversal pattern); Brooks p.121 (in a range you may trade reversals in both directions — but they are range trades). | **strong** |
| **14. Responsive vs initiative at the extreme — WAIT** | Price auctions above the prior session's value area and finds sellers; a long upper tail forms on M30. But the tail is on the final M30 bar of the session, and the next two bars trade *higher* still, holding above value. | **Wait / no short.** The tail is not confirmed and the activity above value is initiative buying, not responsive selling. | Rejection back inside the prior value area in a subsequent period would confirm the tail and re-open the short case. | Dalton p.34 (a tail in the last period is not a tail; it must be validated by rejection in later periods) and p.66 (selling above value is responsive only if it actually rejects; price finding participants is not itself responsive activity). | **moderate** |

Skip/wait examples: **#2, #3, #9, #10, #14** (five). Failure example with the book's
explanation: **#5** (and #12 flags a data-driven downgrade).

---

## Learning outcome

After this topic the model must be able to (a) refuse a counter-trend entry by naming which
forbid-condition applies — unbroken trend line, counter-move that never reached the MA, no
prior trend, parabolic expansion, wrong session regime, or a second attempt at a level that
already failed; (b) construct the four-step MTR sequence from closed bars and refuse the
label `major_reversal` when any step is missing; (c) discriminate a reversal from a deep
pullback using the three Brooks decision points — depth of the counter-move relative to the
trend line and MA, follow-through after the prior-swing break, and the *momentum quality* of
the test rally back to the old extreme; and (d) state, before entry, that the expected
outcome is a trading range rather than an opposite trend, and size and target accordingly.
Testable: given a labelled chart segment, the model should skip at least as many reversal
opportunities as it takes, and cite the specific rule for each skip.

---

## Implementation

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `trend_present` | Series of higher highs+higher lows (or lower/lower) over ≥3 confirmed swings, using a fixed fractal (e.g. 3-bar pivot) on closed bars | Owning TF: H4 or H1 | Prerequisite for any reversal label (`murphy_ta` p.107) |
| `trendline_broken` | Close beyond the line fitted to the last two confirmed with-trend pivots | Owning TF | Line must be re-fitted only on *confirmed* pivots to avoid lookahead |
| `break_reached_ma` | After `trendline_broken`, did any close cross the 20-EMA of the owning TF, and by how many ATR? | Owning TF | Rule 2 veto if false (`brooks_reversals` p.136) |
| `break_strength` | max(ATR-normalised excursion beyond EMA, count of prior-trend swing points taken out) | Owning TF | Higher = more credible reversal (p.121) |
| `test_of_extreme` | After the break, price returns to within k·ATR of the prior trend extreme (k ≈ 0.5); classify as overshoot / equal / undershoot — all three treated identically | Owning TF | `brooks_reversals` p.127–128, p.136 |
| `test_momentum_score` | On the test leg: % of bars overlapping the prior bar ≥50 %, count of opposite-body bars, number of pullbacks ≥2 bars, slope vs original trend slope. High overlap + opposite bodies + shallower slope ⇒ reversal-favourable; low overlap + steep slope ⇒ continuation | Owning TF | **The single most important discriminator** (p.136–137) |
| `tight_channel_overshoot_veto` | Overshoot of the old extreme with <20 % bar overlap over ≥4 bars ⇒ reset the whole sequence | Owning TF | Hard veto (p.136) |
| `failure_test` | Close beyond level for ≤3 bars, then a close back inside; extreme of the excursion recorded as the stop | Trigger TF: M15/M5 | Grimes p.167–168 |
| `micro_double` | Two probes of the same level within ≤5 bars, both closing back inside | Trigger TF: M5/M1 | `brooks_reversals` p.128 |
| `second_entry` | Second signal within ≤5 bars using identical logic to the first | Trigger TF | Required for wedge reversals and whenever `test_momentum_score` is ambiguous |
| `failed_failure` | After a fade entry, a close back beyond the level in the original breakout direction | Trigger TF | Flips state to `breakout_pullback`; forbids re-fading (Rule 6) |
| `push_count` | Number of impulse legs since the last correction ≥10 bars and ≥2 legs | Owning TF | ≥3 raises correction odds (p.195); >3 raises pullback-failure odds (Grimes p.151) |
| `climax_flag` | Bar range ≥ 2× 20-bar ATR **and** body ≥70 % of range **and** ≥2 same-direction predecessors | Any | Broad Brooks definition (p.153) |
| `parabolic_flag` | ≥3 successively steeper fitted trend lines **and** ≥2 consecutive closes entirely outside a 2.5-ATR Keltner band | Owning TF | Triggers Rule 4 total veto |
| `excess_tail` | Wick ≥ 2× body **and** ≥ 0.5 ATR **and** confirmed by the *next* closed bar failing to trade back into the wick | Any | Dalton's "confirmed in a later period" requirement (p.34) |
| `at_level` | Distance to nearest reference (prior-day H/L, session H/L, prior swing, round number 5/10 USD, measured-move target) ≤ 0.3 ATR | Any | Rule 23 |
| `session` | UTC clock: Asia 00–07, London 08–13, Overlap 13–16, NY 16–21 | — | Drives Rules 31–33 |
| `regime_trend_vs_balance` | Directional efficiency (net move / sum of absolute bar moves) over N bars; high ⇒ trend day | H1 over the session | Drives Carter's fade-vs-follow switch (p.114, p.490) |
| `label` | One of `major_reversal` / `climax_correction` / `range_fade` / `failed_breakout_fade` / `failed_failure_continuation` / `no_trade` | — | Never emit `major_reversal` without all four MTR components |
| `expected_outcome` | Default `trading_range`; `opposite_trend` only if `break_strength` high **and** `push_count` ≥3 **and** `parabolic_flag` false | — | Rule 24 |
| **⚠ volume** | **Not available in the form the books assume.** Murphy's H&S/double-top confirmation, Dalton's excess (defined on *volume*), and Coulling's climax reading all require real traded volume. XAUUSD spot gives tick count only. | — | Use tick-volume as a weak proxy at most; never let it upgrade an evidence label. Consider GC futures volume as a proxy feed if available. |
| **⚠ market profile** | Value area, TPO tails and initiative/responsive classification need a profile build, not just OHLCV. | — | Approximate with a session volume-at-price histogram from M1 bars; flag as approximation. |
| **⚠ trend line** | Trend-line fitting is subjective in the books and must be pinned to a deterministic rule (last two confirmed pivots) for reproducibility. | — | Brooks himself concedes everything is "in a gray fog" (p.555). |

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Brooks:** exact shape is irrelevant — higher high, exact double top and lower high are all the same behaviour, and loose definitions make more money; a formation that reads as a dependable pattern will usually behave like one (`brooks_reversals` p.127–128, p.555). | **Murphy:** the pattern is not valid until a specific criterion is met — the middle trough broken *on a closing basis* — and he recommends explicit price (1–3 %) and time (two-day) filters to reduce whipsaw (`murphy_ta` p.123, p.125–126). | Use Murphy's mechanics as the **trigger** (a definite closing break of a definite level) and Brooks's looseness as the **context classifier**. The bot may recognise the family loosely but may only *enter* on a Murphy-grade closed-bar event. This resolves in favour of computability. |
| **Brooks:** the earliest MTR signal has the best trader's equation despite ~40–50 % probability, because reward is a large multiple of risk; both early and late entry styles have positive equations (`brooks_reversals` p.124, p.129–130). | **Grimes / Elder / Carter:** counter-trend entry at the extreme is where careers end; Grimes prefers the Anti (first pullback *after* the change of character), Elder says professionals survive only by running instantly, Carter restricts fading to choppy sessions (`grimes_art_science` p.187–188; `elder_trading_room` p.18; `carter_mastering` p.490). | Take the Grimes/Elder/Carter side by default. The bot enters reversals on the **Anti or the failure-test/second-entry**, not at the extreme. Brooks's early entry is permitted only in the narrow case where the failure test *is* the extreme (probe beyond a level, close back inside) — i.e. where risk is defined by a printed high/low rather than by hope. |
| **Brooks:** most climaxes are followed by a trading range and the trend often *resumes*; a climax is not a reversal (`brooks_reversals` p.153). | **Grimes:** the parabolic blow-off climax is one of only two scenarios in which a *sudden* trend-to-opposite-trend reversal is more likely than usual, and it carries within itself the seeds of a dramatic reversal (`grimes_art_science` p.154–155). | Both are right about different objects. Resolve by magnitude: the ordinary climax (`climax_flag`) → expect a range, default `climax_correction`. The parabolic climax (`parabolic_flag`) → a genuine reversal is more likely **but is forbidden to trade** (Rule 4), because the same passage says the wrong side of it can be career-ending. The bot reads a parabolic as a with-trend *exit* signal, never as a counter-trend *entry* signal. |
| **Murphy:** volume confirmation is essential — at bottoms "the volume pickup is absolutely essential", and if the volume pattern does not confirm, the entire price pattern should be questioned (`murphy_ta` p.109). | **Brooks:** volume is not reliable enough to warrant his attention; he trades on price action and a 20-EMA alone (`brooks_ranges` p.20). | XAUUSD spot has no true volume, which makes this decidable on data grounds. Follow Brooks: build the reversal logic entirely from price. Where a Murphy pattern requires volume the bot cannot supply, downgrade the evidence label one step rather than pretending confirmation exists (see worked example 12). |
| **Coulling:** at the top of a bull trend, sustained high volume is a **selling climax** (insiders selling to retail); at the bottom of a bear waterfall it is a **buying climax** (`couling_volume` p.22). | **Brooks / Murphy / Grimes:** a **buying climax** is the exhaustive buying that ends an uptrend; a **selling climax** is the capitulation that ends a downtrend (`brooks_reversals` p.153, p.173; `murphy_ta` p.100–101; `grimes_art_science` p.74). | This is a pure terminology inversion, not a disagreement about the market. Adopt the Brooks/Murphy/Grimes convention throughout (climax is named after the *exhausting* side). Never emit Coulling's sense; if Coulling material is ingested later, translate it on the way in. |
| **Nison:** a reversal signal should only be used to initiate a new position when it points in the direction of the **major** trend; against the major trend it is an exit/covering signal, not an entry (`nison_candlesticks` p.43). | **Brooks:** the entire MTR construct exists precisely to enter *against* the established major trend at its extreme (`brooks_reversals` p.124). | Reconcile by timeframe. Nison's "major trend" maps to the bot's D1/H4 bias; Brooks's "trend on the chart in front of you" maps to the owning TF. A reversal against the D1 bias is permitted **only** with the full MTR sequence plus a failure test — otherwise Nison's rule holds and the candle is treated as an exit signal for existing with-trend positions, not an entry. |

---

## Gaps

1. **No measured base rates for XAUUSD.** Every probability in this file is a practitioner's
   estimate for the E-mini (Brooks) or US equities/futures (Grimes, Murphy). The 80 % failure
   rate for reversal attempts, the 40/30/30 outcome split, the 60 % figure for corrections
   after three climaxes, and the 90 % first-hour-extreme statistic have **never been measured
   on spot gold, on any timeframe, in any session**. These are the single highest-value tests
   the project could run against its own tick archive.
2. **No volume.** Murphy's confirmation requirements, Dalton's definition of excess (a
   dramatic extreme *on low volume*), and Coulling's whole framework assume real traded
   volume. Spot XAUUSD does not have it. Whether GC futures volume is an adequate proxy for
   spot reversal analysis is untested and unaddressed by any book in the corpus.
3. **No 24-hour session model.** Brooks's key-times material, and every session-based claim
   in the corpus, is built on a single 6.5-hour equity session with an open, a lunch and a
   close. XAUUSD trades nearly continuously across three overlapping sessions with three
   different participant sets. Nobody in the corpus tells you what "the open" means when
   there are three of them, or how to carry a reversal state across a session boundary.
4. **No treatment of scheduled-news reversals.** Gold's largest intraday reversals cluster on
   CPI/NFP/FOMC prints. The corpus's reversal mechanics (vacuum, trapped traders, failure
   tests) plausibly still apply, but no author addresses the case where the reversal is
   caused by an exogenous information shock rather than by positioning. The correct rule may
   simply be a news blackout, but that is not derivable from these books.
5. **Trend-line subjectivity is never resolved.** Brooks, Murphy and Grimes all make the
   trend-line break the gateway condition for reversal trading, and all three draw trend
   lines by eye. No corpus source gives a deterministic fitting rule, so the bot's
   implementation of the *most important precondition in the topic* is an engineering choice,
   not a distilled one. Sensitivity of every downstream rule to that choice is unmeasured.
6. **No guidance on correlated-instrument confirmation.** DXY, real yields and silver are the
   obvious reversal-confirmation inputs for gold specifically; the corpus is instrument-
   agnostic and offers nothing here.
7. **Nothing on partial-fill / spread behaviour at reversal extremes.** Failure-test stops sit
   exactly where spreads widen. Grimes flags gap risk on held positions (p.168) but nobody
   models execution cost at the precise moment reversal trades are entered.

---

## JSONL seeds

```json
{"principle_id":"reversal_requires_trendline_break","topic":"reversal_trading","lesson":"A counter-trend entry is not permitted until a counter-move has broken the trend line of the owning timeframe and closed decisively past the moving average; the break itself reverses nothing, it only opens the question.","practice":"On each closed owning-TF bar, evaluate trendline_broken and break_reached_ma before any reversal setup is scored. If either is false, emit no_trade for the counter-trend direction and continue scoring with-trend setups only.","guardrail":"If the counter-move never reached the 20-EMA, veto the reversal outright regardless of how good the signal bar looks (brooks_reversals p.136).","evidence_label":"strong"}
{"principle_id":"reversal_default_is_range_not_flip","topic":"reversal_trading","lesson":"The usual outcome of a successful reversal is a trading range, not an opposite trend, because a range represents less change than a full transfer of control.","practice":"Set expected_outcome=trading_range by default; take a substantial partial at the start of the reversal pattern or the range midpoint, and hold only a runner for the flip.","guardrail":"Emit expected_outcome=opposite_trend only when break_strength is high, push_count>=3 and parabolic_flag is false (brooks_reversals p.137; grimes_art_science p.154).","evidence_label":"strong"}
{"principle_id":"reversal_vs_deep_pullback_test_momentum","topic":"reversal_trading","lesson":"The momentum quality of the rally back to the old extreme decides whether the prior move was a reversal or a deep pullback: a tight steep test channel means the trend resumed; an overlapping, two-sided, shallower test means the reversal is live.","practice":"Compute test_momentum_score on the leg back to the extreme (bar overlap, opposite-body count, pullback count, slope vs original trend) and require the reversal-favourable side before entering counter-trend.","guardrail":"If the overshoot of the old extreme runs far in a tight channel, reset the whole sequence and wait for a fresh trendline break and a fresh test (brooks_reversals p.136-137).","evidence_label":"moderate"}
{"principle_id":"failure_test_is_the_standard_trigger","topic":"reversal_trading","lesson":"The most common and best-defined reversal trigger is a failure test: price closes beyond a level, spends no more than two or three bars there without conviction, and closes back inside.","practice":"Enter on the close of the bar that closes back inside; place the hard stop just beyond the extreme of the excursion; require the trade to be profitable within one to three bars.","guardrail":"Consolidation near the level after entry is the failure signature, not patience - reduce or exit rather than waiting (grimes_art_science p.167-170).","evidence_label":"moderate"}
{"principle_id":"failed_failure_flips_the_read","topic":"reversal_trading","lesson":"When the fade of a failed breakout is itself reversed, the structure becomes a breakout pullback and the correct trade is with the original breakout, not another fade.","practice":"On a close back beyond the level in the original breakout direction, exit the counter-trend position, relabel state as breakout_pullback, and look for the with-trend entry on the first pullback.","guardrail":"Never re-fade the same level after a failed failure without new higher-timeframe structure; do not reverse the position in place, exit and re-enter (brooks_ranges p.12; brooks_reversals p.561).","evidence_label":"strong"}
{"principle_id":"second_entry_counter_trend","topic":"reversal_trading","lesson":"Counter-trend setups should be taken on the second signal within a few bars rather than the first, because the first flushes one side out and leaves the market one-sided for the second.","practice":"For wedge reversals and any setup with an ambiguous test_momentum_score, require second_entry=true; budget the risk of a stopped-out first entry plus the re-entry as a single trade.","guardrail":"After a failure-test stop-out, a same-or-next-bar close back inside the level is a near-obligatory re-entry, so size the first attempt small enough to afford it (brooks_reversals p.196, p.568; grimes_art_science p.170).","evidence_label":"moderate"}
{"principle_id":"never_fade_a_parabolic","topic":"reversal_trading","lesson":"A parabolic expansion is the one condition where the corpus forbids both a counter-trend entry and a with-trend pullback entry, because the tail risk on the wrong side is career-ending and the with-trend pullback after a climax is itself a losing trade.","practice":"When parabolic_flag is true, emit no_trade in both directions and flatten with-trend runners; re-engage only after a defined consolidation plus a change-of-character thrust.","guardrail":"Never add to a losing position into a parabolic move and never widen its stop (grimes_art_science p.74, p.155-156).","evidence_label":"strong"}
{"principle_id":"eighty_percent_of_reversals_fail","topic":"reversal_trading","lesson":"In an established trend roughly four out of five reversal attempts fail and become flags, so the default interpretation of any top is the start of a bull flag and of any bottom the start of a bear flag.","practice":"Score every reversal candidate against the forbid-list first; log every skip with the rule that caused it and the subsequent outcome so the base rate can be measured on XAUUSD rather than assumed.","guardrail":"Do not take counter-trend entries at all if the with-trend entries in the same trend were skipped, and suspend reversal trading entirely after a losing period (brooks_reversals p.558, p.561, p.565, p.569).","evidence_label":"moderate"}
{"principle_id":"no_prior_trend_no_reversal","topic":"reversal_trading","lesson":"A reversal pattern with no prior trend to reverse is not a reversal; it is a range fade and must be labelled, sized and targeted as one.","practice":"Gate the major_reversal label on trend_present=true on the owning timeframe; otherwise emit range_fade and target the opposite range edge.","guardrail":"Never carry a trend-has-reversed state forward from a trade that was actually a range fade (murphy_ta p.107; brooks_reversals p.121).","evidence_label":"strong"}
{"principle_id":"candle_signal_needs_confirmation_and_location","topic":"reversal_trading","lesson":"A reversal candle at an extreme is a warning that the prior trend should change, not a prediction that it will reverse, and it supplies no price target.","practice":"Require a close beyond the signal bar in the new direction plus at_level=true before acting; take targets from structure (pattern start, range edge, measured move), never from the candle.","guardrail":"A single-session shooting star or hanging man is not a major reversal signal; against the D1 bias treat it as an exit signal for existing positions rather than an entry (nison_candlesticks p.24, p.43, p.49-50, p.84-85).","evidence_label":"moderate"}
```
