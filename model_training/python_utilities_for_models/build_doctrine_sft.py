#!/usr/bin/env python3
"""Build doctrine SFT JSONL from all store markdown + training bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
STORE = REPO_ROOT / "store"
# Prefer live store; optional topics map. No separate TRADING_KNOWLEDGE_BASE.md.
DEFAULT_BUNDLE = REPO_ROOT / "store" / "core_skill.md"
SYSTEM_PREFIX = (
    "You are a local XAUUSD market-structure research model. "
    "Return only valid JSON when asked for a decision. "
    "Use closed facts only; do not invent future price or live execution authority."
)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def chunk_markdown(text: str, max_chars: int = 12000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            break_at = text.rfind("\n\n", start, end)
            if break_at > start:
                end = break_at
        chunks.append(text[start:end].strip())
        start = end
    return chunks


def make_pair(instruction: str, response: str, source: str) -> dict:
    return {
        "source": source,
        "messages": [
            {"role": "system", "content": SYSTEM_PREFIX},
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": response},
        ],
    }


def doctrine_pairs() -> list[dict]:
    pairs: list[dict] = []
    core = read_text(STORE / "core_skill.md")
    sop = read_text(STORE / "sop.md")

    pairs.append(
        make_pair(
            "Summarize the XAUUSD market-structure doctrine you must follow "
            "when reading closed price data.",
            core,
            "store/core_skill.md",
        )
    )
    pairs.append(
        make_pair(
            "State the JSON output contracts and decision rules from the SOP "
            "for entry, management, and cache qualification.",
            sop,
            "store/sop.md",
        )
    )

    core_chunks = chunk_markdown(core)
    for i, chunk in enumerate(core_chunks, start=1):
        pairs.append(
            make_pair(
                f"Apply this market-structure doctrine section ({i}/{len(core_chunks)}). "
                "When asked for a decision, follow these rules and return valid JSON only.",
                chunk,
                f"store/core_skill.md#chunk-{i}",
            )
        )

    sop_chunks = chunk_markdown(sop)
    for i, chunk in enumerate(sop_chunks, start=1):
        pairs.append(
            make_pair(
                f"Follow this SOP contract section ({i}/{len(sop_chunks)}). "
                "Output must match the schemas described here.",
                chunk,
                f"store/sop.md#chunk-{i}",
            )
        )
    return pairs


def bundle_pairs(bundle_path: Path) -> list[dict]:
    if not bundle_path.exists():
        return []
    text = read_text(bundle_path)
    pairs: list[dict] = []
    for i, chunk in enumerate(chunk_markdown(text, max_chars=14000), start=1):
        pairs.append(
            make_pair(
                f"You are training on the QuantLLMBot trading knowledge bundle "
                f"(part {i}). Internalize this material for XAUUSD structure decisions.",
                chunk,
                f"{bundle_path.name}#chunk-{i}",
            )
        )
    return pairs


def principles_pairs() -> list[dict]:
    path = STORE / "principles_registry.json"
    if not path.exists():
        return []
    payload = json.loads(read_text(path))
    principles = payload.get("principles") or []
    pairs: list[dict] = []
    for item in principles:
        if item.get("status") in {"challenged", "rejected"}:
            continue
        principle = item.get("principle", "")
        condition = item.get("condition", "")
        action = item.get("action", "")
        body = (
            f"Principle: {principle}\n"
            f"Condition: {condition}\n"
            f"Action: {action}\n"
            f"Invalidation: {item.get('invalidation', '')}"
        )
        pairs.append(
            make_pair(
                "Convert this evidence-gated trading principle into an operational "
                "rule for XAUUSD structure decisions.",
                body,
                f"store/principles_registry.json#{item.get('id', 'unknown')}",
            )
        )
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build doctrine SFT JSONL from store.")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "model_training" / "datasets" / "doctrine_sft" / "v003_doctrine.jsonl",
    )
    parser.add_argument(
        "--bundle",
        type=Path,
        default=DEFAULT_BUNDLE,
        help="TRADING_KNOWLEDGE_BASE.md or corpus snapshot",
    )
    parser.add_argument("--skip-bundle", action="store_true")
    parser.add_argument("--skip-principles", action="store_true")
    args = parser.parse_args()

    pairs: list[dict] = []
    pairs.extend(doctrine_pairs())
    if not args.skip_principles:
        pairs.extend(principles_pairs())
    if not args.skip_bundle:
        pairs.extend(bundle_pairs(args.bundle))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for row in pairs:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output": str(args.out),
        "pair_count": len(pairs),
        "sources": sorted({p["source"] for p in pairs}),
        "store_files": [
            "core_skill.md",
            "sop.md",
            "principles_registry.json" if not args.skip_principles else None,
        ],
        "bundle": None if args.skip_bundle else str(args.bundle),
    }
    manifest["store_files"] = [x for x in manifest["store_files"] if x]
    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {len(pairs)} pairs -> {args.out}")
    print(f"Manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
