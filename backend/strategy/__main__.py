"""Strategy command line (run from ``backend/``).

    python -m strategy list                          strategy files in strategy/library
    python -m strategy show <id> [--version N]       rules, doctrine and hash of one strategy
    python -m strategy preview --m1 <files/folders> [--date YYYY-MM-DD] [--n 1] [--save prompt.json]
        replay the bars, and print the first N prompts the model WOULD receive on that day
        (system + user, with their size against the 6 KB budget). --save writes the
        first one as {"system", "user"} for ``python -m llm ask prompt.json``.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from . import available, load  # noqa: E402
from . import template  # noqa: E402
from .runner import make_runner  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m strategy")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    sh.add_argument("--version", type=int)
    pv = sub.add_parser("preview")
    pv.add_argument("--m1", nargs="+", required=True)
    pv.add_argument("--id", default="m1_probe_failure_scalp")
    pv.add_argument("--date")
    pv.add_argument("--n", type=int, default=1)
    pv.add_argument("--save")
    a = ap.parse_args()
    if a.cmd == "list":
        print("\n".join(available()))
        return
    if a.cmd == "show":
        s = load(a.id, a.version)
        print(f"{s.ref}  {s.name}\nrules: {json.dumps(s.rules, indent=1)}\nprompt: {s.prompt}\n")
        print(template.system_message(s))
        return
    from structure_engine.config import load_config
    from structure_engine.engine import StructureEngine
    from structure_engine.feeds import RecordedFeed
    s = load(a.id)
    engine = StructureEngine(load_config())
    runner = make_runner(s, engine)
    day = calendar.timegm(time.strptime(a.date, "%Y-%m-%d")) if a.date else None
    shown = 0
    for bar in RecordedFeed(a.m1):
        events = engine.push(bar)
        step = runner.observe(events, engine.snapshot, engine.now)
        if not step.asks or (day is not None and not day <= bar.time < day + 86400):
            continue
        try:
            p = template.build(s, engine, runner, step.asks, engine.now)
        except template.NothingToAsk:
            continue
        for c in step.asks:
            runner.refuse(c.key, "preview")
        print(f"--- prompt at {time.strftime('%Y-%m-%d %H:%MZ', time.gmtime(engine.now))}: {p.bytes} bytes of {s.prompt['max_bytes']} "
              f"(trimmed {p.trimmed}) ---")
        print(p.system, "\n", p.user, "\n")
        if a.save and shown == 0:
            Path(a.save).write_text(json.dumps({"system": p.system, "user": p.user}, indent=1), encoding="utf-8")
            print(f"saved to {a.save}")
        shown += 1
        if shown >= a.n:
            break
    if not shown:
        print("no candidate in that period")


if __name__ == "__main__":
    main()
