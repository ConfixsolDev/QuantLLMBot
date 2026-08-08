# Topic 3 — Candlestick Patterns

> **Sources read:** `nison_candlesticks` pp.22–24, 36–40, 42–55, 60–70, 71–81, 84–88, 90–97, 102–108, 135–140, 163–172, 180–183, 243–245 · `nison_beyond` pp.61–62, 93–94, 111–112, 132–133, 152–155 · `brooks_trends` pp.37–40 · `brooks_ranges` pp.13–14, 18, 20–21, 48 · `brooks_reversals` pp.14, 21, 32, 62–64, 74–75, 80 · `grimes_art_science` pp.12, 23, 29–30, 40, 51, 54 · `murphy_ta` pp.99–105, 276–285 · `couling_volume` pp.11, 27–33, 34–37, 73–82
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1.2)

---

## Headline finding — read this before the rest

Grimes is the strongest sceptic in the corpus and his objection is *specific*, not
generic hand-waving. Two of his claims cut directly at the foundation of this topic:

1. **Intraday closes are close to arbitrary.** He argues that on intraday bars the closing
   print is essentially a random sample of the session, and that it varies between data
   providers because of time-stamping. Since candlestick patterns assign enormous weight
   to the close, switching broker feeds changes which patterns you see. His rhetorical
   question is whether patterns that fragile can really matter (`grimes_art_science` p.29).
   For XAUUSD this is the worst case in the corpus: spot gold has no exchange settlement,
   no official open or close, and every broker stamps the D1 boundary differently
   (typically somewhere between 21:00 and 00:00 UTC).
2. **Isolated candle geometry has no measured edge.** He states plainly that a naive
   statistical test of "candles with long lower shadows" would find no predictive power —
   and that the same geometry *does* tilt probabilities once you condition on a higher
   time-frame accumulation context (`grimes_art_science` p.51). His framing for the whole
   book is that markets are usually near-efficient, most observed price movement is random,
   and most of the patterns markets create are also random (`grimes_art_science` pp.12, 30).
   His governing rule: we do not trade patterns, we trade the imbalances that create the
   patterns (`grimes_art_science` p.23).

Nison himself concedes much of the ground. He says candle definitions vary between his own
Japanese sources, that technical analysis here is art rather than science, that one should
not expect rigid rules, that candles give no price targets, and that candles are not a
complete system (`nison_candlesticks` pp.22–24). In *Beyond Candlesticks* he goes further:
he warns anyone computer-testing candle patterns that a pattern signal alone is not a valid
test — you must first encode *where* the pattern appeared (`nison_beyond` pp.152–153).

**Operational consequence for this bot:** treat pattern names as a compression vocabulary
for bar geometry, never as a standalone signal. Every pattern label must be emitted together
with (a) prior-trend state, (b) distance to the nearest higher-timeframe level, and (c) the
raw geometry fields. If the geometry and location fields are stripped out, the label carries
no evidence weight.

---

## Core concepts

