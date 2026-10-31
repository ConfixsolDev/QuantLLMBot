"""Back-test runner: replay recorded M1 history through the engine.

Run from ``backend``::

    python -m structure_engine.runner --m1 <M1 folder or files> --out runs/bt
    python -m structure_engine.runner --m1 data/XAUUSD_M1.csv --from 2024-01-01 --to 2024-02-01 --snapshot-every 60

The live application (``python -m quantllm``) runs the very same engine on
MT5 bars; this runner exists to replay history offline.

Output folder
-------------
events.jsonl          every event, one JSON object per line (see events.py)
snapshots.jsonl       engine.snapshot() every N bars (--snapshot-every; 0 = off)
final_snapshot.json   the state after the last bar
summary.json          bars, time range, data gaps, event counts, config hash, speed
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .bars import Bar, parse_time
from .config import load_config
from .engine import StructureEngine


def run_stream(bars: Iterable[Bar], out: Path, config_path: str | None = None,
               snapshot_every: int = 0) -> dict:
    """Push every bar through one engine and write the output folder."""
    cfg = load_config(config_path)
    engine = StructureEngine(cfg)
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    n, first, last, gaps = 0, None, None, 0
    with (out / "events.jsonl").open("w", encoding="utf-8") as ev_fh, \
         (out / "snapshots.jsonl").open("w", encoding="utf-8") as snap_fh:
        for bar in bars:
            if last is not None and bar.time - last > 60:
                gaps += 1                               # weekends count too; that is fine
            events = engine.push(bar)
            n += 1
            first = bar.time if first is None else first
            last = bar.time
            for e in events:
                ev_fh.write(json.dumps(e.as_dict(), separators=(",", ":")) + "\n")
            if snapshot_every and n % snapshot_every == 0:
                snap_fh.write(json.dumps(engine.snapshot(), separators=(",", ":")) + "\n")
    elapsed = time.time() - started
    iso = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).isoformat() if t else None  # noqa: E731
    summary = {
        "config_id": cfg["config_id"], "config_hash": cfg.config_hash,
        "bars": n, "first_bar_utc": iso(first), "last_bar_utc": iso(last),
        "gaps": gaps, "event_counts": engine.snapshot()["event_counts"],
        "seconds": round(elapsed, 1), "bars_per_second": round(n / elapsed) if elapsed else None,
    }
    (out / "final_snapshot.json").write_text(json.dumps(engine.snapshot(), indent=1))
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def _date(text: str | None) -> int | None:
    return parse_time(text) if text else None


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m structure_engine.runner", description=__doc__.splitlines()[0])
    ap.add_argument("--m1", required=True, nargs="+",
                    help="M1 file(s) and/or folder(s): CSV/TSV/JSONL with time,open,high,low,close[,tick_volume]")
    ap.add_argument("--out", default="runs/backtest")
    ap.add_argument("--from", dest="start", help="first bar (UTC), e.g. 2024-01-01")
    ap.add_argument("--to", dest="end", help="stop before this time (UTC)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--snapshot-every", type=int, default=0, help="write a snapshot every N bars")
    args = ap.parse_args()
    from .feeds import RecordedFeed
    feed = RecordedFeed(args.m1, start=_date(args.start), end=_date(args.end))
    print(json.dumps(run_stream(feed, Path(args.out), args.config, args.snapshot_every), indent=1))


if __name__ == "__main__":
    main()
