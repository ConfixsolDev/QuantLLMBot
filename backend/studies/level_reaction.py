"""Level-reaction study: do higher-timeframe levels behave the way the strategy says?

Run (from backend/)::

    python -m studies.level_reaction --m1 <folder or CSV files of M1 bars>
    python -m studies.level_reaction --db --from 2016-01-01        # bars from the database
    python -m studies.level_reaction --m1 data --set BREAK_TF=5 --set CLEAN=1.0

Research only: nothing here is used by the engine or the application. It is
deliberately written separately from structure_engine/levels.py (its own
touch / hold / break tracking), so the two are an independent cross-check.
Results and how to read them: V3 document, Part B (B3c).

Event study on M1 bars. For every higher-timeframe level (H1/H4 swing, prior
day / session high-low, $50 round number) we follow each TEST (touch) and ask:
did the level HOLD (price moved 1 x ATR15 away before an M1 close 0.3 x ATR15
beyond it) or BREAK?

Features at the touch are causal (known at that minute); outcomes use the future.
Control (Osler 2000): random levels placed near each real level, same side of
price, tracked identically. A real level is only "a level" if it beats random.
"""
from __future__ import annotations

import bisect
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))     # backend/
from structure_engine.atr import WilderATR  # noqa: E402
from structure_engine.config import load_config  # noqa: E402
from structure_engine.engine import StructureEngine  # noqa: E402
from structure_engine.feeds import RecordedFeed  # noqa: E402


TOUCH_TOL = 0.10      # x ATR15: high within this of the level = touch
RESET = 1.0           # x ATR15: price must leave this far before a new test counts
HOLD_DIST = 1.0       # x ATR15 away = held
BREAK_BUF = 0.30      # x ATR15 M1 close beyond = broken
HORIZON = 240         # M1 bars to resolve
MAX_AGE = 5 * 86400   # level lifetime


def load(source):
    """Run the engine once over the bars; keep what the study needs."""
    cfg = load_config()
    eng = StructureEngine(cfg)
    bars, events, atr15, atrh1, trend = [], [], [], [], []
    a15, ah1 = WilderATR(14), WilderATR(14)
    cur15 = curh1 = None
    for b in source:
        evs = eng.push(b)
        for c in eng.closed_now.get("M15", []):
            cur15 = a15.update(c)
        for c in eng.closed_now.get("H1", []):
            curh1 = ah1.update(c)
        bars.append(b)
        atr15.append(cur15)
        atrh1.append(curh1)
        trend.append({tf: eng.trend[tf].state if hasattr(eng, "trend") and tf in eng.trend else None
                      for tf in ("M15", "H1", "H4")})
        events.extend(e.as_dict() for e in evs
                      if e.kind in ("swing", "session_level", "prior_day_level", "pattern_confirmed",
                                    "bos", "choch") or e.kind.startswith("level_"))
    return bars, events, atr15, atrh1, trend


