# Topic 5 — ICT Concepts, Translated Into the Literature That Supports Them

> **Sources read:** `chan_algo_trading` p.184–186; `lien_fx_sessions` p.83–89, 131–141;
> `murphy_ta` p.69–76, 104, 126–127; `grimes_art_science` p.115–117, 137–149, 160–163,
> 199–204, 352–360; `brooks_trends` p.17, 21, 24, 154, 356, 415–417; `brooks_reversals`
> p.13–18, 57, 237–240, 272–275, 368–373, 446, 454; `brooks_ranges` p.67, 78–81, 195,
> 217–218; `dalton_mind_over_markets` p.31–34, 38–41, 66, 83–89, 188–190, 257–258;
> `dalton_markets_in_profile` p.103–106, 181–183; `dalton_markets_momentum` p.110–112,
> 248; `couling_volume` p.63–72, 82–83, 107; `nison_beyond` p.100; `person_pivots` p.122
> **Status:** v2 full-corpus distillation, 2026-08-08 (supersedes v1 in its entirety)

---

## Framing: why this topic is written differently

There is **no ICT primary text in the corpus**, and — as far as this distillation can
establish — **no rigorous published test of any ICT-specific construct exists in either
direction**. Absence of a test is not evidence of falsehood; it is simply absence of a test.
So this file does not teach ICT doctrine and does not debunk it either.

It does something more useful. For every ICT term the operator's vocabulary contains, it
identifies the **ancestor or equivalent concept in the serious literature that IS on disk**,
translates the ICT word into that better-founded language, and states plainly what part of
the claim is mechanically supported and what part is decoration.

Verification that the vocabulary is genuinely absent: a case-insensitive scan of all 18
corpus files for `order block`, `breaker`, `fair value gap`, `liquidity sweep`,
`liquidity grab`, `Judas`, `smart money concept`, `break of structure`, `mitigation block`,
`displacement`, `premium and discount`, `optimal trade entry`, `internal range` returns
**zero hits** for every one of them. (`change of character` appears exactly once as a real
technical term — Grimes p.160 — and that is the honest ancestor of CHoCH, discussed below.)
The mechanics, however, are everywhere. The books just call them traps, failed breakouts,
springs, poor highs, excess, opening reversals and stop running.

Three consequences for the bot:

1. **ICT words are allowed in narrative output only when they are aliases** for a rule that
   is already defined on closed bars. They may never be the reason for a decision.
2. **Every ICT-specific term carries `untested` or `weak`.** Each entry below states the
   exact measurement on the tick archive that would upgrade it.
3. **The mapped ancestor carries its own honest label**, which is usually `moderate` and
   occasionally `strong` — never higher just because it is older.

---

## Core concepts

| Concept | Definition (one line, my words) | Sources (slug p.N) | Evidence |
|---|---|---|---|
| **Stop clustering beyond extremes** | Protective stops congregate just past visible highs, lows and range boundaries, because that is where a position is objectively wrong. | `dalton_markets_in_profile` p.181; `dalton_markets_momentum` p.110; `brooks_reversals` p.272–275; `chan_algo_trading` p.185 | **strong** |
| **Take-profit clustering AT round numbers** | Humans set targets on round figures, so resting limit orders pile up on the round number itself while stops sit a little past it. | `lien_fx_sessions` p.131–132; `murphy_ta` p.74–75; `brooks_reversals` p.446, 454 | **strong** |
| **Stop-triggered acceleration** | Once price crosses the level, the resting stops convert to market orders in one direction, producing a short burst of continuation with no new information behind it. | `chan_algo_trading` p.185–186 (cites Osler 2000/2001); `dalton_markets_momentum` p.110 | **strong** |
| **Failed breakout / trap** | Price closes beyond a level, fails to attract follow-through, and returns inside; traders who entered on the break are now forced sellers/buyers. | `grimes_art_science` p.146–149, 199–203; `murphy_ta` p.126; `brooks_ranges` p.104–105, 217–220 | **strong** |
| **Failure test** | A single-bar version of the above: the bar pokes past the level and closes back inside. Grimes states outright that a failure test *is* a failed breakout on a lower timeframe. | `grimes_art_science` p.353, 358–359 | **moderate** |
| **Spring / upthrust** | The Wyckoff-tradition name for the same event at range extremes; the sweep is the entry, not the signal. | `grimes_art_science` p.354; `couling_volume` p.63–72 | **moderate** |
| **Excess** | An auction that terminates with a long tail/spike has *finished*; an auction that terminates flat has not. | `dalton_markets_in_profile` p.103–106 | **moderate** |
| **Poor high / poor low** | A session extreme with no tail — auction incomplete — which the market tends to return to and take out later, sometimes days later. | `dalton_mind_over_markets` p.257–258; `dalton_markets_momentum` p.248 | **moderate** |
| **Role reversal (change of polarity)** | A level that breaks decisively flips function, because the participants who transacted there now have the opposite vested interest. | `murphy_ta` p.69–74; `grimes_art_science` p.115–116; `nison_beyond` p.100; `brooks_ranges` p.67; `person_pivots` p.122 | **strong** (mechanism) / **moderate** (as a trade) |
| **Signal bar of a failed reversal** | The bar that generated a losing entry becomes a durable magnet for later moves — the closest true ancestor of "order block". | `brooks_ranges` p.79–80; `brooks_trends` p.24 | **weak** |
| **Initiative vs responsive activity** | Activity above prior value that pushes further is initiative (someone with conviction); activity that only responds to a price probe is responsive. | `dalton_mind_over_markets` p.66 | **moderate** |
| **Micro measuring gap** | A three-bar structure where the bars either side of a strong trend bar do not overlap — Brooks's ancestor of the fair value gap. He uses it to *project targets*, not as a zone to buy. | `brooks_reversals` p.17, 57, 106 | **moderate** |
| **Change of character** | The established swing rhythm breaks: e.g. a countertrend swing larger than any recent with-trend swing. | `grimes_art_science` p.160–161 | **moderate** |
| **Initial balance / opening range** | The range built in the first block of a session; later trade is classified as extension above or below it. | `dalton_mind_over_markets` p.31–34, 39; `brooks_trends` p.356, 415–417 | **moderate** |
| **Open-Test-Drive** | Session opens, probes beyond a known reference to confirm nothing is there, reverses back through the open and drives — the literature's Judas swing, with a mechanism and no villain. | `dalton_mind_over_markets` p.85–87 | **moderate** |
| **Value area / value-area rule** | The band containing the bulk of a session's volume; re-entry and acceptance inside it implies traversal to the far side. | `dalton_mind_over_markets` p.188–190 | **moderate** |

### The ICT → literature mapping

