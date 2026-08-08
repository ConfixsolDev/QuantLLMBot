# QuantLLMBot Phase 4: Complete Training Pipeline

## Overview

This is the complete Phase 4 curriculum implementation for QuantLLMBot. The pipeline trains a Qwen2.5-7B-Instruct model using QLoRA fine-tuning to predict trading decisions based on quantitative principles, detector outputs, and market structure analysis.

**Curriculum Flow:**
- **Stage 01**: Foundational principles (35 examples) → System prompt context
- **Stage 02**: Structured examples (125 examples, Bucket A/B/C) → Training/test data
- **Stage 03**: Detector definitions (125 examples) → Intermediate representations
- **Stage 04**: Decision contracts (125 examples) → Training targets

---

## Quick Start (3 commands)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run full pipeline
python scripts/00_quickstart.py all

# 3. View results
cat model_training/outputs/evaluation_results.json
```

**Or run stages individually:**
```bash
python scripts/01_preprocess.py      # Create instruction-response pairs
python scripts/02_finetune.py        # QLoRA fine-tuning
python scripts/03_evaluate.py        # Evaluate on holdout test set
```

---

## Directory Structure

```
E:\QuantLLMBot\
├── requirements.txt                           # Python dependencies
├── README_PHASE4.md                          # This file
│
├── model_training/
│   ├── knowledge/
│   │   ├── stage_01_principle_foundation.jsonl    # 35 principles
│   │   ├── stage_02_structured_data.jsonl         # 125 examples
│   │   ├── stage_03_detector_definitions.jsonl    # 125 detector configs
│   │   └── stage_04_decision_contract.jsonl       # 125 decision targets
│   │
│   ├── outputs/
│   │   ├── processed_training_data.jsonl          # Output from preprocessing
│   │   ├── lora_weights/
│   │   │   ├── adapter_config.json
│   │   │   ├── adapter_model.bin
│   │   │   └── special_tokens_map.json
│   │   └── evaluation_results.json                # Final metrics
│   │
│   ├── checkpoints/
│   │   ├── checkpoint-50/
│   │   ├── checkpoint-100/
│   │   └── ...
│   │
│   └── logs/
│       ├── training.log
│       ├── quickstart.log
│       └── ...
│
└── scripts/
    ├── 00_quickstart.py          # Entry point (orchestrates all stages)
    ├── 01_preprocess.py          # Load stages 01/02/04, create training pairs
    ├── 02_finetune.py            # QLoRA fine-tuning
    ├── 03_evaluate.py            # Evaluation on test set
    ├── config.py                 # Centralized configuration
    └── utils.py                  # Utility functions
```

---

## Detailed Stage Descriptions

### Stage 01: Principle Foundation

**Input:** `stage_01_principle_foundation.jsonl`
- 35 foundational trading/market principles
- Fields: `principle_id`, `topic`, `principle_name`, `core_concept`, `foundational_rule`, `why_matters`, `evidence_strength`, `applies_to_detectors`

**Purpose:** System prompt context. Provides domain knowledge to guide the model's decision-making framework.

**Example:**
```json
{
  "principle_id": "001",
  "principle_name": "Mean Reversion in Bounded Markets",
  "core_concept": "Prices oscillate around equilibrium",
  "foundational_rule": "Extreme deviations from moving average predict reversals",
  "why_matters": "Guides overbought/oversold detector thresholds"
}
```

---

### Stage 02: Structured Data (Worked Examples)

**Input:** `stage_02_structured_data.jsonl`
- 125 complete worked examples with outcomes
- **Bucket A:** 54 examples (training)
- **Bucket B:** 61 examples (training)
- **Bucket C:** 10 examples (holdout test set)

Fields: `example_id`, `topic`, `title`, `setup`, `decision`, `invalidation`, `why`, `evidence`, `bucket`

**Purpose:** Training data (Bucket A/B) and evaluation (Bucket C).

**Important:** Only use lines 1-115 (Bucket A/B) for training. Lines 116-125 (Bucket C) are holdout doctrine rules—skip them during training.

**Example:**
```json
{
  "example_id": "001",
  "topic": "Mean Reversion",
  "title": "XYZ oversold on daily RSI",
  "setup": "XYZ close 15% below 50-day MA, RSI(14)=25",
  "decision": "BUY",
  "invalidation": "Close below recent swing low",
  "why": "Extreme deviation predicts mean reversion",
  "evidence": "Strong",
  "bucket": "A"
}
```

---

### Stage 03: Detector Definitions

**Input:** `stage_03_detector_definitions.jsonl`
- 125 detector specifications aligned with Stage 02 examples
- Fields: `example_id`, `detector_type`, `detector_name`, `input_signals`, `logic`, `thresholds`, `output`

**Purpose:** Intermediate representation showing what detector signals would activate for each example.

**Example:**
```json
{
  "example_id": "001",
  "detector_type": "momentum",
  "detector_name": "RSI_Oversold",
  "input_signals": ["RSI(14)", "price_distance_from_MA"],
  "logic": "IF RSI < 30 AND price_distance_from_MA < -15%",
  "thresholds": {"rsi_min": 30, "ma_distance_pct": -15},
  "output": "OVERSOLD_SIGNAL"
}
```

---

### Stage 04: Decision Contract

**Input:** `stage_04_decision_contract.jsonl`
- 125 decision specifications aligned with Stage 02 examples
- Fields: `example_id`, `detector_output`, `trade_decision`, `decision_conditions`, `evidence_label`, `conviction_score`, `risk_control`

**Purpose:** Training target. Maps detector outputs → trade decisions with confidence scores.

**Example:**
```json
{
  "example_id": "001",
  "detector_output": "OVERSOLD_SIGNAL",
  "trade_decision": "BUY",
  "decision_conditions": "Conviction: mean reversion probability >70%, macro environment stable",
  "evidence_label": "Strong Mean Reversion Evidence",
  "conviction_score": 0.75,
  "risk_control": "Stop loss at recent swing low, position size 2%"
}
```

---

## Scripts Overview

### 00_quickstart.py
Orchestrator. Checks environment, verifies data files, and runs the full pipeline.

```bash
python scripts/00_quickstart.py all         # Run all stages
python scripts/00_quickstart.py preprocess  # Just preprocessing
python scripts/00_quickstart.py finetune    # Just fine-tuning
python scripts/00_quickstart.py evaluate    # Just evaluation
```

---

### 01_preprocess.py
**Input:** Stages 01, 02 (lines 1-115), 04 (lines 1-115)
**Output:** `processed_training_data.jsonl` (115 instruction-response pairs)

**What it does:**
1. Loads all stages from JSONL files
2. Validates alignment (stage 02 ↔ stage 04)
3. Creates instruction-response pairs:
   - **Instruction:** Setup context + principles + question
   - **Response:** Trade decision + evidence + conviction score
4. Saves to `processed_training_data.jsonl`

**Command:**
```bash
python scripts/01_preprocess.py
```

**Expected output:**
```
[STEP 1] Verifying data files...
[STEP 2] Loading data stages...
[STEP 3] Validating data integrity...
  ✓ Aligned 125 records
