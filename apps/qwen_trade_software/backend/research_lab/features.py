"""Structure features: what the deterministic engine knows at a decision time.

Every number here is computed from the StructureEngine's state and the events
it has already emitted — nothing from the future. Distances are in ATR units
(of H1 unless said otherwise) so features mean the same thing at $1,800 and
$4,500 gold.

The feature set is deliberately "trader-readable": trend state per timeframe,
how far the protected level is, what liquidity sits above/below, what just
happened at liquidity (sweeps, failed sweeps, false breaks, accepted breaks),
open FVGs and order blocks nearby, ranges, sessions, recent momentum, and the
close-spike context. XGBoost (compare.py) learns which of these matter; a
human can still read every column.
"""

from __future__ import annotations

import math
from collections import deque

TREND_TFS = ("M15", "H1", "H4")
STATE = {"up": 1, "down": -1, "none": 0}
LIQ_KINDS = ("liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken")
SESSION_CODE = {"ASIA": 1, "LONDON": 2, "NEW_YORK": 3}


class FeatureBuilder:
    """Attach to an engine; call ``on_events`` after every push, ``build`` at decisions."""

    def __init__(self, engine, memory_hours: int = 24) -> None:
        self.e = engine
        self.events: deque = deque()
        self.memory = memory_hours * 3600
        self.closes: deque = deque(maxlen=60 * 30)      # recent M1 closes (time, close)

    def on_events(self, bar, events) -> None:
        self.closes.append((bar.close_time, bar.close))
        for ev in events:
            if ev.kind in LIQ_KINDS or ev.kind in ("bos", "choch", "displacement", "close_spike"):
                self.events.append(ev)
        cutoff = bar.close_time - self.memory
        while self.events and self.events[0].available_at < cutoff:
            self.events.popleft()

    # ------------------------------------------------------------------ helpers
    def _ret_atr(self, minutes: int, atr: float) -> float:
        if not self.closes:
            return 0.0
        now_t, now_c = self.closes[-1]
        target = now_t - minutes * 60
        past = next((c for t, c in reversed(self.closes) if t <= target), self.closes[0][1])
        return (now_c - past) / atr

    def _count(self, kinds, hours: float, now: int, tf=None, pred=None) -> int:
        return sum(1 for ev in self.events
                   if ev.kind in kinds and ev.available_at > now - hours * 3600
                   and (tf is None or ev.tf == tf) and (pred is None or pred(ev)))

    # ------------------------------------------------------------------ build
    def build(self) -> dict | None:
        e = self.e
        atr = e.atr["H1"].value
        if atr is None or not self.closes or any(e.atr[tf].value is None for tf in ("M5", "H4")):
            return None                                   # warm-up: not enough history yet
        now, price = e.now, self.closes[-1][1]
        f: dict[str, float] = {}
        # --- trend per timeframe
        for tf in TREND_TFS:
            tr = e.trend[tf]
            f[f"trend_{tf}"] = STATE[tr.state]
            lb = tr.last_break
            f[f"last_break_{tf}"] = 0 if not lb else (1 if lb["kind"] == "bos" else 2) * (1 if lb["direction"] == "up" else -1)
            f[f"hours_since_break_{tf}"] = min(500.0, (now - lb["break_time"]) / 3600) if lb else 500.0
            prot = tr.protected.swing.price if tr.protected and not tr.protected.broken else None
            f[f"dist_protected_{tf}"] = (price - prot) / atr if prot is not None else 0.0
        # --- liquidity pools above / below
        above = [p for p in e.liquidity.pools if p.price > price]
        below = [p for p in e.liquidity.pools if p.price < price]
        f["pool_above_dist"] = min(((p.price - price) / atr for p in above), default=10.0)
        f["pool_below_dist"] = min(((price - p.price) / atr for p in below), default=10.0)
        f["pools_above_2atr"] = sum(1 for p in above if (p.price - price) / atr <= 2)
        f["pools_below_2atr"] = sum(1 for p in below if (price - p.price) / atr <= 2)
        # --- what just happened at liquidity (last 1h and 4h, by side)
        for k in LIQ_KINDS:
            for side in ("high", "low"):
                f[f"{k}_{side}_1h"] = self._count((k,), 1, now, pred=lambda ev, s=side: ev.data["side"] == s)
                f[f"{k}_{side}_4h"] = self._count((k,), 4, now, pred=lambda ev, s=side: ev.data["side"] == s)
        # --- recent BOS/CHoCH and displacement balance
        for tf in ("M15", "H1"):
            for k in ("bos", "choch"):
                up = self._count((k,), 4, now, tf, lambda ev: ev.data["direction"] == "up")
                dn = self._count((k,), 4, now, tf, lambda ev: ev.data["direction"] == "down")
                f[f"{k}_{tf}_4h_net"] = up - dn
            up = self._count(("displacement",), 4, now, tf, lambda ev: ev.data["direction"] == "up")
            dn = self._count(("displacement",), 4, now, tf, lambda ev: ev.data["direction"] == "down")
            f[f"disp_{tf}_4h_net"] = up - dn
        # --- fair value gaps and order blocks near price
        gaps = e.gaps.active
        f["fvg_bull_below_dist"] = min(((price - g.high) / atr for g in gaps if g.direction == "up" and g.high <= price), default=10.0)
        f["fvg_bear_above_dist"] = min(((g.low - price) / atr for g in gaps if g.direction == "down" and g.low >= price), default=10.0)
        f["fvg_inside"] = sum(1 for g in gaps if g.low <= price <= g.high)
        obs = e.obs.active
        f["ob_bull_below_dist"] = min(((price - o.high) / atr for o in obs if o.direction == "up" and o.high <= price), default=10.0)
        f["ob_bear_above_dist"] = min(((o.low - price) / atr for o in obs if o.direction == "down" and o.low >= price), default=10.0)
        f["ob_inside"] = sum(1 for o in obs if o.low <= price <= o.high)
        # --- supply/demand zones
        zones = e.zones.active
        f["demand_below_dist"] = min(((price - z.high) / atr for z in zones if z.side == "demand" and z.high <= price), default=10.0)
        f["supply_above_dist"] = min(((z.low - price) / atr for z in zones if z.side == "supply" and z.low >= price), default=10.0)
        # --- ranges
        for tf, rt in e.ranges.items():
            r = rt.active
            f[f"in_range_{tf}"] = 1 if r else 0
            f[f"range_pos_{tf}"] = (price - r.bottom) / (r.top - r.bottom) if r and r.top > r.bottom else 0.5
        # --- time, session, volatility, momentum
        hour = (now // 3600) % 24
        f["hour_sin"], f["hour_cos"] = math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)
        f["weekday"] = ((now // 86400) + 3) % 7
        win = e.sessions._window_of(now - 60)
        f["session"] = SESSION_CODE.get(win[0], 0) if win else 0
        f["atr_m5_over_h1"] = e.atr["M5"].value / atr
        f["atr_h1_over_h4"] = atr / e.atr["H4"].value
        for m in (60, 240, 1440):
            f[f"ret_{m}m"] = self._ret_atr(m, atr)
        # --- close spike at this very close (H1/H4)
        sp = [ev for ev in self.events if ev.kind == "close_spike" and ev.available_at == now]
        s = sp[-1].data if sp else None
        f["spike_now"] = (1 if s["direction"] == "up" else -1) if s else 0
        f["spike_move_atr"] = s["move_atr"] if s else 0.0
        f["spike_held"] = (1 if s["held"] else 0) if s else 0
        f["spike_swept_prev"] = (1 if s["swept_prev"] else 0) if s else 0
        return f
