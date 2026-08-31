#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Evaluation
Evaluate fine-tuned model on holdout test set (config test_lines_*).
Scores Decision match plus Action/Direction bridge fields (live-aligned).
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
    STAGE_02_PATH, STAGE_04_PATH, STAGE_05_PATH, LORA_WEIGHTS_DIR, EVAL_RESULTS_PATH,
    model_config, pipeline_config
)
from utils import (
    load_jsonl, setup_logging, extract_decision, extract_conviction_score,
    extract_action_direction, extract_evidence_label, compute_exact_match,
    compute_decision_agreement, format_principle_context,
)

logger = logging.getLogger(__name__)

ENTRY_KEYS = {
    "bias", "confidence", "evidence_ids", "plan_status",
    "geometry_row_id", "plan_reason", "data_requests",
}
MANAGEMENT_KEYS = {
    "action", "thesis_state", "decision_level_ref", "next_target_ref",
    "confirmation_type", "confirmation_evidence_ids", "close_confirmed",
    "regime_assessment", "summary",
}


def load_model_with_lora():
    """Load base model (4-bit) and attach LoRA weights.

    14B in bf16 needs ~28 GB — too large for most single GPUs. 4-bit NF4
    keeps eval on the same hardware the training ran on.
    """
    logger.info(f"Loading base model: {model_config.base_model}")

    from transformers import BitsAndBytesConfig
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_config.base_model,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=model_config.trust_remote_code,
    )

    logger.info(f"Loading LoRA weights from: {LORA_WEIGHTS_DIR}")
    if not LORA_WEIGHTS_DIR.exists():
        logger.error(f"LoRA weights not found: {LORA_WEIGHTS_DIR}")
        logger.error("Run 02_finetune.py first.")
        sys.exit(1)

    # Attach LoRA (cannot merge into 4-bit weights; adapter stays active)
    model = PeftModel.from_pretrained(model, str(LORA_WEIGHTS_DIR))
    model.eval()

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
    max_length: int = 350,
    temperature: float = 0.7
) -> str:
    """Generate model prediction for a given instruction.

    Uses the same chat template as training so the model sees an identical
    prompt format (user turn + generation prompt).
    """
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": instruction}],
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=model_config.model_max_length
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_length,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # Decode only the newly generated tokens (everything after the prompt)
    new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
    response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

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

