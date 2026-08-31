"""Low-priority asynchronous Qwen postmortems for factual SQLite journals."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import time
from pathlib import Path

from storage_factory import create_intelligence_store
from review_shared import ollama_generate
from runtime_config import model_for_role

APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "cache" / "market-intelligence.sqlite3"
LOG_FILE = APP_DIR / "logs" / "trade-journal-worker.log"
JOURNAL_MODEL = model_for_role("management")

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "entry_assessment": {"type": "string"},
        "management_assessment": {"type": "string"},
        "what_worked": {"type": "array", "items": {"type": "string"}},
        "what_failed": {"type": "array", "items": {"type": "string"}},
        "likely_loss_reasons": {"type": "array", "items": {"type": "string"}},
        "lesson": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 1, "maximum": 100},
    },
    "required": [
        "summary", "entry_assessment", "management_assessment", "what_worked",
        "what_failed", "likely_loss_reasons", "lesson", "confidence",
    ],
    "additionalProperties": False,
}

LOSS_REASON_TEXT = {
    "structural_geometry_rejected_fallback": "Structural geometry was rejected and fallback risk geometry was used.",
    "favorable_excursion_not_secured": "The trade had favorable excursion but no profit was secured before reversal.",
    "entry_edge_mismatch": "The executed entry differed materially from the recorded optimal entry edge.",
    "broker_stop_without_manager_exit": "The broker stop closed the trade without an earlier manager exit.",
    "market_thesis_failed": "Price invalidated the recorded trade thesis.",
}


def _facts(row: dict) -> dict:
    keep = (
        "proposal_id", "execution_id", "symbol", "side", "result",
        "idea_summary", "idea_reason", "confidence", "structure_timeframe",
        "entry_time_utc", "exit_time_utc", "entry_price", "exit_price", "volume",
        "initial_stop", "initial_target", "geometry_source", "gross_pnl", "costs",
        "net_pnl", "peak_pnl", "maximum_drawdown", "mfe_price", "mae_price",
        "giveback_price", "secured_cash", "secured_stop", "secured_at_utc",
        "exit_reason", "holding_seconds", "loss_reasons_json", "evidence_ids_json",
        "entry_evidence_json",
    )
    return {key: row.get(key) for key in keep}


def _json_list(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _loss_reason_texts(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    if not isinstance(value, list):
        return []
    output = []
    for item in value:
        code = item.get("code") if isinstance(item, dict) else item
        code = str(code or "").strip()
        if code:
            output.append(LOSS_REASON_TEXT.get(code, code.replace("_", " ")))
    return output


def _normalize_analysis(row: dict, analysis: object) -> dict:
    """Keep Qwen commentary subordinate to immutable execution facts."""
    if not isinstance(analysis, dict):
        analysis = {}
    result = str(row.get("result") or "").lower()
    factual_reasons = _loss_reason_texts(row.get("loss_reasons_json"))

    normalized = {
        "summary": str(analysis.get("summary") or "Closed trade reviewed from recorded execution facts."),
        "entry_assessment": str(analysis.get("entry_assessment") or "Entry quality is not established beyond the recorded facts."),
        "management_assessment": str(analysis.get("management_assessment") or "Management assessment is limited to recorded protection and exit events."),
        "what_worked": _json_list(analysis.get("what_worked")),
        "what_failed": _json_list(analysis.get("what_failed")),
        "likely_loss_reasons": _json_list(analysis.get("likely_loss_reasons")),
        "lesson": str(analysis.get("lesson") or "Preserve broker facts and only infer lessons supported by recorded evidence."),
        "confidence": max(1, min(100, int(analysis.get("confidence") or 50))),
    }
    if row.get("fills") or row.get("entry_time_utc"):
        for key in ("summary", "entry_assessment", "management_assessment"):
            if "not_traded" in normalized[key].lower() or "not traded" in normalized[key].lower():
                normalized[key] = "The trade was executed; assessment is limited to the recorded fill and lifecycle facts."
    if result == "loss":
        # Deterministic Python findings are mandatory; Qwen may add supported context,
        # but it cannot omit or overrule them.
        for reason in factual_reasons:
            if reason not in normalized["likely_loss_reasons"]:
                normalized["likely_loss_reasons"].append(reason)
            if reason not in normalized["what_failed"]:
                normalized["what_failed"].append(reason)
    else:
        normalized["likely_loss_reasons"] = []
    return normalized


def analyze_one(store: IntelligenceStore, row: dict, model: str = JOURNAL_MODEL) -> dict:
    prompt = (
        "Analyze this closed XAUUSD trade journal using only supplied facts. "
        "Explain what happened, entry quality, management, what worked, what failed, "
        "and evidence-based likely loss reasons. For a winner, likely_loss_reasons "
        "must be empty. The trade was executed whenever entry_time_utc is present. "
        "Every deterministic loss_reasons_json item is mandatory in both what_failed "
        "and likely_loss_reasons for a loss. Never contradict, remove, or reinterpret "
        "broker facts or deterministic findings. Do not invent candles, news, or "
        "causation. Return JSON only.\n\n"
        "TRADE JOURNAL FACTS:\n" + json.dumps(_facts(row), separators=(",", ":"))
    )
    result = ollama_generate(
        prompt, timeout=None, num_predict=700, num_ctx=4096,
        format_schema=SCHEMA, model=model,
    )
    # Ollama can return a truncated JSON fragment with ok=True while
    # reporting done=False. Treat that as an incomplete generation so the
    # journal remains pending for a retry instead of raising a misleading
    # JSONDecodeError (or recording partial commentary as complete).
    if "done" in result and result.get("done") is not True:
        raise ValueError(
            "Qwen journal response incomplete: "
            f"done={result.get('done')!r} done_reason={result.get('done_reason')!r}"
        )
    response_text = result.get("response") or result.get("response_text") or "{}"
    try:
        parsed_response = json.loads(response_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("Qwen journal response was not valid JSON") from exc
    analysis = _normalize_analysis(row, parsed_response)
    store.update_trade_qwen_analysis(row["proposal_id"], analysis, "complete", model)
    return analysis


def run(db_path: Path, interval: float, once: bool = False) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE, when="midnight", encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    store = create_intelligence_store(db_path)
    while True:
        rows = store.pending_trade_journals(limit=1)
        if not rows:
            if once:
                return
            time.sleep(max(1.0, interval))
            continue
        row = rows[0]
        try:
            analyze_one(store, row)
            logging.info("Qwen journal complete proposal=%s", row["proposal_id"])
        except Exception:
            logging.exception("Qwen journal failed proposal=%s", row["proposal_id"])
            try:
                store.update_trade_qwen_analysis(
                    row["proposal_id"], None, "retry", JOURNAL_MODEL
                )
            except Exception:
                # A failed journal analysis must never terminate the worker;
                # leave the row pending for the next process cycle.
                logging.exception("Qwen journal retry-state update failed proposal=%s", row["proposal_id"])
            time.sleep(max(5.0, interval))
        if once:
            return
        time.sleep(max(1.0, interval))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    run(args.db, args.interval, args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
