"""Independent completed-candle -> persistent market-memory service."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import time
import uuid
from pathlib import Path

import MetaTrader5 as mt5

from market_intelligence.collector import collect_once
from market_intelligence.live_structure_updater import update_live_structure
from market_intelligence.projection import reduce_event
from market_intelligence import MarketIntelligenceService
from storage_factory import create_intelligence_store
from runtime_config import PRIMARY_MARKET_SYMBOL

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"
HEALTH_FILE = APP_DIR / "cache" / "market-memory-health.json"


def configure_logging() -> None:
    import process_logging
    process_logging.configure(LOG_DIR / "market-memory-worker.log", owner="market_memory")


def write_health(
    payload: dict,
    *,
    target: Path = HEALTH_FILE,
    attempts: int = 5,
    retry_seconds: float = 0.05,
) -> bool:
    """Publish health atomically without ever endangering candle ingestion.

    Windows can briefly deny ``os.replace`` while the dashboard has the old
    JSON open. A unique temporary name prevents workers/restarts colliding;
    bounded retries absorb reader locks. Health is diagnostic, so exhausting
    retries logs a warning and returns False instead of killing the collector.
    """
    try:
        from runtime_store import live_runtime_store
        store = live_runtime_store()
        if store is not None:
            store.put_state(target, payload, owner="market_memory")
            return True
    except Exception:
        logging.getLogger(__name__).debug("market memory runtime state publication failed", exc_info=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        for attempt in range(max(1, attempts)):
            try:
                os.replace(temporary, target)
                return True
            except PermissionError:
                if attempt + 1 < max(1, attempts):
                    time.sleep(max(0.0, retry_seconds))
        logging.warning(
            "market memory health publication deferred after %d attempts target=%s",
            max(1, attempts), target,
        )
        return False
    except OSError:
        logging.warning("market memory health publication failed target=%s", target, exc_info=True)
        return False
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def run(db_path: Path, symbol: str, interval: float, once: bool = False) -> None:
    configure_logging()
    store = create_intelligence_store(db_path)
    # The collector owns durable evidence; this small facade only publishes a
    # bounded read-through snapshot so Redis remains warm between reviewer or
    # dashboard requests. It never selects trades or changes the ledger.
    context_service = MarketIntelligenceService(
        db_path, lambda _symbol, _timeframe, _count: []
    )
    replayed = store.rebuild(reduce_event)
    logging.info("startup replay complete events=%d", replayed)
    first_cycle = True
    while True:
        started = time.time()
        try:
            if not mt5.initialize():
                raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
            result = collect_once(store, mt5, symbol, lookback=300 if first_cycle else 20)
            first_cycle = False
            updated_timeframes = [
                key.rsplit(":", 1)[-1]
                for key, count in result.get("inserted", {}).items()
                if key.startswith(f"{symbol}:") and int(count or 0) > 0
            ]
            structure = update_live_structure(store, symbol, updated_timeframes)
            context_service.refresh_snapshot(symbol)
            health = {"status": "ready", "symbol": symbol,
                      "updated_at_epoch": time.time(), "replayed_events": replayed,
                      "live_structure": structure, **result}
            write_health(health)
            if result["inserted_total"]:
                logging.info("candle backfill %s", json.dumps(result, sort_keys=True))
        except Exception as error:
            logging.exception("market memory collection failed")
            write_health({"status": "error", "symbol": symbol,
                          "updated_at_epoch": time.time(), "error": str(error)})
        finally:
            mt5.shutdown()
        if once:
            return
        time.sleep(max(0.25, interval - (time.time() - started)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--symbol", default=PRIMARY_MARKET_SYMBOL)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run(args.db, args.symbol, args.interval, args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
