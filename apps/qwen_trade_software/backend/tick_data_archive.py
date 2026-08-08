"""Permanent daily tick-data archive for learning and long-term analysis.

In this system **tick data** means each timed observation the engine records:
price (bid/ask), market context, Qwen request/response, and the decision at
that moment — one JSON line per tick of the process, not MT5 order tickets.

Every record is appended to BOTH:
  - hot runtime log: backend/logs/{name}-YYYY-MM-DD.jsonl
  - permanent archive: model_training/tick_data/YYYY-MM-DD/{name}.jsonl

RETENTION: tick_data/ is NEVER auto-deleted. Use for 30, 60, 90+ day analysis.
Raw MT5 tick stream also lives in cache/market_context.sqlite3 (ticks table).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
TICK_DATA_ROOT = APP_DIR.parents[2] / "model_training" / "tick_data"

ARCHIVE_FILES: dict[str, str] = {
    "paper-proposals": "paper-proposals.jsonl",
    "paper-executions": "paper-executions.jsonl",
    "reviews": "reviews.jsonl",
    "qwen-decisions": "qwen-decisions.jsonl",
    "qwen-io": "qwen-io.jsonl",
    "mt5-io": "mt5-io.jsonl",
    "day-plans": "day-plans.jsonl",
    "session-plans": "session-plans.jsonl",
    "hourly-updates": "hourly-updates.jsonl",
    "session-verdicts": "session-verdicts.jsonl",
}

_DAY_DIR_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _day(day: date | None = None) -> date:
    return day or datetime.now().date()


def day_dir(day: date | None = None) -> Path:
    folder = TICK_DATA_ROOT / _day(day).isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def runtime_log_path(base_name: str, day: date | None = None) -> Path:
    return LOG_DIR / f"{base_name}-{_day(day):%Y-%m-%d}.jsonl"


def archive_log_path(base_name: str, day: date | None = None) -> Path:
    filename = ARCHIVE_FILES.get(base_name)
    if not filename:
        raise KeyError(f"Unknown tick archive base: {base_name}")
    return day_dir(day) / filename


def append_tick_record(base_name: str, record: dict, *, day: date | None = None) -> None:
    """Append one tick observation to today's runtime log and permanent archive."""
    line = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    day = _day(day)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with runtime_log_path(base_name, day).open("a", encoding="utf-8") as stream:
        stream.write(line)
    with archive_log_path(base_name, day).open("a", encoding="utf-8") as stream:
        stream.write(line)


def append_qwen_decision(
    *,
    decision_type: str,
    symbol: str | None,
    price: float | None,
    prompt_text: str | None,
    raw_response: str,
    parsed: dict,
    model: str,
    duration_ns: int | None = None,
    mt5_position_id: int | None = None,
    proposal_id: str | None = None,
    context: dict | None = None,
) -> None:
    """One decision tick: price + full Qwen in/out for decision-tree analysis."""
    record = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_type": decision_type,
        "symbol": symbol,
        "price": price,
        "mt5_position_id": mt5_position_id,
        "proposal_id": proposal_id,
        "model": model,
        "duration_ns": duration_ns,
        "prompt_text": prompt_text,
        "raw_response": raw_response,
        "parsed": parsed,
    }
    if context:
        record["context"] = context
    append_tick_record("qwen-decisions", record)


def _line_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                count += 1
    return count


def sync_day_to_archive(base_name: str, day: date) -> bool:
    runtime = runtime_log_path(base_name, day)
    if not runtime.exists():
        return False
    archive = archive_log_path(base_name, day)
    runtime_lines = runtime.read_text(encoding="utf-8").splitlines()
    runtime_lines = [line for line in runtime_lines if line.strip()]
    if not runtime_lines:
        return False
    archive_lines: list[str] = []
    if archive.exists():
        archive_lines = [
            line for line in archive.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
    if len(archive_lines) >= len(runtime_lines):
        return False
    if not archive_lines:
        shutil.copy2(runtime, archive)
        logging.info("Archived full %s for %s (%d ticks)", base_name, day, len(runtime_lines))
        return True
    with archive.open("a", encoding="utf-8") as stream:
        for line in runtime_lines[len(archive_lines) :]:
            stream.write(line + "\n")
    logging.info(
        "Appended %d %s tick(s) to archive for %s",
        len(runtime_lines) - len(archive_lines),
        base_name,
        day,
    )
    return True


def sync_all_archives(*, days_back: int = 365) -> list[str]:
    """Ensure tick_data has every runtime log day (call on software startup)."""
    TICK_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    synced: list[str] = []
    today = datetime.now().date()
    for offset in range(days_back + 1):
        day = today - timedelta(days=offset)
        for base_name in ARCHIVE_FILES:
            if sync_day_to_archive(base_name, day):
                synced.append(f"{day.isoformat()}/{base_name}")
    for base_name in ARCHIVE_FILES:
        for runtime in sorted(LOG_DIR.glob(f"{base_name}-*.jsonl")):
            suffix = runtime.stem.replace(f"{base_name}-", "", 1)
            try:
                day = datetime.strptime(suffix, "%Y-%m-%d").date()
            except ValueError:
                continue
            if sync_day_to_archive(base_name, day):
                synced.append(f"{day.isoformat()}/{base_name}")
    if synced:
        logging.info("Tick data archive sync: %s", ", ".join(synced))
    return synced


def write_day_manifest(day: date | None = None) -> Path:
    day = _day(day)
    folder = day_dir(day)
    manifest = {
        "date": day.isoformat(),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "retention": "permanent — never auto-deleted",
        "files": {},
    }
    for base_name, filename in ARCHIVE_FILES.items():
        path = folder / filename
        manifest["files"][filename] = {
            "lines": _line_count(path),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def write_all_day_manifests() -> int:
    if not TICK_DATA_ROOT.exists():
        return 0
    count = 0
    for folder in sorted(TICK_DATA_ROOT.iterdir()):
        if not folder.is_dir() or not _DAY_DIR_PATTERN.match(folder.name):
            continue
        day = datetime.strptime(folder.name, "%Y-%m-%d").date()
        write_day_manifest(day)
        count += 1
    return count
