"""Command-line runner: back-test, live (shadow) and MT5 history export.

Run from ``apps/qwen_trade_software/backend``::

    # 1. Download history once (Windows PC with MT5; uses config/mt5_connection.json)
    python -m structure_engine.runner export --from 2016-01-01 --out data/XAUUSD_M1.csv

    # 2. Back-test: replay the file through the SAME engine used live
    python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --out runs/bt_2016_2026
    python -m structure_engine.runner backtest --m1 data/XAUUSD_M1.csv --from 2024-01-01 --to 2024-02-01 --snapshot-every 60
    python -m structure_engine.runner backtest --m1 ../../../model_training/datasets/raw/candles/XAUUSDr/M1 --out runs/real

    # 3. Live shadow: same engine on MT5 bars; writes events/snapshot, trades nothing
    python -m structure_engine.runner live --out runs/live

Output folder
-------------
events.jsonl          every event, one JSON object per line (see events.py)
snapshots.jsonl       engine.snapshot() every N bars (--snapshot-every; 0 = off)
final_snapshot.json   the state after the last bar
summary.json          bars, time range, data gaps, event counts, config hash,
                      speed — enough to tell two runs apart at a glance
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
               snapshot_every: int = 0, live: bool = False) -> dict:
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
            if live and bar.close_time > time.time() - 300:   # skip during warm-up replay
                ev_fh.flush()
                (out / "live_snapshot.json").write_text(json.dumps(engine.snapshot(), indent=1))
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
    sub = ap.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="replay a recorded M1 file")
    bt.add_argument("--m1", required=True, nargs="+",
                    help="M1 file(s) and/or folder(s): CSV/TSV/JSONL with time,open,high,low,close[,tick_volume]")
    bt.add_argument("--out", default="runs/backtest")
    bt.add_argument("--from", dest="start", help="first bar (UTC), e.g. 2024-01-01")
    bt.add_argument("--to", dest="end", help="stop before this time (UTC)")
    bt.add_argument("--broker-time", action="store_true",
                    help="file times are MT5 broker clock (convert with mt5_connection.server_time)")
    bt.add_argument("--config", default=None)
    bt.add_argument("--snapshot-every", type=int, default=0, help="write a snapshot every N bars")

    lv = sub.add_parser("live", help="shadow mode on MT5 closed M1 bars (no trading)")
    lv.add_argument("--out", default="runs/live")
    lv.add_argument("--config", default=None)
    lv.add_argument("--warmup", type=int, default=20_000)
    lv.add_argument("--poll", type=float, default=2.0)

    ex = sub.add_parser("export", help="download MT5 M1 history to CSV (UTC)")
    ex.add_argument("--from", dest="start", required=True)
    ex.add_argument("--to", dest="end", default=None)
    ex.add_argument("--out", required=True)

    args = ap.parse_args()
    if args.cmd == "backtest":
        from .feeds import RecordedFeed
        feed = RecordedFeed(args.m1, broker_time=args.broker_time,
                            start=_date(args.start), end=_date(args.end))
        print(json.dumps(run_stream(feed, Path(args.out), args.config, args.snapshot_every), indent=1))
    elif args.cmd == "live":
        from .feeds import MT5Feed
        run_stream(MT5Feed(args.warmup, args.poll), Path(args.out), args.config, live=True)
    else:
        from .feeds import export_mt5_history
        start = datetime.fromtimestamp(parse_time(args.start), tz=timezone.utc)
        end = datetime.fromtimestamp(parse_time(args.end), tz=timezone.utc) if args.end else None
        print(f"rows written: {export_mt5_history(args.out, start, end)}")


if __name__ == "__main__":
    main()
