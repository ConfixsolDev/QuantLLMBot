"""LLM command line (run from ``backend/``, with the model server running — Start-LLM.bat).

    python -m llm ping                       server up? which model file? settings in use
    python -m llm ask <prompt.json>          send one saved prompt ({"system", "user"}) and print
                                             the raw answer, its latency and token counts
    python -m llm bench --dataset <dir> [--n 30] [--out results.jsonl]
        run N prompts of a strategy dataset (python -m strategy.dataset) through the
        model, exactly as live (same system message, same JSON-schema constraint,
        same contract check), then score against the hidden answer key:
          - speed: latency p50 / p95, tokens in / out
          - discipline: valid answers %, invalid reasons
          - judgement: take rate; R of the taken candidates vs taking all; how often
            the level of a taken candidate HELD vs the base rate
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

from .client import LLMClient, LLMError
from .contract import answer_schema, check


def _bench(client: LLMClient, ds: Path, n: int, out: Path | None, min_conf: int) -> dict:
    system = (ds / "system.txt").read_text(encoding="utf-8")
    prompts = [json.loads(x) for x in (ds / "prompts.jsonl").read_text(encoding="utf-8").splitlines()]
    labels = {json.loads(x)["id"]: json.loads(x)["candidates"]
              for x in (ds / "labels.jsonl").read_text(encoding="utf-8").splitlines()}
    prompts = [p for p in prompts if p["id"] in labels]
    sample = random.Random(7).sample(prompts, min(n, len(prompts)))
    rows = []
    for i, p in enumerate(sample, 1):
        pr = SimpleNamespace(candidate_map=p["candidate_map"], evidence_map=p["evidence_map"])
        try:
            r = client.ask(system, p["user"], answer_schema(pr))
            v = check(r.text, pr, min_conf)
            row = {"id": p["id"], "action": v.action, "label": v.label, "confidence": v.confidence,
                   "errors": list(v.errors), "why": v.why, "latency_ms": r.latency_ms,
                   "prompt_tokens": r.prompt_tokens, "output_tokens": r.output_tokens, "text": r.text}
        except LLMError as exc:
            row = {"id": p["id"], "action": "invalid", "label": None, "errors": [str(exc)], "latency_ms": None}
        lab = labels[p["id"]]
        row["all_r"] = [c["r"] for c in lab.values()]
        row["held"] = [c["level_outcome"] == "held" for c in lab.values()]
        if row["action"] == "take" and row["label"] in lab:
            row["taken_r"] = lab[row["label"]]["r"]
            row["taken_held"] = lab[row["label"]]["level_outcome"] == "held"
        rows.append(row)
        print(f"  {i:>3}/{len(sample)} {row['action']:<7} {row.get('label') or '':<3} "
              f"conf {row.get('confidence', 0):>3}  {row.get('latency_ms') or '-':>6} ms  "
              f"{(row.get('why') or '; '.join(row['errors']))[:70]}", flush=True)
    if out:
        out.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    lat = sorted(r["latency_ms"] for r in rows if r.get("latency_ms"))
    takes = [r for r in rows if r["action"] == "take"]
    all_r = [x for r in rows for x in r["all_r"]]
    base_held = [x for r in rows for x in r["held"]]
    mean = lambda v: round(statistics.mean(v), 3) if v else None      # noqa: E731
    return {
        "prompts": len(rows),
        "latency_ms": {"p50": lat[len(lat) // 2] if lat else None,
                       "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))] if lat else None},
        "tokens": {"in_avg": mean([r["prompt_tokens"] for r in rows if r.get("prompt_tokens")]),
                   "out_avg": mean([r["output_tokens"] for r in rows if r.get("output_tokens")])},
        "valid_pct": round(100 * sum(r["action"] != "invalid" for r in rows) / max(1, len(rows)), 1),
        "invalid_reasons": sorted({e for r in rows if r["action"] == "invalid" for e in r["errors"]})[:5],
        "take_pct": round(100 * len(takes) / max(1, len(rows)), 1),
        "avg_r_taken": mean([r["taken_r"] for r in takes if "taken_r" in r]),
        "avg_r_take_all": mean(all_r),
        "held_pct_taken": round(100 * mean([float(r["taken_held"]) for r in takes if "taken_r" in r]), 1)
        if takes else None,
        "held_pct_base": round(100 * mean([float(x) for x in base_held]), 1) if base_held else None,
        "note": "a small sample is an anecdote: use --n 100+ before concluding anything about judgement",
    }


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m llm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    a = sub.add_parser("ask")
    a.add_argument("prompt_file")
    b = sub.add_parser("bench")
    b.add_argument("--dataset", required=True)
    b.add_argument("--n", type=int, default=30)
    b.add_argument("--out")
    b.add_argument("--min-confidence", type=int, default=51)
    args = ap.parse_args()
    client = LLMClient()
    try:
        if args.cmd == "ping":
            print(json.dumps(client.ping(), indent=2))
        elif args.cmd == "ask":
            p = json.loads(Path(args.prompt_file).read_text(encoding="utf-8"))
            r = client.ask(p["system"], p["user"])
            print(f"{r.latency_ms} ms, {r.model_digest}, tokens in {r.prompt_tokens} out {r.output_tokens}")
            if r.reasoning:
                print(f"(reasoning: {len(r.reasoning)} characters)")
            print(r.text)
        else:
            res = _bench(client, Path(args.dataset), args.n, Path(args.out) if args.out else None,
                         args.min_confidence)
            print(json.dumps(res, indent=2))
    except LLMError as exc:
        sys.exit(f"Model server not reachable: {exc}\n"
                 "Start it with Start-LLM.bat and check backend/config/llm.json (url).")


if __name__ == "__main__":
    main()
