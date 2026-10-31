"""QuantLLM command line (run from ``backend/``).

    python -m quantllm serve                 start everything (DB, MT5, engine, API)
    python -m quantllm serve --no-mt5        same, from stored data only
    python -m quantllm check                 test the database and MT5 connections
    python -m quantllm import-csv <files or folders...>   load M1 CSV history into the DB
    python -m quantllm import-mt5 --from 2016-01-01       load M1 history from MT5 into the DB
"""

from __future__ import annotations

import argparse
import logging
import sys

from structure_engine.bars import parse_time

from . import mt5_connection
from .settings import load_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)
    ap = argparse.ArgumentParser(prog="python -m quantllm", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--no-mt5", action="store_true")
    sub.add_parser("check")
    ic = sub.add_parser("import-csv")
    ic.add_argument("paths", nargs="+")
    im = sub.add_parser("import-mt5")
    im.add_argument("--from", dest="start", required=True)
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
    elif args.cmd == "import-mt5":
        from .market_feed import connect_mt5, mt5_history
        mt5 = connect_mt5()
        total = 0
        for chunk in mt5_history(mt5, symbol, parse_time(args.start)):
            total += db.insert_candles(symbol, chunk)
            print(f"  {total} new bars (up to {chunk[-1].time})", flush=True)
        print(f"imported {total} new M1 bars for {symbol}; {db.candle_count(symbol)} in the database")


if __name__ == "__main__":
    main()
