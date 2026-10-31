"""Turn engine events into chart drawings for one timeframe and time window.

The website draws exactly what this module returns, so the chart can never
show something the engine did not say. Every time is snapped to the OPEN time
of the chart-timeframe candle that contains it (H4 on the New York grid), so
the browser only has to look up candles.

Output (all prices raw, all times UTC epoch seconds)::

    lines    BOS / CHoCH: horizontal line from the broken swing to the breaking candle
    boxes    FVG, order block, supply/demand zone, range: low..high from start
             until it ended (filled / broken / expired) or until now if alive
    markers  liquidity sweep / failed sweep / false break / accepted break
             (SW, SW✗, FB, TK), close spikes, confirmed double/triple tops &
             bottoms (DT, TT, DB, TB), VWAP band rejects on M1-M30 (VD / VW / VS
             = day / week / session); ``detail`` holds the long description
    curves   (added by the caller) VWAP + bands per anchor at each candle
    levels   confirmed Asia / London / New York / day / week highs and lows
             (last 48 h) and the forming session / day range
    swings   confirmed swing highs/lows of this timeframe with HH/HL/LH/LL labels
    hlevels  higher-timeframe levels (levels.py): price, sources, number of tests,
             from when known until broken (or now); markers R1, R2 ... = M1
             rejection on test n, then R1+ (moved away in 3 bars) / R1- (stalled);
             LDT / LDB ... = M1 double/triple top/bottom formed at the level
"""

from __future__ import annotations

LIQ = {"liquidity_sweep": "sweep", "sweep_failed": "sweep failed",
       "false_break": "false break", "liquidity_taken": "taken"}
# Short chart labels: the chart stays readable; the side panel has the details.
SHORT = {"liquidity_sweep": "SW", "sweep_failed": "SW✗", "false_break": "FB", "liquidity_taken": "TK"}
PATTERN_SHORT = {"double_top": "DT", "triple_top": "TT", "double_bottom": "DB", "triple_bottom": "TB"}
BOX_START = {"fvg_created": "fvg", "order_block_created": "ob", "zone_created": "zone", "range_formed": "range"}
BOX_END = {"fvg_filled", "fvg_expired", "order_block_broken", "order_block_expired",
           "zone_broken", "zone_expired", "range_break", "range_expired"}
BOX_UPDATE = {"fvg_mitigated", "order_block_tested", "zone_tested"}
_ALL = {"M5", "M15", "M30", "H1", "H4", "session", "day", "week"}
POOLS_FOR = {"M1": _ALL, "M5": _ALL, "M15": _ALL, "M30": {"M30", "H1", "H4", "session", "day", "week"},
             "H1": {"H1", "H4", "day", "week"}, "H4": {"H4", "day", "week"}}


