#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Evaluation
Evaluate fine-tuned model on holdout test set (Bucket C, lines 116-125).
Usage: python 03_evaluate.py
"""

import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

import torch
import numpy as np
from tqdm import tqdm
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STAGE_02_PATH, STAGE_04_PATH, LORA_WEIGHTS_DIR, EVAL_RESULTS_PATH,
    model_config, pipeline_config
)
from utils import (
    load_jsonl, setup_logging, extract_decision, extract_conviction_score,
    compute_exact_match, compute_decision_agreement
)

logger = logging.getLogger(__name__)


def load_model_with_lora():
    """Load base model and merge with LoRA weights."""
    logger.info(f"Loading base model: {model_config.base_model}")

    # Load base model (without quantization for inference)
    model = AutoModelForCausalLM.from_pretrained(
        model_config.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=model_config.trust_remote_code,
    )

    logger.info(f"Loading LoRA weights from: {LORA_WEIGHTS_DIR}")
    if not LORA_WEIGHTS_DIR.exists():
        logger.error(f"LoRA weights not found: {LORA_WEIGHTS_DIR}")
        logger.error("Run 02_finetune.py first.")
        sys.exit(1)

    # Load and merge LoRA
    model = PeftModel.from_pretrained(model, str(LORA_WEIGHTS_DIR))
    model = model.merge_and_unload()

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_config.base_model,
        trust_remote_code=model_config.trust_remote_code,
    )
    tokenizer.pad_token = tokenizer.eos_token

    logger.info("  ✓ Model and LoRA weights loaded and merged")
    return model, tokenizer


def generate_prediction(
    model,
    tokenizer,
    instruction: str,
    max_length: int = 200,
    temperature: float = 0.7
) -> str:
    """Generate model prediction for a given instruction."""
    inputs = tokenizer(
        instruction,
        return_tensors="pt",
        truncation=True,
        max_length=model_config.model_max_length
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_length,
            temperature=temperature,
            do_sample=True,
            top_p=0.9,
            top_k=50,
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    # Remove instruction from response
    if instruction in response:
        response = response.split(instruction)[-1].strip()

    return response


def format_test_instruction(example: Dict[str, Any], principles: str) -> str:
    """Format a test example as an instruction for evaluation."""
    return f"""<principle_context>
{principles}
</principle_context>

<trade_setup>
Topic: {example.get('topic', 'N/A')}
Title: {example.get('title', 'N/A')}
Setup: {example.get('setup', 'N/A')}
</trade_setup>

