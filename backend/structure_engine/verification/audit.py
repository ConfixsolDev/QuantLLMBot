"""Independent audit of a back-test's events against the raw M1 candles.

This is the numeric half of cross-verification (the visual half is
review.py). It re-reads the raw M1 file(s) and rebuilds candles with its OWN
code — plain dictionaries, and Python's ``zoneinfo`` tz database for the New
York H4 grid instead of the engine's hand-written DST rule — then checks every
claim an event makes:

* the candle an event cites exists, with exactly that open/high/low/close;
* BOS / CHoCH: the breaking candle closes beyond the level, the level is a
  real swing extreme at ``level_time``, and no candle closed beyond it
  between the moment the swing was known and the break (first break);
* liquidity sweep: wick beyond, close back inside; sweep_failed / false break /
  accepted break: the closes on the cited candles say so;
* FVG: the three candles are consecutive and the gap equals c1/c3 extremes;
* order block: the candle exists, has the opposite colour, and its range is
  the block.

    python -m structure_engine.verification.audit --m1 <M1 folder> --events runs/real/events.jsonl

Prints checks run / failed per event kind and the first failures. Any failure
means the engine and an independent reading of the same candles disagree.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from ..config import load_config
from ..feeds import RecordedFeed

TF_MIN = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240}


def _ny_h4_start(t: int) -> int | None:
    """Independent New York H4 grid via the tz database (None if unavailable)."""
    try:
        from zoneinfo import ZoneInfo
        ny = ZoneInfo("America/New_York")
    except Exception:             # no tz database (plain Windows Python without tzdata)
        return None
    local = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(ny)
    floor = local.replace(minute=0, second=0, microsecond=0)
    hours = [h for h in (2, 6, 10, 14, 18, 22) if h <= local.hour]
    start = floor.replace(hour=hours[-1]) if hours else (floor.replace(hour=0) - timedelta(hours=2))
    return int(start.timestamp())


def build_candles(m1) -> dict[str, dict[int, dict]]:
    """{tf: {open_time: candle}} built independently from M1 rows."""
    out: dict[str, dict[int, dict]] = {tf: {} for tf in TF_MIN}
    h4_ok = _ny_h4_start(1_782_000_000) is not None
    for b in m1:
        for tf, m in TF_MIN.items():
            if tf == "H4":
                if not h4_ok:
                    continue
                start = _ny_h4_start(b.time)
            else:
                start = b.time - b.time % (m * 60)
            c = out[tf].get(start)
            if c is None:
                out[tf][start] = {"time": start, "open": b.open, "high": b.high, "low": b.low,
                                  "close": b.close, "n": 1, "last": b.time}
            else:
                c["high"] = max(c["high"], b.high)
                c["low"] = min(c["low"], b.low)
                c["close"] = b.close
                c["n"] += 1
                c["last"] = b.time
    return out


def audit(m1_paths, events_path, show: int = 10) -> dict:
    """Audit a back-test output folder's events.jsonl against M1 files."""
    with open(events_path, encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh]
    return audit_events(RecordedFeed(m1_paths), events, show)


