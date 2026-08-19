"""Liquidity map — Equal Highs, Equal Lows, and liquidity sweeps.

Tracks zones where stop orders cluster (above EQH, below EQL) and detects
liquidity sweeps: price briefly pierces through a pool level, grabs stops,
then reverses.  A sweep of buy-side liquidity (above EQH) is bearish; a
sweep of sell-side liquidity (below EQL) is bullish.

Part of an ICT / SMC market-structure trading system for XAUUSD scalping.

No project imports.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuning constants
# ---------------------------------------------------------------------------

EQUAL_TOLERANCE_PTS: float = 1.0        # swings within 1 pt are "equal"
SWEEP_OVERSHOOT_MAX_PTS: float = 2.0    # max wick beyond pool to count as sweep
MAX_POOLS_PER_TF: int = 20
STALE_CANDLE_LIMIT: int = 200           # expire pools older than 200 candles
MAX_SWEEP_HISTORY: int = 30


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pool_id(pool_type: str, price: float, timeframe: str) -> str:
    return f"pool:{pool_type}:{timeframe}:{price:.2f}"


def _deduplicate_clusters(clusters: list[dict]) -> list[dict]:
    """Remove clusters that share the majority of their swing points."""
    keep: list[dict] = []
    for cl in clusters:
        swing_set = {id(s) for s in cl["swings"]}
        redundant = False
        for kept in keep:
            kept_set = {id(s) for s in kept["swings"]}
            overlap = len(swing_set & kept_set)
            # If the smaller cluster is a subset (or near-subset), drop it.
            if overlap >= min(len(swing_set), len(kept_set)):
                # Keep whichever has more swings.
                if cl["count"] > kept["count"]:
                    keep.remove(kept)
                else:
                    redundant = True
                break
        if not redundant:
            keep.append(cl)
    return keep


# ---------------------------------------------------------------------------
# LiquidityMap
# ---------------------------------------------------------------------------

class LiquidityMap:
    """Track equal-level formations and detect liquidity sweeps."""

    EQUAL_TOLERANCE_PTS = EQUAL_TOLERANCE_PTS
    SWEEP_OVERSHOOT_MAX_PTS = SWEEP_OVERSHOOT_MAX_PTS

    def __init__(self) -> None:
        self._pools: dict[str, list[dict]] = {}   # tf -> list of pools
        self._sweeps: list[dict] = []              # detected sweep events
        self._candle_counts: dict[str, int] = {}   # tf -> candles processed

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(
        self,
        timeframe: str,
        swings: list[dict],
        candles: list[dict],
        current_price: float,
    ) -> dict:
        """Update liquidity map with latest swing and candle data.

        Args:
            timeframe: ``"M5"``, ``"M15"``, etc.
            swings: swing points ``[{kind, price, time, evidence_id}]``
            candles: recent OHLC candles (keys: open, high, low, close,
                closed_at_utc).
            current_price: live price.

        Returns:
            ``{"pools": [...], "new_sweeps": [...]}``
        """
        self._candle_counts[timeframe] = (
            self._candle_counts.get(timeframe, 0) + len(candles)
        )

        # 1 - Build equal-level pools from swing data.
        eq_levels = self.detect_equal_levels(swings)

        # Merge with existing pools (replace by pool_id).
        existing = {p["pool_id"]: p for p in self._pools.get(timeframe, [])}
        for lvl in eq_levels:
            pid = _pool_id(lvl["type"], lvl["price"], timeframe)
            lvl["pool_id"] = pid
            lvl["timeframe"] = timeframe
            lvl["_birth_candle_idx"] = existing.get(pid, {}).get(
                "_birth_candle_idx", self._candle_counts[timeframe] - len(candles)
            )
            existing[pid] = lvl

        # Expire stale pools.
        active: list[dict] = []
        for pool in existing.values():
            age = self._candle_counts[timeframe] - pool.get("_birth_candle_idx", 0)
            if age <= STALE_CANDLE_LIMIT:
                active.append(pool)
            else:
                log.debug("Expired pool %s (age %d candles)", pool["pool_id"], age)

        # Cap per timeframe.
        active.sort(key=lambda p: p["count"], reverse=True)
        active = active[:MAX_POOLS_PER_TF]
        self._pools[timeframe] = active

        # 2 - Detect sweeps.
        new_sweeps = self.detect_sweeps(timeframe, candles, active)

        log.info(
            "LiquidityMap update %s: %d pools, %d new sweeps",
            timeframe, len(active), len(new_sweeps),
        )

        return {
            "pools": active,
            "new_sweeps": new_sweeps,
        }

    # ------------------------------------------------------------------
    # detect_equal_levels
    # ------------------------------------------------------------------

    def detect_equal_levels(self, swings: list[dict]) -> list[dict]:
        """Find EQH and EQL formations from swing points.

        Returns list of dicts with keys: type, price, count, swings,
        liquidity_side, strength.
        """
        highs = [s for s in swings if s.get("kind") == "high"]
        lows = [s for s in swings if s.get("kind") == "low"]

        clusters: list[dict] = []

        # --- Equal Highs (EQH) ---
        used_high_indices: set[int] = set()
        for i, h1 in enumerate(highs):
            if i in used_high_indices:
                continue
            cluster = [h1]
            for j, h2 in enumerate(highs[i + 1:], start=i + 1):
                if abs(h1["price"] - h2["price"]) <= self.EQUAL_TOLERANCE_PTS:
                    cluster.append(h2)
                    used_high_indices.add(j)
            if len(cluster) >= 2:
                used_high_indices.add(i)
                avg_price = round(
                    sum(s["price"] for s in cluster) / len(cluster), 4
                )
                clusters.append({
                    "type": "EQH",
                    "price": avg_price,
                    "count": len(cluster),
                    "swings": cluster,
                    "liquidity_side": "buy_side",
                    "strength": "strong" if len(cluster) >= 3 else "moderate",
                })

        # --- Equal Lows (EQL) ---
        used_low_indices: set[int] = set()
        for i, l1 in enumerate(lows):
            if i in used_low_indices:
                continue
            cluster = [l1]
            for j, l2 in enumerate(lows[i + 1:], start=i + 1):
                if abs(l1["price"] - l2["price"]) <= self.EQUAL_TOLERANCE_PTS:
                    cluster.append(l2)
                    used_low_indices.add(j)
            if len(cluster) >= 2:
                used_low_indices.add(i)
                avg_price = round(
                    sum(s["price"] for s in cluster) / len(cluster), 4
                )
                clusters.append({
                    "type": "EQL",
                    "price": avg_price,
                    "count": len(cluster),
                    "swings": cluster,
                    "liquidity_side": "sell_side",
                    "strength": "strong" if len(cluster) >= 3 else "moderate",
                })

        # Deduplicate overlapping clusters.
        clusters = _deduplicate_clusters(clusters)
        return clusters

    # ------------------------------------------------------------------
    # detect_sweeps
    # ------------------------------------------------------------------

    def detect_sweeps(
        self,
        timeframe: str,
        candles: list[dict],
        pools: list[dict],
    ) -> list[dict]:
        """Detect liquidity sweeps -- price pierces a pool then reverses.

        A sweep is a candle whose wick exceeds the pool level but whose
        close is back on the other side (rejection).

        Returns list of sweep dicts.
        """
        # Build set of already-swept pool+timeframe keys for dedup.
        swept_keys: set[str] = set()
        for s in self._sweeps:
            if s["timeframe"] == timeframe:
                swept_keys.add(f"{s['pool_price']:.2f}:{timeframe}")

        new_sweeps: list[dict] = []

        for candle in candles:
            for pool in pools:
                dedup_key = f"{pool['price']:.2f}:{timeframe}"
                if dedup_key in swept_keys:
                    continue

                sweep: dict | None = None

                if pool["type"] == "EQH":
                    # Sweep = wick above EQH but close below.
                    if (
                        candle["high"] > pool["price"]
                        and candle["close"] < pool["price"]
                    ):
                        overshoot = round(candle["high"] - pool["price"], 4)
                        if overshoot <= self.SWEEP_OVERSHOOT_MAX_PTS:
                            body = abs(candle["close"] - candle["open"])
                            upper_wick = candle["high"] - max(candle["open"], candle["close"])
                            confidence = (
                                "high"
                                if upper_wick > body * 0.5
                                else "medium"
                            )
                            sweep = {
                                "type": "sweep",
                                "pool_type": "EQH",
                                "pool_price": pool["price"],
                                "sweep_price": round(candle["high"], 4),
                                "overshoot": overshoot,
                                "sweep_candle": dict(candle),
                                "direction": "bearish",
                                "timeframe": timeframe,
                                "detected_at": (
                                    candle.get("close_time_utc")
                                    or candle.get("closed_at_utc")
                                    or datetime.now(timezone.utc).isoformat()
                                ),
                                "confidence": confidence,
                            }

                elif pool["type"] == "EQL":
                    # Sweep = wick below EQL but close above.
                    if (
                        candle["low"] < pool["price"]
                        and candle["close"] > pool["price"]
                    ):
                        overshoot = round(pool["price"] - candle["low"], 4)
                        if overshoot <= self.SWEEP_OVERSHOOT_MAX_PTS:
                            body = abs(candle["close"] - candle["open"])
                            lower_wick = min(candle["open"], candle["close"]) - candle["low"]
                            confidence = (
                                "high"
                                if lower_wick > body * 0.5
                                else "medium"
                            )
                            sweep = {
                                "type": "sweep",
                                "pool_type": "EQL",
                                "pool_price": pool["price"],
                                "sweep_price": round(candle["low"], 4),
                                "overshoot": overshoot,
                                "sweep_candle": dict(candle),
                                "direction": "bullish",
                                "timeframe": timeframe,
                                "detected_at": (
                                    candle.get("close_time_utc")
                                    or candle.get("closed_at_utc")
                                    or datetime.now(timezone.utc).isoformat()
                                ),
                                "confidence": confidence,
                            }

                if sweep is not None:
                    new_sweeps.append(sweep)
                    swept_keys.add(dedup_key)
                    log.info(
                        "Liquidity sweep detected: %s %s at %.2f (overshoot %.2f)",
                        sweep["direction"], sweep["pool_type"],
                        sweep["pool_price"], sweep["overshoot"],
                    )

        # Store and cap history.
        self._sweeps.extend(new_sweeps)
        if len(self._sweeps) > MAX_SWEEP_HISTORY:
            self._sweeps = self._sweeps[-MAX_SWEEP_HISTORY:]

        return new_sweeps

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def active_pools(
        self,
        timeframe: str | None = None,
        side: str | None = None,
    ) -> list[dict]:
        """Get active liquidity pools.

        Args:
            timeframe: filter to a specific TF, or ``None`` for all.
            side: ``"buy_side"`` or ``"sell_side"``, or ``None`` for both.
        """
        result: list[dict] = []
        tfs = [timeframe] if timeframe else list(self._pools.keys())
        for tf in tfs:
            for pool in self._pools.get(tf, []):
                if side and pool.get("liquidity_side") != side:
                    continue
                result.append(pool)
        return result

    def recent_sweeps(self, max_age_minutes: int = 60) -> list[dict]:
        """Return sweep events from the last *max_age_minutes*."""
        now = datetime.now(timezone.utc)
        out: list[dict] = []
        for s in self._sweeps:
            try:
                dt = datetime.fromisoformat(s["detected_at"])
                age = (now - dt).total_seconds() / 60.0
                if age <= max_age_minutes:
                    out.append(s)
            except (KeyError, ValueError):
                out.append(s)
        return out

    def snapshot(self) -> dict:
        """Full liquidity map state."""
        return {
            "pools_by_tf": {
                tf: list(pools) for tf, pools in self._pools.items()
            },
            "total_pools": sum(len(v) for v in self._pools.values()),
            "sweeps": list(self._sweeps),
            "total_sweeps": len(self._sweeps),
        }


# ---------------------------------------------------------------------------
# self_test
# ---------------------------------------------------------------------------

def self_test() -> None:
    """Smoke-test with synthetic XAUUSD data."""
    print("=== LiquidityMap self_test ===\n")

    lm = LiquidityMap()

    # --- 1. Equal level detection ---
    swings = [
        {"kind": "high", "price": 2395.0, "time": "2026-08-18T10:00:00Z", "evidence_id": "sh1"},
        {"kind": "high", "price": 2395.8, "time": "2026-08-18T10:25:00Z", "evidence_id": "sh2"},
        {"kind": "high", "price": 2395.3, "time": "2026-08-18T10:50:00Z", "evidence_id": "sh3"},
        {"kind": "low",  "price": 2380.0, "time": "2026-08-18T10:05:00Z", "evidence_id": "sl1"},
        {"kind": "low",  "price": 2380.5, "time": "2026-08-18T10:30:00Z", "evidence_id": "sl2"},
        {"kind": "high", "price": 2410.0, "time": "2026-08-18T11:00:00Z", "evidence_id": "sh4"},
        {"kind": "low",  "price": 2360.0, "time": "2026-08-18T11:05:00Z", "evidence_id": "sl3"},
    ]

    eq = lm.detect_equal_levels(swings)
    eqh = [e for e in eq if e["type"] == "EQH"]
    eql = [e for e in eq if e["type"] == "EQL"]

    assert len(eqh) >= 1, f"Expected at least 1 EQH cluster, got {len(eqh)}"
    assert eqh[0]["count"] == 3, f"Expected 3-touch EQH, got {eqh[0]['count']}"
    assert eqh[0]["strength"] == "strong", f"3-touch should be strong, got {eqh[0]['strength']}"
    assert eqh[0]["liquidity_side"] == "buy_side"
    print(f"  EQH: price={eqh[0]['price']}, count={eqh[0]['count']}, strength={eqh[0]['strength']}")

    assert len(eql) >= 1, f"Expected at least 1 EQL cluster, got {len(eql)}"
    assert eql[0]["count"] == 2, f"Expected 2-touch EQL, got {eql[0]['count']}"
    assert eql[0]["strength"] == "moderate"
    assert eql[0]["liquidity_side"] == "sell_side"
    print(f"  EQL: price={eql[0]['price']}, count={eql[0]['count']}, strength={eql[0]['strength']}")

    # 2410 and 2360 should NOT form clusters (no match).
    solo_high = [e for e in eqh if abs(e["price"] - 2410.0) < 1.0]
    assert len(solo_high) == 0, "Solo swing high should not form a cluster"
    print("  Solo swings correctly excluded from clusters.")

    # --- 2. Full update + sweep detection ---
    candles = [
        {"open": 2393.0, "high": 2394.0, "low": 2392.0, "close": 2393.5,
         "closed_at_utc": "2026-08-18T11:30:00Z"},
        {"open": 2394.0, "high": 2396.5, "low": 2393.0, "close": 2393.5,
         "closed_at_utc": "2026-08-18T11:35:00Z"},  # sweep candle: wick above EQH, close below
        {"open": 2393.0, "high": 2393.5, "low": 2379.0, "close": 2380.8,
         "closed_at_utc": "2026-08-18T11:40:00Z"},  # sweep candle: wick below EQL, close above
    ]

    result = lm.update("M5", swings, candles, current_price=2390.0)

    assert len(result["pools"]) >= 2, f"Expected >= 2 pools, got {len(result['pools'])}"
    print(f"\n  Pools after update: {len(result['pools'])}")
    for p in result["pools"]:
        print(f"    {p['type']} @ {p['price']}, side={p['liquidity_side']}, strength={p['strength']}")

    assert len(result["new_sweeps"]) >= 1, (
        f"Expected at least 1 sweep, got {len(result['new_sweeps'])}"
    )
    for sw in result["new_sweeps"]:
        print(
            f"\n  Sweep: {sw['direction']} {sw['pool_type']} "
            f"@ {sw['pool_price']}, overshoot={sw['overshoot']}, "
            f"confidence={sw['confidence']}"
        )
        assert sw["type"] == "sweep"
        assert sw["overshoot"] <= SWEEP_OVERSHOOT_MAX_PTS

    # Check bearish sweep of EQH.
    bearish = [s for s in result["new_sweeps"] if s["direction"] == "bearish"]
    assert len(bearish) >= 1, "Expected bearish sweep of EQH"

    # Check bullish sweep of EQL.
    bullish = [s for s in result["new_sweeps"] if s["direction"] == "bullish"]
    assert len(bullish) >= 1, "Expected bullish sweep of EQL"

    # --- 3. Query helpers ---
    buy_pools = lm.active_pools(side="buy_side")
    sell_pools = lm.active_pools(side="sell_side")
    assert len(buy_pools) >= 1
    assert len(sell_pools) >= 1
    print(f"\n  Buy-side pools: {len(buy_pools)}, Sell-side pools: {len(sell_pools)}")

    recent = lm.recent_sweeps(max_age_minutes=5)
    assert len(recent) >= 1
    print(f"  Recent sweeps (5 min): {len(recent)}")

    snap = lm.snapshot()
    assert snap["total_pools"] >= 2
    assert snap["total_sweeps"] >= 1
    print(f"  Snapshot: {snap['total_pools']} pools, {snap['total_sweeps']} sweeps")

    # --- 4. Dedup: same pool not swept twice ---
    result2 = lm.update("M5", swings, candles, current_price=2390.0)
    assert len(result2["new_sweeps"]) == 0, (
        f"Same pools should not be re-swept, got {len(result2['new_sweeps'])} new sweeps"
    )
    print("  Dedup: second pass produced 0 new sweeps (correct).")

    # --- 5. Pool cap ---
    many_swings = []
    for i in range(50):
        price = 2300.0 + i * 5
        many_swings.append({"kind": "high", "price": price, "time": f"T{i}a", "evidence_id": f"h{i}a"})
        many_swings.append({"kind": "high", "price": price + 0.3, "time": f"T{i}b", "evidence_id": f"h{i}b"})

    lm2 = LiquidityMap()
    dummy_candles = [{"open": 2000, "high": 2001, "low": 1999, "close": 2000, "closed_at_utc": "T"}]
    r = lm2.update("M5", many_swings, dummy_candles, 2000.0)
    assert len(r["pools"]) <= MAX_POOLS_PER_TF, (
        f"Pool cap breached: {len(r['pools'])} > {MAX_POOLS_PER_TF}"
    )
    print(f"  Pool cap: {len(r['pools'])} pools (max {MAX_POOLS_PER_TF}).")

    print("\n=== All LiquidityMap self_test checks passed ===")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    self_test()
