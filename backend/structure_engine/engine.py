"""StructureEngine — the single streaming engine (live == test).

Rule 2 of the architecture: there is NO separate back-test version of any
detector. Live trading and back-testing both do exactly this::

    engine = StructureEngine(load_config())
    for bar in <closed M1 bars>:          # MT5 live feed OR a recorded file
        events = engine.push(bar)         # confirmed facts, all known by now
    state = engine.snapshot()             # what the market looks like now

Only the bar SOURCE differs (see runner.py). Same bars in => byte-identical
events out, which the determinism test checks with a fingerprint.

What happens inside one push(bar)
---------------------------------
::

    validate bar (aligned, increasing, sane OHLC)
    now = bar close time                      <- every event's available_at
    1. zone lifecycle   existing zones see the new M1 bar (tested/broken)
    2. sessions         running session/day high-low; confirm finished ones
    1a. FVG / OB life   open gaps and order blocks see the new M1 bar
    1b. close spikes    label outcomes of earlier spikes whose horizon passed
    3. M1 structure     M1 swings -> double/triple tops & bottoms
                        (patterns use patterns.atr_timeframe's ATR as of the
                        last closed bar of that timeframe)
                        a CONFIRMED pattern at a recently tested HTF level
                        -> level_pattern
    3b. HTF levels      H1/H4 swing + session/day/week levels see the M1 bar:
                        tests (with approach, stretch, trend), M1 rejections,
                        follow-through, held (levels.py)
    4. higher TFs       aggregate M1 -> M5..H1, and closed H1 -> H4 on the
                        New York grid; for each bar that CLOSED now:
                        ATR, swings, then the structure layer (_structure):
                        displacement, FVG, BOS/CHoCH + order blocks, liquidity
                        pools with sweeps / false / accepted breaks (on M5),
                        VWAP crosses / band rejections (on M5), HTF level
                        breaks (on M5), ranges; new H1/H4 swings become HTF
                        levels; then close-spike detection on H1/H4, and on
                        zone timeframes: age + new zones
    return the events produced by this bar

Why that order: an existing zone must be checked against this bar before a
new zone created from this bar exists (a zone cannot be "tested" by the very
candle that revealed it), and patterns resolve before new ones are built.

Every event's ``available_at`` equals the close of the M1 bar that produced
it — asserted below, and proven by the no-repaint test, which replays every
prefix of the data and must reproduce the full run's events exactly.
"""

from __future__ import annotations

import hashlib

from .atr import WilderATR
from .bars import Aggregator, Bar, validate_m1
from .clock import anchored_bucket
from .config import StructureConfig
from .displacement import displacement
from .events import Event, make_event
from .fvg import GapBook
from .liquidity import LiquidityBook
from .order_blocks import OrderBlockBook
from .ranges import RangeTracker
from .trend import TrendTracker
from .vwap import VwapTracker
from .levels import LevelBook
from .patterns import PatternDetector
from .scoring import score_zones
from .sessions import SessionTracker
from .spikes import CloseSpikeDetector
from .swings import SwingDetector
from .zones import ZoneBook