def build(events: list[dict], tf: str, t_from: int, now: int, snap, snapshot: dict,
          alive: list[dict] = ()) -> dict:
    """``events``: event dicts (Event.as_dict) in emission order; ``snap(t)``
    maps a time to the containing chart-candle open time. ``alive``: zones /
    order blocks / FVGs still active in the engine, so boxes created before the
    in-memory event window are still drawn."""
    lines, markers, swings = [], [], []
    boxes: dict[str, dict] = {}
    hl: dict[str, dict] = {}
    rej: dict[tuple, dict] = {}
    for e in events:
        k, d, etf = e["kind"], e["data"], e["tf"]
        if k.startswith("level_") and k not in ("level_rejection", "level_pattern", "level_followthrough"):
            lv = d if k == "level_created" else d["level"]
            h = hl.setdefault(lv["id"], {"id": lv["id"], "price": lv["price"], "side": lv["side"],
                                         "sources": lv["sources"], "t1": lv["created_at"], "t2": None, "tests": 0})
            if k == "level_test":
                h["tests"] = d["test_no"]
            elif k == "level_broken":
                h["t2"] = e["available_at"]
            continue
        if e["available_at"] < t_from and k not in BOX_START and k not in BOX_END and k not in BOX_UPDATE:
            continue
        if k in ("bos", "choch") and etf == tf:
            lines.append({"kind": k, "direction": d["direction"], "price": d["level"],
                          "t1": snap(max(d["level_time"], t_from)), "t2": snap(d["break_time"]),
                          "label": "BOS" if k == "bos" else "CHoCH"})
        elif k in BOX_START and (etf == tf or k == "zone_created"):
            key = d["id"]
            if k == "range_formed":
                lo, hi, start, side = d["bottom"], d["top"], d["start"], "range"
            else:
                lo, hi, start = d["low"], d["high"], d["time"]
                side = d.get("direction") or d.get("side")
            boxes[key] = {"kind": BOX_START[k], "tf": etf, "side": side, "low": lo, "high": hi,
                          "t1": start, "t2": None, "status": d.get("status", "OPEN"), "tests": 0}
        elif k in BOX_UPDATE and d["id"] in boxes:
            boxes[d["id"]]["status"] = d["status"]
            boxes[d["id"]]["tests"] = d.get("tests", 1)
        elif k in BOX_END and d["id"] in boxes:
            boxes[d["id"]]["t2"] = e["available_at"]
            boxes[d["id"]]["status"] = d.get("status") or k.split("_")[-1].upper()
        elif k in LIQ:
            # On higher charts only liquidity that matters at that scale:
            # pools from that timeframe or above, and session/day/week levels.
            levels = [lv for lv in d["levels"] if lv["source_tf"] in POOLS_FOR.get(tf, POOLS_FOR["M1"])]
            for lv in levels[:1]:
                markers.append({"kind": k, "time": snap(d["candle"]["time"]), "price": d["extreme"],
                                "position": "above" if d["side"] == "high" else "below",
                                "text": SHORT[k], "detail": f"{LIQ[k]} {lv['kind'].replace('_', ' ')}",
                                "level": lv["price"], "level_t1": snap(max(lv["time"], t_from))})
        elif k == "close_spike":
            markers.append({"kind": "close_spike", "time": snap(d["close_time"] - 60), "price": d["extreme"],
                            "position": "above" if d["direction"] == "up" else "below",
                            "text": f"{etf} spike", "detail": f"{etf} close spike {d['move']:.1f}"})
        elif k == "pattern_confirmed":
            markers.append({"kind": "pattern", "time": snap(d["peaks"][-1]["time"]),
                            "price": d["peaks"][-1]["price"],
                            "position": "above" if d["kind"].endswith("top") else "below",
                            "text": PATTERN_SHORT.get(d["kind"], d["kind"]), "detail": d["kind"].replace("_", " ")})
        elif k == "vwap_band_reject" and tf in ("M1", "M5", "M15", "M30"):
            c = d["candle"]
            markers.append({"kind": "vwap_band_reject", "time": snap(c["time"]),
                            "price": c["high"] if d["side"] == "upper" else c["low"],
                            "position": "above" if d["side"] == "upper" else "below",
                            "text": f"V{d['anchor'][0].upper()}", "detail":
                            f"VWAP {d['anchor']} {d['band']}σ {d['side']} band reject at {d['level']:.2f}"})
        elif k == "level_rejection":
            c, lv = d["candle"], d["level"]
            m = {"kind": "level_rejection", "time": snap(c["time"]),
                 "price": c["high"] if lv["side"] == "high" else c["low"],
                 "position": "above" if lv["side"] == "high" else "below", "text": f"R{d['test_no']}",
                 "detail": f"M1 rejection of {' + '.join(lv['sources'])} {lv['price']:.2f} (test {d['test_no']})"}
            markers.append(m)
            rej[(lv["id"], d["test_no"])] = m
        elif k == "level_followthrough" and (d["level"]["id"], d["test_no"]) in rej:
            m = rej[(d["level"]["id"], d["test_no"])]
            m["text"] += "+" if d["result"] == "moved" else "-"
            m["detail"] += f", {d['result']} ({d['move_atr']} ATR in 3 bars)"
        elif k == "level_pattern":
            lv = d["level"]
            pk = d["peaks"][-1]
            markers.append({"kind": "level_pattern", "time": snap(pk["time"]), "price": pk["price"],
                            "position": "above" if lv["side"] == "high" else "below",
                            "text": "L" + PATTERN_SHORT.get(d["pattern"], d["pattern"]),
                            "detail": f"{d['pattern'].replace('_', ' ')} at {' + '.join(lv['sources'])} {lv['price']:.2f}"})
        elif k == "swing" and etf == tf:
            swings.append({"time": snap(d["time"]), "price": d["price"], "kind": d["kind"],
                           "label": d["label"] or ""})
    for a in alive:
        if a["kind"] == "hlevel":
            if a["id"] not in hl:
                hl[a["id"]] = {k2: a[k2] for k2 in ("id", "price", "side", "sources", "tests")}
                hl[a["id"]].update(t1=a["created_at"], t2=None)
            continue
        if a["id"] not in boxes and (a["tf"] == tf or a["kind"] == "zone"):
            boxes[a["id"]] = {"kind": a["kind"], "tf": a["tf"], "side": a["side"], "low": a["low"],
                              "high": a["high"], "t1": a["time"], "t2": None, "status": a["status"],
                              "tests": a.get("tests", 0)}
    out_boxes = []
    for b in boxes.values():
        end = b["t2"] if b["t2"] is not None else now
        if end < t_from:
            continue                                     # finished before the window
        out_boxes.append({**b, "t1": snap(max(b["t1"], t_from)), "t2": snap(min(end, now)),
                          "alive": b["t2"] is None})
    levels = []
    for lv in snapshot.get("levels", []):
        if lv["end"] >= now - 48 * 3600:
            for side in ("high", "low"):
                levels.append({"name": lv["name"], "side": side, "price": lv[side],
                               "t1": snap(max(lv["start"], t_from)), "confirmed": True})
    for key in ("session", "day"):
        fm = snapshot.get("forming", {}).get(key)
        if fm:
            for side in ("high", "low"):
                levels.append({"name": fm["name"], "side": side, "price": fm[side],
                               "t1": snap(max(fm["start"], t_from)), "confirmed": False})
    hlevels = []
    for h in hl.values():
        end = h["t2"] if h["t2"] is not None else now
        if end < t_from or h["t1"] > now:
            continue
        src = " + ".join(x.replace(" swing ", " sw ") for x in h["sources"])
        hlevels.append({**h, "t1": snap(max(h["t1"], t_from)), "t2": snap(min(end, now)), "alive": h["t2"] is None,
                        "label": src + (f" ×{h['tests']}" if h["tests"] else "")})
    return {"lines": [ln for ln in lines if ln["t2"] >= snap(t_from)], "boxes": out_boxes, "hlevels": hlevels,
            "markers": [m for m in markers if m["time"] >= snap(t_from)], "levels": levels,
            "swings": [s for s in swings if s["time"] >= snap(t_from)]}
