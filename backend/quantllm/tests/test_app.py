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
import urllib.error
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
    d.conn.execute("DELETE FROM reviews")
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
        assert c["candles"] and set(c["overlays"]) == {"lines", "boxes", "markers", "levels", "swings", "curves", "hlevels"}
        times = {k["time"] for k in c["candles"]}
        for ln in c["overlays"]["lines"]:
            assert ln["t2"] in times                              # snapped onto real candles
    snap = get("/api/snapshot")
    assert set(snap["trend"]) == {"M5", "M15", "M30", "H1", "H4"} and snap["price"] == bars[-1].close
    assert set(snap["vwap"]) == {"day", "week", "session"}
    svc.stop()
    httpd.shutdown()


def test_replay_day_and_reviews_api(db, dsn):
    """Replay a stored day: detections, point-in-time chart, automatic checks, verdicts."""
    from http.server import ThreadingHTTPServer
    from quantllm import replay
    from quantllm.service import StructureService, make_handler
    from quantllm.settings import Settings
    bars = random_walk_m1(7, 5 * 1440)
    db.insert_candles("XAUUSDr", bars)
    s = replace(Settings(), db_dsn=dsn, db_schema="quantllm_test", replay_warmup_days=2, replay_after_hours=6)
    svc = StructureService(s, use_mt5=False, db=db)
    svc.symbol = "XAUUSDr"
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    get = lambda p: json.loads(urllib.request.urlopen(base + p, timeout=60).read())  # noqa: E731

    def post(p, body):
        req = urllib.request.Request(base + p, json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())

    date = time.strftime("%Y-%m-%d", time.gmtime(bars[0].time + 3 * 86400))
    start, end = replay.day_bounds(date)
    assert date in get("/api/replay/days")["days"]
    day = get(f"/api/replay/day?date={date}")
    det = day["detections"]
    assert det and all(start <= d["available_at"] < end for d in det)
    assert len({d["id"] for d in det}) == len(det)

    # the chart at noon never shows anything the engine could not know at noon
    noon = start + 12 * 3600
    c = get(f"/api/replay/chart?date={date}&tf=M15&t={noon}&bars=200")
    assert c["candles"] and all(k["time"] + 900 <= noon for k in c["candles"])
    assert c["future"] and all(k["time"] + 900 > noon for k in c["future"])
    assert all(m["time"] <= noon for m in c["overlays"]["markers"])
    assert set(c["overlays"]["curves"]) == {"day", "week", "session"}

    chk = get(f"/api/replay/checks?date={date}")
    for k in ("invariants", "determinism", "no_repaint", "audit"):
        assert chk[k]["ok"], (k, chk[k])

    e = det[0]
    post("/api/reviews", {"id": e["id"], "day": date, "kind": e["kind"], "tf": e["tf"], "time": e["time"],
                          "verdict": "correct", "note": "ok"})
    post("/api/reviews", {"id": det[1]["id"], "day": date, "kind": det[1]["kind"], "tf": det[1]["tf"],
                          "time": det[1]["time"], "verdict": "wrong"})
    post("/api/reviews", {"id": f"missed-{date}-1", "day": date, "kind": "liquidity_sweep", "tf": "M5",
                          "time": noon, "verdict": "missed", "note": "sweep of Asia high not marked"})
    post("/api/reviews", {"id": e["id"], "day": date, "kind": e["kind"], "tf": e["tf"], "time": e["time"],
                          "verdict": "correct", "note": "changed my mind twice"})          # upsert
    revs = get(f"/api/replay/day?date={date}")["reviews"]
    assert len(revs) == 3 and {r["verdict"] for r in revs} == {"correct", "wrong", "missed"}
    summ = get(f"/api/reviews/summary?from={date}&to={date}")
    assert summ["days_reviewed"] == 1
    assert sum(k["correct"] + k["wrong"] + k["missed"] for k in summ["kinds"]) == 3
    post("/api/reviews/delete", {"id": f"missed-{date}-1"})
    assert len(get(f"/api/replay/day?date={date}")["reviews"]) == 2
    with pytest.raises(urllib.error.HTTPError) as err:
        post("/api/reviews", {"id": "x", "day": date, "kind": "bos", "tf": "M5", "verdict": "maybe"})
    assert err.value.code == 400
    httpd.shutdown()


def test_server_refuses_a_port_that_is_already_in_use():
    """A second QuantLLM must fail loudly, not share the port with the old one."""
    from quantllm.service import _Server
    first = _Server(("127.0.0.1", 0), None)
    try:
        with pytest.raises(OSError):
            _Server(("127.0.0.1", first.server_address[1]), None)
    finally:
        first.server_close()
