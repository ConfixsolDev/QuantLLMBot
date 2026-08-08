# v002 training record

Fill this in as you recover artifacts from Colab Drive or local backups.
Everything marked **confirmed** is documented in the repo today.

Last updated: 2026-08-07

---

## Model identity

| Field | Value | Status |
|-------|-------|--------|
| Production name | `qwen-trading-v002:latest` | confirmed |
| Base model | `Qwen/Qwen2.5-7B-Instruct` | confirmed |
| Quantization | Q4_K_M (Ollama) | confirmed |
| Adapter folder | `qwen_trading_lora_v002_complete_market_structure_L4` | name only |
| Training date | _unknown_ | **missing** |
| Trained by | _unknown_ | **missing** |

## Hardware & environment

| Field | Value | Status |
|-------|-------|--------|
| Platform | Google Colab | confirmed (export) |
| GPU | L4 or better | confirmed (export readme) |
| Python packages | see `requirements-export-colab.txt` | export only |

## Training methodology

**v001 baseline recovered** — see
`model_training/qwen7b_complete_market_structure_v001/train_qwen7b_qlora_colab.py`.
v002 likely reused the same QLoRA recipe unless you changed hyperparameters.

| Field | Value | Status |
|-------|-------|--------|
| Method | PEFT QLoRA SFT (4-bit) | confirmed (v001 script) |
| Training script | `qwen7b_complete_market_structure_v001/train_qwen7b_qlora_colab.py` | v001 confirmed |
| Continue from v001 adapter? | _unknown_ | **missing** |
| Fresh from base? | _unknown_ | **missing** |
| LoRA rank (r) | **16** (v001 default) | likely same |
| LoRA alpha | **32** (v001 default) | likely same |
| Learning rate | **2e-4** (v001 default) | likely same |
| Epochs | **1.0** (v001 default) | likely same |
| Batch size / grad accum | **1 / 8** (v001 default) | likely same |
| Max sequence length | **4096** (v001 default) | likely same |
| Train/val split | _unknown_ | **missing** |
| Final train loss | _unknown_ | **missing** |
| Eval metric | _unknown_ | **missing** |

## Training data

### Store files (all files on disk — mark which were in SFT)

| File | In SFT? | Notes |
|------|---------|-------|
| `store/core_skill.md` v2.5 | **likely yes** | Embedded in TRADING_KNOWLEDGE_BASE |
| `store/sop.md` v3.3 | **likely yes** | Embedded in TRADING_KNOWLEDGE_BASE |
| `store/principles_registry.json` | _unknown_ | 5 principles — not in bundle |
| `store/knowledge_cards.json` | no | empty |
| `store/episodes.jsonl` | _unknown_ | 75 MB — confirm if curated subset used |
| `store/audit_log.jsonl` | no | governance |
| `store/run_state.json` | no | runtime state |

### Other corpus sources

| Source | In SFT? | Status |
|--------|---------|--------|
| `TRADING_KNOWLEDGE_BASE.md` (assembled bundle) | **likely yes** | confirmed post-hoc |
| Legacy GoldScalp88 `skills.md` | **likely yes** | embedded as §3 |
| `ResearchLab/*.md` governance docs | **likely yes** | embedded in bundle |
| Tick / Qwen IO examples | _unknown_ | **missing** |
| External books (`Books/`) | _unknown_ | **missing** — list titles below |

### Books / external PDFs

```
(title, author, how used: distilled / raw chunks / not used)
-
-
```

### SFT dataset file

**v001 dataset (confirmed):**

| Field | Value |
|-------|-------|
| Path | `model_training/qwen7b_complete_market_structure_v001/complete_market_structure_v001/train.jsonl` |
| Format | JSONL — `messages[]` chat + metadata (`curriculum_stage`, etc.) |
| Line count | **250** |
| Created by | Curriculum builder from `RandDData/RnD_XAUUSDr_20260101.csv` + jul13 runs |

**v002 dataset (still needed):**

| Field | Value |
|-------|-------|
| Path | _paste path — e.g. `complete_market_structure_v002/train.jsonl`_ |
| Line count | _ |
| Diff from v001 | _more examples? reviewed stage 04? store updates?_ |

---

## Export & deployment (confirmed)

| Step | Tool | Notes |
|------|------|-------|
| Merge LoRA | `export_lora_to_ollama_colab.py` | `--adapter-dir` required |
| GGUF convert | llama.cpp in Colab | Q4_K_M default |
| Ollama register | `ollama create qwen-trading-v002 -f Modelfile` | see OLLAMA_EXPORT_README |
| Distribution | [Google Drive zip](https://drive.google.com/file/d/1pShA0JKZdBdXUOVkhXdFzgwADt5rutrm/view) | |

---

## Artifact drop zone

Copy recovered files to `model_training/sources/v002_recovery/` and note
paths here:

| Artifact | Path | Received |
|----------|------|----------|
| Training notebook | | [ ] |
| LoRA adapter | | [ ] |
| SFT JSONL | | [ ] |
| Training log | | [ ] |
| Loss curve screenshot | | [ ] |