| Concept | Definition (one line, my words) | Sources | Evidence |
|---|---|---|---|
| Real body | The open-to-close span; the Japanese treat it as the essence of the session because it says who finished in control | nison_candlesticks p.36-37; murphy_ta p.276 | strong |
| Shadow / tail / wick | The excursion beyond the body to the session high and low; it records ground taken and then given back | nison_candlesticks p.36; brooks_ranges p.13; couling_volume p.27 | strong |
| Shaven head / shaven bottom | A candle with no upper shadow / no lower shadow; Brooks calls the same thing a shaved body | nison_candlesticks p.36; brooks_ranges p.14 | strong |
| Body fraction | abs(close−open) ÷ (high−low); a continuous conviction measure that subsumes doji, spinning top and marubozu labels | nison_candlesticks p.37; brooks_ranges p.20-21 | strong |
| Close location | Where the close sits inside the bar's range, and where it sits relative to a level; the single most decision-relevant number on a bar | nison_candlesticks p.23, p.39-40; brooks_ranges p.20-21; grimes_art_science p.40 | strong |
| Prior-trend requirement | A reversal label is only valid if the move it claims to reverse actually preceded it; identical geometry inverts meaning with trend | nison_candlesticks p.43-44, p.53, p.78; murphy_ta p.279 | strong |
| Pattern completion | A multi-bar pattern does not exist until its final bar has closed; drawing the line requires the close | nison_candlesticks p.23-24, p.47; nison_beyond p.93 | strong |
| Umbrella line | Small body at the top of the range with a long lower shadow; bullish hammer after a decline, bearish hanging man after a rally | nison_candlesticks p.43-45 | moderate |
| Hammer geometry | Body at the upper end of range (colour irrelevant), lower shadow at least twice the body, no or very short upper shadow | nison_candlesticks p.45 | moderate |
| Hanging man asymmetry | Same shape as hammer but must follow an extended rally, preferably at a high for the move, and must be confirmed; the hammer need not be | nison_candlesticks p.45, p.49-50 | moderate |
| Shooting star / inverted hammer | Small body at the lower end with a long upper shadow; bearish after a rally, bullish (and requiring confirmation) after a decline | nison_candlesticks p.84, p.87-88 | moderate |
| Doji | Open and close equal or within a few ticks; indecision whose meaning is set entirely by location and by how unusual it is on that chart | nison_candlesticks p.38, p.163-165 | moderate |
| Doji sub-types | Long-legged / rickshaw man (both shadows long), gravestone (open, low, close at the low), dragonfly (open, close at the high) | nison_candlesticks p.170; murphy_ta p.278 | moderate |
| Northern vs Southern doji | Nison's own experience is that doji call tops better than bottoms; a doji in a decline needs more confirmation | nison_candlesticks p.165 | weak |
| Spinning top / high-wave | Small body with shadows on both sides; Nison's high-wave candle is the extreme version and means the market has lost directional sense | nison_candlesticks p.37; nison_beyond p.61-62 | moderate |
| Marubozu / belt-hold | Body with little or no shadow; bullish belt-hold opens on its low and closes at its high, bearish is the mirror; longer is more significant | nison_candlesticks p.102 | weak |
| Engulfing | Second body fully covers the prior body (shadows irrelevant), opposite colour, after a clearly definable trend | nison_candlesticks p.53-54 | moderate |
| Engulfing as S/R | Lowest low of a bullish engulfing pair becomes support; highest high of a bearish pair becomes resistance, judged on closes | nison_candlesticks p.55 | moderate |
| Dark cloud cover | Strong white bar, then a bar opening above the prior high that closes deeply — ideally past the midpoint — into that white body | nison_candlesticks p.60-62 | moderate |
| Piercing pattern | Mirror of dark cloud; the white bar must close more than halfway into the prior black body, with less latitude than dark cloud gets | nison_candlesticks p.66-67 | moderate |
| On-neck / in-neck / thrusting | Same shape as piercing but with progressively shallower penetration; weaker, and needs a confirming higher close | nison_candlesticks p.66-67, p.70 | weak |
| Harami | Small body wholly inside the prior unusually long body; unlike a Western inside day only the bodies must nest, not the ranges | nison_candlesticks p.91 | moderate |
| Harami cross | Harami whose second bar is a doji; treated by the Japanese as more potent, and Nison finds it works better at tops | nison_candlesticks p.92 | weak |
| Tweezers | Two or more bars sharing a high or a low; on daily and intraday charts this is only meaningful when combined with another candle signal | nison_candlesticks p.96-97 | weak |
| Star | Small body that gaps clear of the preceding long body — the bodies must not overlap; a doji version is a doji star | nison_candlesticks p.71 | moderate |
| Morning / evening star | Long body, then a star, then a body closing deeply back into the first; the decisive elements are the small middle body and the depth of the third close | nison_candlesticks p.72-73, p.76-77 | moderate |
| Star pattern as S/R | Lowest low of a morning star is support, highest high of an evening star is resistance; the Japanese "three rivers" naming encodes this | nison_candlesticks p.73, p.77-78 | moderate |
| Three white soldiers / black crows | Three consecutive strong same-direction bars, each opening inside the prior body and closing at/near its extreme | nison_candlesticks p.106, p.108 | moderate |
| Advance block / stalled | A three-soldiers sequence that degrades — shrinking bodies or growing upper shadows; use it to protect longs, not to initiate shorts | nison_candlesticks p.108 | moderate |
| Window (gap) | A true gap with no shadow overlap; rising window is bullish, falling window bearish, and the *entire* window is a support/resistance zone | nison_candlesticks p.135-136 | moderate |
| Window's last-gasp level | For a large window the critical level is the bottom of a rising window (top of a falling window); a close beyond it voids the signal | nison_candlesticks p.138 | moderate |
| Record sessions | Count of consecutive-ish new extremes; the traditional guidepost is to stop adding after eight to ten | nison_beyond p.132 | weak |
| Last engulfing | An engulfing pattern appearing in the wrong trend context inverts its meaning and becomes a potential exhaustion signal | nison_beyond p.93 | weak |
| Signal bar (Brooks) | Brooks's replacement for pattern names: a bar is tradable if body direction, tail proportion, overlap and close-versus-prior-closes all line up | brooks_reversals p.62 | moderate |
| Candle pattern trap (Brooks) | A big small-bodied bar with a long countertrend tail inside a strong trend with no prior trend-line break is a trap, not a reversal | brooks_ranges p.48 | moderate |
| Second entry / second signal | The second attempt at the same reversal within a few bars; Brooks treats it as materially more reliable than the first | brooks_reversals p.14, p.21, p.64 | moderate |
| Effort vs result | Wyckoff's third law as Coulling applies it: the volume under a bar must be proportionate to the range the bar produced, or the bar is an anomaly | couling_volume p.11, p.36-37 | moderate |
| Volume-scaled signal | Coulling holds that a shooting star or hammer is never contradicted by volume — volume only sets the magnitude of the implied move | couling_volume p.79 | weak |
| Low-volume long-legged doji | The one candle Coulling says volume *can* contradict: wide swing on low volume implies price was racked around, not repriced | couling_volume p.81-82 | weak |
| Western reversal day | New extreme in the trend then a close back the other way; wider range, heavier volume and outside-day form all add weight | murphy_ta p.99-100 | moderate |
| Filtered candle pattern | Morris's rule inside Murphy: only act on reversal candle patterns while an oscillator sits in its overbought/oversold pre-signal zone | murphy_ta p.284-285 | weak |
| Location dominance | Nison's own summary of a Japanese trader's advice: where you stand matters more than which pattern you have | nison_beyond p.153 | strong |

---

## Distilled rules

Every rule below is computable from bars that have already closed. Nothing peeks at the
current, still-forming bar.

1. **Emit geometry before names.** For every closed bar, compute and record body,
   range, body_fraction, upper_shadow_frac, lower_shadow_frac, close_location_in_range and
   direction *first*; attach a pattern name only afterwards, and only as an additional
   field. (`brooks_ranges` p.20-21; `brooks_reversals` p.32)
2. **Never label a reversal pattern without a measured prior trend.** A bullish reversal
   label requires a preceding decline; a bearish one requires a preceding rally. If
   prior_trend is flat, downgrade the label to a neutral geometry description.
   (`nison_candlesticks` p.43-44, p.78; `murphy_ta` p.279)
3. **Do not label a multi-bar pattern until its last bar has closed.** Two-bar patterns need
   bar 2's close; three-bar patterns need bar 3's close. No provisional labels.
   (`nison_candlesticks` p.23-24, p.47)
4. **Apply Nison's hammer geometry as stated:** body sits in the upper part of the range,
   lower shadow ≥ 2× body, upper shadow absent or very small; body colour is not a filter.
   The mirror thresholds define the shooting star / inverted hammer.
   (`nison_candlesticks` p.45, p.84, p.87)
5. **Require confirmation asymmetrically.** Hanging man and inverted hammer need a
   confirming next bar; hammer and shooting star may be acted on at their own close. For
   the hanging man, Nison's minimum is a next-bar open below the real body and his
   preference is a next-bar *close* below it. (`nison_candlesticks` p.45, p.49-50, p.87-88)
6. **Engulfing requires the bodies only.** Bar 2's body must fully cover bar 1's body;
   shadows are irrelevant. Opposite colours required, except that a doji may be the engulfed
   bar. (`nison_candlesticks` p.53-54)
7. **Upgrade an engulfing when** bar 1 is a spinning top, bar 2's body is long, the move
   into it was fast or extended, and bar 2 carries a relative volume spike.
   (`nison_candlesticks` p.54)
8. **Convert completed patterns into levels.** Store lowest_low of a bullish engulfing /
   morning star as support and highest_high of a bearish engulfing / dark cloud / evening
   star as resistance. Evaluate breaches on closes, not on intrabar pokes.
   (`nison_candlesticks` p.55, p.63, p.73, p.77)
9. **If the pattern completes far from its own level, wait for the retest instead of
   chasing.** Nison's explicit risk/reward remedy: buy back toward the low of the bullish
   pattern rather than at the completing close. (`nison_candlesticks` p.47, p.55, p.74)
10. **Require >50% body penetration for a piercing pattern.** Anything shallower is
    on-neck / in-neck / thrusting and needs a confirming higher close on the following bar.
    Dark cloud gets slightly more latitude than piercing does, but not much.
    (`nison_candlesticks` p.66-67, p.70)
