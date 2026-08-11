"""
QuantLLMBot Phase 4 Configuration
Central location for all paths, model settings, and training hyperparameters.
"""

from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import os

# ============================================================================
# PATHS
# ============================================================================

# Repo root = parent of scripts/. Override with QUANTLLM_ROOT (e.g. on Colab:
# os.environ["QUANTLLM_ROOT"] = "/content/QuantLLMBot").
PROJECT_ROOT = Path(os.environ.get("QUANTLLM_ROOT", Path(__file__).resolve().parents[1]))
KNOWLEDGE_DIR = PROJECT_ROOT / "model_training" / "knowledge"
OUTPUT_DIR = PROJECT_ROOT / "model_training" / "outputs"
CHECKPOINT_DIR = PROJECT_ROOT / "model_training" / "checkpoints"
LOGS_DIR = PROJECT_ROOT / "model_training" / "logs"

# Data files
STAGE_01_PATH = KNOWLEDGE_DIR / "stage_01_principle_foundation.jsonl"
STAGE_02_PATH = KNOWLEDGE_DIR / "stage_02_structured_data.jsonl"
STAGE_03_PATH = KNOWLEDGE_DIR / "stage_03_detector_definitions.jsonl"
STAGE_04_PATH = KNOWLEDGE_DIR / "stage_04_decision_contract.jsonl"

# Outputs
PROCESSED_DATA_PATH = OUTPUT_DIR / "processed_training_data.jsonl"
LORA_WEIGHTS_DIR = OUTPUT_DIR / "lora_weights"
EVAL_RESULTS_PATH = OUTPUT_DIR / "evaluation_results.json"

# Create directories if they don't exist
for directory in [OUTPUT_DIR, CHECKPOINT_DIR, LOGS_DIR, LORA_WEIGHTS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

@dataclass
class ModelConfig:
    base_model: str = "Qwen/Qwen2.5-14B-Instruct"
    model_max_length: int = 4096
    trust_remote_code: bool = True
    device_map: str = "auto"
    torch_dtype: str = "bfloat16"  # or "float16"


@dataclass
class QuantizationConfig:
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = "nf4"


@dataclass
class LoRAConfig:
    r: int = 16
    lora_alpha: int = 32
    target_modules: list = None
    lora_dropout: float = 0.05
    bias: str = "none"
    task_type: str = "CAUSAL_LM"

    def __post_init__(self):
        if self.target_modules is None:
            self.target_modules = [
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ]


@dataclass
class TrainingConfig:
    # Data
    max_seq_length: int = 4096
    preprocessing_num_workers: int = 4

    # Batch and learning
    # 14B + 4096-token sequences OOMs on A100 40GB at batch 2 — use 1x8
    per_device_train_batch_size: int = 1
    per_device_eval_batch_size: int = 2
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    weight_decay: float = 0.01
    max_grad_norm: float = 1.0

    # Epochs and steps (~45 steps at 3 epochs; warmup must stay below that)
    num_train_epochs: int = 5
    warmup_steps: int = 5

    # Checkpointing
    save_steps: int = 50
    eval_steps: int = 50
    save_total_limit: int = 3

    # Logging
    logging_steps: int = 10
    log_model: bool = False

    # Misc
    seed: int = 42
    fp16: bool = False  # Use bf16 instead for A100
    bf16: bool = True
    optim: str = "paged_adamw_32bit"
    gradient_checkpointing: bool = True


# ============================================================================
# TRAINING PIPELINE SETTINGS
# ============================================================================

@dataclass
class PipelineConfig:
    # Preprocessing — train / skill holdout split, by ROW INDEX into the aligned
    # stage_02 + stage_04 files.
    #
    # 2026-08-10: bumped 379/389 -> 498/508 after three packs were appended
    # (M30 anchors, frame-incoherence skips, live-outcome replays). These bounds
    # are absolute indices, not proportions, so leaving them at 389 would have
    # silently dropped every appended row from BOTH training and holdout -- the
    # new material sits at the end of the file. Re-check these after any
    # append_*.py run; audit_training_dataset.py prints the current totals.
    training_lines_start: int = 0
    training_lines_end: int = 702
    test_lines_start: int = 702
    test_lines_end: int = 712

    # Evaluation metrics
    eval_metrics: list = None

    # W&B logging (opt-in: requires `wandb login` first, otherwise training blocks)
    use_wandb: bool = False
    wandb_project: str = "quantllmbot-phase4"
    wandb_entity: Optional[str] = None  # Set to your W&B username if desired

    def __post_init__(self):
        if self.eval_metrics is None:
            self.eval_metrics = [
                "exact_match_decision",
                "decision_agreement",
                "conviction_score_mae",
                "evidence_label_accuracy"
            ]


# ============================================================================
# INSTANTIATE CONFIGS
# ============================================================================

model_config = ModelConfig()
quant_config = QuantizationConfig()
lora_config = LoRAConfig()
training_config = TrainingConfig()
pipeline_config = PipelineConfig()


# ============================================================================
# HELPER: EFFECTIVE BATCH SIZE
# ============================================================================

def get_effective_batch_size(
    per_device_batch_size: int = training_config.per_device_train_batch_size,
    gradient_accumulation: int = training_config.gradient_accumulation_steps,
    num_devices: int = 1
) -> int:
    """
    Compute effective batch size across all devices and accumulation steps.
    effective_batch_size = per_device_batch_size * num_devices * gradient_accumulation_steps
    """
    return per_device_batch_size * num_devices * gradient_accumulation


if __name__ == "__main__":
    print("QuantLLMBot Phase 4 Configuration")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Knowledge Dir: {KNOWLEDGE_DIR}")
    print(f"Output Dir: {OUTPUT_DIR}")
    print(f"\nModel: {model_config.base_model}")
    print(f"LoRA Config: r={lora_config.r}, alpha={lora_config.lora_alpha}")
    print(f"Effective Batch Size: {get_effective_batch_size()}")
    print(f"Training Data: Lines {pipeline_config.training_lines_start}-{pipeline_config.training_lines_end}")
    print(f"Test Data: Lines {pipeline_config.test_lines_start}-{pipeline_config.test_lines_end}")
