"""Independent SQLite-outbox -> Neo4j worker and bounded context publisher."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import time
import uuid
from pathlib import Path

from market_graph.client import Neo4jMarketGraph
from market_graph.context_compiler import compile_market_memory
from market_graph.config import graph_config, graph_context_path, graph_health_path
from market_graph.projector import GraphProjector
from market_graph.market_state import load_current_market_state
from market_intelligence.store import IntelligenceStore

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"
MARKET_CONTEXT_DB = APP_DIR / "cache" / "market_context.sqlite3"
LOG_DIR = APP_DIR / "logs"


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        LOG_DIR / "market-graph-worker.log", when="midnight", encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def atomic_json(path: Path, payload: dict, attempts: int = 5) -> bool:
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
    config = graph_config
    if not config.enabled:
        atomic_json(graph_health_path(APP_DIR), {
            "status": "disabled", "configuration": config.public(),
            "updated_at_epoch": time.time(),
        })
        return
    store = IntelligenceStore(db_path)
    store.enqueue_unprojected_graph_events()
    while True:
        graph = None
        try:
            graph = Neo4jMarketGraph.connect(config)
            graph.ensure_schema()
            projector = GraphProjector(store, graph, config)
            logging.info("graph connection ready")
            while True:
                started = time.monotonic()
                result = projector.project_once()
                graph.upsert_market_state(load_current_market_state(MARKET_CONTEXT_DB, config.symbols))
                stats = store.graph_outbox_stats()
                health = {
                    "status": "ready" if result["status"] != "error" else "degraded",
                    "updated_at_epoch": time.time(),
                    "configuration": config.public(),
                    "projection": result,
                    "outbox": stats,
                }
                try:
                    raw_context = graph.context(config.symbols)
                    raw_context.update({"projection": stats, "schema_version": config.schema_version})
                    context = compile_market_memory(raw_context)
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
