#!/usr/bin/env python3
"""Build QuantLLMBot_training.zip for Colab (Linux-safe forward slashes).

Lives in model_training/python_utilities_for_models/ — model/agent utility.
System Colab train scripts stay in repo scripts/.
"""

import zipfile
from pathlib import Path

# utilities → model_training → repo
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ZIP = PROJECT_ROOT / "QuantLLMBot_training.zip"

FILES = [
    "scripts/__init__.py",
    "scripts/config.py",
    "scripts/utils.py",
    "scripts/01_preprocess.py",
    "scripts/02_finetune.py",
    "scripts/03_evaluate.py",
    "scripts/00_quickstart.py",
    "scripts/inference_example.py",
    "scripts/pre_training_checklist.py",
    "scripts/requirements.txt",
    "scripts/Train_Qwen14B_Colab.ipynb",
    "model_training/knowledge/stage_01_principle_foundation.jsonl",
    "model_training/knowledge/stage_02_structured_data.jsonl",
    "model_training/knowledge/stage_03_detector_definitions.jsonl",
    "model_training/knowledge/stage_04_decision_contract.jsonl",
    # Minimal live-inference contract v3.0. Qwen returns seven decision fields;
    # runtime supplies epochs and expands one approved geometry_row_id.
    "model_training/knowledge/stage_05_live_contract.jsonl",
    "model_training/outputs/processed_training_data.jsonl",
    "model_training/CURRICULUM_AND_DATA_PREP.md",
    "model_training/python_utilities_for_models/build_stage05_live_contract.py",
    "model_training/python_utilities_for_models/audit_training_dataset.py",
    "model_training/python_utilities_for_models/export_lora_to_ollama_colab.py",
]

MARKER = "topic-scoped per example"

print("Creating QuantLLMBot_training.zip")
print("=" * 60)

if OUTPUT_ZIP.exists():
    OUTPUT_ZIP.unlink()
    print(f"  removed old package: {OUTPUT_ZIP}")

missing = []
with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in FILES:
        src = PROJECT_ROOT / rel
        if not src.exists():
            missing.append(rel)
            print(f"  MISSING  {rel}")
            continue
        # Keep Colab-relative path for export script under model_training/
        arc = rel.replace("\\", "/")
        if arc.endswith("export_lora_to_ollama_colab.py"):
            arc = "model_training/export_lora_to_ollama_colab.py"
        zf.write(src, arc)
        print(f"  + {arc}")

if missing:
    raise SystemExit(f"\nAbort: {len(missing)} file(s) missing")

utils_text = (PROJECT_ROOT / "scripts/utils.py").read_text(encoding="utf-8")
if "topic: Optional[str]" not in utils_text:
    raise SystemExit("utils.py missing topic-scoped principle fix")

stage05_text = (PROJECT_ROOT / "model_training/knowledge/stage_05_live_contract.jsonl").read_text(encoding="utf-8")
if '"contract_version": "qwen_cached_entry:3.0"' not in stage05_text:
    raise SystemExit("stage_05 is not the minimal qwen_cached_entry:3.0 contract")

size_kb = OUTPUT_ZIP.stat().st_size / 1024
print("=" * 60)
print(f"OK: {OUTPUT_ZIP}")
print(f"Size: {size_kb:.1f} KB")
print(f"Fix verified: topic-scoped principles ({MARKER})")
print("Contract verified: qwen_cached_entry:3.0 minimal output")
