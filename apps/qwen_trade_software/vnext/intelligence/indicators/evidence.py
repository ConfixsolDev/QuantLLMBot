"""Small, explicit indicator evidence layer; never a trade signal."""

from __future__ import annotations

from statistics import mean
from typing import Iterable

from vnext.data.bars import Bar


def indicator_evidence(bars: Iterable[Bar], *, spread: float | None = None) -> dict:
    rows = list(bars)
    if not rows:
        return {"status": "unavailable", "bars": 0, "vwap": None, "participation": None, "spread": spread}
    volume = sum(max(0.0, bar.tick_volume) for bar in rows)
    vwap = (sum(((bar.high + bar.low + bar.close) / 3) * max(0.0, bar.tick_volume) for bar in rows) / volume) if volume else None
    recent = mean([bar.tick_volume for bar in rows[-min(5, len(rows)):]])
    prior = mean([bar.tick_volume for bar in rows[:-min(5, len(rows))]]) if len(rows) > 5 else recent
    ratio = recent / prior if prior else None
    return {"status": "ready", "bars": len(rows), "vwap": round(vwap, 8) if vwap is not None else None,
            "participation": {"recent_volume": recent, "baseline_volume": prior,
                              "ratio": round(ratio, 6) if ratio is not None else None},
            "spread": spread, "authority": "supportive_evidence_only"}
