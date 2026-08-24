"""Versioned boundary between the observer and the trading processes."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


CONTRACT_VERSION = "qwen-intraday-observer/v1"
BACKEND_DIR = Path(__file__).resolve().parents[1]
STATE_FILE = BACKEND_DIR / "cache" / "intraday-observer-state.json"
MAX_TRADER_AGE_SECONDS = 45 * 60


def _parse_utc(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_state(path: Path | str = STATE_FILE) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(state: dict, path: Path | str = STATE_FILE) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(state, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, target)


def read_for_trader(
    symbol: str,
    *,
    now: datetime | None = None,
    path: Path | str = STATE_FILE,
) -> dict:
    """Return a small validated notebook, never raw observer internals.

    Invalid, stale, cross-symbol, and future-dated state fails closed.  Trading
    code can therefore consume this function without knowing how the observer
    is implemented.
    """
    state = read_state(path)
    if state.get("contract_version") != CONTRACT_VERSION:
        return {"status": "unavailable", "reason": "contract_mismatch"}
    if str(state.get("symbol") or "").upper() != str(symbol).upper():
        return {"status": "unavailable", "reason": "symbol_mismatch"}
    generated = _parse_utc(state.get("generated_at_utc"))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if generated is None:
        return {"status": "unavailable", "reason": "missing_timestamp"}
    age = (now - generated).total_seconds()
    if age < -5:
        return {"status": "unavailable", "reason": "future_timestamp"}
    if age > MAX_TRADER_AGE_SECONDS:
        return {"status": "stale", "age_seconds": round(age, 1)}

    deterministic = state.get("deterministic") or {}
    qwen = state.get("qwen_analysis") or {}
    return {
        "status": "ready",
        "contract_version": CONTRACT_VERSION,
        "execution_authority": False,
        "generated_at_utc": state.get("generated_at_utc"),
        "age_seconds": round(max(0.0, age), 1),
        "episode_id": deterministic.get("episode_id"),
        "today_tape": deterministic.get("today_tape"),
        "structure_sequence": (deterministic.get("structure") or {}).get("sequence", [])[-10:],
        "verified_levels": (deterministic.get("levels") or [])[:8],
        "market_story": qwen.get("market_story"),
        "structure_read": qwen.get("structure_read"),
        "level_reads": (qwen.get("level_reads") or [])[:6],
        "prior_view_review": qwen.get("prior_view_review"),
        "next_focus": qwen.get("next_focus"),
    }
