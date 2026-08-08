# Training Inventory — v002 recovery & v003 plan

Master list of every training-related source in the repo. **All `store/` files
are listed below** — not only the two live doctrine files.

Last updated: 2026-08-07 (v001 package indexed)

---

## v001 training — confirmed in repo

**Location:** `model_training/qwen7b_complete_market_structure_v001/`

| File | Role |
|------|------|
| `train_qwen7b_qlora_colab.py` | **Training script** — QLoRA SFT on Colab |
| `requirements-colab.txt` | Training deps (torch, peft, bitsandbytes, transformers) |
| `complete_market_structure_v001/train.jsonl` | **SFT dataset** — 250 examples, ~16 MB |
| `complete_market_structure_v001/manifest.json` | Dataset metadata |

### v001 methodology (from script + manifest)

| Parameter | Value |
|-----------|-------|
| Base model | `Qwen/Qwen2.5-7B-Instruct` |
| Method | **QLoRA** — 4-bit NF4, double quant, paged AdamW 8-bit |
| LoRA r / alpha | **16 / 32** |
| LoRA targets | q,k,v,o, gate, up, down projections |
| LoRA dropout | 0.05 |
| Learning rate | **2e-4** |
| Epochs | **1.0** |
| Batch size / grad accum | **1 / 8** (effective batch 8) |
| Max sequence length | **4096** |
| Format | Chat messages → `apply_chat_template` → causal LM labels |

### v001 dataset (`complete_market_structure_v001`)

| Field | Value |
|-------|-------|
| Version | `complete_market_structure_v001` |
| Examples | **250** (sequential curriculum) |
| Date range | **2026-05-15 → 2026-07-15** |
| Source CSV | `D:\QuantLLMBot\RandDData\RnD_XAUUSDr_20260101.csv` |
| Lookahead policy | Closed candles only; decision examples keep source review status |
| Status | `unreviewed_complete_curriculum_training_asset` |

**Curriculum stages** (order matters — file is sorted):

| Stage | Count | Content |
|-------|-------|---------|
| `01_principle_foundation` | 10 | Compact principles (location-before-signal, no-lookahead, etc.) |
| `02_multi_h4_sequence` | 40 | Sequential H4 flow across days |
| `03_internal_h4_flow_level_volume` | 80 | H4 built from M15/M30/H1 levels + tick volume |
| `04_decision_contract_examples` | 120 | Full decision JSON from jul13 research runs |

**Stage 04 source runs** (120 examples, mostly `decision_quality_label: unreviewed`):

- `jul13_modular_full_v2` — 48
- `jul13_fixed_store_e2e_v1` — 28
- `jul13_first_response_v2` — 20
- `jul13_storeonly_full_v1` — 10
- `jul13_modular_full_v1` — 10
- Others — 1 each

**Books:** Principles cite *"Distilled from human doctrine and trading literature
principles; no copied book text"* — **no book titles named** in the dataset.

### v001 → v002 lineage (inferred)

| | v001 | v002 |
|--|------|------|
| Dataset folder | `complete_market_structure_v001` | Adapter name: `…_v002_complete_market_structure_L4` |
| Training script in repo | **Yes** | **Not in repo** (likely same script, new dataset) |
| Export script in repo | No | **Yes** |
| Production Ollama name | — | `qwen-trading-v002:latest` |

**Still needed from you:** v002 `train.jsonl` (if different from v001), v002
adapter weights, and whether v002 continued v001 adapter or retrained fresh.

---

## Store — all files (`store/`)

| File | Size (approx) | In git | Live Qwen reads? | v002 training role | v003 training role |
|------|---------------|--------|------------------|--------------------|--------------------|
| `core_skill.md` | 14 KB | Yes | **Yes** — prefix on every call | Primary doctrine SFT corpus | **Primary** — refine, then embed in corpus |
| `sop.md` | 39 KB | Yes | **Yes** — prompt contracts from here | JSON/output contract SFT corpus | **Primary** — refine, then embed in corpus |
| `README.md` | 2 KB | Yes | No | Store edit rules | Reference only |
| `principles_registry.json` | 5 KB | Yes* | No | Candidate principles from jul13 research runs | Review for promotion into `core_skill.md`; optional SFT examples |
| `knowledge_cards.json` | 37 B | Yes* | No | Empty (`cards: []`) | Unused until cards are populated |
| `review_queue.json` | 281 B | Yes* | No | Legacy migration queue | Reference only — not training input |
| `run_state.json` | 87 KB | Yes* | No | Short-term memory / paper run state (jul13–jul20) | Research reference; do not feed raw to SFT |
| `episodes.jsonl` | **75 MB** | Ignored | No | Full episode archive (wins/losses/skips) | Optional tick-derived SFT **after** human curation |
| `audit_log.jsonl` | 1.3 MB | Ignored | No | Promotion/rejection audit trail | Governance reference only |

\* Small JSON memory files are tracked in git. Large JSONL stays local-only.

## Folder map (v003 training layout)

```text
model_training/
├── TRAINING_INVENTORY.md          ← this file
├── qwen7b_complete_market_structure_v001/  ← v001 script + train.jsonl
├── TRADING_KNOWLEDGE_BASE.md      ← live training bundle
├── corpus_snapshots/
│   ├── v002_corpus_reconstructed.md
│   └── v003_corpus.md             ← create at retrain
├── sources/
│   ├── books/                     ← PDFs (local, gitignored)
│   ├── v002_recovery/             ← notebook, logs, recovered SFT
│   └── methodology/
│       ├── v002_training_record.md
│       └── v003_training_plan.md
├── datasets/                      ← generated SFT (gitignored)
├── scripts/
│   └── build_doctrine_sft.py
├── adapters/                      ← LoRA weights (gitignored)
└── tick_data/YYYY-MM-DD/          ← Part 1 evidence
```

