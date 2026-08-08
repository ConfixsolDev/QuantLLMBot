# Session-hierarchy architecture (agreed design)

Decision record from the 2026-08-08 architecture discussion. Implemented in
`apps/qwen_trade_software/backend/session_planner.py` and
`apps/qwen_trade_software/planview/`. Read with `v003_training_plan.md`.

Last updated: 2026-08-08 (implemented)

---

## Model decision

**One model, two roles.** No two-model consensus: Qwen and R1-distill share
the same base (Qwen 14B) — correlated errors mean agreement is not evidence,
and two 14B models do not fit 16 GB VRAM concurrently.

| Item | Decision |
|------|----------|
| Base | Qwen3-14B, Q4_K_M GGUF, Ollama, pinned/warm (~11–13 GB with 16k ctx) |
| Roles | Planner + Validator = same weights, different prompt, temp 0 for validator |
| Optional later | Stock DeepSeek-R1-Distill-Qwen-14B as *sequential* hourly critic (swap-in, never LoRA-trained) |
| Alternative to test | Qwen3-30B-A3B MoE (spills to shared RAM but few active params) |

## Training path

1. **Distill** books → `knowledge/topics/` → structured Q&A SFT (existing pipeline)
2. **QLoRA** (Unsloth, 4-bit base, rank 16–32, seq 4096) — fits 16 GB, or one cheap cloud run
3. **Second-stage LoRA from tick data** — after 30–60 days, reviewed
   situation→outcome pairs (this is where session verdicts pay off)
4. **Store stays lean** — what the LoRA internalizes gets *removed* from
   `core_skill.md` / `sop.md`

## Planning hierarchy

The market has a temporal hierarchy; the system thinks in the same one.
An hour is only meaningful inside its session, a session inside the day.

```
DAY PLAN          once, before Tokyo open
                  bias both directions, daily/H4 levels,
                  "what would make today bullish / bearish"
    │
SESSION PLAN      at each session open (Tokyo → London → Overlap → NY)
                  inherits day plan + verdicts of finished sessions
    │
HOURLY UPDATE     every hour, inside session context
                  input: day plan + session plan + hour-of-session number
                  output: small JSON delta — confirm / adjust confidence /
                  invalidate. Never a fresh analysis.
    │
SESSION VERDICT   at session close
                  what the session did vs. its plan → input to next session
```

### Rules (agreed, enforce in code)

- **Session boundaries are code, not model judgment.** Deterministic
  clock-based state machine in broker time triggers every call. The model
  never decides what session it is.
- **Every artifact carries ancestry**: `day_plan_id`, `session_plan_id`.
  The hourly prompt states literally: "Hour 2 of London. Tokyo verdict:
  ranged. Day plan: bullish above X."
- **Validator runs on day plan and session plans only** (temp 0,
  agree/disagree per scenario). Code aggregates: agree → tradeable,
  disagree → skip or half size.
- **Hourly updates can only narrow the plan, never widen it.** Entries are
  allowed only inside the currently valid session plan.
- **Hourly output stays terse** — confidence, level touched, invalidation
  status. The thinking lives in day/session plans; logs must stay trainable,
  not chatty.

### Why verdicts matter for training

Plan → verdict → next session's plan is a structured conversation the system
has with itself across the day, fully logged to `tick_data/`. After 60 days
it answers questions like: "when Tokyo ranged and London hour-1 broke the
Asia high, what did NY do?" — exactly the situation→outcome pairs stage-3
LoRA needs.

## New tick-data artifacts

| File (per day dir) | One line per |
|--------------------|--------------|
| `day-plans.jsonl` | Day plan + validator verdict |
| `session-plans.jsonl` | Session plan + validator verdict |
| `hourly-updates.jsonl` | Hourly delta |
| `session-verdicts.jsonl` | Session close review |

Existing entry/management loops (30s) keep their current logs; proposals gain
`day_plan_id` and `session_plan_id` when `QWEN_PLAN_GATING=1`.

## Runtime (implemented)

| Process | File | Port / lock |
|---------|------|-------------|
| Session planner | `session_planner.py` | singleton `:48634` |
| Plan API | `reviewer.py` | `GET /plan`, `/candles`, `/plan/history` on `:48632` |
| Plan View UI | `planview/` | dev `:3000`, IIS static `:8088` |