Based on the principles above and the trade setup, decide using this contract:
Action open|wait|skip; Direction buy|sell|none; Confidence 1-100;
named Key Levels; Entry/Stop Loss/Take Profit when Action=open.
Session permission and closed-bar acceptance override pattern names."""


def live_contract_instruction(row: Dict[str, Any]) -> str:
    return (
        f"Return only valid JSON for {row['contract_version']}. "
        "Return exactly the required fields and use only supplied IDs and facts. "
        "For entry ready, select one geometry_row_id and leave data_requests empty; "
        "for wait use geometry_row_id __none__.\n\n"
        + json.dumps(row["prompt_facts"], ensure_ascii=False, separators=(",", ":"))
    )


def validate_live_contract(row: Dict[str, Any], raw: str) -> tuple[dict | None, list[str]]:
    failures = []
    try:
        out = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, ["invalid_json"]
    expected = row["expected_response"]
    facts = row["prompt_facts"]
    if row["role"] == "live_contract":
        if set(out) != ENTRY_KEYS:
            failures.append("wrong_keys")
        if out.get("bias") not in {"buy", "sell", "wait"}:
            failures.append("invalid_bias")
        if not isinstance(out.get("confidence"), int) or not 1 <= out.get("confidence", 0) <= 100:
            failures.append("invalid_confidence")
        known = set(facts.get("citeable_evidence_ids") or ["__no_evidence__"])
        cited = out.get("evidence_ids")
        if not isinstance(cited, list) or not 1 <= len(cited) <= 6 or not set(cited) <= known:
            failures.append("invalid_evidence")
        status = out.get("plan_status")
        requests = out.get("data_requests")
        if status not in {"ready", "wait"} or not isinstance(requests, list) or len(requests) > 2:
            failures.append("invalid_status_or_requests")
        if status == "ready":
            menu = {x.get("geometry_row_id"): x for x in facts.get("entry_geometry_menu") or []}
            selected = menu.get(out.get("geometry_row_id"))
            if not selected or selected.get("side") != out.get("bias"):
                failures.append("invalid_geometry_row")
            if requests:
                failures.append("ready_with_requests")
        elif out.get("geometry_row_id") != "__none__":
            failures.append("wait_without_sentinel")
    else:
        if set(out) != MANAGEMENT_KEYS:
            failures.append("wrong_keys")
        if out.get("action") not in {"hold", "protect", "close"}:
            failures.append("invalid_action")
    return out, failures


def evaluate_live_contracts(model, tokenizer, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    predictions = []
    for row in tqdm(rows, desc="live contract"):
        raw = generate_prediction(model, tokenizer, live_contract_instruction(row), max_length=384)
        parsed, failures = validate_live_contract(row, raw)
        expected = row["expected_response"]
        semantic_match = bool(parsed) and (
            (parsed.get("bias"), parsed.get("plan_status")) ==
            (expected.get("bias"), expected.get("plan_status"))
            if row["role"] == "live_contract"
            else parsed.get("action") == expected.get("action")
        )
        predictions.append({
            "example_id": row["example_id"], "role": row["role"],
            "valid_contract": not failures, "semantic_match": semantic_match,
            "failures": failures, "raw_response": raw,
        })
    return {
        "num_examples": len(rows),
        "valid_contract_count": sum(x["valid_contract"] for x in predictions),
        "semantic_match_count": sum(x["semantic_match"] for x in predictions),
        "deployment_gate_passed": all(x["valid_contract"] for x in predictions),
        "predictions": predictions,
    }


def evaluate_on_test_set(
    model,
    tokenizer,
    test_examples: List[Dict[str, Any]],
    test_contracts: List[Dict[str, Any]],
    principles_data: List[Dict[str, Any]]
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
    evidence_predictions = []
    evidence_references = []
    raw_responses = []
    action_pairs = []

    for idx, (example, contract) in enumerate(tqdm(zip(test_examples, test_contracts), total=len(test_examples))):
        # Same topic-scoped context as training (all 35 principles overflow
        # the 4096-token prompt budget and truncate the question away)
        principle_context = format_principle_context(principles_data, topic=example.get("topic"))
        instruction = format_test_instruction(example, principle_context)

        # Generate prediction
        response = generate_prediction(model, tokenizer, instruction)

        if idx == 0:
            logger.info(f"  Sample raw output ({example.get('example_id')}):\n{response[:500]}")

        pred_decision = extract_decision(response) or "UNKNOWN"
        pred_conviction = extract_conviction_score(response) or 0.5
        pred_action, pred_direction = extract_action_direction(response)
        pred_evidence = extract_evidence_label(response)

        ref_decision = contract.get('trade_decision', 'HOLD')
        ref_conviction = float(contract.get('conviction_score', 0.5))
        ref_action = contract.get("action")
        ref_direction = contract.get("direction")
        ref_evidence = (contract.get("evidence_label") or "").strip().lower() or None

        predictions.append(pred_decision)
        references.append(ref_decision)
        conviction_predictions.append(pred_conviction)
        conviction_references.append(ref_conviction)
        evidence_predictions.append(pred_evidence)
        evidence_references.append(ref_evidence)
        raw_responses.append(response)
        action_pairs.append((pred_action, pred_direction, ref_action, ref_direction))

        if (idx + 1) % 5 == 0:
            logger.debug(f"  Processed {idx + 1}/{len(test_examples)}")

    conviction_preds_np = np.array(conviction_predictions)
    conviction_refs_np = np.array(conviction_references)

    exact_match_count = sum(1 for p, r in zip(predictions, references) if compute_exact_match(p, r))
    exact_match_acc = exact_match_count / len(predictions) * 100

    decision_agreement = compute_decision_agreement(predictions, references)

    conviction_mae = float(np.mean(np.abs(conviction_preds_np - conviction_refs_np)))
    conviction_rmse = float(np.sqrt(np.mean((conviction_preds_np - conviction_refs_np) ** 2)))

    evidence_hits = sum(
        1 for pe, re in zip(evidence_predictions, evidence_references)
        if pe and re and pe == re
    )
    n_ev = max(1, sum(1 for re in evidence_references if re))
    evidence_acc = evidence_hits / n_ev * 100

    action_hits = sum(
        1 for pa, _, ra, _ in action_pairs
        if pa and ra and pa == ra
    )
    direction_hits = sum(
        1 for _, pd, _, rd in action_pairs
        if pd and rd and pd == rd
    )
    n_ad = max(1, sum(1 for _, _, ra, rd in action_pairs if ra and rd))

    results = {
        "num_test_examples": len(test_examples),
        "metrics": {
            "exact_match_decision": round(exact_match_acc, 2),
            "exact_match_count": exact_match_count,
            "decision_agreement": round(decision_agreement, 2),
            "action_agreement": round(action_hits / n_ad * 100, 2),
            "direction_agreement": round(direction_hits / n_ad * 100, 2),
            "conviction_score_mae": round(conviction_mae, 4),
            "conviction_score_rmse": round(conviction_rmse, 4),
            "evidence_label_accuracy": round(evidence_acc, 2),
        },
        "predictions": [
            {
                "example_id": example.get('example_id'),
                "predicted_decision": pred,
                "reference_decision": ref,
                "predicted_action": pa,
                "reference_action": ra,
                "predicted_direction": pd,
                "reference_direction": rd,
                "predicted_conviction": round(pred_conv, 4),
                "reference_conviction": round(ref_conv, 4),
                "predicted_evidence": pe,
                "reference_evidence": re,
                "raw_response": raw,
                "match": compute_exact_match(pred, ref),
            }
            for example, pred, ref, pred_conv, ref_conv, pe, re, raw, (pa, pd, ra, rd) in zip(
                test_examples, predictions, references,
                conviction_predictions, conviction_references,
                evidence_predictions, evidence_references, raw_responses,
                action_pairs,
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
    principles_data = load_jsonl(STAGE_02_PATH.parent / "stage_01_principle_foundation.jsonl")
    logger.info(f"  ✓ Loaded {len(principles_data)} principles (topic-scoped per example)")

    # ========================================================================
    # STEP 4: Evaluate
    # ========================================================================
    logger.info("\n[STEP 4] Running evaluation...")
    results = evaluate_on_test_set(model, tokenizer, test_examples, test_contracts, principles_data)
    live_rows = load_jsonl(
        STAGE_05_PATH,
        start_line=pipeline_config.test_lines_start,
        end_line=pipeline_config.test_lines_end,
    )
    results["live_contract"] = evaluate_live_contracts(model, tokenizer, live_rows)

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
    logger.info(f"Action Agreement: {metrics['action_agreement']}%")
    logger.info(f"Direction Agreement: {metrics['direction_agreement']}%")
    logger.info(f"Conviction Score MAE: {metrics['conviction_score_mae']}")
    logger.info(f"Conviction Score RMSE: {metrics['conviction_score_rmse']}")
    logger.info(f"Evidence Label Accuracy: {metrics['evidence_label_accuracy']}%")
    live = results["live_contract"]
    logger.info(
        "Live Contract: %d/%d valid; semantic match %d/%d; deployment gate=%s",
        live["valid_contract_count"], live["num_examples"],
        live["semantic_match_count"], live["num_examples"],
        "PASS" if live["deployment_gate_passed"] else "FAIL",
    )

    logger.info("\n✓ Evaluation complete!")


if __name__ == "__main__":
    setup_logging(Path(__file__).parent.parent / "model_training" / "logs")
    main()
