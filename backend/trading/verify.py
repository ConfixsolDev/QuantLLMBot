"""Does the trading system behave EXACTLY as specified? Checks on a finished run.

``verify(strategy, settings, journal)`` returns a list of failures (empty =
every rule held). It is run by ``python -m trading.backtest --verify`` and by
the tests. What it checks, trade by trade and decision by decision:

decisions
  D1  every prompt is within the strategy's byte budget
  D2  every verdict is take / wait / invalid; a "take" names a candidate of that prompt
trades
  T1  every trade belongs to a "take" decision (nothing trades without approval)
  T2  stop on the correct side, at least min_stop_atr x ATR from the trigger close
      (stop_mode "atr"), at most max_stop_atr (stop_mode "beyond_higher_level")
  T3  target = trigger close -+ target_r x risk (rules.target "r_multiple")
  T4  money at risk <= balance x risk_pct (the size never exceeds the budget)
  T5  filled within the entry window after the rejection candle closed
  T6  never more open positions than max_open_positions at the same time
  T7  every closed trade has a complete P&L and an R multiple
  T8  stop / target exits happen at the stop / target price; a stop costs about -1 R
      (a little less: the risk money includes the spread + slippage allowance)
  T9  no "stalled" early close when the strategy has close_on_stalled_followthrough off
"""

from __future__ import annotations

TOL_R = 0.15                      # spread and rounding, in R


def verify(strategy, settings, journal) -> list[str]:
    r = strategy.rules
    bad: list[str] = []
    takes = {}
    for d in journal.decisions:
        if d["prompt_bytes"] > strategy.prompt["max_bytes"]:
            bad.append(f"D1 decision {d['id']}: prompt {d['prompt_bytes']} bytes > {strategy.prompt['max_bytes']}")
        if d["action"] not in ("take", "wait", "invalid"):
            bad.append(f"D2 decision {d['id']}: action {d['action']!r}")
        if d["action"] == "take":
            if d.get("label") not in d["candidates"]:
                bad.append(f"D2 decision {d['id']}: took {d.get('label')} not offered {list(d['candidates'])}")
            takes[d["id"]] = d
    trades = sorted(journal.trades.values(), key=lambda t: t["opened_at"])
    for t in trades:
        tid = t["id"]
        if t.get("decision_id") not in takes:
            bad.append(f"T1 trade {tid}: no 'take' decision {t.get('decision_id')}")
        m = t.get("meta", {})
        c = m.get("rejection_candle") or {}
        ref, atr = c.get("close"), m.get("atr") or t.get("atr")
        s = 1 if t["side"] == "buy" else -1
        if ref is None or not atr:
            bad.append(f"T2 trade {tid}: missing trigger close / ATR in the record")
            continue
        risk = s * (ref - t["stop"])
        if risk <= 0:
            bad.append(f"T2 trade {tid}: stop {t['stop']} on the wrong side of {ref}")
            continue
        if risk < r["min_stop_atr"] * atr - 0.005:            # prices are rounded to 3 decimals
            bad.append(f"T2 trade {tid}: stop {risk / atr:.2f} ATR < min {r['min_stop_atr']}")
        if m.get("stop_source", "atr").startswith("beyond") \
                and risk > r["max_stop_atr"] * atr + 0.005:
            bad.append(f"T2 trade {tid}: stop {risk / atr:.2f} ATR > max {r['max_stop_atr']}")
        if r["target"] == "r_multiple":
            want = ref + s * r["target_r"] * risk
            if abs(t["target"] - want) > 0.01:
                bad.append(f"T3 trade {tid}: target {t['target']} != {want:.3f} ({r['target_r']} R)")
        budget = (t.get("balance_before") or 0) * settings.risk_pct / 100
        if t["risk_money"] > budget + 0.01:
            bad.append(f"T4 trade {tid}: risk {t['risk_money']} > budget {budget:.2f}")
        window = 60 * (1 + r["entry_window_bars"])
        if t.get("intent_created_at") is not None and t["opened_at"] - c["time"] > window:
            bad.append(f"T5 trade {tid}: filled {t['opened_at'] - c['time']} s after the rejection candle")
        if t.get("closed_at") is not None:
            if not t.get("pnl_complete") or t.get("r_multiple") is None:
                bad.append(f"T7 trade {tid}: closed without complete P&L / R")
            elif t["close_reason"] in ("stop", "target"):
                want = t["stop"] if t["close_reason"] == "stop" else t["target"]
                if abs((t.get("exit_price") or 0) - want) > max(0.3, 0.1 * atr):
                    bad.append(f"T8 trade {tid}: {t['close_reason']} exit at {t.get('exit_price')} not {want}")
                if t["close_reason"] == "stop" and not -1 - TOL_R <= t["r_multiple"] <= -1 + TOL_R + 0.25:
                    bad.append(f"T8 trade {tid}: stop exit at {t['r_multiple']} R")
            if t["close_reason"] == "strategy_close" and not r["close_on_stalled_followthrough"]:
                bad.append(f"T9 trade {tid}: closed early although early closes are off")
    open_at = []
    for t in trades:
        open_at = [x for x in open_at if x > t["opened_at"]]
        if len(open_at) >= settings.max_open_positions:
            bad.append(f"T6 trade {t['id']}: opened while {len(open_at)} position(s) were open")
        open_at.append(t.get("closed_at") or 10 ** 12)
    return bad