11. **Score dark cloud by penetration depth, not by the name.** Deeper penetration = stronger.
    Full penetration is no longer a dark cloud — it is a bearish engulfing, and structurally
    the stronger signal because the close is beyond the entire prior body.
    (`nison_candlesticks` p.62; `nison_beyond` p.153)
12. **Treat a harami as a pause, not a reversal.** Only the bodies must nest. Rank it below
    engulfing/star patterns in the priority order Nison himself uses.
    (`nison_candlesticks` p.90-91)
13. **Only accept a star's middle bar if its body does not overlap the first body — except
    on intraday and FX-like data, where Nison explicitly relaxes the rule** because
    consecutive opens sit on prior closes. XAUUSD intraday is squarely inside that exception.
    (`nison_candlesticks` p.71, p.73-74)
14. **Score morning/evening stars on two things:** the middle bar must be a small body
    (spinning top or doji), and bar 3 must close deeply into bar 1's body. Gaps around the
    star are ideal but are not required. (`nison_candlesticks` p.73, p.76-77)
15. **Require the true-gap definition for windows:** no overlap between the shadows of the
    two bars. A gap between bodies alone is not a window. Size is irrelevant.
    (`nison_candlesticks` p.136-137)
16. **Trade with the window, not against it.** After a rising window look to buy dips into
    the window zone; after a falling window look to sell bounces into it. Invalidate on a
    close beyond the far edge — bottom of a rising window, top of a falling window.
    (`nison_candlesticks` p.135-136, p.138)
17. **On intraday XAUUSD, expect windows almost exclusively at session boundaries** — the
    daily rollover and the Sunday reopen — because consecutive M5/M15 bars rarely gap.
    (`nison_candlesticks` p.138)
18. **Downgrade any doji that is not unusual on its own chart.** If the recent bars are
    already mostly small-bodied, a new doji carries no information.
    (`nison_candlesticks` p.164-165)
19. **A doji shifts state, it does not flip it.** After a doji in an uptrend, move the
    short-term bias from up to up/neutral. Flip to neutral or down only when a second,
    independent signal agrees. (`nison_candlesticks` p.166)
20. **Take a doji-plus-tall-body pair's extreme as the level.** After a doji following a tall
    white bar, resistance is the higher of the two highs, measured on closes.
    (`nison_candlesticks` p.169)
21. **Never take a countertrend candle signal before the trend has been damaged.** Brooks's
    single most important rule: do not consider trading against a trend until a significant
    trend line or channel has been broken, and then only with a strong signal bar.
    (`brooks_reversals` p.74-75, p.80)
22. **Use Brooks's signal-bar minimum as a hard gate on any reversal entry:** the bar must at
    minimum close beyond its own midpoint in the intended direction; prefer a body in that
    direction, a countertrend tail of roughly one-third to one-half the bar, little overlap
    with prior bars, and a close that reverses more than one prior bar's close.
    (`brooks_reversals` p.62)
23. **Flag the candle-pattern trap.** A large bar with a small body and a long countertrend
    tail inside a tight trending channel, with no prior trend-line break, is a trap. Brooks's
    guidance is to expect the follow-up small bar to fail and to look for entry in the
    *trend* direction. Gravestone dojis in strong trends are his named example.
    (`brooks_ranges` p.48)
24. **Prefer the second signal.** When a first reversal attempt at a level fails and a second
    sets up within a few bars on the same logic, weight the second higher.
    (`brooks_reversals` p.14, p.21, p.64)
25. **Validate the bar with volume where volume exists.** Wide range on relative volume
    consistent with that range = validation; wide range on low relative volume = anomaly.
    (`couling_volume` p.11, p.36-37)
26. **Escalate a high-relative-volume hammer.** Nison's own volume note: a hammer on an
    abnormal volume spike is less likely to see price return to the hammer's low, so it
    justifies acting at the completing close rather than waiting for the retest.
    (`nison_candlesticks` p.243-245)
27. **Treat a low-volume long-legged doji as manipulation, not indecision.** Coulling's one
    named volume anomaly: violent two-sided range on light volume around a news release
    (NFP is her canonical case, and it is a first-order XAUUSD driver) means stops were
    being harvested. Stand aside. (`couling_volume` p.81-82)
28. **Repeated identical rejections at one price outrank a single pattern.** Two or three
    shooting stars failing at the same level, or repeated long shadows into one zone, is
    stronger evidence of that level than any single named pattern.
    (`nison_candlesticks` p.86, p.106; `couling_volume` p.74)
29. **Cap trend-continuation enthusiasm by extension count.** After roughly eight to ten
    record extremes without a meaningful correction, stop initiating with the trend and only
    take exits or countertrend signals. (`nison_beyond` p.132)
30. **Log the data-feed caveat with every intraday pattern.** Record the D1 boundary
    convention and the bar timestamp with any pattern label, because the label is
    feed-dependent. (`grimes_art_science` p.29)
31. **Never let a pattern label alone size a trade.** Sizing must come from the level, the
    higher-timeframe context and the risk to invalidation, because candles supply no price
    targets. (`nison_candlesticks` p.24)

### Confirmation matrix — where Nison demands an extra bar and where he does not

Nison is not uniform about confirmation, and the asymmetries are load-bearing. Encode this
table directly; do not apply a blanket "always wait one bar" rule.

| Pattern | Confirmation required? | What counts as confirmation | Source | Evidence |
|---|---|---|---|---|
| Hammer | No | May be acted on at its own close | nison_candlesticks p.45 | moderate |
| Hanging man | **Yes** | Minimum: next open below the real body. Preferred: next *close* below it | nison_candlesticks p.45, p.49-50 | moderate |
| Shooting star | No (but it is not treated as pivotal resistance either) | — | nison_candlesticks p.84 | weak |
| Inverted hammer | **Yes** | Next open above the real body, especially a close above it | nison_candlesticks p.87-88 | moderate |
| Bullish / bearish engulfing | No | Complete on bar 2's close; the pattern's own extreme is the invalidation | nison_candlesticks p.53-55 | moderate |
| Dark cloud cover, ≥50% penetration | No | — | nison_candlesticks p.61 | moderate |
| Dark cloud cover, <50% penetration | **Yes** | Further bearish action after the pattern | nison_candlesticks p.61 | moderate |
| Piercing pattern | No, but only if >50% penetration — the threshold is stricter here than for dark cloud | — | nison_candlesticks p.66 | moderate |
| Thrusting / in-neck / on-neck | **Yes** | A higher close on the bar after the white candle; less confirmation needed if it also confirms a prior support area | nison_candlesticks p.70 | weak |
| Morning / evening star | No | Complete on bar 3's close | nison_candlesticks p.73, p.76 | moderate |
| Doji in a rally (Northern) | Partial | Shifts bias to up/neutral; a second independent signal is needed to flip it fully | nison_candlesticks p.166 | weak |
| Doji in a decline (Southern) | **Yes**, more than a Northern doji | Nison's stated experience is that doji call bottoms less well; he accepts a doji that confirms a known support | nison_candlesticks p.165 | weak |
| Tweezers on daily/intraday | **Yes** | Matching extremes alone are not meaningful; another candle signal must coincide | nison_candlesticks p.97 | weak |
| Advance block / stalled | n/a — not an entry signal | Use for exits and stop management only | nison_candlesticks p.108 | moderate |
| Breakout above a stored pattern resistance | **Yes** | A *close* above the level, not an intraday poke | nison_candlesticks p.48, p.23 | strong |
| Any countertrend signal (Brooks overlay) | **Yes, always** | Prior trend-line/channel break plus a signal bar meeting the minimum criteria | brooks_reversals p.62, p.74-75, p.80 | moderate |

