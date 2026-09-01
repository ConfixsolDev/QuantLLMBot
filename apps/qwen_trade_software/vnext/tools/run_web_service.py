"""Serve the read-only vNext operations dashboard on localhost."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib import request
from urllib.parse import urlparse

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/lightweight-charts.js": ("lightweight-charts.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
PAGE_ROUTES = frozenset({"/operations", "/history", "/trades"})
CHART_TIMEFRAMES = ("D1", "H4", "H1", "M30", "M15")


def _age_seconds(value: str | None) -> int | None:
    if not value:
        return None
    observed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0, int((datetime.now(timezone.utc) - observed).total_seconds()))


def merge_candles(durable: list[dict[str, Any]], working: list[dict[str, Any]],
                  *, limit: int = 180) -> list[dict[str, Any]]:
    """Merge completed candles by timeframe/open time; fresh V2 context wins."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for source, rows in (("timescale", durable), ("working_memory", working)):
        for raw in rows:
            row = dict(raw)
            timeframe = str(row.get("timeframe", ""))
            start = str(row.get("start_utc", row.get("open_time_utc", "")))
            end = str(row.get("end_utc", row.get("close_time_utc", "")))
            if timeframe not in CHART_TIMEFRAMES or not start or not end:
                continue
            values = [row.get(name) for name in ("open", "high", "low", "close")]
            try:
                prices = [float(value) for value in values]
            except (TypeError, ValueError):
                continue
            merged[(timeframe, start)] = {
                "timeframe": timeframe, "start_utc": start, "end_utc": end,
                "open": prices[0], "high": prices[1], "low": prices[2], "close": prices[3],
                "tick_volume": float(row.get("tick_volume", 0) or 0),
                "spread": float(row["spread"]) if row.get("spread") is not None else None,
                "source": source,
            }
    result = sorted(merged.values(), key=lambda row: (CHART_TIMEFRAMES.index(row["timeframe"]), row["start_utc"]))
    limited: list[dict[str, Any]] = []
    for timeframe in CHART_TIMEFRAMES:
        limited.extend([row for row in result if row["timeframe"] == timeframe][-limit:])
    return limited