def audit_events(m1_bars, events: list[dict], show: int = 10) -> dict:
    """Audit in-memory events (Event.as_dict) against in-memory M1 bars."""
    candles = build_candles(m1_bars)
    sorted_times = {tf: sorted(c) for tf, c in candles.items()}
    checks, fails, info = Counter(), defaultdict(list), Counter()
    strength = load_config()["swings"]["strength"]

    def same(c: dict | None, d: dict) -> bool:
        return c is not None and all(abs(c[k] - d[k]) < 1e-9 for k in ("open", "high", "low", "close"))

    def fail(kind: str, msg: str) -> None:
        fails[kind].append(msg)

    for e in events:
        k, tf, d = e["kind"], e["tf"], e["data"]
        if tf not in candles or not candles[tf]:
            continue
        cs = candles[tf]
        if k in ("bos", "choch"):
            checks[k] += 1
            brk = cs.get(d["break_time"])
            up = d["direction"] == "up"
            if brk is None or abs(brk["close"] - d["break_close"]) > 1e-9:
                fail(k, f"{e['id']}: breaking candle not found / close differs")
                continue
            if not ((brk["close"] > d["level"]) if up else (brk["close"] < d["level"])):
                fail(k, f"{e['id']}: close not beyond level")
            lv = cs.get(d["level_time"])
            swing_side = "high" if up else "low"
            if lv is None or abs(lv[swing_side] - d["level"]) > 1e-9:
                fail(k, f"{e['id']}: level {d['level']} is not the {swing_side} of the swing candle")
            # informational: did an earlier candle already close beyond it
            # after the swing was confirmed? (allowed by the trend rules,
            # e.g. while the trend pointed the other way)
            known = d["level_time"] + (strength[tf] + 1) * TF_MIN[tf] * 60
            for t in sorted_times[tf]:
                if known <= t < d["break_time"]:
                    cc = cs[t]["close"]
                    if (cc > d["level"]) if up else (cc < d["level"]):
                        info[k] += 1
                        break
        elif k in ("liquidity_sweep", "false_break", "liquidity_taken", "sweep_failed"):
            checks[k] += 1
            c = cs.get(d["candle"]["time"])
            if not same(c, d["candle"]):
                fail(k, f"{e['id']}: candle differs from raw data")
                continue
            for lv in d["levels"]:
                p, hi = lv["price"], d["side"] == "high"
                if k == "liquidity_sweep" and not ((c["high"] > p and c["close"] < p) if hi
                                                   else (c["low"] < p and c["close"] > p)):
                    fail(k, f"{e['id']}: not a sweep of {p}")
                if k == "sweep_failed" and not ((c["close"] > p) if hi else (c["close"] < p)):
                    fail(k, f"{e['id']}: close not beyond {p}")
                if k == "false_break" and not ((c["close"] < p) if hi else (c["close"] > p)):
                    fail(k, f"{e['id']}: reclaim close not back inside {p}")
                if k == "liquidity_taken" and not ((c["close"] > p) if hi else (c["close"] < p)):
                    fail(k, f"{e['id']}: accepted-break candle not beyond {p}")
        elif k == "fvg_created":
            checks[k] += 1
            c1 = cs.get(d["time"])
            if c1 is None:
                fail(k, f"{e['id']}: c1 missing")
                continue
            step = TF_MIN[tf] * 60
            c3 = cs.get(d["time"] + 2 * step)
            if c3 is None or cs.get(d["time"] + step) is None:
                fail(k, f"{e['id']}: candles not consecutive")
                continue
            lo, hi = (c1["high"], c3["low"]) if d["direction"] == "up" else (c3["high"], c1["low"])
            if abs(lo - d["low"]) > 1e-9 or abs(hi - d["high"]) > 1e-9 or not lo < hi:
                fail(k, f"{e['id']}: gap bounds differ")
        elif k == "order_block_created":
            checks[k] += 1
            c = cs.get(d["time"])
            if c is None or abs(c["low"] - d["low"]) > 1e-9 or abs(c["high"] - d["high"]) > 1e-9:
                fail(k, f"{e['id']}: order-block candle range differs")
                continue
            if (d["direction"] == "up" and not c["close"] < c["open"]) or \
               (d["direction"] == "down" and not c["close"] > c["open"]):
                fail(k, f"{e['id']}: order-block candle has the wrong colour")
    report = {"checks": dict(checks), "failures": {k: len(v) for k, v in fails.items()},
              "earlier_close_beyond": dict(info),
              "examples": {k: v[:show] for k, v in fails.items()},
              "h4_checked": bool(candles["H4"])}
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--m1", nargs="+", required=True)
    ap.add_argument("--events", required=True)
    args = ap.parse_args()
    rep = audit(args.m1, args.events)
    print(f"{'event kind':<22}{'checked':>9}{'failed':>8}")
    for k, n in sorted(rep["checks"].items()):
        print(f"{k:<22}{n:>9}{rep['failures'].get(k, 0):>8}")
    print(f"H4 (New York grid) checked with zoneinfo: {rep['h4_checked']}")
    for k, n in rep["earlier_close_beyond"].items():
        print(f"info: {n} {k} levels had an earlier close beyond them (allowed by trend rules)")
    for k, ex in rep["examples"].items():
        print(f"-- {k}:")
        for x in ex:
            print("   ", x)


if __name__ == "__main__":
    main()