### Failure modes — the catalogued ways a valid pattern stops working

Each of these is an explanation the books actually give, not a generic "sometimes it fails".

1. **No prior trend to reverse.** The commonest error. A shape that matches a bearish
   engulfing but follows a decline is not one; Nison rejects exactly this case in his own
   worked chart. (`nison_candlesticks` p.78)
2. **Wrong-context inversion.** Worse than "no signal": in *Beyond Candlesticks* the same
   shape in the wrong trend becomes a last engulfing pattern with the opposite implication.
   (`nison_beyond` p.93)
3. **Completion too far from invalidation.** The pattern is correct but unusable. Nison's
   Trader A/Trader B illustration has both traders reading the same hammer correctly; only
   the one who waited for the retest survives the next session's gap.
   (`nison_candlesticks` p.47)
4. **The trap.** A strong-looking countertrend bar inside a tight channel with no prior
   trend-line break. Brooks's diagnosis is that the tail and the close near the extreme
   *are* real evidence of countertrend pressure, but they arrive before the trend has been
   damaged, so the bar's high becomes the wrong place to buy. (`brooks_ranges` p.48)
5. **Signal weaker than the breakout that preceded it.** Brooks's comparative test: if the
   spike into a level is stronger than the reversal bar against it, expect the reversal
   attempt to fail within a few bars and become a with-trend pullback setup.
   (`brooks_ranges` p.34; `brooks_reversals` p.68)
6. **Signal saturation.** A doji or spinning top in a chart already full of them conveys
   nothing; a tweezers on an intraday chart with no accompanying candle signal conveys
   nothing. (`nison_candlesticks` p.97, p.164-165)
7. **Effort/result anomaly.** Wide range produced on light volume was not repricing; it was
   stop-hunting. Coulling's named case is a long-legged doji on a news release.
   (`couling_volume` p.81-82)
8. **Exhaustion of the underlying move.** After roughly eight to ten record extremes the
   market is stretched, and continuation patterns stop paying even when correctly formed.
   (`nison_beyond` p.132)
9. **Location absent.** Nison's flat statement to would-be back-testers: testing a pattern
   without encoding where it appeared is not a valid test, because a less-than-ideal pattern
   at resistance can be more bearish than a textbook one in open space.
   (`nison_beyond` p.152-155)
10. **The pattern was an artefact of the feed.** Grimes's case: a different data provider
    with a different bar boundary would have shown a different pattern at the same moment.
    (`grimes_art_science` p.29)

---

## Worked examples

All examples restated into XAUUSD terms. Session clock: Asia 00:00–07:00 UTC, London
08:00–13:00, overlap 13:00–16:00, NY 16:00–21:00.

