"""Independent SQLite-outbox -> Neo4j worker and bounded context publisher."""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import time
import uuid
from pathlib import Path

from market_graph.client import Neo4jMarketGraph
from market_graph.config import graph_config, graph_context_path, graph_health_path
from market_graph.live_updater import Neo4jLiveUpdater
from market_graph.market_state import load_current_market_state
from storage_factory import create_intelligence_store
import process_logging

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"
MARKET_CONTEXT_DB = APP_DIR / "cache" / "market_context.sqlite3"
LOG_DIR = APP_DIR / "logs"
SINGLETON_PORT = 48637


def configure_logging() -> None:
    process_logging.configure(
        LOG_DIR / "market-graph-worker.log", owner="market_graph"
    )


def atomic_json(path: Path, payload: dict, attempts: int = 5) -> bool:
    try:
        from runtime_store import live_runtime_store
        store = live_runtime_store()
        if store is not None:
            store.put_state(path, payload, owner="market_graph")
            return True
    except Exception:
        logging.getLogger(__name__).debug("graph runtime state publication failed", exc_info=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        for attempt in range(max(1, attempts)):
            try:
                os.replace(temporary, path)
                return True
            except PermissionError:
                if attempt + 1 < max(1, attempts):
                    time.sleep(0.05)
        logging.warning("graph JSON publication deferred target=%s", path)
        return False
    except OSError:
        logging.warning("graph JSON publication failed target=%s", path, exc_info=True)
        return False
    finally:
        temporary.unlink(missing_ok=True)


def run(db_path: Path, once: bool = False) -> None:
    configure_logging()
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        singleton.bind(("127.0.0.1", SINGLETON_PORT))
        singleton.listen(1)
    except OSError as error:
        process_logging.structured_event(
            "worker_singleton_conflict",
            level=logging.ERROR,
            worker="market_graph",
            port=SINGLETON_PORT,
            error=str(error),
        )
        return
    config = graph_config
    if not config.enabled:
        atomic_json(graph_health_path(APP_DIR), {
            "status": "disabled", "configuration": config.public(),
            "updated_at_epoch": time.time(),
        })
        return
    store = None
    while store is None:
        try:
            store = create_intelligence_store(db_path)
            store.enqueue_unprojected_graph_events()
        except Exception as error:
            process_logging.structured_event(
                "graph_store_startup",
                level=logging.WARNING,
                status="retrying",
                error_type=type(error).__name__,
                error=str(error),
            )
            if once:
                return
            time.sleep(config.interval_seconds)
    process_logging.structured_event(
        "worker_started",
        worker="market_graph",
        port=SINGLETON_PORT,
        schema_version=config.schema_version,
        interval_seconds=config.interval_seconds,
    )
    while True:
        graph = None
        try:
            graph = Neo4jMarketGraph.connect(config)
            graph.ensure_schema()
            updater = Neo4jLiveUpdater(store, graph, config)
            logging.info("graph connection ready")
            process_logging.structured_event("graph_connection", status="ready")
            last_health_log = 0.0
            while True:
                started = time.monotonic()
                context = None
                market_state = load_current_market_state(MARKET_CONTEXT_DB, config.symbols)
                cycle = updater.update(market_state)
                result = cycle["projection"]
                stats = cycle["outbox"]
                health = {
                    "status": (
                        "ready" if result["status"] != "error" and cycle["m1_freshness"]["fresh"]
                        else "degraded"
                    ),
                    "updated_at_epoch": time.time(),
                    "configuration": config.public(),
                    "projection": result,
                    "outbox": stats,
                    "m1_freshness": cycle["m1_freshness"],
                }
                try:
                    context = cycle["context"]
                    atomic_json(graph_context_path(APP_DIR), context)
                    health["context_compiler"] = {
                        "packet_bytes": context["packet_bytes"],
                        "within_packet_budget": context["within_packet_budget"],
                        "mode": context["mode"],
                    }
                except Exception as error:
                    health["context_error"] = str(error)
                    logging.warning("graph context publication failed", exc_info=True)
                atomic_json(graph_health_path(APP_DIR), health)
                if result.get("selected") or time.monotonic() - last_health_log >= 30:
                    process_logging.structured_event(
                        "graph_cycle",
                        status=health["status"],
                        selected=int(result.get("selected", 0)),
                        projected=int(result.get("projected", 0)),
                        pending=int(stats.get("pending", 0)),
                        dead=int(stats.get("dead", 0)),
                        packet_bytes=(health.get("context_compiler") or {}).get("packet_bytes"),
                        story_memory_status=(context.get("qwen_intraday_story_memory") or {}).get("status")
                        if context is not None else "context_error",
                        duration_ms=round((time.monotonic() - started) * 1000, 2),
                    )
                    last_health_log = time.monotonic()
                if result["status"] == "error":
                    logging.warning("graph projection failed: %s", result.get("error"))
                if once:
                    return
                # Catch-up mode is bounded and temporary. Once the immutable
                # outbox is below 10k, return to the configured steady cadence.
                target_interval = 0.25 if stats.get("pending", 0) > 10000 else config.interval_seconds
                time.sleep(max(0.05, target_interval - (time.monotonic() - started)))
        except Exception as error:
            logging.exception("market graph worker unavailable")
            process_logging.structured_event(
                "graph_connection",
                level=logging.ERROR,
                status="unavailable",
                error_type=type(error).__name__,
                error=str(error),
            )
            atomic_json(graph_health_path(APP_DIR), {
                "status": "unavailable",
                "updated_at_epoch": time.time(),
                "configuration": config.public(),
                "error": str(error),
                "outbox": store.graph_outbox_stats(),
            })
            if once:
                return
            time.sleep(config.interval_seconds)
        finally:
            if graph is not None:
                graph.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--once", action="store_true")
    # Accepted for parity with the unified runtime command. The validated
    # environment-backed GraphConfig remains the single interval authority.
    parser.add_argument("--interval", type=float, default=None)
    args = parser.parse_args()
    run(args.db, args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