| ICT term | Best ancestor in corpus | What survives translation | ICT label | Ancestor label |
|---|---|---|---|---|
| Liquidity sweep / stop hunt / liquidity grab | Failed breakout (Grimes p.199–203), bull/bear trap (Brooks, Murphy p.126), spring/upthrust (Grimes p.354), stop running (Dalton MiP p.181) | Stops really do cluster past visible extremes and really do accelerate price when hit. Everything else — intent, targeting, a specific actor — is unsupported. | **weak** | **strong** |
| Liquidity pool / equal highs & lows | Poor high / poor low (Dalton MoM p.257–258), double top/bottom (Brooks p.281–282) | Flat, tail-less extremes get revisited because the auction never completed. This is the honest version of "resting liquidity". | **weak** | **moderate** |
| Order block | Signal bar of a failed reversal as magnet (Brooks ranges p.79–80); origin of initiative activity (Dalton MoM p.66); accumulation/distribution zone (Coulling p.63–72, 107) | The bar an impulse started from is a real reference level, mostly because it is where the last group of losers entered. There is no evidence the *last opposing candle specifically* is privileged over the whole base. | **untested** | **weak** to **moderate** |
| Breaker block | Role reversal / change of polarity (Murphy p.69–74; Nison p.100; Grimes p.115–116) | Broken levels flip function; the psychology (Murphy p.70–72) is the mechanism. ICT's extra requirement that the level must first have *failed as an order block* adds no evidence. | **untested** | **strong** (mechanism) |
| Fair value gap / imbalance | Micro measuring gap (Brooks reversals p.17, 57); excess gap (Dalton MiP p.105–106) | Non-overlapping three-bar structures mark genuinely fast, one-sided trade. Brooks uses them to *project*; Dalton reads a gap as excess, i.e. an ending, not an entry. Neither treats them as reliable retest zones. | **untested** | **moderate** |
| Break of structure (BOS) | Swing-high/low break as trend continuation (Grimes p.138–140, 163); initiative range extension (Dalton MoM p.66) | Definitionally true: a trend up must take out prior highs. As a *signal* it is weak, because most breakouts fail (Grimes p.139, 163). | **weak** | **moderate** |
| Change of character (CHoCH) | Change of character (Grimes p.160–161); trend-termination-into-range (Grimes p.138) | Grimes gives a computable version: a countertrend swing larger than the recent with-trend swings. That is the definition to use. | **weak** | **moderate** |
| Displacement | Breakout spike / initiative activity (Brooks trends p.357; Dalton MoM p.66, 87) | Real and measurable as body-to-ATR and follow-through. The word adds nothing. | **weak** | **moderate** |
| Premium / discount / equilibrium | Range midpoint and directional probability (Brooks ranges p.79); 50% retracement (Murphy p.143–145, 151); value area (Dalton MoM p.188–190) | Brooks's version is strictly better: at the range midpoint directional probability is ~50%, and it improves toward the extremes. Same geometry, honest probability statement attached. | **untested** | **moderate** |
| Mitigation / return to zone | Pullback to breakout level (Grimes p.358); earlier entry price as target (Brooks ranges p.79–80) | Grimes explicitly warns the retest may violate, stop at, or never reach the level — "there is nothing magical about the breakout level" (p.358). | **untested** | **weak** |
| Inducement | Trapped traders as fuel (Grimes p.161, 353; Brooks reversals p.272) | The energy from trapped traders is real. The claim that a specific prior level was *created in order to* trap them is not testable from OHLCV. | **untested** | **moderate** |
| Judas swing / session-open false move | Open-Test-Drive and Open-Rejection-Reverse (Dalton MoM p.85–88); opening reversal (Brooks trends p.21, reversals p.368–372); "waiting for the real deal" (Lien p.136–138) | Lien published essentially this pattern in 2008 with an explicit rule and an explicit dealer-flow rationale. Dalton gives the auction-theory version with no villain. Both are far more precise than the ICT telling. | **untested** | **moderate** |

---

## What is actually supported

These are the load-bearing claims. Each one is mechanical, and each one is stated by more
than one independent source or by peer-reviewed research the corpus cites.

1. **Stops cluster just beyond visible extremes.** Dalton states it as a definitional
   consequence of the level being visible (`dalton_markets_in_profile` p.181: balance areas
   are *by definition* visual, so stops sit just past their extremes). Brooks describes the
   same placement from the trader's side (`brooks_reversals` p.272–275; `brooks_ranges` p.94,
   206). Dalton names the resulting behaviour explicitly — "gunning for stops" — and lists
   the reference points that attract it: multi-day, monthly, weekly and yearly extremes, and
   trend lines (`dalton_markets_momentum` p.110). **Evidence: strong.**

2. **Take-profit orders cluster AT round numbers; stop orders cluster JUST BEYOND them.**
   This is the single most important asymmetry in this topic, and Lien states it directly
   (`lien_fx_sessions` p.131–132). The two clusters produce *opposite* price effects:
   the take-profit wall at the figure produces a **reversal**; the stop cluster past the
   figure produces **acceleration** once breached. Murphy independently gives the same
   order-placement advice from the other direction — put limits just inside round numbers,
   put protective stops away from them (`murphy_ta` p.75) — and his worked example of the
   phenomenon is **gold** ($300, $400, $500 acting repeatedly as barriers, p.75).
   **Evidence: strong.**

3. **Stop-triggered acceleration is a documented, published effect.** Chan cites Osler
   (2000, 2001) — the working papers behind Osler's *Journal of Finance* (2003) and *JIMF*
   (2005) work on real bank order data — for the finding that once support or resistance is
   breached, price continues in the breach direction for a while, driven by the stop orders
   populating round numbers near the market (`chan_algo_trading` p.185–186). He classifies
   "stop hunting" as a *high-frequency momentum strategy*, i.e. as a real, exploitable
   microstructure effect. **This is the genuine mechanism.** Note carefully what it does not
   require: no intent, no coordination, no "smart money hunting retail". Ordinary
   participants placing ordinary orders at ordinary places is sufficient.
   **Evidence: strong.**

4. **Most breakouts fail.** Grimes says it flatly and repeatedly (`grimes_art_science`
   p.139: "the majority of breakout trades fail"; p.163: "breakout failures are far more
   common than successful breakouts"; p.200: the concept heading of the failed-breakout
   template is literally *most breakouts fail*). Brooks builds a whole scalping regime on
   the same base rate (`brooks_reversals` p.368: scalpers bet that breakout attempts will
   usually fail). Murphy names the outcome a bull trap (`murphy_ta` p.126). **Evidence:
   strong.** This is the real content of "liquidity sweep": it is the base rate of breakout
   failure, observed at a level where the failure is conspicuous.

5. **Broken levels reverse their role, and the reason is inventory, not magic.** Murphy's
   four-group psychology (`murphy_ta` p.70–72) is the mechanism: everyone who transacted at
   the level has a vested interest in it, and when price passes decisively through, all of
   those resting buy interests become resting sell interests. Grimes p.115–116, Nison p.100
   ("change of polarity"), Brooks ranges p.67 and Person p.122 all state the same effect
   independently. **Evidence: strong** for the mechanism.

6. **The significance of a level scales with time spent there, volume transacted there, and
   recency.** Murphy states all three (`murphy_ta` p.71). Dalton's entire value-area
   apparatus is the volume version of the same idea. This gives a *ranking function* for
   candidate levels, which the naive ICT framing lacks.