| # | Setup (observable, all bars closed) | Decision | Invalidation | Why (concept) | Evidence |
|---|---|---|---|---|---|
| 1 | H1 has printed five consecutive lower closes into an H4 support level. The current closed H1 bar has body_fraction 0.18 with its body in the top quarter of the range, lower_shadow ≈ 3× body, upper shadow ~0. Low sits 2 USD under the H4 level; close sits back above it. | **Open long** on the M5 trigger after the H1 close, stop below the hammer low. | H1 close back below the hammer low, or below the H4 level. | Nison hammer: body at upper end of range, lower shadow ≥ 2× body, minimal upper shadow, after a decline; hammer becomes support and the level under it is the "price that says we are wrong". (`nison_candlesticks` p.45, p.48) | moderate |
| 2 | Same geometry as #1 but the preceding ten H1 bars are *rising* and the bar prints at a new high for the London session. | **Wait** — this is a hanging man, not a hammer. Do nothing until the next H1 bar closes. | Next H1 closes *above* the hanging man body → bull trend still intact, cancel the idea. | Identical shape, opposite meaning; Nison requires bearish confirmation for the hanging man because the long lower shadow is itself a bullish element. His preference is a close beneath the real body. (`nison_candlesticks` p.43-45, p.49-50) | moderate |
| 3 | London session: H1 bar 1 is a small bearish body after a 30 USD decline; H1 bar 2 is a large bullish body whose open is below bar 1's close and whose close is above bar 1's open, on the highest relative volume of the last 20 bars. Pattern completes at the H4 prior swing low. | **Open long** at bar 2's close, stop below the lower of the two lows. Record lowest_low as a new support level. | Close below the pair's lowest low. | Bullish engulfing with all three Nison enhancers present — small first body, long second body, volume spike on the second — sitting at a location. Pattern low becomes support. (`nison_candlesticks` p.53-55) | moderate |
| 4 | Same bullish engulfing completes, but price is already 18 USD above the swing low and the ATR(14) on H1 is 4 USD. Stop-to-entry distance would be ~5× ATR. | **Wait for the retest** into the pattern's lowest low rather than entering at the completing close. | A close below the pattern low while waiting → the idea is dead, no entry. | Nison's own risk/reward remedy: by the time the pattern completes the market may be too far from an attractive entry, so use the pattern's own extreme as the buy zone. (`nison_candlesticks` p.47, p.55) | moderate |
| 5 | NY session, H4 downtrend intact and no H4 trend-line break yet. An M15 bar prints a very large range, near-zero body, and an upper shadow covering ~85% of its range — a textbook gravestone doji — at the low of a tight bear channel. Next M15 bar is small. | **Skip the long. Consider the short** at one tick below the small bar's low if the H4 context permits. | An M15 close above the gravestone's high. | Brooks's candle-pattern trap: big small-bodied bars with long tails in a tight trending channel with no prior trend-line break are traps, and he singles out the gravestone doji as the one novices worship. The lack of follow-through in the next bar traps the early buyers. (`brooks_ranges` p.48) | moderate |
| 6 | Asia session, M15 chart. The last six bars all have body_fraction below 0.25 and overlap heavily; three of them qualify as doji. Price is in the middle of the Asia range, well away from any D1 or H4 level. | **Skip.** Take no candle signal from this cluster. | n/a — no position. | Two independent grounds: Nison says a doji is meaningless when the chart is already full of them; Brooks calls three or more overlapping bars with a doji "barbwire" — a continuation structure where you must not buy the high or sell the low. (`nison_candlesticks` p.164-165; `brooks_ranges` p.48) | strong |
| 7 | H4: bar 1 is a long bullish body after a multi-day rally; bar 2 is a small body whose range sits above bar 1's body; bar 3 is a bearish body closing back below the midpoint of bar 1's body. | **Open short** on bar 3's close, stop above the highest high of the three bars. Store that high as resistance. | H4 close above the three-bar high. | Evening star. Nison's decisive criteria are the small middle body and the depth of bar 3's close into bar 1; the pattern's highs become resistance. (`nison_candlesticks` p.76-77) | moderate |
| 8 | Same three-bar shape on M15 during the overlap, but bar 2's body slightly overlaps bar 1's body and there is no gap anywhere. | **Still label it an evening star**, then apply the normal location and confirmation gates. | Same as #7. | Nison explicitly relaxes the no-overlap requirement for FX-style instruments and intraday charts, where each open sits on the prior close; he reports the relaxed version performs like the classic one. (`nison_candlesticks` p.73-74, p.78) | moderate |
| 9 | Sunday 22:00 UTC reopen: XAUUSD's first H1 bar has a low 6 USD above Friday's final H1 high, with no shadow overlap. Price then trends up for six hours and pulls back into the 6 USD band. | **Open long** on the first M15 bar that closes back above the band's midpoint, stop below the bottom of the window. | H1 close below the bottom of the window → the rising window is voided, look for the next window below as the new reference. | Rising window: entire window is a support zone, "corrections stop at the window", the critical level is the window's bottom, and window size does not matter. On intraday charts windows form at day boundaries. (`nison_candlesticks` p.135-138) | moderate |
| 10 | **FAILURE CASE.** M15 during the 13:00–16:00 overlap: a clean bullish engulfing completes at a round number. Price never reaches the pattern low; instead the next four M15 bars overlap heavily and the fifth closes below the engulfing pair's low. | **The pattern failed.** Exit on the close below the pair's low; do not re-enter long on the next similar shape at the same price. | Already invalidated. | Three converging explanations. Nison: the engulfing pattern's *only* structural claim is the level, and a close beyond it voids the bullish outlook (`nison_candlesticks` p.48, p.55). Brooks: this was a countertrend signal with no prior break of the bear trend line, and countertrend signals without that break usually become breakout-pullback setups in the original direction (`brooks_reversals` p.74-75). Grimes: an isolated long-tail/engulfing geometry with no accumulation context has no measured predictive power (`grimes_art_science` p.51). | moderate |
| 11 | The same level as #10 is tested again eleven M15 bars later. This time an H1 bear trend line has been broken, and the second attempt prints a bullish bar closing above its midpoint with a lower tail ~40% of its range and little overlap with the prior bar. | **Open long** — this is the second signal at the same level after a trend-line break. Stop below the second signal bar. | Close below the second signal bar's low. | Brooks: a second entry on the same logic within a few bars is materially more reliable, and the trend-line break is the precondition that made the first attempt premature. The signal bar also meets his minimum reversal-bar criteria. (`brooks_reversals` p.14, p.62, p.64, p.74-75) | moderate |
| 12 | 12:30 UTC on the first Friday of the month (NFP). The M5 bar spanning the release has a range 6× the 20-bar average, open and close within 0.4 USD of each other, long shadows both sides, and tick volume *below* its 20-bar average. | **Skip.** Do not label this a reversal and do not trade the level it printed at. | n/a — no position. | Coulling's single named volume anomaly: a long-legged doji requires effort to create, so low volume with a huge range means price was racked around to harvest stops rather than repriced. She names NFP as the canonical case. (`couling_volume` p.11, p.81-82) | weak |
| 13 | D1 XAUUSD makes a new high for a three-week uptrend, then closes below the previous day's close, on the widest daily range and highest volume of the month, with the day's high and low both outside the prior day's range. | **Reduce or exit longs.** Do not initiate short from this alone. | A D1 close back above the reversal day's high. | Murphy's key reversal day: wider range and heavier volume increase significance, and outside-day form adds more. Note it is also a bearish engulfing on the candle chart, so the two traditions agree. Nison's rule that a reversal signal should not be used to initiate against the major trend applies. (`murphy_ta` p.99-100; `nison_candlesticks` p.43) | moderate |
| 14 | H1 uptrend, three consecutive long bullish bodies each opening inside the prior body and closing near its high, followed by a fourth bullish bar with a much smaller body and a long upper shadow. | **Do not short. Tighten stops on existing longs** and stop adding. | H1 close above the fourth bar's high resumes the sequence. | Three white soldiers degrading into an advance block / stalled pattern. Nison is explicit that these are for protecting or liquidating longs, not for initiating shorts. (`nison_candlesticks` p.108) | moderate |

---

## Learning outcome

After this topic the model must be able to: (1) describe any single closed bar numerically —
body fraction, shadow proportions, close location in range, direction — *before* naming it,
and refuse to name it when the geometry does not meet the stated thresholds; (2) attach a
reversal label only after verifying prior-trend direction and only once every constituent
bar has closed; (3) convert a completed pattern into an explicit support or resistance
level with a close-based invalidation price, and choose between entering at the completing
close versus waiting for a retest based on distance-to-invalidation; (4) state, for any
pattern it emits, which of Nison's confirmation requirements apply, whether Brooks's
trend-line-break precondition is satisfied, and whether the setup is a first or second
signal. It must also be able to explain, unprompted, why the same geometry can be a hammer,
a hanging man, or a trap.

---

## Implementation

