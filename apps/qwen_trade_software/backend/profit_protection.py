"""Independent low-latency broker worker for MFE/ATR profit protection."""

from __future__ import annotations

import logging
import socket
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

import build_manifest
import process_logging
from profit_protection_policy import evaluate
from review_shared import (
    LOG_DIR, PROTECTION_STATE_FILE, QWEN_MAGIC, connect_mt5, gold_market_open,
    is_qwen_owned, write_json_atomic,
)
from tick_data_archive import append_tick_record


POLL_SECONDS = 0.25
HEARTBEAT_SECONDS = 10.0
STATE: dict[int, dict] = {}
process_logging.configure(LOG_DIR / "profit-protection.log", owner="profit_protection")
build_manifest.log_identity("profit_protection")


def _atr_m1(symbol: str, periods: int = 51) -> float:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, periods + 1)
    if rates is None or len(rates) < 3:
        return 0.0
    rows = list(rates)[-(periods + 1):]
    values = []
    for previous, row in zip(rows, rows[1:]):
        values.append(max(
            float(row["high"]) - float(row["low"]),
            abs(float(row["high"]) - float(previous["close"])),
            abs(float(row["low"]) - float(previous["close"])),
        ))
    return sum(values) / len(values) if values else 0.0


def _audit(position, decision, event: str, **extra) -> None:
    record = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "ticket": int(position.ticket),
        "symbol": position.symbol,
        "side": "buy" if position.type == mt5.POSITION_TYPE_BUY else "sell",
        "volume": float(position.volume),
        "entry": float(position.price_open),
        "current": float(position.price_current),
        "broker_sl": float(position.sl or 0.0),
        "broker_tp": float(position.tp or 0.0),
        **decision.record(), **extra, **build_manifest.stamp(),
    }
    append_tick_record("profit-protection", record)
    write_json_atomic(PROTECTION_STATE_FILE, record)


def _close(position, price: float):
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    return mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket,
        "symbol": position.symbol, "volume": position.volume,
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "price": price, "deviation": 20, "magic": QWEN_MAGIC,
        "comment": "QWEN_PROTECT_CLOSE", "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })


def supervise_once(now: float | None = None) -> None:
    now = now or time.monotonic()
    positions = tuple(p for p in (mt5.positions_get() or ()) if is_qwen_owned(p))
    live = {int(p.ticket) for p in positions}
    for ticket in set(STATE) - live:
        STATE.pop(ticket, None)
    for position in positions:
        tick = mt5.symbol_info_tick(position.symbol)
        info = mt5.symbol_info(position.symbol)
        if tick is None or info is None:
            continue
        is_buy = position.type == mt5.POSITION_TYPE_BUY
        current = float(tick.bid if is_buy else tick.ask)
        state = STATE.setdefault(int(position.ticket), {
            "peak": current, "atr": 0.0, "atr_at": 0.0,
            "heartbeat_at": 0.0, "last_state": None,
            "initial_risk": abs(float(position.price_open) - float(position.sl or 0.0)),
        })
        state["peak"] = max(state["peak"], current) if is_buy else min(state["peak"], current)
        if not state["atr"] or now - state["atr_at"] >= 10.0:
            state["atr"] = _atr_m1(position.symbol)
            state["atr_at"] = now
        decision = evaluate(
            side="buy" if is_buy else "sell", entry=float(position.price_open),
            current=current, peak=float(state["peak"]), broker_sl=float(position.sl or 0.0),
            atr=float(state["atr"]), spread=max(0.0, float(tick.ask - tick.bid)),
            point=float(info.point), initial_risk=float(state["initial_risk"]),
        )
        changed = decision.state != state["last_state"]
        heartbeat = now - state["heartbeat_at"] >= HEARTBEAT_SECONDS
        if changed or heartbeat:
            _audit(position, decision, "state" if changed else "heartbeat",
                   quote_time_msc=getattr(tick, "time_msc", None),
                   risk_cash=round(decision.initial_risk * float(position.volume) * 100, 2),
                   locked_cash=round(decision.locked_move * float(position.volume) * 100, 2))
            state["last_state"] = decision.state
            state["heartbeat_at"] = now
        if not decision.should_modify:
            continue
        candidate = round(float(decision.candidate_stop), int(info.digits))
        if decision.crossed:
            result = _close(position, current)
            _audit(position, decision, "market_close", requested_price=current,
                   retcode=getattr(result, "retcode", None),
                   comment=getattr(result, "comment", str(mt5.last_error())))
            continue
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_SLTP, "position": position.ticket,
            "symbol": position.symbol, "sl": candidate, "tp": float(position.tp or 0.0),
        })
        _audit(position, decision, "stop_update", requested_stop=candidate,
               retcode=getattr(result, "retcode", None),
               comment=getattr(result, "comment", str(mt5.last_error())))


def main() -> None:
    singleton = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # 48634 belongs to session_planner. Sharing it silently disabled the
        # planner whenever this faster worker started first.
        singleton.bind(("127.0.0.1", 48635)); singleton.listen(1)
    except OSError:
        return
    logging.info("Profit protection starting; poll=%.2fs", POLL_SECONDS)
    while True:
        started = time.monotonic()
        try:
            if gold_market_open().get("open"):
                connect_mt5(); supervise_once(started)
            else:
                STATE.clear()
        except Exception:
            logging.exception("Profit protection cycle failed")
            try: mt5.shutdown()
            except Exception: pass
        time.sleep(max(0.05, POLL_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
