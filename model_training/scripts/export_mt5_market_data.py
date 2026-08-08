#!/usr/bin/env python3
"""Download MT5 historical data for v003 training.

Downloads:
  - Tick prints (max broker history, daily CSV chunks)
  - M1 candles (max history, monthly CSV)
  - H1 candles (max history, monthly CSV) — direct from MT5
  - M5, M15, M30 — resampled from M1 (UTC bar alignment)
  - H4 — resampled from H1 using 4-hour buckets in America/New_York

Requires MetaTrader 5 terminal logged in (same as live app).

Example:
  cd E:\\QuantLLMBot\\model_training
  ..\\apps\\qwen_trade_software\\backend\\.venv\\Scripts\\python.exe scripts\\export_mt5_market_data.py

  # Or with backend conda/python that has MetaTrader5 installed:
  C:\\ProgramData\\Miniconda3\\python.exe scripts\\export_mt5_market_data.py --symbol XAUUSDr
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from mt5_export_lib import (
    CANDLE_COLUMNS,
    TICK_COLUMNS,
    ExportStats,
    append_log,
    connect_mt5,
    copy_m1_via_positions,
    copy_rates_chunk,
    copy_ticks_chunk,
    day_key,
    day_range,
    ensure_symbol,
    iso_utc,
    month_key,
    month_range,
    probe_earliest_bar,
    probe_earliest_tick,
    read_candles_csv,
    resample_h4_ny_from_h1,
    resample_utc,
    shutdown_mt5,
    utc_now,
    write_csv,
    parse_utc,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "model_training" / "datasets" / "raw"


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def export_ticks(
    symbol: str,
    start: datetime,
    end: datetime,
    out_dir: Path,
    log_path: Path,
    *,
    force: bool,
) -> ExportStats:
    stats = ExportStats()
    tick_dir = out_dir / "ticks" / symbol
    for chunk_start, chunk_end in day_range(start, end):
        path = tick_dir / f"{day_key(chunk_start)}_ticks.csv"
        if path.exists() and not force:
            stats.skipped += 1
            continue
        rows: list[dict] = []
        window = chunk_start
        while window < chunk_end:
            sub_end = min(window + timedelta(hours=6), chunk_end)
            try:
                part = copy_ticks_chunk(symbol, window, sub_end)
            except RuntimeError as exc:
                append_log(
                    log_path,
                    {
                        "event": "tick_chunk_error",
                        "symbol": symbol,
                        "from": iso_utc(window),
                        "to": iso_utc(sub_end),
                        "error": str(exc),
                    },
                )
                window = sub_end
                continue
            rows.extend(part)
            window = sub_end
        if not rows:
            append_log(
                log_path,
                {
                    "event": "tick_chunk_empty",
                    "symbol": symbol,
                    "day": day_key(chunk_start),
                },
            )
            continue
        count = write_csv(path, TICK_COLUMNS, rows)
        stats.rows += count
        stats.files += 1
        append_log(
            log_path,
            {
                "event": "ticks_exported",
                "symbol": symbol,
                "path": str(path),
                "rows": count,
                "from": iso_utc(chunk_start),
                "to": iso_utc(chunk_end),
            },
        )
        print(f"  ticks {day_key(chunk_start)}: {count:,} rows")
    return stats


def export_m1(
    symbol: str,
    start: datetime,
    end: datetime,
    out_dir: Path,
    log_path: Path,
    *,
    force: bool,
) -> ExportStats:
    stats = ExportStats()
    candle_dir = out_dir / "candles" / symbol / "M1"
    candle_dir.mkdir(parents=True, exist_ok=True)

    pending_months = [
        (chunk_start, chunk_end)
        for chunk_start, chunk_end in month_range(start, end)
        if force or not (candle_dir / f"{month_key(chunk_start)}_M1.csv").exists()
    ]
    if not pending_months:
        stats.skipped = len(list(month_range(start, end)))
        return stats

    print("  fetching all available M1 bars once...")
    all_rows = copy_m1_via_positions(symbol, start, end)
    by_month: dict[str, list[dict]] = {}
    for row in all_rows:
        key = month_key(parse_utc(row["time_utc"]))
        by_month.setdefault(key, []).append(row)

    for chunk_start, chunk_end in month_range(start, end):
        path = candle_dir / f"{month_key(chunk_start)}_M1.csv"
        if path.exists() and not force:
            stats.skipped += 1
            continue
        rows = by_month.get(month_key(chunk_start), [])
        if not rows:
            append_log(
                log_path,
                {
                    "event": "m1_empty",
                    "symbol": symbol,
                    "month": month_key(chunk_start),
                },
            )
            continue
        count = write_csv(path, CANDLE_COLUMNS, rows)
        stats.rows += count
        stats.files += 1
        append_log(
            log_path,
            {
                "event": "m1_exported",
                "symbol": symbol,
                "path": str(path),
                "rows": count,
                "from": iso_utc(chunk_start),
                "to": iso_utc(chunk_end),
                "method": "copy_rates_from_pos",
            },
        )
        print(f"  M1 {month_key(chunk_start)}: {count:,} bars")
    return stats


def export_rates(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    out_dir: Path,
    log_path: Path,
    *,
    force: bool,
) -> ExportStats:
    stats = ExportStats()
    candle_dir = out_dir / "candles" / symbol / timeframe
    for chunk_start, chunk_end in month_range(start, end):
        path = candle_dir / f"{month_key(chunk_start)}_{timeframe}.csv"
        if path.exists() and not force:
            stats.skipped += 1
            continue
        rows = copy_rates_chunk(symbol, timeframe, chunk_start, chunk_end)
        if not rows:
            append_log(
                log_path,
                {
                    "event": "rates_empty",
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "month": month_key(chunk_start),
                },
            )
            continue
        count = write_csv(path, CANDLE_COLUMNS, rows)
        stats.rows += count
        stats.files += 1
        append_log(
            log_path,
            {
                "event": "rates_exported",
                "symbol": symbol,
                "timeframe": timeframe,
                "path": str(path),
                "rows": count,
                "from": iso_utc(chunk_start),
                "to": iso_utc(chunk_end),
            },
        )
        print(f"  {timeframe} {month_key(chunk_start)}: {count:,} bars")
    return stats


def derive_from_m1(symbol: str, out_dir: Path, log_path: Path, *, force: bool) -> ExportStats:
    stats = ExportStats()
    m1_dir = out_dir / "candles" / symbol / "M1"
    if not m1_dir.exists():
        return stats
    for target in ("M5", "M15", "M30"):
        target_dir = out_dir / "candles" / symbol / target
        target_dir.mkdir(parents=True, exist_ok=True)
        for m1_path in sorted(m1_dir.glob("*_M1.csv")):
            month = m1_path.stem.replace("_M1", "")
            out_path = target_dir / f"{month}_{target}.csv"
            if out_path.exists() and not force:
                stats.skipped += 1
                continue
            m1_rows = read_candles_csv(m1_path)
            derived = resample_utc(m1_rows, target, derived_from="M1")
            count = write_csv(out_path, CANDLE_COLUMNS, derived)
            stats.rows += count
            stats.files += 1
            append_log(
                log_path,
                {
                    "event": "derived_candles",
                    "symbol": symbol,
                    "timeframe": target,
                    "source_file": str(m1_path),
                    "path": str(out_path),
                    "rows": count,
                },
            )
            print(f"  derived {target} {month}: {count:,} bars")
    return stats


def derive_h4_ny(symbol: str, out_dir: Path, log_path: Path, *, force: bool) -> ExportStats:
    stats = ExportStats()
    h1_dir = out_dir / "candles" / symbol / "H1"
    h4_dir = out_dir / "candles" / symbol / "H4"
    h4_dir.mkdir(parents=True, exist_ok=True)
    if not h1_dir.exists():
        return stats
    for h1_path in sorted(h1_dir.glob("*_H1.csv")):
        month = h1_path.stem.replace("_H1", "")
        out_path = h4_dir / f"{month}_H4_NY.csv"
        if out_path.exists() and not force:
            stats.skipped += 1
            continue
        h1_rows = read_candles_csv(h1_path)
        derived = resample_h4_ny_from_h1(h1_rows)
        count = write_csv(out_path, CANDLE_COLUMNS, derived)
        stats.rows += count
        stats.files += 1
        append_log(
            log_path,
            {
                "event": "derived_h4_ny",
                "symbol": symbol,
                "source_file": str(h1_path),
                "path": str(out_path),
                "rows": count,
                "bar_timezone": "America/New_York",
            },
        )
        print(f"  derived H4(NY) {month}: {count:,} bars")
    return stats


def write_manifest(out_dir: Path, symbol: str, payload: dict) -> None:
    manifest_path = out_dir / "manifest.json"
    existing: dict = {}
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing[symbol] = payload
    manifest_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export MT5 ticks and candles for v003.")
    parser.add_argument("--symbol", default="XAUUSDr")
    parser.add_argument("--from-date", help="UTC start (YYYY-MM-DD or ISO). Default: earliest available.")
    parser.add_argument("--to-date", help="UTC end. Default: now.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", help="Overwrite existing chunk files.")
    parser.add_argument("--skip-ticks", action="store_true")
    parser.add_argument("--skip-m1", action="store_true")
    parser.add_argument("--skip-h1", action="store_true")
    parser.add_argument("--skip-derived", action="store_true", help="Skip M5/M15/M30/H4 derivation.")
    args = parser.parse_args()

    out_dir = args.out_dir
    log_path = out_dir / "export_log.jsonl"
    end = parse_date(args.to_date) or utc_now()

    print(f"Connecting MT5 for {args.symbol}...")
    connect_mt5()
    ensure_symbol(args.symbol)

    earliest_m1 = probe_earliest_bar(args.symbol, "M1")
    earliest_h1 = probe_earliest_bar(args.symbol, "H1")
    earliest_tick = None if args.skip_ticks else probe_earliest_tick(args.symbol)

    start = parse_date(args.from_date)
    if start is None:
        candidates = [dt for dt in (earliest_m1, earliest_h1, earliest_tick) if dt is not None]
        if not candidates:
            shutdown_mt5()
            raise SystemExit("Could not probe earliest MT5 history. Check symbol and terminal login.")
        start = min(candidates)

    print(f"Range: {iso_utc(start)} -> {iso_utc(end)}")
    print(f"Earliest M1: {iso_utc(earliest_m1) if earliest_m1 else 'n/a'}")
    print(f"Earliest H1: {iso_utc(earliest_h1) if earliest_h1 else 'n/a'}")
    print(f"Earliest tick: {iso_utc(earliest_tick) if earliest_tick else 'n/a'}")

    summary: dict = {
        "symbol": args.symbol,
        "from": iso_utc(start),
        "to": iso_utc(end),
        "earliest_m1": iso_utc(earliest_m1) if earliest_m1 else None,
        "earliest_h1": iso_utc(earliest_h1) if earliest_h1 else None,
        "earliest_tick": iso_utc(earliest_tick) if earliest_tick else None,
        "exported_at": iso_utc(utc_now()),
    }

    if not args.skip_ticks and earliest_tick is not None:
        tick_start = max(start, earliest_tick)
        print("Exporting ticks...")
        summary["ticks"] = export_ticks(
            args.symbol, tick_start, end, out_dir, log_path, force=args.force
        ).__dict__

    if not args.skip_m1 and earliest_m1 is not None:
        m1_start = max(start, earliest_m1)
        print("Exporting M1 (position-based — broker bar limit)...")
        summary["m1"] = export_m1(
            args.symbol, m1_start, end, out_dir, log_path, force=args.force
        ).__dict__

    if not args.skip_h1 and earliest_h1 is not None:
        h1_start = max(start, earliest_h1)
        print("Exporting H1...")
        summary["h1"] = export_rates(
            args.symbol, "H1", h1_start, end, out_dir, log_path, force=args.force
        ).__dict__

    if not args.skip_derived:
        print("Deriving M5/M15/M30 from M1...")
        summary["derived_intraday"] = derive_from_m1(
            args.symbol, out_dir, log_path, force=args.force
        ).__dict__
        print("Deriving H4 (New York 4h buckets) from H1...")
        summary["derived_h4_ny"] = derive_h4_ny(
            args.symbol, out_dir, log_path, force=args.force
        ).__dict__

    write_manifest(out_dir, args.symbol, summary)
    append_log(log_path, {"event": "export_complete", **summary})
    shutdown_mt5()
    print(f"Done. Output: {out_dir}")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
