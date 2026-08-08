# Knowledge map — v2 full-corpus distillation

Built 2026-08-08 from 18 books, 2,036,375 words, re-extracted at full length with page
markers. This supersedes the v1.2 topic set, which was distilled from text truncated at
roughly 500KB per book — Brooks *Trading Ranges* had lost 61% of its content, Grimes 53%,
Brooks *Trends* 49%.

**Canonical index:** this file (`KNOWLEDGE_MAP.md`)  
**Operator doctrine:** levels = *where* · nested candles = *how* · session + H4(NY) = *when*  
**Plan:** [`V2_CANONICAL_PLAN.md`](V2_CANONICAL_PLAN.md) · **Brief:** [`_SHARED_BRIEF.md`](_SHARED_BRIEF.md)

Source corpus and per-agent instructions: `_SHARED_BRIEF.md`.

---

## The nine topics

| # | Topic | File | Lines | Concepts | Examples | Rules | Seeds |
|---|---|---|---:|---:|---:|---:|---:|
| 1 | Market | `01_market.md` | 313 | 36 | 13 | 24 | 11 |
| 2 | Market structure | `02_market_structure.md` | 349 | 42 | 18 | 32 | 10 |
| 3 | Candlestick patterns | `03_candlestick_patterns.md` | 428 | 42 | 14 | 41 | 12 |
| 4 | Timeframe relations | `04_timeframe_relations.md` | 452 | 29 | 14 | 20 | 10 |
| 5 | ICT concepts | `05_ict_concepts.md` | 657 | 29 | 12 | 20 | 10 |
| 6 | FVG / imbalance | `06_fvg_imbalance.md` | 746 | 21 | 12 | 20 | 10 |
| 7 | Trend trading | `07_trend_trading.md` | 489 | 36 | 13 | 35 | 10 |
| 8 | Range trading | `08_range_trading.md` | 381 | 54 | 15 | 32 | 11 |
| 9 | Reversal trading | `09_reversal_trading.md` | 415 | 24 | 13 | 33 | 10 |
| | **Total** | | **4,230** | **313** | **124** | **257** | **94** |

Every topic file carries the same eight sections: core concepts, distilled rules, worked
examples, learning outcome, implementation, contradictions between sources, gaps, and JSONL
seeds. Examples are XAUUSD- and session-specific, decided on closed bars, and each states its
own invalidation.

---

## Primary source by topic

| Topic | Load-bearing sources | Counterweight |
|---|---|---|
| 1 Market | Dalton (all three), Lien, Murphy | Chan on cost and pattern decay |
| 2 Market structure | Grimes, Brooks *Ranges*, Dalton | Grimes's random-levels experiment |
| 3 Candlesticks | Nison (both), Brooks | Grimes on pattern statistics |
| 4 Timeframes | Elder, Murphy, Dalton, Brooks | Grimes and Chan on cross-horizon correlation |
| 5 ICT concepts | Brooks, Dalton, Murphy (as ancestors) | the whole topic is a translation exercise |
| 6 FVG / imbalance | Nison on windows, Murphy on gap types, Dalton on single prints | Chan's tested gap results |
| 7 Trend | Brooks *Trends*, Grimes, Dalton | Chan's Example 1.1 |
| 8 Range | Brooks *Ranges*, Dalton (all three) | Grimes on ranges as random walks |
| 9 Reversal | Brooks *Reversals*, Grimes, Murphy | Douglas on why traders pick tops |

Grimes and Chan carry the sceptical load across the whole set. They are the only two authors
in the corpus who test claims rather than assert them, and nearly every contradiction table
resolves toward one of them.

---

## What the corpus actually established

**The books refute themselves more often than they agree.** That turned out to be the most
valuable property of reading by topic rather than by book — the same claim gets made
confidently by one author and dismantled by another two shelves over.

The five findings that should shape the model's behaviour most:

Grimes hid the price bars on a chart, drew levels at random, restored the bars, and observed
textbook holds, breaks and role reversals (`grimes_art_science` pp.117–119). A level cannot be
validated by inspection, and favourable reward/risk geometry at a level is not a reason to
trade. This is the direct counterweight to Murphy's role-reversal chapter and it drove the
hardest gate in topic 2.

The naive higher-timeframe filter is refuted inside the corpus. Grimes rejects "higher
timeframe is always more important" and notes the cleanest lower-timeframe trends occur inside
higher-timeframe ranges; Dalton puts markets in balance 70–80% of the time, so a permanent
trend filter is mis-specified most of the time; Brooks observes you can always find a higher
timeframe that endorses the setup you want; Chan shows cross-horizon return correlations are
small, mostly insignificant, and flip sign between horizon pairs. Topic 4 therefore requires
the bot to classify higher-timeframe structure as trending or bracketing *before* applying any
directional filter, with "trending" as the exception it must prove.

