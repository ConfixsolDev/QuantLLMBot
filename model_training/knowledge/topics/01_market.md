# Topic 1 — Market

> **Sources read:** `dalton_mind_over_markets` pp.15, 29, 33–39, 61, 121, 135, 250–253; `dalton_markets_in_profile` pp.31–33, 37–43, 122, 164, 203; `dalton_markets_momentum` pp.44, 87, 99, 102, 132; `lien_fx_sessions` pp.20–22, 27, 30, 32–35, 53, 75–77, 83–93, 136–140, 151; `murphy_ta` pp.23–27, 32, 181–182, 244, 373, 378–380, 409; `couling_volume` pp.9, 11, 16, 20–22; `carter_mastering` pp.13, 72, 191, 282, 345, 382–398, 493; `chan_algo_trading` pp.22–29, 43, 176, 201, 207; `douglas_zone` pp.12, 72, 76–81; `grimes_art_science` pp.23, 25, 31, 56, 114, 119; `elder_trading_room` pp.18–21; `brooks_trends` pp.19, 34
> **Status:** v2 full-corpus distillation, 2026-08-08. Supersedes v1.2 (which was built from truncated text and contained several unsupported session claims).

---

## Core concepts

| Concept | Definition (one line, my words) | Sources | Evidence |
|---|---|---|---|
| Two-way auction | A market has one job — facilitate trade — and it does that by auctioning up until buyers stop buying and down until sellers stop selling, in search of a price where business gets done | dalton_mind_over_markets p.36; dalton_markets_in_profile p.40 | `strong` |
| Price / time / volume | Price advertises an opportunity, time regulates how long that opportunity stays open, volume measures whether the advertisement worked | dalton_markets_in_profile p.41; dalton_mind_over_markets p.61, p.121 | `strong` |
| Value | The band of prices attracting the most trade; "fair" only within the timeframe you measured it, and routinely unfair to a longer one | dalton_markets_in_profile p.42 | `strong` |
| Market-generated information (MGI) | Information produced by the act of trading itself — where price went, how long it stayed, how much traded — as opposed to opinion about the instrument | dalton_markets_in_profile pp.31, 40 | `strong` |
| Other-timeframe participant | A participant whose horizon exceeds the current bar/session; they enter when price moves away from their idea of value, and only they move price far | dalton_mind_over_markets pp.33, 37 | `moderate` |
| Timeframe stack | Scalper / day / short-term / intermediate / long-term all trade the same tape with different definitions of "fair"; a seller exists for every buyer but they are rarely the same timeframe | dalton_markets_in_profile p.43; dalton_mind_over_markets p.253 | `strong` |
| Price as consensus | Each print is a momentary agreement on value between the most eager buyer and the most eager seller — not a measurement of worth | elder_trading_room pp.20–21 | `strong` |
| Institutional dominance | The large majority of volume in a major market is institutional; no single participant moves a major market for long | brooks_trends pp.19, 34 | `moderate` |
| Decentralised OTC structure | Spot FX/metals has no central exchange; multiple market makers quote simultaneously, participants are ranked by credit and size, and quotes are venue-dependent | lien_fx_sessions pp.32–35; chan_algo_trading pp.28–29 | `strong` |
| Liquidity varies by clock | Participation in a 24h instrument is a function of which financial centres are staffed, not of the instrument | lien_fx_sessions pp.21–22, 83–89; dalton_markets_momentum p.44 | `strong` |
| Session boundary as regime change | Every session open injects a new population with a different mandate; the character of the tape changes even though price never stopped | lien_fx_sessions pp.87–88; carter_mastering pp.72, 345 | `moderate` |
| Overnight inventory | The net position built while the dominant session was closed; extreme skew tends to be adjusted early in the next dominant session, and failure to adjust is itself information | dalton_mind_over_markets pp.250–252 | `moderate` |
| Tick volume | Count of quote changes per bar — a proxy for *activity*, not for size traded; spot FX/metals has no reported trade volume at all | couling_volume pp.20–21; chan_algo_trading p.29 | `strong` |
| Effort vs result | Compare the effort (volume/activity) against the result (range and close location); a mismatch is the signal, not the volume level | couling_volume p.11 | `moderate` |
| Volume is relative | A volume bar means nothing absolutely; it only means something against a local baseline for the same instrument, timeframe and time-of-day | couling_volume p.21 | `strong` |
| Price leads known fundamentals | By the time a fundamental reason is public it is already priced; important moves routinely begin before the reason is knowable | murphy_ta pp.26–27, 409 | `moderate` |
| Reaction > release | What the release does to price matters more than what the release said; failure to move on favourable news is the information | murphy_ta pp.244, 409 | `moderate` |
| Intermarket context | Dollar and gold usually trend opposite; gold tends to lead the broader commodity/inflation complex | murphy_ta pp.181, 378–380 | `moderate` |
| Correlations drift | Any cross-market relationship you measure has a shelf life and can invert over a shorter window | lien_fx_sessions p.93; chan_algo_trading pp.43, 201 | `strong` |
| Regime shift / pattern decay | A pattern can stop working permanently because the market's structure or the crowd changed, not because your test was wrong | chan_algo_trading pp.43, 201, 207; carter_mastering p.13 | `strong` |
| Equilibrium ≈ noise | A balanced, two-sided market is statistically close to a random walk, and no durable edge lives there | grimes_art_science pp.31, 114 | `moderate` |
| Liquidity floor on patterns | Below some liquidity level, structure degenerates into noise; the same pattern is meaningful on one instrument/timeframe and meaningless on another | grimes_art_science pp.25, 56 | `moderate` |
| Probabilistic single trade | Any one trade is a unique event with an unknowable outcome; consistency comes from an edge applied over a large sample, not from being right now | douglas_zone pp.12, 72, 80–81 | `strong` |
| Instrument personality | Instruments have persistent behavioural character — gold is described as a trender that rewards breakout continuation, index futures as a chopper that punishes it | carter_mastering p.383 | `weak` |

### Who trades it, and on what horizon

The corpus gives two independent taxonomies of participants. They agree on the important part: **the market is a small number of large, slow participants whose flow sets direction, plus a large number of fast participants who set the path.**

