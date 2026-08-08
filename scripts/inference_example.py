#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Inference Example
Shows how to load and use the fine-tuned model for trading decision predictions.
Usage: python inference_example.py
"""

import sys
import logging
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    model_config, LORA_WEIGHTS_DIR, STAGE_01_PATH
)
from utils import (
    load_jsonl, format_principle_context, extract_decision,
    extract_conviction_score, setup_logging
)

logger = logging.getLogger(__name__)


def load_model_inference(merge_adapter: bool = True):
    """
    Load model with LoRA weights for inference.

    Args:
        merge_adapter: If True, merge LoRA weights and unload for single-file inference.
                      If False, keep as LoRA + base model (smaller download).

    Returns:
        (model, tokenizer)
    """
    logger.info(f"Loading base model: {model_config.base_model}")
    model = AutoModelForCausalLM.from_pretrained(
        model_config.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=model_config.trust_remote_code,
    )

    logger.info(f"Loading LoRA weights: {LORA_WEIGHTS_DIR}")
    if not LORA_WEIGHTS_DIR.exists():
        logger.error(f"LoRA weights not found: {LORA_WEIGHTS_DIR}")
        logger.error("Run 02_finetune.py first")
        sys.exit(1)

    model = PeftModel.from_pretrained(model, str(LORA_WEIGHTS_DIR))

    if merge_adapter:
        logger.info("Merging LoRA weights into base model...")
        model = model.merge_and_unload()

    tokenizer = AutoTokenizer.from_pretrained(
        model_config.base_model,
        trust_remote_code=model_config.trust_remote_code,
    )
    tokenizer.pad_token = tokenizer.eos_token

    logger.info("  ✓ Model ready for inference")
    return model, tokenizer


def predict(model, tokenizer, instruction: str, max_length: int = 256) -> str:
    """
    Generate a trading decision prediction.

    Args:
        model: Fine-tuned model
        tokenizer: Tokenizer
        instruction: Trade setup instruction
        max_length: Max tokens to generate

    Returns:
        Model response (decision + evidence + conviction)
    """
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
            temperature=0.7,
            do_sample=True,
            top_p=0.9,
            top_k=50,
        )

    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Remove instruction from response if present
    if instruction in response:
        response = response.split(instruction)[-1].strip()

    return response


def example_prediction():
    """Run example prediction on a sample trade setup."""
    logger.info("=" * 80)
    logger.info("QuantLLMBot Phase 4: Inference Example")
    logger.info("=" * 80)

    # Load model
    logger.info("\n[STEP 1] Loading model...")
    model, tokenizer = load_model_inference(merge_adapter=True)

    # Load principles for context
    logger.info("\n[STEP 2] Loading principles context...")
    principles_data = load_jsonl(STAGE_01_PATH)
    principle_context = format_principle_context(principles_data)

    # Create a sample trade setup
    logger.info("\n[STEP 3] Creating sample trade setup...")
    sample_setup = """<principle_context>
Fundamental Principle: Prices oscillate around equilibrium in bounded markets.
When price deviates significantly from moving average (>2 std), mean reversion is likely.

Secondary Principle: Confirmation requires volume and trend alignment.
Do not trade reversals against strong macro trends without additional signals.
</principle_context>

<trade_setup>
Topic: Mean Reversion
Title: XYZ oversold on daily RSI after earnings
Setup: XYZ closed at $45, down 18% from 50-day MA ($55). RSI(14)=22. Volume 40% above average.
Recent swing low: $44.50. Major support: $42. VIX elevated at 22.

Macro: Fed held rates; bond yields stable. Tech sector relatively stable, no major macro shocks.
</trade_setup>

