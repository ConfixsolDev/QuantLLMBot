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
             bottoms (DT, TT, DB, TB); ``detail`` holds the long description
    levels   confirmed Asia / London / New York / day / week highs and lows
             (last 48 h) and the forming session / day range
    swings   confirmed swing highs/lows of this timeframe with HH/HL/LH/LL labels
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
    for e in events:
        k, d, etf = e["kind"], e["data"], e["tf"]
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
        elif k == "swing" and etf == tf:
            swings.append({"time": snap(d["time"]), "price": d["price"], "kind": d["kind"],
                           "label": d["label"] or ""})
    for a in alive:
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
    return {"lines": [ln for ln in lines if ln["t2"] >= snap(t_from)], "boxes": out_boxes,
            "markers": [m for m in markers if m["time"] >= snap(t_from)], "levels": levels,
            "swings": [s for s in swings if s["time"] >= snap(t_from)]}