| Participant | Horizon | Why they trade | What they leave on the chart | Source |
|---|---|---|---|---|
| Interbank / major dealers | Minutes to days, but continuously | Making markets, servicing client flow, managing their own book | They sit between every trade; they can see where client stops rest, which is Lien's stated mechanism for the false first move at the London open | lien_fx_sessions pp.34–35, 137 |
| Hedge funds, real-money institutions | Days to months | Position-taking on a macro view | Range extension — movement beyond the balance established by short-term participants. Dalton is explicit: short-timeframe locals are not responsible for major moves; only the other timeframe moves price substantially | dalton_mind_over_markets p.33 |
| Corporates / exporters / hedgers | Weeks to quarters, mechanically timed | Converting or hedging exposures on a calendar, not on a view | Repeatable time-of-day flow — Lien names Japanese exporters repatriating in Tokyo hours and European desks reconverting into dollars ahead of the US open | lien_fx_sessions pp.85, 88 |
| Locals / market makers / HFT | Seconds to hours | Capturing spread, providing liquidity, statistical arbitrage | The initial balance and the noise inside it. Brooks separates the roles cleanly: traditional institutions determine direction and target, statistical firms determine the path taken to get there | dalton_mind_over_markets p.38; brooks_trends p.19 |
| Retail | Any, usually too short | Everything | Predictable stop clusters at round numbers and at obvious session highs/lows; Coulling frames the whole point of volume analysis as identifying which side of this the wholesalers are on | couling_volume p.22; lien_fx_sessions p.85 |

Three consequences the bot must carry:

- **"Other timeframe" is the only category that matters for direction.** Dalton defines it as anyone whose participation spans more than the current session, and says flatly that it is other-timeframe activity that moves and shapes the market (dalton_mind_over_markets p.33). They enter when price has moved away from their idea of value or when external information convinces them (p.37). The practical inference is that a move which extends the range and *holds* is other-timeframe evidence; a move that extends and returns is not.
- **Participation is geographic, so it is clock-bound.** Lien's whole session chapter rests on the fact that a currency pair's range depends on which centres are staffed (p.83). Gold inherits this because it is quoted against the dollar and traded through the same desks — but with the caveat that gold also has genuine Asian physical demand, which is exactly the untested part.
- **Everyone at the table is a professional.** Brooks estimates 90%+ of volume in large markets is institutional and notes almost all such firms are profitable over time or they cease to exist (brooks_trends p.34). Elder's version: the efficient-market theory is right that price aggregates the crowd's intelligence and wrong that the crowd is rational (elder_trading_room p.19). Grimes' practical conclusion is to pick a timeframe where you are not competing directly with the fastest participants (p.25). For this bot that argues against M1-only decisions and for M5/M15 confirmation.

### Session anatomy — exactly what the sources say

Lien is the primary session source and she quotes everything in **EST**. Converted to UTC (winter, EST = UTC−5) her boundaries are:

| Lien's session | Her hours (EST) | UTC (winter) | This bot's grid | Note |
|---|---|---|---|---|
| Asian (Tokyo) | 7pm–4am | 00:00–09:00 | asia 00–07 | Bot's window is 2h shorter at the tail |
| European (London) | 2am–12pm | 07:00–17:00 | london 08–13 | Bot starts 1h later, ends 4h earlier |
| U.S. (New York) | 8am–5pm | 13:00–22:00 | ny 16–21 | Bot starts 3h later |
| U.S.–Europe overlap | 8am–12pm | 13:00–17:00 | overlap 13–16 | Closest match; bot is 1h short |
| Europe–Asia overlap | 2am–4am | 07:00–09:00 | pre_london 07–08 | Bot's thinnest-window label is roughly right |

**What actually changes at each boundary, per source:**

- **Asia (00–07 UTC).** Tokyo leads, then Hong Kong and Singapore (lien_fx_sessions p.83). Lien calls Tokyo trading "thin from time to time" and states plainly that **large banks and hedge funds use the Asian session to run stop and option-barrier levels** (p.85) — meaning clean-looking breaks of overnight levels in this window are manufactured often enough to be a documented behaviour, not an anomaly. Japanese exporters repatriate earnings in these hours (p.85). Critically, her range table (p.84) shows Asia is quiet **only for the dollar/European majors**: EUR/USD 51 vs 87 European pips, GBP/USD 65 vs 112, USD/CHF 68 vs 117, USD/CAD 47 vs 94 — but USD/JPY is 78 vs 79, essentially flat. Whether XAUUSD sits in the first group or the second is the open question.
- **Pre-London / Europe–Asia overlap (07–09 UTC).** Lien names this the **lowest-intensity window of the entire 24h cycle** and her literal advice is to nap or to spend it positioning for a breakout at the European or US open (p.89). Her own "real deal" strategy uses 06:00–07:00 UTC (the Frankfurt–London "power hour") as the reference range to be swept (pp.136–137).
- **London (08–13 UTC).** The UK is ~31% of global FX turnover and Europe as a whole ~42% (p.136); London is where most major transactions are completed and, in Lien's words, the most volatile centre of all (p.87). Her stated reason the London open matters is **repricing**: it is the first time the bulk of the market can act on anything that happened during late US trade or overnight Asia (p.136). She immediately qualifies this: because European dealers make the market and can see client stops, **the first move at the London open may not be the real one** (pp.136–137).
- **Overlap (13–16 UTC).** Lien's headline number: the 8am–noon EST window contributes on average **~70% of the whole European session's range and ~80% of the whole US session's range** (p.89). She adds that if you can only sit at the screen for part of the day, this is the part. London desks are simultaneously reconverting European assets into dollars ahead of the US open, which is her stated mechanism for the volatility spike (p.88).
- **New York (16–21 UTC).** ~19% of turnover; the majority of US-session transactions land between 8am and noon EST — i.e. inside the overlap, not after it (p.86). Lien describes NY as guarding the back door: **activity winds down to a minimum from the NY afternoon until Tokyo reopens** (p.86).
- **Gold-specific timing.** Carter's gold material is COMEX GC, not spot: settlement is struck at 1:30pm EST / 18:30 UTC and is *not* the same as the close (carter_mastering p.385); the contract reopens at 6:00pm EST / 23:00 UTC and Senters notes it is **thin at that reopen** (p.387). Lien separately records that in her era COMEX gold futures pit hours were only 7:20am–1:30pm (p.27) — a reminder that "gold" means different instruments with different clocks.
- **Carter's four opens.** He frames the 24h day as four equity-open-like events — Tokyo 20:00, Frankfurt 00:00, London 03:00, New York 08:30 (all EST; p.72) — and observes that consolidations forming near a local 8am open resolve fast and, once resolved, usually carry into a directional move (p.345). He also refuses to act on his own opening-range indicator in the **first 30 minutes** of a session, treating signals from that window as too erratic to act on (p.191).

