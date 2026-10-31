"""The running application: database + MT5 + structure engine + HTTP API.

Start (from ``backend/``)::

    python -m quantllm serve

What happens, in order
----------------------
1. API up immediately on http://127.0.0.1:8765 (status "starting").
2. History: connect to MT5 and copy every closed M1 bar the database does not
   have yet, back to ``history_days`` (status "importing"). If MT5 is not
   available the service continues with what the database already holds.
3. Replay: the last ``replay_days`` of stored M1 bars are pushed through a
   fresh StructureEngine; the ``events`` table is rebuilt from that run
   (status "replaying", with progress).
4. Live: every ``poll_seconds`` new CLOSED M1 bars from MT5 are stored and
   pushed through the same engine; their events are stored (status "live").
   Without MT5 the service stays up ("offline") and retries every 30 s.

The website (web/out, built once) is served at http://127.0.0.1:8765/ and
reads three endpoints (all JSON, CORS open for localhost):

    GET /api/health                      status, progress, last bar, counts
    GET /api/chart?tf=M15&bars=300       closed candles + forming candle + overlays
    GET /api/snapshot                    what the engine thinks right now
"""

from __future__ import annotations

import json
import logging
import mimetypes
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from structure_engine.config import load_config
from structure_engine.engine import StructureEngine

from . import mt5_connection, overlays
from .database import Database
from .market_feed import LivePoller, connect_mt5, mt5_history
from .settings import Settings

log = logging.getLogger("quantllm")
# The website, built once with `npm run build` (static export), is served by
# this same server at http://127.0.0.1:8765/ — no separate web server needed.
WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "out"
TFS = ("M1", "M5", "M15", "M30", "H1", "H4")


