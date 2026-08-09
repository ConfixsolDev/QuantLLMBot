# Shared brief for all topic distillation agents

## Corpus
Book corpus extracts are optional/offline tooling (see `python_utilities_for_models/extract_book_corpus.py`). Distilled topics in this folder are the working source.
Each file has `[[PAGE n]]` markers so you can cite page numbers. Slugs:

| slug | book |
|---|---|
| brooks_trends | Al Brooks, Trading Price Action: Trends (2011), 480pp |
| brooks_ranges | Al Brooks, Trading Price Action: Trading Ranges (2012), 237pp |
| brooks_reversals | Al Brooks, Trading Price Action: Reversals (2012), 587pp |
| grimes_art_science | Adam Grimes, The Art & Science of Technical Analysis (2012), 482pp |
| dalton_mind_over_markets | James Dalton, Mind Over Markets, Updated ed., 296pp (24 image pages missing) |
| dalton_markets_in_profile | James Dalton, Markets in Profile (2007), 226pp |
| dalton_markets_momentum | James Dalton, Markets and Momentum, 259pp |
| murphy_ta | John Murphy, Technical Analysis of the Financial Markets (1999), 502pp |
| nison_candlesticks | Steve Nison, Japanese Candlestick Charting Techniques 2e (2001), 299pp |
| nison_beyond | Steve Nison, Beyond Candlesticks (1994), 278pp |
| lien_fx_sessions | Kathy Lien, Day Trading & Swing Trading the Currency Market 2e (2008), 308pp |
| elder_trading_room | Alexander Elder, Come Into My Trading Room (2002), 323pp |
| couling_volume | Anna Coulling, A Complete Guide to Volume Price Analysis (2013), 158pp |
| person_pivots | John Person, A Complete Guide to Technical Trading Tactics (2004), 288pp |
| carter_mastering | John Carter, Mastering the Trade 2e (2012), 526pp |
| chan_algo_trading | Ernie Chan, Algorithmic Trading: Winning Strategies and Their Rationale (2013), 226pp |
| douglas_zone | Mark Douglas, Trading in the Zone (2000), 145pp |
| weis_trades | David Weis, Trades About to Happen — 24pp EXCERPT ONLY, intro only |

## Reproducing the corpus
```
python scripts/extract_book_corpus.py --books-dir "E:\Trading Books" --out-dir model_training/knowledge/_pdf_extract
```

## How to read efficiently
Files are large (up to 1.4MB). Do NOT read them end to end. Use Grep with `output_mode:
"content"` and generous `-C` context (30-60 lines) against the `_pdf_extract` directory,
then Read specific regions with offset/limit around the strongest hits. Search many
synonyms — these authors use different vocabulary for the same idea. Budget roughly
25-45 searches and 10-20 targeted reads.

## Hard constraints
1. **No verbatim copying.** These books are under active copyright. Every sentence you write
   must be your own restatement of the concept. Never reproduce a sentence, definition, or
   list from a book. Paraphrase at the level of the *idea*, not the wording. Short technical
   terms (e.g. "morning star", "value area") are fine; running prose is not.
   Verify: `python scripts/check_no_verbatim.py --corpus-dir knowledge/_pdf_extract --check-files knowledge/topics/*.md --n 12`
2. **Cite as `slug p.N`** so claims are traceable, e.g. `brooks_ranges p.112`.
3. **Closed candles only, no lookahead.** Every implementation rule must be computable from
   bars that have already closed at decision time.
4. **Evidence labels** on every worked example and every rule that could be traded:
   - `strong` — multiple independent books agree AND the mechanism is structural/definitional
   - `moderate` — well-established in the literature but essentially untested statistically
   - `weak` — one author's assertion, or a heuristic with known counterexamples
   - `untested` — popular practitioner claim with no rigorous test in either direction
   Be honest. Most classical technical analysis is `moderate` at best. Do not inflate.
5. **Instrument context:** the target is XAUUSD (spot gold) intraday, timeframes D1/H4(NY)/H1/
   M30/M15/M5/M1, sessions Asia 00-07 UTC, London 08-13, overlap 13-16, NY 16-21 UTC.
   **H4 bars:** `America/New_York` anchor (00/04/08/12/16/20 NY close) — not UTC 00/04/08.

## Required output structure
Write a single markdown file. Use this exact section order:

```
# Topic N — <Title>

> **Sources read:** <slugs actually used, with page ranges>
> **Status:** v2 full-corpus distillation, 2026-08-08

## Core concepts
Table: Concept | Definition (one line, your words) | Sources (slug p.N) | Evidence

## Distilled rules
Numbered list. Each rule must be an instruction, not an observation. Include the source.

## Worked examples
MINIMUM 8 examples, formatted as a table or as short blocks, each with:
Setup (observable state) | Decision (open/wait/skip + direction) | Invalidation (what
proves it wrong) | Why (which concept) | Evidence label
Draw the examples from what the books actually teach, restated into XAUUSD/session terms.
Include at least 2 examples where the correct decision is SKIP or WAIT, and at least
1 example where the pattern FAILS and the book explains why.

## Learning outcome
2-4 sentences: what the model must be able to DO after this topic. Behavioural, testable.

## Implementation
Table: Field | Computation | Timeframe | Notes. Everything must be computable from closed
OHLCV bars plus session clock. Flag anything that needs data the bot may not have.

## Contradictions between sources
Table: Author A position | Author B position | How to resolve for this bot. Find at least 3
REAL disagreements from your reading — do not invent them, and do not paper over them.

## Gaps
What this topic needs that no book in the corpus covers.

## JSONL seeds
5-10 stage-01 principle seeds in this exact shape:
{"principle_id":"...","topic":"<topic_slug>","lesson":"...","practice":"...","guardrail":"...","evidence_label":"..."}
```

Aim for a substantial file — roughly 400-700 lines. Depth over breadth: it is better to
explain 12 concepts precisely with page citations than to list 40 shallowly.
