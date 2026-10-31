"""Supply and demand zones: "base + departure", with a lifecycle.

The idea in one picture (DEMAND; supply is the mirror image)
------------------------------------------------------------
::

          departure: 1-3 strong candles that leave fast
                    |
          ┌─┐ ┌─┐   ▲   price left the base by >= departure_min_move_atr
    ──────┤ ├─┤ ├───┘
    base: 1-3 small candles      <- the ZONE is the base's price range
    (each range <= base_max_range_atr)

Big players filled orders in the base; the violent departure shows demand
overwhelmed supply there. When price later RETURNS to the base, unfilled
orders may defend it again. That return is a "test".

Detection (on each CLOSED bar of a zone timeframe: H4, H1, M30)
---------------------------------------------------------------
Try departure lengths d = 1 .. departure_max_candles ending at the new bar:

1. The first departure candle points the right way (bullish for demand) and
   its body >= ``departure_min_body_atr`` x ATR.
2. Every later departure candle closes beyond the previous one (one push).
3. The base = up to ``base_max_candles`` candles right before the departure,
   each with range <= ``base_max_range_atr`` x ATR. At least one is needed.
4. The departure's last close is >= ``departure_min_move_atr`` x ATR beyond
   the base edge (above base high for demand).

ATR is the value as of the LAST BASE candle — measured before the departure
existed, so a huge departure candle cannot lower its own bar.

Zone bounds:  demand  low = min(base lows, first departure low), high = base high
              supply  high = max(base highs, first departure high), low = base low
Proximal edge (where price meets the zone first): demand high / supply low.
Distal edge (the invalidation side):              demand low  / supply high.

Lifecycle (updated on every CLOSED M1 bar after the zone became known)
----------------------------------------------------------------------
FRESH  --price trades into the proximal edge-->  TESTED (tests += 1)
any    --an M1 CLOSE beyond distal +/- break_close_buffer_atr x ATR-->  BROKEN
any    --older than max_age_bars bars of its own timeframe-->        EXPIRED
any    --tested more than max_tests times-->                         EXPIRED

A "test" counts once per visit: price must leave the zone (an M1 bar fully
outside) before the next touch counts again. BROKEN and EXPIRED are final.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bars import Bar

FRESH, TESTED, BROKEN, EXPIRED = "FRESH", "TESTED", "BROKEN", "EXPIRED"


@dataclass
class Zone:
    id: str
    tf: str
    side: str                    # "demand" | "supply"
    low: float
    high: float
    time: int                    # open time of the first departure candle
    base_start: int              # open time of the first base candle
    base_len: int
    departure_len: int
    departure_move_atr: float    # how far the departure travelled, in ATR
    departure_volume_ratio: float  # departure avg volume / prior avg volume
    atr: float                   # the ATR used to judge it (zone timeframe)
    created_at: int              # available_at of the zone_created event
    status: str = FRESH
    tests: int = 0
    age_bars: int = 0
    inside: bool = False         # currently inside (visit already counted)
    closed_at: int | None = None
    close_reason: str | None = None

    @property
    def proximal(self) -> float:
        return self.high if self.side == "demand" else self.low

    @property
    def distal(self) -> float:
        return self.low if self.side == "demand" else self.high

    @property
    def active(self) -> bool:
        return self.status in (FRESH, TESTED)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "tf": self.tf, "side": self.side, "low": self.low,
            "high": self.high, "proximal": self.proximal, "distal": self.distal,
            "time": self.time, "base_start": self.base_start, "base_len": self.base_len,
            "departure_len": self.departure_len,
            "departure_move_atr": round(self.departure_move_atr, 4),
            "departure_volume_ratio": round(self.departure_volume_ratio, 4),
            "atr": round(self.atr, 6), "created_at": self.created_at,
            "status": self.status, "tests": self.tests, "age_bars": self.age_bars,
            "closed_at": self.closed_at, "close_reason": self.close_reason,
        }


@dataclass
class _TfState:
    """Closed bars and the ATR after each, for one zone timeframe."""
    bars: list[Bar] = field(default_factory=list)
    atr_after: list[float | None] = field(default_factory=list)
    used_departures: set[tuple[str, int]] = field(default_factory=set)


class ZoneBook:
    """Detects zones on their timeframes and runs every zone's lifecycle."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg["zones"]
        self.volume_lookback = cfg["scoring"]["volume_lookback"]
        self.state = {tf: _TfState() for tf in self.cfg["timeframes"]}
        self.active: list[Zone] = []
        self.closed: list[Zone] = []           # recent finished zones (bounded)
        # how many closed bars to keep per timeframe: enough for base +
        # departure + the volume look-back, and a margin
        self._keep = self.cfg["base_max_candles"] + self.cfg["departure_max_candles"] + self.volume_lookback + 5

    # ------------------------------------------------------------- detection
    def on_tf_bar(self, tf: str, bar: Bar, atr_after: float | None, now: int,
                  make_id) -> list[Zone]:
        """A bar of a zone timeframe closed. Age zones, then look for new ones.

        Returns newly created zones (the engine turns them into events).
        ``make_id(tf, side, time)`` gives the deterministic zone id.
        """
        st = self.state[tf]
        st.bars.append(bar)
        st.atr_after.append(atr_after)
        if len(st.bars) > self._keep:            # bounded memory for 10-year runs
            drop = len(st.bars) - self._keep
            del st.bars[:drop]
            del st.atr_after[:drop]
        created: list[Zone] = []
        c = self.cfg
        last = len(st.bars) - 1
        for d in range(1, c["departure_max_candles"] + 1):
            first = last - d + 1                  # index of the first departure candle
            base_last = first - 1
            if base_last < 0:
                break
            atr = st.atr_after[base_last]
            if atr is None or atr <= 0:
                continue
            dep = st.bars[first:last + 1]
            for side in ("demand", "supply"):
                key = (side, dep[0].time)
                if key in st.used_departures:
                    continue
                zone = self._try_zone(tf, side, st, base_last, dep, atr, now, make_id)
                if zone is not None:
                    st.used_departures.add(key)
                    created.append(zone)
        # forget dedupe keys older than anything we still hold
        oldest = st.bars[0].time
        st.used_departures = {k for k in st.used_departures if k[1] >= oldest}
        return created

    def _try_zone(self, tf, side, st, base_last, dep, atr, now, make_id) -> Zone | None:
        c = self.cfg
        up = side == "demand"
        d0 = dep[0]
        # (1) first departure candle: right direction and a real body
        if (up and not d0.bullish) or (not up and not d0.bearish):
            return None
        if d0.body < c["departure_min_body_atr"] * atr:
            return None
        # (2) one push: each later candle closes beyond the previous close
        for prev, cur in zip(dep, dep[1:]):
            if (up and cur.close <= prev.close) or (not up and cur.close >= prev.close):
                return None
        # (3) base: small candles right before the departure (newest first)
        base: list[Bar] = []
        j = base_last
        while j >= 0 and len(base) < c["base_max_candles"]:
            if st.bars[j].range > c["base_max_range_atr"] * atr:
                break
            base.insert(0, st.bars[j])
            j -= 1
        if not base:
            return None
        base_hi = max(b.high for b in base)
        base_lo = min(b.low for b in base)
        # (4) the departure travelled far enough beyond the base edge
        move = (dep[-1].close - base_hi) if up else (base_lo - dep[-1].close)
        if move < c["departure_min_move_atr"] * atr:
            return None
        low = min(base_lo, d0.low) if up else base_lo
        high = base_hi if up else max(base_hi, d0.high)
        if high <= low:
            return None
        # skip if it is mostly the same area as a zone we already track
        for z in self.active:
            if z.tf == tf and z.side == side:
                overlap = min(z.high, high) - max(z.low, low)
                if overlap > 0 and overlap / min(z.high - z.low, high - low) >= c["merge_overlap_ratio"]:
                    return None
        # volume: departure average vs the bars before the base
        start_prior = max(0, base_last - len(base) + 1 - self.volume_lookback)
        prior = st.bars[start_prior: base_last - len(base) + 1]
        prior_avg = sum(b.volume for b in prior) / len(prior) if prior else 0.0
        dep_avg = sum(b.volume for b in dep) / len(dep)
        vol_ratio = dep_avg / prior_avg if prior_avg > 0 else 1.0
        zone = Zone(
            id=make_id(tf, side, d0.time), tf=tf, side=side, low=low, high=high,
            time=d0.time, base_start=base[0].time, base_len=len(base),
            departure_len=len(dep), departure_move_atr=move / atr,
            departure_volume_ratio=vol_ratio, atr=atr, created_at=now,
        )
        self.active.append(zone)
        return zone

    # ------------------------------------------------------------- lifecycle
    def age(self, tf: str, now: int) -> list[Zone]:
        """A bar of ``tf`` closed: zones on that timeframe get one bar older."""
        expired = []
        for z in self.active:
            if z.tf == tf and now > z.created_at:
                z.age_bars += 1
                if z.age_bars > self.cfg["max_age_bars"]:
                    expired.append(self._close(z, EXPIRED, now, "max_age"))
        return expired

    def on_m1(self, bar: Bar, now: int) -> list[tuple[str, Zone]]:
        """Update every active zone with one closed M1 bar.

        Returns (event_kind, zone) pairs: zone_tested / zone_broken / zone_expired.
        Zones created on this very bar are skipped (they did not exist yet).
        """
        out: list[tuple[str, Zone]] = []
        buf = self.cfg["break_close_buffer_atr"]
        for z in list(self.active):
            if bar.time < z.created_at:
                continue
            if z.side == "demand":
                broken = bar.close < z.low - buf * z.atr
                touched = bar.low <= z.high
            else:
                broken = bar.close > z.high + buf * z.atr
                touched = bar.high >= z.low
            if broken:
                out.append(("zone_broken", self._close(z, BROKEN, now, "close_beyond_distal")))
                continue
            if touched and not z.inside:
                z.inside = True
                z.tests += 1
                z.status = TESTED
                out.append(("zone_tested", z))
                if z.tests > self.cfg["max_tests"]:
                    out.append(("zone_expired", self._close(z, EXPIRED, now, "max_tests")))
            elif not touched:
                z.inside = False
        return out

    def _close(self, z: Zone, status: str, now: int, reason: str) -> Zone:
        z.status, z.closed_at, z.close_reason = status, now, reason
        self.active.remove(z)
        self.closed.append(z)
        del self.closed[:-200]
        return z
