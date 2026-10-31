# QuantLLMBot Phase 4: Setup & Installation Guide

Complete step-by-step instructions to get up and running.

---

## Prerequisites

### System Requirements
- **OS:** Windows 10+, macOS 11+, Linux (Ubuntu 20.04+)
- **Python:** 3.10 or higher
- **GPU:** NVIDIA (RTX 3070+, RTX 4070+, A100, H100) with 8+ GB VRAM
- **CPU RAM:** 16 GB minimum
- **Disk Space:** 50 GB free (model weights + checkpoints + data)

### Check your GPU
```bash
python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
```

If `False`, your GPU isn't recognized. See troubleshooting below.

---

## Installation Steps

### 1. Clone/Download Project

```bash
# If you have git
git clone <repo_url>
cd E:\QuantLLMBot

# Otherwise, download the zip and extract to E:\QuantLLMBot
```

### 2. Create Python Virtual Environment (Recommended)

```bash
# Create venv
python -m venv venv

# Activate venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate
```

### 3. Upgrade pip

```bash
pip install --upgrade pip setuptools wheel
```

### 4. Install PyTorch with GPU Support

**For NVIDIA GPUs (CUDA 12.1):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**For older CUDA versions (11.8):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**For CPU-only (not recommended for training):**
```bash
pip install torch torchvision torchaudio
```

Verify installation:
```bash
python -c "import torch; print(f'PyTorch {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}')"
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `transformers`, `peft`, `bitsandbytes` (model & fine-tuning)
- `trl`, `accelerate` (training)
- `datasets`, `pandas`, `numpy` (data)
- `wandb` (monitoring)
- `jupyter` (optional, for notebooks)

### 6. Verify Data Files

Ensure all stage files exist:
```bash
ls -la E:\QuantLLMBot\model_training\knowledge\stage_*.jsonl
```

Should show:
- `stage_01_principle_foundation.jsonl` (35 records, ~25 KB)
- `stage_02_structured_data.jsonl` (125 records, ~41 KB)
- `stage_03_detector_definitions.jsonl` (125 records, ~36 KB)
- `stage_04_decision_contract.jsonl` (125 records, ~34 KB)

If missing, populate these files before proceeding.

### 7. Create Output Directories

```bash
python scripts/config.py
```

This creates directories if they don't exist. Or manually:
```bash
mkdir -p model_training/outputs/lora_weights
mkdir -p model_training/checkpoints
mkdir -p model_training/logs
```

---

## Quick Verification

Run the environment check:
```bash
python -c "
import torch
import transformers
import peft
import datasets