**Session-to-session claims, stated honestly.** Across the whole corpus there are exactly three claims that cross a session boundary, and none of them is "Asia's direction predicts London's":

1. **Lien, pp.136–137** — the first London impulse is often a stop-run in the *wrong* direction, and the tradable move is the reversal that penetrates the opposite side of the pre-London range. This is a **fade**. Evidence: `untested`. She gives a mechanism and three winning GBP/USD chart examples (Figures 9.11–9.13, pp.138–140) and no losing example for this strategy; there is no statistical test.
2. **Dalton, dalton_mind_over_markets pp.250–252** — overnight volume is often ≤25% of the dominant session's, overnight participants are shorter-timeframe and weaker-handed, and extreme long or short overnight inventory tends to be adjusted shortly after the dominant session opens; if it is *not* adjusted, that non-adjustment is short-term strength. This is a **conditional fade with a confirmation stage**. Evidence: `moderate` — the mechanism is structural and Dalton gives the measurement rule mechanically, but he offers one illustrative example and explicitly says it "isn't as simple as conveyed."
3. **Carter/Senters, carter_mastering pp.387–388** — enter at 11:30pm EST (04:30 UTC), ahead of the Asian open and the imminent European open, in the direction of the **daily** trend, when price is 3–20 points from the prior settlement in that direction and D1 ADX(14) > 20. This is a **continuation**, but the conditioning variable is the daily chart, not the Asian session. Evidence: `untested`, and see the arithmetic caveat in worked example #10.

Lien's one explicitly Asia→London statement (p.151) is about **volatility regime, not direction**: her common scenario is channel trading through Asia and a breakout in London or the US, frequently triggered by an economic release. She never says which side breaks.

---

## Distilled rules

1. **Classify the session before anything else.** Stamp every decision with `session ∈ {asia, pre_london, london, overlap, ny, off}` derived from the closed bar's UTC timestamp, and carry it into the log. Nothing downstream may run without it. (lien_fx_sessions pp.83–89)
2. **Treat every session boundary as a regime break, not a continuation point.** Reset per-session statistics (session high/low, session volume baseline) at the boundary rather than smoothing across it. (lien_fx_sessions pp.87–88; carter_mastering p.345)
3. **Never assume the direction of one session predicts the direction of the next.** No source in this corpus makes that claim; two make near-opposite claims (see Contradictions). Any Asia→London directional bias must be measured on the tick archive before it may be used, and until then it is `untested`. (lien_fx_sessions p.137; dalton_mind_over_markets pp.250–252)
4. **Do use one session's *range* to condition the next session's *volatility expectation*.** Lien's own range table shows European ranges roughly 1.6–2.0× Asian ranges for the dollar majors, and she describes the standard pattern as channel/consolidation in Asia followed by a breakout in London or the US. Expect expansion, not a direction. (lien_fx_sessions pp.84, 151)
5. **Measure overnight inventory mechanically.** Compare where Asia traded against the prior NY-session close: majority above = long inventory, majority below = short, straddled = neutral. (dalton_mind_over_markets p.250)
6. **When Asian inventory is extreme, expect an adjustment early in London — and treat a *failure* to adjust as the bullish/bearish evidence, not the initial drift.** This is a two-stage read; do not collapse it to "Asia up therefore London up". (dalton_mind_over_markets pp.250–252)
7. **Do not treat the first impulse after the London open as the session's move.** Lien's explicit mechanism is that early-session order flow trips stops on both sides before the real direction emerges; require a close-based rejection or acceptance before committing. (lien_fx_sessions pp.136–137)
8. **Size down or stand aside in the 07:00–08:00 UTC pre-London window.** Lien identifies the Europe–Asia overlap as the lowest-intensity window of the entire 24h cycle. (lien_fx_sessions p.89)
9. **Prefer the London/NY overlap for anything that needs range.** Lien reports the overlap window contributes ~70% of the whole European-session range and ~80% of the whole US-session range on average across the majors. (lien_fx_sessions p.89)
10. **Downgrade signals in the late-NY / pre-Tokyo dead zone.** Activity winds down from the NY afternoon until Tokyo reopens; Carter separately notes gold is thin at its own 18:00 EST reopen. (lien_fx_sessions p.86; carter_mastering p.387)
11. **Normalise tick volume before comparing it.** Express each bar's tick volume as a ratio to a rolling median of the same timeframe *and the same session*, never as a raw number. (couling_volume p.21)
12. **Never trade tick volume alone.** Require a paired price result — range, close location, follow-through — on the same closed bar. Volume without price is meaningless. (couling_volume pp.11, 21)
13. **Never claim to read order flow, delta, or bid/ask aggression on spot XAUUSD.** No trade prints and sizes are published in this market; Carter's own bid/ask delta tool is stated to work on every market *except* spot FX. (chan_algo_trading p.29; carter_mastering p.398)
14. **Treat tick volume as broker-specific.** It is a property of the feed, not of the market; do not port a threshold calibrated on one broker's data to another. (couling_volume p.20; chan_algo_trading pp.28–29)
15. **Block new entries in a window around scheduled high-impact releases and require a fresh calendar.** Lien's own measurement puts a ~20-minute knee-jerk window on the top US releases, with NFP and FOMC ranked first and second. Use a wider window than 20 minutes for safety, and a stale calendar must block, not permit. (lien_fx_sessions pp.75–77)
16. **After a release, grade the reaction, not the number.** Record whether price accepted or rejected the release direction on closed bars, and require acceptance before acting. (murphy_ta pp.244, 409)
17. **Do not open a position because of a fundamental or intermarket reason.** Macro belongs to the analysis stage; the entry trigger must be structural and on a named timeframe. (murphy_ta p.27)
18. **Use the dollar/real-rate/risk context as a size-and-conviction filter at H4/D1 only, never as an intraday trigger or veto.** Murphy's dollar–gold inverse relationship is a multi-month observation, not an M5 one. (murphy_ta pp.378–380)
19. **Re-estimate any cross-market relationship on a rolling window and let it expire.** Lien documents correlations that inverted sign between a one-year and a one-month window. (lien_fx_sessions p.93)
20. **Assume every discovered pattern decays.** Log the discovery date, monitor live performance against the backtest, and treat a persistent divergence as a regime shift rather than as bad luck. (chan_algo_trading pp.43, 201, 207)
21. **Prefer few parameters and simple, near-linear rules.** Complexity is what turns a session artefact into a fitted ghost. (chan_algo_trading pp.22–23)
22. **Refuse to trade balance.** When the market is two-sided and rotating inside a defined range with no rejection at an edge, the correct output is `skip` — that state is statistically closest to a random walk. (grimes_art_science p.31; dalton_markets_in_profile p.42)
23. **Never report confidence about a single trade.** Express expectation as a distribution over a sample, and treat the current trade as one draw. (douglas_zone pp.12, 80–81)
24. **Every rule above must be computable from bars already closed plus a session clock.** No intra-bar peeking, no using the current bar's high/low before it closes. (project constraint; supported by chan_algo_trading p.22 on look-ahead)

