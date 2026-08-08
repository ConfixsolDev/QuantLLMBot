# How the three parts connect

See **`../../SYSTEM_THREE_PARTS.md`**.

| Part | What | Where |
|------|------|-------|
| **1 — Tick data** | Each price/decision observation | `../tick_data/YYYY-MM-DD/` |
| **2 — Skill** | Lean LLM template | `../../store/` |
| **3 — Code** | Stabilizing app | `../../apps/qwen_trade_software/` |

**Tick** = one timed record: bid/ask, context, Qwen in/out, decision — not MT5
order tickets.

## All store files (live + training reference)

See **`../TRAINING_INVENTORY.md`** for sizes, git status, and v003 roles.

| File | Role |
|------|------|
| `../../store/core_skill.md` | **Live doctrine** — market structure |
| `../../store/sop.md` | **Live doctrine** — JSON contracts, prompts |
| `../../store/principles_registry.json` | Candidate principles — promote into store |
| `../../store/knowledge_cards.json` | Distilled cards (empty until populated) |
| `../../store/review_queue.json` | Human review queue |
| `../../store/run_state.json` | Short-term paper/experiment state |
| `../../store/episodes.jsonl` | Episode archive (local, large) |
| `../../store/audit_log.jsonl` | Governance audit trail |
| `../TRADING_KNOWLEDGE_BASE.md` | Offline Colab bundle |

## Part 1 → Part 2

Review tick folders with evidence before editing `store/`.

## Training (v003)

- **`topics/KNOWLEDGE_MAP.md`** — **canonical index (start here)**
- **`topics/01_market.md` … `09_reversal_trading.md`** — **v2 topics (canonical)**
- **`topics/V2_CANONICAL_PLAN.md`** — MT5 grounding, doctrine promotion gate
- **`topics/_SHARED_BRIEF.md`** — distillation agent brief
- **`../sources/books/BOOK_REGISTRY.md`** — books per knowledge domain
- **`CANDLE_MOMENT_AND_SESSION_DISTILLATION.md`** — nested candle + session operator records
- **`book_notes/`** — per-book raw notes while reading

**Doctrine loop:** levels = *where* · nested candles = *how* · session (UTC) + H4(NY) = *when*

## After code matures

Only **tick data** keeps growing every session; store **improves** without
getting bigger; code changes rarely.