All fields computable from closed OHLCV bars plus a session clock.

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `body` | `abs(close - open)` | all | — |
| `range` | `high - low` | all | Guard `range == 0` (possible on M1 in thin Asia). |
| `body_fraction` | `body / range` | all | Primary conviction measure; supersedes doji/spinning-top/marubozu names. |
| `direction` | `sign(close - open)` | all | 0 for exact doji. |
| `upper_shadow` | `high - max(open, close)` | all | — |
| `lower_shadow` | `min(open, close) - low` | all | — |
| `upper_shadow_frac` / `lower_shadow_frac` | shadow ÷ `range` | all | — |
| `close_location` | `(close - low) / range` | all | Grimes's conviction proxy; 0 = closed on low, 1 = on high. (`grimes_art_science` p.40) |
| `shaved_top` / `shaved_bottom` | `upper_shadow <= tick` / `lower_shadow <= tick` | all | Nison's shaven head/bottom; Brooks's shaved body. |
| `is_doji` | `body <= max(2*tick, 0.05 * median_range_20)` | all | Threshold is relative, per Nison's rule that a near-doji only counts when it stands out against recent bodies. (`nison_candlesticks` p.164) |
| `doji_is_unusual` | `count(is_doji, last 10 bars) <= 2` | all | Suppress the label when the chart is already full of doji. |
| `doji_subtype` | gravestone if `lower_shadow_frac < 0.05` and `upper_shadow_frac > 0.6`; dragonfly if mirrored; long_legged if both shadows > 0.3 | all | (`nison_candlesticks` p.170) |
| `is_hammer_shape` | `lower_shadow >= 2 * body` AND `upper_shadow <= 0.5 * body` AND `close_location >= 0.6` | all | Shape only — no directional claim yet. (`nison_candlesticks` p.45) |
| `is_star_shape` | mirror of `is_hammer_shape` (long upper shadow, body low in range) | all | Shooting star or inverted hammer depending on `prior_trend`. |
| `prior_trend` | sign of `close[-1] - close[-N]` with N=10, plus fraction of last N closes above/below a 20-EMA | all | Murphy's chapter recommends a short moving average, around ten periods, precisely for this. (`murphy_ta` p.279) |
| `trend_extension` | count of new N-bar extremes in the last 30 bars, resetting on a >3-bar counter move | H4/H1 | Nison's record-session count; guidepost 8–10. (`nison_beyond` p.132) |
| `pattern_label` | rule cascade applied only when all constituent bars are closed | all | Emit `null` rather than a guess. |
| `pattern_complete` | bool — every bar in the window has `bar_closed == true` | all | Hard gate; no provisional labels. |
| `engulfing` | `body[t]` fully covers `body[t-1]`; opposite `direction`; `prior_trend` opposes `direction[t]` | all | Shadows ignored by design. (`nison_candlesticks` p.53) |
| `engulf_strength` | `body[t] / body[t-1]`, plus `body_fraction[t-1] < 0.3` flag, plus `rel_volume[t]` | all | Nison's three enhancers. (`nison_candlesticks` p.54) |
| `dark_cloud_penetration` | `(open[t-1] + close[t-1])/2` vs `close[t]`, expressed as fraction of `body[t-1]` covered | all | Report the fraction; do not binarise at 0.5. (`nison_candlesticks` p.62) |
| `piercing_penetration` | mirror of above | all | Require > 0.5 or downgrade to thrusting. (`nison_candlesticks` p.66) |
| `harami` | `body[t]` entirely inside `body[t-1]`; `body[t-1]` above 80th percentile of last 20 bodies | all | Bodies only, not ranges. (`nison_candlesticks` p.91) |
| `tweezer` | `abs(high[t] - high[t-1]) <= tick` (or lows) | all | Only emit if a named candle signal also fires — Nison says matching extremes alone are not meaningful intraday. (`nison_candlesticks` p.97) |
| `star_middle_ok` | `body_fraction[t-1] < 0.3` | all | Overlap tolerated on intraday XAUUSD per Nison's FX/intraday exception. (`nison_candlesticks` p.73-74) |
| `star_third_depth` | fraction of `body[t-2]` retraced by `close[t]` | all | Score it; the depth matters more than any gap. |
| `pattern_support` / `pattern_resistance` | `min(low)` / `max(high)` across the pattern's bars | all | Persist as a level object with a creation timestamp. (`nison_candlesticks` p.55, p.73, p.77) |
| `level_violated` | a *closed* bar's close beyond the stored level | all | Close-based only, per Nison's reading of "surpassed". (`nison_candlesticks` p.23) |
| `is_window` | `low[t] > high[t-1]` (rising) or `high[t] < low[t-1]` (falling) | all | Shadow-based, not body-based. (`nison_candlesticks` p.136) |
| `window_zone` | `[high[t-1], low[t]]` for a rising window | all | Whole zone is support; far edge is the invalidation. (`nison_candlesticks` p.138) |
| `window_is_session_boundary` | bar index is the first of a new broker day, or the Sunday reopen | M1–H1 | On XAUUSD nearly all intraday windows will be of this kind. (`nison_candlesticks` p.138) |
| `rel_volume` | `volume[t] / median(volume, 20)` on the same timeframe *and* same session bucket | all | **Flag:** XAUUSD spot volume is broker tick-count, not true traded volume. Coulling's and Nison's volume rules were written for exchange volume. Treat every volume-conditioned rule as one grade weaker. |
| `effort_result_anomaly` | `range[t] > 2 * median_range_20` AND `rel_volume[t] < 0.8` | all | Coulling's anomaly test; drives the NFP long-legged-doji skip. (`couling_volume` p.11, p.81) |
| `signal_bar_ok` (Brooks gate) | `close` beyond bar midpoint in the intended direction; countertrend tail between ~0.3 and ~0.5 of range; opposite tail small; overlap with prior bar below ~0.5 of range | M15/M5 | Hard gate on any countertrend entry. (`brooks_reversals` p.62) |
| `trendline_broken` | a closed bar's close beyond a fitted swing-to-swing trend line on the parent timeframe | H4→H1, H1→M15 | Brooks's precondition for considering any countertrend signal. (`brooks_reversals` p.74) |
| `is_second_signal` | a same-direction setup at the same level within ~10 bars of a failed first | all | Weight higher than the first. (`brooks_reversals` p.21, p.64) |
| `session` | UTC hour bucket → asia / london / overlap / ny / off | all | — |
| `feed_boundary_utc` | broker's D1 rollover hour | D1 | **Flag:** must be recorded with every D1 pattern. Grimes's objection means D1 candle labels on XAUUSD are only valid relative to a stated boundary. (`grimes_art_science` p.29) |
| `oscillator_presignal` | RSI(14) > 70 / < 30, or stochastic %D > 80 / < 20 | H1/H4 | Optional Morris filter: only act on reversal candle patterns while in the pre-signal band. (`murphy_ta` p.284-285) |

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Nison:** candle patterns are the fastest available reversal signal and can flag a turn within one session (`nison_candlesticks` p.38); the shape itself carries the information. | **Grimes:** a naive statistical test of that same geometry — e.g. candles with long lower shadows — would find no predictive power; the geometry only matters conditioned on higher-timeframe context (`grimes_art_science` p.51). Markets are mostly random and most patterns they produce are random too (p.30). | Adopt Grimes's framing as the default. A pattern label alone is never a trade. Emit patterns as *features*, and require a location + prior-trend + (where possible) volume condition before any label contributes to a decision. Cap standalone-pattern evidence at `weak`. |
| **Nison / Coulling / Murphy-Morris:** the close is the pivotal price, "the rudder of the session", and the whole pattern taxonomy is built on it (`nison_candlesticks` p.39-40; `murphy_ta` p.276). | **Grimes:** intraday closes are essentially random samples of the session and differ across data providers; the patterns you see are artefacts of your feed (`grimes_art_science` p.29). | Both are partly right and the resolution is procedural. Keep close-based rules — they are what the corpus actually teaches — but (a) pin one feed and one D1 boundary, (b) record `feed_boundary_utc` with every D1 label, (c) prefer patterns whose validity survives a ±1-bar timestamp shift, and (d) never build a rule that depends on a body/no-body distinction of a few ticks. |
| **Nison:** a hammer needs no confirmation and can be acted on at its own close; only the hanging man and inverted hammer need a confirming bar (`nison_candlesticks` p.45, p.49, p.87). | **Brooks:** *any* countertrend entry requires both a prior trend-line/channel break and a strong signal bar; without those, an apparently strong reversal bar in a tight channel is a trap and the correct trade is the other way (`brooks_reversals` p.74-75, p.80; `brooks_ranges` p.48). | Brooks's gate wins for intraday execution because it is the stricter and the more mechanically testable. Implement: hammer at a level with `trendline_broken == true` → tradable at the close; hammer at a level with `trendline_broken == false` → downgrade to "watch", and check the trap pattern instead. Nison's no-confirmation allowance survives only on D1/H4 at a major level. |
| **Nison:** an ideal morning/evening star has gaps around the middle bar, but the gaps are not necessary; overlap does not weaken it, and he explicitly relaxes the rule for FX and intraday charts (`nison_candlesticks` p.73-74, p.78). | **Murphy / Morris:** the canonical evening star gaps up into the star and gaps down out of it, and closes below the midpoint of bar 1; deviations are accepted by "many references" but are hard for a computer to encode (`murphy_ta` p.281-282). | Use Nison's relaxed definition — XAUUSD intraday is exactly the case he carved out. Encode the strict version as a separate `star_is_classic` boolean so the difference stays measurable rather than being silently absorbed. |
| **Nison:** doji reliably call tops but "tend to lose reversal potential in downtrends"; a doji in a decline needs more confirmation than one in a rally (`nison_candlesticks` p.165). He immediately concedes this is his personal experience. | **Coulling:** the long-legged doji signals a potential reversal in either direction, and the direction is set by the preceding trend, not by an inherent top/bottom asymmetry (`couling_volume` p.81). | This is a genuine, untested asymmetry claim from one author. Do not encode a directional prior on doji. Encode instead the two things both authors agree on — preceding trend sets direction, and confirmation is required — and log the Northern/Southern distinction as an observation to be measured later. |
| **Coulling:** a shooting star or hammer is never contradicted by volume; volume only scales how far the resulting move travels (`couling_volume` p.79). | **Brooks:** he does not find volume reliable enough to warrant his attention at all, and treats the same long-tailed bars in a strong channel as traps that lead the *opposite* way (`brooks_ranges` p.20, p.48). Nison sits in between: volume confirms, and a high-volume hammer specifically reduces the chance of a pullback to the hammer's low (`nison_candlesticks` p.243-245). | Coulling's "never an anomaly" claim is too strong and is untestable as stated. Adopt Nison's narrower, falsifiable version: high `rel_volume` on a hammer/engulfing raises confidence and permits entry at the close rather than at the retest. Keep Brooks's trap check as an overriding veto. Downgrade all XAUUSD volume rules one grade because spot volume is tick-count. |
| **Coulling:** VPA is an art, is inherently subjective, and cannot work in software — a program has no subjectivity, so it can never do this (`couling_volume` p.34). **Nison** makes the compatible point that pattern recognition is subjective enough that computer identification is genuinely difficult (`nison_candlesticks` p.69; `nison_beyond` p.154). | **Chan / Grimes / the premise of this project:** rules must be explicit and testable, and an edge must be verifiable (`grimes_art_science` p.12). | Resolve by making the subjectivity explicit rather than pretending it is absent. Where the books use a judgement word ("unusually long", "deeply into", "well off"), replace it with a *scored continuous field* plus a threshold that is recorded as a tunable parameter, never with a silent binary. That preserves the authors' gradation while remaining machine-executable. |
| **Nison:** a bearish engulfing is by definition a top reversal and requires a preceding rally; the same shape after a decline is not one (`nison_candlesticks` p.78). | **Nison (Beyond Candlesticks):** the same shape in the wrong trend context is a *last engulfing* pattern and may be an exhaustion signal in the opposite direction, confirmed by a close beyond the engulfing bar's close (`nison_beyond` p.93). | The author contradicts himself across books. Resolve conservatively: emit `engulfing_wrong_context` as a distinct, low-weight label rather than either suppressing it or treating it as a reversal. Require the confirming close Nison specifies before it influences anything. |

