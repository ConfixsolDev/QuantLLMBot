"""Replay one day: what the engine knew at every moment, and is it right?

Used by the website's Replay page (verification, Part B of the V3 document).

A replay day is a UTC calendar day. To give the engine context, it is run
from ``warmup_days`` before the day until ``after_hours`` after it, on the M1
bars stored in the database — the very same StructureEngine as live.
Because every event carries ``available_at``, the chart "as of" any cursor
time t is simply every event with available_at <= t: no second engine run,
no look-ahead, and stepping through the day is instant.

The candles after t are returned separately (``future``) so the page can
show them shaded: the reviewer sees what happened next, the engine never did.

Automatic checks per day (``checks``)
-------------------------------------
invariants    geometry that must always hold (verification/causality.py)
determinism   a second run gives byte-identical events for the day
no_repaint    runs that stop at 3 cut points inside the day reproduce exactly
              the full run's events up to each cut
audit         every event re-checked against candles rebuilt by independent
              code (verification/audit.py)
"""

from __future__ import annotations

import bisect
import time
from collections import OrderedDict
from datetime import datetime, timezone

from structure_engine.engine import StructureEngine
from structure_engine.events import Event, fingerprint
from structure_engine.verification.audit import audit_events
from structure_engine.verification.causality import invariants

from . import overlays

DAY = 86400
TFS = ("M1", "M5", "M15", "M30", "H1", "H4")
# events shown in the day's check sheet (the reviewable structure)
REVIEW_KINDS = {
    "bos", "choch", "liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken",
    "equal_highs", "equal_lows", "fvg_created", "order_block_created", "zone_created",
    "range_formed", "pattern_confirmed", "close_spike", "session_level", "prior_day_level",
    "prior_week_level", "vwap_cross", "vwap_band_reject",
}


def day_bounds(date: str) -> tuple[int, int]:
    d = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    start = int(d.timestamp())
    return start, start + DAY


def describe(e: dict) -> str:
    """One readable line per event for the check sheet."""
    k, d, tf = e["kind"], e["data"], e["tf"]
    p = lambda x: f"{x:.2f}"  # noqa: E731
    if k in ("bos", "choch"):
        return f"{tf} {k.upper()} {d['direction']} — closed beyond {p(d['level'])}"
    if k in overlays.LIQ:
        lv = ", ".join(f"{x['kind'].replace('_', ' ')} {p(x['price'])}" for x in d["levels"])
        return f"{overlays.LIQ[k]} ({d['side']}) — {lv}"
    if k in ("equal_highs", "equal_lows"):
        return f"{tf} {k.replace('_', ' ')} at {p(d['pool']['price'])} ({d['count']} swings)"
    if k == "fvg_created":
        return f"{tf} FVG {'bullish' if d['direction'] == 'up' else 'bearish'} {p(d['low'])}–{p(d['high'])}"
    if k == "order_block_created":
        return f"{tf} order block {'bullish' if d['direction'] == 'up' else 'bearish'} {p(d['low'])}–{p(d['high'])} (from {d['break_kind'].upper()})"
    if k == "zone_created":
        return f"{tf} {d['side']} zone {p(d['low'])}–{p(d['high'])}"
    if k == "range_formed":
        return f"{tf} range {p(d['bottom'])}–{p(d['top'])}"
    if k == "pattern_confirmed":
        return f"{d['kind'].replace('_', ' ')} — neckline {p(d['neckline'])}"
    if k == "close_spike":
        return f"{tf} close spike {d['direction']} {d['move']:.1f} ({'held' if d['held'] else 'rejected'})"
    if k in ("session_level", "prior_day_level", "prior_week_level"):
        return f"{d['name']} range {p(d['low'])}–{p(d['high'])}"
    if k == "vwap_cross":
        return f"VWAP {d['anchor']} cross {d['direction']} at {p(d['vwap'])}"
    if k == "vwap_band_reject":
        return f"VWAP {d['anchor']} {d['band']}σ {d['side']} band reject at {p(d['level'])}"
    return k


