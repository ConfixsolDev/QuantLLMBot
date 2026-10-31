# Ready to Train Qwen 14B! 🚀

## Configuration Confirmed
✓ **Model:** Qwen2.5-14B-Instruct (updated in `config.py`)  
✓ **GPU VRAM:** 24GB+  
✓ **Data Files:** All 4 JSONL files present  
✓ **Training Setup:** 115 instruction-response pairs (Bucket A/B)  
✓ **Test Set:** 10 holdout examples (Bucket C)

---

## Step 1: Pre-Training Checklist

Run this to verify everything is ready:

```bash
cd E:\QuantLLMBot
python scripts/pre_training_checklist.py
```

**Expected output:**
```
✓ Python 3.10.x
✓ GPU: NVIDIA RTX 4090 (or similar 24GB+)
✓ VRAM: 24.0 GB
✓ torch 2.0.x
✓ transformers 4.36.x
✓ peft 0.7.x
... (all dependencies)
✓ Stage 01: 25.0 KB
✓ Stage 02: 41.0 KB
✓ Stage 03: 36.0 KB
✓ Stage 04: 34.0 KB

[SUMMARY] Checks passed: 7/7
✓ All checks passed! Ready to train.
```

If any check fails, see troubleshooting in `SETUP_GUIDE.md`.

---

## Step 2: Run Full Training Pipeline

Once checklist passes, run the complete pipeline:

```bash
python scripts/00_quickstart.py all
```

This will execute in order:
1. **Preprocessing** (1-2 min)
   - Load stages 01/02/04
   - Create 115 instruction-response pairs
   - Output: `processed_training_data.jsonl`

2. **Fine-Tuning** (60-90 min on RTX 4090, slower on smaller GPUs)
   - Load Qwen 14B with 4-bit quantization
   - Apply LoRA (r=16, alpha=32)
   - Train 3 epochs
   - Save checkpoints every 50 steps
   - Output: `lora_weights/adapter_model.bin` (~100-150 MB)

3. **Evaluation** (5-10 min)
   - Load model + LoRA weights (merged)
   - Generate predictions on 10 test examples
   - Compute metrics
   - Output: `evaluation_results.json`

---

## Step 3: Monitor Training

### Watch logs in real-time:

**Windows (PowerShell):**
```powershell
Get-Content model_training/logs/training.log -Wait
```

**macOS/Linux:**
```bash
tail -f model_training/logs/training.log
```

### Expected training output:
```
[STEP 5] Starting training...
Epoch 1/3:  33%|███       | 38/115 [XX:XXs, X.XXs/it, loss=2.12]
Epoch 1/3:  67%|██████▋   | 77/115 [XX:XXs, X.XXs/it, loss=1.89]
Epoch 1/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=1.76]

Epoch 2/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=1.55]
Epoch 3/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=1.42]

Training loss: 1.5789
Total time: 72m 34s
```

---

## Step 4: Review Results

After training completes, check evaluation results:

```bash
cat model_training/outputs/evaluation_results.json
```

**Expected metrics:**
```json
{
  "num_test_examples": 10,
  "metrics": {
    "exact_match_decision": 65.00,
    "decision_agreement": 82.50,
    "conviction_score_mae": 0.0845,
    "conviction_score_rmse": 0.1123,
    "evidence_label_accuracy": 0.0
  },
  "predictions": [
    {
      "example_id": "001",
      "predicted_decision": "BUY",
      "reference_decision": "BUY",
      "match": true
    },
    ...
  ]
}
```

---

## Alternative: Run Stages Individually

If you want to run each stage separately:

```bash
# Stage 1: Preprocessing (1-2 min)
python scripts/01_preprocess.py

# Stage 2: Fine-Tuning (60-90 min)
# NOTE: This is the main training step
python scripts/02_finetune.py

# Stage 3: Evaluation (5-10 min)
python scripts/03_evaluate.py
```

---

## Storage Requirements

**Total disk space needed during training:**

```
Raw data:                ~140 KB
Processed training data: ~3 MB
Model weights (14B 4-bit): ~9 GB
Checkpoints (3 saved):   ~15 GB
LoRA weights (final):    ~150 MB
─────────────────────────────────
Total:                   ~24 GB
```

After training, you can delete checkpoints to free space:
```bash
rm -rf model_training/checkpoints/
```

---

## Key Files Generated

| File | Location | Size | Purpose |
|------|----------|------|---------|
| Processed data | `outputs/processed_training_data.jsonl` | 3 MB | Training data |
| LoRA adapter config | `outputs/lora_weights/adapter_config.json` | 1 KB | Config metadata |
| LoRA weights | `outputs/lora_weights/adapter_model.bin` | 100-150 MB | Trained weights |
| Evaluation results | `outputs/evaluation_results.json` | 50-100 KB | Metrics + predictions |
| Training logs | `logs/training.log` | Variable | Full training log |

---

## Expected Timeline (RTX 4090 / A100)

```
Preprocessing:     2 min  ██░░░░░░░░░░░░░░░░░░ 2%
Fine-tuning:      60 min ██████████████░░░░░░░ 80%
Evaluation:        5 min  ██████████████████░░ 97%
────────────────────────────────────────────────
Total:            67 min ██████████████████░░ 100%
```

If you have a smaller GPU (RTX 4070, RTX 3090), training will take 2-3 hours.

---

## If Training Gets Interrupted

**Resume from checkpoint:**

Edit `config.py`:
```python
training_args = TrainingArguments(
    resume_from_checkpoint="model_training/checkpoints/checkpoint-100"
)
```

Then run:
```bash
python scripts/02_finetune.py
```

---

## Next: Inference & Deployment

Once training is complete, use the fine-tuned model:

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base + LoRA
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-14B-Instruct", ...)
model = PeftModel.from_pretrained(model, "model_training/outputs/lora_weights")

# Merge for deployment
model = model.merge_and_unload()

# Use for trading decisions
response = model.generate(inputs, max_new_tokens=200)
```

Or run the inference example:
```bash
python scripts/inference_example.py
```

---

## Troubleshooting During Training

### Training is very slow
- Check GPU utilization: `nvidia-smi -l 1`
- May need to reduce batch size or use smaller model

### Out of memory (OOM) error
- Reduce batch size in `config.py`:
  ```python
  training_config.per_device_train_batch_size = 1
  ```
- Increase gradient accumulation:
  ```python
  training_config.gradient_accumulation_steps = 8
  ```

### Model doesn't download
```bash
huggingface-cli download Qwen/Qwen2.5-14B-Instruct --cache-dir ./cache
```

### Checkpoints not saving
Ensure `model_training/checkpoints/` exists:
```bash
mkdir -p E:\QuantLLMBot\model_training\checkpoints
```

---

## You're All Set! 🎯

**Run this command to start training:**

```bash
python scripts/pre_training_checklist.py && python scripts/00_quickstart.py all
```

Good luck! 🚀

---

**Config Summary:**
- **Model:** Qwen/Qwen2.5-14B-Instruct
- **Quantization:** 4-bit NF4 (reduces 28GB → ~7GB)
- **LoRA:** r=16, alpha=32
- **Training Data:** 115 examples, 3 epochs
- **Batch Size:** 2 (effective: 8 with gradient accumulation)
- **Learning Rate:** 2e-4
- **Expected Time:** 60-90 minutes