---

## Gaps

Nothing in the corpus covers these, and they are all first-order for an XAUUSD intraday bot:

- **Base rates.** Not one book in the corpus reports a hit rate, expectancy, or sample size
  for any candlestick pattern. Murphy's chapter is written by Morris and cites no statistics.
  Nison offers charts and experience. Grimes is the only author who even frames the question
  and he answers it negatively for isolated geometry. Every pattern rule here is therefore at
  best `moderate` and needs empirical validation on XAUUSD before it is allowed to size risk.
- **Instrument specificity.** No source studies gold. Nison's examples are US equities,
  indices and crude; Brooks trades the Emini; Coulling uses equities and futures with true
  volume. Gold's 23-hour session, its Asia-session character, and its sensitivity to real
  yields and USD are absent from every source's reasoning about candle formation.
- **The D1 boundary problem for spot.** No book defines what a "daily candle" is for a
  24-hour OTC instrument. Grimes raises the problem (p.29) but offers no remedy. The bot
  must pick a convention and defend it; the corpus cannot help.
- **Threshold calibration.** "At least twice the body", "more than halfway", "unusually long",
  "well off its highs" — none of these are calibrated to volatility, timeframe, or instrument.
  A 2× lower-shadow rule on M1 XAUUSD and on D1 XAUUSD are not the same test.
- **Volume proxy validity.** Every volume rule in Coulling and Nison assumes exchange volume.
  Whether broker tick-count on XAUUSD is an adequate proxy is untested anywhere in the corpus.