def levels_from(events, bars):
    """(available_at, price, side, source) for every HTF level."""
    lv = []
    for e in events:
        d = e["data"]
        if e["kind"] == "swing" and e["tf"] in ("H1", "H4"):
            lv.append((e["available_at"], d["price"], "high" if d["kind"] == "high" else "low", f"{e['tf']} swing"))
        elif e["kind"] in ("session_level", "prior_day_level"):
            src = "day" if e["kind"] == "prior_day_level" or d["name"].upper() == "DAY" else "session"
            if d["name"].upper() == "WEEK":
                src = "week"
            lv.append((e["available_at"], d["high"], "high", src))
            lv.append((e["available_at"], d["low"], "low", src))
    # $50 round numbers: active all the time, re-created each day near price
    seen = set()
    for i in range(0, len(bars), 1440):
        p = bars[i].close
        for r in range(int(p // 50 - 2) * 50, int(p // 50 + 3) * 50 + 1, 50):
            key = (r, bars[i].time // 86400)
            if key not in seen:
                seen.add(key)
                lv.append((bars[i].time, float(r), "both", "round50"))
    return lv


def track(level, side, start_i, bars, atr15, times, label_extra=None):
    """Follow one level from start_i; return list of tests (dicts)."""
    tests = []
    n = len(bars)
    i = start_i
    end_t = bars[start_i].time + MAX_AGE
    # side "high": resistance, approached from below. Price must be below it at start.
    p0 = bars[start_i].close
    if side == "both":
        side = "high" if level > p0 else "low"
    sgn = 1 if side == "high" else -1
    if sgn * (level - p0) <= 0:
        return tests
    away = True              # price is "away" (reset satisfied) at birth
    test_no = 0
    while i < n and bars[i].time < end_t:
        b = bars[i]
        a = atr15[i]
        if a is None or a <= 0:
            i += 1
            continue
        ext = b.high if sgn > 0 else b.low
        dist = sgn * (level - ext)                       # >0 below resistance
        if dist > RESET * a:
            away = True
        if away and dist <= TOUCH_TOL * a:
            test_no += 1
            away = False
            res = resolve(level, sgn, i, bars, atr15)
            tests.append({"i": i, "test_no": test_no, "outcome": res[0], "bars": res[1], "atr": a, "sgn": sgn})
            if res[0] == "break":
                return tests                              # level is gone after a real break
        # a close well beyond without a counted touch (gap) also kills it
        if sgn * (b.close - level) > max(BREAK_BUF, 1.0) * a:
            return tests
        i += 1
    return tests


CLEAN = 0.0           # control levels must be this far (x ATR15) from any real level
BREAK_TF = 1          # judge breaks on M1 (1) or M5 (5) closes


def resolve(level, sgn, i, bars, atr15, horizon=HORIZON):
    a = atr15[i]
    for j in range(i, min(len(bars), i + horizon)):
        b = bars[j]
        closes = BREAK_TF == 1 or (b.time + 60) % (BREAK_TF * 60) == 0
        if closes and sgn * (b.close - level) > BREAK_BUF * a:
            return "break", j - i
        if sgn * (level - (b.low if sgn > 0 else b.high)) >= HOLD_DIST * a:
            return "hold", j - i
    return "open", horizon


def resolve2(p0, level, sgn, i, bars, atr15, horizon=HORIZON):
    """From price p0 (already away from the level): hold = another HOLD_DIST x ATR
    away from p0 before a close beyond the level; break otherwise."""
    a = atr15[i]
    for j in range(i + 1, min(len(bars), i + horizon)):
        b = bars[j]
        closes = BREAK_TF == 1 or (b.time + 60) % (BREAK_TF * 60) == 0
        if closes and sgn * (b.close - level) > BREAK_BUF * a:
            return "break"
        if sgn * (p0 - (b.low if sgn > 0 else b.high)) >= HOLD_DIST * a:
            return "hold"
    return "open"


# ------------------------------------------------------------------ features at touch
def approach(i, level, sgn, bars, a, look=20):
    """push / squeeze / drift, from the last `look` M1 bars before the touch."""
    if i < 2 * look:
        return "na"
    w = bars[i - look:i]
    prev = bars[i - 2 * look:i - look]
    net = sgn * (w[-1].close - w[0].open)
    path = sum(abs(x.close - x.open) for x in w) or 1e-9
    eff = net / path
    rng = max(x.high for x in w) - min(x.low for x in w)
    rng_prev = max(x.high for x in prev) - min(x.low for x in prev)
    # pressing: bars whose extreme came within 0.5 ATR of the level
    press = sum(1 for x in w if sgn * (level - (x.high if sgn > 0 else x.low)) <= 0.5 * a)
    # rising lows into resistance (falling highs into support): slope of opposite extremes
    opp = [(x.low if sgn > 0 else -x.high) for x in w]
    k = len(opp)
    mx = (k - 1) / 2
    slope = sum((t - mx) * (v - sum(opp) / k) for t, v in enumerate(opp)) / sum((t - mx) ** 2 for t in range(k))
    if press >= 6 and rng < 0.8 * rng_prev and slope * k > 0.3 * a:
        return "squeeze"
    if net >= 1.5 * a and eff >= 0.35:
        return "push"
    return "drift"


def stretch(i, sgn, bars, atrh1, look=24 * 60):
    """How far the move into the level has run: from the opposite extreme of the last 24 h, in H1 ATR."""
    a = atrh1[i]
    if a is None or i < 60:
        return None
    w = bars[max(0, i - look):i + 1]
    base = min(x.low for x in w) if sgn > 0 else max(x.high for x in w)
    ext = bars[i].high if sgn > 0 else bars[i].low
    return sgn * (ext - base) / a


def m1_rejection(i, level, sgn, bars, atr15, within=10):
    """First M1 rejection after the touch: poke beyond and close back inside."""
    a = atr15[i]
    for j in range(i, min(len(bars), i + within)):
        b = bars[j]
        beyond = sgn * ((b.high if sgn > 0 else b.low) - level)
        if sgn * (b.close - level) > BREAK_BUF * a:
            return None, j
        if beyond >= 0.05 * a and sgn * (level - b.close) > 0:
            return "poke_reclaim", j
    return None, None


# ------------------------------------------------------------------ stats
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, c - h, c + h


def rate(rows):
    res = [r for r in rows if r["outcome"] in ("hold", "break")]
    k = sum(r["outcome"] == "hold" for r in res)
    return k, len(res)


def fmt(name, rows, ctrl=None):
    k, n = rate(rows)
    p, lo, hi = wilson(k, n)
    s = f"  {name:<34} n={n:5d}  hold {p*100:5.1f}%  [{lo*100:4.1f}-{hi*100:4.1f}]"
    if ctrl is not None:
        kc, nc = rate(ctrl)
        pc = kc / nc if nc else float("nan")
        s += f"   random {pc*100:5.1f}% (n={nc})  edge {(p-pc)*100:+5.1f} pts"
    return s


def _source(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--m1", nargs="*", help="M1 CSV files or folders")
    ap.add_argument("--db", action="store_true", help="read M1 bars from the database (QUANTLLM_DB_DSN)")
    ap.add_argument("--from", dest="start", default=None, help="first day (YYYY-MM-DD) with --db")
    ap.add_argument("--set", dest="params", action="append", default=[],
                    help="NAME=value override: HOLD_DIST BREAK_BUF BREAK_TF CLEAN TOUCH_TOL RESET")
    a = ap.parse_args(argv)
    for arg in a.params:
        k, v = arg.split("=")
        if k not in ("HOLD_DIST", "BREAK_BUF", "BREAK_TF", "CLEAN", "TOUCH_TOL", "RESET"):
            raise SystemExit(f"unknown parameter {k}")
        globals()[k] = int(v) if k == "BREAK_TF" else float(v)
    if a.db:
        import calendar
        import time as _t
        from quantllm import mt5_connection
        from quantllm.database import Database
        from quantllm.settings import load_settings
        s = load_settings()
        start = calendar.timegm(_t.strptime(a.start, "%Y-%m-%d")) if a.start else None
        return Database(s.db_dsn, s.db_schema).iter_candles(mt5_connection.settings().broker_symbol, start)
    if not a.m1:
        raise SystemExit("give --m1 <files/folders> or --db")
    return RecordedFeed(a.m1)


def main(argv=None):
    source = _source(sys.argv[1:] if argv is None else argv)
    print(f"params HOLD_DIST={HOLD_DIST} BREAK_BUF={BREAK_BUF} BREAK_TF=M{BREAK_TF} CLEAN={CLEAN}")
    bars, events, atr15, atrh1, trend = load(source)
    times = [b.time for b in bars]
    lv = levels_from(events, bars)
    rng = random.Random(7)
    real, ctrl = [], []
    pats = [e for e in events if e["kind"] == "pattern_confirmed"]
    for (t, price, side, src) in lv:
        i = bisect.bisect_left(times, t)
        if i >= len(bars) - 10:
            continue
        for tst in track(price, side, i, bars, atr15, times):
            tst.update(src=src, level=price, side=side)
            real.append(tst)
        a = atr15[i]
        if a is None:
            continue
        known = [q for (tq, q, _s, _src) in lv if t - MAX_AGE <= tq <= t]
        tries = 0
        made = 0
        while made < 4 and tries < 40:              # controls: nearby, but >= CLEAN x ATR from every known level
            tries += 1
            off = rng.uniform(0.5, 3.0) * a * rng.choice((-1, 1))
            if any(abs(price + off - q) < CLEAN * a for q in known):
                continue
            made += 1
            for tst in track(price + off, side, i, bars, atr15, times):
                tst.update(src=src, level=price + off, side=side)
                ctrl.append(tst)
    for rows in (real, ctrl):
        for r in rows:
            sgn = r["sgn"]
            r["approach"] = approach(r["i"], r["level"], sgn, bars, r["atr"])
            r["stretch"] = stretch(r["i"], sgn, bars, atrh1)
            tr = trend[r["i"]].get("H1")
            r["htf"] = "none" if tr in (None, "none") else ("with" if (tr == "down") == (sgn > 0) else "against")
            rej, j = m1_rejection(r["i"], r["level"], sgn, bars, atr15)
            r["rej"] = rej
            if rej:
                o, nb = resolve(r["level"], sgn, j, bars, atr15)
                r["rej_outcome"] = o
                # works right away: within 3 bars after the rejection candle, price moves 0.5 ATR15 away
                fast = any(sgn * (r["level"] - (bars[k].low if sgn > 0 else bars[k].high)) >= 0.5 * r["atr"]
                           for k in range(j + 1, min(len(bars), j + 4)))
                r["fast"] = fast
            # M1 double top/bottom near the level, confirmed within 60 bars of the touch
            r["m1_dt"] = False
            for e in pats:
                d = e["data"]
                if not (bars[r["i"]].time <= e["available_at"] <= bars[r["i"]].time + 3600):
                    continue
                top = d["kind"].endswith("top")
                if top != (sgn > 0):
                    continue
                pk = max(p["price"] for p in d["peaks"]) if top else min(p["price"] for p in d["peaks"])
                if abs(pk - r["level"]) <= 0.5 * r["atr"]:
                    j = bisect.bisect_left(times, e["available_at"] - 60)
                    if sgn * (bars[j].close - r["level"]) > BREAK_BUF * r["atr"]:
                        continue
                    r["m1_dt"] = True
                    r["dt_outcome"] = resolve2(bars[j].close, r["level"], sgn, j, bars, atr15)
                    break
    print(f"bars {len(bars)}  ({bars[0].time} .. {bars[-1].time})  levels {len(lv)}")
    print(f"tests: real {len(real)}  random {len(ctrl)}")
    print("\n1) Are HTF levels real? (Osler control: random nearby levels, same rules)")
    print(fmt("all levels, all tests", real, ctrl))
    for src in ("H1 swing", "H4 swing", "day", "session", "round50"):
        print(fmt(src, [r for r in real if r["src"] == src], [r for r in ctrl if r["src"] == src]))
    print("\n2) Test number (MTF: 1st/2nd best, 3rd+ breaks more)")
    for tn, lab in ((1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th+")):
        sel = (lambda r: r["test_no"] >= 4) if tn == 4 else (lambda r, tn=tn: r["test_no"] == tn)
        print(fmt(lab, [r for r in real if sel(r)], [r for r in ctrl if sel(r)]))
    print("\n3) Approach (MTF: don't fade a squeeze, fade a push)")
    for a in ("push", "drift", "squeeze"):
        print(fmt(a, [r for r in real if r["approach"] == a], [r for r in ctrl if r["approach"] == a]))
    print("\n4) H1 trend vs the fade direction")
    for h in ("with", "none", "against"):
        print(fmt(f"H1 trend {h} the fade", [r for r in real if r["htf"] == h], [r for r in ctrl if r["htf"] == h]))
    print("\n5) Stretch: move into the level over the last 24 h, in H1 ATR")
    for lo, hi in ((0, 2), (2, 4), (4, 6), (6, 99)):
        f = lambda r: r["stretch"] is not None and lo <= r["stretch"] < hi  # noqa: E731
        print(fmt(f"{lo}-{hi} H1 ATR", [r for r in real if f(r)], [r for r in ctrl if f(r)]))
    print("\n6) M1 confirmation (outcome measured from the rejection candle)")
    def rj(rows, cond):
        return [{"outcome": r["rej_outcome"]} for r in rows if r.get("rej") and cond(r)]
    print(fmt("poke-and-reclaim (any)", rj(real, lambda r: True), rj(ctrl, lambda r: True)))
    print(fmt("  ...and moved away in 3 bars", rj(real, lambda r: r["fast"]), rj(ctrl, lambda r: r["fast"])))
    print(fmt("  ...stalled (not in 3 bars)", rj(real, lambda r: not r["fast"]), rj(ctrl, lambda r: not r["fast"])))
    print(fmt("  ...on 1st/2nd test", rj(real, lambda r: r["test_no"] <= 2), rj(ctrl, lambda r: r["test_no"] <= 2)))
    print(fmt("  ...after a squeeze", rj(real, lambda r: r["approach"] == "squeeze"), rj(ctrl, lambda r: r["approach"] == "squeeze")))
    print(fmt("touch WITHOUT M1 rejection", [r for r in real if not r.get("rej")], [r for r in ctrl if not r.get("rej")]))
    dt = lambda rows, c: [{"outcome": r["dt_outcome"]} for r in rows if r["m1_dt"] and c(r)]  # noqa: E731
    print(fmt("M1 double top/bottom (from confirm)", dt(real, lambda r: True), dt(ctrl, lambda r: True)))
    print(fmt("  ...with poke-and-reclaim first", dt(real, lambda r: r.get("rej")), dt(ctrl, lambda r: r.get("rej"))))
    print("\n7) Stability by month (all tests)")
    import time as _t
    for m in sorted({_t.strftime("%Y-%m", _t.gmtime(bars[r["i"]].time)) for r in real}):
        f = lambda r: _t.strftime("%Y-%m", _t.gmtime(bars[r["i"]].time)) == m  # noqa: E731
        print(fmt(m, [r for r in real if f(r)], [r for r in ctrl if f(r)]))
    engine_report(events)
    return real, ctrl


def engine_report(events):
    """The same questions asked of the ENGINE's own level events (levels.py)."""
    tests = {}
    for e in events:
        d = e["data"]
        if not e["kind"].startswith("level_") or e["kind"] == "level_created":
            continue
        key = (d["level"]["id"], d.get("test_no") or d.get("during_test"))
        if e["kind"] == "level_test":
            tests[key] = {"no": d["test_no"], "approach": d["approach"], "n": len(d["level"]["sources"]),
                          "outcome": None, "rej": False, "ft": None}
        elif key in tests:
            t = tests[key]
            if e["kind"] == "level_held":
                t["outcome"] = "hold"
            elif e["kind"] == "level_broken":
                t["outcome"] = "break"
            elif e["kind"] == "level_rejection":
                t["rej"] = True
            elif e["kind"] == "level_followthrough":
                t["ft"] = d["result"]
    T = list(tests.values())
    print("\n8) The engine's own level events (levels.py) — same questions, no control")
    for name, f in (("all tests", lambda t: True), ("test 1", lambda t: t["no"] == 1),
                    ("test 2", lambda t: t["no"] == 2), ("test 3+", lambda t: t["no"] >= 3),
                    ("approach push", lambda t: t["approach"] == "push"),
                    ("approach drift", lambda t: t["approach"] == "drift"),
                    ("approach squeeze", lambda t: t["approach"] == "squeeze"),
                    ("confluence (2+ sources)", lambda t: t["n"] >= 2),
                    ("M1 rejection", lambda t: t["rej"]), ("no M1 rejection", lambda t: not t["rej"]),
                    ("rejection, moved in 3 bars", lambda t: t["ft"] == "moved"),
                    ("rejection, stalled", lambda t: t["ft"] == "stalled")):
        print(fmt(name, [t for t in T if f(t)]))


if __name__ == "__main__":
    main()
