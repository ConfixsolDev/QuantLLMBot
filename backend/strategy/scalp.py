"""Strategy kind ``m1_probe_failure``: M1 scalps at mapped gold locations.

The owner's system is a SCALPER (the old system: ~18 fills a day, trades held
3 minutes on median, stops ~$3.5). Structure comes from H4, H1, M30 and M15;
timing from M1. M5 is not used anywhere ("gold does not trade well on M5").

A CANDIDATE is one completed M1 "probe and failure" (the old doctrine's
execution trigger): an M1 candle went beyond a mapped location and closed
back. The structure engine (config v2, M1 closes) reports four kinds::

    level_rejection    an M15/M30/H1/H4 swing or session/day/week level
    liquidity_sweep    a liquidity pool (swing, equal highs/lows, session, range edge)
    false_break        a pool closed beyond, then closed back within 5 M1 bars
    vwap_band_reject   the day / week / session VWAP 2 sd band

Every trigger of one side in the same M1 bar is ONE candidate (its ``at``
list names them all). The model is asked at once; an approval becomes a
TradeIntent with exact prices (code, never the model)::

    reference  = close of the probe candle
    stop       = beyond the candle's extreme by stop_buffer_atr x ATR(M1), and at
                 least min_stop_atr x ATR(M1) from the reference (1.2 = the
                 owner's minimum for gold noise; ~$2-5); wider than
                 max_stop_atr x ATR(M1) -> no candidate
    target     = reference +- target_r x risk (1.0 R)
    entry      = reference +- entry_slack_atr x ATR(M1), never at the stop
    valid for  = entry_window_bars M1 bars; after max_hold_bars the trade is
                 closed at market (a scalp that has not worked in 30 minutes
                 is not the trade any more)

The five CHECKS (code-measured facts the doctrine weighs; study 2026-11-01,
May-Jul 2026, take-all, 1 R / 30 min, $0.25 spread)::

    confluence          >= 2 probe-failures on the same side within confluence_minutes
    wick                rejection wick >= half of the candle's range
    close_against_probe the candle closed in the trade's direction (buy: close > open)
    volume              >= 2x the average volume of the 20 M1 bars before
    stretched           price ran >= 4 ATR(M1) into the location in the last 15 M1 bars

    passed  0-1: -0.09 R/trade   2: -0.06 R   3+: +0.10 R (53.5 % won, n=739, every month positive)

``min_checks`` drops candidates below it before the model is asked (2:
0-1 lost in every month and would only cost model time).
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections import deque
from dataclasses import dataclass, field

from trading.intent import TradeIntent

from . import outlook
from .runner import Ev, Step, StrategyRunner, _price_of, age

CHECKS = ("confluence", "wick", "close_against_probe", "volume", "stretched")
VOLUME_X = 2.0
STRETCH_ATR = 4.0
STRETCH_BARS = 15
VOLUME_BARS = 20
WICK_MIN = 0.5
THESIS_TFS = ("H4", "H1", "M30", "M15")


@dataclass
class ScalpCandidate:
    key: str                         # id of the first trigger event (stable across restarts)
    side: str                        # "buy" | "sell"
    candle: dict                     # the M1 probe-and-failure candle
    created_at: int
    expires_at: int
    atr: float                       # ATR(M1) at the trigger close (the stop's ruler)
    atr15: float | None
    session: str
    at: list = field(default_factory=list)       # the mapped locations it failed at
    facts: dict = field(default_factory=dict)
    checks: dict = field(default_factory=dict)
    status: str = "new"              # new -> asked -> approved / refused -> triggered | expired
    decision_id: str | None = None
    opened_at: int | None = None

    @property
    def dir(self) -> int:
        return 1 if self.side == "buy" else -1

    @property
    def passed(self) -> int:
        return sum(1 for k in CHECKS if self.checks.get(k))

    @property
    def rejection(self) -> dict:                  # runner/template compatibility
        return {"data": {"candle": self.candle}}

    @property
    def level(self) -> dict:
        """The main location as a level dict (a level rejection when there is one)."""
        lv = next((a for a in self.at if a.get("level_id")), self.at[0])
        return {"id": lv.get("level_id") or self.key, "price": lv["price"], "sources": [lv["src"]]}

    @property
    def test_no(self) -> int:
        return next((a["test"] for a in self.at if a.get("level_id")), 0)


# ---------------------------------------------------------------------- triggers
def trigger_of(e: dict, rules: dict) -> tuple[str, dict] | None:
    """An engine event -> (side, location) when it is a probe-and-failure this strategy trades."""
    k, d = e["kind"], e["data"]
    if k not in rules["triggers"] or e["tf"] != "M1":
        return None
    if k == "level_rejection":
        lv = d["level"]
        return ("sell" if lv["side"] == "high" else "buy",
                {"what": "level rejection", "price": round(lv["price"], 2),
                 "src": outlook.short_sources(lv["sources"]), "test": d["test_no"], "level_id": lv["id"]})
    if k in ("liquidity_sweep", "false_break"):
        pools = d["levels"]
        price = (max if d["side"] == "high" else min)(p["price"] for p in pools)
        src = "+".join(sorted({(p["kind"] if p["source_tf"] in ("day", "week", "session")
                                else f"{p['source_tf']} {p['kind']}").replace("_", " ") for p in pools}))
        return ("sell" if d["side"] == "high" else "buy",
                {"what": "liquidity sweep" if k == "liquidity_sweep" else "false break",
                 "price": round(price, 2), "src": src})
    if k == "vwap_band_reject":
        if d["anchor"] not in rules["vwap_anchors"]:
            return None
        return ("sell" if d["side"] == "upper" else "buy",
                {"what": "VWAP band reject", "price": round(d["level"], 2),
                 "src": f"VWAP {d['anchor']} {'+' if d['side'] == 'upper' else '-'}{d['band']:g}sd"})
    return None


def stop_of(rules: dict, side: str, candle: dict, atr: float) -> tuple[float, float]:
    """(stop, risk) for a probe candle: beyond its extreme, at least min_stop_atr x ATR(M1)."""
    d = 1 if side == "buy" else -1
    ref = float(candle["close"])
    ext = float(candle["low"]) if d > 0 else float(candle["high"])
    stop = ext - d * rules["stop_buffer_atr"] * atr
    if d * (ref - stop) < rules["min_stop_atr"] * atr:
        stop = ref - d * rules["min_stop_atr"] * atr
    return stop, d * (ref - stop)


def trigger(strategy, c: ScalpCandidate, now: int) -> tuple[TradeIntent | None, str]:
    """An approved candidate -> a TradeIntent with exact prices."""
    r = strategy.rules
    d, atr = c.dir, c.atr
    ref = float(c.candle["close"])
    stop, risk = stop_of(r, c.side, c.candle, atr)
    if risk > r["max_stop_atr"] * atr:
        return None, f"stop {risk / atr:.1f} ATR(M1) > max {r['max_stop_atr']}"
    target = ref + d * r["target_r"] * risk
    lo, hi = ref - r["entry_slack_atr"] * atr, ref + r["entry_slack_atr"] * atr
    if d > 0:
        lo = max(lo, stop + 0.05 * atr)
    else:
        hi = min(hi, stop - 0.05 * atr)
    iid = hashlib.sha1(f"{strategy.ref}|{c.key}|{c.candle['time']}".encode()).hexdigest()[:16]
    return TradeIntent(
        intent_id=iid, strategy_ref=strategy.ref, decision_id=c.decision_id or "", candidate_id=c.key,
        side=c.side, entry_low=round(lo, 3), entry_high=round(hi, 3), stop=round(stop, 3),
        target=round(target, 3), created_at=c.created_at,
        expires_at=c.candle["time"] + 60 * (1 + r["entry_window_bars"]), atr=atr,
        meta={"level": c.at[0]["price"], "sources": [a["src"] for a in c.at], "test_no": c.test_no,
              "rejection_candle": c.candle, "rr": r["target_r"], "target_source": f"{r['target_r']:g}R",
              "stop_source": "atr" if abs(risk - r["min_stop_atr"] * atr) < 1e-9 else "candle",
              "checks": dict(c.checks), "checks_passed": c.passed,
              "max_hold_bars": r["max_hold_bars"]}), "ok"


# ---------------------------------------------------------------------- runner
class ScalpRunner(StrategyRunner):
    """StrategyRunner for ``m1_probe_failure``: asks at every probe-and-failure, closes on the time cap."""

    def __init__(self, strategy, session_of, m1_bars, history: int = 600) -> None:
        super().__init__(strategy, session_of, history)
        self.m1_bars = m1_bars                     # () -> recent closed M1 bars, the newest last
        self.triggers: deque[tuple[int, str]] = deque(maxlen=200)
        self.closing: set[str] = set()

    def observe(self, events: list, snapshot_fn, now: int) -> Step:
        r = self.s.rules
        step, new = Step(), {}
        for ev in events:
            e = ev if isinstance(ev, dict) else ev.as_dict()
            k, d = e["kind"], e["data"]
            if k in outlook.EVIDENCE_KINDS:
                txt = outlook.brief(e)
                if txt:
                    lid = d["level"]["id"] if k.startswith("level_") else None
                    self.recent.append(Ev(e["id"], k, e["tf"], e["available_at"], txt, _price_of(e), lid))
            self._history(e)
            t = trigger_of(e, r)
            if t is None:
                continue
            side, where = t
            self.triggers.append((e["available_at"], side))
            if side in new:
                if all(a["price"] != where["price"] or a["what"] != where["what"] for a in new[side][1]):
                    new[side][1].append(where)
            else:
                new[side] = (e, [where])
        if new:
            snap = snapshot_fn()
            for side, (e, where) in new.items():
                c, why = self._candidate(side, e, where, snap, now)
                if c is None:
                    step.skipped.append((e["id"], why))
                    continue
                self.active[c.key] = c
                step.asks.append(c)
        for key, c in list(self.active.items()):
            if c.status in ("new", "asked", "approved", "refused") and now >= c.expires_at:
                step.ended.append(self.active.pop(key))
        for key, c in list(self.traded.items()):
            if c.opened_at is not None and key not in self.closing \
                    and now - c.opened_at >= r["max_hold_bars"] * 60:
                self.closing.add(key)
                step.closes.append((key, f"time cap: {r['max_hold_bars']} M1 bars"))
        return step

    def _candidate(self, side, e, where, snap, now) -> tuple[ScalpCandidate | None, str]:
        r = self.s.rules
        c_ = e["data"]["candle"]
        sess = self.session_of(c_["time"]) or "OFF"
        if side not in r["sides"]:
            return None, f"side {side} not in this strategy"
        if sess not in r["sessions"]:
            return None, f"session {sess} not traded"
        atr = (snap.get("atr") or {}).get(r["atr_timeframe"])
        if not atr:
            return None, f"no ATR({r['atr_timeframe']}) yet"
        stop, risk = stop_of(r, side, c_, atr)
        if risk > r["max_stop_atr"] * atr:
            return None, f"probe candle too big: stop {risk / atr:.1f} ATR > {r['max_stop_atr']}"
        c = ScalpCandidate(e["id"], side, c_, e["available_at"], c_["time"] + 60 * (1 + r["entry_window_bars"]),
                           float(atr), (snap.get("atr") or {}).get("M15"), sess, list(where))
        c.facts, c.checks = self._checks(c, now)
        if c.passed < r["min_checks"]:
            return None, f"{c.passed} checks passed < min_checks {r['min_checks']}"
        return c, "ok"

    def _checks(self, c: ScalpCandidate, now: int) -> tuple[dict, dict]:
        r, k, d = self.s.rules, c.candle, c.dir
        bars = list(self.m1_bars())
        if bars and bars[-1].time == k["time"]:
            prior = bars[:-1]
        else:
            prior = [b for b in bars if b.time < k["time"]]
        rng = (k["high"] - k["low"]) or 1e-9
        wick = ((min(k["open"], k["close"]) - k["low"]) if d > 0 else (k["high"] - max(k["open"], k["close"]))) / rng
        vols = [b.volume for b in prior[-VOLUME_BARS:]]
        avg = statistics.mean(vols) if vols else 0
        vol_x = k["volume"] / avg if avg > 0 else None
        into = None
        if len(prior) >= STRETCH_BARS:
            into = -d * (k["close"] - prior[-STRETCH_BARS].open) / c.atr
        since = now - 60 * r["confluence_minutes"]
        n = sum(1 for t, s in self.triggers if s == c.side and since <= t <= now)
        poke = max((d * (a["price"] - (k["low"] if d > 0 else k["high"])) for a in c.at), default=0.0)
        facts = {"triggers_in_window": n, "wick": round(wick, 2), "close_vs_open": "with trade"
                 if d * (k["close"] - k["open"]) > 0 else "against trade",
                 "vol_x": None if vol_x is None else round(vol_x, 1),
                 "into_15m_atr": None if into is None else round(into, 1),
                 "range_atr": round(rng / c.atr, 1), "poke_atr": round(poke / c.atr, 2)}
        checks = {"confluence": n >= 2, "wick": wick >= WICK_MIN, "close_against_probe": d * (k["close"] - k["open"]) > 0,
                  "volume": vol_x is not None and vol_x >= VOLUME_X,
                  "stretched": into is not None and into >= STRETCH_ATR}
        return facts, checks

    def _fire(self, c, now: int, step: Step) -> None:
        intent, why = trigger(self.s, c, now)
        if intent is None or now > intent.expires_at:
            c.status = "expired"
            step.skipped.append((c.key, why if intent is None else "entry window passed"))
            return
        c.status, c.opened_at = "triggered", now
        self.traded[c.key] = c
        self.active.pop(c.key, None)
        step.intents.append(intent)

    def trade_closed(self, key: str) -> None:
        self.traded.pop(key, None)
        self.closing.discard(key)


# ---------------------------------------------------------------------- prompt
def thesis(snapshot: dict) -> dict:
    """Code's direction read, H4 -> M15 (old doctrine: 'establish one directional bias first')."""
    tr = {tf: (snapshot["trend"].get(tf) or {}).get("state", "none") for tf in THESIS_TFS}
    h4, h1 = tr.get("H4"), tr.get("H1")
    if h4 == h1 and h1 in ("up", "down"):
        bias = "buy" if h1 == "up" else "sell"
        note = f"H4 and H1 {h1}"
    elif h1 in ("up", "down"):
        bias = "buy" if h1 == "up" else "sell"
        note = f"H1 {h1}, H4 {h4} (weaker)"
    else:
        bias, note = "none", "H1 has no trend"
    m15 = tr.get("M15")
    if bias != "none" and m15 in ("up", "down") and (m15 == "up") != (bias == "buy"):
        note += f"; M15 {m15} = pullback against it"
    return {"bias": bias, "why": note}


