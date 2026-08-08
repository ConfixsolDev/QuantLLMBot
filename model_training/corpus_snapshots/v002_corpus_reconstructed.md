# v002 corpus snapshot (reconstructed)

**Frozen:** 2026-08-07  
**Status:** Reconstructed from repo — original SFT JSONL and training notebook
are **not** in git. Treat this as the best available record until you provide
v002 artifacts in `sources/v002_recovery/`.

## Canonical bundle

The full embedded corpus lives in:

`model_training/TRADING_KNOWLEDGE_BASE.md` (assembled 2026-08-06)

Do not duplicate that file here. This snapshot records **what went into it** and
**store versions at assembly time**.

## Store doctrine at v002 assembly

| File | Version | Role in corpus |
|------|---------|----------------|
| `store/core_skill.md` | **2.5** | §1 — primary market-structure doctrine |
| `store/sop.md` | **3.3** | §2 — JSON contracts and prompt sections |

## Other store files (present locally, unclear if in v002 SFT)

| File | In TRADING_KNOWLEDGE_BASE? | Notes |
|------|---------------------------|-------|
| `principles_registry.json` | No | 5 candidate principles — may have informed edits |
| `knowledge_cards.json` | No | Empty |
| `episodes.jsonl` | No | 75 MB replay archive — SFT use unconfirmed |
| `audit_log.jsonl` | No | Governance only |
| `run_state.json` | No | Jul paper-run state |
| `review_queue.json` | No | Migration artifact |

## Embedded non-store sections (TRADING_KNOWLEDGE_BASE.md)

| Section | Source |
|---------|--------|
| §3 Trade management heuristics | Legacy GoldScalp88 `skills.md` |
| §4 Proven harmful changes | `ResearchLab/PROVEN_HARMFUL_CHANGES.md` |
| §5 System architecture | `ResearchLab/SYSTEM_TEXTBOOK.md` |
| §6 Research process | `ResearchLab/RESEARCH_LOOP.md`, `IMPROVEMENT_GUIDE.md` |
| §7 Cache architecture | `ResearchLab/CACHE_CONTEXT_ARCHITECTURE.md` |

## Production model metadata (documented)

| Field | Value |
|-------|-------|
| Ollama name | `qwen-trading-v002:latest` |
| Base | `Qwen/Qwen2.5-7B-Instruct` |
| Method | PEFT LoRA → merge → GGUF Q4_K_M |
| Adapter hint | `qwen_trading_lora_v002_complete_market_structure_L4` |
| Export | `export_lora_to_ollama_colab.py` |
| Colab work dir | `/content/drive/MyDrive/QuantLLMBot/ollama_export/qwen_trading_v002` |

## Missing (fill in from your Colab Drive)

- [ ] Training notebook path
- [ ] SFT JSONL path and line count
- [ ] Hyperparameters (rank, alpha, LR, epochs, batch size)
- [ ] Train/val split
- [ ] Books/PDFs list
- [ ] Whether `episodes.jsonl` was curated into SFT

Update `sources/methodology/v002_training_record.md` when artifacts arrive.
