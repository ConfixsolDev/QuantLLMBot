#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Fine-Tuning with QLoRA
Fine-tune Qwen2.5-14B-Instruct using LoRA adapters on instruction-response pairs.
Usage: python 02_finetune.py

Uses plain transformers Trainer (same proven recipe as v001
train_qwen7b_qlora_colab.py) to avoid TRL API drift between versions.
The chat template wraps instruction (user) + response (assistant) so the
model learns to produce the response, not to reproduce the instruction.
"""

import sys
import logging
from pathlib import Path
import os

os.environ.setdefault("WANDB_PROJECT", "quantllmbot-phase4")

import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from datasets import load_dataset

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    model_config, quant_config, lora_config, training_config, pipeline_config,
    PROCESSED_DATA_PATH, CHECKPOINT_DIR, LORA_WEIGHTS_DIR, LOGS_DIR
)
from utils import setup_logging

logger = logging.getLogger(__name__)


def setup_model_and_tokenizer():
    """Initialize model and tokenizer with quantization."""
    logger.info(f"Loading base model: {model_config.base_model}")

    # BitsAndBytes quantization config
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=quant_config.load_in_4bit,
        bnb_4bit_use_double_quant=quant_config.bnb_4bit_use_double_quant,
        bnb_4bit_quant_type=quant_config.bnb_4bit_quant_type,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    # Load model with quantization
    model = AutoModelForCausalLM.from_pretrained(
        model_config.base_model,
        quantization_config=bnb_config,
        device_map=model_config.device_map,
        trust_remote_code=model_config.trust_remote_code,
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False
    if training_config.gradient_checkpointing:
        model.gradient_checkpointing_enable()
    model = prepare_model_for_kbit_training(model)

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_config.base_model,
        trust_remote_code=model_config.trust_remote_code,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    logger.info(f"  ✓ Model loaded: {model.config.model_type}")
    logger.info(f"  ✓ Tokenizer loaded, vocab size: {len(tokenizer)}")

    return model, tokenizer


def setup_lora(model):
    """Configure and apply LoRA to model."""
    logger.info("Setting up LoRA...")
    logger.info(f"  LoRA r={lora_config.r}, alpha={lora_config.lora_alpha}")
    logger.info(f"  Target modules: {lora_config.target_modules}")

    peft_config = LoraConfig(
        r=lora_config.r,
        lora_alpha=lora_config.lora_alpha,
        target_modules=lora_config.target_modules,
        lora_dropout=lora_config.lora_dropout,
        bias=lora_config.bias,
        task_type=TaskType.CAUSAL_LM,
    )

    model = get_peft_model(model, peft_config)
    logger.info(f"  ✓ LoRA applied. Trainable params: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

    return model


def load_training_data(tokenizer):
    """Load preprocessed training data and tokenize instruction+response pairs.

    CRITICAL: the model must see the assistant response as training labels.
    We render each pair through the Qwen chat template and train on the
    full sequence (causal LM), matching the v001/v002 recipe.
    """
    logger.info(f"Loading training data from {PROCESSED_DATA_PATH}...")

    if not PROCESSED_DATA_PATH.exists():
        logger.error(f"Processed data not found: {PROCESSED_DATA_PATH}")
        logger.error("Run 01_preprocess.py first.")
        sys.exit(1)

    dataset = load_dataset(
        "json",
        data_files=str(PROCESSED_DATA_PATH),
        split="train"
    )

    logger.info(f"  ✓ Loaded {len(dataset)} training examples")
    logger.info(f"    Sample instruction: {dataset[0]['instruction'][:100]}...")
    logger.info(f"    Sample response: {dataset[0]['response'][:100]}...")

    def to_text(example):
        messages = [
            {"role": "user", "content": example["instruction"]},
            {"role": "assistant", "content": example["response"]},
        ]
        return {
            "text": tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=False
            )
        }

    dataset = dataset.map(to_text, remove_columns=dataset.column_names)

    def tokenize(batch):
        tokens = tokenizer(
            batch["text"],
            max_length=training_config.max_seq_length,
            truncation=True,
            padding=False,
        )
        tokens["labels"] = [ids.copy() for ids in tokens["input_ids"]]
        return tokens

    dataset = dataset.map(tokenize, batched=True, remove_columns=["text"])
    logger.info(f"  ✓ Tokenized {len(dataset)} sequences (max_len={training_config.max_seq_length})")
    return dataset


def main():
    """Main fine-tuning pipeline."""
    logger.info("=" * 80)
    logger.info("QuantLLMBot Phase 4: FINE-TUNING (QLoRA)")
    logger.info("=" * 80)
    logger.info(f"GPU Available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        logger.info(f"GPU: {torch.cuda.get_device_name(0)}")
        logger.info(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")

    # ========================================================================
    # STEP 1: Setup model, tokenizer, LoRA
    # ========================================================================
    logger.info("\n[STEP 1] Setting up model and LoRA...")
    model, tokenizer = setup_model_and_tokenizer()
    model = setup_lora(model)

    # ========================================================================
    # STEP 2: Load training data
    # ========================================================================
    logger.info("\n[STEP 2] Loading training data...")
    train_dataset = load_training_data(tokenizer)

    # ========================================================================
    # STEP 3: Configure training arguments
    # ========================================================================
    logger.info("\n[STEP 3] Configuring training arguments...")
    training_args = TrainingArguments(
        output_dir=str(CHECKPOINT_DIR),
        per_device_train_batch_size=training_config.per_device_train_batch_size,
        per_device_eval_batch_size=training_config.per_device_eval_batch_size,
        gradient_accumulation_steps=training_config.gradient_accumulation_steps,
        learning_rate=training_config.learning_rate,
        weight_decay=training_config.weight_decay,
        max_grad_norm=training_config.max_grad_norm,
        num_train_epochs=training_config.num_train_epochs,
        warmup_steps=training_config.warmup_steps,
        save_steps=training_config.save_steps,
        logging_steps=training_config.logging_steps,
        save_total_limit=training_config.save_total_limit,
        bf16=training_config.bf16,
        fp16=training_config.fp16,
        optim=training_config.optim,
        gradient_checkpointing=training_config.gradient_checkpointing,
        seed=training_config.seed,
        report_to=["wandb"] if pipeline_config.use_wandb else [],
        logging_dir=str(LOGS_DIR),
    )

    logger.info(f"  ✓ Effective batch size: {training_config.per_device_train_batch_size * training_config.gradient_accumulation_steps}")
    logger.info(f"  ✓ Learning rate: {training_config.learning_rate}")
    logger.info(f"  ✓ Epochs: {training_config.num_train_epochs}")

    # ========================================================================
    # STEP 4: Initialize trainer
    # ========================================================================
    logger.info("\n[STEP 4] Initializing trainer...")
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )

    logger.info("  ✓ Trainer initialized")

    # ========================================================================
    # STEP 5: Train
    # ========================================================================
    logger.info("\n[STEP 5] Starting training...")
    logger.info("=" * 80)

    train_result = trainer.train()

    logger.info("\n" + "=" * 80)
    logger.info("TRAINING COMPLETE")
    logger.info("=" * 80)

    # ========================================================================
    # STEP 6: Save LoRA weights
    # ========================================================================
    logger.info("\n[STEP 6] Saving LoRA weights...")
    model.save_pretrained(str(LORA_WEIGHTS_DIR))
    tokenizer.save_pretrained(str(LORA_WEIGHTS_DIR))

    logger.info(f"  ✓ LoRA weights saved to: {LORA_WEIGHTS_DIR}")
    logger.info(f"  ✓ Adapter config: {LORA_WEIGHTS_DIR / 'adapter_config.json'}")
    logger.info(f"  ✓ Adapter weights: {LORA_WEIGHTS_DIR / 'adapter_model.safetensors'}")

    # ========================================================================
    # STEP 7: Summary
    # ========================================================================
    logger.info("\n[STEP 7] Training summary")
    logger.info(f"  Training loss: {train_result.training_loss:.4f}")
    logger.info(f"  Total time: {train_result.metrics['train_runtime']:.2f}s")
    logger.info(f"  Samples/second: {train_result.metrics['train_samples_per_second']:.2f}")

    logger.info("\n✓ Fine-tuning successful!")
    logger.info("Next step: Run 03_evaluate.py to evaluate on holdout test set")


if __name__ == "__main__":
    setup_logging(LOGS_DIR)
    main()
