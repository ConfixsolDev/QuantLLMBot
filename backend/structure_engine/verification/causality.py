"""Proofs that the engine never cheats: no repaint, determinism, invariants.

no_repaint
    Run the engine on ALL bars and remember every event. Then, for several
    cut points c, run a FRESH engine on only the first c bars. The prefix run
    must produce exactly the full run's events whose ``available_at`` is at
    or before the cut. If any detector peeked at future bars, or changed its
    mind about the past, the two lists differ and the test fails.

determinism
    Two runs on the same bars produce the same event fingerprint.

invariants
    Geometry that must always hold (zone low < high, a top's neckline is
    below its peaks, nothing is known before its structure finished ...).
"""

from __future__ import annotations

import random

from ..bars import Bar
from ..config import StructureConfig
from ..engine import StructureEngine
from ..events import Event, fingerprint


def run(bars: list[Bar], cfg: StructureConfig) -> list[Event]:
    engine = StructureEngine(cfg)
    events: list[Event] = []
    for bar in bars:
        events.extend(engine.push(bar))
    return events


def no_repaint(bars: list[Bar], cfg: StructureConfig, cuts: int = 8, seed: int = 0) -> list[str]:
    """Return a list of human-readable failures (empty list = pass)."""
    full = run(bars, cfg)
    rng = random.Random(seed)
    points = sorted(rng.sample(range(1, len(bars)), min(cuts, len(bars) - 1)))
    failures = []
    for c in points:
        cut_time = bars[c - 1].close_time
        expected = [e for e in full if e.available_at <= cut_time]
        got = run(bars[:c], cfg)
        if fingerprint(got) != fingerprint(expected):
            failures.append(f"cut at bar {c}: prefix run has {len(got)} events, full run {len(expected)}")
    return failures


def determinism(bars: list[Bar], cfg: StructureConfig) -> bool:
    return fingerprint(run(bars, cfg)) == fingerprint(run(bars, cfg))


