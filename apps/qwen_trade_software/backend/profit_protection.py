"""Independent low-latency broker worker for MFE/ATR profit protection."""

from __future__ import annotations

import logging
import math
import socket
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5

import build_manifest
from cooldown_manager import (
    VolatilityDetector, start_volatility_cooldown, volatility_cooldown_active,
)
from entry_safety import temporal_protection_window
import process_logging
from profit_protection_policy import FRONT_LAYER_VOLUME_FRACTION, evaluate
from review_shared import (
    LOG_DIR, PROTECTION_STATE_FILE, QWEN_MAGIC, connect_mt5, gold_market_open,
    is_qwen_owned, read_json_safe, write_json_atomic,
)
from tick_data_archive import append_tick_record
from runtime_config import PRIMARY_MARKET_SYMBOL


POLL_SECONDS = 0.25
HEARTBEAT_SECONDS = 10.0
STATE: dict[int, dict] = {}
VOLATILITY = VolatilityDetector()
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


def _close(
    position, price: float, volume: float | None = None,
    *, comment: str = "QWEN_PROTECT_CLOSE",
):
    is_buy = position.type == mt5.POSITION_TYPE_BUY
    return mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL, "position": position.ticket,
        "symbol": position.symbol, "volume": float(volume or position.volume),
        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
        "price": price, "deviation": 20, "magic": QWEN_MAGIC,
        "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })


def _partial_volume(original_volume: float, current_volume: float, info) -> float:
    """Return a broker-valid close volume that leaves a tradable remainder."""
    step = float(getattr(info, "volume_step", 0.01) or 0.01)
    minimum = float(getattr(info, "volume_min", step) or step)
    requested = float(original_volume) * FRONT_LAYER_VOLUME_FRACTION
    close_volume = math.floor((requested + step * 1e-9) / step) * step
    maximum_close = float(current_volume) - minimum
    close_volume = min(close_volume, maximum_close)
    close_volume = math.floor((close_volume + step * 1e-9) / step) * step
    if close_volume < minimum:
        return 0.0
    decimals = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
    return round(close_volume, decimals)


def _order_succeeded(result) -> bool:
    return bool(result) and getattr(result, "retcode", None) in {
        getattr(mt5, "TRADE_RETCODE_DONE", 10009),
        getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
    }


def supervise_once(now: float | None = None) -> None:
    now = now or time.monotonic()
    market_tick = mt5.symbol_info_tick(PRIMARY_MARKET_SYMBOL)
    if market_tick is not None:
        tick_seconds = float(getattr(market_tick, "time_msc", 0) or 0) / 1000.0
        midpoint = (float(market_tick.bid) + float(market_tick.ask)) / 2.0
        shock = VOLATILITY.observe(
            PRIMARY_MARKET_SYMBOL, tick_seconds or time.time(), midpoint
        )
        if shock:
            cooldown = start_volatility_cooldown(shock)
            append_tick_record("profit-protection", {
                "schema_version": 1,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event": "volatility_cooldown_started",
                **shock,
                "until_utc": cooldown["until_utc"],
                **build_manifest.stamp(),
            })
            logging.warning("Volatility cooldown started: %s", shock)
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
        ticket = int(position.ticket)
        if ticket not in STATE:
            prior = read_json_safe(PROTECTION_STATE_FILE, {})
            same_position = int(prior.get("ticket") or 0) == ticket
            STATE[ticket] = {
                "peak": float(prior.get("peak") or current)
                if same_position else current,
                "atr": float(prior.get("atr") or 0.0)
                if same_position else 0.0,
                "atr_at": now if same_position and prior.get("atr") else 0.0,
                "heartbeat_at": 0.0, "last_state": None,
                "initial_risk": float(prior.get("initial_risk") or 0.0)
                if same_position else abs(
                    float(position.price_open) - float(position.sl or 0.0)
                ),
                "original_volume": float(prior.get("original_volume") or position.volume)
                if same_position else float(position.volume),
                "front_layer_closed": bool(prior.get("front_layer_closed"))
                if same_position else False,
            }
        state = STATE[ticket]
        state["peak"] = max(state["peak"], current) if is_buy else min(state["peak"], current)
        # Freeze the first usable ATR for this position.  Recalculating the
        # ruler while a trade is moving makes the same price path produce
        # different floors and can silently tighten the ladder.
        if not state["atr"]:
            observed_atr = _atr_m1(position.symbol)
            if observed_atr > 0:
                state["atr"] = observed_atr
                state["atr_at"] = now
        decision = evaluate(
            side="buy" if is_buy else "sell", entry=float(position.price_open),
            current=current, peak=float(state["peak"]), broker_sl=float(position.sl or 0.0),
            atr=float(state["atr"]), spread=max(0.0, float(tick.ask - tick.bid)),
            point=float(info.point), initial_risk=float(state["initial_risk"]),
            force_break_even=bool(
                temporal_protection_window() or volatility_cooldown_active()
            ),
        )
        changed = decision.state != state["last_state"]
        heartbeat = now - state["heartbeat_at"] >= HEARTBEAT_SECONDS
        if changed or heartbeat:
            _audit(position, decision, "state" if changed else "heartbeat",
                   quote_time_msc=getattr(tick, "time_msc", None),
                   risk_cash=round(decision.initial_risk * float(position.volume) * 100, 2),
                   locked_cash=round(decision.locked_move * float(position.volume) * 100, 2),
                   atr_frozen=True,
                   peak=float(state["peak"]),
                   original_volume=float(state["original_volume"]),
                   front_layer_closed=bool(state["front_layer_closed"]))
            state["last_state"] = decision.state
            state["heartbeat_at"] = now
        if (
            decision.front_crossed
            and not state["front_layer_closed"]
        ):
            close_volume = _partial_volume(
                float(state["original_volume"]), float(position.volume), info
            )
            if close_volume > 0:
                result = _close(
                    position, current, close_volume,
                    comment="QWEN_PROTECT_FRONT_25",
                )
                succeeded = _order_succeeded(result)
                if succeeded:
                    state["front_layer_closed"] = True
                _audit(
                    position, decision, "front_layer_close",
                    requested_price=current, requested_volume=close_volume,
                    succeeded=succeeded,
                    peak=float(state["peak"]),
                    original_volume=float(state["original_volume"]),
                    front_layer_closed=succeeded,
                    retcode=getattr(result, "retcode", None),
                    comment=getattr(result, "comment", str(mt5.last_error())),
                )
                if succeeded:
                    refreshed = mt5.positions_get(ticket=position.ticket) or ()
                    if not refreshed:
                        continue
                    position = refreshed[0]
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