Chan's Example 1.1 is the load-bearing calibration for topic 7: on one momentum backtest,
1,166 of 10,000 random return series matched only on kurtosis beat the strategy's actual
return. It sits above the concepts table, not buried in a footnote.

No book in the corpus claims Asian session direction predicts London session direction. Lien's
one cross-session statement is about volatility expansion, not direction, and her London-open
claim is a *fade* — the first impulse read as a stop-run. Dalton has the only serious version:
extreme overnight inventory usually gets adjusted early, and it is the *non*-adjustment that
signals. Carter's continuation trade is gated on the **daily** trend, not on Asia's direction.

On FVG, five authors independently state that intraday gaps essentially do not exist on liquid
24-hour instruments. On XAUUSD every true gap is a weekend gap — and Chan's *tested* result on
currencies framed at the London open is momentum, not mean reversion. The prior should be to
trade with the gap, not fade it. The three-candle FVG construct appears nowhere in the corpus
as a zone to trade; Brooks defines the identical geometry and uses it to *project a target*.

---

## Evidence posture

Seed labels across all 94 JSONL seeds: 40 `strong`, 51 `moderate`, 2 `weak`, 1 `untested`.

`strong` was reserved for claims that are definitional, arithmetic or structural — bar
composition, pattern completion on close, the break hierarchy, the trader's-equation
arithmetic, volatility scaling. **No directional claim anywhere in the nine files is labelled
`strong`.** Every ICT-specific term is `untested` or `weak` and carries a named tick-archive
measurement that would upgrade it.

This is deliberate and it is the point of the exercise. The books are written in a confident
register; the labels are not.

---

## The gap that spans every topic

**The corpus contains no base rate for gold.** Not one hit rate, expectancy or sample size for
any pattern, on any instrument, measured on XAUUSD. Brooks's 80% breakout-failure figure, the
90% first-hour-extreme figure, the 40/30/30 reversal outcome split — all are US-equity-session
practitioner estimates, several from the pre-1990 era, none sourced in the books themselves.

Three structural problems compound it:

Every session-based concept in the corpus — Dalton's initial balance, Elder's opening range,
Murphy's intraday pivot windows, Brooks's trend-from-the-open — presupposes one opening bell.
Spot gold has three plausible ones, and no author addresses the case.

Volume confirmation is required by Murphy, Dalton and Coulling, and is uncomputable on spot
gold. Tick count is a proxy for activity of unknown fidelity and is useless as a proxy for
size. Several classical patterns can therefore only ever carry a downgraded label.

No author gives an operational definition of a range boundary — all of them admit they draw it
by eye — yet boundary selection dominates every downstream statistic, including the 80% figure
itself. Similarly, "the H4 closed below support" depends entirely on broker bar anchoring,
which makes a meaningful share of topic 4's rules convention-dependent rather than
market-dependent.

Everything above is measurable on the tick archive. That is the natural next phase.

---

## Verification performed

All nine files were checked mechanically against the full source corpus:

12-word verbatim overlap against 1,993,743 corpus n-grams: **zero** remaining in prose.
Eleven-word overlap across all lines including tables: three remaining, all standard technical
vocabulary (the textbook higher-high/higher-low definition, and Brooks's named "failed low 2 /
failed high 2" terms) rather than copyrightable expression. Fifteen short attributed
quotations found in the first pass were rewritten into original phrasing to comply with the
dataset's `source_policy`.

All 94 JSONL seeds parse as valid JSON, carry the required keys, and use only the four
permitted evidence labels. Page citations resolve to slugs in the corpus and fall within each
book's actual page count.

---

## Next steps

1. **Convert seeds to stage-01 JSONL.** The 94 seeds map onto the existing
   `01_principle_foundation` schema with the same four-key assistant contract used by
   principles 011–060 in `complete_market_structure_v002`. Evidence metadata goes at record
   level, outside `messages`.
2. **Convert worked examples to stage 03/04.** The 124 examples already carry setup, decision,
   invalidation and reasoning — the shape the decision-contract examples need. They need real
   bar data attached before they are training-grade.
3. **Measure, do not assume.** The named tick-archive measurements are listed per topic in the
   `Gaps` sections. The FVG upgrade backlog in topic 6 alone has ten. Start with the
   reach-versus-react split and the XAUUSD weekend-gap fill curve — both are directly
   measurable from data you already have.
4. **Fill the Harris gap.** Nothing in the corpus covers limit-order-book mechanics, and it is
   the single strongest evidence base behind the liquidity concepts in topic 5.