7. **A session's high or low usually forms early.** Dalton reports that the opening half hour
   produces one of the session's two extremes far more often than not (`dalton_mind_over_markets`
   p.83). Brooks puts an Emini number on the same tendency: about half of all sessions set
   their extreme inside the first five bars, and within the opening range — which can run a
   couple of hours — roughly 90% of the time (`brooks_trends` p.416). **Evidence: moderate**
   (single-instrument, single-era, author-reported).

8. **The disambiguation rule for a level breach is follow-through, not intent.** Both Dalton
   passages give the *same* rule independently: if the move beyond the reference dries up
   immediately, it was a stop run and price returns; if activity persists and price settles
   out there, it is a real breakout (`dalton_markets_in_profile` p.182; `dalton_markets_momentum`
   p.110–111). **Evidence: strong** — two independent statements, and it is the only part of
   the sweep story that is actually decidable from data.

---

## What is folklore

Not "false" — **unsupported by anything in this corpus, and untested anywhere I can find.**
The bot must not treat any of these as a reason.

1. **That a specific actor is hunting a specific pool.** The strongest version of intent
   anywhere in the corpus is Coulling (`couling_volume` p.16, 82–83), who asserts market
   makers and insiders "rack" price around news to shake traders out. Coulling asserts this;
   she does not test it. Grimes takes the opposite view of the same tape — that markets are
   highly random and very close to efficient (`grimes_art_science` p.162) — and Brooks
   explicitly rejects the naive version: he asks why smart money is not gunning an obvious
   cluster of stops one tick below an entry bar, and answers that they are not, because if
   those stops were hit the chart's character would change and the setup would no longer be
   what it appeared (`brooks_ranges` p.195). The intent narrative is **untested**; the order
   *clustering* is `strong`. Keep them separated.

2. **That the "last opposing candle before the impulse" is privileged.** Nothing in the
   corpus singles out that bar. Brooks's closest analogue is the *signal bar of a failed
   reversal* (`brooks_ranges` p.79–80), which is a different bar chosen by a different rule,
   and he explicitly hedges the explanation — offering scaling-in behaviour, algorithmic
   levels, and trader regret as candidate causes and admitting he does not know which
   (p.79). Dalton would treat the same region as the origin of initiative activity, i.e. a
   *zone* with a volume signature, not a candle. **untested.**

3. **That price must "return to mitigate" an order block or fill an imbalance.** Grimes
   directly contradicts the necessity: the pullback after a breakout can violate the level,
   stop at it, or hold well clear of it, and "there is nothing magical about the breakout
   level" (`grimes_art_science` p.358). He goes further and calls the plan of flipping
   position on a breakout-level violation *futile* (p.200). Brooks's measuring gaps are used
   to project targets, not as return zones (`brooks_reversals` p.57). **untested, and there
   is corpus evidence pointing the other way.**

4. **That the session-open move is systematically the false one.** Dalton's Open-Drive is
   the direct counterexample: in the majority of Open-Drive cases the opening extreme holds
   for the entire day (`dalton_mind_over_markets` p.83). Brooks quantifies the other side —
   only about one session in five has its extreme set by the very first bar
   (`brooks_reversals` p.369) — which is a statement that *neither* "the first move is real"
   *nor* "the first move is fake" is a usable prior on its own. **untested as a blanket
   claim.** It becomes tradeable only after the open is *classified*.

5. **That ICT's specific fractal grammar (BOS → CHoCH → OB → FVG → premium/discount) has
   predictive content beyond its parts.** Each part maps to something older. The composition
   has never been tested. **untested.**

6. **Precision.** ICT levels are typically drawn to the tick. Murphy notes there is real
   subjectivity in what counts as significant penetration, and cites benchmarks of roughly
   3% for major levels and about 1% for shorter-term ones (`murphy_ta` p.74). Grimes says
   support and resistance "may or may not be clean, exact levels" (p.163). Dalton works in
   zones. **The tick-precise version is folklore; use bands.**

---

## Distilled rules

Every rule below is computable from closed bars plus a UTC session clock. Sessions:
Asia 00–07, London 08–13, Overlap 13–16, NY 16–21 UTC.

1. **Build the liquidity-reference set before the session, not during it.** At 00:00 UTC
   enumerate: prior day H/L/close, prior week H/L, Asia H/L (once 07:00 closes), London H/L
   (once 13:00 closes), the last 3 M15 swing highs and lows, and the nearest gold round
   numbers at $10 and $50 spacing. These are the only levels the bot may call "liquidity".
   Source: `dalton_markets_momentum` p.110 (which lists exactly this class of references);
   `dalton_markets_in_profile` p.181. Evidence: **strong**.

2. **Rank each reference by Murphy's three factors** — bars spent within 0.1×ATR of it,
   cumulative tick volume transacted there, and recency in bars. Trade only the top-ranked
   references. Source: `murphy_ta` p.71. Evidence: **moderate**.

3. **Never call a breach a "sweep" until the bar that made the breach has closed back inside
   the level.** A breach with a close beyond the level is a breakout candidate, not a sweep.
   Source: `grimes_art_science` p.353 (failure test = failed breakout); `murphy_ta` p.126.
   Evidence: **strong** (definitional).

4. **Disambiguate breach outcomes by follow-through, on a fixed clock, not by narrative.**
   After the first close beyond a reference, wait N bars (N = 3 on M15, 6 on M5). If the
   extension beyond the level in that window is < 0.5×ATR and price has closed back inside →
   classify `failed_breakout` and bias against the breach. If price is still beyond the level
   and has printed a higher low (up-break) or lower high (down-break) → classify
   `accepted_breakout` and bias with the breach. If neither, classify `undecided` and stand
   down. Source: `dalton_markets_in_profile` p.182; `dalton_markets_momentum` p.110–111.
   Evidence: **strong**.

5. **Treat the round number and the zone past it as two different objects with opposite
   expectations.** Fade *into* the round number (resting take-profit wall); expect
   acceleration *past* it. In gold, use the $10 handle as the primary figure and $50/$100 as
   major. Source: `lien_fx_sessions` p.131–132; `chan_algo_trading` p.185; `murphy_ta`
   p.74–75. Evidence: **strong** (mechanism), **weak** (as a standalone gold entry — Lien's
   pip-based sizing does not transfer to XAUUSD without re-fitting).

6. **Do not place the bot's own protective stops on round numbers or exactly at the obvious
   swing extreme.** Push them a configurable buffer beyond. Source: `murphy_ta` p.75 (avoid
   obvious round-number stops); `brooks_ranges` p.218 (the market routinely reaches
   round-number stop distances from entry). Evidence: **moderate**.

7. **Flag flat, tail-less session extremes as `poor_high` / `poor_low` and expect them to be
   revisited — possibly not the same day.** Operational test: the extreme bar's wick beyond
   the body is < 0.15×ATR and ≥ 2 bars closed within 0.1×ATR of the extreme. Source:
   `dalton_mind_over_markets` p.257–258; `dalton_markets_momentum` p.248. Evidence:
   **moderate**.

