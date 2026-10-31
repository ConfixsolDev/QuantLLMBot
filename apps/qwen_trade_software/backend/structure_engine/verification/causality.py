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
        if e.kind in ("session_level", "prior_day_level") and not d["low"] <= d["high"]:
            bad.append(f"{e.id}: level low > high")
    return bad