def invariants(events: list[Event], cfg: StructureConfig) -> list[str]:
    bad = []
    tfmin = cfg.tf_minutes
    level_tests: dict[str, int] = {}          # level id -> last test number seen
    for e in events:
        d = e.data
        if e.available_at < e.time:
            bad.append(f"{e.id}: known before its own time")
        if e.kind.startswith("zone_"):
            if not d["low"] < d["high"]:
                bad.append(f"{e.id}: zone low >= high")
            if d["side"] == "demand" and not (d["proximal"] == d["high"] and d["distal"] == d["low"]):
                bad.append(f"{e.id}: demand edges wrong")
            if d["side"] == "supply" and not (d["proximal"] == d["low"] and d["distal"] == d["high"]):
                bad.append(f"{e.id}: supply edges wrong")
            if e.kind == "zone_created" and e.available_at < e.time + d["departure_len"] * tfmin[e.tf] * 60:
                bad.append(f"{e.id}: zone known before its departure closed")
        if e.kind == "swing":
            k = cfg["swings"]["strength"][e.tf]
            if e.available_at < e.time + (k + 1) * tfmin[e.tf] * 60:
                bad.append(f"{e.id}: swing known before its right side closed")
        if e.kind.startswith("pattern_"):
            prices = [p["price"] for p in d["peaks"]]
            if d["kind"].endswith("top") and not d["neckline"] < min(prices):
                bad.append(f"{e.id}: top neckline not below peaks")
            if d["kind"].endswith("bottom") and not d["neckline"] > max(prices):
                bad.append(f"{e.id}: bottom neckline not above troughs")
            times = [p["time"] for p in d["peaks"]]
            if times != sorted(times):
                bad.append(f"{e.id}: peaks out of order")
        if e.kind in ("session_level", "prior_day_level", "prior_week_level") and not d["low"] <= d["high"]:
            bad.append(f"{e.id}: level low > high")
        if e.kind in ("bos", "choch"):
            up = d["direction"] == "up"
            if (up and not d["break_close"] > d["level"]) or (not up and not d["break_close"] < d["level"]):
                bad.append(f"{e.id}: {e.kind} close not beyond the broken level")
            if e.available_at < d["break_time"] + tfmin[e.tf] * 60:
                bad.append(f"{e.id}: {e.kind} known before the breaking candle closed")
        if e.kind.startswith("fvg_") or e.kind.startswith("order_block_"):
            if not d["low"] < d["high"]:
                bad.append(f"{e.id}: {e.kind} low >= high")
        if e.kind == "liquidity_sweep":
            for lv in d["levels"]:
                if d["side"] == "high" and not (d["extreme"] > lv["price"] and d["candle"]["close"] < lv["price"]):
                    bad.append(f"{e.id}: high sweep geometry")
                if d["side"] == "low" and not (d["extreme"] < lv["price"] and d["candle"]["close"] > lv["price"]):
                    bad.append(f"{e.id}: low sweep geometry")
        if e.kind.startswith("level_") and e.kind != "level_created":
            lv, hl = d["level"], cfg["htf_levels"]
            sg = 1 if lv["side"] == "high" else -1
            c = d.get("candle")
            if e.kind == "level_test":
                ext = c["high"] if sg > 0 else c["low"]
                if sg * (lv["price"] - ext) > hl["touch_tolerance_atr"] * d["atr"] + 1e-9:
                    bad.append(f"{e.id}: level_test candle did not reach the touch zone")
                if d["test_no"] != lv["tests"]:
                    bad.append(f"{e.id}: test number differs from the level's count")
                prev = level_tests.get(lv["id"])       # (a window may start mid-life)
                if prev is not None and d["test_no"] != prev + 1:
                    bad.append(f"{e.id}: test {d['test_no']} follows test {prev}")
                level_tests[lv["id"]] = d["test_no"]
            if e.kind == "level_rejection":
                ext = c["high"] if sg > 0 else c["low"]
                if not (sg * (ext - lv["price"]) > 0 and sg * (lv["price"] - c["close"]) > 0):
                    bad.append(f"{e.id}: rejection did not poke beyond and close back inside")
            if e.kind == "level_broken" and not sg * (c["close"] - lv["price"]) > 0:
                bad.append(f"{e.id}: break candle did not close beyond the level")
            if e.kind in ("level_broken", "level_expired"):
                level_tests.pop(lv["id"], None)
            if e.kind == "level_pattern":
                top = d["pattern"].endswith("top")
                if top != (sg > 0):
                    bad.append(f"{e.id}: pattern direction does not match the level side")
        if e.kind == "vwap_cross":
            c = d["candle"]["close"]
            if (d["direction"] == "up" and c < d["vwap"]) or (d["direction"] == "down" and c > d["vwap"]):
                bad.append(f"{e.id}: vwap_cross close on the wrong side")
        if e.kind == "vwap_band_reject":
            cd = d["candle"]
            if d["side"] == "upper" and not (cd["high"] > d["level"] > cd["close"]):
                bad.append(f"{e.id}: upper band reject geometry")
            if d["side"] == "lower" and not (cd["low"] < d["level"] < cd["close"]):
                bad.append(f"{e.id}: lower band reject geometry")
        if e.kind == "sweep_failed":
            for lv in d["levels"]:
                c = d["candle"]["close"]
                if (d["side"] == "high" and not c > lv["price"]) or (d["side"] == "low" and not c < lv["price"]):
                    bad.append(f"{e.id}: sweep_failed close not beyond the level")
        if e.kind in ("liquidity_sweep", "false_break", "liquidity_taken", "sweep_failed"):
            if any(lv["active_from"] > d["candle"]["time"] + tfmin[e.tf] * 60 for lv in d["levels"]):
                bad.append(f"{e.id}: level used before it was known")
    return bad
