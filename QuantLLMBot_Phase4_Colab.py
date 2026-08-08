#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Google Colab Training Notebook
Complete training pipeline for Qwen 14B on Google Colab A100
Copy this entire script into a Colab cell and run.
"""

# ============================================================================
# STEP 0: Install dependencies (run once)
# ============================================================================

import subprocess
import sys

print("=" * 80)
print("INSTALLING DEPENDENCIES (takes 2-3 minutes)...")
print("=" * 80)

# Install PyTorch with CUDA support
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-q",
    "torch>=2.0.0", "torchvision", "torchaudio",
    "--index-url", "https://download.pytorch.org/whl/cu121"
])

# Install required packages
packages = [
    "transformers>=4.36.0",
    "peft>=0.7.0",
    "bitsandbytes>=0.41.0",
    "datasets>=2.14.0",
    "accelerate>=0.24.0",
    "trl>=0.7.0",
    "wandb>=0.15.0",
    "pydantic>=2.0.0",
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "tqdm>=4.66.0",
    "pyyaml>=6.0",
    "jsonlines>=4.0.0",
]

for package in packages:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])

print("✓ All dependencies installed!")

# ============================================================================
# STEP 1: Setup Google Drive and data
# ============================================================================

print("\n" + "=" * 80)
print("MOUNTING GOOGLE DRIVE...")
print("=" * 80)

from google.colab import drive
drive.mount('/content/drive', force_remount=True)

import os
from pathlib import Path

# Set working directory
COLAB_ROOT = Path("/content/drive/MyDrive/QuantLLMBot")
COLAB_ROOT.mkdir(parents=True, exist_ok=True)
os.chdir(str(COLAB_ROOT))

print(f"✓ Working directory: {COLAB_ROOT}")

# Create subdirectories
for dir_name in ["model_training/knowledge", "model_training/outputs/lora_weights",
                  "model_training/checkpoints", "model_training/logs", "scripts"]:
    (COLAB_ROOT / dir_name).mkdir(parents=True, exist_ok=True)

print("✓ Directories created")

# ============================================================================
# STEP 2: Download data files from your source
# ============================================================================

print("\n" + "=" * 80)
print("VERIFYING DATA FILES...")
print("=" * 80)

required_files = [
    "model_training/knowledge/stage_01_principle_foundation.jsonl",
    "model_training/knowledge/stage_02_structured_data.jsonl",
    "model_training/knowledge/stage_03_detector_definitions.jsonl",
    "model_training/knowledge/stage_04_decision_contract.jsonl",
]

all_files_exist = True
for file_path in required_files:
    full_path = COLAB_ROOT / file_path
    if full_path.exists():
        size_kb = full_path.stat().st_size / 1024
        print(f"✓ {file_path} ({size_kb:.1f} KB)")
    else:
        print(f"⚠ MISSING: {file_path}")
        all_files_exist = False

if not all_files_exist:
    print("\n⚠ Some data files are missing!")
    print("Please upload them to your Google Drive:")
    print(f"  Path: {COLAB_ROOT}/model_training/knowledge/")
    print("Then restart this cell.")

# ============================================================================
# STEP 3: Create configuration
# ============================================================================

print("\n" + "=" * 80)
print("CREATING CONFIGURATION FOR QWEN 14B (A100)...")
print("=" * 80)

import json
from dataclasses import dataclass, asdict
from typing import Optional, List

@dataclass
class QuantLLMConfig:
    # Model
    base_model: str = "Qwen/Qwen2.5-14B-Instruct"
    model_max_length: int = 4096

    # Quantization
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = "nf4"

    # LoRA
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05

    # Training
    per_device_train_batch_size: int = 2
    per_device_eval_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0
    num_train_epochs: int = 3
    warmup_steps: int = 100

    # A100 optimizations
    fp16: bool = False
    bf16: bool = True
    optim: str = "paged_adamw_32bit"
    gradient_checkpointing: bool = True

    # Data
    training_lines_start: int = 0
    training_lines_end: int = 115
    test_lines_start: int = 115
    test_lines_end: int = 125

config = QuantLLMConfig()

print(f"Model: {config.base_model}")
print(f"Quantization: 4-bit {config.bnb_4bit_quant_type}")
print(f"LoRA: r={config.lora_r}, alpha={config.lora_alpha}")
print(f"Batch Size: {config.per_device_train_batch_size} (effective: {config.per_device_train_batch_size * config.gradient_accumulation_steps})")
print(f"Learning Rate: {config.learning_rate}")
print(f"Epochs: {config.num_train_epochs}")
print(f"Training Data: Lines {config.training_lines_start}-{config.training_lines_end-1}")
print(f"Test Data: Lines {config.test_lines_start}-{config.test_lines_end-1}")

# ============================================================================
# STEP 4: Preprocessing
# ============================================================================

print("\n" + "=" * 80)
print("PREPROCESSING: Creating instruction-response pairs...")
print("=" * 80)

import json
import logging
from tqdm import tqdm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_jsonl(filepath, start_line=0, end_line=None):
    """Load JSONL with line range filtering."""
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if end_line is not None and idx >= end_line:
                break
            if idx < start_line:
                continue
            try:
                obj = json.loads(line.strip())
                data.append(obj)
            except json.JSONDecodeError:
                pass
    return data

def save_jsonl(data, filepath):
    """Save list of dicts to JSONL."""
    with open(filepath, 'w', encoding='utf-8') as f:
        for obj in data:
            f.write(json.dumps(obj) + '\n')

def format_principle_context(principles):
    """Format principles as system prompt."""
    lines = ["# Foundational Principles for Trading Decisions\n"]
    for p in principles:
        lines.append(f"## {p.get('principle_name', 'Unknown')}")
        lines.append(f"Topic: {p.get('topic', 'N/A')}")
        lines.append(f"Core Concept: {p.get('core_concept', 'N/A')}")
        lines.append(f"Foundational Rule: {p.get('foundational_rule', 'N/A')}")
        lines.append("")
    return "\n".join(lines)

def create_instruction_response_pair(example, principle_context, contract):
    """Create instruction-response pair."""
    instruction = f"""<principle_context>
{principle_context}
</principle_context>