[STEP 4] Creating instruction-response pairs...
  Created 115 instruction-response pairs
[STEP 5] Saving processed data...
  Saved 115 records to processed_training_data.jsonl
```

---

### 02_finetune.py
**Input:** `processed_training_data.jsonl` (115 pairs)
**Output:** `lora_weights/adapter_model.bin`, `lora_weights/adapter_config.json`

**What it does:**
1. Loads Qwen2.5-7B-Instruct with 4-bit quantization
2. Applies QLoRA (LoRA rank=16, alpha=32)
3. Fine-tunes on 115 instruction-response pairs
4. Saves LoRA weights to `lora_weights/`

**Model Config:**
- Base: Qwen/Qwen2.5-7B-Instruct
- Quantization: 4-bit NF4 (reduces memory from ~16GB → ~8GB)
- LoRA: r=16, alpha=32, dropout=0.05
- Training: 3 epochs, batch_size=2, gradient_accumulation=4, lr=2e-4

**Hardware Requirements:**
- GPU VRAM: ≥8GB (RTX 3070, RTX 4070, A100, H100, etc.)
- CPU RAM: ≥16GB
- Disk: ≥50GB (model + checkpoints)

**Command:**
```bash
python scripts/02_finetune.py
```

**Expected output:**
```
[STEP 1] Setting up model and LoRA...
  ✓ Model loaded: qwen2
  ✓ LoRA applied. Trainable params: 4,194,304
[STEP 2] Loading training data...
  ✓ Loaded 115 training examples
[STEP 5] Starting training...
  Epoch 1/3: 100%|███████| 115/115 [XX:XXs, X.XXs/it]
  ...
[STEP 6] Saving LoRA weights...
  ✓ LoRA weights saved to: lora_weights
```

**Duration:** ~30-60 minutes on modern GPU (A100, H100)

---

### 03_evaluate.py
**Input:** 
- Base model + LoRA weights
- Test set: Stage 02 lines 116-125, Stage 04 lines 116-125

**Output:** `evaluation_results.json` (metrics + predictions)

**What it does:**
1. Loads base model with merged LoRA weights
2. Evaluates on 10 holdout test examples (Bucket C)
3. Computes metrics:
   - **Exact Match Decision:** % of decisions matching reference
   - **Decision Agreement:** % of decisions matching reference
   - **Conviction Score MAE/RMSE:** Prediction vs. reference scores
   - **Evidence Label Accuracy:** Placeholder for NLP evaluation
4. Saves results to `evaluation_results.json`

**Command:**
```bash
python scripts/03_evaluate.py
```

**Expected output:**
```
[STEP 4] Running evaluation...
  Evaluating on 10 test examples...
  100%|███████| 10/10 [XX:XXs, X.XXs/it]