class SystemHealthProbe:
    """Perform bounded read-only connectivity checks; never call MT5 directly."""

    def __init__(self, *, cache_seconds: float = 10.0) -> None:
        self.cache_seconds = cache_seconds
        self._cached_at = 0.0
        self._cached: dict[str, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _model_host(expected_model: str) -> dict[str, Any]:
        endpoint = os.environ.get("QWEN_MODEL_TAGS_ENDPOINT", "http://127.0.0.1:11434/api/tags")
        try:
            with request.urlopen(endpoint, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            names = [str(item.get("name", "")) for item in payload.get("models", ()) if isinstance(item, dict)]
            installed = not expected_model or expected_model in names
            detail = f"{len(names)} installed · expected {expected_model or 'not declared'}"
            return {"label": "Model host", "ok": installed, "short": "online" if installed else "model missing", "detail": detail}
        except Exception as exc:
            return {"label": "Model host", "ok": False, "short": "offline", "detail": f"Ollama probe failed ({type(exc).__name__})"}

    @staticmethod
    def _redis() -> dict[str, Any]:
        url = os.environ.get("QWEN_REDIS_URL", "")
        if not url:
            return {"label": "Redis working memory", "ok": False, "short": "unconfigured", "detail": "QWEN_REDIS_URL is not set"}
        try:
            import redis
            client = redis.Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
            try:
                ok = bool(client.ping())
            finally:
                client.close()
            return {"label": "Redis working memory", "ok": ok, "short": "online" if ok else "offline", "detail": "Disposable V2 cache and leases"}
        except Exception as exc:
            return {"label": "Redis working memory", "ok": False, "short": "offline", "detail": f"Connectivity failed ({type(exc).__name__})"}

    @staticmethod
    def _neo4j() -> dict[str, Any]:
        uri = os.environ.get("QWEN_NEO4J_URI", "")
        user = os.environ.get("QWEN_NEO4J_USER", "")
        password = os.environ.get("QWEN_NEO4J_PASSWORD", "")
        if not all((uri, user, password)):
            return {"label": "Neo4j projection", "ok": False, "short": "unconfigured", "detail": "Graph connection settings are incomplete"}
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(uri, auth=(user, password), connection_timeout=1)
            try:
                driver.verify_connectivity()
            finally:
                driver.close()
            return {"label": "Neo4j projection", "ok": True, "short": "online", "detail": "Causal graph endpoint is reachable"}
        except Exception as exc:
            return {"label": "Neo4j projection", "ok": False, "short": "offline", "detail": f"Connectivity failed ({type(exc).__name__})"}

    def snapshot(self, latest: dict[str, dict[str, Any]]) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            if self._cached and now - self._cached_at < self.cache_seconds:
                return self._cached
            debug = latest.get("VNEXT_DEBUG_CYCLE")
            broker = latest.get("MAGIC_POSITION_SNAPSHOT")
            expectation = latest.get("TIMEFRAME_EXPECTATION_RECORDED")
            debug_age = _age_seconds(debug.get("observed_at_utc") if debug else None)
            broker_age = _age_seconds(broker.get("observed_at_utc") if broker else None)
            expectation_age = _age_seconds(expectation.get("observed_at_utc") if expectation else None)
            debug_payload = debug.get("payload", {}) if debug else {}
            broker_payload = broker.get("payload", {}) if broker else {}
            mt5_ok = broker_age is not None and broker_age <= 20
            debug_ok = debug_age is not None and debug_age <= 180
            services = {
                "model_host": self._model_host(str(debug_payload.get("model", ""))),
                "mt5": {"label": "MT5 broker connection", "ok": mt5_ok,
                        "short": "connected" if mt5_ok else "stale",
                        "detail": f"Broker-truth snapshot {broker_age}s ago · magic {broker_payload.get('magic_number', '—')}" if broker_age is not None else "No durable broker-truth snapshot"},
                "timescale": {"label": "TimescaleDB authority", "ok": True, "short": "online", "detail": "V2 immutable event ledger is readable"},
                "timeframe_audit": {"label": "Candle expectation audit", "ok": expectation_age is not None and expectation_age <= 2700,
                                    "short": "tracking" if expectation_age is not None and expectation_age <= 2700 else "awaiting boundary",
                                    "detail": f"Latest causal M15 expectation {expectation_age}s ago" if expectation_age is not None else "No causal expectation recorded yet"},
                "redis": self._redis(),
                "neo4j": self._neo4j(),
                "debug_worker": {"label": "No-order debug worker", "ok": debug_ok,
                                 "short": "running" if debug_ok else "stale",
                                 "detail": f"Latest diagnostic cycle {debug_age}s ago" if debug_age is not None else "No diagnostic cycle recorded"},
                "demo_monitor": {"label": "Demo broker monitor", "ok": mt5_ok,
                                 "short": "running" if mt5_ok else "stale",
                                 "detail": "Fresh strategy-magic reconciliation snapshots" if mt5_ok else "Broker snapshots are not fresh"},
                "web": {"label": "V2 web surface", "ok": True, "short": "online", "detail": "Localhost-only and read-only"},
            }
            self._cached = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "services": services}
            self._cached_at = now
            return self._cached


class LedgerDashboardReader:
    """Read operational projections without acquiring leases or writing state."""

    def __init__(self, dsn: str, connect: Callable[..., Any] | None = None,
                 health_probe: SystemHealthProbe | None = None) -> None:
        if not dsn:
            raise ValueError("QWEN_TIMESCALE_DSN is required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._dsn = dsn
        self._connect = connect
        self._health_probe = health_probe or SystemHealthProbe()
        self._working_state: dict[str, Any] = {}
        self._working_state_lock = threading.Lock()

    @staticmethod
    def _event(row: Any) -> dict[str, Any] | None:
        if row is None:
            return None
        payload = row[3] if isinstance(row[3], dict) else json.loads(row[3])
        return {
            "event_type": row[0],
            "pair": row[1],
            "observed_at_utc": row[2].isoformat(),
            "payload": payload,
        }

    def snapshot(self, *, limit: int = 24) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        with self._connect(self._dsn, connect_timeout=3) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT event_type,pair,observed_at_utc,payload_json "
                "FROM vnext_event_ledger ORDER BY observed_at_utc DESC LIMIT %s",
                (limit,),
            )
            recent = [self._event(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT DISTINCT ON (event_type) event_type,pair,observed_at_utc,payload_json "
                "FROM vnext_event_ledger WHERE event_type = ANY(%s) "
                "ORDER BY event_type,observed_at_utc DESC",
                ([
                    "VNEXT_DEBUG_CYCLE", "VNEXT_DEBUG_CYCLE_FAILED",
                    "PAIR_MARKET_STATE_COMPOSED", "STRATEGY_LIFECYCLE",
                    "QWEN_ARBITRATION", "RISK_DECISION", "ORDER_SUBMITTED",
                    "MAGIC_POSITION_SNAPSHOT", "TIMEFRAME_EXPECTATION_RECORDED",
                    "TIMEFRAME_EXPECTATION_ASSESSED",
                ],),
            )
            latest = {event["event_type"]: event for event in map(self._event, cursor.fetchall()) if event}
            cursor.execute(
                "SELECT event_type,COUNT(*) FROM vnext_event_ledger "
                "WHERE observed_at_utc >= NOW() - INTERVAL '24 hours' "
                "GROUP BY event_type ORDER BY event_type"
            )
            counts = {str(event_type): int(count) for event_type, count in cursor.fetchall()}

            cursor.execute(
                "SELECT date_trunc('hour',observed_at_utc) AS bucket,COUNT(*) AS events,"
                "COUNT(*) FILTER (WHERE event_type='STRATEGY_LIFECYCLE' AND payload_json->>'state'='CANDIDATE_CREATED') AS candidates,"
                "COUNT(*) FILTER (WHERE event_type='RISK_DECISION' AND payload_json->>'approved'='true') AS risk_approved,"
                "COUNT(*) FILTER (WHERE event_type='ORDER_SUBMITTED') AS orders "
                "FROM vnext_event_ledger WHERE observed_at_utc >= NOW() - INTERVAL '7 days' "
                "GROUP BY bucket ORDER BY bucket"
            )
            hourly = [{"bucket": row[0].isoformat(), "events": int(row[1]), "candidates": int(row[2]),
                       "risk_approved": int(row[3]), "orders": int(row[4])} for row in cursor.fetchall()]
            cursor.execute(
                "SELECT date_trunc('day',observed_at_utc) AS bucket,COUNT(*) AS events,"
                "COUNT(*) FILTER (WHERE event_type='STRATEGY_LIFECYCLE' AND payload_json->>'state'='CANDIDATE_CREATED') AS candidates,"
                "COUNT(*) FILTER (WHERE event_type='RISK_DECISION' AND payload_json->>'approved'='true') AS risk_approved,"
                "COUNT(*) FILTER (WHERE event_type='ORDER_SUBMITTED') AS orders "
                "FROM vnext_event_ledger WHERE observed_at_utc >= NOW() - INTERVAL '30 days' "
                "GROUP BY bucket ORDER BY bucket"
            )
            daily = [{"day": row[0].date().isoformat(), "events": int(row[1]), "candidates": int(row[2]),
                      "risk_approved": int(row[3]), "orders": int(row[4])} for row in cursor.fetchall()]
            cursor.execute(
                "SELECT event_type,pair,observed_at_utc,payload_json FROM vnext_event_ledger "
                "WHERE event_type='ORDER_SUBMITTED' ORDER BY observed_at_utc DESC LIMIT 200"
            )
            order_events = [self._event(row) for row in cursor.fetchall()]
            cursor.execute(
                "SELECT timeframe,open_time_utc,close_time_utc,open,high,low,close,tick_volume,spread "
                "FROM (SELECT timeframe,open_time_utc,close_time_utc,open,high,low,close,tick_volume,spread,"
                "ROW_NUMBER() OVER (PARTITION BY timeframe ORDER BY open_time_utc DESC) AS row_number "
                "FROM completed_candles WHERE symbol=%s AND timeframe = ANY(%s)) ranked "
                "WHERE row_number <= 180 ORDER BY timeframe,open_time_utc",
                ((latest.get("PAIR_MARKET_STATE_COMPOSED") or {}).get("pair", "XAUUSDr"), list(CHART_TIMEFRAMES)),
            )
            durable_candles = [{"timeframe": row[0], "start_utc": row[1].isoformat(),
                                "end_utc": row[2].isoformat(), "open": row[3], "high": row[4],
                                "low": row[5], "close": row[6], "tick_volume": row[7],
                                "spread": row[8]} for row in cursor.fetchall()]

        newest = recent[0]["observed_at_utc"] if recent else None
        freshness = _age_seconds(newest)
        totals = {name: sum(int(row[name]) for row in hourly)
                  for name in ("events", "candidates", "risk_approved", "orders")}
        trade_records = []
        for event in order_events:
            payload = dict(event["payload"])
            payload["observed_at_utc"] = event["observed_at_utc"]
            payload["pair"] = event["pair"]
            trade_records.append(payload)
        working_state: dict[str, Any] = {}
        forming_state: dict[str, Any] = {}
        redis_url = os.environ.get("QWEN_REDIS_URL", "")
        pair = (latest.get("PAIR_MARKET_STATE_COMPOSED") or {}).get("pair", "XAUUSDr")
        if redis_url:
            try:
                import redis
                client = redis.Redis.from_url(redis_url, decode_responses=True,
                                              socket_connect_timeout=1, socket_timeout=1)
                try:
                    raw_state = client.get(f"qwen:vnext:working:{pair}")
                    raw_forming = client.get(f"qwen:vnext:working:forming:{pair}")
                finally:
                    client.close()
                if raw_state:
                    candidate_state = json.loads(raw_state)
                    if isinstance(candidate_state, dict):
                        working_state = candidate_state
                if raw_forming:
                    candidate_forming = json.loads(raw_forming)
                    if isinstance(candidate_forming, dict):
                        forming_state = candidate_forming
            except Exception:
                working_state = {}
        with self._working_state_lock:
            if working_state:
                self._working_state = working_state
            elif self._working_state:
                working_state = self._working_state
        working_candles = [bar for timeframe in CHART_TIMEFRAMES
                           for bar in (working_state.get("timeframes", {}).get(timeframe, ()) or ())
                           if isinstance(bar, dict)]
        candles = merge_candles(durable_candles, working_candles)
        by_timeframe = {timeframe: [row for row in candles if row["timeframe"] == timeframe]
                        for timeframe in CHART_TIMEFRAMES}
        forming_by_timeframe = {timeframe: next((dict(row) for row in forming_state.get("bars", ())
                                                  if isinstance(row, dict) and row.get("timeframe") == timeframe), None)
                                for timeframe in CHART_TIMEFRAMES}
        relationships = [dict(row) for row in working_state.get("mtf_relationships", ())
                         if isinstance(row, dict)]
        zones = [{key: row.get(key) for key in ("zone_id", "timeframe", "lower", "upper", "lifecycle_state")}
                 for row in working_state.get("zones", ()) if isinstance(row, dict)]
        expectation_event = latest.get("TIMEFRAME_EXPECTATION_RECORDED") or {}
        outcome_event = latest.get("TIMEFRAME_EXPECTATION_ASSESSED") or {}
        return {
            "schema_version": "VNEXT_WEB_STATUS_V2",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "architecture": "V2/vNext",
            "freshness_seconds": freshness,
            "latest": latest,
            "counts_24h": counts,
            "recent_events": recent,
            "history": {"window_days": 7, "totals": totals, "hourly": hourly, "daily": daily},
            "trades": {
                "scope": "V2_ORDER_ATTEMPTS",
                "scope_note": "This page contains every V2 ORDER_SUBMITTED record. V2 does not yet persist a complete fill-to-close trade journal, so broker attempts are not presented as completed trades or P&L.",
                "records": trade_records,
            },
            "system_health": self._health_probe.snapshot(latest),
            "market_data": {
                "schema_version": "VNEXT_WEB_MARKET_DATA_V1",
                "pair": pair,
                "frontier_utc": working_state.get("time_frontier_utc"),
                "working_memory_available": bool(working_state),
                "timeframes": by_timeframe,
                "forming": forming_by_timeframe,
                "forming_display_only": True,
                "relationships": relationships,
                "zones": zones,
                "timeframe_audit": {
                    "expectation": expectation_event.get("payload"),
                    "outcome": outcome_event.get("payload"),
                    "method": "LAST_COMPLETED_CANDLE_CONTINUATION_BASELINE_V1",
                    "non_authoritative": True,
                    "training_eligible": False,
                },
            },
        }


def make_handler(reader: LedgerDashboardReader, web_root: Path = WEB_ROOT):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "QuantLLMVNextWeb/1.0"

        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in PAGE_ROUTES:
                path = "/"
            if path == "/healthz":
                self._send(HTTPStatus.OK, b'{"status":"ok","read_only":true}', "application/json")
                return
            if path == "/api/status":
                try:
                    payload = reader.snapshot()
                    body = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
                    self._send(HTTPStatus.OK, body, "application/json; charset=utf-8")
                except Exception as exc:
                    body = json.dumps({"error": "status_unavailable", "detail": str(exc)[:240]}).encode("utf-8")
                    self._send(HTTPStatus.SERVICE_UNAVAILABLE, body, "application/json; charset=utf-8")
                return
            asset = ASSETS.get(path)
            if asset is None:
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain; charset=utf-8")
                return
            file_name, content_type = asset
            self._send(HTTPStatus.OK, (web_root / file_name).read_bytes(), content_type)

        def do_POST(self) -> None:  # noqa: N802
            self._send(HTTPStatus.METHOD_NOT_ALLOWED, b"Read-only service", "text/plain; charset=utf-8")

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def log_message(self, format: str, *args: Any) -> None:
            print(f"vnext-web {self.address_string()} {format % args}", flush=True)

    return DashboardHandler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("vNext web service is localhost-only")
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    reader = LedgerDashboardReader(os.environ.get("QWEN_TIMESCALE_DSN", ""))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(reader))
    print(f"vNext read-only dashboard: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
