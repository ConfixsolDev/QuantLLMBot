#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Preprocessing
Load stages 01/02/04/05, including exact deployed-contract response pairs.
Usage: python 01_preprocess.py
"""

import sys
import logging
from pathlib import Path

# Add parent dir to path so we can import config and utils
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STAGE_01_PATH, STAGE_02_PATH, STAGE_04_PATH, STAGE_05_PATH, PROCESSED_DATA_PATH,
    pipeline_config
)
from utils import (
    load_jsonl, save_jsonl, prepare_training_data, prepare_live_contract_data, setup_logging
)

logger = logging.getLogger(__name__)


def main():
    """Main preprocessing pipeline."""
    logger.info("=" * 80)
    logger.info("QuantLLMBot Phase 4: PREPROCESSING")
    logger.info("=" * 80)

    # ========================================================================
    # STEP 1: Verify data files exist
    # ========================================================================
    logger.info("\n[STEP 1] Verifying data files...")
    for path in [STAGE_01_PATH, STAGE_02_PATH, STAGE_04_PATH, STAGE_05_PATH]:
        if not path.exists():
            logger.error(f"Missing required data file: {path}")
            sys.exit(1)
        logger.info(f"  OK Found: {path.name}")

    # ========================================================================
    # STEP 2: Load all stages
    # ========================================================================
    logger.info("\n[STEP 2] Loading data stages...")
    logger.info(f"  Loading stage 01 (principles) from {STAGE_01_PATH.name}...")
    stage_01_data = load_jsonl(STAGE_01_PATH)

    logger.info(f"  Loading stage 02 (examples) from {STAGE_02_PATH.name}...")
    stage_02_data = load_jsonl(STAGE_02_PATH)

    logger.info(f"  Loading stage 04 (contracts) from {STAGE_04_PATH.name}...")
    stage_04_data = load_jsonl(STAGE_04_PATH)
    logger.info(f"  Loading stage 05 (live contracts) from {STAGE_05_PATH.name}...")
    stage_05_data = load_jsonl(STAGE_05_PATH)

    # ========================================================================
    # STEP 3: Validate data alignment
    # ========================================================================
    logger.info("\n[STEP 3] Validating data integrity...")
    if len(stage_02_data) != len(stage_04_data):
        logger.warning(
            f"Stage 02 has {len(stage_02_data)} records but stage 04 has {len(stage_04_data)}. "
            f"Will use min({len(stage_02_data)}, {len(stage_04_data)})"
        )
    aligned_count = min(len(stage_02_data), len(stage_04_data))
    logger.info(f"  OK Aligned {aligned_count} records")
    if len(stage_05_data) != aligned_count:
        logger.error(
            f"Stage 05 has {len(stage_05_data)} records; expected one per aligned stage 02/04 row ({aligned_count})."
        )
        sys.exit(1)

    # ========================================================================
    # STEP 4: Create instruction-response pairs (training data only)
    # ========================================================================
    logger.info("\n[STEP 4] Creating instruction-response pairs...")
    logger.info(
        f"  Using lines {pipeline_config.training_lines_start}-{pipeline_config.training_lines_end-1} "
        f"(Bucket A/B training data only)"
    )

    judgement_pairs = prepare_training_data(
        stage_02_data,
        stage_01_data,
        stage_04_data,
        start_idx=pipeline_config.training_lines_start,
        end_idx=pipeline_config.training_lines_end
    )
    live_contract_pairs = prepare_live_contract_data(
        stage_05_data,
        start_idx=pipeline_config.training_lines_start,
        end_idx=pipeline_config.training_lines_end,
    )
    training_pairs = judgement_pairs + live_contract_pairs

    if not training_pairs:
        logger.error("No training pairs created!")
        sys.exit(1)

    # ========================================================================
    # STEP 5: Save processed data
    # ========================================================================
    logger.info("\n[STEP 5] Saving processed data...")
    PROCESSED_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_jsonl(training_pairs, PROCESSED_DATA_PATH)

    # ========================================================================
    # STEP 6: Summary
    # ========================================================================
    logger.info("\n" + "=" * 80)
    logger.info("PREPROCESSING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Input:  {len(stage_02_data)} total examples in stage 02")
    logger.info(
        f"Output: {len(training_pairs)} pairs "
        f"({len(judgement_pairs)} judgement + {len(live_contract_pairs)} exact live-contract)"
    )
    logger.info(f"Saved to: {PROCESSED_DATA_PATH}")
    logger.info(f"Each pair includes: instruction, response, example_id, topic, bucket")
    logger.info("\nNext step: Run 02_finetune.py to begin training")


if __name__ == "__main__":
    setup_logging(Path(__file__).parent.parent / "model_training" / "logs")
    main()
