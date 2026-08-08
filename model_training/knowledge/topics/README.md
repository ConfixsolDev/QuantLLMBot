# Topic-based knowledge distillation

Read **by topic** (not book-by-book).

## Canonical (v2 at this folder root)

**Index:** [`KNOWLEDGE_MAP.md`](KNOWLEDGE_MAP.md)  
**Topics:** `01_market.md` … `09_reversal_trading.md`  
**Brief:** [`_SHARED_BRIEF.md`](_SHARED_BRIEF.md)  
**Plan:** [`V2_CANONICAL_PLAN.md`](V2_CANONICAL_PLAN.md)  
**Seeds (combined):** [`_all_seeds.json`](_all_seeds.json)

## Operator loop

> Levels = **where** · Nested candles = **how** · Session + H4(NY) = **when**

## Rules

**Evidence labels:** `strong` | `moderate` | `weak` | `untested`  
**Constraints:** closed candles only, no lookahead. ICT/FVG default `untested` until tick-measured.  
**No verbatim book text** in training JSON — paraphrase + `slug p.N` citations.

Convert to JSONL: stage 01 (seeds) → stage 02/03 (bar-grounded examples) → stage 04 (decisions).