8. **Conversely, flag extremes with long tails as `excess` and treat them as auction
   endings, not as pools to be raided.** Source: `dalton_markets_in_profile` p.103–106.
   Evidence: **moderate**.

9. **Classify the London open (08:00 UTC) into one of Dalton's four types before forming any
   session bias.** Measured over the first four M15 bars: *Drive* — price never trades back
   through the 08:00–08:15 range and extends ≥ 1.0×ATR(M15) one way; *Test-Drive* — price
   first probes beyond a named prior reference (Asia H/L or prior-day H/L), then closes back
   through the opening range and extends the other way; *Rejection-Reverse* — price moves one
   way without breaching a named reference, then returns through the opening range;
   *Auction* — price oscillates around the opening range with no extension. Source:
   `dalton_mind_over_markets` p.83–89. Evidence: **moderate**.

10. **Only the Test-Drive classification licenses the "session-open false move" narrative,
    and only with a *named* reference that was actually probed.** A reversal that probed
    nothing is a Rejection-Reverse, whose initial extreme holds less than half the time
    (`dalton_mind_over_markets` p.88) — meaning it carries no edge. Evidence: **moderate**.

11. **Under Open-Drive, the opening extreme is a working invalidation level, not a target.**
    Dalton: the extreme left behind by an Open-Drive holds for the entire day in the majority
    of cases, and a return through the opening range is the signal that conditions changed
    (`dalton_mind_over_markets` p.83, 85). Evidence: **moderate**.

12. **Compute equilibrium as the plain midpoint of the named range and attach Brooks's
    probability statement to it, not ICT's.** At the midpoint, directional probability is
    approximately 50%; it improves toward the extremes because that is where participants
    agree price has gone too far (`brooks_ranges` p.79). Therefore: do not initiate at the
    midpoint in either direction. Evidence: **moderate**.

13. **Define CHoCH computably as Grimes does: the first countertrend swing whose magnitude
    exceeds every with-trend swing of the last K swings (K = 3).** Do not use any other
    definition. Source: `grimes_art_science` p.160. Evidence: **moderate**.

14. **Define BOS as a *close* beyond the prior confirmed swing extreme on the stated
    timeframe, and immediately downgrade it**, because most such breaks fail (`grimes_art_science`
    p.139, 163). BOS may raise a flag; it may never open a position alone. Evidence:
    **moderate**.

15. **Where the bot would say "order block", it must instead emit the observable:
    `impulse_origin(tf, bar_index, high, low)` plus the volume transacted in that band.**
    If the band cannot be described by an observable, it does not exist. Source:
    `brooks_ranges` p.79–80; `dalton_mind_over_markets` p.66. Evidence: **weak**.

16. **Where the bot would say "breaker", it must emit `role_reversal(level, break_bar,
    penetration_atr)` with penetration measured in ATR**, and require penetration ≥ 1.0×ATR
    before the flip is recognised. Murphy is explicit that role reversal requires *significant*
    penetration, because the participants must be convinced they were wrong (`murphy_ta`
    p.72, 74). Evidence: **strong** (mechanism) / **moderate** (threshold is a fitted
    parameter, not a book value).

17. **Never require a retest.** After an accepted breakout, permit entry on the first
    pullback whether or not it reaches the breakout level. Source: `grimes_art_science`
    p.358, 200. Evidence: **moderate**.

18. **Stand down in the first 2 minutes after a scheduled release.** Brooks: the minutes
    after a report are dominated by programs with a speed edge, and it is better to wait a bar
    or two (`brooks_reversals` p.369–370). Coulling: a wide-range doji on *low* volume around
    news is an anomaly and a trap, not a reversal signal (`couling_volume` p.82–83).
    Evidence: **moderate**.

19. **Size down when the bars are large.** Brooks is explicit that opening-range bars require
    wider stops and smaller size (`brooks_reversals` p.369). Implement as: position size ∝
    1/ATR(M5, 12), floor and cap applied. Evidence: **moderate**.

20. **Log the ICT alias, never act on it.** Every narrative record carries
    `{observable_rule, ict_alias, evidence_label}`. A decision whose only support is
    `ict_alias` is rejected at the gate. Evidence: **strong** (process control, not a market
    claim).

---

## Worked examples

All restated into XAUUSD intraday terms. "ATR" means ATR(14) on the stated timeframe.

### 1 — Asia high swept at the London open, no follow-through (Test-Drive)
- **Setup:** Asia (00–07 UTC) builds a 9-dollar range. At 08:10 UTC an M15 bar trades $1.40
  above the Asia high and closes $0.90 back inside it. The next two M15 bars close inside the
  Asia range; extension beyond the high never exceeds 0.5×ATR(M15).
- **Decision:** OPEN short on the close of the second inside bar, targeting Asia low.
- **Invalidation:** any M15 close back above the Asia high.
- **Why:** Dalton's disambiguation — activity in the direction of the boundary dried up, so
  the probe was a stop run and price returns into the balance area
  (`dalton_markets_in_profile` p.182). It is simultaneously Grimes's failure test at a level
  (`grimes_art_science` p.353) and a Dalton Open-Test-Drive (`dalton_mind_over_markets` p.85).
- **Evidence:** **moderate** (mapped ancestor). ICT gloss "Asia liquidity sweep": **weak**.

### 2 — Same probe, but price stays out (Open-Drive)
- **Setup:** Identical 08:10 probe above the Asia high, but the bar *closes* above it, the
  next two M15 bars both close above it, a higher low prints, and total extension exceeds
  1.0×ATR(M15) by 09:00.
- **Decision:** OPEN long on the pullback that holds above the Asia high — with the trend, not
  against it.
- **Invalidation:** M15 close back below the Asia high.
- **Why:** Same event, opposite classification. Dalton: when the stops are taken out and the
  market settles there, a genuine balance-area breakout has occurred and you must trade *with*
  it (`dalton_markets_in_profile` p.182). Chan/Osler supplies the microstructure reason the
  first leg is fast (`chan_algo_trading` p.185).
- **Evidence:** **strong** (the branch rule) / **moderate** (the entry).
- **Note:** Examples 1 and 2 are the same first bar. Any system that labels the first bar a
  "sweep" is guessing.

### 3 — Equal highs during the overlap: WAIT
- **Setup:** Three M15 highs within $0.60 of each other form between 13:00 and 14:30 UTC. No
  probe has occurred yet. The bot's narrative layer wants to call this a liquidity pool and
  pre-position short in anticipation of the raid.
- **Decision:** **WAIT.** No position on the anticipation.
- **Invalidation of the wait:** an actual probe closing back inside (→ example 1) or an
  accepted break (→ example 2).
- **Why:** The flat cluster is a Dalton poor high, which does say the level is likely to be
  revisited (`dalton_mind_over_markets` p.257–258) — but "likely to be revisited" is a
  statement about *price reaching there*, not about what happens next. Grimes's rule is that
  the decision comes from what price does at the level, not from the level's shape (p.358).
- **Evidence:** **moderate** for the poor-high read; **untested** for the anticipatory short.