[STEP 6] EVALUATION RESULTS
  Exact Match Decision: 65.00% (6/10)
  Decision Agreement: 80.00%
  Conviction Score MAE: 0.0832
  Conviction Score RMSE: 0.1205
  Evidence Label Accuracy: 0.00%
```

---

## Configuration

All settings are centralized in `config.py`. Key parameters:

```python
# Model
base_model = "Qwen/Qwen2.5-7B-Instruct"
quantization = "4bit_nf4"

# LoRA
lora_r = 16
lora_alpha = 32
lora_dropout = 0.05

# Training
per_device_batch_size = 2
gradient_accumulation_steps = 4
learning_rate = 2e-4
num_epochs = 3
warmup_steps = 100

# Data
training_lines_start = 0    # Lines 1-115 (Bucket A/B)
training_lines_end = 115
test_lines_start = 115      # Lines 116-125 (Bucket C)
test_lines_end = 125
```

To override:
```python
# In config.py
training_config.num_epochs = 5
training_config.learning_rate = 1e-4
```

---

## Utilities (utils.py)

Helper functions available:

```python
load_jsonl(filepath, start_line=0, end_line=None)
save_jsonl(data, filepath)
format_principle_context(principles)
create_instruction_response_pair(example, principle_context, contract)
prepare_training_data(stage_02_data, stage_01_data, stage_04_data, start_idx, end_idx)
compute_exact_match(predicted, reference)
compute_conviction_mae/rmse(predicted, reference)
compute_decision_agreement(predicted, reference)
extract_decision(response_text)
extract_conviction_score(response_text)
setup_logging(log_dir, log_name)
```

---

## Expected Results

**After Preprocessing:**
- `processed_training_data.jsonl`: 115 instruction-response pairs
- File size: ~2-3 MB
- Format: JSONL (one JSON object per line)

**After Fine-Tuning:**
- `lora_weights/adapter_model.bin`: ~50-100 MB
- `lora_weights/adapter_config.json`: ~1 KB
- Total training time: 30-60 min (A100/H100)
- Training loss trajectory: ~2.5 → ~1.8 (3 epochs)

**After Evaluation:**
- `evaluation_results.json`: Full results with metrics
- **Expected metrics (baseline):**
  - Exact Match Decision: 65-75%
  - Decision Agreement: 80-85%
  - Conviction Score MAE: 0.05-0.10
  - Conviction Score RMSE: 0.08-0.15

---

## Inference / Deployment

### Use the fine-tuned model:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    torch_dtype="bfloat16",
    device_map="auto"
)

# Load LoRA weights
model = PeftModel.from_pretrained(model, "model_training/outputs/lora_weights")

# Merge for deployment (optional)
model = model.merge_and_unload()

# Inference
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
inputs = tokenizer("Your trading setup...", return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(outputs[0]))
```

---

## Troubleshooting

### Out of Memory (VRAM)
```python
# In config.py, reduce:
training_config.per_device_train_batch_size = 1  # Was 2
# Or increase gradient accumulation:
training_config.gradient_accumulation_steps = 8  # Was 4
```

### Missing data files
Ensure Stage 01/02/04 JSONL files exist:
```bash
ls -lah E:\QuantLLMBot\model_training\knowledge\stage_*.jsonl
```

### CUDA errors
```bash
# Test GPU availability
python -c "import torch; print(torch.cuda.is_available())"

# If False, install CUDA-compatible PyTorch:
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### Training stalls
Check logs: `cat model_training/logs/training.log`

---

## Next Steps

1. **Review Results:** Check `model_training/outputs/evaluation_results.json`
2. **Iterate:** Adjust hyperparameters in `config.py` and re-run
3. **Deploy:** Use merged model or LoRA weights in production
4. **Monitor:** Track metrics in W&B (if enabled in config)

---

## Files Summary

| File | Purpose | Input | Output |
|------|---------|-------|--------|
| `config.py` | Configuration management | — | (imports) |
| `utils.py` | Utility functions | — | (imports) |
| `01_preprocess.py` | Preprocessing | Stage 01/02/04 | `processed_training_data.jsonl` |
| `02_finetune.py` | Fine-tuning | `processed_training_data.jsonl` | `lora_weights/` |
| `03_evaluate.py` | Evaluation | `lora_weights/` + test set | `evaluation_results.json` |
| `00_quickstart.py` | Orchestrator | — | Runs all stages |

---

## References

- [QLoRA Paper](https://arxiv.org/abs/2305.14314)
- [Qwen2.5 Docs](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct)
- [PEFT Library](https://huggingface.co/docs/peft/)
- [Hugging Face SFT Trainer](https://huggingface.co/docs/trl/sft_trainer)

---

**Version:** 2.0  
**Last Updated:** 2026-08-08  
**Status:** Production Ready