def market(engine, snap: dict, price: float, now: int, rules: dict, exclude: set, max_levels: int) -> dict:
    win = engine.sessions._window_of(now - 60)
    atr = snap["atr"]
    out = {"now": time.strftime("%Y-%m-%d %H:%MZ", time.gmtime(now)),
           "session": win[0] if win else "OFF", "session_min": (now - win[1]) // 60 if win else None,
           "price": round(price, 2),
           "atr": {tf: round(atr[tf], 2) for tf in ("M1", "M15", "H1") if atr.get(tf)},
           "thesis": thesis(snap)}
    day = (snap.get("forming") or {}).get("day")
    if day:
        out["day"] = {"high": round(day["high"], 2), "low": round(day["low"], 2)}
    out["trend"] = {tf: {"dir": (snap["trend"][tf] or {}).get("state"),
                         "protected": outlook._r((snap["trend"][tf] or {}).get("protected"))}
                    for tf in THESIS_TFS if snap["trend"].get(tf)}
    vw = {}
    for anchor, v in (snap.get("vwap") or {}).items():
        if v and v.get("sd"):
            vw[anchor] = {"at": round(v["vwap"], 2), "sd_away": round((price - v["vwap"]) / v["sd"], 1)}
    out["vwap"] = vw
    levels = []
    for lv in snap.get("htf_levels", []):
        if lv["id"] in exclude:
            continue
        levels.append({"side": "R" if lv["side"] == "high" else "S", "price": round(lv["price"], 2),
                       "src": outlook.short_sources(lv["sources"]), "tests": lv["tests"],
                       "usd_away": round(lv["price"] - price, 2)})
        if len(levels) >= max_levels:
            break
    out["levels"] = levels
    return out


