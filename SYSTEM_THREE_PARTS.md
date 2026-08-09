# QuantLLMBot — Three-Part System

The live system has three parts. Only **one** keeps growing forever after the
code matures: **tick data** (each price/decision observation). Skill grows
separately, on **evidence**, not conversation alone.

```
┌─────────────────────────────────────────────────────────────────┐
│  PART 1 — TICK DATA (permanent, grows every trading day)        │
│  model_training/tick_data/YYYY-MM-DD/                           │
│  each line = one tick: price + context + Qwen in/out + decision │
└───────────────────────────────┬─────────────────────────────────┘
                                │ evidence input
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  PART 2 — SKILL (grows slowly, evidence-gated)                  │
│  store/core_skill.md · store/sop.md  (lean LLM template)        │
│  daily review → store edits · see CURRICULUM_AND_DATA_PREP.md   │
└───────────────────────────────┬─────────────────────────────────┘
                                │ read at runtime
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  PART 3 — CODE (maturing → stable in weeks)                     │
│  apps/qwen_trade_software/                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 1 — Tick data (learning fuel)

**What is a tick here?** Each timed observation the system records: bid/ask
price, structure context, Qwen prompt/response, and the decision at that
moment. One JSON line = one tick of the process.

**Not** MT5 order tickets (broker position IDs) — those are fields inside
records when relevant (`mt5_position_id`).

**Location:** `model_training/tick_data/YYYY-MM-DD/`

| File | What each line (tick) holds |
|------|----------------------------|
| `qwen-decisions.jsonl` | Price + full decision tree |
| `qwen-io.jsonl` | Full Qwen request/response |
| `paper-proposals.jsonl` | Entry tick + market snapshot |
| `paper-executions.jsonl` | Fill/close ticks |
| `reviews.jsonl` | Management cycle ticks |
| `mt5-io.jsonl` | MT5 API calls at that time |
| `day-plans.jsonl` | Day plan + validator verdict |
| `session-plans.jsonl` | Session plan + validator verdict |
| `hourly-updates.jsonl` | Hourly plan delta |
| `session-verdicts.jsonl` | Session close review |

**Policy:** Never auto-deleted. Compare decisions at different prices over
30, 60, 90+ days. Back up externally.

---

## Part 2 — Skill (store = lean LLM template)

**Purpose:** Turn tick data into **durable trading judgment** — evidence from
logged prices and decisions, not chat alone.

**The store** (`core_skill.md`, `sop.md`) is the **LLM template prefix**. It
**matures** (clearer rules) but must **not grow without bound** — refine in
place. See `store/README.md`.

**Where growth goes instead of the store:**

| Location | Holds |
|----------|--------|
| `model_training/tick_data/` | All ticks (grows forever) |
| `model_training/knowledge/stage_*.jsonl` | Curated SFT curriculum |
| `model_training/CURRICULUM_AND_DATA_PREP.md` | Sole process doc for train/data |

Do not recreate LESSON_LEDGER / TRADING_KNOWLEDGE_BASE / review markdown trees.

---

## Part 3 — Code (maturing, then stable)

Plumbing only. After a few weeks, change rarely. Log tick data; put doctrine
in the store.

---

## Long-term growth

| Part | Keeps growing? |
|------|----------------|
| **Tick data** | **Yes — forever** (each session adds ticks) |
| **Store** | **Improves, stays lean** |
| **Code** | **No — stabilizes** |

After code matures, **tick data** is what keeps growing to improve the system
over time.
