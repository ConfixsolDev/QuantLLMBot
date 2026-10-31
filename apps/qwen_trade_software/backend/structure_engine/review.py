"""Point-in-time review: charts of what the engine KNEW at sampled moments.

Verification step 4 of Module 1 (architecture doc, Part B §B4). The engine
replays real M1 history bar by bar. At sampled moments it freezes what it
knew — the snapshot — and draws it on a chart together with the candles that
came AFTER (shaded grey, for checking only; the engine never saw them).

A reviewer (Claude or a human) then marks each detection correct / wrong /
missed with a reason in ``review_template.csv``. The owner re-checks 10-20%
of those reviews (§B4 step 5).

    python -m structure_engine.review --m1 <folder or files> --out runs/review
    python -m structure_engine.review --m1 <...> --out runs/review --samples 24 --tf M15 --seed 7

Output: ``index.html`` (one chart per moment, self-contained SVG, opens in any
browser), ``review_template.csv`` (one row per detection to judge),
``moments.json`` (the frozen snapshots).

What is drawn
-------------
green / red boxes   active demand / supply zones at the moment (top-N ranked;
                    label = timeframe, rank, score, tests)
triangles           confirmed swing highs / lows of the chart timeframe
dashed lines        confirmed session / prior-day highs and lows (last 24 h)
BOS / CHoCH         line from the broken swing to the breaking candle
FVG / OB boxes      fair value gaps (light) and order blocks (outlined)
EQH / EQL           equal highs / lows (dotted teal)
x sweep / false brk / taken   what price did at a liquidity level (teal)
dashed box          a detected range
orange polyline     double/triple tops & bottoms: peaks -> neckline
                    (solid = confirmed before the moment, dotted = pending)
purple diamond      close spikes (H1/H4) up to the moment
grey area           the future after the moment (not known to the engine)

Standard library only.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import html
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from .bars import Bar
from .config import load_config
from .engine import StructureEngine

W, H, PAD_L, PAD_R, PAD_T, PAD_B = 1100, 430, 10, 70, 22, 26

LIQ_KINDS = ("liquidity_sweep", "false_break", "liquidity_taken", "sweep_failed")
DRAWN_KINDS = ("bos", "choch", "fvg_created", "order_block_created", "range_formed",
               "equal_highs", "equal_lows") + LIQ_KINDS
END_KINDS = ("fvg_filled", "fvg_expired", "order_block_broken", "order_block_expired",
             "range_break", "range_expired")
STRUCTURE_KINDS = ("pattern_confirmed", "pattern_pending", "close_spike", "swing") + DRAWN_KINDS + END_KINDS
ALL_LAYERS = ("swings", "levels", "zones", "patterns", "spikes", "trend", "liquidity", "eq", "fvg", "ob", "ranges")
DEFAULT_LAYERS = ("swings", "levels", "trend", "liquidity", "eq", "ob", "ranges")
LAYER_OF = {"bos": "trend", "choch": "trend", "fvg_created": "fvg", "order_block_created": "ob",
            "range_formed": "ranges", "equal_highs": "eq", "equal_lows": "eq",
            "liquidity_sweep": "liquidity", "false_break": "liquidity", "liquidity_taken": "liquidity",
            "sweep_failed": "liquidity"}


def _iso(t: int) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def collect(m1_bars, cfg, sample_times: set[int], tf: str, before: int, after: int,
            layers=DEFAULT_LAYERS) -> list[dict]:
    """Replay everything once; freeze snapshot + context at each sample time."""
    engine = StructureEngine(cfg)
    tf_bars: list[Bar] = []
    events_so_far: list = []
    moments, waiting = [], []
    for bar in m1_bars:
        evs = engine.push(bar)
        events_so_far.extend(e for e in evs if e.kind in STRUCTURE_KINDS)
        new = engine.closed_now.get(tf, [])
        tf_bars.extend(new)
        for m in waiting:                          # fill the "after" candles
            m["after"].extend(b.as_dict() for b in new)
        waiting = [m for m in waiting if len(m["after"]) < after]
        if engine.now in sample_times and len(tf_bars) >= before:
            snap = engine.snapshot(swings_per_tf=40, levels=30)
            start = tf_bars[-before].time
            m = {
                "t": engine.now,
                "tf": tf,
                "before": [b.as_dict() for b in tf_bars[-before:]],
                "after": [],
                "snapshot": snap,
                "patterns": [e.data for e in events_so_far
                             if e.kind == "pattern_confirmed" and e.data["peaks"][0]["time"] >= start],
                "spikes": [{"tf": e.tf, **e.data} for e in events_so_far
                           if e.kind == "close_spike" and e.data["close_time"] >= start],
                # structure events of the chart timeframe (liquidity: detect tf) in the window
                "structure": [{"kind": e.kind, "tf": e.tf, "available_at": e.available_at, **e.data}
                              for e in events_so_far
                              if e.available_at >= start and e.kind in DRAWN_KINDS
                              and LAYER_OF[e.kind] in layers
                              and (e.tf == tf or e.kind in LIQ_KINDS)],
                # when gaps / order blocks ended (filled, broken, expired) before the moment
                "ended": {e.data["id"]: e.available_at for e in events_so_far if e.kind in END_KINDS},
                "layers": list(layers),
            }
            moments.append(m)
            waiting.append(m)
        # keep memory bounded
        if len(tf_bars) > before * 4:
            del tf_bars[: len(tf_bars) - before * 2]
        if len(events_so_far) > 20000:
            del events_so_far[:10000]
    return moments


def _svg(m: dict) -> str:
    bars = m["before"] + m["after"]
    n = len(bars)
    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)
    span = hi - lo or 1.0
    lo, hi = lo - 0.05 * span, hi + 0.05 * span
    t0 = bars[0]["time"]
    step = (bars[1]["time"] - bars[0]["time"]) if n > 1 else 60
    cw = (W - PAD_L - PAD_R) / n

    times = [b["time"] for b in bars]

    def x(t: float) -> float:
        # Position by candle INDEX, not by elapsed time: the daily 21-22 UTC
        # break and weekends leave holes in time that are not drawn.
        i = bisect.bisect_right(times, t) - 1
        if i < 0:
            return PAD_L + (t - t0) / step * cw
        return PAD_L + (i + min(1.0, (t - times[i]) / step)) * cw

    def y(p: float) -> float:
        return PAD_T + (hi - p) / (hi - lo) * (H - PAD_T - PAD_B)

    out = [f'<svg viewBox="0 0 {W} {H}" width="100%" xmlns="http://www.w3.org/2000/svg" '
           f'style="background:var(--chart-bg);font:10px sans-serif">']
    # future shading
    xf = x(m["t"])
    out.append(f'<rect x="{xf:.1f}" y="0" width="{W - PAD_R - xf:.1f}" height="{H}" fill="var(--future)"/>')
    out.append(f'<text x="{xf + 4:.1f}" y="12" fill="var(--muted)">after (not known)</text>')
    layers = set(m.get("layers", ALL_LAYERS))
    # zones
    for rank, z in enumerate(m["snapshot"]["top_zones"] if "zones" in layers else [], 1):
        zz = z["zone"]
        if zz["high"] < lo or zz["low"] > hi:       # off-chart: note it at the edge
            col = "var(--demand)" if zz["side"] == "demand" else "var(--supply)"
            edge, arrow = (H - PAD_B - 4, "v") if zz["high"] < lo else (PAD_T + 10, "^")
            out.append(f'<text x="{W - PAD_R - 190 - 0 * rank:.1f}" y="{edge - 11 * (rank - 1) * (1 if arrow == "^" else -1):.1f}" '
                       f'fill="{col}">{arrow} {zz["tf"]} {zz["side"]} {zz["low"]:.0f}-{zz["high"]:.0f} #{rank} {z["score"]:.2f}</text>')
            continue
        x1 = max(PAD_L, x(zz["time"]))
        col = "var(--demand)" if zz["side"] == "demand" else "var(--supply)"
        out.append(f'<rect x="{x1:.1f}" y="{y(min(zz["high"], hi)):.1f}" width="{W - PAD_R - x1:.1f}" '
                   f'height="{max(1.5, y(max(zz["low"], lo)) - y(min(zz["high"], hi))):.1f}" fill="{col}" opacity="0.22"/>')
        out.append(f'<text x="{W - PAD_R + 3}" y="{y((zz["high"] + zz["low"]) / 2) + 3:.1f}" fill="{col}">'
                   f'{zz["tf"]} #{rank} {z["score"]:.2f} t{zz["tests"]}</text>')
    # session / day levels (last 24h before the moment)
    for lv in m["snapshot"]["levels"] if "levels" in layers else []:
        if lv["end"] < m["t"] - 86400:
            continue
        for side in ("high", "low"):
            p = lv[side]
            if lo <= p <= hi:
                out.append(f'<line x1="{max(PAD_L, x(lv["start"])):.1f}" x2="{W - PAD_R}" y1="{y(p):.1f}" y2="{y(p):.1f}" '
                           f'stroke="var(--level)" stroke-dasharray="4 3" stroke-width="0.8"/>')
                out.append(f'<text x="{max(PAD_L, x(lv["start"])) + 2:.1f}" y="{y(p) - 2:.1f}" fill="var(--level)">'
                           f'{lv["name"][:3]} {side[0].upper()}</text>')
    # ---- market structure (drawn under the candles)
    xf_now = xf
    for st in m.get("structure", []):
        k = st["kind"]
        if k in ("fvg_created", "order_block_created"):
            if st["high"] < lo or st["low"] > hi:
                continue
            col = "var(--demand)" if st["direction"] == "up" else "var(--supply)"
            x1 = max(PAD_L, x(st["time"]))
            end = m.get("ended", {}).get(st["id"])
            xe = x(end) if end and end <= m["t"] else xf_now
            # box runs until it was filled/broken, or until the moment if still alive
            op = "0.14" if k == "fvg_created" else "0.30"
            out.append(f'<rect x="{x1:.1f}" y="{y(st["high"]):.1f}" width="{max(2, xe - x1):.1f}" '
                       f'height="{max(1.2, y(st["low"]) - y(st["high"])):.1f}" fill="{col}" opacity="{op}"'
                       f'{" stroke=" + chr(34) + col + chr(34) if k == "order_block_created" else ""}/>')
            out.append(f'<text x="{x1 + 2:.1f}" y="{y(st["high"]) - 2:.1f}" fill="{col}" font-size="9">'
                       f'{"FVG" if k == "fvg_created" else "OB"}</text>')
        elif k == "range_formed":
            x1 = max(PAD_L, x(st["start"]))
            end = m.get("ended", {}).get(st["id"])
            xe = x(end) if end and end <= m["t"] else xf_now
            out.append(f'<rect x="{x1:.1f}" y="{y(st["top"]):.1f}" width="{max(2, xe - x1):.1f}" '
                       f'height="{y(st["bottom"]) - y(st["top"]):.1f}" fill="none" stroke="var(--muted)" '
                       f'stroke-dasharray="2 2"/>')
            out.append(f'<text x="{x1 + 2:.1f}" y="{y(st["bottom"]) + 10:.1f}" fill="var(--muted)">range</text>')
        elif k in ("bos", "choch"):
            if not lo <= st["level"] <= hi:
                continue
            col = "var(--text)" if k == "bos" else "var(--choch)"
            x1, x2 = max(PAD_L, x(st["level_time"])), x(st["break_time"]) + cw
            out.append(f'<line x1="{x1:.1f}" x2="{x2:.1f}" y1="{y(st["level"]):.1f}" y2="{y(st["level"]):.1f}" '
                       f'stroke="{col}" stroke-width="1.3"/>')
            out.append(f'<text x="{(x1 + x2) / 2 - 12:.1f}" y="{y(st["level"]) + (-3 if st["direction"] == "up" else 11):.1f}" '
                       f'fill="{col}" font-weight="600">{"BOS" if k == "bos" else "CHoCH"}</text>')
        elif k in ("equal_highs", "equal_lows"):
            p = st["pool"]["price"]
            if lo <= p <= hi:
                x1 = max(PAD_L, x(st["times"][0]))
                out.append(f'<line x1="{x1:.1f}" x2="{x(st["times"][-1]) + cw:.1f}" y1="{y(p):.1f}" y2="{y(p):.1f}" '
                           f'stroke="var(--liq)" stroke-width="2" stroke-dasharray="1 2"/>')
                out.append(f'<text x="{x1:.1f}" y="{y(p) + (-4 if k == "equal_highs" else 11):.1f}" fill="var(--liq)">'
                           f'{"EQH" if k == "equal_highs" else "EQL"}</text>')
        elif k in LIQ_KINDS:
            cx = x(st["candle"]["time"]) + cw / 2
            tag = {"liquidity_sweep": "sweep", "false_break": "false brk", "liquidity_taken": "taken",
                   "sweep_failed": "sweep failed"}[k]
            for lv in st["levels"][:1]:
                if not lo <= lv["price"] <= hi:
                    continue
                out.append(f'<line x1="{max(PAD_L, x(lv["time"])):.1f}" x2="{cx + 6:.1f}" y1="{y(lv["price"]):.1f}" '
                           f'y2="{y(lv["price"]):.1f}" stroke="var(--liq)" stroke-width="0.9"/>')
                yy = y(st["extreme"]) + (-6 if st["side"] == "high" else 14)
                out.append(f'<text x="{cx - 14:.1f}" y="{yy:.1f}" fill="var(--liq)" font-size="9">x {tag}</text>')
    # candles
    for i, b in enumerate(bars):
        cx = PAD_L + (i + 0.5) * cw
        col = "var(--up)" if b["close"] >= b["open"] else "var(--down)"
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(b["high"]):.1f}" y2="{y(b["low"]):.1f}" stroke="{col}"/>')
        top, bot = y(max(b["open"], b["close"])), y(min(b["open"], b["close"]))
        out.append(f'<rect x="{cx - cw * 0.35:.1f}" y="{top:.1f}" width="{cw * 0.7:.1f}" height="{max(0.8, bot - top):.1f}" fill="{col}"/>')
    # swings of the chart timeframe
    for s in m["snapshot"]["swings"].get(m["tf"], []) if "swings" in layers else []:
        if s["time"] < t0:
            continue
        cx = x(s["time"]) + cw / 2
        if s["kind"] == "high":
            py = y(s["price"]) - 4
            out.append(f'<path d="M{cx - 3:.1f},{py - 5:.1f} L{cx + 3:.1f},{py - 5:.1f} L{cx:.1f},{py:.1f} Z" fill="var(--swing)"/>')
            out.append(f'<text x="{cx - 6:.1f}" y="{py - 7:.1f}" fill="var(--swing)">{s["label"] or ""}</text>')
        else:
            py = y(s["price"]) + 4
            out.append(f'<path d="M{cx - 3:.1f},{py + 5:.1f} L{cx + 3:.1f},{py + 5:.1f} L{cx:.1f},{py:.1f} Z" fill="var(--swing)"/>')
            out.append(f'<text x="{cx - 6:.1f}" y="{py + 15:.1f}" fill="var(--swing)">{s["label"] or ""}</text>')
    # patterns (confirmed in window) and pending at the moment
    pats = ([(p, "") for p in m["patterns"]] + [(p, ' stroke-dasharray="3 3"')
                                               for p in m["snapshot"]["pending_patterns"]]) if "patterns" in layers else []
    for pat, dash in pats:
        pts = [(x(pk["time"]) + cw / 2, y(pk["price"])) for pk in pat["peaks"]]
        if not pts or pts[0][0] < PAD_L:
            continue
        out.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" '
                   f'stroke="var(--pattern)" stroke-width="1.6"{dash}/>')
        out.append(f'<line x1="{pts[0][0]:.1f}" x2="{min(W - PAD_R, pts[-1][0] + 40):.1f}" y1="{y(pat["neckline"]):.1f}" '
                   f'y2="{y(pat["neckline"]):.1f}" stroke="var(--pattern)"{dash}/>')
        out.append(f'<text x="{pts[-1][0] + 4:.1f}" y="{y(pat["neckline"]) - 3:.1f}" fill="var(--pattern)">{pat["kind"]}</text>')
    # close spikes
    for sp in m["spikes"] if "spikes" in layers else []:
        cx, cy = x(sp["close_time"]), y(sp["extreme"])
        out.append(f'<path d="M{cx:.1f},{cy - 6:.1f} L{cx + 5:.1f},{cy:.1f} L{cx:.1f},{cy + 6:.1f} L{cx - 5:.1f},{cy:.1f} Z" '
                   f'fill="var(--spike)"/>')
        out.append(f'<text x="{cx + 6:.1f}" y="{cy:.1f}" fill="var(--spike)">{sp["tf"]} spike {sp["move"]:.1f}</text>')
    # price axis
    for k in range(6):
        p = lo + (hi - lo) * k / 5
        out.append(f'<text x="{W - PAD_R + 3}" y="{y(p):.1f}" fill="var(--muted)" font-size="9">{p:.1f}</text>')
    out.append(f'<text x="{PAD_L}" y="{H - 8}" fill="var(--muted)">{_iso(t0)}</text>')
    out.append(f'<text x="{xf - 60:.1f}" y="{H - 8}" fill="var(--text)">moment {_iso(m["t"])}</text>')
    out.append("</svg>")
    return "".join(out)


CSS = """
:root{--bg:#fafaf8;--text:#1d1d1b;--muted:#77756f;--chart-bg:#ffffff;--future:#ececea;--up:#2f7d4f;
--down:#b8433a;--demand:#2f9e5c;--supply:#d0473c;--level:#4a6fb3;--swing:#5b5b5b;--pattern:#d98200;
--spike:#8b46c6;--line:#e2e1dc;--choch:#c2410c;--liq:#0e7490}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#161615;--text:#ecebe7;--muted:#9a988f;
--chart-bg:#1e1e1c;--future:#2a2a27;--up:#4fb57b;--down:#e0675d;--demand:#4fc27f;--supply:#ef6a5e;
--level:#7c9be0;--swing:#c9c7c0;--pattern:#f2a640;--spike:#b67ef0;--line:#33332f;--choch:#fb8c4a;--liq:#38bdd8}}
body{background:var(--bg);color:var(--text);font:14px/1.45 system-ui,sans-serif;margin:0;padding:16px;max-width:1180px;margin:auto}
h2{font-size:15px;margin:28px 0 6px}table{border-collapse:collapse;font-size:12px;margin:6px 0 4px;width:100%}
td,th{border-bottom:1px solid var(--line);padding:3px 6px;text-align:left}p.small{color:var(--muted);font-size:12px}
"""


def write_html(moments: list[dict], out: Path, cfg) -> None:
    rows = []
    parts = [f"<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Structure review</title><style>{CSS}</style>"
             f"<h1 style='font-size:18px'>Structure engine — point-in-time review</h1>"
             f"<p class='small'>config {cfg['config_id']} · hash {cfg.config_hash} · {len(moments)} moments. "
             f"Grey area = candles after the moment, for checking only. Judge each row in review_template.csv.</p>"]
    for i, m in enumerate(moments, 1):
        parts.append(f"<h2>{i}. {_iso(m['t'])} — {m['tf']} chart</h2>{_svg(m)}")
        tbl = ["<table><tr><th>id</th><th>detection</th><th>details</th></tr>"]
        for rank, z in enumerate(m["snapshot"]["top_zones"], 1):
            zz = z["zone"]
            d = f"{zz['tf']} {zz['side']} {zz['low']:.2f}-{zz['high']:.2f} score {z['score']} tests {zz['tests']} status {zz['status']}"
            tbl.append(f"<tr><td>{zz['id']}</td><td>zone #{rank}</td><td>{html.escape(d)}</td></tr>")
            rows.append([i, _iso(m["t"]), zz["id"], f"zone #{rank}", d, "", ""])
        for p in m["patterns"] + m["snapshot"]["pending_patterns"]:
            d = f"{p['kind']} {p['status']} peaks {[round(x['price'], 2) for x in p['peaks']]} neck {p['neckline']:.2f} tags {p['tags']}"
            tbl.append(f"<tr><td>{p['id']}</td><td>pattern</td><td>{html.escape(d)}</td></tr>")
            rows.append([i, _iso(m["t"]), p["id"], "pattern", d, "", ""])
        for st in m.get("structure", []):
            if st["kind"] in ("bos", "choch"):
                d = f"{st['tf']} {st['kind'].upper()} {st['direction']} level {st['level']:.2f} displacement={st['displacement']}"
            elif st["kind"] in LIQ_KINDS:
                d = f"{st['kind']} {st['side']} levels {[(lv['kind'], round(lv['price'], 2)) for lv in st['levels']]}"
            elif st["kind"] in ("fvg_created", "order_block_created"):
                d = f"{st['tf']} {st['kind'][:-8]} {st['direction']} {st['low']:.2f}-{st['high']:.2f}"
            elif st["kind"] == "range_formed":
                d = f"{st['tf']} range {st['bottom']:.2f}-{st['top']:.2f}"
            else:
                d = f"{st['kind']} {st.get('prices')}"
            sid = st.get("id") or st.get("pool", {}).get("id") or f"{st['kind']}@{st['available_at']}"
            tbl.append(f"<tr><td>{html.escape(str(sid))}</td><td>{st['kind']}</td><td>{html.escape(d)}</td></tr>")
            rows.append([i, _iso(m["t"]), sid, st["kind"], d, "", ""])
        for sp in m["spikes"]:
            d = (f"{sp['tf']} {sp['direction']} {sp['move']:.2f} ({sp['move_atr']} ATR) held={sp['held']} "
                 f"swept_prev={sp['swept_prev']} trend={sp['htf_trend']} session={sp['session']}")
            tbl.append(f"<tr><td>{sp['spike_id']}</td><td>close spike</td><td>{html.escape(d)}</td></tr>")
            rows.append([i, _iso(m["t"]), sp["spike_id"], "close spike", d, "", ""])
        tbl.append("</table>")
        parts.append("".join(tbl))
    (out / "index.html").write_text("".join(parts), encoding="utf-8")
    with (out / "review_template.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["moment", "time", "id", "detection", "details", "verdict (correct/wrong/missed)", "reason"])
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="+", required=True)
    ap.add_argument("--out", default="runs/review")
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--tf", default="M15", help="chart timeframe")
    ap.add_argument("--before", type=int, default=120, help="candles shown before the moment")
    ap.add_argument("--after", type=int, default=24, help="candles shown after the moment")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--config", default=None)
    ap.add_argument("--layers", default=",".join(DEFAULT_LAYERS),
                    help=f"comma list to draw (review one structure at a time): {','.join(ALL_LAYERS)}")
    args = ap.parse_args()
    layers = tuple(x.strip() for x in args.layers.split(",") if x.strip())
    unknown = set(layers) - set(ALL_LAYERS)
    if unknown:
        raise SystemExit(f"unknown layers {sorted(unknown)}; choose from {ALL_LAYERS}")
    from .feeds import RecordedFeed
    cfg = load_config(args.config)
    bars = list(RecordedFeed(args.m1))
    minutes = cfg.tf_minutes[args.tf]
    # candidate moments: chart-candle closes with enough history before and after
    lo = bars[0].time + args.before * minutes * 60 * 2
    hi = bars[-1].time - args.after * minutes * 60 * 2
    candidates = [b.close_time for b in bars if lo <= b.time <= hi and b.close_time % (minutes * 60) == 0]
    picks = set(random.Random(args.seed).sample(candidates, min(args.samples, len(candidates))))
    moments = collect(bars, cfg, picks, args.tf, args.before, args.after, layers)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "moments.json").write_text(json.dumps(moments), encoding="utf-8")
    write_html(moments, out, cfg)
    print(f"{len(moments)} moments -> {out / 'index.html'}")


if __name__ == "__main__":
    main()
