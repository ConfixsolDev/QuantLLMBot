"""Module 1 test suite. Run from backend/:

    python -m pytest structure_engine/tests -q

Every guarantee in the architecture doc (Part B) has a test here:
strict config, exact aggregation, causal swings == offline reference,
zone and pattern accuracy on planted ground truth (incl. near-miss
negatives), no repaint, determinism, invariants, sessions, and an
end-to-end back-test run through the CLI code path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # backend/

from structure_engine import Bar, StructureEngine, fingerprint, load_config, load_m1  # noqa: E402
from structure_engine.bars import BarError, aggregate  # noqa: E402
from structure_engine.config import ConfigError  # noqa: E402
from structure_engine.runner import run_stream  # noqa: E402
from structure_engine.verification.causality import determinism, invariants, no_repaint, run  # noqa: E402
from structure_engine.verification.synthetic import (  # noqa: E402
    START, expand_to_m1, pattern_series, random_walk_m1, zone_series)
from structure_engine.verification.synthetic_accuracy import (  # noqa: E402
    evaluate_patterns, evaluate_swings, evaluate_zones)

CFG = load_config()
SEEDS = (0, 1, 2)


# ------------------------------------------------------------------ config
def test_config_is_strict():
    with pytest.raises(ConfigError, match="unknown"):
        load_config(overrides={"zones": {"max_tset": 3}})
    with pytest.raises(ConfigError, match="invalid"):
        load_config(overrides={"atr": {"period": "14"}})
    with pytest.raises(ConfigError, match="declared timeframe"):
        load_config(overrides={"swings": {"strength": {"M2": 3}}})
    from structure_engine.config import DEFAULT_CONFIG, build_config
    raw = json.loads(DEFAULT_CONFIG.read_text())
    del raw["patterns"]["history"]
    with pytest.raises(ConfigError, match="missing"):
        build_config(raw)


def test_config_hash_changes_with_any_threshold_and_is_on_every_event():
    other = load_config(overrides={"zones": {"max_tests": 4}})
    assert other.config_hash != CFG.config_hash
    events = run(random_walk_m1(0, 1500), CFG)
    assert events and all(e.config_hash == CFG.config_hash for e in events)


# ------------------------------------------------------------------ bars
def test_expand_and_aggregate_round_trip_exactly():
    tf_bars = [Bar(START + 1800 * i, 10 + i, 12 + i, 9 + i, 11 + i, 300.0, minutes=30) for i in range(5)]
    back = aggregate(expand_to_m1(tf_bars, 30), "M30", 30)
    assert [(b.time, b.open, b.high, b.low, b.close) for b in back] == \
           [(b.time, b.open, b.high, b.low, b.close) for b in tf_bars]


def test_gap_closes_partial_bar_only_when_later_data_arrives():
    from structure_engine.bars import Aggregator
    agg = Aggregator("M5", 5)
    assert agg.update(Bar(START, 1, 2, 0.5, 1.5)) == []           # 00:00
    assert agg.update(Bar(START + 60, 1.5, 2, 1, 1.2)) == []      # 00:01, then a gap
    closed = agg.update(Bar(START + 600, 1, 1, 1, 1))              # 00:10 closes 00:00 bucket
    assert len(closed) == 1 and closed[0].m1_count == 2 and closed[0].close == 1.2


def test_engine_rejects_bad_bars():
    e = StructureEngine(CFG)
    e.push(Bar(START, 1, 2, 0.5, 1.5))
    with pytest.raises(BarError):
        e.push(Bar(START, 1, 2, 0.5, 1.5))                         # not increasing
    with pytest.raises(BarError):
        e.push(Bar(START + 90, 1, 2, 0.5, 1.5))                    # not minute aligned
    with pytest.raises(BarError):
        e.push(Bar(START + 120, 1, 1.2, 0.5, 1.5))                 # high below close


def test_load_m1_reads_mt5_export_format(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\n"
                 "2026.01.01\t00:00:00\t1\t2\t0.5\t1.5\t10\n"
                 "2026.01.01\t00:01:00\t1.5\t2\t1\t1.2\t12\n")
    bars = list(load_m1(p))
    assert [b.time for b in bars] == [START, START + 60] and bars[1].volume == 12


# ------------------------------------------------------------------ accuracy
@pytest.mark.parametrize("seed", SEEDS)
def test_swings_equal_offline_reference_on_every_timeframe(seed):
    for tf, score in evaluate_swings(CFG, seed).items():
        assert score.fp == 0 and score.fn == 0, (tf, score.as_dict())


@pytest.mark.parametrize("seed", SEEDS)
def test_planted_zones_found_and_weak_departures_rejected(seed):
    for tf, (score, rejected, negatives) in evaluate_zones(CFG, seed).items():
        assert score.recall == 1.0 and score.precision >= 0.9, (tf, score.as_dict())
        assert rejected == negatives, tf


@pytest.mark.parametrize("seed", SEEDS)
def test_planted_patterns_found_and_near_misses_rejected(seed):
    score, rejected, negatives = evaluate_patterns(CFG, seed)
    assert score.recall >= 0.9 and score.precision >= 0.9, score.as_dict()
    assert rejected == negatives


# ------------------------------------------------------------------ causality
def test_no_repaint_on_zone_series():
    bars = zone_series(3, "M30", 30, plants=4).m1
    assert no_repaint(bars, CFG, cuts=5, seed=1) == []


def test_no_repaint_on_pattern_series():
    bars = pattern_series(4, plants=6).m1
    assert no_repaint(bars, CFG, cuts=8, seed=2) == []


def test_determinism_and_invariants():
    bars = pattern_series(5, plants=6).m1
    assert determinism(bars, CFG)
    assert invariants(run(bars, CFG), CFG) == []
    assert invariants(run(zone_series(5, "H1", 60, plants=4).m1, CFG), CFG) == []


def test_every_event_is_known_at_the_close_of_the_bar_that_produced_it():
    e = StructureEngine(CFG)
    for bar in random_walk_m1(7, 3000):
        for ev in e.push(bar):
            assert ev.available_at == bar.close_time


# ------------------------------------------------------------------ sessions
def test_sessions_forming_then_confirmed():
    e = StructureEngine(CFG)
    levels = []
    # 00:00-07:00 UTC is ASIA; price peaks at 03:00 and bottoms at 05:00
    for i in range(7 * 60 + 1):
        p = 100 + (5 if i == 180 else 0) - (5 if i == 300 else 0)
        evs = e.push(Bar(START + 60 * i, p, p + 0.1, p - 0.1, p))
        if i < 7 * 60 - 1:
            assert e.snapshot()["forming"]["session"]["name"] == "ASIA"
        levels += [x for x in evs if x.kind == "session_level"]
    assert len(levels) == 1
    asia = levels[0].data
    assert asia["name"] == "ASIA" and asia["high"] == pytest.approx(105.1) and asia["low"] == pytest.approx(94.9)
    assert levels[0].available_at == START + 7 * 3600     # known exactly at 07:00


# ------------------------------------------------------------------ end to end
def test_backtest_run_writes_outputs_and_matches_direct_run(tmp_path):
    bars = zone_series(1, "M30", 30, plants=3).m1
    csv_path = tmp_path / "m1.csv"
    with csv_path.open("w") as fh:
        fh.write("time,open,high,low,close,tick_volume\n")
        for b in bars:
            fh.write(f"{b.time},{b.open!r},{b.high!r},{b.low!r},{b.close!r},{b.volume!r}\n")
    summary = run_stream(load_m1(csv_path), tmp_path / "out", snapshot_every=500)
    assert summary["bars"] == len(bars) and summary["config_hash"] == CFG.config_hash
    lines = (tmp_path / "out" / "events.jsonl").read_text().splitlines()
    direct = run(bars, CFG)
    assert len(lines) == len(direct)
    assert fingerprint(direct) == fingerprint(run(list(load_m1(csv_path)), CFG))
    snap = json.loads((tmp_path / "out" / "final_snapshot.json").read_text())
    assert len(snap["top_zones"]) <= CFG["scoring"]["top_n"]


# ------------------------------------------------------------------ New York H4
def _utc(text: str) -> int:
    from structure_engine.bars import parse_time
    return parse_time(text)


@pytest.mark.parametrize("moment,start,end", [
    # summer (EDT, UTC-4): NY 02/06/10/14/18/22 = UTC 06/10/14/18/22/02
    ("2026-07-15T07:30:00", "2026-07-15T06:00:00", "2026-07-15T10:00:00"),
    ("2026-07-15T23:10:00", "2026-07-15T22:00:00", "2026-07-16T02:00:00"),
    # winter (EST, UTC-5): UTC 07/11/15/19/23/03
    ("2026-01-15T07:30:00", "2026-01-15T07:00:00", "2026-01-15T11:00:00"),
    ("2026-01-15T02:59:00", "2026-01-14T23:00:00", "2026-01-15T03:00:00"),
])
def test_new_york_h4_grid(moment, start, end):
    from structure_engine.clock import anchored_bucket
    rule = CFG["alignment"]["H4"]
    assert anchored_bucket(_utc(moment), 240, rule["open_hours_local"], rule["timezone"]) == (_utc(start), _utc(end))


def test_h4_is_built_from_h1_on_the_new_york_grid():
    from structure_engine.engine import closed_bars_by_timeframe
    # Sunday 2026-08-02 22:00 UTC = 18:00 NY (EDT) session open; 12 hours of M1
    t0 = _utc("2026-08-02T22:00:00")
    m1 = [Bar(t0 + 60 * i, 100 + i % 7, 101 + i % 7, 99 + i % 7, 100.5 + i % 7, 1) for i in range(12 * 60)]
    by_tf = closed_bars_by_timeframe(m1, CFG)
    h4 = by_tf["H4"]
    assert [b.time for b in h4] == [t0, t0 + 4 * 3600, t0 + 8 * 3600]
    h1 = by_tf["H1"]
    for i, b in enumerate(h4):                     # each H4 = exactly its four H1 candles
        part = h1[4 * i:4 * i + 4]
        assert (b.open, b.close) == (part[0].open, part[-1].close)
        assert b.high == max(x.high for x in part) and b.low == min(x.low for x in part)
        assert b.m1_count == 240


def test_alignment_config_is_validated():
    with pytest.raises(ConfigError, match="every 4h"):
        load_config(overrides={"alignment": {"H4": {"source": "H1", "timezone": "America/New_York",
                                                    "open_hours_local": [2, 6, 10, 14, 18]}}})
    with pytest.raises(ConfigError, match="timezone"):
        load_config(overrides={"alignment": {"H4": {"source": "H1", "timezone": "Europe/London",
                                                    "open_hours_local": [2, 6, 10, 14, 18, 22]}}})


# ------------------------------------------------------------------ close spikes
def _spike_series(direction: int, then: str) -> list[Bar]:
    """3 calm days of M1 bars, then a 10-minute burst into the 14:00 UTC H1
    close, then ``then`` = 'reverse' or 'continue' for 4 hours."""
    t0 = _utc("2026-07-13T00:00:00")
    bars, p = [], 2000.0
    spike_end = _utc("2026-07-16T14:00:00")
    t = t0
    while t < spike_end + 5 * 3600:
        o = p
        if spike_end - 600 <= t < spike_end:
            p += direction * 1.5                      # 15.0 in the last 10 minutes
        elif t >= spike_end and then == "reverse" and t < spike_end + 1200:
            p -= direction * 1.0                      # back 20.0 within 20 minutes
        elif t >= spike_end and then == "continue" and t < spike_end + 600:
            p += direction * 1.0
        else:
            p += 0.05 if (t // 60) % 2 else -0.05
        bars.append(Bar(t, o, max(o, p) + 0.2, min(o, p) - 0.2, p, 100.0))
        t += 60
    return bars


@pytest.mark.parametrize("direction,then,label", [(1, "reverse", "reversal"), (-1, "reverse", "reversal"),
                                                  (1, "continue", "continuation")])
def test_close_spike_detected_and_labelled(direction, then, label):
    events = run(_spike_series(direction, then), CFG)
    spikes = [e for e in events if e.kind == "close_spike" and e.tf == "H1"]
    assert len(spikes) == 1
    sp = spikes[0].data
    assert sp["direction"] == ("up" if direction > 0 else "down") and sp["held"]
    assert spikes[0].available_at == _utc("2026-07-16T14:00:00")
    outs = {e.data["horizon_minutes"]: e for e in events
            if e.kind == "close_spike_outcome" and e.data["spike_id"] == sp["spike_id"]}
    assert sorted(outs) == [15, 60, 240]
    assert outs[60].data["label"] == label
    assert outs[60].available_at == spikes[0].available_at + 3600


def test_close_spike_no_repaint():
    bars = _spike_series(1, "reverse")
    assert no_repaint(bars, CFG, cuts=6, seed=3) == []


# ------------------------------------------------------------------ market structure layer
# Hand-built M5 candles (expanded to M1) with exactly known structure. Each
# scenario asserts the specific events a trader would mark on that chart.

def _m5(seq, t0="2026-07-13T08:00:00"):
    from structure_engine.verification.synthetic import expand_to_m1
    start = _utc(t0)
    tf_bars = [Bar(start + 300 * i, o, h, l, c, 100.0, minutes=5, m1_count=5, tf="M5")
               for i, (o, h, l, c) in enumerate(seq)]
    return expand_to_m1(tf_bars, 5), start


def _flat(p, n):
    return [(p, p + 0.5, p - 0.5, p)] * n


def _peak(top):
    b = top - 2.0
    return [(b, b + 0.8, b - 0.2, b + 0.7), (b + 0.7, top - 0.5, b + 0.6, top - 0.6),
            (top - 0.6, top, top - 0.9, top - 0.7), (top - 0.7, top - 0.6, top - 1.5, top - 1.4),
            (top - 1.4, top - 1.3, b - 0.1, b)]


TREND_SCENARIO = _flat(100, 20) + [
    (100, 101.2, 99.8, 101), (101, 102.5, 100.8, 102.3), (102.3, 104, 102, 103.8), (103.8, 105, 103.5, 104.6),
    (104.6, 104.8, 103.2, 103.4), (103.4, 103.6, 102.2, 102.4), (102.4, 102.6, 101.9, 102.2),
    (102.2, 103.5, 102.1, 103.4), (103.4, 104.6, 103.3, 104.5), (104.5, 107.6, 104.4, 107.5),
    (107.5, 108.5, 106.8, 108.2), (108.2, 109, 107.9, 108.8), (108.8, 108.9, 107.6, 107.8),
    (107.8, 108, 106.9, 107.1), (107.1, 107.6, 107.0, 107.5), (107.5, 108.3, 107.4, 108.2),
    (108.2, 109.8, 108.1, 109.6), (109.6, 109.7, 107.5, 107.6), (107.6, 107.7, 106.0, 106.2),
    (106.2, 106.4, 103.9, 104.1)] + [(104.1, 104.6, 103.6, 104.1)] * 12


def test_bos_choch_order_blocks_displacement_and_fvg_lifecycle():
    cfg = load_config(overrides={"order_blocks": {"timeframes": ["M5", "M15", "M30", "H1", "H4"]}})
    m1, _ = _m5(TREND_SCENARIO)
    ev = [e for e in run(m1, cfg) if e.tf == "M5"]
    breaks = [(e.kind, e.data["direction"], e.data["level"]) for e in ev if e.kind in ("bos", "choch")]
    assert breaks[-3:] == [("bos", "up", 105.0), ("bos", "up", 109.0), ("choch", "down", 106.9)]
    first = next(e for e in ev if e.kind == "bos" and e.data["level"] == 105.0)
    assert first.data["displacement"] is True and first.data["protected"] == 101.9
    choch = next(e for e in ev if e.kind == "choch")
    assert choch.data["trend_before"] == "up" and choch.data["trend_after"] == "down"
    obs = {(e.data["direction"], e.data["low"], e.data["high"]) for e in ev if e.kind == "order_block_created"}
    assert ("up", 101.9, 102.6) in obs and ("down", 108.1, 109.8) in obs
    gap = [e for e in ev if e.kind.startswith("fvg_") and (e.data["low"], e.data["high"]) == (104.6, 106.8)]
    assert [e.kind for e in gap] == ["fvg_created", "fvg_mitigated", "fvg_filled"]


LIQUIDITY_SCENARIO = (
    _flat(100, 20) + _peak(103) + _flat(101, 4)
    + [(101, 103.4, 100.9, 102.5)]                                     # sweep of 103
    + _flat(102.5, 3) + [(102.5, 103.8, 102.4, 103.7)] + _peak(105.6)[1:] + _flat(103.6, 3)
    + [(103.6, 106.2, 103.5, 106.0), (106.0, 106.1, 104.9, 105.0)]     # false break of 105.6
    + _flat(105, 3) + _peak(107.8)[1:] + _flat(105.8, 3)
    + [(105.8, 108.4, 105.7, 108.3)] + [(108.3, 108.8, 108.0, 108.5)] * 4)   # 107.8 taken


def test_liquidity_sweep_false_break_and_accepted_break():
    cfg = load_config(overrides={"liquidity": {"swing_timeframes": ["M5"], "equal_timeframes": ["M5"]}})
    m1, _ = _m5(LIQUIDITY_SCENARIO)
    ev = run(m1, cfg)
    got = {(e.kind, lv["price"]) for e in ev if e.kind in ("liquidity_sweep", "false_break", "liquidity_taken")
           for lv in e.data["levels"]}
    assert ("liquidity_sweep", 103.0) in got
    assert ("false_break", 105.6) in got
    assert ("liquidity_taken", 107.8) in got
    assert not any(lv == 105.6 for k, lv in got if k != "false_break")   # one fate per pool
    assert invariants(ev, cfg) == []


def test_equal_highs_and_ranges():
    cfg = load_config(overrides={"liquidity": {"swing_timeframes": ["M5"], "equal_timeframes": ["M5"]},
                                 "ranges": {"timeframes": ["M5"]}})
    m1, _ = _m5(_flat(100, 20) + _peak(103) + _flat(101, 3) + _peak(103.05) + _flat(101, 6))
    eq = [e for e in run(m1, cfg) if e.kind == "equal_highs"]
    assert len(eq) == 1 and eq[0].data["prices"] == [103.0, 103.05] and eq[0].data["pool"]["price"] == 103.05
    osc = [(100, 101, 99.6, 100.8) if i % 2 == 0 else (100.8, 101.0, 99.0, 99.4) for i in range(24)]
    m1, _ = _m5(_flat(100, 20) + osc + [(99.4, 102.6, 99.3, 102.5)] + _flat(102.5, 3))
    rng = [e for e in run(m1, cfg) if e.kind.startswith("range") and e.tf == "M5"]
    formed = [e for e in rng if e.kind == "range_formed" and e.data["top"] == 101.0]
    assert formed and formed[0].data["bottom"] == 99.0
    assert any(e.kind == "range_break" and e.data["direction"] == "up" and e.data["top"] == 101.0 for e in rng)


@pytest.mark.parametrize("moment,start", [
    ("2026-07-15T12:00:00", "2026-07-12T21:00:00"),    # summer: Sunday 17:00 NY = 21:00 UTC
    ("2026-07-12T20:59:00", "2026-07-05T21:00:00"),
    ("2026-01-14T12:00:00", "2026-01-11T22:00:00"),    # winter: 22:00 UTC
])
def test_trading_week_starts_sunday_17_new_york(moment, start):
    from structure_engine.clock import anchored_week
    a = CFG["sessions"]["week_anchor"]
    assert anchored_week(_utc(moment), a["timezone"], a["weekday"], a["hour"])[0] == _utc(start)


def test_fvg_stream_equals_offline_reference():
    from structure_engine.atr import WilderATR
    from structure_engine.engine import closed_bars_by_timeframe
    from structure_engine.fvg import find_gap
    bars = random_walk_m1(11, 8000)
    for tf in CFG["fvg"]["timeframes"]:
        tfb = closed_bars_by_timeframe(bars, CFG)[tf]
        atr, prev, ref = WilderATR(CFG["atr"]["period"]), [], set()
        for i, b in enumerate(tfb):
            prev.append(atr.value)
            atr.update(b)
            if i >= 2 and b.time - tfb[i - 2].time == 2 * b.minutes * 60:
                g = find_gap(tfb[i - 2], tfb[i - 1], b, prev[i], CFG["fvg"]["min_gap_atr"])
                if g:
                    ref.add((tfb[i - 2].time, g[0], g[1], g[2]))
        got = {(e.time, e.data["direction"], e.data["low"], e.data["high"])
               for e in run(bars, CFG) if e.kind == "fvg_created" and e.tf == tf}
        assert got == ref, tf


def test_structure_layer_no_repaint_and_invariants():
    cfg = load_config(overrides={"liquidity": {"swing_timeframes": ["M5"], "equal_timeframes": ["M5"]},
                                 "order_blocks": {"timeframes": ["M5", "M15", "M30", "H1", "H4"]}})
    for scenario in (TREND_SCENARIO, LIQUIDITY_SCENARIO):
        m1, _ = _m5(scenario)
        assert no_repaint(m1, cfg, cuts=6, seed=5) == []
        assert invariants(run(m1, cfg), cfg) == []
    walk = random_walk_m1(13, 5000)
    assert no_repaint(walk, CFG, cuts=4, seed=9) == []
    assert invariants(run(walk, CFG), CFG) == []


def test_no_fvg_across_a_market_closure():
    """Friday close -> Sunday open jump is a closure gap, not a fair value gap."""
    bars = []
    t = _utc("2026-07-17T16:00:00")                      # Friday, last 5 hours
    for i in range(300):
        bars.append(Bar(t + 60 * i, 100, 100.3, 99.7, 100, 10))
    t2 = _utc("2026-07-19T22:00:00")                     # Sunday open, 30 higher
    for i in range(60):
        bars.append(Bar(t2 + 60 * i, 130, 130.3, 129.7, 130, 10))
    engine = StructureEngine(CFG)
    gaps = [e for b in bars for e in engine.push(b) if e.kind == "fvg_created"]
    assert engine.atr["M5"].value is not None            # the gap WOULD qualify on size
    assert gaps == []


def test_sweep_followed_by_break_is_reported_as_failed():
    cfg = load_config(overrides={"liquidity": {"swing_timeframes": ["M5"], "equal_timeframes": ["M5"]}})
    seq = (_flat(100, 20) + _peak(103) + _flat(101, 4)
           + [(101, 103.4, 100.9, 102.5), (102.5, 104.6, 102.4, 104.5)] + _flat(104.5, 4))
    m1, _ = _m5(seq)
    ev = run(m1, cfg)
    kinds = [e.kind for e in ev if e.kind in ("liquidity_sweep", "sweep_failed")
             and any(lv["price"] == 103.0 for lv in e.data["levels"])]
    assert kinds == ["liquidity_sweep", "sweep_failed"]
    assert invariants(ev, cfg) == []


def test_event_ids_are_unique():
    """Every event id is unique (the database uses it as primary key)."""
    from collections import Counter
    from structure_engine.verification.synthetic import pattern_series, zone_series
    for bars in (random_walk_m1(21, 20000), zone_series(4, "M30", 30).m1, pattern_series(4).m1):
        ids = Counter(e.id for e in run(bars, CFG))
        assert max(ids.values()) == 1
