"""Application tests: database, MT5 polling (fake), service replay, HTTP API.

    python -m pytest quantllm/tests -q        (from backend/)

The database tests need PostgreSQL. They use ``QUANTLLM_TEST_DSN`` if set,
else a throw-away server from the ``pgserver`` package if installed, else skip.
They write only to the schema ``quantllm_test``.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from structure_engine.verification.synthetic import random_walk_m1  # noqa: E402


@pytest.fixture(scope="module")
def dsn(tmp_path_factory):
    if os.environ.get("QUANTLLM_TEST_DSN"):
        return os.environ["QUANTLLM_TEST_DSN"]
    pgserver = pytest.importorskip("pgserver")
    pytest.importorskip("psycopg")
    srv = pgserver.get_server(str(tmp_path_factory.mktemp("pg")), cleanup_mode="stop")
    return srv.get_uri()


@pytest.fixture()
def db(dsn):
    from quantllm.database import Database
    d = Database(dsn, "quantllm_test")
    d.conn.execute("DELETE FROM m1_candles")
    d.conn.execute("DELETE FROM events")
    yield d
    d.close()


def test_candles_round_trip_and_idempotent(db):
    bars = random_walk_m1(1, 3000)
    assert db.insert_candles("XAU", bars) == 3000
    assert db.insert_candles("XAU", bars[:100]) == 0          # already stored
    back = list(db.iter_candles("XAU", bars[1000].time))
    assert [(b.time, b.close) for b in back] == [(b.time, b.close) for b in bars[1000:]]
    assert db.last_candle_time("XAU") == bars[-1].time


class FakeMT5:
    TIMEFRAME_M1 = 1

    def __init__(self, bars):
        self.bars = bars
        self.visible = 0

    def copy_rates_from_pos(self, symbol, tf, start, count):
        # position 0 (the forming bar) is excluded by start=1
        upto = self.bars[: self.visible]
        return [{"time": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                 "tick_volume": b.volume} for b in upto[-count:]]


def test_live_poller_returns_only_new_closed_bars(monkeypatch):
    from quantllm import market_feed, mt5_connection
    monkeypatch.setattr(mt5_connection, "server_to_utc_epoch", lambda t, rule=None: t)
    bars = random_walk_m1(2, 50)
    fake = FakeMT5(bars)
    p = market_feed.LivePoller(fake, "XAU", None)
    fake.visible = 10
    assert [b.time for b in p.poll()] == [b.time for b in bars[:10]]
    assert p.poll() == []
    fake.visible = 13
    assert [b.time for b in p.poll()] == [b.time for b in bars[10:13]]


def test_service_replays_stores_events_and_serves_api(db, dsn, monkeypatch):
    from http.server import ThreadingHTTPServer
    from quantllm.service import StructureService, make_handler
    from quantllm.settings import Settings
    bars = random_walk_m1(5, 6 * 1440)
    db.insert_candles("XAUUSDr", bars)
    s = replace(Settings(), db_dsn=dsn, db_schema="quantllm_test", replay_days=30, api_port=0)
    svc = StructureService(s, use_mt5=False, db=db)
    svc.symbol = "XAUUSDr"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    threading.Thread(target=svc.run, daemon=True).start()
    get = lambda p: json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}{p}", timeout=20).read())  # noqa: E731
    for _ in range(120):
        if get("/api/health")["state"] == "offline":
            break
        time.sleep(0.5)
    h = get("/api/health")
    assert h["state"] == "offline" and h["bars_processed"] == len(bars)
    assert db.event_count("XAUUSDr") == h["events"]                 # every event stored once
    for tf in ("M1", "M5", "M15", "H1", "H4"):
        c = get(f"/api/chart?tf={tf}&bars=200")
        assert c["candles"] and set(c["overlays"]) == {"lines", "boxes", "markers", "levels", "swings"}
        times = {k["time"] for k in c["candles"]}
        for ln in c["overlays"]["lines"]:
            assert ln["t2"] in times                              # snapped onto real candles
    snap = get("/api/snapshot")
    assert set(snap["trend"]) == {"M5", "M15", "M30", "H1", "H4"} and snap["price"] == bars[-1].close
    svc.stop()
    httpd.shutdown()
