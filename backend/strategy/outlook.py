"""What Qwen reads about the market and about each candidate (template v2).

Everything comes from the structure engine (snapshot, recent candles, events)
— selection and compression only, no new analysis. Field names are spelled
out and explained in the strategy's ``legend`` (a 14B model reads named
fields far more reliably than positional arrays; v1 used arrays and a reader
had to guess what ["up", 4069.0] meant). All distances are in ATR(M15).

``market(...)``::

    {"now": "2026-07-14 15:09Z", "session": "NEW_YORK", "session_min": 129, "price": 4098.6,
     "atr": {"M15": 13.1, "H1": 18.9}, "m15_range_vs_atr": 1.6,
     "day": {"high": 4099.4, "low": 4031.0},
     "trend": {"H4": {"dir": "down", "protected": 4121.2}, ...},   (the breaks themselves are evidence)
     "ranges": {"H1": {"top": .., "bottom": .., "pos": 0.9}},
     "vwap": {"day": {"at": 4038.5, "sd_away": 1.7}, ...},
     "levels": [{"side": "R", "price": 4103.3, "src": "LONDON high+H1 sw high", "tests": 0, "atr_away": 0.4}]}

``candidate(...)``: level + its history, approach, rejection quality, the
exact trade (entry / stop / target from code), and the obstacles on the way.
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


DIR = {"up": "up", "down": "down", "none": "none"}


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def market(engine, snapshot: dict, price: float, now: int, exclude_levels: set, max_levels: int) -> dict:
    atr15 = snapshot["atr"].get("M15") or 0.0
    win = engine.sessions._window_of(now - 60)
    out = {"now": time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(now)), "session": win[0] if win else "OFF",
           "session_min": (now - win[1]) // 60 if win else None, "price": _r(price),
           "atr": {tf: _r(snapshot["atr"][tf]) for tf in ("M15", "H1") if snapshot["atr"].get(tf)}}
    last4 = [b for b, _ in engine.hist.get("M15", [])[-4:]]
    if last4 and atr15:
        out["m15_range_vs_atr"] = _r((max(b.high for b in last4) - min(b.low for b in last4)) / atr15, 1)
    day = (snapshot.get("forming") or {}).get("day")
    if day:
        out["day"] = {"high": _r(day["high"]), "low": _r(day["low"])}
    trend = {}
    for tf in ("H4", "H1", "M15", "M5"):
        t = snapshot["trend"].get(tf)
        if not t:
            continue
        trend[tf] = {"dir": DIR.get(t["state"], t["state"]), "protected": _r(t.get("protected"))}
    out["trend"] = trend
    ranges = {}
    for tf, rg in (snapshot.get("ranges") or {}).items():
        width = rg["top"] - rg["bottom"] if rg else 0
        pos = (price - rg["bottom"]) / width if width > 0 else None
        if pos is not None and -0.5 <= pos <= 1.5:          # only ranges price is in or near
            ranges[tf] = {"top": _r(rg["top"]), "bottom": _r(rg["bottom"]), "pos": _r(pos, 2)}
    if ranges:
        out["ranges"] = ranges
    vw = {}
    for anchor, v in (snapshot.get("vwap") or {}).items():
        if v and v.get("sd"):
            vw[anchor] = {"at": _r(v["vwap"]), "sd_away": _r((price - v["vwap"]) / v["sd"], 1)}
    out["vwap"] = vw
    levels = []
    for lv in snapshot.get("htf_levels", []):
        if lv["id"] in exclude_levels:
            continue
        item = {"side": "R" if lv["side"] == "high" else "S", "price": _r(lv["price"]),
                "src": short_sources(lv["sources"]), "tests": lv["tests"],
                "atr_away": _r((lv["price"] - price) / atr15, 1) if atr15 else None}
        if (lv["side"] == "high") == (price > lv["price"]):
            item["beyond"] = True       # price is past it, not yet confirmed broken (M5 close)
        levels.append(item)
        if len(levels) >= max_levels:
            break
    out["levels"] = levels
    return out


def obstacles(side: str, entry: float, target: float, snapshot: dict, skip_price: float, atr: float,
              limit: int = 3) -> list[dict]:
    """Prices strictly between entry and target that may stop the move."""
    lo, hi = sorted((entry, target))
    found = []
    for anchor, v in (snapshot.get("vwap") or {}).items():
        if v and lo < v["vwap"] < hi:
            found.append((f"VWAP {anchor}", v["vwap"]))
    want = "low" if side == "sell" else "high"
    for tf in ("H1", "M15"):
        for sw in (snapshot.get("swings") or {}).get(tf, []):
            if sw["kind"] == want and lo < sw["price"] < hi:
                found.append((f"{tf} swing {want}", sw["price"]))
    for lv in snapshot.get("htf_levels", []):
        if lo < lv["price"] < hi and abs(lv["price"] - skip_price) > 1e-9:
            found.append(("level " + short_sources(lv["sources"]), lv["price"]))
    found.sort(key=lambda x: abs(x[1] - entry))
    out, used = [], []
    for what, p in found:
        if any(abs(p - q) < 0.1 * atr for q in used):       # one entry per price cluster
            continue
        used.append(p)
        out.append({"what": what, "price": _r(p), "atr_away": _r(abs(p - entry) / atr, 1)})
        if len(out) >= limit:
            break
    return out


def candidate(c, label: str, history: list[str], intent, snapshot: dict, avg_m1_volume: float | None) -> dict:
    lv, atr = c.level, c.atr
    d = (c.test_event or {}).get("data", {})
    ad = d.get("approach_detail") or {}
    view = {"id": label, "side": c.side,
            "level": {"price": _r(lv["price"]), "src": short_sources(lv["sources"]), "test": c.test_no,
                      "history": history or ["first test of this level"]},
            "approach": {"type": c.approach, "move_atr": _r(ad.get("net_atr"), 1), "eff": _r(ad.get("efficiency")),
                         "press": ad.get("pressing_bars")},
            "stretch_h1atr": _r(c.stretch, 1)}
    if c.rejection is not None:
        k = c.rejection["data"]["candle"]
        rng = (k["high"] - k["low"]) or 1e-9
        wick = (k["high"] - max(k["open"], k["close"])) if c.side == "sell" else (min(k["open"], k["close"]) - k["low"])
        view["rejection"] = {"poke_atr": c.rejection["data"]["pierce_atr"], "wick": _r(wick / rng),
                             "back_atr": _r(c.sgn * (lv["price"] - k["close"]) / atr),
                             "vol_x": _r(k["volume"] / avg_m1_volume, 1) if avg_m1_volume else None}
    if intent is not None:
        entry = (intent.entry_low + intent.entry_high) / 2 if intent.meta.get("rejection_candle") is None \
            else intent.meta["rejection_candle"]["close"]
        stop, target = intent.stop, intent.target
    else:
        entry, stop, target = lv["price"], c.plan_stop, c.target
    risk = abs(entry - stop) or 1e-9
    view["trade"] = {"entry": _r(entry), "stop": _r(stop), "target": _r(target), "target_src": c.target_source,
                     "stop_atr": _r(risk / atr), "target_atr": _r(abs(target - entry) / atr, 1),
                     "rr": _r(abs(target - entry) / risk, 1)}
    view["obstacles"] = obstacles(c.side, entry, target, snapshot, target, atr)
    return view
