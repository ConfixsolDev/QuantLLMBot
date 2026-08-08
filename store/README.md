# Store — LLM template (lean, improving)

The live Qwen backend loads **`core_skill.md`** + **`sop.md`** as the stable
prefix on every decision. These two files are the **template**, not a growing
archive.

## Rules

1. **Exactly two live doctrine files** — `core_skill.md` + `sop.md` only; no
   third markdown or prompt file. JSON/JSONL memory files may exist locally but
   are not loaded at runtime.
2. **Improve, do not inflate** — maturity means clearer and tighter doctrine,
   not more lines every week. Replace weak rules; merge duplicates; delete
   what repeated evidence disproved.
3. **Evidence before edit** — promote from ticket data + daily review only
   (see `../model_training/DAILY_REVIEW_PROCESS.md`). Verbal discussion alone
   does not change the store.
4. **Bump the version** in the HTML comment at the top when you edit; one-line
   changelog there — history lives in git, not in repeated paragraphs inside
   the file.
5. **Size budget** — aim to keep each file roughly stable over time (order of
   hundreds of lines, not thousands). If a lesson needs long narrative, put the
   working notes in `../model_training/reviews/` or `LESSON_LEDGER.md`; distill
   the rule into one precise paragraph in the store.

## Where growth is allowed

| Need | Put it here | Not in store |
|------|-------------|--------------|
| Raw daily ticks | `model_training/tick_data/` | — |
| Candidate lessons | `model_training/reviews/`, `LESSON_LEDGER.md` | — |
| Training export bundle | `model_training/TRADING_KNOWLEDGE_BASE.md` | — |
| Canonical live doctrine | **`core_skill.md`** | append-only logs |
| Live model contracts | **`sop.md`** | duplicate examples |

## Edit pattern (refine)

When a lesson is approved:

1. Find the section it belongs to (or add one **short** section if truly new).
2. **Remove or rewrite** the old wording it supersedes — do not leave both.
3. State the rule in operational terms Qwen can apply from closed data.
4. Increment version in the file header comment.

Wrong: append a new bullet every day → file doubles in a month.  
Right: one sharper rule replaces three vague ones → file stays lean, skill improves.

## All files in this folder

| File | Category | Role |
|------|----------|------|
| `core_skill.md` | **Live doctrine** | Market-structure rules — loaded on every Qwen call |
| `sop.md` | **Live doctrine** | JSON contracts, entry/management/cache prompt sections |
| `README.md` | Docs | Edit rules for this folder |
| `principles_registry.json` | Memory (local) | Candidate principles awaiting evidence-gated promotion |
| `knowledge_cards.json` | Memory (local) | Distilled cards (currently empty) |
| `review_queue.json` | Memory (local) | Human review queue for doctrine changes |
| `run_state.json` | Memory (local) | Short-term experiment / paper run state |
| `episodes.jsonl` | Ledger (local, large) | Win/loss/skip episode archive — not loaded at runtime |
| `audit_log.jsonl` | Ledger (local) | Promotion/rejection audit trail |

**Live app loads only** `core_skill.md` + `sop.md`. JSON/JSONL files are local
memory and training reference — see `model_training/TRAINING_INVENTORY.md`.

After store edits, refresh `model_training/TRADING_KNOWLEDGE_BASE.md` before a
LoRA retrain so the offline bundle matches live doctrine.
