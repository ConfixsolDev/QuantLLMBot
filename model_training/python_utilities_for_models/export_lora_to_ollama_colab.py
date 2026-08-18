from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def fix_colab_torchao() -> None:
    """Colab preinstalls torchao 0.10; peft merge requires >=0.16 or none."""
    try:
        import importlib.metadata as md
        from packaging.version import Version

        if Version(md.version("torchao")) < Version("0.16.0"):
            print("Upgrading torchao for peft merge...", flush=True)
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "-q", "-U", "torchao>=0.16.0"]
            )
    except md.PackageNotFoundError:
        pass
    except Exception as exc:
        print(f"torchao check skipped: {exc}", flush=True)


def load_peft_model(base_model, adapter_dir: str):
    fix_colab_torchao()
    from peft import PeftModel

    return PeftModel.from_pretrained(base_model, adapter_dir)


def write_modelfile(path: Path, gguf_name: str) -> None:
    path.write_text(
        f"""FROM ./{gguf_name}
TEMPLATE \"\"\"{{{{ if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{ if .Prompt }}}}<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
<|im_start|>assistant
{{{{ end }}}}\"\"\"
PARAMETER stop <|im_end|>
PARAMETER temperature 0
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
SYSTEM \"\"\"You are a local XAUUSD market-structure research model. Return only valid JSON when asked for a decision. Use closed facts only; do not invent future price or live execution authority.\"\"\"
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--adapter-dir", required=True)
    # 2026-08-17: bumped v004 -> v005 (Phase 4 regime pack retrain).
    # See CURRICULUM_AND_DATA_PREP.md 3.0. v004 still names geometry/reason
    # conventions in CURRICULUM 1.1/1.2 -- same number, different scope.
    parser.add_argument("--work-dir", default="/content/drive/MyDrive/QuantLLMBot/ollama_export/qwen_trading_v005")
    parser.add_argument("--outfile-prefix", default="qwen-trading-v005")
    parser.add_argument("--quant", default="Q4_K_M")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument("--skip-llama-build", action="store_true")
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep merged_hf and f16 GGUF (~55 GB). Default: delete after quantize.",
    )
    args = parser.parse_args()

    adapter_dir = Path(args.adapter_dir)
    work_dir = Path(args.work_dir)
    merged_dir = work_dir / "merged_hf"
    llama_dir = work_dir / "llama.cpp"
    export_dir = work_dir / "ollama_model"
    f16_gguf = export_dir / f"{args.outfile_prefix}-f16.gguf"
    quant_gguf = export_dir / f"{args.outfile_prefix}-{args.quant.lower()}.gguf"

    work_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_merge:
        if merged_dir.exists():
            shutil.rmtree(merged_dir)
        print("Loading base model and adapter for merge...", flush=True)
        tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model,
            torch_dtype=torch.float16,
            device_map="auto",
            trust_remote_code=True,
        )
        model = load_peft_model(model, str(adapter_dir))
        model = model.merge_and_unload()
        model.save_pretrained(str(merged_dir), safe_serialization=True, max_shard_size="4GB")
        tokenizer.save_pretrained(str(merged_dir))
        metadata = {
            "base_model": args.base_model,
            "adapter_dir": str(adapter_dir),
            "merged_dir": str(merged_dir),
            "outfile_prefix": args.outfile_prefix,
            "quant": args.quant,
        }
        (work_dir / "export_manifest.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    if not llama_dir.exists():
        run(["git", "clone", "https://github.com/ggml-org/llama.cpp", str(llama_dir)])
    else:
        run(["git", "pull", "--ff-only"], cwd=llama_dir)

    if not args.skip_llama_build:
        run(["cmake", "-B", "build", "-DGGML_CUDA=ON"], cwd=llama_dir)
        run(["cmake", "--build", "build", "--config", "Release", "-j"], cwd=llama_dir)

    convert = llama_dir / "convert_hf_to_gguf.py"
    if not convert.exists():
        raise FileNotFoundError(f"llama.cpp converter not found: {convert}")

    run(["python", str(convert), str(merged_dir), "--outfile", str(f16_gguf), "--outtype", "f16"])

    quant_bin = llama_dir / "build" / "bin" / "llama-quantize"
    if not quant_bin.exists():
        quant_bin = llama_dir / "build" / "bin" / "Release" / "llama-quantize.exe"
    if not quant_bin.exists():
        raise FileNotFoundError("llama-quantize binary not found after build")

    run([str(quant_bin), str(f16_gguf), str(quant_gguf), args.quant])
    write_modelfile(export_dir / "Modelfile", quant_gguf.name)

    # Drop huge temp artifacts — only the quantized GGUF goes to Drive/PC.
    if not args.keep_intermediates:
        if f16_gguf.exists():
            f16_gb = f16_gguf.stat().st_size / (1024 ** 3)
            f16_gguf.unlink()
            print(f"Removed f16 GGUF ({f16_gb:.1f} GB)", flush=True)
        if merged_dir.exists():
            shutil.rmtree(merged_dir)
            print("Removed merged_hf/ (~28 GB)", flush=True)

    quant_gb = quant_gguf.stat().st_size / (1024 ** 3)
    print("\nDONE")
    print(f"GGUF (download this): {quant_gguf}  [{quant_gb:.2f} GB]")
    print(f"Modelfile: {export_dir / 'Modelfile'}")
    print("For Ollama: copy ONLY the .gguf + Modelfile into one folder.")


if __name__ == "__main__":
    main()

