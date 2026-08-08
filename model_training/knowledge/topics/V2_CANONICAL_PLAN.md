# Plan — make v2 canonical, clean the tree, and ground the examples in MT5 data

**Status (2026-08-08):** Phase **1.1 done** — v2 files promoted to `topics/` root (9 topics + map + brief + seeds).  
Phases 2–5 still pending. Remove stale `topics/v2/` folder if anything remains.

---

## Operator decisions (locked)

**Doctrine (2026-08-08):**
> Levels tell you *where*; nested candles tell you *how price behaves there*;  
> session (UTC) + H4(NY) tell you *when* it matters.

**D1 — H4 anchoring: RESOLVED → (b) NY H4 canonical**
- Keep `H4_NY` (`America/New_York`, closes 00/04/08/12/16/20 NY).
- UTC session grid stays for Asia/London/overlap/NY **permission** rules.
- Document in every H4 example: bar uses NY anchor; session label uses UTC.
- Winter/summer: H4 UTC open hours shift ±1h at DST — tag examples with `bar_timezone`.

**Topic 10 (planned, not written):** `10_intra_bar_moment.md` — last slice of parent bar at levels (M1 inside M5…), intra-bar phase stats from M1 CSV.

**D2 — rebuild M1 from ticks?** Still open.

**D3 — Grimes duplicate.** Still open.

**D4 — example volume target.** Still open (~800 recommended).

---

## Two findings from recon that change the shape of the work

### 1. The H4 grid is NY-anchored and slides one hour against UTC twice a year

`datasets/raw/candles/XAUUSDr/H4/` is labelled `_H4_NY` with `bar_timezone:
America/New_York`, and it is genuinely NY-anchored. Verified against the data:

| Month | H4 bar open hours (UTC) | NY offset |
|---|---|---|
| 2026-07 | 00, 04, 08, 12, 16, 20 | UTC−4 |
| 2026-01 | 01, 05, 09, 13, 17, 21 | UTC−5 |

In summer the London open at 08:00 UTC lands exactly on an H4 boundary. In winter it lands
one hour inside an H4 bar. So "the H4 that contains the London open" is a structurally
different object depending on the season, and any rule that keys off both an H4 close and a
UTC session boundary is silently inconsistent across the DST changeover.

Topic 4 flagged broker bar anchoring as a gap on theoretical grounds. This is that gap,
confirmed, in your own data. **D1 resolved:** keep NY H4; never mix UTC session boundaries with
H4 close rules without documenting both clocks.

### 2. Lower-timeframe history starts 2026-04-28

| Timeframe | Coverage | Files |
|---|---|---|
| H1 | 2014-01-14 → 2026-08-07 (12.6 yrs) | 152 |
| H4_NY | 2014-01 → 2026-08 (derived from H1) | 152 |
| M1 / M5 / M15 / M30 | **2026-04-28 19:45 → 2026-08-07** (~101 days) | 5 each |
| Ticks | 2026-01-01 → 2026-08-07, 61.8M rows, 4.68 GB | 187 |

MT5 only retains ~3 months of M1 for this symbol. So any example needing M5/M15 timing is
confined to a 101-day window, roughly 29,000 M5 bars. That is enough for a first pass but it
caps how many independent instances exist, and it means every intraday example comes from one
season and one volatility regime.

The ticks predate M1 by four months. M1 can be rebuilt from ticks back to 2026-01-01, which
would roughly double the intraday window. That is real work, so it is proposed as an optional
phase rather than assumed. **This is decision D2 below.**

---

## Decisions still open

**D2 — rebuild M1 from ticks?** Yes doubles the intraday window to ~7 months at the cost of
processing 4.68 GB. No keeps the window at 101 days and ships sooner.

**D3 — the Grimes duplicate.** `E:\Trading Books\The Art and Science…annotated.pdf` and
`grimes/The Art and Science…2012.pdf` are 100% content-identical. Do your annotations live in
the root copy? If yes I keep that one and drop `grimes/`; if you do not care, I drop the root
copy. Same question does not arise elsewhere.

**D4 — example volume target.** How many bar-grounded examples for this pass: ~300 (tight,
reviewable), ~800 (recommended), or as many as the detectors find (could be several thousand,
unreviewable by hand)?

---

## Decisions (reference — D1 closed above)

## Phase 1 — Canonicalise v2 and clean the tree