---

## Worked examples

All examples are restated into XAUUSD/UTC terms from what the source actually teaches. Session clock: Asia 00–07, pre-London 07–08, London 08–13, overlap 13–16, NY 16–21.

### 1 — Asia inside prior NY value, no edge test
| | |
|---|---|
| **Setup** | 02:30 UTC. Price has spent all of Asia so far inside the prior NY session's range, roughly straddling the prior NY close. M5 tick volume at or below its Asia-session median. No H4 level within reach. |
| **Decision** | **SKIP.** |
| **Invalidation** | A closed M15 outside the Asia range on ≥1.5× session-median tick volume converts this to a live context. |
| **Why** | Balanced two-sided trade with no timeframe imbalance is the state closest to a random walk; overnight inventory is neutral so there is nothing to adjust. |
| **Evidence** | `moderate` — grimes_art_science p.31; dalton_markets_in_profile p.42; dalton_mind_over_markets p.250 |

### 2 — Extreme long Asian inventory into the London open
| | |
|---|---|
| **Setup** | 08:00 UTC. Essentially all of Asia's 00–07 trade printed above the prior NY close; the Asia range is narrow and price is sitting near its high. |
| **Decision** | **WAIT** through the first London bars. Do not buy the strength. Watch for an early downward adjustment. |
| **Invalidation of the WAIT** | If London opens and price *fails* to adjust lower — i.e. holds above the Asia value area for the first hour on closed M15s — Dalton reads the non-adjustment as short-term strength and the long side becomes viable. |
| **Why** | Overnight inventory: overnight participants are shorter-timeframe and thinner; extreme skew is usually flattened shortly after the dominant session opens. |
| **Evidence** | `moderate` — dalton_mind_over_markets pp.250–252 |

### 3 — First London impulse through the Asia high, closing back inside
| | |
|---|---|
| **Setup** | 08:20 UTC. M5 spikes ~$3 above the Asia high and the bar closes back below it. Tick volume on the spike bar is the highest of the day so far. |
| **Decision** | **WAIT / do not buy the break.** Mark the swept high. Prepare for a trade in the *opposite* direction if price then breaks the other side of the pre-London range. |
| **Invalidation** | Two consecutive M15 closes accepted above the Asia high with holding volume — that is acceptance, not a sweep, and the fade thesis is dead. |
| **Why** | Lien's "waiting for the real deal": early-session flow deliberately trips stops on both sides of a compressed overnight range before the genuine directional move; the first move at the London open is often not the real one. |
| **Evidence** | `untested` — lien_fx_sessions pp.136–137. Lien states the mechanism confidently and shows three winning chart examples on GBP/USD and no losing one; there is no statistical test in the book and none for XAUUSD anywhere in this corpus. |

### 4 — Overlap acceptance at an H4 level
| | |
|---|---|
| **Setup** | 14:10 UTC (overlap). Price trades into a marked H4 prior high. Three consecutive M15 bars close above it, ranges expanding, tick volume ≥2× the overlap-session median. |
| **Decision** | **OPEN long** on the pullback that holds above the level, with stop below the acceptance base. |
| **Invalidation** | An M15 close back below the level, or a stall where time accumulates at the level without further range extension — Dalton's "too much time" read. |
| **Why** | Price advertised above value, volume confirmed the advertisement worked, and the highest-participation window of the day is the one that can sustain it. |
| **Evidence** | `moderate` — dalton_markets_in_profile pp.41–42; dalton_mind_over_markets p.121; lien_fx_sessions p.89 |

### 5 — Same setup, wrong clock: 03:00 UTC
| | |
|---|---|
| **Setup** | Identical structure to #4 — three M15 closes above an H4 prior high, tick volume 2× the *Asia* median — but at 03:00 UTC. |
| **Decision** | **SKIP or take at reduced size**, and require a wider stop. |
| **Invalidation** | n/a — this is a size/participation decision, not a directional one. |
| **Why** | Volume is relative: 2× a thin baseline is not the same evidence as 2× a thick one, and patterns are bounded by the liquidity available to sustain them. Lien also notes Asia is where large players are known to run stop and option-barrier levels, which manufactures exactly this pattern without follow-through. |
| **Evidence** | `moderate` — couling_volume p.21; grimes_art_science p.56; lien_fx_sessions p.85 |

