"""Brokers: the MT5 demo account, and a paper broker for replays and tests.

Both have the same small interface, so the executor never knows which one
it talks to::

    account()                      {"balance", "equity", "currency", "login", "demo"}
    spec(symbol)                   SymbolSpec (tick value/size, volume limits, digits)
    quote(symbol)                  (bid, ask, utc time)
    positions(symbol, magic)       our open positions only
    open(symbol, side, lots, sl, tp, magic, comment, deviation) -> Fill
    close(position, comment)       market close of one position
    exit_summary(position_id, since) -> ExitSummary   (P&L from the broker's deals)

Lessons kept from the old executor (git tag pre-clean-2026-10-31,
goldflow/execution/paper_executor.py):

* the broker stop and target are sent WITH the order — protection never
  depends on our process staying alive;
* our positions are recognised by the magic number (comments can be
  rewritten by brokers);
* fill mode IOC where the symbol allows it (else FOK, else RETURN);
* after a position disappears, WAIT for its exit deal to settle (up to 5 s)
  before reading P&L — reading in that gap once recorded seven fake
  "0.00 P&L" trades; P&L without an exit deal is marked incomplete, never zero;
* close reason from the deal comments: "[sl" / "[tp" / "[so" = broker,
  our own comment prefix = strategy close, otherwise external.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .risk import SymbolSpec

OUR_PREFIX = "QL"          # order comments: "QL <intent id>" / "QL close <reason>"


@dataclass
class Position:
    id: int
    symbol: str
    side: str
    volume: float
    price_open: float
    sl: float
    tp: float
    time: int
    comment: str = ""
    magic: int = 0


@dataclass(frozen=True)
class Fill:
    position_id: int
    price: float
    volume: float
    time: int


@dataclass(frozen=True)
class ExitSummary:
    exit_price: float | None
    gross: float
    costs: float
    reason: str               # stop | target | strategy_close | stop_out | external | unsettled
    complete: bool            # False = the exit deal never appeared: P&L is unknown, not zero
    closed_at: int | None = None

    @property
    def net(self) -> float:
        return self.gross + self.costs


class BrokerError(RuntimeError):
    pass


# =========================================================================== MT5
class MT5Broker:
    SETTLE_S, POLL_S = 5.0, 0.25

    def __init__(self, mt5, to_utc) -> None:
        """``mt5``: the connected MetaTrader5 module; ``to_utc``: broker time -> UTC epoch."""
        self.mt5, self.to_utc = mt5, to_utc

    def account(self) -> dict:
        a = self.mt5.account_info()
        if a is None:
            raise BrokerError(f"MT5 account unavailable: {self.mt5.last_error()}")
        return {"balance": float(a.balance), "equity": float(a.equity), "currency": a.currency,
                "login": int(a.login), "demo": a.trade_mode == self.mt5.ACCOUNT_TRADE_MODE_DEMO}

    def spec(self, symbol: str) -> SymbolSpec:
        i = self.mt5.symbol_info(symbol)
        if i is None:
            raise BrokerError(f"symbol {symbol} unknown to MT5")
        return SymbolSpec(symbol, float(i.trade_tick_value), float(i.trade_tick_size), float(i.volume_min),
                          float(i.volume_max), float(i.volume_step), int(i.digits))

    def quote(self, symbol: str) -> tuple[float, float, int]:
        t = self.mt5.symbol_info_tick(symbol)
        if t is None:
            raise BrokerError(f"no tick for {symbol}")
        return float(t.bid), float(t.ask), self.to_utc(int(t.time))

    def positions(self, symbol: str, magic: int) -> list[Position]:
        out = []
        for p in self.mt5.positions_get(symbol=symbol) or ():
            if int(p.magic) == magic:
                out.append(Position(int(p.ticket), str(p.symbol),
                                    "buy" if p.type == self.mt5.POSITION_TYPE_BUY else "sell",
                                    float(p.volume), float(p.price_open), float(p.sl), float(p.tp),
                                    self.to_utc(int(p.time)), str(p.comment), int(p.magic)))
        return out

    def _filling(self, symbol: str) -> int:
        mode = int(getattr(self.mt5.symbol_info(symbol), "filling_mode", 0))
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        return self.mt5.ORDER_FILLING_RETURN

    def open(self, symbol: str, side: str, lots: float, sl: float, tp: float, magic: int,
             comment: str, deviation: int) -> Fill:
        bid, ask, now = self.quote(symbol)
        m = self.mt5
        req = {"action": m.TRADE_ACTION_DEAL, "symbol": symbol, "volume": lots,
               "type": m.ORDER_TYPE_BUY if side == "buy" else m.ORDER_TYPE_SELL,
               "price": ask if side == "buy" else bid, "sl": sl, "tp": tp, "deviation": deviation,
               "magic": magic, "comment": comment[:31], "type_time": m.ORDER_TIME_GTC,
               "type_filling": self._filling(symbol)}
        res = m.order_send(req)
        if res is None or res.retcode not in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL):
            raise BrokerError(f"order rejected: {res.comment if res else m.last_error()}")
        return Fill(int(res.order), float(res.price or req["price"]), float(res.volume or lots), now)

    def close(self, position: Position, comment: str) -> None:
        bid, ask, _ = self.quote(position.symbol)
        m = self.mt5
        req = {"action": m.TRADE_ACTION_DEAL, "symbol": position.symbol, "volume": position.volume,
               "type": m.ORDER_TYPE_SELL if position.side == "buy" else m.ORDER_TYPE_BUY,
               "position": position.id, "price": bid if position.side == "buy" else ask, "deviation": 50,
               "magic": position.magic, "comment": comment[:31],
               "type_time": m.ORDER_TIME_GTC, "type_filling": self._filling(position.symbol)}
        res = m.order_send(req)
        if res is None or res.retcode not in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL):
            raise BrokerError(f"close rejected: {res.comment if res else m.last_error()}")

    def exit_summary(self, position_id: int, since: int) -> ExitSummary:
        m = self.mt5
        start = datetime.fromtimestamp(since - 3600, tz=timezone.utc)
        deadline = time.monotonic() + self.SETTLE_S
        while True:
            deals = [d for d in (m.history_deals_get(start, datetime.now(timezone.utc)) or ())
                     if int(d.position_id) == position_id]
            exits = [d for d in deals if d.entry != m.DEAL_ENTRY_IN]
            if exits or time.monotonic() >= deadline:
                break
            time.sleep(self.POLL_S)
        gross = sum(float(d.profit) for d in deals)
        costs = sum(float(d.commission) + float(d.swap) + float(getattr(d, "fee", 0.0)) for d in deals)
        if not exits:
            return ExitSummary(None, gross, costs, "unsettled", False)
        comments = " ".join(str(d.comment) for d in exits)
        reason = ("stop" if "[sl" in comments else "target" if "[tp" in comments else
                  "stop_out" if "[so" in comments else
                  "strategy_close" if f"{OUR_PREFIX} close" in comments else "external")
        vol = sum(float(d.volume) for d in exits)
        price = sum(float(d.price) * float(d.volume) for d in exits) / vol
        return ExitSummary(price, gross, costs, reason, True, self.to_utc(int(exits[-1].time)))


# =========================================================================== paper
@dataclass
class PaperBroker:
    """Simulated demo account driven by closed M1 bars (replays, tests).

    Prices: the bar's OHLC are bids; ask = bid + spread. Market orders fill at
    the current bar's close (+ spread for buys). Inside a later bar the stop is
    assumed hit BEFORE the target when both are touched (conservative).
    """
    spec_: SymbolSpec
    balance: float = 10_000.0
    spread: float = 0.2
    commission_per_lot: float = 0.0
    demo: bool = True
    now: int = 0
    bid: float = 0.0
    open_: dict = field(default_factory=dict)
    closed: dict = field(default_factory=dict)
    _next: int = 1

    def account(self) -> dict:
        return {"balance": self.balance, "equity": self.balance, "currency": "USD", "login": 0, "demo": self.demo}

    def spec(self, symbol: str) -> SymbolSpec:
        return self.spec_

    def quote(self, symbol: str) -> tuple[float, float, int]:
        return self.bid, self.bid + self.spread, self.now

    def positions(self, symbol: str, magic: int) -> list[Position]:
        return list(self.open_.values())

    def open(self, symbol, side, lots, sl, tp, magic, comment, deviation) -> Fill:
        price = self.bid + self.spread if side == "buy" else self.bid
        pid = self._next
        self._next += 1
        self.open_[pid] = Position(pid, symbol, side, lots, price, sl, tp, self.now, comment, magic)
        return Fill(pid, price, lots, self.now)

    def close(self, position: Position, comment: str) -> None:
        price = self.bid if position.side == "buy" else self.bid + self.spread
        self._settle(position, price, "strategy_close" if comment.startswith(f"{OUR_PREFIX} close") else "external")

    def on_bar(self, bar) -> None:
        """Advance to a closed M1 bar: stops/targets inside it first, then the new close."""
        for p in list(self.open_.values()):
            if p.side == "buy":
                if p.sl and bar.low <= p.sl:
                    self._settle(p, p.sl, "stop", bar.close_time)
                elif p.tp and bar.high >= p.tp:
                    self._settle(p, p.tp, "target", bar.close_time)
            else:
                if p.sl and bar.high + self.spread >= p.sl:
                    self._settle(p, p.sl, "stop", bar.close_time)
                elif p.tp and bar.low + self.spread <= p.tp:
                    self._settle(p, p.tp, "target", bar.close_time)
        self.bid, self.now = bar.close, bar.close_time

    def _settle(self, p: Position, price: float, reason: str, when: int | None = None) -> None:
        move = (price - p.price_open) if p.side == "buy" else (p.price_open - price)
        gross = round(move * self.spec_.value_per_unit * p.volume, 2)
        costs = -round(self.commission_per_lot * p.volume, 2)
        self.balance += gross + costs
        self.open_.pop(p.id, None)
        self.closed[p.id] = ExitSummary(price, gross, costs, reason, True, when or self.now)

    def exit_summary(self, position_id: int, since: int) -> ExitSummary:
        return self.closed.get(position_id) or ExitSummary(None, 0.0, 0.0, "unsettled", False)
