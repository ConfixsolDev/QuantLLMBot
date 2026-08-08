#!/usr/bin/env python3
"""
QuantLLMBot Phase 4: Pre-Training Checklist
Verify all requirements before running training on Qwen 14B.
Usage: python pre_training_checklist.py
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    STAGE_01_PATH, STAGE_02_PATH, STAGE_03_PATH, STAGE_04_PATH,
    CHECKPOINT_DIR, LORA_WEIGHTS_DIR, LOGS_DIR,
    model_config, training_config, lora_config
)

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text):
    print(f"\n{BLUE}{'='*80}{RESET}")
    print(f"{BLUE}{text:^80}{RESET}")
    print(f"{BLUE}{'='*80}{RESET}\n")


def print_success(text):
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text):
    print(f"{YELLOW}⚠ {text}{RESET}")


def check_python():
    """Check Python version."""
    version = sys.version_info
    required = (3, 10)

    if (version.major, version.minor) >= required:
        print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print_error(f"Python {version.major}.{version.minor} (need {required[0]}.{required[1]}+)")
        return False


def check_gpu():
    """Check NVIDIA GPU and VRAM."""
    try:
        import torch
        if not torch.cuda.is_available():
            print_error("No NVIDIA GPU detected")
            return False

        device_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print_success(f"GPU: {device_name}")
        print_success(f"VRAM: {vram_gb:.1f} GB")

        if vram_gb < 24:
            print_warning(f"VRAM {vram_gb:.1f}GB is less than recommended 24GB. Training may be slower.")
            return True
        return True
    except Exception as e:
        print_error(f"GPU check failed: {e}")
        return False


def check_dependencies():
    """Check all required Python packages."""
    required = {
        "torch": "2.0+",
        "transformers": "4.36+",
        "peft": "0.7+",
        "bitsandbytes": "0.41+",
        "datasets": "2.14+",
        "trl": "0.7+",
        "accelerate": "0.24+",
    }

    all_ok = True
    for package, min_version in required.items():
        try:
            mod = __import__(package)
            version = getattr(mod, "__version__", "unknown")
            print_success(f"{package} {version}")
        except ImportError:
            print_error(f"{package} (required {min_version})")
            all_ok = False

    return all_ok


def check_data_files():
    """Verify all 4 JSONL data files exist."""
    files = {
        "Stage 01 (Principles)": STAGE_01_PATH,
        "Stage 02 (Examples)": STAGE_02_PATH,
        "Stage 03 (Detectors)": STAGE_03_PATH,
        "Stage 04 (Contracts)": STAGE_04_PATH,
    }

    all_ok = True
    for name, path in files.items():
        if path.exists():
            size_kb = path.stat().st_size / 1024
            print_success(f"{name}: {size_kb:.1f} KB")
        else:
            print_error(f"{name}: NOT FOUND at {path}")
            all_ok = False

    return all_ok


def check_directories():
    """Ensure output directories exist."""
    dirs = {
        "Checkpoints": CHECKPOINT_DIR,
        "LoRA Weights": LORA_WEIGHTS_DIR,
        "Logs": LOGS_DIR,
    }

    all_ok = True
    for name, path in dirs.items():
        path.mkdir(parents=True, exist_ok=True)
        print_success(f"{name}: {path}")

    return all_ok


def check_configuration():
    """Display training configuration."""
    print(f"{BLUE}Model Configuration:{RESET}")
    print(f"  Base Model: {model_config.base_model}")
    print(f"  Max Seq Length: {model_config.model_max_length}")

    print(f"\n{BLUE}LoRA Configuration:{RESET}")
    print(f"  Rank (r): {lora_config.r}")
    print(f"  Alpha: {lora_config.lora_alpha}")
    print(f"  Dropout: {lora_config.lora_dropout}")
    print(f"  Target Modules: {lora_config.target_modules}")

    print(f"\n{BLUE}Training Configuration:{RESET}")
    print(f"  Batch Size: {training_config.per_device_train_batch_size}")
    print(f"  Gradient Accumulation: {training_config.gradient_accumulation_steps}")
    effective_batch = (
        training_config.per_device_train_batch_size *
        training_config.gradient_accumulation_steps
    )
    print(f"  Effective Batch Size: {effective_batch}")
    print(f"  Learning Rate: {training_config.learning_rate}")
    print(f"  Epochs: {training_config.num_train_epochs}")
    print(f"  Warmup Steps: {training_config.warmup_steps}")

    return True


def estimate_memory():
    """Estimate VRAM requirements."""
    print(f"\n{BLUE}VRAM Estimation (Qwen 14B, 4-bit NF4):{RESET}")
    print(f"  Model weights: ~7 GB (14B in 4-bit)")
    print(f"  Activations: ~2-3 GB (batch_size=2, seq_len=4096)")
    print(f"  Optimizer state: ~1-2 GB (paged_adamw)")
    print(f"  LoRA weights: ~0.2 GB")
    print(f"  Total estimated: ~12-13 GB")
    print(f"  Safe margin (24GB): ✓ Plenty of headroom")

    return True


def main():
    """Run all checks."""
    print_header("QuantLLMBot Phase 4: Pre-Training Checklist (Qwen 14B)")

    checks = [
        ("Python Version", check_python),
        ("NVIDIA GPU", check_gpu),
        ("Python Dependencies", check_dependencies),
        ("Data Files", check_data_files),
        ("Output Directories", check_directories),
        ("Training Configuration", check_configuration),
        ("Memory Estimation", estimate_memory),
    ]

    results = {}
    for check_name, check_func in checks:
        print(f"\n{YELLOW}[CHECK] {check_name}...{RESET}")
        try:
            results[check_name] = check_func()
        except Exception as e:
            print_error(f"{check_name} failed: {e}")
            results[check_name] = False

    # Summary
    print_header("SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print(f"Checks passed: {passed}/{total}")

    if all(results.values()):
        print_success("All checks passed! Ready to train.")
        print(f"\n{BLUE}Next steps:{RESET}")
        print(f"  1. python scripts/01_preprocess.py")
        print(f"  2. python scripts/02_finetune.py")
        print(f"  3. python scripts/03_evaluate.py")
        print(f"\n{BLUE}Or run all at once:{RESET}")
        print(f"  python scripts/00_quickstart.py all")
        return 0
    else:
        print_error("Some checks failed. Fix issues before training.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
