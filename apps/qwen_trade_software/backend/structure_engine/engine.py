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
    1b. close spikes    label outcomes of earlier spikes whose horizon passed
    3. M1 structure     M1 swings -> double/triple tops & bottoms
                        (patterns use patterns.atr_timeframe's ATR as of the
                        last closed bar of that timeframe)
    4. higher TFs       aggregate M1 -> M5..H1, and closed H1 -> H4 on the
                        New York grid; for each bar that CLOSED now:
                        ATR, swings, close-spike detection on H1/H4, and on
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
from .events import Event, make_event
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
        self.last_time: int | None = None      # open time of the last M1 bar
        self.now: int | None = None            # close time of the last M1 bar
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
        self.now = bar.close_time
        self.m1_index += 1
        events: list[Event] = []
        # ATR of every timeframe as of BEFORE this bar (spikes are measured
        # with it, so the spike cannot inflate its own yardstick)
        atr_before = {tf: self.atr[tf].value for tf in self.tfs}

        # 1. existing zones meet the new bar
        for kind, z in self.zones.on_m1(bar, self.now):
            events.append(self._ev(kind, z.tf, z.time, z.as_dict(), key=f"{z.id}:{z.tests}:{z.status}"))

        # 1b. open close-spikes: label outcomes whose horizon has now passed
        for kind, sp, label in self.spikes.on_m1(bar, self.now):
            events.append(self._ev(kind, sp.tf, sp.data["htf_open"], label,
                                   key=f"{sp.id}:{label['horizon_minutes']}"))

        # 2. session / day liquidity levels
        for kind, level in self.sessions.update(bar, self.now):
            events.append(self._ev(kind, "M1", level["start"], level, key=level["name"]))

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
        self.atr["M1"].update(bar)

        # 4. higher timeframes that closed with this minute
        zone_tfs = set(self.cfg["zones"]["timeframes"])
        self.closed_now = {"M1": [bar]}
        for tf in self.higher:                    # ascending size: sources come first
            closed_list = [c for src in self.closed_now.get(self.source[tf], [])
                           for c in self.aggs[tf].update(src)]
            self.closed_now[tf] = closed_list
            for closed in closed_list:
                atr_after = self.atr[tf].update(closed)
                for s in self.swings[tf].update(closed):
                    events.append(self._ev("swing", tf, s.time, s.as_dict(), key=s.kind))
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
    engine builds them (used by the swing reference test and studies)."""
    engine = StructureEngine(cfg)
    out: dict[str, list[Bar]] = {tf: [] for tf in engine.tfs}
    for bar in m1_bars:
        engine.push(bar)
        for tf, bars in engine.closed_now.items():
            out[tf].extend(bars)
    return out