Based on the principles above, what trading decision should be made?"""

    logger.info("Sample setup (excerpt):")
    logger.info(sample_setup[:200] + "...\n")

    # Get prediction
    logger.info("[STEP 4] Generating prediction...")
    response = predict(model, tokenizer, sample_setup)

    # Parse response
    logger.info("\n" + "=" * 80)
    logger.info("PREDICTION")
    logger.info("=" * 80)
    logger.info(response)

    decision = extract_decision(response)
    conviction = extract_conviction_score(response)

    logger.info("\n" + "=" * 80)
    logger.info("PARSED RESULTS")
    logger.info("=" * 80)
    logger.info(f"Decision: {decision}")
    logger.info(f"Conviction Score: {conviction}")

    # Additional examples
    logger.info("\n\n" + "=" * 80)
    logger.info("ADDITIONAL EXAMPLES")
    logger.info("=" * 80)

    examples = [
        {
            "title": "Momentum Breakout",
            "setup": "XYZ at $52, breaking above 50-day MA ($50) on volume spike. RSI=65. MACD bullish crossover."
        },
        {
            "title": "Support Hold",
            "setup": "XYZ tested support at $44 twice in past week, held both times. Volume selling lighter on second test. Price recovered to $47."
        },
        {
            "title": "Bearish Divergence",
            "setup": "XYZ made new high at $56, but RSI lower than previous high (65 vs 68). MACD momentum weakening. Volume declining."
        }
    ]

    for i, example in enumerate(examples, 1):
        example_instruction = f"""{principle_context}

<trade_setup>
Topic: Technical Setup
Title: {example['title']}
Setup: {example['setup']}
</trade_setup>

What trading decision should be made?"""

        logger.info(f"\n[EXAMPLE {i}] {example['title']}")
        logger.info(f"Setup: {example['setup']}")

        response = predict(model, tokenizer, example_instruction, max_length=200)
        decision = extract_decision(response)
        conviction = extract_conviction_score(response)

        logger.info(f"Decision: {decision}")
        logger.info(f"Conviction: {conviction}")

    logger.info("\n✓ Inference examples complete")


# Example 2: Batch inference
def batch_prediction_example():
    """Show how to do batch inference on multiple setups."""
    logger.info("\n\n" + "=" * 80)
    logger.info("BATCH INFERENCE EXAMPLE")
    logger.info("=" * 80)

    model, tokenizer = load_model_inference(merge_adapter=True)
    principles_data = load_jsonl(STAGE_01_PATH)
    principle_context = format_principle_context(principles_data)

    setups = [
        "XYZ oversold on RSI(14)=22, price -18% from 50-day MA",
        "XYZ breaking above 50-day MA on strong volume",
        "XYZ momentum slowing, MACD bearish divergence",
    ]

    for i, setup in enumerate(setups, 1):
        instruction = f"""{principle_context}

<trade_setup>
Title: Setup {i}
Setup: {setup}
</trade_setup>

What trading decision should be made?"""

        response = predict(model, tokenizer, instruction, max_length=150)
        decision = extract_decision(response)

        logger.info(f"Setup {i}: {setup}")
        logger.info(f"  Decision: {decision}\n")


# Example 3: Custom setup
def custom_setup_inference():
    """Allow user to input custom trade setup."""
    logger.info("\n\n" + "=" * 80)
    logger.info("CUSTOM SETUP INFERENCE")
    logger.info("=" * 80)

    model, tokenizer = load_model_inference(merge_adapter=True)
    principles_data = load_jsonl(STAGE_01_PATH)
    principle_context = format_principle_context(principles_data)

    logger.info("Enter your trade setup (or 'quit' to exit):")
    while True:
        user_setup = input("\nSetup description: ").strip()

        if user_setup.lower() == "quit":
            break

        instruction = f"""{principle_context}

<trade_setup>
Setup: {user_setup}
</trade_setup>

What trading decision should be made?"""

        logger.info("Generating prediction...")
        response = predict(model, tokenizer, instruction)
        decision = extract_decision(response)
        conviction = extract_conviction_score(response)

        logger.info(f"\nDecision: {decision}")
        logger.info(f"Conviction: {conviction}")
        logger.info(f"Full response:\n{response}")


if __name__ == "__main__":
    setup_logging(Path(__file__).parent.parent / "model_training" / "logs", "inference.log")

    # Run examples
    example_prediction()
    batch_prediction_example()

    # Uncomment to enable interactive mode
    # custom_setup_inference()