### 4 — Round-number rejection at a gold figure
- **Setup:** Price is trading well below its M15 20-period SMA and grinding down toward a $50
  figure (e.g. 3150.00). No scheduled release within 30 minutes. The figure also coincides
  with the prior week's low.
- **Decision:** OPEN long on a bid a short distance *above* the figure — deliberately not at
  it and not below it.
- **Invalidation:** an M15 close more than 1.0×ATR(M15) below the figure — at which point the
  stop cluster beneath has been activated and Osler-type acceleration is the live scenario.
- **Why:** Take-profit orders pile up *at* the figure and stops sit *just past* it
  (`lien_fx_sessions` p.131–132); Murphy independently recommends resting limits just inside
  round numbers and cites gold's own history at $300/$400/$500 (`murphy_ta` p.74–75); the
  confluence with a real technical level is Lien's own stated filter (p.133).
- **Evidence:** **strong** (mechanism) / **weak** (the entry — Lien's 15/20-pip geometry was
  fitted to 2005 FX majors and must be re-fitted to gold's ATR).

### 5 — Failed breakout of the London high that becomes a breaker: SKIP the first touch
- **Setup:** London high is broken at 15:20 UTC on an M15 close, extension reaches 1.4×ATR,
  price then rolls over and closes back below the London high at 16:10. At 17:00 price rallies
  back up and touches the London high from below.
- **Decision:** **SKIP** the touch itself. Wait for the M15 bar at the level to close, and
  short only if it closes below the level with a lower high already in place.
- **Invalidation:** M15 close back above the London high.
- **Why:** The role reversal is real — broken support/resistance flips function (`murphy_ta`
  p.69–74; `nison_beyond` p.100). But Murphy conditions the flip on penetration being
  *significant enough to convince participants they were wrong* (p.72, 74), and here the
  penetration was undone within the hour, so conviction is weak. Grimes warns that the touch
  itself carries no information (p.358).
- **Evidence:** **strong** (role reversal mechanism) / **moderate** (the skip discipline).
- **ICT alias:** this is the "breaker block". Label **untested**.

### 6 — The pattern FAILS: sweep of Asia low reverses, then keeps going down
- **Setup:** 08:05 UTC, an M5 bar prints $1.10 below the Asia low and closes back inside. The
  bot classifies `failed_breakout` and goes long, stop below the probe low. Two bars later
  price breaks the probe low and runs another 1.8×ATR down without pausing.
- **Decision:** exit at stop. Do not re-enter long. Do not average.
- **Why it failed, per the books:** Grimes explains this exact failure mode — the failed
  breakout is itself a *pullback* pattern, and it fails when strong countertrend momentum
  emerges in the pullback (`grimes_art_science` p.201). He also warns that failed-breakout
  trades expose the account to a tail no one can size in advance, so the stop has to be
  honoured exactly and never averaged into (p.203). Brooks describes the
  same trap from the other side: at a swing low, the push below the bar is a micro *vacuum* —
  price is pulled to the obvious level by a relative absence of opposing orders, and whether
  it snaps back or falls through depends on what is waiting there, which you cannot see
  (`brooks_reversals` p.238). And in this case the second probe was not a probe: it was
  Dalton's "stops taken out and market settles there" branch (`dalton_markets_in_profile`
  p.182).
- **Evidence:** **strong** — this is the documented failure mode, not an excuse.

### 7 — NY open reversal with no reference probed: SKIP
- **Setup:** 16:00 UTC. Price drops 0.9×ATR(M15) in the first two bars, then reverses and
  closes back through the 16:00–16:15 range. No prior-day, prior-week, Asia or London
  reference was touched in the drop.
- **Decision:** **SKIP.**
- **Invalidation of the skip:** the reversal extends past the London high, at which point it is
  a with-trend continuation setup on other grounds.
- **Why:** This is Dalton's Open-Rejection-Reverse, not Open-Test-Drive. The distinction is
  precisely whether a *known reference* was probed and rejected. Rejection-Reverse initial
  extremes hold less than half the time (`dalton_mind_over_markets` p.88), so there is no edge
  in the pattern itself. Calling this a "Judas swing" would be a pure narrative overlay.
- **Evidence:** **moderate** (the classification) / **untested** (the ICT reading).

### 8 — Impulse origin as a reference, used as a *magnet* rather than an entry
- **Setup:** During London, an M15 bull spike of 2.2×ATR launches from a two-bar base at
  3208.40–3210.10. Price runs to 3231, then over the following four hours retraces. It reaches
  3212 during the NY session and stalls.
- **Decision:** Take partial profit on any short held into 3212. Do NOT open a long merely
  because price reached "the order block".
- **Invalidation:** M15 close below 3208.40.
- **Why:** Brooks's actual claim is that earlier entry levels behave as **magnets that
  frequently draw price back** — and he adds explicitly that none of these targets ever has to
  be reached (`brooks_ranges` p.79–80). A magnet is a *target management* object. Converting
  it into an entry signal is the step the literature does not support. Dalton would add the
  volume question: was that base the origin of *initiative* activity, i.e. did it transact
  meaningfully (`dalton_mind_over_markets` p.66)?
- **Evidence:** **weak** (as magnet) / **untested** (as entry). The ICT alias "order block"
  stays in metadata only.

### 9 — Micro measuring gap used correctly
- **Setup:** M5 bars at 09:20–09:30 UTC: bar A high 3204.10, bar B a strong bull trend bar
  spanning 3204.30–3209.80, bar C low 3205.40 — A's high and C's low do not overlap.
- **Decision:** Do not treat the 3204.10–3205.40 band as a buy zone. Instead project a
  measured move: leg start to the gap midpoint, extended by the same distance, as the working
  target for the existing long.
- **Invalidation:** M5 close below bar B's low, which converts the read from measuring gap to
  exhaustion gap.
- **Why:** This is exactly Brooks's micro measuring gap and exactly his use of it
  (`brooks_reversals` p.17, 57, 106). He also warns the same structure can turn out to be an
  *exhaustion* gap rather than a measuring gap (p.117) — the distinction is decided by what
  follows, not by the shape. Dalton reads price gaps as a form of *excess*, i.e. an auction
  ending (`dalton_markets_in_profile` p.105–106), which is another reason not to buy into one.
- **Evidence:** **moderate**. ICT alias "fair value gap": **untested**.

### 10 — Premium/discount replaced by the honest probability statement
- **Setup:** London built a $14 range; price is now at the 52% mark of it during the overlap.
  The narrative layer wants a short because price is "in premium".
- **Decision:** **WAIT.** No initiation anywhere in the middle third of a named range in
  either direction.
- **Invalidation of the wait:** price reaches the outer third with a rejection bar, or breaks
  and is accepted outside.
- **Why:** Brooks's statement is that in the middle of a trading range there is uncertainty —
  directional probability is roughly 50% — and it only tilts once price reaches an extreme
  where participants agree it went too far (`brooks_ranges` p.79). Dalton's value-area logic
  says something adjacent: price re-entering and being *accepted* inside prior value tends to
  traverse the whole value area (`dalton_mind_over_markets` p.189), which again argues against
  fading the middle.