class ReplayDay:
    """One engine run covering a day (plus warm-up before and context after)."""

    def __init__(self, bars, cfg, date: str, warmup_days: int, after_hours: int) -> None:
        self.date = date
        self.day_start, self.day_end = day_bounds(date)
        self.cfg = cfg
        engine = StructureEngine(cfg)
        self.engine = engine
        self.bars = {tf: [] for tf in TFS}
        self.vwap = {tf: [] for tf in TFS}
        self.events: list[dict] = []
        self.m1 = []
        for b in bars:
            evs = engine.push(b)
            self.m1.append(b)
            for tf, closed in engine.closed_now.items():
                if closed:
                    v = engine.vwap.values()
                    for c in closed:
                        self.bars[tf].append(c)
                        self.vwap[tf].append((c.time, v))
            self.events.extend(e.as_dict() for e in evs)
        self.avail = [e["available_at"] for e in self.events]
        self.snaps = {tf: (lambda t, a=engine.aggs.get(tf): t - t % 60 if a is None else a._span(t)[0]) for tf in TFS}
        self.built_at = time.time()

    # ---------------------------------------------------------------- views
    def detections(self) -> list[dict]:
        out = []
        for e in self.events:
            if e["kind"] in REVIEW_KINDS and self.day_start <= e["available_at"] < self.day_end:
                out.append({"id": e["id"], "kind": e["kind"], "tf": e["tf"], "time": e["time"],
                            "available_at": e["available_at"], "text": describe(e)})
        return out

    def chart(self, tf: str, t: int, n: int) -> dict:
        """The chart as the engine knew it at time t, plus the shaded future."""
        bars = self.bars[tf]
        closes = [b.close_time for b in bars]
        i = bisect.bisect_right(closes, t)                   # candles closed by t
        past = bars[max(0, i - n): i]
        future = [b for b in bars[i:] if b.time < self.day_end + 6 * 3600][:n]
        if not past:
            return {"tf": tf, "candles": [], "future": [], "overlays": None, "as_of": t}
        t_from = past[0].time
        k = bisect.bisect_right(self.avail, t)
        evs = [e for e in self.events[:k] if e["available_at"] >= t_from or e["kind"] in overlays.BOX_START]
        levels = [e["data"] for e in self.events[:k] if e["kind"] in ("session_level", "prior_day_level", "prior_week_level")]
        snap = {"levels": levels[-40:], "forming": {}}
        ov = overlays.build(evs, tf, t_from, t, self.snaps[tf], snap)
        ov["curves"] = vwap_curves(self.vwap[tf], t_from, t)
        trend = {}
        for e in self.events[:k]:
            if e["kind"] in ("bos", "choch"):
                trend[e["tf"]] = {"state": e["data"]["trend_after"], "protected": e["data"]["protected"],
                                  "last_break": {"kind": e["kind"], "direction": e["data"]["direction"],
                                                 "level": e["data"]["level"], "break_time": e["data"]["break_time"]}}
        return {"tf": tf, "candles": [b.as_dict() for b in past], "future": [b.as_dict() for b in future],
                "overlays": ov, "trend": trend, "as_of": t,
                "price": past[-1].close}

    def checks(self) -> dict:
        """Automatic verification of the day (takes a few seconds)."""
        day_events = [e for e in self.events if self.day_start <= e["available_at"] < self.day_end]
        objs = [Event(e["kind"], e["tf"], e["time"], e["available_at"], e["data"], e["config_hash"], e["id"])
                for e in day_events]
        inv = invariants(objs, self.cfg)
        # determinism: a second, independent run over the same bars
        e2 = StructureEngine(self.cfg)
        second = []
        for b in self.m1:
            second.extend(x for x in e2.push(b) if self.day_start <= x.available_at < self.day_end)
        deterministic = fingerprint(second) == fingerprint(objs)
        # no-repaint: stop at 3 cut points inside the day
        cuts, repaint_fail = [], []
        day_m1 = [i for i, b in enumerate(self.m1) if self.day_start <= b.time < self.day_end]
        if day_m1:
            for frac in (0.25, 0.5, 0.75):
                ci = day_m1[int(len(day_m1) * frac)]
                cut_t = self.m1[ci].close_time
                e3 = StructureEngine(self.cfg)
                got = []
                for b in self.m1[: ci + 1]:
                    got.extend(x for x in e3.push(b) if x.available_at >= self.day_start)
                want = [x for x in objs if x.available_at <= cut_t]
                cuts.append(cut_t)
                if fingerprint(got) != fingerprint(want):
                    repaint_fail.append(cut_t)
        aud = audit_events(self.m1, day_events)
        audit_fail = sum(aud["failures"].values())
        return {
            "date": self.date, "events": len(day_events),
            "invariants": {"ok": not inv, "violations": inv[:10]},
            "determinism": {"ok": deterministic},
            "no_repaint": {"ok": not repaint_fail, "cuts": cuts, "failed_cuts": repaint_fail},
            "audit": {"ok": audit_fail == 0, "checked": sum(aud["checks"].values()), "failed": audit_fail,
                      "examples": aud["examples"]},
        }


def vwap_curves(hist: list, t_from: int, t: int) -> dict:
    """VWAP and bands per anchor at each chart candle up to t (None = gap)."""
    out: dict[str, list] = {}
    for ct, vals in hist:
        if ct < t_from or ct > t:
            continue
        for anchor, v in vals.items():
            pts = out.setdefault(anchor, [])
            if v is None:
                pts.append({"time": ct, "vwap": None})
            else:
                pts.append({"time": ct, "vwap": v["vwap"], "bands": v["bands"], "start": v["start"]})
    return out


class ReplayCache:
    """Keeps the last few replayed days in memory (a day takes ~2 s to build)."""

    def __init__(self, size: int = 4) -> None:
        self.size = size
        self.days: OrderedDict[str, ReplayDay] = OrderedDict()
        self.checks: dict[str, dict] = {}

    def get(self, key: str, build) -> ReplayDay:
        if key in self.days:
            self.days.move_to_end(key)
            return self.days[key]
        day = build()
        self.days[key] = day
        while len(self.days) > self.size:
            self.days.popitem(last=False)
        return day
