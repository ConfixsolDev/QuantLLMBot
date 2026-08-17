"""Timestamped request/response logs for Qwen and MT5 — full text in permanent archive."""

from __future__ import annotations

import inspect
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tick_data_archive import append_tick_record


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(base_name: str, record: dict) -> None:
    append_tick_record(base_name, record)


def _caller_label(skip: int = 2) -> str:
    frame = inspect.stack()[skip]
    return f"{Path(frame.filename).name}:{frame.function}"


def _summarize_mt5_result(operation: str, result: Any) -> dict:
    if result is None:
        return {"result": None}
    if operation in {"initialize", "shutdown", "symbol_select"}:
        return {"result": bool(result)}
    if operation == "symbol_info_tick" and hasattr(result, "_asdict"):
        row = result._asdict()
        return {
            "bid": row.get("bid"),
            "ask": row.get("ask"),
            "time": row.get("time"),
        }
    if operation == "account_info" and hasattr(result, "_asdict"):
        row = result._asdict()
        return {
            "login": row.get("login"),
            "server": row.get("server"),
            "trade_mode": row.get("trade_mode"),
            "balance": row.get("balance"),
            "equity": row.get("equity"),
        }
    if operation == "order_send" and hasattr(result, "_asdict"):
        row = result._asdict()
        return {
            "retcode": row.get("retcode"),
            "deal": row.get("deal"),
            "order": row.get("order"),
            "comment": row.get("comment"),
        }
    if hasattr(result, "__len__") and not isinstance(result, (str, bytes, dict)):
        try:
            length = len(result)
        except TypeError:
            length = None
        if length is not None:
            return {"count": length}
    if hasattr(result, "_asdict"):
        return {"fields": list(result._asdict().keys())}
    return {"result_type": type(result).__name__}


def log_mt5_exchange(
    *,
    operation: str,
    request: dict,
    response: dict | None,
    started_at_utc: str,
    finished_at_utc: str,
    duration_ms: float,
    ok: bool,
    caller: str | None = None,
    error: str | None = None,
) -> None:
    record = {
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "duration_ms": round(duration_ms, 3),
        "system": "mt5",
        "caller": caller or _caller_label(skip=3),
        "operation": operation,
        "request": request,
        "response": response or {},
        "ok": ok,
        "error": error,
    }
    _append_jsonl("mt5-io", record)
    logging.info(
        "MT5 %s caller=%s duration_ms=%.1f ok=%s",
        operation,
        record["caller"],
        duration_ms,
        ok,
    )


def mt5_timed(operation: str, request: dict, fn: Callable[[], Any]) -> Any:
    started_at = utc_now_iso()
    started = time.perf_counter()
    error = None
    ok = True
    result = None
    try:
        result = fn()
        if operation == "initialize" and not result:
            ok = False
            error = "initialize returned False"
        return result
    except Exception as exc:
        ok = False
        error = str(exc)
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        response = {}
        if ok and error is None:
            response = _summarize_mt5_result(operation, result)
        log_mt5_exchange(
            operation=operation,
            request=request,
            response=response,
            started_at_utc=started_at,
            finished_at_utc=utc_now_iso(),
            duration_ms=duration_ms,
            ok=ok,
            error=error,
        )


