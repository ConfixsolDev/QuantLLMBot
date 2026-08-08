# Daily Trade Review & Skill-Update Process

This is the repeatable loop for reviewing each day's live paper trading,
deciding what's actually a durable lesson, and feeding approved lessons
toward the next LoRA version. It lives in `model_training\` because that's
what it ultimately feeds — the trading knowledge corpus a future model gets
trained on — separate from `ResearchLab\`, which is the retired research
engine, and separate from `apps\`, which is the live code.

Two lanes, kept deliberately separate:

- **Trading-skill lessons** — patterns about market behavior, session
  timing, entry/exit judgment, things Qwen got right or wrong that say
  something about *how to trade*. These are the only things that belong in
  `TRADING_KNOWLEDGE_BASE.md` and, eventually, in a LoRA retrain.
- **Engineering findings** — bugs, source/deployment divergences, logic that
  doesn't behave as documented (like the ±5.0 safety-bracket divergence
  found on 2026-08-06). These matter, but they get fixed in code, not
  written into the model's trading doctrine. They belong in
  `ResearchLab\PROVEN_HARMFUL_CHANGES.md` or a plain engineering to-do, not
  here.

If a day's finding is "the code did something undocumented," that's
engineering. If it's "the market did X and the right read was Y," that's a
trading-skill lesson. Most days will produce more of the first than the
second, and that's fine — don't force a lesson that isn't really one.

## The daily loop

1. **Pull today's tick data.** From the permanent archive
   (`E:\QuantLLMBot\model_training\tick_data\YYYY-MM-DD\`):
   `paper-proposals.jsonl`, `paper-executions.jsonl`, `reviews.jsonl`,
   `qwen-decisions.jsonl`, and `qwen-io.jsonl` (full Qwen prompt/response).
   Or run `daily_trade_review.py` which reads this folder automatically.
   Hot runtime logs under `apps\qwen_trade_software\backend\logs\` are a
   fallback only — the archive is the source of truth.

2. **Reconstruct the trade narrative.** For every filled trade: entry
   rationale/confidence, fill price, close reason, net/gross P&L, peak P&L,
   max drawdown, holding time. (This is exactly the table style used in
   `TRADE_REVIEW_2026-08-06.md` — reuse that format daily rather than
   reinventing it.)

3. **Fill out `DAILY_REVIEW_TEMPLATE.md`** (copy it fresh each day, e.g. to
   `model_training\reviews\2026-08-07_review.md`) with the aggregate stats,
   the per-trade table, and a first-pass list of candidate lessons —
   trading-skill and engineering, kept in their separate sections.

4. **Human approval.** You read the candidate lessons and mark each one
   approved, rejected, or needs-more-days-of-evidence. Discussion alone is
   not enough — each approved lesson must cite ticket-data evidence (date
   folder, proposal id, price, outcome). One day's data is a small sample;
   a pattern that only showed up once is usually needs-more-evidence, not
   an approved lesson. This mirrors the preregistration/walk-forward
   discipline in `ResearchLab\RESEARCH_LOOP.md`.

5. **Promote approved lessons into the store (refine, don't inflate).** Each
   approved trading-skill lesson gets:
   - one line appended to `LESSON_LEDGER.md` (date, one-line summary, which
     section of the store it touches)
   - **edited into** `store/core_skill.md` or the relevant section of
     `store/sop.md` — replace or tighten existing wording; do not add a new
     paragraph every day without removing what it supersedes. Bump the version
     comment at the top of the file you changed.
   - merged into `TRADING_KNOWLEDGE_BASE.md` when preparing a retrain, as an
     edit or addition, not a wholesale rewrite of the section

6. **Check the retrain counter.** `LESSON_LEDGER.md` tracks how many
   approved lessons have accumulated since the last LoRA version. When that
   count reaches the threshold (default **20**, adjustable — see the top of
   the ledger), it's time for a retrain cycle, not before. This is
   deliberately *not* a fixed daily or weekly schedule — with roughly a
   dozen trades a day, a handful of genuinely durable lessons will take
   more than a few days to accumulate, and that's the point: training on
   too little, too often, mostly trains on noise.

## When the retrain threshold is hit

1. Freeze the current `TRADING_KNOWLEDGE_BASE.md` as the training corpus
   for the next version (e.g. copy it to
   `model_training\corpus_snapshots\v003_corpus.md`).
2. Train a **fresh** LoRA from the current production base checkpoint (not
   a continuation of the previous adapter — see the reasoning below) on
   that corpus.
3. Walk-forward evaluate the new adapter against the current production
   model on held-out days before promoting it, same gate structure as any
   other change in `IMPROVEMENT_GUIDE.md`.
4. On promotion: tag the corpus snapshot and the ledger entries that fed it
   with the version number, and reset the ledger's "since last retrain"
   counter to 0.
5. On rejection: the lessons stay in `TRADING_KNOWLEDGE_BASE.md` (they're
   still true, they just didn't earn a new model version yet) and the
   counter is *not* reset — the next attempt can include more evidence
   plus whatever's accumulated since.

## Why fresh-from-base, not incremental-on-the-adapter

Repeatedly continuing to fine-tune the same LoRA adapter on each new small
batch compounds drift — the model tends to overweight whatever's most
recent and can quietly forget earlier learned behavior, and it becomes hard
to say whether a later version is actually better or just differently
overfit. Training fresh from the base checkpoint on the full accumulated,
curated corpus each time keeps every version independently reproducible and
directly comparable, and avoids that compounding effect. It also means the
threshold-gating in step 6 above is doing real work: it's there specifically
so retraining only happens with enough accumulated signal to be worth it,
not on a fixed calendar.