class StructureEngine:
    def __init__(self, cfg: StructureConfig) -> None:
        self.cfg = cfg
        self.config_hash = cfg.config_hash
        # timeframes sorted by size: M1 first, then M5 ... H4
        self.tfs = sorted(cfg.tf_minutes, key=cfg.tf_minutes.get)
        self.higher = [tf for tf in self.tfs if tf != "M1"]
        # Each higher timeframe is fed either M1 bars (UTC grid) or, when
        # config "alignment" says so, the CLOSED bars of a source timeframe
        # cut on a local-time grid (H4 from H1 on New York hours).
        self.source = {tf: cfg["alignment"].get(tf, {}).get("source", "M1") for tf in self.higher}
        self.aggs = {}
        for tf in self.higher:
            rule = cfg["alignment"].get(tf)
            bucket = None
            if rule:
                bucket = (lambda t, m=cfg.tf_minutes[tf], r=rule:
                          anchored_bucket(t, m, r["open_hours_local"], r["timezone"]))
            self.aggs[tf] = Aggregator(tf, cfg.tf_minutes[tf], bucket)
        self.closed_now: dict[str, list[Bar]] = {}   # bars of each tf that closed in the last push
        self.atr = {tf: WilderATR(cfg["atr"]["period"]) for tf in self.tfs}
        self.swings = {tf: SwingDetector(tf, cfg["swings"]["strength"][tf], cfg["swings"]["history"])
                       for tf in self.tfs}
        self.zones = ZoneBook(cfg)
        self.sessions = SessionTracker(cfg)
        self.patterns = PatternDetector(cfg, self._pattern_id)
        self.spikes = CloseSpikeDetector(cfg, lambda tf, t: "S" + self._id("spike", tf, t))
        # market-structure layer (BOS/CHoCH, liquidity, FVG, order blocks, ranges)
        self.trend = {tf: TrendTracker(tf, cfg["trend"]["break_buffer_atr"], cfg["trend"]["history"])
                      for tf in cfg["trend"]["timeframes"]}
        self.liquidity = LiquidityBook(cfg, lambda *k: "L" + self._id("pool", *k))
        self.gaps = GapBook(cfg, lambda *k: "F" + self._id("fvg", *k))
        self.obs = OrderBlockBook(cfg, lambda *k: "O" + self._id("ob", *k))
        self.ranges = {tf: RangeTracker(tf, cfg, lambda *k: "R" + self._id("range", *k))
                       for tf in cfg["ranges"]["timeframes"]}
        self.vwap = VwapTracker(cfg)
        self.levels = LevelBook(cfg, lambda *k: "V" + self._id("level", *k))
        # recent closed candles (+ displacement info) per timeframe, for order blocks / FVGs
        self.hist: dict[str, list[tuple[Bar, dict | None]]] = {tf: [] for tf in self.tfs}
        self.last_time: int | None = None      # open time of the last M1 bar
        self.now: int | None = None            # close time of the last M1 bar
        self._last_close: float | None = None
        self.m1_index = -1
        self.counts: dict[str, int] = {}

    # ------------------------------------------------------------------ ids
    def _id(self, *parts) -> str:
        raw = "|".join([self.config_hash, *map(str, parts)])
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    def _zone_id(self, tf: str, side: str, time: int) -> str:
        return "Z" + self._id("zone", tf, side, time)

    def _pattern_id(self, kind: str, first_time: int, last_time: int) -> str:
        return "P" + self._id("pattern", kind, first_time, last_time)

    def _ev(self, kind: str, tf: str, time: int, data: dict, key: str = "") -> Event:
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return make_event(kind, tf, time, self.now, data, self.config_hash, key)

    # ------------------------------------------------------------------ push
    def push(self, bar: Bar) -> list[Event]:
        """Feed ONE closed M1 bar. Returns the events it produced (maybe none)."""
        validate_m1(bar, self.last_time)
        self.last_time = bar.time
        self._last_close = bar.close
        self.now = bar.close_time
        self.m1_index += 1
        events: list[Event] = []
        # ATR of every timeframe as of BEFORE this bar (spikes are measured
        # with it, so the spike cannot inflate its own yardstick)
        atr_before = {tf: self.atr[tf].value for tf in self.tfs}

        # 1. existing zones meet the new bar
        for kind, z in self.zones.on_m1(bar, self.now):
            events.append(self._ev(kind, z.tf, z.time, z.as_dict(), key=f"{z.id}:{z.tests}:{z.status}"))

        # 1a. fair value gaps and order blocks meet the new bar
        for kind, g in self.gaps.on_m1(bar, self.now):
            events.append(self._ev(kind, g.tf, g.time, g.as_dict(), key=f"{g.id}:{g.status}"))
        for kind, o in self.obs.on_m1(bar, self.now):
            events.append(self._ev(kind, o.tf, o.time, o.as_dict(), key=f"{o.id}:{o.tests}:{o.status}"))

        # 1b. open close-spikes: label outcomes whose horizon has now passed
        for kind, sp, label in self.spikes.on_m1(bar, self.now):
            events.append(self._ev(kind, sp.tf, sp.data["htf_open"], label,
                                   key=f"{sp.id}:{label['horizon_minutes']}"))

        # 2. session / day liquidity levels
        for kind, level in self.sessions.update(bar, self.now):
            events.append(self._ev(kind, "M1", level["start"], level, key=level["name"]))
            src = {"DAY": "day", "WEEK": "week"}.get(level["name"], "session")
            for side in ("high", "low"):
                self.liquidity.add(f"{level['name'].lower()}_{side}", side, level[side], src,
                                   level["start"], self.now)
                if self.cfg["htf_levels"]["session_levels"]:
                    lv = self.levels.add(f"{level['name']} {side}", side, level[side], level["start"],
                                         self.now, self._lv_atr(), bar.close)
                    if lv is not None:
                        events.append(self._ev("level_created", "M1", lv.time, lv.as_dict(), key=lv.id))

        # 3. M1 swings, then patterns built from them. Patterns measure in the
        #    ATR of patterns.atr_timeframe (a slower ruler than M1's own ATR,
        #    which collapses in quiet chop and makes every wiggle look "big").
        #    Value as of the last CLOSED bar of that timeframe -> causal.
        m1_atr_before = self.atr[self.cfg["patterns"]["atr_timeframe"]].value
        m1_swings = self.swings["M1"].update(bar)
        for s in m1_swings:
            events.append(self._ev("swing", "M1", s.time, s.as_dict(), key=s.kind))
        for kind, pat in self.patterns.on_bar(bar, self.m1_index, m1_atr_before, m1_swings, self.now):
            events.append(self._ev(kind, "M1", pat.peaks[0].time, pat.as_dict(), key=f"{pat.id}:{pat.status}"))
            if kind == "pattern_confirmed":
                link = self.levels.on_pattern(pat.as_dict(), self.now, self._lv_atr())
                if link is not None:
                    lv, data = link
                    events.append(self._ev("level_pattern", "M1", bar.time, {"level": lv.as_dict(), **data},
                                           key=f"{lv.id}:{pat.id}"))

        # 3b. higher-timeframe levels meet this M1 bar (tests, rejections, holds)
        trends = {tf: self.trend[tf].state for tf in ("M15", "H1", "H4") if tf in self.trend}
        for kind, lv, data in self.levels.on_m1(bar, self.now, self._lv_atr(), self.atr["H1"].value, trends):
            events.append(self._ev(kind, "M1", bar.time, {"level": lv.as_dict(), **data},
                                   key=f"{lv.id}:{data.get('test_no')}:{kind}"))
        self.atr["M1"].update(bar)
        self.vwap.on_m1(bar)                      # VWAPs include this closed minute

        # 4. higher timeframes that closed with this minute
        zone_tfs = set(self.cfg["zones"]["timeframes"])
        self.closed_now = {"M1": [bar]}
        for tf in self.higher:                    # ascending size: sources come first
            closed_list = [c for src in self.closed_now.get(self.source[tf], [])
                           for c in self.aggs[tf].update(src)]
            self.closed_now[tf] = closed_list
            for closed in closed_list:
                atr_prev = self.atr[tf].value         # ATR known BEFORE this candle
                atr_after = self.atr[tf].update(closed)
                new_swings = self.swings[tf].update(closed)
                for s in new_swings:
                    events.append(self._ev("swing", tf, s.time, s.as_dict(), key=s.kind))
                    if tf in self.cfg["htf_levels"]["swing_timeframes"]:
                        lv = self.levels.add(f"{tf} swing {s.kind}", s.kind, s.price, s.time, self.now,
                                             self._lv_atr(), bar.close)
                        if lv is not None:
                            events.append(self._ev("level_created", tf, lv.time, lv.as_dict(), key=lv.id))
                events.extend(self._structure(tf, closed, atr_prev, new_swings))
                if tf in self.spikes.tfs:
                    sp = self.spikes.on_htf_close(
                        tf, closed, self.now, atr_before[self.cfg["close_spikes"]["atr_timeframe"]],
                        list(self.sessions.levels), self.zones.active, self._htf_trend(),
                        self._session_name(bar.time))
                    if sp is not None:
                        events.append(self._ev("close_spike", tf, closed.time, sp.data, key=sp.id))
                if tf in zone_tfs:
                    for z in self.zones.age(tf, self.now):
                        events.append(self._ev("zone_expired", tf, z.time, z.as_dict(), key=f"{z.id}:age"))
                    for z in self.zones.on_tf_bar(tf, closed, atr_after, self.now, self._zone_id):
                        events.append(self._ev("zone_created", tf, z.time, z.as_dict(), key=z.id))

        # Rule 4 guard: nothing may be known before the bar that revealed it.
        assert all(e.available_at == self.now for e in events)
        return events

    def _structure(self, tf: str, bar: Bar, atr: float | None, new_swings) -> list[Event]:
        """Market-structure layer for one CLOSED candle of ``tf``.

        Order: displacement -> FVG -> BOS/CHoCH (+ order block) -> liquidity
        pools (new swing / equal-level pools, then sweeps & breaks on the
        detection timeframe) -> ranges. Every threshold uses ``atr``, the
        ATR as of BEFORE this candle.
        """
        cfg, ev = self.cfg, []
        disp = displacement(bar, atr, cfg) if tf in cfg["displacement"]["timeframes"] else None
        if disp:
            ev.append(self._ev("displacement", tf, bar.time, {**disp, "candle": bar.as_dict()}))
        h = self.hist[tf]
        h.append((bar, disp))
        del h[:-200]
        if tf in cfg["fvg"]["timeframes"]:
            last3 = [b for b, _ in h[-3:]]
            c2_disp = len(h) >= 2 and h[-2][1] is not None
            for kind, g in self.gaps.on_tf_bar(tf, last3, atr, c2_disp, self.now):
                ev.append(self._ev(kind, tf, g.time, g.as_dict(), key=f"{g.id}:{g.status}"))
        if tf in self.trend:
            for o in self.obs.age(tf, self.now):
                ev.append(self._ev("order_block_expired", tf, o.time, o.as_dict(), key=f"{o.id}:age"))
            self.trend[tf].add_swings(new_swings)
            for brk in self.trend[tf].on_bar(bar, atr, disp):
                ev.append(self._ev(brk["kind"], tf, brk["level_time"], brk, key=f"{brk['kind']}:{bar.time}"))
                if tf in cfg["order_blocks"]["timeframes"]:
                    ob = self.obs.on_break(tf, brk, [b for b, _ in h], [d for _, d in h], atr, self.now)
                    if ob is not None:
                        ev.append(self._ev("order_block_created", tf, ob.time, ob.as_dict(), key=ob.id))
        if new_swings:
            for eq in self.liquidity.add_swings(tf, new_swings, atr, self.now):
                kind = "equal_highs" if eq["pool"]["side"] == "high" else "equal_lows"
                ev.append(self._ev(kind, tf, eq["times"][0], eq, key=eq["pool"]["id"]))
        if tf == cfg["liquidity"]["detect_timeframe"]:
            for kind, side, data in self.liquidity.on_detect_bar(bar, atr, self.now):
                ev.append(self._ev(kind, tf, bar.time, data, key=side))
        if tf == cfg["htf_levels"]["break_timeframe"]:
            for kind, lv, data in self.levels.on_break_bar(bar, self._lv_atr()):
                ev.append(self._ev(kind, tf, bar.time, {"level": lv.as_dict(), **data}, key=lv.id))
        if tf == cfg["vwap"]["detect_timeframe"]:
            for kind, data in self.vwap.on_detect_bar(bar, atr):
                ev.append(self._ev(kind, tf, bar.time, data, key=f"{data['anchor']}:{kind}:{data.get('side') or data.get('direction')}"))
        if tf in self.ranges:
            for kind, data in self.ranges[tf].on_bar(bar, atr, self.now):
                ev.append(self._ev(kind, tf, data["start"], data, key=f"{kind}:{bar.time}"))
                if kind == "range_formed":
                    self.liquidity.add("range_high", "high", data["top"], tf, data["start"], self.now)
                    self.liquidity.add("range_low", "low", data["bottom"], tf, data["start"], self.now)
        return ev

    def _lv_atr(self) -> float | None:
        """Ruler of the HTF-level layer: ATR of htf_levels.atr_timeframe (last closed candle)."""
        return self.atr[self.cfg["htf_levels"]["atr_timeframe"]].value

    def _htf_trend(self) -> str:
        """H4 swing structure: up = last high HH and last low HL; down = LH + LL."""
        sw = self.swings.get("H4") or self.swings[self.tfs[-1]]
        hi = sw.last_high.label if sw.last_high else None
        lo = sw.last_low.label if sw.last_low else None
        if hi == "HH" and lo == "HL":
            return "up"
        if hi == "LH" and lo == "LL":
            return "down"
        return "mixed"

    def _session_name(self, t: int) -> str | None:
        win = self.sessions._window_of(t)
        return win[0] if win else None

    # -------------------------------------------------------------- snapshot
    def snapshot(self, swings_per_tf: int = 10, levels: int = 12) -> dict:
        """Everything Module 2 needs to describe the market *as of now*.

        ``confirmed``-type content (zones, swings, levels) is separated from
        ``forming`` content (running session/day, unfinished higher-TF candles)
        and ``pending`` patterns, per Rule 5.
        """
        level_prices = self.sessions.confirmed_prices()
        return {
            "as_of": self.now,
            "config_id": self.cfg["config_id"],
            "config_hash": self.config_hash,
            "atr": {tf: self.atr[tf].value for tf in self.tfs},
            "top_zones": score_zones(self.zones.active, level_prices, self.cfg),
            "active_zone_count": len(self.zones.active),
            "swings": {tf: [s.as_dict() for s in list(self.swings[tf].recent)[-swings_per_tf:]]
                       for tf in self.tfs},
            "levels": list(self.sessions.levels)[-levels:],
            "trend": {tf: t.state_dict() for tf, t in self.trend.items()},
            "vwap": self.vwap.values(),
            "htf_levels": sorted(
                ({**lv.as_dict(), "testing": lv.test.no if lv.test else None} for lv in self.levels.active),
                key=lambda d: abs(d["price"] - (self._last_close or 0)))[:12],
            "liquidity_pools": self.liquidity.nearest(self._last_close, 10) if self._last_close else [],
            "recent_liquidity_events": self.liquidity.history[-10:],
            "fair_value_gaps": [g.as_dict() for g in sorted(
                self.gaps.active, key=lambda g: abs((g.low + g.high) / 2 - (self._last_close or 0)))[:10]],
            "order_blocks": [o.as_dict() for o in self.obs.active],
            "ranges": {tf: (r.active.as_dict() if r.active else None) for tf, r in self.ranges.items()},
            "pending_patterns": [p.as_dict() for p in self.patterns.pending],
            "open_spikes": [{"id": sp.id, "tf": sp.tf, **sp.data, "horizons_left": sp.pending}
                            for sp in self.spikes.open],
            "forming": {
                **self.sessions.forming(),
                "bars": {tf: (a.current.as_dict() if a.current else None) for tf, a in self.aggs.items()},
            },
            "event_counts": dict(sorted(self.counts.items())),
        }


def closed_bars_by_timeframe(m1_bars, cfg: StructureConfig) -> dict[str, list[Bar]]:
    """Offline helper: every closed bar of every timeframe, exactly as the
    engine builds them (used by the swing reference test and verification)."""
    engine = StructureEngine(cfg)
    out: dict[str, list[Bar]] = {tf: [] for tf in engine.tfs}
    for bar in m1_bars:
        engine.push(bar)
        for tf, bars in engine.closed_now.items():
            out[tf].extend(bars)
    return out
