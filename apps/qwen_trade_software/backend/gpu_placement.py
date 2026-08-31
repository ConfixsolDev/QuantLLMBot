"""GPU-only placement policy shared by every local Qwen caller."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable


OLLAMA_PS = "http://127.0.0.1:11434/api/ps"
MIN_VRAM_SHARE = 0.90


class GpuPlacementRequired(RuntimeError):
    """Raised before inference when Qwen is not fully resident in VRAM."""


def classify_residency(
    running: list[dict], model: str, *, min_vram_share: float = MIN_VRAM_SHARE
) -> dict:
    # 2026-08-28: matched only row["name"]. If an Ollama version keys the
    # running-process entry as "model" instead of (or in addition to) "name",
    # every row here would look nameless and this always reports "unloaded"
    # even while the model is genuinely resident on GPU. Check both fields;
    # this can only widen a match, never falsely narrow one.
    base_name = model.split(":")[0].strip().lower()

    def _row_name(row: dict) -> str:
        return str(row.get("name") or row.get("model") or "").strip()

    resident = next(
        (
            row
            for row in running
            if _row_name(row).lower() == model.strip().lower()
            or _row_name(row).lower().startswith(base_name)
        ),
        None,
    )
    if not resident:
        return {"state": "unloaded", "vram_share": None, "detail": "not resident"}

    size = float(resident.get("size") or 0)
    vram = float(resident.get("size_vram") or 0)
    share = (vram / size) if size > 0 else 0.0
    if vram <= 0:
        state = "cpu"
    elif share >= min_vram_share:
        state = "gpu"
    else:
        state = "mixed"
    return {
        "state": state,
        "vram_share": round(share, 3),
        "detail": f"{vram/1e9:.1f}GB of {size/1e9:.1f}GB in VRAM",
    }


def gpu_residency(
    model: str,
    *,
    opener: Callable = urllib.request.urlopen,
    endpoint: str = OLLAMA_PS,
) -> dict:
    """Return Ollama placement without raising on a failed probe."""
    try:
        with opener(endpoint, timeout=5) as response:
            running = json.loads(response.read().decode("utf-8")).get("models", [])
    except Exception as error:
        return {"state": "unknown", "vram_share": None, "detail": str(error)}
    return classify_residency(running, model)


def require_gpu_residency(
    model: str,
    *,
    owner: str,
    opener: Callable = urllib.request.urlopen,
) -> dict:
    """Fail closed before inference unless the entire model is in VRAM."""
    residency = gpu_residency(model, opener=opener)
    if residency["state"] != "gpu":
        raise GpuPlacementRequired(
            f"Qwen GPU-only gate blocked {owner}: {model} is "
            f"{residency['state']} ({residency['detail']})"
        )
    return residency


def recovery_action(*, desired_loaded: bool, state: str) -> str:
    """Return the supervisor action for the current placement state."""
    if not desired_loaded or state == "gpu":
        return "none"
    if state in {"cpu", "mixed"}:
        return "restart_ollama"
    if state == "unloaded":
        return "warm_model"
    return "none"
