"""QuantLLM command line (run from ``backend/``).

    python -m quantllm serve                 start everything (DB, MT5, engine, API)
    python -m quantllm serve --no-mt5        same, from stored data only
    python -m quantllm check                 test the database and MT5 connections
    python -m quantllm import-csv <files or folders...>   load M1 CSV history into the DB
    python -m quantllm import-mt5 --from 2016-01-01       load M1 history from MT5 into the DB
    python -m quantllm reimport-mt5 --from 2025-10-01 --yes
                                             DELETE stored bars from that day and load them
                                             again from MT5 (after a broker-clock fix)

Everything is also written to logs/quantllm.log (repository root, 5 x 5 MB).
"""

from __future__ import annotations

import argparse
import logging
import sys

from structure_engine.bars import parse_time

from . import mt5_connection
from .settings import load_settings


def main() -> None:
    from logging.handlers import RotatingFileHandler
    from pathlib import Path
    logs = Path(__file__).resolve().parents[2] / "logs"
    logs.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout),
                                  RotatingFileHandler(logs / "quantllm.log", maxBytes=5_000_000,
                                                      backupCount=5, encoding="utf-8")])
    ap = argparse.ArgumentParser(prog="python -m quantllm", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--no-mt5", action="store_true")
    sub.add_parser("check")
    ic = sub.add_parser("import-csv")
    ic.add_argument("paths", nargs="+")
    im = sub.add_parser("import-mt5")
    im.add_argument("--from", dest="start", required=True)
    rim = sub.add_parser("reimport-mt5")
    rim.add_argument("--from", dest="start", required=True)
    rim.add_argument("--yes", action="store_true", help="confirm: stored bars from --from on are deleted")
    args = ap.parse_args()
    settings = load_settings()
    symbol = mt5_connection.settings().broker_symbol

    if args.cmd == "serve":
        from .service import serve
        serve(settings, use_mt5=not args.no_mt5)
        return

    from .database import Database
    if args.cmd == "check":
        print(f"database schema: {settings.db_schema}")
        db = Database(settings.db_dsn, settings.db_schema)
        print(f"  connected ({'TimescaleDB' if db.timescale else 'PostgreSQL'}); "
              f"{db.candle_count(symbol)} M1 bars for {symbol}")
        try:
            from .market_feed import connect_mt5
            mt5 = connect_mt5()
            acc = mt5.account_info()
            print(f"MT5: connected, login {acc.login}, server {acc.server}, symbol {symbol} OK")
            clock = mt5_connection.resolve_server_time(mt5, symbol)
            print(f"broker clock: {clock['using']} (configured {clock['configured']!r}; "
                  f"{clock['breaks']} daily 17:00 New York breaks checked)")
        except Exception as exc:
            print(f"MT5: NOT connected: {exc}")
        return

    db = Database(settings.db_dsn, settings.db_schema)
    if args.cmd == "import-csv":
        from .market_feed import csv_bars
        total, chunk = 0, []
        for bar in csv_bars(args.paths):
            chunk.append(bar)
            if len(chunk) >= 50000:
                total += db.insert_candles(symbol, chunk)
                chunk = []
                print(f"  {total} new bars...", flush=True)
        total += db.insert_candles(symbol, chunk)
        print(f"imported {total} new M1 bars for {symbol}; {db.candle_count(symbol)} in the database")
    elif args.cmd in ("import-mt5", "reimport-mt5"):
        from .market_feed import connect_mt5, mt5_history
        mt5 = connect_mt5()                         # checks the broker clock first
        if args.cmd == "reimport-mt5":
            if not args.yes:
                raise SystemExit("reimport-mt5 deletes stored bars; add --yes to confirm")
            n = db.delete_candles(symbol, parse_time(args.start))
            print(f"deleted {n} stored M1 bars for {symbol} from {args.start}")
        total = 0
        for chunk in mt5_history(mt5, symbol, parse_time(args.start)):
            total += db.insert_candles(symbol, chunk)
            print(f"  {total} new bars (up to {chunk[-1].time})", flush=True)
        print(f"imported {total} new M1 bars for {symbol}; {db.candle_count(symbol)} in the database")


if __name__ == "__main__":
    main()
