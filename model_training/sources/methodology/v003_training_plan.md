# v003 training plan

Concrete checklist for the next LoRA version. Read with
`TRAINING_INVENTORY.md` and `DAILY_REVIEW_PROCESS.md`.

Last updated: 2026-08-07

---

## Goals

1. **Organize** — complete v002 record; no training until inventory is honest
2. **Evidence loop** — daily tick review → approved lessons → store edits
3. **Retrain** — fresh LoRA from base when gate hits or you explicitly approve

## Current readiness

| Item | Status |
|------|--------|
| Approved lessons toward retrain | **0 / 20** (`LESSON_LEDGER.md`) |
| Tick archive days | **1** (`2026-08-07`) |
| Store doctrine versions | `core_skill.md` 2.5, `sop.md` 3.3 |
| v002 training notebook | **missing** |
| SFT builder script | `scripts/build_doctrine_sft.py` |
| Export script | `export_lora_to_ollama_colab.py` (reuse for v003) |

### Tick evidence available (2026-08-07)

| File | Lines | Notes |
|------|-------|-------|
| `paper-proposals.jsonl` | 202 | Entry decisions + snapshots |
| `paper-executions.jsonl` | 2719 | 15 starts, 8 closed, 6 skipped |
| `qwen-decisions.jsonl` | 255 | Decision tree |
| `qwen-io.jsonl` | 622 | Full Qwen prompt/response |
| `reviews.jsonl` | 53 | Management cycles |

---

## Phase A — Recover v002 (before v003 design is final)

**Owner:** you provide files → agent updates `v002_training_record.md`

- [ ] Colab training notebook → `sources/v002_recovery/`
- [ ] Adapter weights → `adapters/` (gitignored)
- [ ] SFT JSONL → `datasets/doctrine_sft/v002_recovered.jsonl`
- [ ] Training log + hyperparameters recorded
- [ ] Book list filled in v002 record
- [ ] Confirm which **store** files were in v002 SFT (all 9 listed in inventory)

**Exit criteria:** `v002_training_record.md` has no blank **missing** fields you
can fill, or explicit "lost" markers.

---

## Phase B — Evidence loop (ongoing, start now)

Daily (or after each session):

1. Run `daily_trade_review.py` on `tick_data/YYYY-MM-DD/`
2. Copy `DAILY_REVIEW_TEMPLATE.md` → `reviews/YYYY-MM-DD_review.md`
3. Human-approve trading-skill lessons only (not engineering bugs)
4. Promote approved lessons:
   - one line in `LESSON_LEDGER.md`
   - refine `store/core_skill.md` or `store/sop.md` (bump version comment)
5. Review `principles_registry.json` — promote vetted rules into store; do
   **not** train on challenged/candidate status raw

**Exit criteria:** 20 approved lessons **or** you explicitly waive the gate.

---

## Phase C — Build v003 corpus & dataset

When Phase B gate is met:

1. **Freeze corpus**
   ```text
   copy TRADING_KNOWLEDGE_BASE.md → corpus_snapshots/v003_corpus.md
   ```
   Record store versions in the snapshot header.

2. **Build doctrine SFT JSONL**
   ```powershell
   cd E:\QuantLLMBot\model_training
   python scripts/build_doctrine_sft.py --out datasets/doctrine_sft/v003_doctrine.jsonl
   ```
   Optional: add curated tick pairs later (`datasets/tick_derived_sft/`).

3. **Review principles** — only `active`/`promoted` rules distilled into store;
   never raw registry JSON in SFT.

---

## Phase D — Train & export

| Step | Action |
|------|--------|
| 1 | Colab L4+: fresh LoRA on `Qwen2.5-7B-Instruct` (**not** continue v002) |
| 2 | Train on `v003_doctrine.jsonl` (+ optional tick SFT if curated) |
| 3 | Walk-forward eval vs v002 on held-out tick days |
| 4 | Export: `export_lora_to_ollama_colab.py --outfile-prefix qwen-trading-v003` |
| 5 | Local test: `ollama create qwen-trading-v003 -f Modelfile` |
| 6 | Promote or reject; update `LESSON_LEDGER.md` version tag |

### Default hyperparameters (placeholder — replace with v002 recovered values)

| Param | Placeholder | Source |
|-------|-------------|--------|
| LoRA r | 16 | **replace from v002 log** |
| LoRA alpha | 32 | **replace from v002 log** |
| LR | 2e-4 | **replace from v002 log** |
| Epochs | 3 | **replace from v002 log** |
| Batch size | 4 | **replace from v002 log** |
| Max seq len | 4096 | matches Ollama `num_ctx` |

---

## Phase E — Promotion gate

Before replacing `qwen-trading-v002:latest`:

- [ ] Walk-forward on ≥2 held-out tick days not in training set
- [ ] JSON contract compliance ≥ v002 on sample prompts
- [ ] No regression on session-skip / off-session behavior
- [ ] Human sign-off on 10 spot-checked decisions

On **promotion:** tag ledger + corpus with `v003`; reset counter to 0.  
On **rejection:** lessons stay in store; counter **not** reset.

---

## What to send next

Paste paths or files for Phase A:

```
v002 notebook: 
v002 adapter folder: 
v002 SFT JSONL: 
v002 training log: 
books used: 
store files in v002 SFT: [ ] all doctrine md  [ ] principles  [ ] episodes subset
```
