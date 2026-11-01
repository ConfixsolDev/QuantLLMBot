"""Executor: TradeIntent -> order (or a refusal with a reason), then the trade's life.

``execute(intent, now)`` checks, in this order, and refuses at the first failure:

  1. demo account (require_demo; the executor never trades a live account)
  2. the intent has not expired (entry window = a few M1 bars after the trigger)
  3. fewer than max_open_positions of OUR positions are open (default 1)
  4. daily loss limit, only when one is set (off during the demo learning phase)
  5. the live price (ask for buys, bid for sells) is inside the intent's entry range
  6. the stop and the target are on the correct sides of that price
  7. a size > 0 from risk.position_size (% of balance per stop distance)

then sends ONE market order with the stop and target attached.

``close(candidate_key, reason)`` closes our position for a strategy reason
(e.g. "rejection stalled"). ``sync(now)`` notices positions that are gone
(stop, target, our close, or external) and finalises their record from the
broker's deals: exit price, gross, costs, net and the result in R
(net / money risked), so results compare across any position size.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .broker import OUR_PREFIX, BrokerError
from .intent import TradeIntent
from .risk import position_size
from .settings import TradingSettings


@dataclass
class Outcome:
    status: str          # "filled" | "refused" | "error"
    reason: str
    trade: dict | None = None


class Executor:
    def __init__(self, broker, settings: TradingSettings, symbol: str, journal=None) -> None:
        self.b, self.s, self.symbol, self.journal = broker, settings, symbol, journal
        self.open_trades: dict[int, dict] = {}            # position id -> trade record

    # ------------------------------------------------------------------ entry
    def execute(self, intent: TradeIntent, now: int) -> Outcome:
        out = self._execute(intent, now)
        if self.journal is not None and out.status != "filled":
            self.journal.refusal(intent, out.status, out.reason, now)
        return out

    def _execute(self, intent: TradeIntent, now: int) -> Outcome:
        s = self.s
        try:
            acc = self.b.account()
            if s.require_demo and not acc["demo"]:
                return Outcome("refused", "account is NOT a demo account")
            if now > intent.expires_at:
                return Outcome("refused", f"intent expired {now - intent.expires_at} s ago")
            if len(self.b.positions(self.symbol, s.magic)) >= s.max_open_positions:
                return Outcome("refused", f"{s.max_open_positions} position(s) already open")
            if s.daily_loss_limit_pct is not None and self.journal is not None:
                lost = -min(0.0, self.journal.net_today(now))
                if lost >= acc["balance"] * s.daily_loss_limit_pct / 100:
                    return Outcome("refused", f"daily loss limit {s.daily_loss_limit_pct}% reached")
            bid, ask, _ = self.b.quote(self.symbol)
            price = ask if intent.side == "buy" else bid
            if not intent.entry_low <= price <= intent.entry_high:
                return Outcome("refused", f"price {price} outside entry range "
                                          f"{intent.entry_low}-{intent.entry_high}")
            sgn = 1 if intent.side == "buy" else -1
            if sgn * (price - intent.stop) <= 0:
                return Outcome("refused", f"stop {intent.stop} is not beyond price {price}")
            if sgn * (intent.target - price) <= 0:
                return Outcome("refused", f"target {intent.target} is not ahead of price {price}")
            spec = self.b.spec(self.symbol)
            size = position_size(acc["balance"], s.risk_pct, price, intent.stop, spec,
                                 spread=ask - bid, slippage=s.slippage_allowance)
            if size.lots <= 0:
                return Outcome("refused", size.reason)
            fill = self.b.open(self.symbol, intent.side, size.lots, round(intent.stop, spec.digits),
                               round(intent.target, spec.digits), s.magic,
                               f"{OUR_PREFIX} {intent.intent_id[:12]}", s.deviation_points)
        except BrokerError as exc:
            return Outcome("error", str(exc))
        trade = {"id": intent.intent_id, "decision_id": intent.decision_id, "strategy_ref": intent.strategy_ref,
                 "candidate_key": intent.candidate_id, "side": intent.side, "lots": fill.volume,
                 "entry": fill.price, "stop": intent.stop, "target": intent.target,
                 "risk_money": size.risk_money, "balance_before": acc["balance"], "risk_pct": s.risk_pct,
                 "position_id": fill.position_id, "opened_at": max(fill.time or 0, now), "mode": self.s.mode,
                 "atr": intent.atr, "intent_created_at": intent.created_at,
                 "meta": intent.meta}
        self.open_trades[fill.position_id] = trade
        if self.journal is not None:
            self.journal.trade_opened(trade)
        return Outcome("filled", "ok", trade)

    # ------------------------------------------------------------------ management
    def close(self, candidate_key: str, reason: str, now: int) -> bool:
        for pos in self.b.positions(self.symbol, self.s.magic):
            t = self.open_trades.get(pos.id)
            if t and t["candidate_key"] == candidate_key:
                try:
                    self.b.close(pos, f"{OUR_PREFIX} close {reason}")
                except BrokerError:
                    return False
                t["close_note"] = reason
                return True
        return False

    def sync(self, now: int) -> list[dict]:
        """Finalise trades whose position is gone. Returns the closed trade records."""
        live = {p.id for p in self.b.positions(self.symbol, self.s.magic)}
        done = []
        for pid in [p for p in self.open_trades if p not in live]:
            t = self.open_trades.pop(pid)
            ex = self.b.exit_summary(pid, t["opened_at"])
            t.update(closed_at=ex.closed_at or now, exit_price=ex.exit_price, gross=ex.gross, costs=ex.costs,
                     net=round(ex.net, 2), close_reason=ex.reason, pnl_complete=ex.complete,
                     r_multiple=round(ex.net / t["risk_money"], 3) if ex.complete and t["risk_money"] else None)
            if self.journal is not None:
                self.journal.trade_closed(t)
            done.append(t)
        return done


def utc_now() -> int:
    return int(time.time())