<trade_setup>
Topic: {example.get('topic', 'N/A')}
Title: {example.get('title', 'N/A')}
Setup: {example.get('setup', 'N/A')}
</trade_setup>

Based on the principles and setup above, what is the trading decision?"""

    response = f"""Decision: {contract.get('trade_decision', 'HOLD')}

Evidence: {contract.get('evidence_label', 'Unknown')}

Conviction Score: {contract.get('conviction_score', 0.5)}"""

    return {"instruction": instruction.strip(), "response": response.strip()}

# Load all stages
stage_01_path = COLAB_ROOT / "model_training/knowledge/stage_01_principle_foundation.jsonl"
stage_02_path = COLAB_ROOT / "model_training/knowledge/stage_02_structured_data.jsonl"
stage_04_path = COLAB_ROOT / "model_training/knowledge/stage_04_decision_contract.jsonl"

print("Loading stages...")
stage_01 = load_jsonl(stage_01_path)
stage_02 = load_jsonl(stage_02_path)
stage_04 = load_jsonl(stage_04_path)

print(f"  ✓ Stage 01: {len(stage_01)} principles")
print(f"  ✓ Stage 02: {len(stage_02)} examples")
print(f"  ✓ Stage 04: {len(stage_04)} contracts")

# Create training pairs
principle_context = format_principle_context(stage_01)
training_pairs = []

for idx in range(config.training_lines_start, min(config.training_lines_end, len(stage_02))):
    pair = create_instruction_response_pair(stage_02[idx], principle_context, stage_04[idx])
    training_pairs.append(pair)

processed_data_path = COLAB_ROOT / "model_training/outputs/processed_training_data.jsonl"
save_jsonl(training_pairs, processed_data_path)

print(f"\n✓ Created {len(training_pairs)} instruction-response pairs")
print(f"✓ Saved to: {processed_data_path}")

# ============================================================================
# STEP 5: Fine-tuning
# ============================================================================

print("\n" + "=" * 80)
print("FINE-TUNING: Training Qwen 14B with QLoRA (A100)...")
print("=" * 80)

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer
from datasets import load_dataset

# Check GPU
print(f"GPU: {torch.cuda.get_device_name(0)}")
print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")

# Load model with quantization
print("\nLoading model with 4-bit quantization...")
bnb_config = BitsAndBytesConfig(
    load_in_4bit=config.load_in_4bit,
    bnb_4bit_use_double_quant=config.bnb_4bit_use_double_quant,
    bnb_4bit_quant_type=config.bnb_4bit_quant_type,
    bnb_4bit_compute_dtype=torch.bfloat16,
)

model = AutoModelForCausalLM.from_pretrained(
    config.base_model,
    quantization_config=bnb_config,
    device_map="auto",
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(config.base_model, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

print("✓ Model and tokenizer loaded")

# Setup LoRA
print("\nApplying LoRA...")
peft_config = LoraConfig(
    r=config.lora_r,
    lora_alpha=config.lora_alpha,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "up_proj", "down_proj"],
    lora_dropout=config.lora_dropout,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
)

model = get_peft_model(model, peft_config)
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"✓ LoRA applied. Trainable params: {trainable_params:,}")

# Load training data
print("\nLoading training data...")
train_dataset = load_dataset("json", data_files=str(processed_data_path), split="train")
print(f"✓ Loaded {len(train_dataset)} examples")

# Training arguments (optimized for A100)
training_args = TrainingArguments(
    output_dir=str(COLAB_ROOT / "model_training/checkpoints"),
    per_device_train_batch_size=config.per_device_train_batch_size,
    per_device_eval_batch_size=config.per_device_eval_batch_size,
    gradient_accumulation_steps=config.gradient_accumulation_steps,
    learning_rate=config.learning_rate,
    weight_decay=config.weight_decay,
    max_grad_norm=config.max_grad_norm,
    num_train_epochs=config.num_train_epochs,
    warmup_steps=config.warmup_steps,
    save_steps=50,
    logging_steps=10,
    save_total_limit=3,
    bf16=config.bf16,
    fp16=config.fp16,
    optim=config.optim,
    gradient_checkpointing=config.gradient_checkpointing,
    seed=42,
    report_to=[],  # Disable W&B for Colab
    logging_dir=str(COLAB_ROOT / "model_training/logs"),
)

# Create trainer
print("\nInitializing SFT trainer...")
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_dataset,
    args=training_args,
    packing=False,
    dataset_text_field="instruction",
    max_seq_length=config.model_max_length,
)

print("✓ Trainer initialized")

# Train
print("\n" + "=" * 80)
print("STARTING TRAINING (3 epochs)...")
print("=" * 80 + "\n")

train_result = trainer.train()

print("\n" + "=" * 80)
print("TRAINING COMPLETE")
print("=" * 80)
print(f"Training loss: {train_result.training_loss:.4f}")
print(f"Total time: {train_result.metrics['train_runtime']:.0f}s")

# Save LoRA weights
print("\nSaving LoRA weights...")
lora_weights_dir = COLAB_ROOT / "model_training/outputs/lora_weights"
model.save_pretrained(str(lora_weights_dir))
tokenizer.save_pretrained(str(lora_weights_dir))

print(f"✓ LoRA weights saved to: {lora_weights_dir}")
print(f"  - adapter_config.json")
print(f"  - adapter_model.bin (~150 MB)")

# ============================================================================
# STEP 6: Evaluation
# ============================================================================

print("\n" + "=" * 80)
print("EVALUATION: Testing on holdout set...")
print("=" * 80)

from peft import PeftModel
import numpy as np

# Reload model for inference
print("\nLoading model with LoRA for inference...")
base_model = AutoModelForCausalLM.from_pretrained(
    config.base_model,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
)

model = PeftModel.from_pretrained(base_model, str(lora_weights_dir))
model = model.merge_and_unload()

print("✓ Model loaded and LoRA merged")

# Load test data
test_examples = load_jsonl(stage_02_path, config.test_lines_start, config.test_lines_end)
test_contracts = load_jsonl(stage_04_path, config.test_lines_start, config.test_lines_end)

print(f"\nEvaluating on {len(test_examples)} test examples...")

def extract_decision(text):
    """Extract decision from response."""
    if "Decision:" in text:
        return text.split("Decision:")[1].split("\n")[0].strip()
    return "UNKNOWN"

def extract_conviction(text):
    """Extract conviction score from response."""
    try:
        if "Conviction Score:" in text:
            score = text.split("Conviction Score:")[1].split("\n")[0].strip()
            return float(score)
    except:
        pass
    return 0.5

predictions = []
references = []
conviction_preds = []
conviction_refs = []

for example, contract in tqdm(zip(test_examples, test_contracts), total=len(test_examples)):
    instruction = f"""<principle_context>
{principle_context}
</principle_context>

