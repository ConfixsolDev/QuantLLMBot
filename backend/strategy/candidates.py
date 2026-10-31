"""Deterministic trade candidates for the strategy kind ``htf_level_rejection``.

Two moments, both decided by code from structure-engine events:

1. PLAN — a ``level_test`` event (price reached a higher-timeframe level)
   becomes a Candidate when the strategy rules allow it. Its prices are
   estimates for Qwen to judge::

       sell at resistance L (buy at support is the mirror image)
       plan stop   = L + plan_stop_allowance_atr x ATR(M15)
       target      = the nearest SUPPORT level below L by >= min_target_atr x ATR
                     (fallback: fallback_target_r x the planned risk)
       R:R         = (L - target) / (plan stop - L)  must be >= min_rr

   Qwen is asked: take this plan, or wait?

2. TRIGGER — a ``level_rejection`` on the same level and test (M1 poked
   beyond and closed back inside) turns an APPROVED candidate into a
   TradeIntent with exact prices::

       reference   = close of the rejection candle
       stop        = rejection candle extreme + stop_buffer_atr x ATR
                     (at least min_stop_atr x ATR from the reference)
       target      = the candidate's target
       entry range = reference +- 0.3 ATR (never at or beyond the stop)
       valid for   = entry_window_bars M1 bars

   R:R is re-checked with the real stop; below min_rr there is no trade.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from trading.intent import TradeIntent

ENTRY_SLACK_ATR = 0.3


@dataclass
class Candidate:
    key: str                  # "<level id>:<test number>" — stable across restarts
    side: str                 # "buy" | "sell"
    level: dict               # level as the engine reported it (id, price, side, sources, tests)
    test_no: int
    approach: str
    stretch: float | None
    trend: dict
    session: str
    atr: float
    plan_stop: float
    target: float
    target_source: str
    rr: float
    created_at: int
    expires_at: int
    evidence: list[str] = field(default_factory=list)     # engine event ids about this level
    status: str = "new"       # new -> asked -> approved / refused -> triggered | expired
    decision_id: str | None = None
    rejection: dict | None = None                         # the rejection event, once seen

    @property
    def sgn(self) -> int:
        return 1 if self.side == "sell" else -1           # +1: the stop is ABOVE the level

    def prompt_view(self, label: str) -> dict:
        lv = self.level
        return {"id": label, "side": self.side, "level": round(lv["price"], 2),
                "src": "+".join(lv["sources"]), "test": self.test_no, "appr": self.approach,
                "stretch_h1atr": self.stretch, "stop": round(self.plan_stop, 2),
                "target": round(self.target, 2), "target_src": self.target_source, "rr": round(self.rr, 2),
                "trigger": f"M1 candle beyond {lv['price']:.2f} closing back "
                           f"{'below' if self.side == 'sell' else 'above'} it"}


def plan(strategy, test_event: dict, snapshot: dict, session: str | None) -> tuple[Candidate | None, str]:
    """A level test -> a Candidate, or (None, reason it is not one)."""
    r, d = strategy.rules, test_event["data"]
    lv = d["level"]
    side = "sell" if lv["side"] == "high" else "buy"
    sess = session or "OFF"
    if side not in r["sides"]:
        return None, f"side {side} not in this strategy"
    if sess not in r["sessions"]:
        return None, f"session {sess} not traded"
    if d["test_no"] > r["max_test_no"]:
        return None, f"test {d['test_no']} > max_test_no {r['max_test_no']}"
    if d.get("approach", "unknown") not in r["approaches"]:
        return None, f"approach {d.get('approach')} not traded"
    atr = float(d["atr"])
    L = float(lv["price"])
    s = 1 if side == "sell" else -1
    plan_stop = L + s * r["plan_stop_allowance_atr"] * atr
    risk = abs(plan_stop - L)
    # the nearest higher-timeframe level on the other side, far enough away
    others = [x for x in snapshot.get("htf_levels", [])
              if x["side"] != lv["side"] and s * (L - x["price"]) >= r["min_target_atr"] * atr]
    if others:
        best = min(others, key=lambda x: abs(L - x["price"]))
        target, target_src = float(best["price"]), "+".join(best["sources"])
    else:
        target, target_src = L - s * r["fallback_target_r"] * risk, f"{r['fallback_target_r']}R (no level)"
    rr = abs(L - target) / risk if risk > 0 else 0.0
    if rr < r["min_rr"]:
        return None, f"R:R {rr:.2f} < {r['min_rr']}"
    created = test_event["available_at"]
    expires = test_event["time"] + 60 * (r["rejection_within_bars"] + r["entry_window_bars"] + 1)
    return Candidate(f"{lv['id']}:{d['test_no']}", side, lv, d["test_no"], d.get("approach", "unknown"),
                     d.get("stretch_h1_atr"), {k: v for k, v in (d.get("trend") or {}).items()}, sess, atr,
                     plan_stop, target, target_src, rr, created, expires), "ok"


def trigger(strategy, cand: Candidate, rejection_event: dict, now: int) -> tuple[TradeIntent | None, str]:
    """An approved candidate + its M1 rejection -> a TradeIntent with exact prices."""
    r = strategy.rules
    c = rejection_event["data"]["candle"]
    s, atr = cand.sgn, cand.atr
    ref = float(c["close"])
    extreme = float(c["high"]) if s > 0 else float(c["low"])
    stop = extreme + s * r["stop_buffer_atr"] * atr
    if s * (stop - ref) < r["min_stop_atr"] * atr:
        stop = ref + s * r["min_stop_atr"] * atr
    if s * (ref - cand.target) <= 0:
        return None, "target already reached"
    rr = abs(ref - cand.target) / abs(stop - ref)
    if rr < r["min_rr"]:
        return None, f"R:R at trigger {rr:.2f} < {r['min_rr']}"
    lo, hi = ref - ENTRY_SLACK_ATR * atr, ref + ENTRY_SLACK_ATR * atr
    if s > 0:
        hi = min(hi, stop - 0.05 * atr)
    else:
        lo = max(lo, stop + 0.05 * atr)
    created = rejection_event["available_at"]
    iid = hashlib.sha1(f"{strategy.ref}|{cand.key}|{c['time']}".encode()).hexdigest()[:16]
    return TradeIntent(
        intent_id=iid, strategy_ref=strategy.ref, decision_id=cand.decision_id or "", candidate_id=cand.key,
        side=cand.side, entry_low=round(lo, 3), entry_high=round(hi, 3), stop=round(stop, 3),
        target=round(cand.target, 3), created_at=created,
        expires_at=c["time"] + 60 * (1 + r["entry_window_bars"]), atr=atr,
        meta={"level": cand.level["price"], "sources": cand.level["sources"], "test_no": cand.test_no,
              "rejection_candle": c, "rr": round(rr, 2), "target_source": cand.target_source}), "ok"