def candidate_view(c: ScalpCandidate, label: str, runner, intent: TradeIntent, snap: dict, now: int) -> dict:
    at = []
    for a in c.at:
        item = {k: v for k, v in a.items() if k != "level_id"}
        if a.get("level_id"):
            item["history"] = runner.history(a["level_id"], a["test"], now) or ["first test"]
        at.append(item)
    ref = float(c.candle["close"])
    risk = abs(ref - intent.stop)
    view = {"id": label, "side": c.side, "at": at, "candle": c.facts,
            "checks": {**{k: bool(c.checks.get(k)) for k in CHECKS}, "passed": c.passed},
            "trade": {"entry": round(ref, 2), "stop": round(intent.stop, 2), "target": round(intent.target, 2),
                      "risk_usd": round(risk, 2), "stop_atr": round(risk / c.atr, 1),
                      "rr": intent.meta["rr"], "max_hold_min": intent.meta["max_hold_bars"]}}
    obs = outlook.obstacles(c.side, ref, intent.target, snap, intent.target, 1.0)
    view["obstacles"] = [{"what": o["what"], "price": o["price"], "usd_away": o["atr_away"]} for o in obs]
    return view


CITE_FIELDS = ("at", "candle", "checks", "trade", "obstacles")


def build_prompt(strategy, engine, runner, asks: list, now: int):
    from . import template
    snap = engine.snapshot()
    price = engine._last_close
    views, cmap, previews = [], {}, {}
    for c in sorted(asks, key=lambda x: -x.passed):          # best-checked first
        if len(cmap) >= strategy.rules["max_candidates"]:
            break
        intent, why = trigger(strategy, c, now)
        if intent is None:
            continue
        label = f"C{len(cmap) + 1}"
        cmap[label], previews[label] = c.key, intent
        views.append(candidate_view(c, label, runner, intent, snap, now))
    if not cmap:
        raise template.NothingToAsk("no candidate left to offer")
    exclude = {a.get("level_id") for c in asks for a in c.at}
    mk = market(engine, snap, price, now, strategy.rules, exclude, strategy.prompt["max_levels"])
    ev = runner.evidence(asks, price, snap["atr"].get("M15") or 1.0, now, strategy.prompt["max_evidence"])
    system = template.system_message(strategy)
    trimmed = {"evidence": 0, "levels": 0}
    while True:
        user = json.dumps({"market": mk, "candidates": views,
                           "evidence": {f"E{i + 1}": txt for i, (_, txt) in enumerate(ev)}},
                          separators=(",", ":"), ensure_ascii=False)
        size = len(system.encode()) + len(user.encode())
        if size <= strategy.prompt["max_bytes"]:
            break
        if len(ev) > 3:
            ev.pop()
            trimmed["evidence"] += 1
        elif len(mk.get("levels", [])) > 1:
            mk["levels"] = mk["levels"][:-1]
            trimmed["levels"] += 1
        else:
            raise template.PromptTooLarge(f"prompt is {size} bytes > {strategy.prompt['max_bytes']} after trimming")
    emap = {f"E{i + 1}": eid for i, (eid, _) in enumerate(ev)}
    sha = hashlib.sha1((system + "\n" + user).encode()).hexdigest()[:16]
    return template.Prompt(system, user, size, sha, cmap, emap, trimmed, previews, CITE_FIELDS)


__all__ = ["ScalpCandidate", "ScalpRunner", "trigger", "trigger_of", "build_prompt", "thesis", "CHECKS", "age"]
