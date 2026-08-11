#!/usr/bin/env python3
"""Prune the per-tick path logs. Decision logs are never touched.

2026-08-11 -- why this exists
----------------------------
logs/ had reached 346 MB with no retention policy of any kind, 96.7% of it
per-tick heartbeat rows. Those rows matter while a trade is live -- trade
management reads them to recover MFE, MAE and giveback -- and matter very little
a fortnight later.

The split between what is prunable and what is not is deliberate and narrow:

    paper-path-*.jsonl      per-tick heartbeat     PRUNABLE
    everything else         decisions, proposals,  NEVER pruned
                            outcomes, prompts

Decision-bearing artifacts are the evidence base for strategy work and for v5/v6
training. Deleting them to save disk would be trading the entire point of the
system for a few hundred megabytes.

Usage
-----
    python tools/prune_path_logs.py                # dry run, shows what would go
    python tools/prune_path_logs.py --apply
    python tools/prune_path_logs.py --days 30 --apply
"""

from __future__ import annotations

import argparse
import re
from datetime import date, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
LOG_DIR = BACKEND / "logs"
ARCHIVE_DIR = BACKEND / "tick-archive"

DEFAULT_KEEP_DAYS = 14
PRUNABLE = ("paper-path",)
DATED = re.compile(r"-(\d{4}-\d{2}-\d{2})\.jsonl$")


def prunable_files(keep_days: int) -> list[tuple[Path, date]]:
    cutoff = date.today() - timedelta(days=keep_days)
    found: list[tuple[Path, date]] = []
    for directory in (LOG_DIR, ARCHIVE_DIR):
        if not directory.exists():
            continue
        for prefix in PRUNABLE:
            for path in directory.glob(f"{prefix}-*.jsonl"):
                match = DATED.search(path.name)
                if not match:
                    continue
                try:
                    day = date.fromisoformat(match.group(1))
                except ValueError:
                    continue
                if day < cutoff:
                    found.append((path, day))
    return sorted(found, key=lambda item: item[1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=DEFAULT_KEEP_DAYS,
                        help=f"keep this many days of path logs (default {DEFAULT_KEEP_DAYS})")
    parser.add_argument("--apply", action="store_true",
                        help="actually delete; without this it is a dry run")
    args = parser.parse_args()

    targets = prunable_files(args.days)
    if not targets:
        print(f"Nothing older than {args.days} days. Path logs are within retention.")
        return 0

    total = sum(p.stat().st_size for p, _ in targets)
    print(f"{'DELETING' if args.apply else 'WOULD DELETE'} "
          f"{len(targets)} path file(s), {total/1e6:.1f} MB:\n")
    for path, day in targets:
        print(f"  {day}  {path.stat().st_size/1e6:>7.1f} MB  {path.name}")
        if args.apply:
            try:
                path.unlink()
            except OSError as error:
                print(f"      could not remove: {error}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to delete.")
    print("\nDecision logs (proposals, executions, qwen-decisions) were not "
          "considered — they are never pruned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