class StructureService:
    def __init__(self, settings: Settings, use_mt5: bool = True, db: Database | None = None) -> None:
        self.s = settings
        self.use_mt5 = use_mt5
        self.db = db
        self.symbol = mt5_connection.settings().broker_symbol
        self.cfg = load_config()
        self.lock = threading.RLock()
        self.engine = StructureEngine(self.cfg)
        self.bars = {tf: deque(maxlen=settings.keep_bars_per_tf) for tf in TFS}
        self.events: deque = deque(maxlen=settings.keep_events)
        self.status = {"state": "starting", "progress": 0.0, "message": "", "mt5": "not connected",
                       "symbol": self.symbol, "config_id": self.cfg["config_id"],
                       "config_hash": self.cfg.config_hash, "last_bar": None, "bars_processed": 0,
                       "events": 0, "started_at": int(time.time())}
        self.mt5 = None
        self._stop = threading.Event()

    # ---------------------------------------------------------------- engine
    def _push(self, bar) -> list:
        with self.lock:
            evs = self.engine.push(bar)
            for tf, closed in self.engine.closed_now.items():
                self.bars[tf].extend(closed)
            self.events.extend(e.as_dict() for e in evs)
            self.status["last_bar"] = bar.time
            self.status["bars_processed"] += 1
            self.status["events"] += len(evs)
        return evs

    def snap(self, tf: str):
        if tf == "M1":
            return lambda t: t - t % 60
        agg = self.engine.aggs[tf]
        return lambda t: agg._span(t)[0]

    # ---------------------------------------------------------------- startup
    def _set(self, state: str, message: str = "", progress: float | None = None) -> None:
        self.status["state"], self.status["message"] = state, message
        if progress is not None:
            self.status["progress"] = round(progress, 3)
        log.info("%s %s", state, message)

    def import_history(self) -> None:
        if not self.use_mt5:
            return
        try:
            self.mt5 = connect_mt5()
            self.status["mt5"] = "connected"
        except Exception as exc:                            # MT5 missing / closed / wrong symbol
            self.status["mt5"] = f"unavailable: {exc}"
            return
        now = int(time.time())
        last = self.db.last_candle_time(self.symbol)
        since = max(last + 60 if last else 0, now - self.s.history_days * 86400)
        total, span = 0, max(1, now - since)
        for chunk in mt5_history(self.mt5, self.symbol, since):
            total += self.db.insert_candles(self.symbol, chunk)
            self._set("importing", f"{total} new M1 bars from MT5", (chunk[-1].time - since) / span)
        self._set("importing", f"{total} new M1 bars from MT5", 1.0)

    def replay(self) -> None:
        last = self.db.last_candle_time(self.symbol)
        if last is None:
            self._set("waiting", "no M1 bars in the database yet: run import-csv or connect MT5")
            return
        start = last - self.s.replay_days * 86400
        self.db.clear_events(self.symbol)
        batch, span = [], max(1, last - start)
        for bar in self.db.iter_candles(self.symbol, start):
            batch.extend(self._push(bar))
            if len(batch) >= 5000:
                self.db.insert_events(self.symbol, batch)
                batch = []
                self._set("replaying", f"structure rebuilt up to {_iso(bar.time)}", (bar.time - start) / span)
        self.db.insert_events(self.symbol, batch)
        self.db.set_state("last_replay", {"symbol": self.symbol, "from": start, "to": last,
                                          "config_hash": self.cfg.config_hash})

    def live_loop(self) -> None:
        poller = None
        while not self._stop.is_set():
            if self.mt5 is None and self.use_mt5:
                try:
                    self.mt5 = connect_mt5()
                    self.status["mt5"] = "connected"
                except Exception as exc:
                    self.status["mt5"] = f"unavailable: {exc}"
                    self._set("offline", "showing stored data; MT5 not connected (retrying every 30 s)")
                    self._stop.wait(30)
                    continue
            if self.mt5 is None:
                self._set("offline", "MT5 disabled (--no-mt5); showing stored data")
                self._stop.wait(3600)
                continue
            if poller is None:
                poller = LivePoller(self.mt5, self.symbol, self.status["last_bar"])
            self._set("live", "", 1.0)
            try:
                new = poller.poll()
            except Exception as exc:                        # keep the service alive
                log.warning("poll failed: %s", exc)
                new = []
            if new:
                self.db.insert_candles(self.symbol, new)
                evs = []
                for b in new:
                    evs.extend(self._push(b))
                self.db.insert_events(self.symbol, evs)
            self._stop.wait(self.s.poll_seconds)

    def run(self) -> None:
        self._set("starting", "connecting to the database")
        if self.db is None:
            self.db = Database(self.s.db_dsn, self.s.db_schema)
        self.status["database"] = f"{self.s.db_schema} ({'TimescaleDB' if self.db.timescale else 'PostgreSQL'})"
        self.import_history()
        self.replay()
        self.live_loop()

    def stop(self) -> None:
        self._stop.set()

    # ---------------------------------------------------------------- API data
    def chart(self, tf: str, n: int) -> dict:
        with self.lock:
            candles = list(self.bars[tf])[-n:]
            forming = None
            if tf != "M1" and self.engine.aggs[tf].current is not None:
                forming = self.engine.aggs[tf].current.as_dict()
            if not candles:
                return {"tf": tf, "candles": [], "forming": forming, "overlays": None, "as_of": self.engine.now}
            t_from = candles[0].time
            evs = [e for e in self.events if e["available_at"] >= t_from]
            snap_dict = {"levels": list(self.engine.sessions.levels)[-40:], "forming": self.engine.sessions.forming()}
            alive = ([{"kind": "zone", "id": z.id, "tf": z.tf, "side": z.side, "low": z.low, "high": z.high,
                       "time": z.time, "status": z.status, "tests": z.tests} for z in self.engine.zones.active]
                     + [{"kind": "ob", "id": o.id, "tf": o.tf, "side": o.direction, "low": o.low, "high": o.high,
                         "time": o.time, "status": o.status, "tests": o.tests} for o in self.engine.obs.active]
                     + [{"kind": "fvg", "id": g.id, "tf": g.tf, "side": g.direction, "low": g.low, "high": g.high,
                         "time": g.time, "status": g.status} for g in self.engine.gaps.active])
            ov = overlays.build(evs, tf, t_from, self.engine.now, self.snap(tf), snap_dict, alive)
            return {"tf": tf, "candles": [c.as_dict() for c in candles], "forming": forming,
                    "overlays": ov, "as_of": self.engine.now}

    def snapshot(self) -> dict:
        with self.lock:
            if self.engine.now is None:
                return {"as_of": None}
            s = self.engine.snapshot(swings_per_tf=5, levels=12)
            price = self.engine._last_close
            recent = [e for e in self.events if e["kind"] in overlays.LIQ][-12:]
            return {
                "as_of": s["as_of"], "price": price, "config_hash": s["config_hash"], "atr": s["atr"],
                "trend": s["trend"], "liquidity_pools": s["liquidity_pools"],
                "recent_liquidity": [{"kind": e["kind"], "side": e["data"]["side"], "time": e["data"]["candle"]["time"],
                                      "levels": [(lv["kind"], lv["price"]) for lv in e["data"]["levels"]]}
                                     for e in reversed(recent)],
                "top_zones": s["top_zones"][:6], "order_blocks": sorted(
                    s["order_blocks"], key=lambda o: abs((o["low"] + o["high"]) / 2 - price))[:8],
                "fair_value_gaps": s["fair_value_gaps"][:8], "ranges": s["ranges"],
                "levels": s["levels"], "forming": {k: v for k, v in s["forming"].items() if k != "bars"},
                "pending_patterns": s["pending_patterns"], "open_spikes": s["open_spikes"],
                "event_counts": s["event_counts"],
            }


def _iso(t: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(t))


def make_handler(service: StructureService):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _static(self, path: str) -> None:
            rel = unquote(path).lstrip("/") or "index.html"
            f = (WEB_DIR / rel).resolve()
            if f.is_dir():
                f = f / "index.html"
            if WEB_DIR.resolve() not in f.parents or not f.is_file():
                if not WEB_DIR.exists():
                    body = b"Website not built yet: run  npm install && npm run build  in the web folder."
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                return self._send(404, {"error": "not found"})
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                return self._static(url.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/api/health":
                    self._send(200, service.status)
                elif url.path == "/api/chart":
                    tf = q.get("tf", "M15")
                    if tf not in TFS:
                        return self._send(400, {"error": f"tf must be one of {TFS}"})
                    n = max(20, min(int(q.get("bars", 300)), service.s.keep_bars_per_tf))
                    self._send(200, service.chart(tf, n))
                elif url.path == "/api/snapshot":
                    self._send(200, service.snapshot())
                else:
                    self._send(404, {"error": "unknown endpoint"})
            except Exception as exc:                        # never take the API down
                log.exception("API error")
                self._send(500, {"error": str(exc)})

        def log_message(self, *args) -> None:               # keep the console quiet
            return

    return Handler


def serve(settings: Settings, use_mt5: bool = True) -> None:
    service = StructureService(settings, use_mt5)
    httpd = ThreadingHTTPServer((settings.api_host, settings.api_port), make_handler(service))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log.info("API on http://%s:%d/api/health", settings.api_host, settings.api_port)
    try:
        service.run()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        httpd.shutdown()