- **Evidence:** **moderate**. ICT alias "premium/discount": **untested**.

### 11 — Poor high revisited two sessions later
- **Setup:** Tuesday's NY session ends with a flat high: four M15 closes within $0.50 of
  3244.60 and a top wick under 0.15×ATR. Wednesday does not reach it. Thursday's London
  session rallies into 3244.
- **Decision:** Do not fade 3244 on the approach. Expect the level to be taken out; manage any
  existing short accordingly, and re-arm the sweep detector (rule 4) above it.
- **Invalidation:** rejection with a close more than 1.0×ATR back below on M15.
- **Why:** Dalton's revised position is that a poor high means the auction was never completed
  and that the market often returns to take out the extreme to complete it — explicitly noting
  this may not happen on the same day (`dalton_mind_over_markets` p.258), and that a poor
  high/low gives low odds of holding (`dalton_markets_momentum` p.248).
- **Evidence:** **moderate**.

### 12 — News-driven spike with no volume: SKIP
- **Setup:** 12:30 UTC release. The M5 bar spans 2.8×ATR, closes near its open (long-legged
  doji), and tick volume is *below* the 20-bar median.
- **Decision:** **SKIP** entirely, in both directions, for at least four M5 bars.
- **Invalidation of the skip:** a subsequent bar with above-median volume closing decisively
  beyond the spike's range.
- **Why:** Coulling's testable claim: a wide-range bar on low volume is an effort/result
  anomaly, and around a release it is a whipsaw that clears stops on both sides rather than a
  reversal signal (`couling_volume` p.82–83). Brooks arrives at the same abstention from
  different reasoning — post-report minutes belong to programs with a latency edge, so wait
  (`brooks_reversals` p.369–370). Lien's own version: the initial London-open move may simply
  not be the real one (`lien_fx_sessions` p.137).
- **Evidence:** **weak** (Coulling asserts, does not test) but **moderate** as an abstention
  rule, because two independent authors reach the same abstention.
- **Upgrade path:** this is directly measurable on the tick archive — see Implementation.

---

## Learning outcome

After this topic the model must, given any bar sequence and session clock, (a) name the
observable mechanism behind any ICT term it is tempted to use, and refuse to emit the term
without an accompanying computable rule and evidence label; (b) classify a level breach into
`failed_breakout` / `accepted_breakout` / `undecided` using follow-through over a fixed bar
window, and never by asserting intent; (c) classify a session open into Dalton's four types
before forming a session bias, and recognise that the Open-Drive case forbids the
false-move narrative outright; and (d) state, for every ICT concept it references, the exact
measurement on the tick archive that would move its label from `untested` to something better.
Testable: prompt the model with an Asia-high wick, and it must ask for the follow-through
window before taking a side.

---

## Implementation

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `session_id` | UTC hour → {asia 00–07, london 08–13, overlap 13–16, ny 16–21, dead 21–24} | clock | Fixed windows per brief |
| `asia_high` / `asia_low` | max/min of high/low over bars with 00 ≤ hour < 07 | M15 | Frozen at 07:00 close; do not update intrasession |
| `london_high` / `london_low` | same for 08 ≤ hour < 13 | M15 | Frozen at 13:00 close |
| `pdh/pdl/pdc`, `pwh/pwl` | prior completed D1/W1 extremes | D1/W1 | Closed bars only |
| `swing_high[i]` / `swing_low[i]` | fractal pivot, 2 bars either side, confirmed only after the right-hand bars close | M15/M5 | 2-bar confirmation lag is mandatory — no lookahead |
| `round_levels` | nearest multiples of 10 and 50 within ±2×ATR(M15) | any | Gold analogue of Lien's double/triple zeros (`lien_fx_sessions` p.131) |
| `ref_score` | `w1*bars_touched + w2*volume_at_level + w3*recency_decay` | M15 | Murphy's three factors (`murphy_ta` p.71); weights fitted, not from book |
| `breach(level)` | first bar whose high > level (or low < level) | stated tf | Trigger only |
| `breach_close_beyond` | breach bar closes beyond level | stated tf | Distinguishes sweep candidate from breakout candidate — rule 3 |
| `sweep_flag` | `breach AND NOT breach_close_beyond AND close_back_inside` | M15/M5 | The only sanctioned meaning of "liquidity sweep" |
| `followthrough_atr` | max extension beyond level over next N bars ÷ ATR | M15 N=3, M5 N=6 | Core disambiguator, rule 4 |
| `breach_class` | `failed` if ft<0.5 and back inside; `accepted` if still beyond with HL/LH; else `undecided` | M15/M5 | Dalton MiP p.182 |
| `excess_flag` | wick beyond body at session extreme ≥ 0.5×ATR | M15 | Auction completed (`dalton_markets_in_profile` p.103) |
| `poor_extreme_flag` | wick < 0.15×ATR AND ≥2 closes within 0.1×ATR of extreme | M15 | Auction incomplete; expect revisit (`dalton_mind_over_markets` p.257) |
| `open_type` | Drive / Test-Drive / Rejection-Reverse / Auction per rule 9 | M15, first 4 bars | Needs the named-reference set to already exist |
| `opening_range` | high/low of first 4 bars of the session | M15 | Brooks's opening range (`brooks_trends` p.356) |
| `ib_high` / `ib_low` | high/low of first hour of the session | M15 | Dalton initial balance (`dalton_mind_over_markets` p.31) |
| `range_eq` | (range_high + range_low) / 2 for the named range | any | Premium/discount replacement; no-trade band = middle third (rule 12) |
| `choch_flag` | latest countertrend swing magnitude > max of last 3 with-trend swing magnitudes | M15 | Grimes p.160, made computable |
| `bos_flag` | close beyond last confirmed swing extreme | M15 | Flag only; never sufficient (rule 14) |
| `impulse_origin` | base of the last leg whose body sum ≥ 2×ATR, as a (high, low) band + volume in band | M5/M15 | The observable behind "order block"; emitted as a band, not a candle |
| `micro_gap` | bar[i-1].high < bar[i+1].low (bull) or inverse | M5/M15 | Brooks micro measuring gap; used for projection only |
| `role_reversal` | level with penetration ≥ 1.0×ATR then re-approach from the other side | M15 | The observable behind "breaker"; threshold fitted |
| `vol_anomaly` | range ≥ 2×ATR AND tick_volume < median(20) | M5 | Coulling's trap test (`couling_volume` p.82) |
| `news_lockout` | boolean, ±2 min around scheduled release | clock | **Requires an economic calendar feed the bot may not have — flag** |
| `size_scalar` | k / ATR(M5,12), clipped | M5 | Brooks: wider bars → smaller size (`brooks_reversals` p.369) |
| `ict_alias` | string, metadata only | — | Must never appear in the decision predicate |