- **Multiple-testing / pattern-mining risk.** Murphy's chapter lists roughly forty reversal
  and sixteen continuation patterns. No source addresses what happens to false-positive rates
  when you scan that many templates across seven timeframes. Chan is the only corpus author
  with the statistical machinery to address it and he never applies it to candlesticks.
- **Interaction with algorithmic execution.** All these patterns were described before
  execution algorithms dominated. Whether "the open and close are the two most emotionally
  charged points" still holds on a 24-hour OTC instrument in 2026 is not addressed.
- **Concurrent-pattern conflict resolution.** The books never say what to do when a bullish
  pattern on M15 sits inside a bearish pattern on H1. Nison's convergence chapters combine
  candles with Western tools, not candles with candles across timeframes.

---

## JSONL seeds

```json
{"principle_id":"candle_geometry_before_names","topic":"candlestick_patterns","lesson":"A bar's body fraction, shadow proportions and close location carry the information; the pattern name is only a label attached afterwards.","practice":"For every closed bar emit body, range, body_fraction, upper/lower_shadow_frac, close_location and direction, then attach pattern_label as an extra field or null.","guardrail":"Never emit a pattern name without the underlying geometry fields alongside it.","evidence_label":"strong"}
{"principle_id":"pattern_requires_prior_trend","topic":"candlestick_patterns","lesson":"Identical geometry is a hammer after a decline and a hanging man after a rally; the reversal label is a claim about the preceding trend, not about the bar.","practice":"Compute prior_trend over the last 10 closes plus position relative to a 20-EMA before assigning any reversal label; if prior_trend is flat, emit a neutral geometry description instead.","guardrail":"No bullish reversal label in an uptrend and no bearish reversal label in a downtrend.","evidence_label":"strong"}
{"principle_id":"pattern_completion_on_close","topic":"candlestick_patterns","lesson":"A multi-bar candle pattern does not exist until its final bar has closed, because the pattern is defined by that close.","practice":"Gate every multi-bar label on pattern_complete == true; two-bar patterns wait for bar 2's close, three-bar patterns for bar 3's.","guardrail":"Never label or act on a still-forming bar, and never revise a label retroactively as a new bar prints.","evidence_label":"strong"}
{"principle_id":"pattern_becomes_a_level","topic":"candlestick_patterns","lesson":"The durable output of a completed reversal pattern is a price level: the pattern's lowest low is support and its highest high is resistance.","practice":"On completion, persist pattern_support or pattern_resistance with a creation timestamp, and evaluate breaches only on closed-bar closes.","guardrail":"A single intrabar poke through the level does not invalidate it; only a close beyond it does.","evidence_label":"moderate"}
{"principle_id":"wait_for_retest_when_extended","topic":"candlestick_patterns","lesson":"When a pattern completes far from its own invalidation level, the risk/reward at the completing close is poor even though the pattern is valid.","practice":"If distance from the completing close to the pattern's extreme exceeds a preset multiple of ATR, place a limit order back toward the pattern's extreme instead of entering at the close.","guardrail":"If price closes beyond the pattern's extreme while waiting, cancel the order — the setup is dead, not cheaper.","evidence_label":"moderate"}
{"principle_id":"confirmation_asymmetry","topic":"candlestick_patterns","lesson":"Hanging man and inverted hammer contain a countertrend shadow that argues against their own signal, so they require a confirming next bar; hammer and shooting star do not.","practice":"For a hanging man require the next closed bar to close below its real body; for an inverted hammer require the next closed bar to close above its real body.","guardrail":"If the confirming bar closes the other way, the pattern is cancelled outright, not merely weakened.","evidence_label":"moderate"}
{"principle_id":"trendline_break_precondition","topic":"candlestick_patterns","lesson":"A reversal-shaped bar inside a strong trend that has not yet broken its trend line is more often a trap than a turn.","practice":"Require trendline_broken == true on the parent timeframe plus a signal bar that closes beyond its own midpoint before taking any countertrend candle signal.","guardrail":"A large bar with a small body and a long countertrend tail in a tight channel with no trend-line break is a short-with-trend setup, not a reversal.","evidence_label":"moderate"}
{"principle_id":"prefer_second_signal","topic":"candlestick_patterns","lesson":"A second reversal attempt at the same level on the same logic within a few bars is materially more reliable than the first.","practice":"Track failed setups by level; when a same-direction setup recurs at that level within about ten bars, raise its weight and allow a tighter stop behind the second signal bar.","guardrail":"Do not average into the first failed attempt; treat the second signal as a fresh trade with its own invalidation.","evidence_label":"moderate"}
{"principle_id":"window_as_zone_not_line","topic":"candlestick_patterns","lesson":"A true gap requires no shadow overlap, and the whole gap is a support or resistance zone whose far edge is the invalidation.","practice":"Detect windows from low[t] > high[t-1] or high[t] < low[t-1]; store the zone; buy dips into a rising window and sell bounces into a falling one.","guardrail":"A gap between bodies alone is not a window, and a close beyond the far edge voids it regardless of how large the window was.","evidence_label":"moderate"}
{"principle_id":"suppress_uninformative_indecision","topic":"candlestick_patterns","lesson":"A doji or spinning top carries no information when the surrounding bars are already small-bodied and overlapping.","practice":"Suppress doji and spinning-top labels when more than two of the last ten bars already qualify, or when the last three or more bars overlap heavily.","guardrail":"In an overlapping small-bar cluster, never buy the cluster's high or sell its low.","evidence_label":"strong"}
{"principle_id":"volume_scales_not_creates","topic":"candlestick_patterns","lesson":"Volume changes how much weight a candle signal deserves; it does not create a signal where the geometry and location give none.","practice":"Compute rel_volume against a same-session 20-bar median; raise confidence on a hammer or engulfing with a spike, and flag an effort/result anomaly when a wide range prints on below-average volume.","guardrail":"Treat all XAUUSD volume conclusions one evidence grade weaker because broker tick-count is not true traded volume; skip wide-range low-volume bars around scheduled news entirely.","evidence_label":"weak"}
{"principle_id":"pattern_label_is_feed_dependent","topic":"candlestick_patterns","lesson":"Candlestick patterns depend on the close, and on a 24-hour OTC instrument the close is a convention rather than a fact, so labels vary by data feed and daily boundary.","practice":"Pin one feed and one D1 rollover hour, record feed_boundary_utc alongside every D1 pattern label, and avoid rules that hinge on a few ticks of body.","guardrail":"Never claim a pattern-based edge that has not been shown to survive a one-bar timestamp shift.","evidence_label":"moderate"}
```
