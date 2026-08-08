# QuantLLMBot Phase 4: Google Colab Training Guide

Complete guide for training Qwen 14B on Google Colab A100 GPU.

---

## Why Google Colab?

✓ **A100 GPU** (40GB VRAM) - Fastest available  
✓ **Free tier available** - 12-100 compute units/month  
✓ **No local setup needed** - Everything runs in cloud  
✓ **Google Drive integration** - Easy file access  
✓ **Pre-installed libraries** - Skip dependency hell  

**Training time on A100:** ~45-60 minutes for full pipeline

---

## Step 1: Upload Data to Google Drive

1. Open **Google Drive** (drive.google.com)
2. Create folder: `My Drive > QuantLLMBot`
3. Create subfolder: `QuantLLMBot > model_training > knowledge`
4. Upload 4 JSONL files:
   - `stage_01_principle_foundation.jsonl`
   - `stage_02_structured_data.jsonl`
   - `stage_03_detector_definitions.jsonl`
   - `stage_04_decision_contract.jsonl`

**Folder structure:**
```
My Drive/
├── QuantLLMBot/
│   └── model_training/
│       └── knowledge/
│           ├── stage_01_principle_foundation.jsonl
│           ├── stage_02_structured_data.jsonl
│           ├── stage_03_detector_definitions.jsonl
│           └── stage_04_decision_contract.jsonl
```

---

## Step 2: Create Colab Notebook

1. Go to **Google Colab** (colab.research.google.com)
2. Click **New notebook**
3. Rename: `QuantLLMBot Phase 4 Training`
4. Go to **Runtime → Change runtime type**
   - GPU: **A100**
   - Disk: **High** (recommended)
   - Click **Save**

---

## Step 3: Copy & Run Training Script

1. Copy the entire content of `QuantLLMBot_Phase4_Colab.py`
2. Paste into a Colab cell
3. Run the cell (Ctrl+Enter or click play button)

**The script will:**
- ✓ Install all dependencies (takes 2-3 min)
- ✓ Mount your Google Drive
- ✓ Verify data files
- ✓ Preprocess data (1-2 min)
- ✓ Fine-tune Qwen 14B (45-60 min)
- ✓ Evaluate on test set (5-10 min)
- ✓ Save results to Google Drive

---

## Step 4: Monitor Training

### Watch real-time output
The Colab cell shows live output as training progresses:
```
INSTALLING DEPENDENCIES...
✓ All dependencies installed!

MOUNTING GOOGLE DRIVE...
✓ Working directory: /content/drive/MyDrive/QuantLLMBot

VERIFYING DATA FILES...
✓ stage_01_principle_foundation.jsonl (25.0 KB)
✓ stage_02_structured_data.jsonl (41.0 KB)
✓ stage_03_detector_definitions.jsonl (36.0 KB)
✓ stage_04_decision_contract.jsonl (34.0 KB)

CREATING CONFIGURATION FOR QWEN 14B (A100)...
Model: Qwen/Qwen2.5-14B-Instruct
Quantization: 4-bit nf4
...

PREPROCESSING: Creating instruction-response pairs...
✓ Created 115 instruction-response pairs

FINE-TUNING: Training Qwen 14B with QLoRA (A100)...
GPU: NVIDIA A100-SXM4-40GB
VRAM: 40.0 GB

STARTING TRAINING (3 epochs)...
Epoch 1/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=2.12]
Epoch 2/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=1.55]
Epoch 3/3: 100%|██████████| 115/115 [XX:XXs, X.XXs/it, loss=1.42]

TRAINING COMPLETE
Training loss: 1.4789

EVALUATION: Testing on holdout set...
✓ TRAINING COMPLETE!
```

### Check GPU usage
In a new Colab cell:
```python
!nvidia-smi
```

You should see A100 with ~20-30GB utilization during training.

---

## Step 5: Download Results

Once training completes:

1. Go to **Google Drive > QuantLLMBot > model_training > outputs**
2. Download folder: `lora_weights/` (contains adapter_model.bin)
3. Download file: `evaluation_results.json`

**Files to download:**
- `lora_weights/adapter_model.bin` (~150 MB) — trained weights
- `lora_weights/adapter_config.json` (1 KB) — config
- `evaluation_results.json` (50 KB) — metrics

---

## Step 6: Use the Trained Model

### Option A: In Colab (before disconnecting)

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

# Load base model
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-14B-Instruct",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

# Load LoRA weights
lora_path = "/content/drive/MyDrive/QuantLLMBot/model_training/outputs/lora_weights"
model = PeftModel.from_pretrained(model, lora_path)

# Merge and unload
model = model.merge_and_unload()