### 6 — Pre-release freeze
| | |
|---|---|
| **Setup** | 12:20 UTC. A textbook M5 continuation trigger fires. The calendar shows US NFP at 12:30 UTC. |
| **Decision** | **SKIP.** No new entry inside the news window; if the calendar feed is stale or unreachable, also skip. |
| **Invalidation** | Window clears and the structure is re-derived from bars that closed *after* the release. |
| **Why** | Releases reprice in seconds; Lien measures a distinct knee-jerk window on the top releases and rates NFP first. A stale calendar is an unknown, and an unknown must fail closed. |
| **Evidence** | `strong` — lien_fx_sessions pp.75–77 |

### 7 — Post-release non-reaction
| | |
|---|---|
| **Setup** | 13:00 UTC. A gold-supportive release (soft US data) has printed 30 minutes ago. XAUUSD spiked, then gave back the whole move and closed the M30 below the pre-release price. |
| **Decision** | **Do not buy.** Flip the working bias to neutral-or-short and look for a short trigger at structure. |
| **Invalidation** | Reclaim and acceptance above the pre-release price on closed M15s. |
| **Why** | The failure of price to react to favourable news is Murphy's explicit warning sign; the reaction is the information, not the number. |
| **Evidence** | `moderate` — murphy_ta pp.244, 409 |

### 8 — Dollar conflict at H4
| | |
|---|---|
| **Setup** | 15:00 UTC. Valid M5 long trigger at an H4 demand zone. The dollar index has been trending up for three days. |
| **Decision** | **OPEN long, reduced size.** Do not veto. |
| **Invalidation** | Structural — the H4 zone failing on a closed H4 basis. The dollar trend is not an invalidation. |
| **Why** | Murphy's dollar–gold inverse is a trend-scale relationship, and he separates analysis from timing explicitly: the macro view sets conviction, the chart sets the trigger. Lien separately shows cross-market correlations invert over short windows. |
| **Evidence** | `moderate` — murphy_ta pp.27, 378–380; lien_fx_sessions p.93 |

### 9 — Asia-range compression into London (volatility, not direction)
| | |
|---|---|
| **Setup** | 08:00 UTC. The Asia 00–07 range is in the bottom quartile of its own 20-day distribution. |
| **Decision** | **Arm a two-sided breakout plan** for the London session — levels on both edges, no directional pre-commitment. |
| **Invalidation** | London elapses with no closed M15 outside the Asia range → stand down at 13:00 UTC and do not carry the plan into the overlap unchanged. |
| **Why** | Lien's stated common scenario is channel trading in Asia followed by a breakout in London or the US, and her range table shows European ranges materially exceed Asian ranges for the dollar majors. She does **not** say which way the break goes. |
| **Evidence** | `moderate` for the expansion, `untested` for any direction — lien_fx_sessions pp.84, 151 |

### 10 — Carter's Good Night Gold, restated (and why it is not a session-direction claim)
| | |
|---|---|
| **Setup** | 04:30 UTC (11:30pm EST). D1 ADX(14) > 20 and D1 trend up. Gold is +$3 to +$20 versus the 18:30 UTC (1:30pm EST) settlement. |
| **Decision** | **OPEN long** with a fixed 6-point stop and 60-point target, held through the European open; optional partial exits at +20 and +40. |
| **Invalidation** | ADX ≤ 20 (choppy), or displacement outside the 3–20 band — Senters explicitly passes the trade when gold is on the wrong side of settlement, and warns that being already extended leaves nothing to work with. |
| **Why** | The stated rationale is positioning ahead of the Asian open and the imminent European open to capture the volatility that boundary brings. Note what conditions the trade: the **daily** trend and a bounded displacement — not the Asian session's own direction. |
| **Evidence** | `untested`, and treat with suspicion. Senters puts the hit rate somewhere in the low-to-mid thirties against a 10:1 payoff, which would imply an expectancy near +17 points per trade. A live edge that large would not survive publication; Carter himself documents exactly that decay for his own 3:52 trade. Do not implement without an independent test on the tick archive. — carter_mastering pp.387–388, 393; p.13 |

### 11 — FAILURE case: the pattern that decayed
| | |
|---|---|
| **Setup** | A time-of-day setup that tested well historically — e.g. a fixed-clock reversal in the last minutes of a low-volume window. Backtest Sharpe is attractive. Live results drift to zero after a few months. |
| **Decision** | **Retire it.** Do not re-optimise the parameters. |
| **Invalidation** | n/a — this *is* the invalidation. |
| **Why** | Carter names this precisely: his 3:52 trade stopped working once readers crowded into it, and he attributes the fragility to it being a low-volume setup at a specific time of day — a small amount of extra flow was enough to break it. Chan generalises: strategies that performed superbly before a regime shift may simply stop, and live-vs-backtest divergence is usually structural rather than a backtesting error. Both authors say re-fitting is the wrong response. |
| **Evidence** | `strong` — carter_mastering p.13; chan_algo_trading pp.43, 201, 207 |

### 12 — FAILURE case: reward:risk mistaken for edge
| | |
|---|---|
| **Setup** | Price approaches a level. The plan is a 1-unit stop for a 10-unit target, justified as "I only need to be right 1 in 10." |
| **Decision** | **SKIP** unless there is an independent structural reason the level should hold. |
| **Invalidation** | A demonstrated non-random response at the level — rejection with closed-bar evidence and an effort/result mismatch. |
| **Why** | Grimes works the arithmetic: in a random walk, a 10:1 target produces a win rate just over 9% and an expectancy of zero. Payoff geometry cannot manufacture edge; only non-random price behaviour can. He also notes real markets stop at random levels often enough that support/resistance appears where none exists. |
| **Evidence** | `strong` — grimes_art_science pp.114, 119 |

### 13 — Weekend / rollover transition
| | |
|---|---|
| **Setup** | 22:10 UTC Sunday. Price gapped from Friday's close. A trigger fires on the first M5 bars. |
| **Decision** | **WAIT** until a session's worth of structure exists. |
| **Invalidation** | Structure forms and the gap is either accepted or filled on closed bars. |
| **Why** | The reopen has the thinnest participation of the week; Carter separately observes gold is thin at its own reopen, and Dalton treats a gap as a form of excess whose meaning only resolves once the next session's participants weigh in. |
| **Evidence** | `moderate` — carter_mastering p.387; dalton_mind_over_markets p.253; dalton_markets_momentum p.99 |

