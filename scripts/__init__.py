"""
QuantLLMBot Phase 4 Training Pipeline

Modules:
  - config: Centralized configuration for all stages
  - utils: Utility functions for data loading, formatting, metrics
  - 00_quickstart: Entry point orchestrator
  - 01_preprocess: Preprocessing (load stages, create training pairs)
  - 02_finetune: QLoRA fine-tuning
  - 03_evaluate: Evaluation on holdout test set
"""

__version__ = "2.0"
__author__ = "QuantLLMBot Team"