print('✓ PyTorch:', torch.__version__)
print('✓ Transformers:', transformers.__version__)
print('✓ PEFT:', peft.__version__)
print('✓ Datasets:', datasets.__version__)
print('✓ CUDA available:', torch.cuda.is_available())
if torch.cuda.is_available():
    print('✓ GPU:', torch.cuda.get_device_name(0))
    print('✓ VRAM:', torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')
"
```

Expected output:
```
✓ PyTorch: 2.0.0+cu121
✓ Transformers: 4.36.0
✓ PEFT: 0.7.0
✓ Datasets: 2.14.0
✓ CUDA available: True
✓ GPU: NVIDIA RTX 4090
✓ VRAM: 24.0 GB
```

---

## Run Full Pipeline

### Option 1: Quick Start (Recommended)

```bash
# Run everything
python scripts/00_quickstart.py all

# Or individual stages
python scripts/00_quickstart.py preprocess
python scripts/00_quickstart.py finetune
python scripts/00_quickstart.py evaluate
```

### Option 2: Manual Pipeline

```bash
# Step 1: Preprocess
python scripts/01_preprocess.py
# Output: model_training/outputs/processed_training_data.jsonl

# Step 2: Fine-tune (takes 30-60 min)
python scripts/02_finetune.py
# Output: model_training/outputs/lora_weights/

# Step 3: Evaluate
python scripts/03_evaluate.py
# Output: model_training/outputs/evaluation_results.json
```

### Option 3: Jupyter Notebook (Optional)

```bash
jupyter notebook
```

Create a cell:
```python
%cd E:\QuantLLMBot\scripts
import sys; sys.path.insert(0, '.')

# Now you can run sections interactively
from config import *
from utils import *

# Load and inspect data
stage_01 = load_jsonl(STAGE_01_PATH)
print(f"Loaded {len(stage_01)} principles")
```

---

## Monitoring Training

### Real-time Logs

```bash
# Watch training logs (Unix/Linux/macOS)
tail -f model_training/logs/training.log

# Windows (PowerShell)
Get-Content model_training/logs/training.log -Wait
```

### W&B Dashboard (Optional)

If `use_wandb=True` in `config.py`:

```bash
# Login to W&B
wandb login

# Then during training, logs upload to dashboard
# View at: https://wandb.ai/your-username/quantllmbot-phase4
```

### Checkpoints

During fine-tuning, checkpoints save every N steps:
```bash
ls -la model_training/checkpoints/
# checkpoint-50/
# checkpoint-100/
# ...
```

Resume from checkpoint:
```python
# In config.py
training_args = TrainingArguments(
    resume_from_checkpoint="model_training/checkpoints/checkpoint-50"
)
```

---

## Inference

### Load and Use Model

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load
model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-7B-Instruct",
    torch_dtype="bfloat16",
    device_map="auto"
)
model = PeftModel.from_pretrained(model, "model_training/outputs/lora_weights")

# Or merge for single-file deployment
model = model.merge_and_unload()

# Tokenizer
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")

# Inference
prompt = "Your trading setup..."
inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
outputs = model.generate(**inputs, max_new_tokens=200)
print(tokenizer.decode(outputs[0]))
```

### Use Inference Script

```bash
python scripts/inference_example.py
```

Includes 3 examples of how to use the model.

---

## Troubleshooting

### CUDA Not Found

**Error:** `torch.cuda.is_available() → False`

**Solution:**
1. Check NVIDIA driver:
   ```bash
   nvidia-smi
   ```
   If not found, [install NVIDIA driver](https://www.nvidia.com/Download/driverDetails.aspx)

2. Reinstall PyTorch with correct CUDA version:
   ```bash
   pip uninstall torch torchvision torchaudio
   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
   ```

3. Check `nvcc` version:
   ```bash
   nvcc --version
   ```

### Out of Memory (OOM)

**Error:** `CUDA out of memory`

**Solutions:**
1. Reduce batch size in `config.py`:
   ```python
   training_config.per_device_train_batch_size = 1  # Was 2
   ```

2. Increase gradient accumulation:
   ```python
   training_config.gradient_accumulation_steps = 8  # Was 4
   ```

3. Enable CPU offloading:
   ```python
   training_config.gradient_checkpointing = True
   ```

### Data Files Not Found

**Error:** `Missing required data file: stage_02_structured_data.jsonl`

**Solution:**
Ensure all JSONL files are in `E:\QuantLLMBot\model_training\knowledge\`:
```bash
ls E:\QuantLLMBot\model_training\knowledge\*.jsonl
```

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'transformers'`

**Solution:**
1. Activate venv:
   ```bash
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

2. Reinstall:
   ```bash
   pip install -r requirements.txt
   ```

### Model Download Timeout

**Error:** `Connection timeout downloading model`

**Solution:**
```bash
# Set HF_HOME to cache models locally
export HF_HOME=/path/to/cache
# Then retry
python scripts/02_finetune.py
```

Or manually download model:
```bash
huggingface-cli download Qwen/Qwen2.5-7B-Instruct
```

---

## Configuration Tuning

### Hyperparameters

Edit `scripts/config.py` to adjust:

```python
# Learning rate (lower = more stable, slower convergence)
training_config.learning_rate = 1e-4  # Default 2e-4

# Batch size (larger = faster, needs more VRAM)
training_config.per_device_train_batch_size = 4  # Default 2

# Epochs (more = better fit, risk of overfitting)
training_config.num_epochs = 5  # Default 3

# Warmup steps (for stability)
training_config.warmup_steps = 50  # Default 100

# LoRA rank (higher = more capacity, more parameters)
lora_config.r = 32  # Default 16
```

### Model Size

To use different model:
```python
# config.py
model_config.base_model = "Qwen/Qwen2.5-14B-Instruct"  # Larger model
```

Or smaller:
```python
model_config.base_model = "Qwen/Qwen2.5-3B-Instruct"  # Smaller, faster
```

---

## Performance Expectations

### Preprocessing (~1 min)
- Load 4 JSONL files
- Create 115 instruction-response pairs
- Output: `processed_training_data.jsonl`

### Fine-tuning (~45 min on A100)
- 3 epochs, 115 examples
- Batch size 2, gradient accumulation 4
- Effective batch size: 8
- Time varies: RTX 4090 (~1h), A100 (~30m), RTX 3070 (~2h)

### Evaluation (~5 min)
- Generate predictions on 10 test examples
- Compute metrics
- Output: `evaluation_results.json`

### Expected Metrics
- Exact Match: 65-75%
- Decision Agreement: 80-85%
- Conviction MAE: 0.05-0.10
- Conviction RMSE: 0.08-0.15

---

## Next Steps

1. **Verify Setup:** Run `python scripts/00_quickstart.py all`
2. **Review Results:** Open `model_training/outputs/evaluation_results.json`
3. **Iterate:** Adjust hyperparameters and re-run
4. **Deploy:** Use LoRA weights or merged model in production

---

## Support

### Logs Location
- Training: `model_training/logs/training.log`
- Quickstart: `model_training/logs/quickstart.log`
- Inference: `model_training/logs/inference.log`

### Debug Mode

Enable verbose logging:
```python
# In scripts
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Check GPU Memory
```python
import torch
print(f"Allocated: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
print(f"Reserved: {torch.cuda.memory_reserved() / 1e9:.2f} GB")
torch.cuda.empty_cache()  # Clear cache
```

---

**Status:** ✓ Ready for production  
**Version:** 2.0  
**Last Updated:** 2026-08-08
