"""Research-only boundary for native versus external structure decisions.

The MT5 process only publishes immutable, completed-M5 samples.  A supported
Python 3.12/3.13 worker consumes them and runs optional scientific packages.
Nothing produced here is returned to Qwen or to an execution validator.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
STATE_FILE = LOG_DIR / "structure-shadow-state.json"
SCHEMA_VERSION = "structure-shadow/v1"
HORIZON_BARS = 3
NEUTRAL_ATR_FRACTION = 0.10
_PUBLISHED: set[str] = set()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bar_time(bar: dict) -> str:
    value = bar.get(
        "close_time_utc",
        bar.get("open_time_utc", bar.get("time_utc", bar.get("time", bar.get("timestamp", "")))),
    )
    return str(value)


def _sample_id(symbol: str, timeframe: str, bar: dict) -> str:
    identity = f"{symbol}|{timeframe}|{_bar_time(bar)}|{bar.get('close')}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def native_decision(context: dict) -> str:
    """Freeze one deterministic native call for later fair comparison."""
    htf = str(context.get("htf_bias", "mixed")).lower()
    if htf in {"bullish", "bearish"}:
        return htf
    m5 = str((context.get("trends") or {}).get("M5", "mixed")).lower()
    return m5 if m5 in {"bullish", "bearish"} else "mixed"


def publish_sample(symbol: str, bars: list[dict], atr: float, native_context: dict,
                   log_dir: Path | None = None) -> dict:
    """Append one sample per completed M5 candle; safe to call every cycle."""
    log_dir = log_dir or LOG_DIR
    if not bars:
        return {"status": "no_data", "execution_authority": False}
    sample_id = _sample_id(symbol, "M5", bars[-1])
    if sample_id in _PUBLISHED:
        return {"status": "already_published", "sample_id": sample_id,
                "execution_authority": False}
    _PUBLISHED.add(sample_id)
    row = {
        "schema_version": SCHEMA_VERSION,
        "record_type": "sample",
        "sample_id": sample_id,
        "observed_at_utc": _utc_now(),
        "symbol": symbol,
        "timeframe": "M5",
        "closed_bar_time": _bar_time(bars[-1]),
        "origin_close": float(bars[-1]["close"]),
        "atr": float(atr),
        "native": {
            "direction": native_decision(native_context),
            "htf_bias": native_context.get("htf_bias", "mixed"),
            "m5_trend": (native_context.get("trends") or {}).get("M5", "unknown"),
            "alignment": native_context.get("alignment", "mixed"),
        },
        "bars": bars[-120:],
        "execution_authority": False,
    }
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"structure-shadow-input-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return {"status": "published", "sample_id": sample_id,
            "native_direction": row["native"]["direction"],
            "execution_authority": False}


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"), ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def realised_direction(origin: float, future: float, atr: float) -> str:
    change = future - origin
    threshold = max(abs(atr) * NEUTRAL_ATR_FRACTION, 1e-12)
    if change > threshold:
        return "bullish"
    if change < -threshold:
        return "bearish"
    return "mixed"


def is_correct(decision: str, realised: str) -> bool:
    return decision == realised


def build_summary(decisions: list[dict], resolutions: list[dict]) -> dict:
    actors: dict[str, dict[str, int]] = {}
    for row in resolutions:
        realised = row["realised_direction"]
        calls = {"native": row["native_direction"], "external_consensus": row["external_direction"]}
        calls.update(row.get("provider_directions") or {})
        for actor, decision in calls.items():
            stats = actors.setdefault(actor, {"resolved": 0, "correct": 0, "directional": 0})
            stats["resolved"] += 1
            stats["correct"] += int(is_correct(decision, realised))
            stats["directional"] += int(decision in {"bullish", "bearish"})
    for stats in actors.values():
        stats["accuracy"] = round(stats["correct"] / stats["resolved"], 4) if stats["resolved"] else None
    latest = decisions[-1] if decisions else None
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at_utc": _utc_now(),
        "decision_samples": len(decisions),
        "resolved_samples": len(resolutions),
        "pending_samples": max(0, len(decisions) - len(resolutions)),
        "actors": actors,
        "latest": latest,
        "execution_authority": False,
    }
