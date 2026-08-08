# QuantLLMBot System Introduction

## Three-part system

Read **`SYSTEM_THREE_PARTS.md`**:

1. **Tick data** — each price/decision observation, permanent daily archive
   (`model_training/tick_data/`) — **grows forever**
2. **Skill** — evidence-gated; **`store/`** is the lean LLM template (improves, not inflates)
3. **Code** — maturing app (`apps/qwen_trade_software/`) — stabilizes in weeks

## Start here

- **Architecture:** `SYSTEM_THREE_PARTS.md`
- **Tick archive (Part 1):** `model_training/tick_data/README.md`
- **Store rules (Part 2):** `store/README.md`
- **Live app (Part 3):** `apps/qwen_trade_software/backend/`
- **Daily review:** `model_training/DAILY_REVIEW_PROCESS.md`
- **Training inventory (all store files):** `model_training/TRAINING_INVENTORY.md`
- **v003 plan:** `model_training/sources/methodology/v003_training_plan.md`

## Store = LLM template (Part 2)

`store/core_skill.md` + `store/sop.md` — loaded on every Qwen call. **Improve,
don't inflate.** Tick data holds raw history; store holds distilled doctrine.

## Safety

- Never commit large tick JSONL (see `.gitignore`).
- Cache must reach `ready` before paper execution.
