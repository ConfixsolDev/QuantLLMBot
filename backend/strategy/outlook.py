"""The market outlook Qwen reads: a compact, deterministic summary of NOW.

Everything comes from the structure engine's snapshot and its recent events —
no new analysis here, only selection and compression (the whole prompt must
stay under the strategy's ``prompt.max_bytes``, 6 KB, so the GPU answers fast).

Output of ``build`` (keys kept short on purpose)::

    {"t": "2026-10-30T12:00Z", "px": 3966.2, "sess": "NEW_YORK",
     "atr": {"M15": 8.1, "H1": 14.9},
     "trend": {"M5": ["dn", 3984.9], ... "H4": ["up", 3901.0]},   # state, protected level
     "levels": [["R", 4058.25, "H1 sw high+LONDON high", 2, 1.6], ...],
                # R = resistance / S = support, price, sources, tests so far,
                # distance from price in ATR(M15) (+ above, - below)
     "vwap": {"day": [4049.3, -1.2], ...}}                         # vwap, (px - vwap) / sigma

and a list of recent evidence: (engine event id, one-line text).
"""

from __future__ import annotations

import time

TREND = {"up": "up", "down": "dn", "none": "-"}
EVIDENCE_KINDS = {
    "bos", "choch", "liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken",
    "level_test", "level_rejection", "level_followthrough", "level_held", "level_broken",
    "level_pattern", "pattern_confirmed", "vwap_band_reject", "close_spike",
}


def hhmm(t: int) -> str:
    return time.strftime("%H:%M", time.gmtime(t))


def iso(t: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(t))


def short_sources(sources: list[str]) -> str:
    return "+".join(s.replace(" swing ", " sw ").replace("NEW_YORK", "NY") for s in sources)


def brief(e: dict) -> str | None:
    """One short line per engine event (None = not evidence-worthy)."""
    k, d, tf = e["kind"], e["data"], e["tf"]
    t = hhmm(e["available_at"])
    if k in ("bos", "choch"):
        if tf in ("M1",):
            return None
        return f"{t} {tf} {k.upper()} {'up' if d['direction'] == 'up' else 'dn'} close beyond {d['level']:.2f}"
    if k in ("liquidity_sweep", "sweep_failed", "false_break", "liquidity_taken"):
        name = {"liquidity_sweep": "sweep", "sweep_failed": "sweep failed", "false_break": "false break",
                "liquidity_taken": "taken"}[k]
        prices = sorted({round(x["price"], 2) for x in d["levels"]})
        kinds = sorted({x["kind"].split("_")[0] if x["kind"].startswith(("swing", "equal")) else x["kind"]
                        for x in d["levels"]})
        return f"{t} {name} {d['side']} {'/'.join(f'{p:.2f}' for p in prices)} ({','.join(kinds)})"
    if k.startswith("level_"):
        lv = d["level"]
        name = f"{'R' if lv['side'] == 'high' else 'S'} {lv['price']:.2f} {short_sources(lv['sources'])}"
        if k == "level_test":
            return f"{t} test {d['test_no']} of {name}, {d['approach']} in"
        if k == "level_rejection":
            return f"{t} M1 rejection at {name} (test {d['test_no']}, poke {d['pierce_atr']} ATR)"
        if k == "level_followthrough":
            return f"{t} after rejection at {name}: {d['result']} {d['move_atr']} ATR"
        if k == "level_held":
            return f"{t} {name} held on test {d['test_no']}"
        if k == "level_broken":
            return f"{t} {name} broken (M5 close) after {d['tests']} tests"
        if k == "level_pattern":
            return f"{t} M1 {d['pattern']} at {name}"
        return None
    if k == "pattern_confirmed":
        return f"{t} M1 {d['kind']} confirmed, neckline {d['neckline']:.2f}"
    if k == "vwap_band_reject":
        return f"{t} VWAP {d['anchor']} {d['band']}sd {d['side']} band reject"
    if k == "close_spike":
        return f"{t} {tf} close spike {d['direction']} {d['move']:.1f} ({'held' if d['held'] else 'rejected'})"
    return None


def build(snapshot: dict, price: float, session: str | None, max_levels: int) -> dict:
    atr15 = snapshot["atr"].get("M15") or 0.0
    out = {
        "t": iso(snapshot["as_of"]), "px": round(price, 2), "sess": session or "OFF",
        "atr": {tf: round(snapshot["atr"][tf], 2) for tf in ("M15", "H1") if snapshot["atr"].get(tf)},
        "trend": {tf: [TREND.get(v["state"], v["state"]),
                       round(v["protected"], 2) if v.get("protected") is not None else None]
                  for tf, v in snapshot["trend"].items()},
    }
    levels = []
    for lv in snapshot.get("htf_levels", [])[:max_levels]:
        dist = round((lv["price"] - price) / atr15, 1) if atr15 else None
        levels.append(["R" if lv["side"] == "high" else "S", round(lv["price"], 2),
                       short_sources(lv["sources"]), lv["tests"], dist])
    out["levels"] = levels
    vw = {}
    for anchor, v in (snapshot.get("vwap") or {}).items():
        if v and v.get("sd"):
            vw[anchor] = [round(v["vwap"], 2), round((price - v["vwap"]) / v["sd"], 1)]
    out["vwap"] = vw
    return out