<trade_setup>
Topic: {example.get('topic')}
Setup: {example.get('setup')}
</trade_setup>

What is the trading decision?"""

    inputs = tokenizer(instruction, return_tensors="pt", truncation=True, max_length=4096).to(model.device)

    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=200, temperature=0.7, do_sample=True, top_p=0.9)

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    if instruction in response:
        response = response.split(instruction)[-1].strip()

    pred_decision = extract_decision(response)
    pred_conviction = extract_conviction(response)

    predictions.append(pred_decision)
    references.append(contract.get('trade_decision', 'HOLD'))
    conviction_preds.append(pred_conviction)
    conviction_refs.append(float(contract.get('conviction_score', 0.5)))

# Compute metrics
exact_match = sum(1 for p, r in zip(predictions, references) if p.lower() == r.lower()) / len(predictions) * 100
conviction_mae = np.mean(np.abs(np.array(conviction_preds) - np.array(conviction_refs)))
conviction_rmse = np.sqrt(np.mean((np.array(conviction_preds) - np.array(conviction_refs)) ** 2))

results = {
    "num_test_examples": len(test_examples),
    "metrics": {
        "exact_match_decision": round(exact_match, 2),
        "conviction_score_mae": round(float(conviction_mae), 4),
        "conviction_score_rmse": round(float(conviction_rmse), 4),
    }
}

eval_results_path = COLAB_ROOT / "model_training/outputs/evaluation_results.json"
with open(eval_results_path, 'w') as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 80)
print("EVALUATION RESULTS")
print("=" * 80)
print(f"Exact Match Decision: {results['metrics']['exact_match_decision']}%")
print(f"Conviction Score MAE: {results['metrics']['conviction_score_mae']}")
print(f"Conviction Score RMSE: {results['metrics']['conviction_score_rmse']}")

print(f"\n✓ Results saved to: {eval_results_path}")

# ============================================================================
# STEP 7: Summary
# ============================================================================

print("\n" + "=" * 80)
print("✓ TRAINING COMPLETE!")
print("=" * 80)

print(f"""
Files saved to Google Drive:
  📁 {COLAB_ROOT}

  ✓ model_training/outputs/processed_training_data.jsonl (3 MB)
  ✓ model_training/outputs/lora_weights/adapter_model.bin (~150 MB)
  ✓ model_training/outputs/evaluation_results.json

  🚀 Ready for deployment!

Next steps:
  1. Download lora_weights folder from Google Drive
  2. Use with base model: model + PeftModel.from_pretrained(lora_path)
  3. Or merge: model.merge_and_unload() for single-file deployment
""")

print("✓ All done! Check your Google Drive for outputs.")