# Use for inference
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-14B-Instruct")
inputs = tokenizer("Your trade setup...", return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(outputs[0]))
```

### Option B: On Local Machine

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Download lora_weights from Google Drive to E:\QuantLLMBot\model_training\outputs\

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-14B-Instruct", ...)
model = PeftModel.from_pretrained(model, "path/to/lora_weights")
model = model.merge_and_unload()

# Now use model for inference
```

---

## Troubleshooting

### "GPU out of memory" error

**Solution:** The script already uses 4-bit quantization (reduces 28GB → ~7GB). If you still get OOM:

1. Reduce batch size in the Colab script:
   ```python
   config.per_device_train_batch_size = 1  # Was 2
   ```

2. Increase gradient accumulation:
   ```python
   config.gradient_accumulation_steps = 8  # Was 4
   ```

### "Data files not found" error

**Solution:** Make sure files are in the correct Google Drive path:
```
My Drive/QuantLLMBot/model_training/knowledge/stage_*.jsonl
```

If paths are different, edit this line in the Colab script:
```python
COLAB_ROOT = Path("/content/drive/MyDrive/YOUR_ACTUAL_PATH")
```

### Training interrupted (disconnected)

**Note:** A100 training only takes 45-60 minutes, so it should complete without interruption. But if it does:

1. You can resume from checkpoints (if saved)
2. Or just re-run the entire script (it overwrites)

### Model download timeout

If Hugging Face is slow, pre-download in Colab:
```python
!huggingface-cli download Qwen/Qwen2.5-14B-Instruct
```

---

## Expected Timeline (A100)

```
Task                    Time      Progress
─────────────────────────────────────────────
Install dependencies    3 min     ████░░░░░░░░░░░░░░░░░  10%
Mount Drive            30 sec    ████░░░░░░░░░░░░░░░░░  12%
Preprocessing          2 min     ████░░░░░░░░░░░░░░░░░  15%
Fine-tuning           45 min     ████████████████░░░░░  80%
Evaluation             5 min     ██████████████████░░░  95%
Save & Summary        1 min     ██████████████████░░░  100%
─────────────────────────────────────────────
Total:               56 min
```

---

## Configuration for A100

The Colab script is pre-configured for A100:

```python
# Qwen 14B (28GB base → 7GB with 4-bit quantization)
per_device_train_batch_size = 2
gradient_accumulation_steps = 4
effective_batch_size = 8

# Optimizations for A100
fp16 = False
bf16 = True              # A100 has bfloat16 support
optim = "paged_adamw_32bit"
gradient_checkpointing = True
```

---

## Cost

**Google Colab Pricing:**
- **Free tier:** Up to 12 compute units/month (A100 = ~0.25 units/hour)
- **Colab Pro:** $10/month, 100 units/month
- **Cost per training:** ~$0.25-0.50 on Colab Pro

For this training (45 min on A100): **~$0.20**

---

## Next Steps

1. **Download outputs** from Google Drive
2. **Review evaluation results** (`evaluation_results.json`)
3. **Use the model** for trading predictions (see "Use the Trained Model" above)
4. **Deploy** using LoRA weights

---

## Tips

- **Keep Colab tab open** during training (don't close)
- **Use Colab Pro** for longer stability and better GPUs
- **Save checkpoints to Drive** during training (script does this automatically)
- **Monitor GPU** with `!nvidia-smi` in a new cell
- **Download early** — don't wait until connection times out

---

## File Locations

| Purpose | Location |
|---------|----------|
| Input data | Google Drive: `QuantLLMBot/model_training/knowledge/` |
| Training logs | Google Drive: `QuantLLMBot/model_training/logs/` |
| Checkpoints | Google Drive: `QuantLLMBot/model_training/checkpoints/` |
| LoRA weights | Google Drive: `QuantLLMBot/model_training/outputs/lora_weights/` |
| Results | Google Drive: `QuantLLMBot/model_training/outputs/evaluation_results.json` |

---

## Support

If you run into issues:

1. Check **Colab cell output** for error messages
2. Run **GPU check cell:** `!nvidia-smi`
3. Verify **Google Drive paths** are correct
4. Check **data files** are uploaded
5. Re-run the script (it's safe to run multiple times)

---

**You're all set! 🚀**

**Next: Run the Colab script and watch your Qwen 14B model train on A100!**

```
python QuantLLMBot_Phase4_Colab.py
```

(Copy the script content into a Colab cell and run)

---

**Version:** 2.0  
**Last Updated:** 2026-08-08  
**GPU:** A100 (40GB)  
**Model:** Qwen2.5-14B-Instruct  
**Training Time:** 45-60 minutes
