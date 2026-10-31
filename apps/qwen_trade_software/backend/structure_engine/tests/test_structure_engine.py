"""Module 1 test suite. Run from apps/qwen_trade_software/backend:

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


# ------------------------------------------------------------------ tools
def test_spike_study_and_review_run_end_to_end(tmp_path):
    from structure_engine.review import collect, write_html
    from structure_engine.studies.close_spikes import load, report
    bars = _spike_series(1, "reverse")
    run_stream(iter(bars), tmp_path / "bt")
    rows, outcomes, horizons = load(tmp_path / "bt" / "events.jsonl")
    table = report(rows, outcomes, horizons)
    assert table["all=all"]["n"] >= 1 and table["all=all"]["60"]["reversal_pct"] == 100.0
    moments = collect(bars, CFG, {_utc("2026-07-16T15:00:00")}, "M5", before=60, after=12)
    assert len(moments) == 1 and len(moments[0]["after"]) == 12
    assert all(b["time"] < moments[0]["t"] for b in moments[0]["before"])      # nothing from the future
    out = tmp_path / "rev"
    out.mkdir()
    write_html(moments, out, CFG)
    assert "<svg" in (out / "index.html").read_text() and (out / "review_template.csv").exists()
