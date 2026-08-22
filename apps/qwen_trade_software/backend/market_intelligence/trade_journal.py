"""Canonical SQLite trade journal and evidence-based postmortem builder."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .store import IntelligenceStore, canonical

log = logging.getLogger(__name__)
BACKEND = Path(__file__).resolve().parents[1]
LOG_DIR = BACKEND / "logs"
DEFAULT_DB = BACKEND / "cache" / "market-intelligence.sqlite3"


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except (json.JSONDecodeError, TypeError):
            continue
    return rows


def _proposal(proposal_id: str, day: str) -> dict:
    current = datetime.fromisoformat(day).date()
    for suffix in (str(current), str(current - timedelta(days=1))):
        for row in reversed(_jsonl(LOG_DIR / f"paper-proposals-{suffix}.jsonl")):
            if row.get("proposal_id") == proposal_id:
                return row
    return {}


def _secured(fills: list[dict], day: str) -> dict:
    tickets = {str(fill.get("order")) for fill in fills if fill.get("order")}
    best = {"cash": 0.0, "stop": None, "at": None}
    if not tickets:
        return best
    current = datetime.fromisoformat(day).date()
    rows = []
    for suffix in (str(current - timedelta(days=1)), str(current)):
        rows.extend(_jsonl(LOG_DIR / f"profit-protection-{suffix}.jsonl"))
    for row in rows:
        if str(row.get("ticket")) not in tickets:
            continue
        if row.get("event") not in {"stop_update", "market_close"}:
            continue
        if row.get("event") == "stop_update" and row.get("retcode") not in (10009, "10009"):
            continue
        cash = max(0.0, float(row.get("locked_cash") or 0.0))
        if cash <= 0:
            cash = max(
                0.0,
                float(row.get("locked_move") or 0.0)
                * float(row.get("volume") or 0.0)
                * 100.0,
            )
        if cash >= best["cash"]:
            best = {
                "cash": cash,
                "stop": row.get("requested_stop") or row.get("candidate_stop"),
                "at": row.get("timestamp_utc"),
            }
    return best


def _loss_reasons(close: dict, proposal: dict, secured: dict) -> list[dict]:
    try:
        net = float(close.get("net_pnl") or 0.0)
    except (TypeError, ValueError):
        net = 0.0
    if net >= 0:
        return []
    qwen = proposal.get("qwen") or {}
    plan = qwen.get("execution_plan") or {}
    fills = close.get("fills") or []
    source = str((fills[0] if fills else {}).get("sl_source") or "")
    reasons = []
    if "after_geometry:" in source:
        reasons.append({
            "code": "structural_geometry_rejected_fallback",
            "evidence": source.split("after_", 1)[-1],
        })
    peak = float(close.get("peak_pnl") or 0.0)
    if peak > 0 and float(secured.get("cash") or 0.0) <= 0:
        reasons.append({
            "code": "favorable_excursion_not_secured",
            "evidence": {"peak_pnl": peak, "price_giveback": close.get("price_giveback")},
        })
    try:
        planned = float(plan["optimal_entry_price"])
        structural = float(plan["zone_edge_context"]["optimal_entry_price"])
        width = abs(float(plan["entry_high"]) - float(plan["entry_low"]))
        if abs(planned - structural) > max(0.5, width * 0.5):
            reasons.append({
                "code": "entry_edge_mismatch",
                "evidence": {"planned": planned, "structural": structural},
            })
    except (KeyError, TypeError, ValueError):
        pass
    if close.get("manager_close_decision") is None and "sl" in " ".join(
        str(value).lower() for value in (close.get("close_comments") or [])
    ):
        reasons.append({"code": "broker_stop_without_manager_exit", "evidence": close.get("close_comments")})
    return reasons or [{"code": "market_thesis_failed", "evidence": close.get("reason")}]


def build_journal(close: dict, proposal: dict | None = None) -> dict:
    proposal_id = str(close["proposal_id"])
    exit_time = str(close["created_at_utc"])
    day = exit_time[:10]
    proposal = proposal or _proposal(proposal_id, day)
    qwen = proposal.get("qwen") or {}
    plan = qwen.get("execution_plan") or {}
    fills = close.get("fills") or []
    fill = fills[0] if fills else {}
    secured = _secured(fills, day)
    net = float(close.get("net_pnl") or 0.0)
    result = "win" if net > 0 else "loss" if net < 0 else "breakeven"
    evidence = list(dict.fromkeys(
        str(value) for value in (plan.get("cache_evidence_ids") or []) if value
    ))
    outcome = {
        "reason": close.get("reason"),
        "close_comments": close.get("close_comments") or [],
        "manager_close_decision": close.get("manager_close_decision"),
        "pnl_is_complete": close.get("pnl_is_complete"),
    }
    source_hash = hashlib.sha256(canonical({
        "close": close, "proposal_id": proposal_id, "secured": secured,
    }).encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    return {
        "proposal_id": proposal_id,
        "execution_id": str(close.get("execution_id") or ""),
        "symbol": str(proposal.get("symbol") or fill.get("symbol") or "XAUUSDr"),
        "side": str(plan.get("side") or fill.get("side") or "unknown"),
        "result": result,
        "idea_summary": qwen.get("summary"),
        "idea_reason": plan.get("reason"),
        "model": qwen.get("model"),
        "confidence": qwen.get("confidence"),
        "structure_timeframe": plan.get("structure_timeframe"),
        "entry_time_utc": fill.get("filled_at_utc"),
        "exit_time_utc": exit_time,
        "entry_price": close.get("average_entry") or fill.get("price"),
        "exit_price": close.get("exit_price"),
        "volume": fill.get("volume"),
        "initial_stop": fill.get("stop_loss"),
        "initial_target": fill.get("take_profit"),
        "geometry_source": fill.get("sl_source"),
        "gross_pnl": close.get("gross_pnl"),
        "costs": close.get("costs"),
        "net_pnl": net,
        "peak_pnl": close.get("peak_pnl"),
        "maximum_drawdown": close.get("maximum_drawdown"),
        "mfe_price": close.get("peak_favorable_price_move"),
        "mae_price": close.get("adverse_price_move"),
        "giveback_price": close.get("price_giveback"),
        "secured_cash": secured["cash"],
        "secured_stop": secured["stop"],
        "secured_at_utc": secured["at"],
        "exit_reason": close.get("reason"),
        "attribution_source": close.get("attribution_source"),
        "holding_seconds": close.get("position_holding_seconds"),
        "loss_reasons_json": canonical(_loss_reasons(close, proposal, secured)),
        "evidence_ids_json": canonical(evidence),
        "plan_json": canonical(plan),
        "outcome_json": canonical(outcome),
        "source_hash": source_hash,
        "created_at_utc": now,
        "updated_at_utc": now,
    }


def journal_closed_trade(close: dict, proposal: dict | None = None,
                         db_path: Path | str = DEFAULT_DB) -> dict:
    journal = build_journal(close, proposal)
    store = IntelligenceStore(db_path, busy_timeout_ms=5000)
    try:
        store.upsert_trade_journal(journal)
    finally:
        store.db.close()
    return journal


def backfill_day(day: str, db_path: Path | str = DEFAULT_DB) -> int:
    count = 0
    for row in _jsonl(LOG_DIR / f"paper-executions-{day}.jsonl"):
        if row.get("event") != "mt5_execution_closed" or not row.get("fills"):
            continue
        journal_closed_trade(row, db_path=db_path)
        count += 1
    return count
