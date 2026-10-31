"""Qwen command line (run from ``backend/``).

    python -m qwen ping                 is the server up, is the model there, its digest
    python -m qwen ask <prompt.json>    send a saved prompt ({"system": ..., "user": ...}) and
                                        print the raw answer and its latency
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import QwenClient, QwenError


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m qwen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping")
    a = sub.add_parser("ask")
    a.add_argument("prompt_file")
    args = ap.parse_args()
    client = QwenClient()
    try:
        if args.cmd == "ping":
            print(json.dumps(client.ping(), indent=2))
        else:
            p = json.loads(Path(args.prompt_file).read_text(encoding="utf-8"))
            r = client.ask(p["system"], p["user"])
            print(f"{r.latency_ms} ms, model {r.model} ({r.model_digest}), tokens in {r.prompt_tokens} out {r.output_tokens}")
            print(r.text)
    except QwenError as exc:
        sys.exit(f"Qwen not reachable: {exc}\nCheck backend/config/qwen.json (url, model) and that the server is running.")


if __name__ == "__main__":
    main()