**Data the bot may not have — flagged explicitly:**
- **True traded volume.** Spot gold from a retail feed gives *tick* volume, not contract
  volume. Every volume-conditioned rule above (Murphy's ranking, Dalton's acceptance,
  Coulling's anomaly) degrades to a proxy. Cross-check against COMEX GC futures volume if a
  feed is available.
- **Order flow / order book.** Chan's central point is that signed transaction volume predicts
  short-term direction (`chan_algo_trading` p.186), and that in FX this is hard precisely
  because dealers do not report transaction prices — he suggests trading the *futures* to get
  it. The bot has none of this. Every "smart money" claim in ICT is a claim about exactly the
  data the bot cannot see.
- **Economic calendar** for the news lockout.
- **Market Profile / TPO structure.** Dalton's poor-high, excess and value-area constructs are
  approximated here from OHLCV; they are not the real thing.

---

## Contradictions between sources

| Author A position | Author B position | How to resolve for this bot |
|---|---|---|
| **Dalton:** in the majority of Open-Drive cases the extreme left behind at the open holds for the entire day (`dalton_mind_over_markets` p.83) — the first move is the real move. | **Brooks:** reversals are common, abrupt and often large in the first hour; the first bar is the day's high or low only about 20% of the time (`brooks_reversals` p.369). | Not actually incompatible, and the resolution is the whole point of this topic: Dalton is conditioning on a *classified* open, Brooks is describing the unconditional distribution. **Classify first (rule 9), then apply the matching prior.** This also kills the blanket Judas-swing claim: it is only licensed under Test-Drive. |
| **Dalton (MiP p.181–182, MoM p.110):** activity at visible extremes is often day traders deliberately pushing price far enough to trigger the stops sitting there. | **Brooks (ranges p.195):** rejects the naive form — asks why smart money is not gunning an obvious stop cluster, and answers that they are not, because triggering it would change the market's character and destroy the setup. | Both are describing order mechanics, not motive; Brooks's objection is that *obviousness alone does not create a raid*. Resolve by acting only on the **outcome branch** (rule 4), which both authors' logic supports, and never on an inference about who did what. |
| **Coulling (p.16, 82–83):** markets are manipulated; insiders rack price around news to shake traders out; volume reveals their footprint. | **Grimes (p.162):** markets are highly random and very close to efficient; every edge comes from an identifiable imbalance, and traders should restrict activity to those points. | Adopt Grimes's epistemology and Coulling's **measurable** claim only. Keep `vol_anomaly` (wide range + low volume → abstain) because it is testable; discard the insider narrative because it is not. Note the abstention is the same either way, which is why it survives. |
| **Grimes (p.358, 200):** there is nothing magical about the breakout level; the pullback may violate it, stop at it, or never reach it, and flipping position on a level violation is futile. | **Person (p.122)** and **Murphy (p.69–74):** breakout points reliably reverse roles and serve as test points; prior resistance becomes new support. | Both are true at different resolutions. Murphy/Person describe the *tendency across many instances*; Grimes describes the *variance within one instance*. Resolve: use role reversal to **rank and locate** candidate zones, never as a trigger. Require a closed-bar rejection signal at the zone (example 5). |
| **Brooks (reversals p.57, 106):** a measuring gap is a projection device — measure from the leg start through the gap midpoint to get a target. | **Dalton (MiP p.105–106):** a price gap is an extreme form of *excess*, marking the end of an auction. | Opposite trade implications from the same structure: Brooks says "the move continues", Dalton says "the move is finishing". Resolve by location: treat a gap in the **first third** of a leg as a measuring gap (project), and one occurring **after an extended move at a session or daily extreme** as excess (do not chase). If ambiguous, no position. This also means the ICT "fair value gap must be filled" claim has *two* incompatible ancestors, neither of which says that. |
| **Lien (p.136–138):** the London-open move is often not the real one; U.K. dealers survey books and trigger close stops both sides before the real direction emerges. | **Dalton (p.83–85):** the open, when it is a Drive, is caused by participants who made their decisions *before* the bell — the open is maximally informative, not deceptive. | Instrument- and era-dependent. Lien is describing 2005 GBP/USD with U.K. dealers as the dominant market makers; gold's London window is dominated by different flow. Resolve: **treat Lien's pattern as a hypothesis to measure on the XAUUSD tick archive, not as a prior**, and let Dalton's classification arbitrate in the meantime. |
| **Lien (p.131–133):** fade the round number — take-profit clustering makes it a reversal point. | **Chan (p.185–186):** trade *through* the round number — stop clustering just past it makes it a momentum point. | These are the two sides of the same asymmetry and are not in conflict, but they are trivially easy to conflate into a contradiction. Encode the asymmetry explicitly (rule 5): **fade into the figure, go with the break past it**, and let `breach_class` decide which regime is live. |

---

## Gaps

Things this topic needs that **no book in the corpus provides**:

1. **Any primary ICT source.** All ICT content here is reconstructed from the operator's
   vocabulary and mapped onto other authors. If ICT's own definitions differ in detail — and
   they will — the mappings above are approximations. Obtaining a primary text would change
   the *fidelity* of the mapping but not the evidence labels, since no test exists either way.

2. **Osler (2003, 2005) themselves.** Chan *cites* Osler (2000, 2001) at `chan_algo_trading`
   p.185 but reproduces only the headline result. The actual papers contain the effect sizes,
   the horizon over which post-breach momentum persists, and the take-profit/stop asymmetry
   quantified from real bank order books. Without them, the strongest mechanism in this topic
   is known only qualitatively. This is the highest-value external acquisition.

3. **Anything on XAUUSD specifically.** Every quantitative statement in the corpus is from
   Emini/Treasuries (Brooks, Dalton), FX majors (Lien), or equities (Grimes). Murphy's gold
   round-number examples (p.75) are the only gold-specific content found, and they are
   anecdotal. Gold's session structure, its dual identity as commodity and monetary asset, and
   its behaviour around London fix times are entirely uncovered.

4. **Base rates for sweeps.** Nobody states how often a probe-and-close-back-inside at a named
   level is followed by a move to the opposite side of the range. Grimes says most breakouts
   fail; nobody says how often the *failure* is tradeable, or what the conditional distribution
   of the subsequent move looks like. This is a measurement, not a reading task.

5. **The London/AM and PM gold fixings** (10:30 and 15:00 UTC). These are precisely the kind
   of scheduled, order-concentrating events where the stop/take-profit clustering mechanism
   should be strongest, and no corpus author mentions them.

6. **Multi-timeframe alignment protocol.** ICT is fractal by construction; Grimes discusses
   timeframe relationships (p.353: "it is usually a question of time frames") but gives no
   algorithm for which timeframe wins when M5 and H4 sweeps disagree. Currently unresolved.

7. **The correlation between sweep events and spread widening.** Lien establishes session
   volatility profiles (p.83–89) but not spread behaviour at the moment of a stop cascade —
   which is exactly when a bot's fills degrade. Execution cost at sweep moments is unmodelled.

### Measurement backlog — what would upgrade each `untested` label

| Term | Current | Measurement on the XAUUSD tick archive | Upgrade to |
|---|---|---|---|
| Liquidity sweep | `weak` | Over ≥2000 probe events at named references: P(return to opposite side of the range) conditional on `followthrough_atr` bucket. Compare against a matched control of non-probe bars. | `moderate` if lift over control is significant |
| Equal highs / pool | `weak` | P(revisit within 5 sessions) for `poor_extreme_flag=1` vs `excess_flag=1` extremes. | `moderate` |
| Order block | `untested` | Forward return distribution on first re-touch of `impulse_origin` bands, split by volume-in-band quartile. Null: re-touch is indistinguishable from a random band of equal width at equal distance. | `weak` at best without a rejection of the null |
| Breaker block | `untested` | Same, restricted to `role_reversal=1` bands, stratified by `penetration_atr`. Tests Murphy's "significant penetration" claim directly and yields the threshold empirically. | `moderate` |
| Fair value gap | `untested` | Fill rate of `micro_gap` bands vs a random-band control at matched distance; plus Brooks's projection accuracy (does the measured move complete?). | `weak`/`moderate` |
| BOS | `weak` | Continuation rate after `bos_flag`, split by `open_type` and session. Expected to be near or below the breakout base rate. | `moderate` |
| CHoCH | `weak` | P(trend does not resume within 20 bars) after `choch_flag`, vs unconditional. | `moderate` |
| Premium/discount | `untested` | Realised directional probability by decile of position within the named range. Brooks predicts ~50% at the midpoint improving toward the extremes — this is directly falsifiable. | `moderate` |
| Judas swing | `untested` | For each session open: classify `open_type`, then measure P(opening extreme holds to session close) per class. Dalton predicts Drive > Test-Drive > Rejection-Reverse ≈ coin flip. Falsifiable in one pass. | `moderate` |
| Round-number asymmetry | `weak` (for gold) | Reversal rate on approach to $10/$50 handles vs continuation rate after a close beyond, using Osler's framing. This is the cleanest, highest-value test in the whole backlog. | `strong` if the asymmetry replicates |
| Volume anomaly trap | `weak` | Forward absolute return and sign persistence after `vol_anomaly=1` bars vs matched high-range bars with normal volume. | `moderate` |

---

## JSONL seeds

```json
{"principle_id":"ict_translate_before_acting","topic":"ict_concepts","lesson":"Every ICT term is an alias for an older, better-documented concept: sweep is a failed breakout, breaker is role reversal, CHoCH is a change of character, Judas swing is an Open-Test-Drive.","practice":"Before emitting any ICT term, name the observable rule and the corpus source behind it; store the ICT word only in metadata.","guardrail":"Reject any decision whose only support is an ICT alias with no computable rule attached.","evidence_label":"strong"}
{"principle_id":"ict_sweep_requires_close_inside","topic":"ict_concepts","lesson":"A breach that closes beyond a level is a breakout candidate; only a breach that closes back inside is a sweep candidate. The two have opposite expectations.","practice":"Set sweep_flag only when the breach bar's close is back inside the level on the stated timeframe; otherwise set breakout_candidate.","guardrail":"Never label a live, unclosed bar as a sweep. Never use an intrabar wick as evidence of anything.","evidence_label":"strong"}
{"principle_id":"ict_followthrough_decides_not_intent","topic":"ict_concepts","lesson":"Dalton gives the same rule twice: if activity beyond a level dries up the move was a stop run and price returns; if price settles out there it was a real breakout.","practice":"After the first close beyond a named reference, wait 3 M15 bars (or 6 M5) and classify as failed, accepted or undecided by extension in ATR and swing structure.","guardrail":"Stand down on undecided. Never infer who triggered the move or why — the classification uses only price and time.","evidence_label":"strong"}
{"principle_id":"ict_round_number_asymmetry","topic":"ict_concepts","lesson":"Take-profit orders cluster AT round numbers and produce reversals; stop orders cluster JUST BEYOND them and produce acceleration once triggered. This is the genuine mechanism behind stop hunts and requires no intent.","practice":"On approach to a $10 or $50 gold handle, bias toward fading into the figure; after an accepted close beyond it, bias with the move.","guardrail":"Do not place the bot's own protective stops on round numbers or exactly at the visible swing extreme.","evidence_label":"strong"}
{"principle_id":"ict_classify_open_before_bias","topic":"ict_concepts","lesson":"Dalton's four opening types carry different priors: an Open-Drive extreme usually holds all day, while an Open-Rejection-Reverse extreme holds less than half the time.","practice":"Classify each session open from its first four M15 bars into Drive, Test-Drive, Rejection-Reverse or Auction before forming any session bias.","guardrail":"The session-open-false-move narrative is licensed only under Test-Drive, and only when a named prior reference was actually probed.","evidence_label":"moderate"}
{"principle_id":"ict_no_required_retest","topic":"ict_concepts","lesson":"Grimes states plainly that there is nothing magical about the breakout level: the pullback may violate it, stop at it, or never reach it, and flipping position on a level violation is a futile plan.","practice":"After an accepted breakout, allow entry on the first pullback whether or not it touches the breakout level, judged by the pullback's own geometry.","guardrail":"Never make a trade conditional on price returning to mitigate an order block or fill an imbalance.","evidence_label":"moderate"}
{"principle_id":"ict_equilibrium_is_fifty_fifty","topic":"ict_concepts","lesson":"Brooks's version of premium/discount attaches an honest probability: at the midpoint of a range directional probability is about 50 percent, improving only toward the extremes.","practice":"Compute the plain midpoint of the named range and refuse to initiate anywhere in its middle third, in either direction.","guardrail":"Do not short merely because price is 'in premium' or buy merely because it is 'in discount'.","evidence_label":"moderate"}
{"principle_id":"ict_poor_extremes_get_revisited","topic":"ict_concepts","lesson":"A session extreme with no tail is an incomplete auction and tends to be taken out later, sometimes days later; an extreme with a long tail is excess and marks an ending.","practice":"Flag poor_high/poor_low when the extreme's wick is under 0.15 ATR with at least two closes clustered at it, and stop fading that level on approach.","guardrail":"Likely to be revisited is a claim about price reaching the level, not about what happens after. Do not pre-position for the raid.","evidence_label":"moderate"}
{"principle_id":"ict_failed_breakout_has_a_known_failure_mode","topic":"ict_concepts","lesson":"Grimes warns that failed-breakout trades carry real tail risk, fail through strong countertrend momentum in the pullback, and must have their stops respected absolutely.","practice":"On any sweep-fade entry, place the stop beyond the probe extreme and exit at the stop without averaging or re-entering in the same direction.","guardrail":"Never scale into a losing sweep-fade. A second probe that is accepted beyond the level is the accepted-breakout branch, not a deeper discount.","evidence_label":"strong"}
{"principle_id":"ict_intent_is_not_observable","topic":"ict_concepts","lesson":"The order-flow data that would reveal who is doing what is exactly the data the bot does not have; Chan notes signed transaction volume is unavailable in spot FX and gold for the same reason.","practice":"Express every liquidity claim as an order-placement fact (stops cluster past visible extremes, targets cluster at figures) rather than an actor claim.","guardrail":"Reject any narrative containing smart money, manipulation, engineered liquidity or hunting retail; rewrite it as the observable or drop it.","evidence_label":"strong"}
```