### Principles in `principles_registry.json` (5 entries)

| ID | Status | Summary |
|----|--------|---------|
| `mp_002` | candidate | Avoid sell when rejection level too close to support |
| `mp_003` | calibrating | Skip midrange without fresh mapped level test |
| `prop_001` | challenged | First rejection starter |
| `prop_002` | calibrating | Pre-London skip (07–08 UTC) |
| `prop_003` | challenged | Rejection failure condition |

**Action for v003:** Distill approved principles into `core_skill.md` — do not
train directly on challenged/candidate status without human review.

---

## Other canonical training sources (outside store)

| Source | Path | In v002? | v003 role |
|--------|------|----------|-----------|
| Training bundle | `model_training/TRADING_KNOWLEDGE_BASE.md` | Yes (assembled post-hoc) | Freeze to `corpus_snapshots/v003_corpus.md` at retrain |
| Governance | `ResearchLab/PROVEN_HARMFUL_CHANGES.md` | Embedded in bundle | Keep embedded |
| Governance | `ResearchLab/SYSTEM_TEXTBOOK.md` | Embedded in bundle | Keep embedded |
| Governance | `ResearchLab/RESEARCH_LOOP.md` | Embedded in bundle | Keep embedded |
| Governance | `ResearchLab/IMPROVEMENT_GUIDE.md` | Embedded in bundle | Keep embedded |
| Governance | `ResearchLab/CACHE_CONTEXT_ARCHITECTURE.md` | Embedded in bundle | Keep embedded |
| Legacy skill export | GoldScalp88 `skills.md` | Embedded in bundle §3 only | Review; merge or drop for v003 |
| Lesson index | `model_training/LESSON_LEDGER.md` | N/A | Gate: 20 approved lessons before retrain |
| Daily reviews | `model_training/reviews/` | N/A | Evidence input for store edits |
| Tick archive | `model_training/tick_data/YYYY-MM-DD/` | N/A | Primary live evidence (Part 1) |
| Books | `Books/` (gitignored) | Unknown — not listed in repo | **You provide:** titles + PDFs |

---

## v002 training — what we know

| Item | Value | Documented? |
|------|-------|-------------|
| Production model | `qwen-trading-v002:latest` | Yes |
| Base model | `Qwen/Qwen2.5-7B-Instruct` | Yes |
| Method | PEFT LoRA → merge → GGUF Q4_K_M → Ollama | Yes (export only) |
| Adapter hint | `qwen_trading_lora_v002_complete_market_structure_L4` | Name only |
| Hardware | Colab L4+ | Export confirmed |
| Export script | `model_training/export_lora_to_ollama_colab.py` | Yes |
| SFT dataset | Unknown path/format | **Missing** |
| Training notebook | Unknown | **Missing** |
| Hyperparameters | Unknown (rank, LR, epochs) | **Missing** |
| Books used | Unknown | **Missing** |

### v002 store files used (reconstructed)

| Store file | Likely used in v002? | Evidence |
|------------|---------------------|----------|
| `core_skill.md` | **Yes** | Embedded in TRADING_KNOWLEDGE_BASE.md |
| `sop.md` | **Yes** | Embedded in TRADING_KNOWLEDGE_BASE.md |
| `principles_registry.json` | **Maybe** | Principles may have informed doctrine; not in bundle |
| `episodes.jsonl` | **Maybe** | Large replay archive exists; unclear if in SFT |
| `knowledge_cards.json` | **No** | Empty |
| `audit_log.jsonl` | **No** | Governance only |
| `run_state.json` | **No** | Runtime state |
| `review_queue.json` | **No** | Migration artifact |

---

## v003 training plan

### Phase A — Recover v002 (needs your input)

- [ ] Colab training notebook / script
- [ ] LoRA adapter folder (`qwen_trading_lora_v002_complete_market_structure_L4`)
- [ ] SFT JSONL used for v002
- [ ] Training logs (loss, epochs, hyperparameters)
- [ ] Book list + PDFs (if any)
- [ ] Confirm which store files were in the v002 SFT set

### Phase B — Evidence loop (ongoing)

- [ ] Daily review from `tick_data/YYYY-MM-DD/`
- [ ] Approve lessons → `LESSON_LEDGER.md`
- [ ] Edit `store/core_skill.md` / `store/sop.md` (refine, don't inflate)
- [ ] Promote vetted principles from `principles_registry.json` into store

### Phase C — Train v003 (at 20 lessons or explicit approval)

1. Freeze `corpus_snapshots/v003_corpus.md` from store + ResearchLab
2. Build SFT JSONL: doctrine + optional curated tick examples
3. Fresh LoRA on `Qwen2.5-7B-Instruct` (not continue v002 adapter)
4. Export → `qwen-trading-v003`
5. Walk-forward eval vs v002 on held-out tick days

---

## What to provide next

Paste or point to:

```
v002 artifacts:
- [ ] Colab notebook path
- [ ] Adapter folder path
- [ ] SFT JSONL path
- [ ] Training log

Books used for v002:
- [title 1, title 2, ...]

Store files that were in v002 training:
- [ ] core_skill.md + sop.md only
- [ ] principles_registry.json
- [ ] episodes.jsonl (curated subset)
- [ ] other: ___

Extra data for v003:
- [ ] tick days beyond 2026-08-07
- [ ] labeled good/bad entry examples
- [ ] MT5 backtest exports
```
