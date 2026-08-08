# QuantLLMBot — Folder Guide

See **`SYSTEM_THREE_PARTS.md`**.

| Part | Folder | Role |
|------|--------|------|
| **1 — Tick data** | `model_training/tick_data/YYYY-MM-DD/` | Each tick: price + decision + Qwen I/O — grows forever |
| **2 — Skill** | `store/` | Lean LLM template — improves, does not balloon |
| **3 — Code** | `apps/qwen_trade_software/` | Live app — stabilizing |

| File | Detail |
|------|--------|
| `store/README.md` | Store edit rules (refine, don't grow) |
| `model_training/tick_data/README.md` | What a tick is in this system |
| `model_training/DAILY_REVIEW_PROCESS.md` | Evidence-based daily review |

**Permanent (back up):** `model_training/tick_data/`
