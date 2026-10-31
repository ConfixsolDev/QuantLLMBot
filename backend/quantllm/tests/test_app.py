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


def _gold_minutes_utc(day0: int, days: int) -> list[int]:
    """UTC M1 open times of gold: daily break 17:00-18:00 New York, closed from
    Friday 17:00 to Sunday 18:00 New York."""
    import time as _t
    from structure_engine.clock import new_york_offset_hours
    out = []
    for t in range(day0, day0 + days * 86400, 60):
        ny = t + new_york_offset_hours(t) * 3600
        wd, hour = _t.gmtime(ny).tm_wday, (ny % 86400) // 3600      # Monday = 0
        if hour == 17 or wd == 5 or (wd == 4 and hour >= 17) or (wd == 6 and hour < 18):
            continue
        out.append(t)
    return out


@pytest.mark.parametrize("rule", ["utc", "ny_close", 2])
def test_broker_clock_is_detected_from_the_daily_break(rule):
    from quantllm import mt5_connection as m
    utc = _gold_minutes_utc(1_793_000_000 - 1_793_000_000 % 86400, 12)      # spans the 1 Nov DST change
    server = []
    for t in utc:                                                           # utc -> broker clock
        off = 0 if rule == "utc" else 2 if rule == 2 else (3 if m._us_dst_active(
            __import__("datetime").datetime.fromtimestamp(t, tz=__import__("datetime").timezone.utc)) else 2)
        server.append(t + off * 3600)
    det = m.detect_server_time(server)
    assert det["rule"] == rule and det["breaks"] >= 7
    assert [m.server_to_utc_epoch(s, det["rule"]) for s in server] == utc


def test_wrong_broker_clock_setting_refuses_to_import(monkeypatch):
    from dataclasses import replace as dc_replace
    from quantllm import mt5_connection as m
    utc = _gold_minutes_utc(1_792_000_000 - 1_792_000_000 % 86400, 6)

    class Fake:
        TIMEFRAME_M1 = 1

        def copy_rates_from_pos(self, symbol, tf, start, n):
            return [{"time": t} for t in utc[-n:]]                      # broker reports UTC
    monkeypatch.setattr(m, "_CACHED", dc_replace(m.MT5Settings(), server_time="ny_close"))
    with pytest.raises(RuntimeError, match="broker clock check FAILED"):
        m.resolve_server_time(Fake(), "XAU")
    monkeypatch.setattr(m, "_CACHED", dc_replace(m.MT5Settings(), server_time="auto"))
    assert m.resolve_server_time(Fake(), "XAU")["using"] == "utc" and m.settings().server_time == "utc"


def test_replay_clock_check_flags_shifted_bars():
    from quantllm.replay import clock_check
    utc = _gold_minutes_utc(1_792_000_000 - 1_792_000_000 % 86400, 3)
    assert clock_check(utc)["ok"] and len(clock_check(utc)["breaks"]) >= 2
    shifted = [t - 3 * 3600 for t in utc]                                  # the bug seen on 2026-10-31
    assert not clock_check(shifted)["ok"]
