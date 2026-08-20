"""Consume closed-M5 samples in the isolated scientific Python environment."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from market_structure_providers import run_shadow_providers  # noqa: E402
from market_structure_shadow import (  # noqa: E402
    HORIZON_BARS, STATE_FILE, build_summary, realised_direction, _atomic_json,
)


def _load_rows(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    rows.append(json.loads(line))
                except (ValueError, TypeError):
                    continue
    return rows


def run(inputs: list[Path], output_dir: Path, state_file: Path = STATE_FILE,
        *, reprocess: bool = False) -> dict:
    samples = _load_rows(inputs)
    state = (json.loads(state_file.read_text(encoding="utf-8"))
             if state_file.exists() and not reprocess else {})
    seen = set(state.get("seen_sample_ids") or [])
    decisions = list(state.get("decisions") or [])
    resolutions = list(state.get("resolutions") or [])
    resolved_ids = {row["sample_id"] for row in resolutions}

    for sample in samples:
        if sample["sample_id"] in seen:
            continue
        external = run_shadow_providers(sample["bars"], sample["timeframe"], sample["atr"])
        decisions.append({
            "sample_id": sample["sample_id"],
            "closed_bar_time": sample["closed_bar_time"],
            "symbol": sample["symbol"],
            "origin_close": sample["origin_close"],
            "atr": sample["atr"],
            "native_direction": sample["native"]["direction"],
            "external": external,
            "execution_authority": False,
        })
        seen.add(sample["sample_id"])

    by_symbol = {}
    for decision in decisions:
        by_symbol.setdefault(decision["symbol"], []).append(decision)
    for symbol_rows in by_symbol.values():
        for index, decision in enumerate(symbol_rows):
            if decision["sample_id"] in resolved_ids or index + HORIZON_BARS >= len(symbol_rows):
                continue
            future = symbol_rows[index + HORIZON_BARS]
            realised = realised_direction(decision["origin_close"], future["origin_close"], decision["atr"])
            provider_directions = {
                row["provider"]: row["direction"]
                for row in decision["external"].get("provider_decisions", [])
            }
            resolutions.append({
                "sample_id": decision["sample_id"],
                "resolved_by_sample_id": future["sample_id"],
                "realised_direction": realised,
                "native_direction": decision["native_direction"],
                "external_direction": decision["external"]["direction"],
                "provider_directions": provider_directions,
                "execution_authority": False,
            })
            resolved_ids.add(decision["sample_id"])

    summary = build_summary(decisions, resolutions)
    state = {"seen_sample_ids": sorted(seen), "decisions": decisions[-5000:],
             "resolutions": resolutions[-5000:], "summary": summary}
    _atomic_json(state_file, state)
    output_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = output_dir / f"structure-shadow-decisions-{today}.jsonl"
    with out.open("w", encoding="utf-8") as handle:
        for row in decisions:
            handle.write(json.dumps({"record_type": "decision", **row}, separators=(",", ":")) + "\n")
        for row in resolutions:
            handle.write(json.dumps({"record_type": "resolution", **row}, separators=(",", ":")) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--output-dir", type=Path, default=BACKEND / "logs")
    parser.add_argument("--state-file", type=Path, default=STATE_FILE)
    parser.add_argument("--reprocess", action="store_true",
                        help="recompute all samples after provider/package changes")
    parser.add_argument("--watch-seconds", type=float, default=0,
                        help="poll continuously at this interval")
    args = parser.parse_args()
    first = True
    while True:
        inputs = args.inputs or sorted((BACKEND / "logs").glob("structure-shadow-input-*.jsonl"))
        print(json.dumps(run(inputs, args.output_dir, args.state_file,
                             reprocess=args.reprocess and first), indent=2), flush=True)
        first = False
        if args.watch_seconds <= 0:
            break
        time.sleep(max(5.0, args.watch_seconds))


if __name__ == "__main__":
    main()
