"""Zone ranking: which active zones matter most right now (top N).

Each active zone gets eight features, every one scaled to 0..1 so the config
weights (``scoring.weights``) mean what they say:

=========== ===============================================================
freshness   1 / (1 + tests). Untouched zones still hold their orders.
departure   departure_move_atr / departure_cap_atr, capped at 1. Violent
            departures mean more unfilled orders were left behind.
base        1.0 for a one-candle base, falling to 0 at base_max_candles.
            Short bases = decisive; long bases = indecision.
volume      departure volume ratio / volume_cap_ratio, capped at 1.
room        distance from this zone's proximal edge to the nearest OPPOSING
            active zone, in this zone's ATR / room_cap_atr, capped at 1.
            (Room to run before the next wall.) 1.0 if no opposing zone.
nesting     1.0 if a same-side zone of a LOWER timeframe sits inside this
            zone (a refined entry inside a higher-timeframe area).
liquidity   1.0 if a confirmed session / prior-day high or low lies inside
            the zone or within liquidity_proximity_atr x ATR of it (stops
            resting there can fuel the reaction).
timeframe   scoring.timeframe_weight[zone tf] (H4 > H1 > M30 by default).
=========== ===============================================================

score = sum(weight * feature) / sum(weights), in 0..1.

STATUS: built, NOT yet validated. Whether higher scores really hold better is
measured by forward usefulness (first-retest hold rate per score bucket) on
real data — see the architecture doc, "How accuracy is verified".
"""

from __future__ import annotations

from .zones import Zone


def _tf_rank(cfg: dict, tf: str) -> int:
    return cfg["timeframes"][tf]


def score_zones(zones: list[Zone], levels: list[float], cfg: dict) -> list[dict]:
    """Return the top-N active zones with their score and feature breakdown."""
    s = cfg["scoring"]
    w = s["weights"]
    total_w = sum(w.values()) or 1.0
    base_max = cfg["zones"]["base_max_candles"]
    ranked = []
    for z in zones:
        if not z.active:
            continue
        opposing = [o for o in zones if o.active and o.side != z.side]
        if z.side == "demand":     # opposing supply ABOVE
            gaps = [o.low - z.high for o in opposing if o.low >= z.high]
        else:                      # opposing demand BELOW
            gaps = [z.low - o.high for o in opposing if o.high <= z.low]
        room = min(1.0, (min(gaps) / z.atr) / s["room_cap_atr"]) if gaps else 1.0
        nested = any(
            o.active and o.side == z.side and _tf_rank(cfg, o.tf) < _tf_rank(cfg, z.tf)
            and o.low >= z.low and o.high <= z.high
            for o in zones
        )
        reach = s["liquidity_proximity_atr"] * z.atr
        liquid = any(z.low - reach <= p <= z.high + reach for p in levels)
        f = {
            "freshness": 1.0 / (1 + z.tests),
            "departure": min(1.0, z.departure_move_atr / s["departure_cap_atr"]),
            "base": 1.0 if base_max <= 1 else 1.0 - (z.base_len - 1) / (base_max - 1),
            "volume": min(1.0, z.departure_volume_ratio / s["volume_cap_ratio"]),
            "room": room,
            "nesting": 1.0 if nested else 0.0,
            "liquidity": 1.0 if liquid else 0.0,
            "timeframe": s["timeframe_weight"][z.tf],
        }
        score = sum(w[k] * f[k] for k in w) / total_w
        ranked.append({"score": round(score, 4),
                       "features": {k: round(v, 4) for k, v in f.items()},
                       "zone": z.as_dict()})
    # deterministic order: score desc, then id
    ranked.sort(key=lambda r: (-r["score"], r["zone"]["id"]))
    return ranked[: s["top_n"]]
