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
    GET /api/trading                     trading pipeline: mode, counters, recent the model
                                         decisions and trades (config/trading.json)

Replay page (verify the engine day by day, see replay.py):

    GET  /api/replay/days                    days that have M1 bars
    GET  /api/replay/day?date=2026-10-01     the day's detections + your verdicts
    GET  /api/replay/chart?date=&tf=&t=&bars= the chart as the engine knew it at t
    GET  /api/replay/checks?date=            automatic checks (invariants, determinism,
                                             no-repaint, independent audit)
    GET  /api/reviews/summary?from=&to=      scorecard of your verdicts per kind
    POST /api/reviews                        save a verdict {id, day, kind, tf, time,
                                             verdict: correct|wrong|missed, note}
    POST /api/reviews/delete                 {id}: remove a verdict
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from structure_engine.config import load_config
from structure_engine.engine import StructureEngine

from . import mt5_connection, overlays, replay as replay_mod
from .database import Database
from .market_feed import LivePoller, connect_mt5, mt5_history
from .settings import Settings

log = logging.getLogger("quantllm")
# The website, built once with `npm run build` (static export), is served by
# this same server at http://127.0.0.1:8765/ — no separate web server needed.
WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "out"
TFS = ("M1", "M5", "M15", "M30", "H1", "H4")
LEVEL_FEED = {"level_test", "level_rejection", "level_followthrough", "level_held", "level_broken", "level_pattern"}


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
        self.vwap = {tf: deque(maxlen=settings.keep_bars_per_tf) for tf in TFS}   # (time, values)
        self.replays = replay_mod.ReplayCache()
        self.replay_lock = threading.Lock()
        self.mt5 = None
        self.pipeline = None                      # trading pipeline (config/trading.json mode paper/demo)
        self.journal = None
        self.broker = None
        self._stop = threading.Event()

    # ---------------------------------------------------------------- engine
    def _push(self, bar) -> list:
        with self.lock:
            evs = self.engine.push(bar)
            for tf, closed in self.engine.closed_now.items():
                if closed:
                    v = self.engine.vwap.values()
                    self.bars[tf].extend(closed)
                    self.vwap[tf].extend((c.time, v) for c in closed)
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
        changed = (state, message) != (self.status["state"], self.status["message"])
        self.status["state"], self.status["message"] = state, message
        if progress is not None:
            self.status["progress"] = round(progress, 3)
        if changed:                                        # log changes, not every 2-second poll
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
        # stored bar times must be real UTC (gold's daily break at 17:00 New York)
        recent = [b.time for b in self.db.candles_between(self.symbol, last - 5 * 86400, last + 60)]
        clock = replay_mod.clock_check(recent)
        if not clock["ok"]:
            bad = ", ".join(sorted({x["ny"] for x in clock["breaks"] if not x["ok"]}))
            self.status["clock"] = (f"STORED BAR TIMES ARE NOT UTC: daily break found at {bad} New York "
                                    "instead of 17:00. Stop the app and run: python -m quantllm "
                                    "reimport-mt5 --from <first day> --yes")
            log.error(self.status["clock"])
        else:
            self.status["clock"] = "ok"
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
                    bar_events = self._push(b)
                    evs.extend(bar_events)
                    self._trade(b, bar_events)
                self.db.insert_events(self.symbol, evs)
            self._stop.wait(self.s.poll_seconds)

    def run(self) -> None:
        while self.db is None and not self._stop.is_set():
            self._set("starting", "connecting to the database")
            try:
                self.db = Database(self.s.db_dsn, self.s.db_schema)
            except Exception as exc:                        # e.g. Docker not started yet
                self.status["database"] = f"unreachable: {exc}"
                self._set("waiting", "database unreachable - is the TimescaleDB container running? retrying in 10 s")
                self._stop.wait(10)
        if self.db is None:
            return
        self.status["database"] = f"{self.s.db_schema} ({'TimescaleDB' if self.db.timescale else 'PostgreSQL'})"
        self.import_history()
        self.replay()
        self.start_trading()
        self.live_loop()

    # ---------------------------------------------------------------- trading (Part F)
    def start_trading(self) -> None:
        """Build the decision pipeline when config/trading.json mode is paper or demo.

        Only LIVE bars go through it (never the history replay). the model is asked
        inside the live loop; with the GPU and a prompt under 6 KB that takes
        seconds, and a candidate stays valid for its whole test window.
        """
        from trading.settings import load_settings as trading_settings
        try:
            ts = trading_settings()
        except ValueError as exc:
            self.status["trading"] = f"settings error: {exc}"
            log.error(self.status["trading"])
            return
        self.status["trading"] = ts.mode
        if ts.mode == "off":
            return
        from llm.decider import LLMDecider
        from strategy import load as load_strategy
        from trading.broker import MT5Broker, PaperBroker
        from trading.executor import Executor
        from trading.journal import DbJournal
        from trading.pipeline import Pipeline
        from trading.risk import XAUUSD_DEFAULT as XAU
        strat = load_strategy(ts.strategy, ts.strategy_version)
        if ts.mode == "demo":
            if self.mt5 is None:
                self.status["trading"] = "demo: waiting for MT5 (not connected) - trading off"
                return
            broker = MT5Broker(self.mt5, mt5_connection.server_to_utc_epoch)
            if not broker.account()["demo"]:
                self.status["trading"] = "REFUSED: the MT5 account is not a demo account"
                log.error(self.status["trading"])
                return
        else:
            spec = MT5Broker(self.mt5, mt5_connection.server_to_utc_epoch).spec(self.symbol) if self.mt5 else XAU
            broker = PaperBroker(spec)
        self.journal = DbJournal(self.db.conn)
        self.broker = broker
        from llm import LLMClient, LLMError
        client = LLMClient()
        try:
            info = client.ping()
            self.status["model"] = f"{info.get('identity') or info['model']} ({info['api']}, reasoning "\
                                   f"{info['reasoning_effort']})"
        except LLMError as exc:
            self.status["model"] = f"NOT reachable ({exc}) - start Start-LLM.bat; decisions are journaled as invalid"
            log.error("model server: %s", self.status["model"])
        self.pipeline = Pipeline(strat, self.engine, LLMDecider(client),
                                 Executor(broker, ts, self.symbol, self.journal), self.journal, mode=ts.mode,
                                 clock=time.time)
        self.status["trading"] = f"{ts.mode}: {strat.ref}, risk {ts.risk_pct}% per trade"
        log.info("trading %s", self.status["trading"])

    def _trade(self, bar, events) -> None:
        if self.pipeline is None:
            return
        try:
            if hasattr(self.broker, "on_bar"):                # paper broker: stops/targets inside the bar
                self.broker.on_bar(bar)
            # No lock: the pipeline only READS the engine, from this same live
            # thread that writes it — holding the lock through a model call
            # would freeze the website for the seconds the model thinks.
            self.pipeline.on_bar(bar, events, self.engine.now)
        except Exception:                                     # never stop the structure feed
            log.exception("trading pipeline error")

    def trading_view(self) -> dict:
        j = self.journal
        return {"status": self.status.get("trading", "off"), "model": self.status.get("model"),
                "stats": self.pipeline.stats if self.pipeline else None,
                "decisions": [{k: d.get(k) for k in ("id", "time", "action", "label", "candidate_key", "confidence",
                                                      "why", "errors", "latency_ms", "prompt_bytes", "model")}
                              for d in (j.decisions[-30:] if j else [])][::-1],
                "trades": list(j.trades.values())[-50:][::-1] if j else []}

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
                         "time": g.time, "status": g.status} for g in self.engine.gaps.active]
                     + [{"kind": "hlevel", **lv.as_dict()} for lv in self.engine.levels.active])
            ov = overlays.build(evs, tf, t_from, self.engine.now, self.snap(tf), snap_dict, alive)
            ov["curves"] = replay_mod.vwap_curves(list(self.vwap[tf]), t_from, self.engine.now)
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
                "event_counts": s["event_counts"], "vwap": s["vwap"], "htf_levels": s["htf_levels"],
                "recent_level_events": [
                    {"kind": e["kind"], "time": e["time"], "level": e["data"]["level"]["price"],
                     "side": e["data"]["level"]["side"], "sources": e["data"]["level"]["sources"],
                     "test_no": e["data"].get("test_no"), "result": e["data"].get("result"),
                     "approach": e["data"].get("approach"), "pattern": e["data"].get("pattern")}
                    for e in [x for x in self.events if x["kind"] in LEVEL_FEED][-12:][::-1]],
            }

    # ---------------------------------------------------------------- replay
    def replay_day(self, date: str) -> replay_mod.ReplayDay:
        """Build (or reuse) the engine run for one UTC day from stored M1 bars."""
        replay_mod.day_bounds(date)                       # validates the date
        with self.replay_lock:                            # one build at a time
            def build():
                start, end = replay_mod.day_bounds(date)
                bars = self.db.candles_between(self.symbol, start - self.s.replay_warmup_days * 86400,
                                               end + self.s.replay_after_hours * 3600)
                if not any(start <= b.time < end for b in bars):
                    raise LookupError(f"no M1 bars stored for {date}")
                return replay_mod.ReplayDay(bars, self.cfg, date, self.s.replay_warmup_days,
                                            self.s.replay_after_hours)
            return self.replays.get(date, build)

    def replay_checks(self, date: str) -> dict:
        if date not in self.replays.checks:
            self.replays.checks[date] = self.replay_day(date).checks()
        return self.replays.checks[date]


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
                elif url.path == "/api/trading":
                    self._send(200, service.trading_view())
                elif url.path == "/api/replay/days":
                    self._send(200, {"days": service.db.days_with_data(service.symbol)})
                elif url.path == "/api/replay/day":
                    day = service.replay_day(q["date"])
                    self._send(200, {"date": day.date, "start": day.day_start, "end": day.day_end,
                                     "detections": day.detections(),
                                     "reviews": service.db.reviews(service.symbol, day.date),
                                     "checks": service.replays.checks.get(day.date)})
                elif url.path == "/api/replay/chart":
                    tf = q.get("tf", "M15")
                    if tf not in TFS:
                        return self._send(400, {"error": f"tf must be one of {TFS}"})
                    day = service.replay_day(q["date"])
                    t = int(q.get("t", day.day_end))
                    self._send(200, day.chart(tf, t, max(20, min(int(q.get("bars", 300)), 2000))))
                elif url.path == "/api/replay/checks":
                    self._send(200, service.replay_checks(q["date"]))
                elif url.path == "/api/reviews/summary":
                    self._send(200, service.db.review_summary(service.symbol, q["from"], q["to"]))
                else:
                    self._send(404, {"error": "unknown endpoint"})
            except (KeyError, ValueError, LookupError) as exc:   # bad / missing parameter, no data
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:                        # never take the API down
                log.exception("API error")
                self._send(500, {"error": str(exc)})

        def do_OPTIONS(self) -> None:  # noqa: N802         # CORS preflight (npm run dev)
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            try:
                n = int(self.headers.get("Content-Length", 0))
                if n > 100_000:
                    return self._send(413, {"error": "body too large"})
                body = json.loads(self.rfile.read(n) or b"{}")
                if url.path == "/api/reviews":
                    if body.get("verdict") not in ("correct", "wrong", "missed"):
                        return self._send(400, {"error": "verdict must be correct, wrong or missed"})
                    replay_mod.day_bounds(body["day"])
                    body["note"] = str(body.get("note", ""))[:2000]
                    service.db.save_review(service.symbol, body)
                    self._send(200, {"ok": True})
                elif url.path == "/api/reviews/delete":
                    service.db.delete_review(body["id"])
                    self._send(200, {"ok": True})
                else:
                    self._send(404, {"error": "unknown endpoint"})
            except (KeyError, ValueError) as exc:
                self._send(400, {"error": f"{type(exc).__name__}: {exc}"})
            except Exception as exc:
                log.exception("API error")
                self._send(500, {"error": str(exc)})

        def log_message(self, *args) -> None:               # keep the console quiet
            return

    return Handler


class _Server(ThreadingHTTPServer):
    """HTTP server that refuses a port another process already holds.

    Python's default (SO_REUSEADDR) lets a SECOND server bind the same port on
    Windows; requests then keep going to the OLD process while the new one
    looks fine. Seen 2026-10-31: a restarted service kept serving old code.
    """
    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        """A browser that closes the connection mid-answer (reload, tab closed,
        a newer refresh replacing an older one) is normal, not an error:
        Windows reports it as WinError 10053/10054. Log anything else."""
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        log.exception("HTTP request from %s failed", client_address)


def serve(settings: Settings, use_mt5: bool = True) -> None:
    try:
        httpd = _Server((settings.api_host, settings.api_port), None)
    except OSError as exc:
        log.error("port %d is already in use (%s): QuantLLM is probably still running. "
                  "Close it, or use Restart-QuantLLM.bat.", settings.api_port, exc)
        raise SystemExit(1)
    service = StructureService(settings, use_mt5)
    httpd.RequestHandlerClass = make_handler(service)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    log.info("API on http://%s:%d/api/health", settings.api_host, settings.api_port)
    try:
        service.run()
    except KeyboardInterrupt:
        pass
    finally:
        service.stop()
        httpd.shutdown()