**1.0 Done:** `topics/KNOWLEDGE_MAP.md`, `topics/README.md`, `knowledge/README.md`.

**1.1 Promote v2.** ✅ Done — nine topic files + `_SHARED_BRIEF.md`, `_all_seeds.json`, `V2_CANONICAL_PLAN.md` at `topics/` root.

**1.2 Rewrite the index.** ✅ Done — root `KNOWLEDGE_MAP.md` is the single map; links are sibling files. Delete leftover `topics/v2/` if present.

**1.3 Update `topics/README.md`** with the v2 status line, the evidence-label definitions, the
no-copy policy, and a pointer to the corpus rebuild script.

**1.4 Cleanup script** — `scripts/cleanup_v2.ps1`, every line commented with why:

| Path | Reason |
|---|---|
| `Trading Books\dalton\Mind over Markets (verify title).pdf` | 30-page file, byte-identical to old Brooks Reversals; real MoM now present |
| `Trading Books\brooks\Al-Brooks-Trading-Price-Action-Trends-alt.pdf` | 56 MB, 96% duplicate of the Trends PDF |
| `Trading Books\nison\Japanese Candlestick…2001.pdf` | image scan, 0 extractable text; `_text.pdf` supersedes |
| `Trading Books\murphy\Technical Analysis…1999.pdf` | image scan, 0 extractable text; `by John J. Murphy.pdf` supersedes |
| `Trading Books\` Grimes duplicate | per decision D3 |
| `Trading Books\substitutes\` | empty directory |
| `knowledge\_pdf_extract\Al_Brooks_—_…Reversals.txt` | 57 KB stub from the 30-page file |
| `knowledge\_pdf_extract\Mind_over_Markets_(verify_title).txt` | same stub |
| `knowledge\_pdf_extract\Japanese_Candlestick…2001.txt` | 594 bytes, failed extract |
| `knowledge\_pdf_extract\Technical_Analysis…Guide_to_Trading_M.txt` | 1.1 KB, failed extract |
| `knowledge\_pdf_extract\Al-Brooks-…Trends-alt.txt` | duplicate book |
| `knowledge\topics\v2\` | after promotion to `topics/` |

Estimated reclaim: ~90 MB, 12 items.

---

## Phase 2 — Fix the corpus so it is reproducible

The `_pdf_extract/` files in your repo are the truncated ones — Brooks *Ranges* at 39%,
Grimes at 47%. That is the defect that produced the thin v1 topics, and it is still sitting
there waiting to mislead the next run.

**2.1** Ship `scripts/extract_book_corpus.py` — the exact `pdftotext -layout` extraction used
for v2, emitting `[[PAGE n]]` markers, with a slug map and a manifest recording pages, chars
and words per book so truncation is detectable at a glance.

**2.2** Regenerate all 18 extracts at full length and overwrite `_pdf_extract/`, replacing
`manifest.json` with one that records the real counts. Total ~13 MB; commits in two batches
under the 100 MB/call limit.

**2.3** Point `_SHARED_BRIEF.md` at `model_training/knowledge/_pdf_extract/` instead of
`/tmp/corpus/`, and note the rebuild command so anyone can reproduce it.

**2.4** Add `scripts/check_no_verbatim.py` — the 11/12-gram overlap checker used for
verification, so the no-copy rule is enforceable on every future distillation rather than
being a one-off.

---

## Phase 3 — BOOK_REGISTRY

Add rows for the five books v2 cites that the registry does not list as first-class entries:
Carter *Mastering the Trade*, Chan *Algorithmic Trading*, Grimes *Art & Science*, Coulling
*VPA*, Elder *Come Into My Trading Room*, Person *Technical Trading Tactics*, Nison *Beyond
Candlesticks*. Each row gets: registry number, on-disk path, page count, extracted word count,
which of the nine topics it feeds, and status.

Also correct two existing rows: Weis is a 23-page excerpt, not the book; the Nison and Murphy
rows should point at the readable PDFs rather than the scans being deleted.

---

## Phase 4 — Ground the worked examples in MT5 bars

This is the substantial new work. The 124 v2 worked examples are **templates** — they describe
a setup shape, not an instance. Turning them into training data means finding real occurrences
in your bars.

**4.1 Stage the candle cache.** All six timeframes, ~18 MB of CSV. The 4.68 GB of ticks is
*not* needed for candle-based examples and stays on your disk. Schema is already clean:
`symbol,timeframe,time_utc,open,high,low,close,tick_volume,spread,real_volume,source,
derived_from,bar_timezone`.

**4.2 Triage the 124 examples** into three buckets:

- **A — mechanically detectable.** Setup is expressible as closed-bar conditions. Example:
  "M5 probes the Asian high and closes back inside." Roughly 60–75 of the 124.
- **B — detectable with a scored judgement.** Needs a soft feature such as "weak momentum on
  the test rally". Detect candidates, compute the feature, threshold it, and flag every
  instance for review rather than trusting the threshold. Roughly 30–40.
- **C — not instantiable.** Pure doctrine such as "never infer H4 bias from M1". These stay
  stage-01 principles and need no bars. Roughly 15–25.

I will produce the triage table for your review *before* writing any detector, because bucket
assignment determines everything downstream.

**4.3 Build a feature layer** computed once per bar per timeframe, closed bars only: body
fraction, wick bias, close location in range, ATR, range percentile, tick-volume ratio versus
rolling median, distance to nearest level, session label, position within the parent H4,
swing-pivot orders 1–3 per Grimes's recursive definition, and balance/trend classification.
Every downstream detector reads this layer, so a definition is fixed in exactly one place.

**4.4 Write one detector per bucket-A/B example**, each returning matched decision timestamps
plus the evidence that fired. Detectors are pure functions of bars at or before the decision
time — enforced structurally, not by convention.

**4.5 Emit JSONL** in the existing v001/v002 schema so it merges cleanly:

- `curriculum_stage`: `03_internal_h4_flow_level_volume` for structure and flow examples,
  `04_decision_contract_examples` for decisions.
- `messages[1]` (user): market snapshot — closed bars only, level map, session, features.
- `messages[2]` (assistant): the decision contract with the same field set v001 uses
  (`action`, `direction`, `confidence`, `auction_assessment`, `validation`, and so on).
- Record level: `example_id`, source topic and example number, `evidence_strength`,
  `detector_version`, `no_lookahead_confirmed`, and the **forward outcome** — what price
  actually did — kept strictly outside `messages` so it can inform review without ever
  reaching the model.

**4.6 Sampling and balance.** Detectors will over-fire on common patterns. Cap instances per
example template, stratify across session, month and direction, and log what was dropped so
coverage is never silently truncated.

**4.7 Validation gate** before anything is written: schema match against v001 field-for-field;
a lookahead audit asserting every referenced bar closed at or before the decision timestamp;
duplicate detection on `(template, timestamp)`; label balance report; and a random sample of
20 rendered as human-readable summaries for you to eyeball.

---

## Phase 5 — Doctrine promotion gate

v2 is richer than `store/core_skill.md`, but promoting it wholesale would push `moderate` and
`untested` material into live doctrine. So promotion is gated, not bulk.

**5.1** Emit `knowledge/PROMOTION_QUEUE.md`: every v2 rule that is a candidate for
`core_skill.md`, sorted by evidence label, each mapped to the `core_skill` section it belongs
in, with the exact proposed wording and its page citations.

**5.2** Auto-eligible: `strong` items only, and only where they do not contradict an existing
`core_skill` rule. Contradictions get listed separately with both wordings side by side for
you to arbitrate — there will be some, because v2 contradicts classical doctrine in several
places on purpose.

**5.3** `moderate` items go to `store/principles_registry.json` as candidates, not to
`core_skill.md`. `weak` and `untested` items go to a measurement backlog with the specific
tick-archive test that would upgrade them.

**5.4** No edit to `store/core_skill.md` happens in this pass. I prepare the diff; you approve
it. The store is live doctrine and should not move on my judgement alone.

---

## Sequencing and what it costs

| Phase | Depends on | Rough effort |
|---|---|---|
| 1 Canonicalise + cleanup script | D3 | small |
| 2 Corpus rebuild | — | small, mostly compute |
| 3 BOOK_REGISTRY | 2 | small |
| 4 MT5 grounding | **D1, D2, D4** | large — the bulk of the work |
| 5 Promotion queue | 1 | medium |

Phases 1–3 are mechanical and safe, and I would do them in one pass. Phase 4 is where the
real value is and where I would want the triage table reviewed mid-flight. Phase 5 ends in a
diff you approve rather than a change I make.

Suggested order: answer D1–D4, then run 1–3 together, review the Phase 4 triage table, then
build detectors, then Phase 5.
