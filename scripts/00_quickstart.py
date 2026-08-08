#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Quick Start
Run this to verify environment setup and execute the full pipeline.
Usage: python 00_quickstart.py [preprocess|finetune|evaluate|all]
"""

import sys
import subprocess
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    PROJECT_ROOT, STAGE_01_PATH, STAGE_02_PATH, STAGE_04_PATH,
    PROCESSED_DATA_PATH, LORA_WEIGHTS_DIR, EVAL_RESULTS_PATH
)
from utils import setup_logging

logger = logging.getLogger(__name__)


def check_environment():
    """Verify Python environment and required packages."""
    logger.info("Checking environment setup...")

    try:
        import torch
        logger.info(f"  ✓ PyTorch {torch.__version__}")
        logger.info(f"    CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"    GPU: {torch.cuda.get_device_name(0)}")

        import transformers
        logger.info(f"  ✓ Transformers {transformers.__version__}")

        import peft
        logger.info(f"  ✓ PEFT {peft.__version__}")

        import datasets
        logger.info(f"  ✓ Datasets {datasets.__version__}")

        import pandas
        logger.info(f"  ✓ Pandas {pandas.__version__}")

        import trl
        logger.info(f"  ✓ TRL {trl.__version__}")

    except ImportError as e:
        logger.error(f"  ✗ Missing dependency: {e}")
        logger.error("Run: pip install -r requirements.txt")
        return False

    return True


def check_data_files():
    """Verify all required data files exist."""
    logger.info("\nVerifying data files...")

    files = {
        "Stage 01 (Principles)": STAGE_01_PATH,
        "Stage 02 (Examples)": STAGE_02_PATH,
        "Stage 04 (Contracts)": STAGE_04_PATH,
    }

    all_exist = True
    for name, path in files.items():
        if path.exists():
            size_kb = path.stat().st_size / 1024
            logger.info(f"  ✓ {name}: {path.name} ({size_kb:.1f} KB)")
        else:
            logger.error(f"  ✗ {name} NOT FOUND: {path}")
            all_exist = False

    return all_exist


def run_preprocessing():
    """Execute preprocessing step."""
    logger.info("\n" + "=" * 80)
    logger.info("Running: PREPROCESSING (01_preprocess.py)")
    logger.info("=" * 80)

    result = subprocess.run(
        [sys.executable, "01_preprocess.py"],
        cwd=Path(__file__).parent,
        capture_output=False
    )

    if result.returncode != 0:
        logger.error("Preprocessing failed!")
        return False

    if not PROCESSED_DATA_PATH.exists():
        logger.error(f"Expected output not found: {PROCESSED_DATA_PATH}")
        return False

    logger.info(f"✓ Preprocessing complete: {PROCESSED_DATA_PATH}")
    return True


def run_finetuning():
    """Execute fine-tuning step."""
    logger.info("\n" + "=" * 80)
    logger.info("Running: FINE-TUNING (02_finetune.py)")
    logger.info("=" * 80)

    result = subprocess.run(
        [sys.executable, "02_finetune.py"],
        cwd=Path(__file__).parent,
        capture_output=False
    )

    if result.returncode != 0:
        logger.error("Fine-tuning failed!")
        return False

    if not (LORA_WEIGHTS_DIR / "adapter_model.bin").exists():
        logger.error(f"Expected output not found: {LORA_WEIGHTS_DIR}/adapter_model.bin")
        return False

    logger.info(f"✓ Fine-tuning complete: {LORA_WEIGHTS_DIR}")
    return True


def run_evaluation():
    """Execute evaluation step."""
    logger.info("\n" + "=" * 80)
    logger.info("Running: EVALUATION (03_evaluate.py)")
    logger.info("=" * 80)

    result = subprocess.run(
        [sys.executable, "03_evaluate.py"],
        cwd=Path(__file__).parent,
        capture_output=False
    )

    if result.returncode != 0:
        logger.error("Evaluation failed!")
        return False

    if not EVAL_RESULTS_PATH.exists():
        logger.error(f"Expected output not found: {EVAL_RESULTS_PATH}")
        return False

    logger.info(f"✓ Evaluation complete: {EVAL_RESULTS_PATH}")
    return True


def main():
    """Main quick-start flow."""
    setup_logging(Path(__file__).parent.parent / "model_training" / "logs", "quickstart.log")

    logger.info("=" * 80)
    logger.info("QuantLLMBot Phase 4: QUICK START")
    logger.info("=" * 80)

    # Parse command
    stage = "all"
    if len(sys.argv) > 1:
        stage = sys.argv[1].lower()

    if stage not in ["preprocess", "finetune", "evaluate", "all"]:
        logger.error(f"Invalid stage: {stage}")
        logger.error("Usage: python 00_quickstart.py [preprocess|finetune|evaluate|all]")
        sys.exit(1)

    # Check environment
    logger.info("\n[CHECK 1] Verifying environment...")
    if not check_environment():
        sys.exit(1)

    # Check data files
    logger.info("\n[CHECK 2] Verifying data files...")
    if not check_data_files():
        sys.exit(1)

    logger.info("\n✓ All checks passed!")

    # Run pipeline stages
    success = True

    if stage in ["preprocess", "all"]:
        if not run_preprocessing():
            success = False
            if stage == "preprocess":
                sys.exit(1)

    if stage in ["finetune", "all"] and success:
        if not run_finetuning():
            success = False
            if stage == "finetune":
                sys.exit(1)

    if stage in ["evaluate", "all"] and success:
        if not run_evaluation():
            success = False
            if stage == "evaluate":
                sys.exit(1)

    # Final summary
    logger.info("\n" + "=" * 80)
    if success:
        logger.info("✓ PIPELINE COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"Outputs:")
        logger.info(f"  - Processed training data: {PROCESSED_DATA_PATH}")
        logger.info(f"  - LoRA weights: {LORA_WEIGHTS_DIR}")
        logger.info(f"  - Evaluation results: {EVAL_RESULTS_PATH}")
        logger.info(f"\nNext steps:")
        logger.info(f"  1. Review evaluation results in: {EVAL_RESULTS_PATH}")
        logger.info(f"  2. For inference, load model + LoRA: model + PeftModel.from_pretrained(lora_path)")
        logger.info(f"  3. Merge: model.merge_and_unload() for single-file deployment")
    else:
        logger.error("✗ PIPELINE FAILED")
        logger.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