---

## Learning outcome

After this topic the model must, for any XAUUSD decision, (a) name the active session from the closed bar's UTC timestamp and state what changes at the nearest boundary, (b) express tick volume only as a ratio to a same-session baseline and always alongside a price result, never alone, and (c) refuse to assert that one session's direction implies the next session's direction, instead naming the specific two-stage overnight-inventory or sweep-then-acceptance test it would need to run. It must state that any single trade is one draw from a distribution, distinguish the analysis stage (macro, intermarket, dollar) from the timing stage (closed-bar structure on a named timeframe), and refuse to let the former trigger or veto the latter. When the market is balanced and two-sided with no edge test, its output must be `skip`.

---

## Implementation

| Field | Computation | Timeframe | Notes |
|---|---|---|---|
| `session` | Bucket the closed bar's UTC hour: 00–07 asia, 07–08 pre_london, 08–13 london, 13–16 overlap, 16–21 ny, else off | any | **DST hazard.** Lien's boundaries are local-centre times (lien_fx_sessions pp.83–89). London and New York shift by an hour at different dates, so a fixed UTC grid is misaligned for most of the year and the overlap changes *width* during the 2–3 week windows when the two regions disagree. Log which DST regime is in force alongside the session label. |
| `trade_permitted` | Policy flag per session | any | Policy, not market fact. Keep it separate from `session` so the market model and the risk gate can be evaluated independently. |
| `session_seconds_remaining` | Session end minus bar close time | any | Used to suppress entries that cannot reasonably resolve before the regime changes. |
| `asia_high`, `asia_low`, `asia_range` | Max/min of completed M5 bars with `session == asia` for the current UTC day | M5 → session | Closed bars only. Undefined until 00:05 UTC. |
| `asia_range_pctile` | Rank of `asia_range` in the trailing 20 days of Asia ranges | D1 | Drives example #9. Low quartile = arm two-sided breakout. |
| `overnight_inventory` | Fraction of completed Asia M5 bars whose close is above the prior NY-session close; `long` if >0.65, `short` if <0.35, else `neutral` | M5 → session | Direct restatement of dalton_mind_over_markets p.250, with the pit-session settle replaced by the prior NY close. The 0.65/0.35 cut is arbitrary and must be calibrated on the archive. |
| `inventory_adjusted` | Whether price traded back through the Asia value midpoint within the first N closed M15s of London | M15 | The second stage of the two-stage read. Non-adjustment is the actionable signal (example #2). |
| `tv_ratio` | Bar tick volume ÷ rolling median tick volume for the same timeframe **and same session** over the trailing 20 sessions | M5/M15/M30/H1 | Never compare raw tick volume across sessions. Broker-specific (couling_volume p.20). |
| `effort_result` | `tv_ratio` paired with (bar range ÷ ATR) and close position within the bar | same bar | Wyckoff effort-vs-result; the mismatch is the signal (couling_volume p.11). |
| `spread_proxy` | Not available from OHLCV. If the feed carries bid/ask, log median spread per session; otherwise use per-session realised slippage from the trade log as a stand-in | tick / trade log | **Flag: data the bot may not have.** Lien claims FX spreads are as tight at night as by day (lien_fx_sessions pp.21–22, 27); for retail XAUUSD this is very likely false and must be measured, not assumed. |
| `news_blocked` | External economic calendar; block new entries inside a window around high-impact releases; block on stale/unreachable feed | event | **Flag: external dependency.** Lien's measured knee-jerk window is ~20 min (pp.76–77); use a wider guard. Fail closed. |
| `news_reaction` | Sign and magnitude of the first fully-closed M15 after the release versus the pre-release price | M15 | Implements murphy_ta p.244 — grade the reaction, not the number. |
| `dxy_h4_trend` | Sign of an H4 trend measure on the dollar index | H4 | **Flag: requires a second instrument the bot may not stream.** Filter for size/conviction only; must never veto or trigger (murphy_ta p.27). Re-estimate the gold/dollar relation on a rolling window and let it expire (lien_fx_sessions p.93). |
| `real_rates`, `risk_sentiment` | — | — | **Flag: not derivable from OHLCV and not covered by any book in this corpus.** Do not fabricate. |
| `order_flow`, `delta`, `bid_ask_aggression` | **Do not implement.** | — | Spot XAUUSD publishes no trade prints or sizes (chan_algo_trading p.29); Carter's delta tool is stated not to work on spot FX (carter_mastering p.398). Any such field would be fabricated. |
| `pattern_age`, `live_vs_backtest_drift` | Days since the rule was adopted; rolling live expectancy versus backtest expectancy | per rule | Implements the decay discipline (chan_algo_trading pp.43, 207; carter_mastering p.13). Persistent divergence retires the rule; it does not trigger re-optimisation. |

---

## Contradictions between sources

| Position A | Position B | Resolution for this bot |
|---|---|---|
| **Lien**: with a good online broker, a decent online broker makes out-of-hours FX no worse on liquidity or spread than any other part of the day (pp.21–22, 27). | **Lien, same book**: participation, turnover share and pip ranges differ enormously by session, with the Europe–Asia overlap the thinnest window of the day (pp.84–89); **Dalton**: liquidity is by far best during the dominant session, and the overnight sample is too thin to validate activity (dalton_markets_momentum p.44); **Grimes**: patterns are bounded by liquidity and degenerate into noise below a threshold (p.56). | Lien's spread claim is a 2008 marketing-flavoured argument for FX over equities, and it contradicts her own data two chapters later. **Reject it.** Assume execution quality varies by session; measure `spread_proxy` per session from the live feed and treat any untested session as expensive. |
| **Lien**: the FX/metals market never stops, so a trader can work any hours and still find the same opportunity set (pp.20–22). | **Carter**: markets have local opens that behave like the equity open, and there are windows — lunchtime doldrums, August, opex Thu/Fri, Fed days — where you should simply not be trading (pp.72, 345, 493); **Dalton**: liquidity is optimal only in the dominant session (dalton_markets_momentum p.44). | Continuous quoting is not continuous opportunity. **Carter and Dalton win.** Encode session-conditional permission and size, and default to `skip` in thin windows rather than searching harder for a setup. |
| **Coulling**: tick volume is a valid volume proxy, roughly 90% representative of true market activity (pp.20–21). | **Chan**: in FX there are no published trade prices or sizes at all, quotes are venue-dependent, and no rule forces any venue to the consolidated best bid/ask (pp.28–29); **Coulling herself**: tick volume differs between platforms and depends on the broker's feed quality (p.20). | Both are right about different things. Tick volume is a legitimate proxy for **activity** and useless as a proxy for **size**. The "90%" figure is unsourced in the book and must not be cited as a fact. Use `tv_ratio` for effort-vs-result only; never infer participant size, direction, or institutional intent from it. |
| **Coulling**: volume–price analysis will never reduce to an automated procedure, because reading it is an interpretive craft (p.22). | **Chan**: discretionary judgment is exactly what data-snooping bias exploits; prefer few parameters and simple linear rules (pp.22–23); **Elder**: following explicit rules is the trader's advantage over the crowd (p.20). | The bot cannot be discretionary. **Resolve toward Chan.** Automate only the mechanical, falsifiable core of VPA (`tv_ratio` + range + close location, evaluated on closed bars), accept that the interpretive richness Coulling describes is not reproducible, and label anything derived from it no higher than `moderate`. |
| **Murphy**: market action discounts everything; price alone is sufficient and price leads the known fundamentals (pp.23–24, 26–27). | **Lien**: nearly everyone factors economic data in; pure technical formations fail on major fundamental events, and automated systems in particular need to switch off around releases (pp.53, 75). | Not actually opposed — Murphy is about *forecasting*, Lien about *survival*. **Adopt both**: price structure is the only entry trigger (Murphy), and the scheduled-event calendar is a hard gate on when that trigger may fire (Lien). |
| **Lien**: the *first* move at the London open is often the false one, driven by stop-running before the real direction emerges (pp.136–137). | **Carter**: consolidations built around the major local opens resolve fast and then run (p.345); **Senters**: enter at 04:30 UTC precisely to be positioned *ahead of* the European open in the daily-trend direction (p.388). | A live disagreement on the most important boundary for this bot. **Do not resolve by preference — resolve by measurement.** Until the tick archive says otherwise, require the boundary move to demonstrate *acceptance* (repeated closes beyond a level) rather than merely *displacement*. Acceptance satisfies Carter's continuation read and simultaneously filters Lien's sweep. |
| **Dalton**: extreme overnight inventory is usually adjusted early in the dominant session — an implicit fade (pp.250–252). | **Carter/Senters**: overnight displacement of 3–20 points in the daily-trend direction is a reason to hold *through* the next open — a continuation (p.388). | Both are conditional and the conditions differ: Dalton's fade is unconditional on higher-timeframe trend, Senters' continuation requires D1 ADX>20 and D1 trend alignment. **Encode the conjunction**: fade extreme overnight skew *only when the daily chart is not trending*; allow continuation *only when it is*, and require the displacement to be bounded (Senters' 3–20 band, generalised as a fraction of daily ATR). |
| **Carter/Senters**: the Good Night Gold trade risks 6 to make 60 and works 30–40% of the time (p.388). | **Douglas**: consistency comes from a modest edge over a large sample — his benchmark is a casino's ~4.5% (pp.80–81); **Chan**: published, crowded, low-volume time-of-day setups decay (pp.43, 176); **Carter himself**: his 3:52 trade died on publication (p.13). | The stated win rate and payoff imply an edge orders of magnitude larger than anything Douglas or Chan treats as realistic. **Label `untested` and require independent verification.** Its structural components (session-boundary positioning, higher-timeframe trend gate, bounded displacement) are worth testing; its claimed statistics are not evidence. |

---

## Gaps

Things this topic needs that **no book in this corpus supplies**:

1. **Any measurement on XAUUSD spot.** Lien's session tables are FX pairs, 2002–2004. Dalton's work is CBOT/CME pit and electronic futures. Carter's gold material is COMEX GC futures with a 18:30 UTC settlement that spot XAUUSD does not have. Nobody in the corpus measures spot gold by session. Every session-conditional number in this file must be re-derived from the tick archive before use.
2. **Whether XAUUSD behaves like a dollar major or like a yen cross in Asia.** Lien's own table (p.84) shows the "Asia is quiet" claim holds for EUR/USD, GBP/USD, USD/CHF and USD/CAD but *fails* for USD/JPY (78 vs 79 pips) and is weak for GBP/JPY. Gold has genuine Asian physical demand. Which bucket it falls in is unknown and is the single highest-value first measurement.
3. **The Asia→London directional question itself.** No source in this corpus claims it. The nearest analogues — Dalton's overnight inventory adjustment and Lien's real-deal sweep — both point *against* naive continuation, while Carter's GNG points weakly for it under daily-trend conditioning. The hypothesis is genuinely open and must be labelled `untested` in every artefact until tested.
4. **DST handling.** Every source gives session times in local-centre terms. None addresses what happens to a fixed UTC session grid across the four annual DST transitions, or during the weeks when London and New York disagree. This will silently corrupt any session statistic computed on a fixed grid.
5. **Retail XAUUSD spread and slippage by session.** Lien asserts FX spreads are clock-invariant; that is almost certainly false for retail gold and is untested here. Needs direct measurement from the broker feed.
6. **Real rates and risk sentiment as gold drivers.** Murphy (1999) gives dollar–gold and gold-leads-commodities. The post-2008 framing of gold against real yields and risk appetite appears nowhere in the corpus. Do not synthesise it from these books.
7. **Modern microstructure.** Brooks mentions HFT in passing (p.19) and Grimes advises trading a timeframe that avoids it (p.25), but there is no treatment of how HFT, aggregation and last-look affect a retail XAUUSD feed's tick volume or its session character.
8. **Sample-size guidance for session studies.** Douglas argues for large samples and Chan for statistical significance, but neither gives a usable minimum for a session-conditional test. With ~250 sessions a year, a per-session directional study is data-poor by construction and needs an explicit power analysis before its result is believed either way.

---

## JSONL seeds

```json
{"principle_id":"market_two_way_auction","topic":"market","lesson":"The market exists to facilitate trade; it auctions upward until buyers stop and downward until sellers stop, and the record of that search — price, time, volume — is the only unbiased information available (dalton_mind_over_markets p.36; dalton_markets_in_profile pp.40-41).","practice":"Describe any chart state as an auction: what price is advertising, how long it has stayed there, and whether volume confirmed the advertisement worked.","guardrail":"Never describe the market as 'bullish' or 'bearish' without naming a timeframe and the structure on it.","evidence_label":"strong"}
{"principle_id":"market_session_regime","topic":"market","lesson":"XAUUSD quotes continuously but its participant mix changes at each session boundary; liquidity, range and follow-through are properties of the clock, not of the instrument (lien_fx_sessions pp.83-89; dalton_markets_momentum p.44).","practice":"Stamp every decision with the UTC session label derived from the closed bar, reset per-session statistics at boundaries, and state what changes at the nearest boundary.","guardrail":"Do not carry a volume, range or volatility baseline across a session boundary, and log which DST regime is in force.","evidence_label":"strong"}
{"principle_id":"market_no_session_direction_carryover","topic":"market","lesson":"No source in this corpus claims that one session's direction predicts the next session's direction; Lien's London-open read is a fade of the first move and Dalton's overnight-inventory read expects an early adjustment, while Carter's continuation trade is gated by the daily trend rather than by Asian direction (lien_fx_sessions pp.136-137; dalton_mind_over_markets pp.250-252; carter_mastering p.388).","practice":"When asked whether Asia biases London, answer that the claim is untested, name the two-stage test (extreme inventory, then adjustment or non-adjustment on closed M15s), and refuse to assert a direction.","guardrail":"Label any session-carryover claim 'untested' until measured on the tick archive; never let a book's confident tone raise the label.","evidence_label":"untested"}
{"principle_id":"market_range_expansion_not_direction","topic":"market","lesson":"A compressed Asian range legitimately raises the expectation of range expansion in London or the US, but says nothing about which way (lien_fx_sessions pp.84, 151).","practice":"On a bottom-quartile Asia range, arm levels on both edges and pre-commit to neither.","guardrail":"Never convert a volatility expectation into a directional bias.","evidence_label":"moderate"}
{"principle_id":"market_tick_volume_is_activity","topic":"market","lesson":"Spot gold publishes no trade prints or sizes; tick volume counts quote changes and is a broker-specific proxy for activity only (couling_volume pp.20-21; chan_algo_trading p.29).","practice":"Express tick volume as a ratio to a same-session rolling median and always pair it with a price result — range and close location on the same closed bar.","guardrail":"Never infer participant size, direction, delta or institutional intent from tick volume, and never quote a raw tick-volume number as evidence.","evidence_label":"strong"}
{"principle_id":"market_effort_vs_result","topic":"market","lesson":"The signal is the mismatch between effort and result: high activity with a small range and a poor close means the move is being absorbed (couling_volume p.11).","practice":"For each candidate bar, report effort (tv_ratio) and result (range/ATR, close position) together and name whether they agree.","guardrail":"High volume alone is not bullish or bearish; report the pair or report nothing.","evidence_label":"moderate"}
{"principle_id":"market_price_leads_fundamentals","topic":"market","lesson":"Known fundamentals are already priced; important moves often begin before any public reason exists, and the market's reaction to a release carries more information than the release (murphy_ta pp.26-27, 244).","practice":"Grade the first fully-closed bar after a release against the pre-release price and treat non-reaction to favourable news as evidence against that direction.","guardrail":"Never open a position because of a macro reason; macro sets conviction and size, structure sets the trigger.","evidence_label":"moderate"}
{"principle_id":"market_intermarket_is_a_filter","topic":"market","lesson":"Gold and the dollar usually trend in opposite directions and gold tends to lead the commodity complex, but these are trend-scale relationships whose strength drifts and can invert on short windows (murphy_ta pp.378-380; lien_fx_sessions p.93).","practice":"Use the H4/D1 dollar trend only to adjust size and conviction, and re-estimate the relationship on a rolling window.","guardrail":"An intermarket conflict may reduce size; it may never veto or trigger a valid closed-bar setup, and it may never be quoted on M5/M1.","evidence_label":"moderate"}
{"principle_id":"market_patterns_decay","topic":"market","lesson":"Patterns stop working because market structure or the crowd changed, not because the test was wrong; Carter's own low-volume time-of-day setup died once it was published (carter_mastering p.13; chan_algo_trading pp.43, 201, 207).","practice":"Record each rule's adoption date and monitor live expectancy against backtest expectancy; retire on persistent divergence.","guardrail":"Do not re-optimise parameters in response to live underperformance, and treat any low-participation clock-specific setup as fragile by default.","evidence_label":"strong"}
{"principle_id":"market_single_trade_is_a_draw","topic":"market","lesson":"Any single trade is a unique event with an unknowable outcome; consistency comes from a modest edge over a large sample, on the order of a casino's few percent, not from being right on this trade (douglas_zone pp.12, 80-81).","practice":"State expectation as a distribution over a sample and predefine risk before entry.","guardrail":"Never express confidence in an individual outcome, and treat any claimed setup with an implausibly large expectancy as unverified rather than as an opportunity.","evidence_label":"strong"}
{"principle_id":"market_balance_means_skip","topic":"market","lesson":"A balanced, two-sided market rotating inside a range is statistically close to a random walk, and favourable reward-to-risk geometry cannot manufacture an edge there (grimes_art_science pp.31, 119).","practice":"When there is no edge test at a defined boundary and no effort/result mismatch, output skip.","guardrail":"Do not justify a trade with reward:risk alone; a 10:1 target in a random walk has zero expectancy.","evidence_label":"moderate"}
```