Based on the principles above and the trade setup, what should the trading decision be?"""


def evaluate_on_test_set(
    model,
    tokenizer,
    test_examples: List[Dict[str, Any]],
    test_contracts: List[Dict[str, Any]],
    principle_context: str
) -> Dict[str, Any]:
    """
    Evaluate model on test set and compute metrics.

    Returns:
        Dict with all metrics and predictions
    """
    logger.info(f"Evaluating on {len(test_examples)} test examples...")

    predictions = []
    references = []
    conviction_predictions = []
    conviction_references = []

    for idx, (example, contract) in enumerate(tqdm(zip(test_examples, test_contracts), total=len(test_examples))):
        instruction = format_test_instruction(example, principle_context)

        # Generate prediction
        response = generate_prediction(model, tokenizer, instruction)

        # Extract decision and conviction score
        pred_decision = extract_decision(response) or "UNKNOWN"
        pred_conviction = extract_conviction_score(response) or 0.5

        ref_decision = contract.get('trade_decision', 'HOLD')
        ref_conviction = float(contract.get('conviction_score', 0.5))

        predictions.append(pred_decision)
        references.append(ref_decision)
        conviction_predictions.append(pred_conviction)
        conviction_references.append(ref_conviction)

        if (idx + 1) % 5 == 0:
            logger.debug(f"  Processed {idx + 1}/{len(test_examples)}")

    # Compute metrics
    conviction_preds_np = np.array(conviction_predictions)
    conviction_refs_np = np.array(conviction_references)

    exact_match_count = sum(1 for p, r in zip(predictions, references) if compute_exact_match(p, r))
    exact_match_acc = exact_match_count / len(predictions) * 100

    decision_agreement = compute_decision_agreement(predictions, references)

    conviction_mae = float(np.mean(np.abs(conviction_preds_np - conviction_refs_np)))
    conviction_rmse = float(np.sqrt(np.mean((conviction_preds_np - conviction_refs_np) ** 2)))

    # Evidence label accuracy (simplified: check if certain keywords present)
    evidence_accuracy = 0.0  # Placeholder; requires NLP parsing

    results = {
        "num_test_examples": len(test_examples),
        "metrics": {
            "exact_match_decision": round(exact_match_acc, 2),
            "exact_match_count": exact_match_count,
            "decision_agreement": round(decision_agreement, 2),
            "conviction_score_mae": round(conviction_mae, 4),
            "conviction_score_rmse": round(conviction_rmse, 4),
            "evidence_label_accuracy": round(evidence_accuracy, 2),
        },
        "predictions": [
            {
                "example_id": example.get('example_id'),
                "predicted_decision": pred,
                "reference_decision": ref,
                "predicted_conviction": round(pred_conv, 4),
                "reference_conviction": round(ref_conv, 4),
                "match": compute_exact_match(pred, ref),
            }
            for example, pred, ref, pred_conv, ref_conv in zip(
                test_examples, predictions, references, conviction_predictions, conviction_references
            )
        ]
    }

    return results


def main():
    """Main evaluation pipeline."""
    logger.info("=" * 80)
    logger.info("QuantLLMBot Phase 4: EVALUATION")
    logger.info("=" * 80)
    logger.info(f"GPU Available: {torch.cuda.is_available()}")

    # ========================================================================
    # STEP 1: Load model with LoRA
    # ========================================================================
    logger.info("\n[STEP 1] Loading model with LoRA weights...")
    model, tokenizer = load_model_with_lora()

    # ========================================================================
    # STEP 2: Load test data
    # ========================================================================
    logger.info("\n[STEP 2] Loading test data (Bucket C, lines 116-125)...")
    test_examples = load_jsonl(
        STAGE_02_PATH,
        start_line=pipeline_config.test_lines_start,
        end_line=pipeline_config.test_lines_end
    )
    test_contracts = load_jsonl(
        STAGE_04_PATH,
        start_line=pipeline_config.test_lines_start,
        end_line=pipeline_config.test_lines_end
    )

    if not test_examples:
        logger.error("No test examples found!")
        sys.exit(1)

    logger.info(f"  ✓ Loaded {len(test_examples)} test examples")

    # ========================================================================
    # STEP 3: Load principles for context
    # ========================================================================
    logger.info("\n[STEP 3] Loading principles...")
    from utils import load_jsonl, format_principle_context
    principles_data = load_jsonl(STAGE_02_PATH.parent / "stage_01_principle_foundation.jsonl")
    principle_context = format_principle_context(principles_data)
    logger.info(f"  ✓ Loaded {len(principles_data)} principles")

    # ========================================================================
    # STEP 4: Evaluate
    # ========================================================================
    logger.info("\n[STEP 4] Running evaluation...")
    results = evaluate_on_test_set(model, tokenizer, test_examples, test_contracts, principle_context)

    # ========================================================================
    # STEP 5: Save results
    # ========================================================================
    logger.info("\n[STEP 5] Saving results...")
    EVAL_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(EVAL_RESULTS_PATH, 'w') as f:
        json.dump(results, f, indent=2)

    logger.info(f"  ✓ Results saved to: {EVAL_RESULTS_PATH}")

    # ========================================================================
    # STEP 6: Print summary
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 80)
    metrics = results["metrics"]
    logger.info(f"Exact Match Decision: {metrics['exact_match_decision']}% ({metrics['exact_match_count']}/{len(test_examples)})")
    logger.info(f"Decision Agreement: {metrics['decision_agreement']}%")
    logger.info(f"Conviction Score MAE: {metrics['conviction_score_mae']}")
    logger.info(f"Conviction Score RMSE: {metrics['conviction_score_rmse']}")
    logger.info(f"Evidence Label Accuracy: {metrics['evidence_label_accuracy']}%")

    logger.info("\n✓ Evaluation complete!")


if __name__ == "__main__":
    setup_logging(Path(__file__).parent.parent / "model_training" / "logs")
    main()