def log_qwen_exchange(
    *,
    operation: str,
    request: dict,
    response: dict | None,
    started_at_utc: str,
    finished_at_utc: str,
    duration_ms: float,
    ok: bool,
    caller: str | None = None,
    error: str | None = None,
    atr: dict | None = None,
) -> None:
    """Archive stores full prompt_text and response_text for later analysis."""
    response = response or {}
    atr_snapshot = atr if atr is not None else request.get("atr")
    record = {
        "started_at_utc": started_at_utc,
        "finished_at_utc": finished_at_utc,
        "duration_ms": round(duration_ms, 3),
        "system": "qwen",
        "caller": caller or _caller_label(skip=3),
        "operation": operation,
        # Top-level twin of request/response atr so exports never dig for it.
        "atr": atr_snapshot,
        "request": request,
        "response": {
            "response_text": response.get("response_text"),
            "response_chars": response.get("response_chars"),
            "total_duration_ns": response.get("total_duration_ns"),
            "load_duration_ns": response.get("load_duration_ns"),
            "prompt_eval_count": response.get("prompt_eval_count"),
            "eval_count": response.get("eval_count"),
            "done": response.get("done"),
            "done_reason": response.get("done_reason"),
            "model": response.get("model"),
            # Same snapshot that was recorded on the request, injected onto the
            # response so every answer carries the volatility regime it saw.
            "atr": atr_snapshot,
        },
        "ok": ok,
        "error": error,
    }
    _append_jsonl("qwen-io", record)
    atr_m1_51 = atr_m1_3 = atr_ratio = None
    if isinstance(atr_snapshot, dict):
        atr_m1_51 = atr_snapshot.get("atr_m1_51")
        atr_m1_3 = atr_snapshot.get("atr_m1_3")
        atr_ratio = atr_snapshot.get("atr_ratio_3_51")
    logging.info(
        "Qwen %s caller=%s duration_ms=%.1f ok=%s prompt_chars=%s "
        "response_chars=%s atr_m1_51=%s atr_m1_3=%s atr_ratio_3_51=%s%s",
        operation,
        record["caller"],
        duration_ms,
        ok,
        request.get("prompt_chars"),
        response.get("response_chars"),
        atr_m1_51,
        atr_m1_3,
        atr_ratio,
        f" error={error}" if error else "",
    )


def capture_atr_snapshot(symbol: str | None = None) -> dict:
    """ATR at Qwen-request time from cached M1 bars. Never calls MT5."""
    from market_atr import empty_atr_snapshot, snapshot_atr_from_cache

    try:
        from market_context_cache import get_cached_m1_bars

        m1_bars = get_cached_m1_bars(symbol)
        if m1_bars:
            return snapshot_atr_from_cache(m1_bars, symbol)
        return empty_atr_snapshot(symbol, error="no_cached_m1_bars")
    except Exception as exc:
        return empty_atr_snapshot(symbol, error=f"atr_cache_unavailable:{exc}")


def log_qwen_generate(
    *,
    model: str,
    prompt: str,
    num_ctx: int,
    num_predict: int,
    timeout: float | None,
    format_schema: dict | None,
    caller: str | None,
    fn: Callable[[], dict],
) -> dict:
    started_at = utc_now_iso()
    started = time.perf_counter()
    operation = "warm" if not prompt else "generate"
    atr_snapshot = capture_atr_snapshot()
    request = {
        "model": model,
        "prompt_text": prompt,
        "prompt_bytes": len(prompt.encode("utf-8")),
        "prompt_chars": len(prompt),
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "timeout": timeout,
        "format": "json" if format_schema or prompt else None,
        "atr": atr_snapshot,
    }
    error = None
    ok = True
    result: dict = {}
    try:
        result = fn()
        # Hand the same snapshot to callers (append_qwen_decision, etc.).
        if isinstance(result, dict):
            result = dict(result)
            result["market_atr"] = atr_snapshot
        return result
    except Exception as exc:
        ok = False
        error = str(exc)
        raise
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        response_text = result.get("response", "") if isinstance(result, dict) else ""
        log_qwen_exchange(
            operation=operation,
            request=request,
            response={
                "response_text": response_text,
                "response_chars": len(response_text),
                "total_duration_ns": result.get("total_duration") if isinstance(result, dict) else None,
                "load_duration_ns": result.get("load_duration") if isinstance(result, dict) else None,
                "prompt_eval_count": result.get("prompt_eval_count") if isinstance(result, dict) else None,
                "eval_count": result.get("eval_count") if isinstance(result, dict) else None,
                "done": result.get("done") if isinstance(result, dict) else None,
                "done_reason": result.get("done_reason") if isinstance(result, dict) else None,
                "model": (result.get("model", model) if isinstance(result, dict) else model),
            },
            started_at_utc=started_at,
            finished_at_utc=utc_now_iso(),
            duration_ms=duration_ms,
            ok=ok,
            caller=caller,
            error=error,
            atr=atr_snapshot,
        )
