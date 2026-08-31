"""Persist level IDs Qwen actually cited so the dashboard can rank them."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
QUALIFIED_LEVELS_PATH = APP_DIR / "qualified-levels.json"


def load_qualified_level_ids() -> set[str]:
    try:
        from runtime_store import live_runtime_store
        runtime = live_runtime_store()
        if runtime is not None:
            payload = runtime.get_state(QUALIFIED_LEVELS_PATH)
            if isinstance(payload, dict):
                return {str(item) for item in (payload.get("ids") or []) if item}
    except Exception:
        pass
    try:
        payload = json.loads(QUALIFIED_LEVELS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return set()
    ids = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list):
        return set()
    return {str(item) for item in ids if item}


def remember_qualified_level_ids(ids) -> list[str]:
    """Merge newly cited level IDs. Returns the sorted full set."""
    current = load_qualified_level_ids()
    added = [str(item) for item in (ids or []) if item]
    if added:
        current.update(added)
        payload = {"ids": sorted(current),
                   "updated_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            from runtime_store import live_runtime_store
            runtime = live_runtime_store()
        except Exception:
            runtime = None
        if runtime is not None:
            runtime.put_state(QUALIFIED_LEVELS_PATH, payload, owner="qualified_levels")
        else:
            QUALIFIED_LEVELS_PATH.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return sorted(current)
