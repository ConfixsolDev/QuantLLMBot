"""Shared infrastructure for the entry-decision and trade-management processes.

2026-08-06 split: reviewer.py used to own both trade entry and trade
management in one file/process. They're being split into two independent
processes -- entry_decision stays in reviewer.py, management moves to
trade_management.py -- because they increasingly need separate knowledge
bases and, eventually, separate trained skills/models. This module holds
exactly the pieces both genuinely need: the Qwen model call, MT5 connection
setup, the review-ticket file (read/written by both), small dashboard-facing
normalizers used by both processes' dashboard-state output, the ownership
check used by both for live MT5 position filtering, and tiny JSON read/write
helpers used for the cross-process dashboard-state handoff (see
dashboard_state.py-style usage in each caller). Nothing trading-decision-
specific lives here on purpose -- if a function only matters to one side,
it belongs in that side's own file, not here.
"""

import json
import logging
import os
import time
# Module scope, not function scope. unload_stale_models() and the /api/ps probe
# both call urllib.request but only _ollama_generate_raw imported it -- and a
# local import binds nothing outside its own function. So every startup logged
# "could not query Ollama for resident models: name 'urllib' is not defined"
# and returned early, meaning the eviction that stops two trading models
# sharing VRAM never actually ran. The guard existed and had never once fired.
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5

from market_context_cache import DEFAULT_STORE_ROOT, model_generation_lock
from runtime_config import (
    ACTIVE_QWEN_MODEL, DEFAULT_QWEN_MODEL, PRIMARY_MARKET_SYMBOL,
    configured_models, model_for_role,
)


# Model version. See model_training/CURRICULUM_AND_DATA_PREP.md 3.0.
#
# v004 is the active rollback target. v005's live behavior was not acceptable:
# it emitted zero confidence and required an unsafe runtime floor to trade.
#
# Switching model invalidates the qualification certificate (keyed on
# model_digest). The cache child still starts with --no-qwen, but it now
# flushes the stale certificate and runs one qualifying cycle automatically.
# Manual fallback if that cycle fails repeatedly:
#
#     ollama list | grep qwen-trading-v004
#     py -3 market_context_cache.py --once
#
# runtime_config is the single source of truth. The cache and all model callers
# import the same resolved value, so promotion requires one constant change.
DEFAULT_MODEL = DEFAULT_QWEN_MODEL  # compatibility for existing imports
MODEL = ACTIVE_QWEN_MODEL
OLLAMA_GENERATE = "http://127.0.0.1:11434/api/generate"
OLLAMA_PS = "http://127.0.0.1:11434/api/ps"

# Offload every layer to the GPU. 999 is the idiomatic "all layers" value for
# Ollama's num_gpu -- it clamps to the model's actual layer count.
#
# 2026-08-12 -- why this is not optional
# --------------------------------------
# The payload previously carried no placement option at all, so Ollama decided
# on its own. When VRAM was unavailable at load time it fell back to CPU
# silently, and the system carried on as though nothing had happened:
#
#     entry decision latency on GPU    13-33s
#     entry decision latency on CPU    190-455s
#     proposal TTL                     60s
#
# Every decision then arrived after the proposal it belonged to had already
# expired. 106 proposals produced 4 fills. Nothing errored, nothing alarmed --
# the system did correct work far too slowly to use, which is a worse failure
# than a crash because it looks like operation.
FORCE_GPU_LAYERS = int(os.environ.get("QWEN_NUM_GPU_LAYERS", "999"))

# Below this share of the model resident in VRAM, treat the load as CPU or
# mixed. Ollama reports size_vram against total size; a genuine full-GPU load
# sits at ~1.0, and anything materially short of that is partly on CPU and
# will not meet the decision deadline.
MIN_VRAM_SHARE = 0.90
QWEN_MAGIC = 26072401
QWEN_COMMENT_PREFIX = "QWEN_"
# XAUUSD typically quiets Friday ~21:00 UTC through Sunday ~22:00 UTC. When the
# calendar says closed, or MT5 stops producing fresh ticks, unload Qwen from
# Ollama and skip model calls until the market is quoting again.
GOLD_SYMBOL = PRIMARY_MARKET_SYMBOL  # compatibility name; configured primary market
MAX_QUOTE_AGE_MS_MARKET_OPEN = 180_000
MODEL_RESIDENCY_FILE = None  # set after APP_DIR below
# Both processes read the same skill/contract text off disk (entry reads
# core_skill.md + the entry contract; management reads the management
# contract via build_management_prompt), so the root is shared here rather
# than each file hardcoding its own copy of DEFAULT_STORE_ROOT.
STORE_ROOT = DEFAULT_STORE_ROOT

APP_DIR = Path(__file__).resolve().parent
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
REVIEW_TICKETS_FILE = APP_DIR / "review-tickets.json"
MODEL_RESIDENCY_FILE = APP_DIR / "model-residency.json"
DEFAULT_TERMINAL = r"C:\Program Files\MetaTrader 5\terminal64.exe"

# 2026-08-06 split: reviewer.py (entry-decision) and trade_management.py
# (management) are now separate processes with no shared memory, so the
# dashboard state that used to be one in-process dict is now two files --
# each process owns writing its own file and only reads the other's.
# DashboardHandler (still hosted in reviewer.py) merges both into the one
# /snapshot shape the GoldFlow Plan View frontend already expects.
ENTRY_STATE_FILE = APP_DIR / "entry-dashboard-state.json"
MANAGEMENT_STATE_FILE = APP_DIR / "management-dashboard-state.json"
PROTECTION_STATE_FILE = APP_DIR / "profit-protection-state.json"
PLANNER_STATE_FILE = APP_DIR / "planner-state.json"

DEFAULT_ENTRY_QWEN_STATE = {
    "bias": "Waiting for review",
    "confidence": 50,
    "summary": "The local Qwen entry process is preparing the first deal sheet.",
    "invalidation": "No active thesis.",
    "updated_at": "",
}

# Management's own state additionally carries "qwen_management" (its most
# recent in-trade review) separately from entry's "qwen" thesis -- reviewer.py
# picks whichever one is currently relevant (open Qwen position or not) when
# it builds the merged /snapshot payload.
DEFAULT_MANAGEMENT_STATE = {
    "connected": False,
    "model": MODEL,
    "model_status": "Starting",
    "symbol": PRIMARY_MARKET_SYMBOL,
    "price": 0.0,
    "change": 0.0,
    "timeframe": "M1",
    "levels": {},
    "market_context": {},
    "positions": [],
    "today": {
        "net_profit": 0.0,
        "baskets": 0,
        "deals": 0,
        "median_hold_seconds": 0,
        "win_rate": 0,
    },
    "context_cache": {},
    "qwen_management": {
        "bias": "Waiting for review",
        "confidence": 50,
        "summary": "The local trade-management process is starting up.",
        "invalidation": "No open Qwen position under management.",
        "updated_at": "",
    },
}


def _dated_log_path(base_name: str) -> Path:
    """Today's log file, e.g. paper-executions-2026-08-06.jsonl.

    Computed fresh on every call (never cached) so a long-running process
    rolls over to a new file automatically at local midnight, the same way
    reviews-*.jsonl already rotates by date.
    """
    return LOG_DIR / f"{base_name}-{datetime.now():%Y-%m-%d}.jsonl"


def _dated_log_files(base_name: str, days_back: int = 1) -> list[Path]:
    """Existing dated files for `base_name`, today first then earlier days.

    A position opened just before midnight can still be under management
    just after it, so lookups by id need to see yesterday's file too, not
    only today's.
    """
    today = datetime.now().date()
    paths = []
    for offset in range(days_back + 1):
        day = today - timedelta(days=offset)
        path = LOG_DIR / f"{base_name}-{day:%Y-%m-%d}.jsonl"
        if path.exists():
            paths.append(path)
    return paths


def load_review_tickets() -> set:
    try:
        return {int(ticket) for ticket in json.loads(REVIEW_TICKETS_FILE.read_text())}
    except (FileNotFoundError, ValueError, TypeError):
        return set()


def save_review_tickets(tickets: set) -> None:
    REVIEW_TICKETS_FILE.write_text(
        json.dumps(sorted(tickets), separators=(",", ":")),
        encoding="utf-8",
    )


def read_json_safe(path: Path, default: dict) -> dict:
    """Read a shared JSON state file written by the other process.

    Returns `default` (a fresh copy, never the caller's own default object)
    on anything short of a clean read -- missing file (other process hasn't
    written its first cycle yet), a write caught mid-flight, or corruption.
    Never raises; the dashboard and the soft pre-checks that use this should
    degrade gracefully, not crash a process over the other process's file.
    """
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return json.loads(json.dumps(default))


def write_json_atomic(path: Path, data: dict) -> None:
    """Write JSON so a concurrent reader in the other process never sees a
    half-written file. Write to a temp file in the same directory, then
    rename -- rename is atomic on the same volume on Windows and POSIX."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(data, separators=(",", ":")), encoding="utf-8"
    )
    os.replace(tmp_path, path)


def _ollama_generate_raw(
    prompt: str, keep_alive=-1, timeout=45, num_predict=160, num_ctx=4096,
    format_schema: dict | None = None,
    model: str | None = None,
) -> dict:
    import urllib.request

    payload = json.dumps(
        {
            "model": model or MODEL,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
            "format": format_schema or ("json" if prompt else None),
            "options": {
                "temperature": 0,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                # Put every layer on the GPU. See FORCE_GPU_LAYERS.
                "num_gpu": FORCE_GPU_LAYERS,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_GENERATE,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with model_generation_lock():
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def ollama_generate(
    prompt: str, keep_alive=-1, timeout=45, num_predict=160, num_ctx=4096,
    format_schema: dict | None = None,
    model: str | None = None,
) -> dict:
    # Empty-prompt warm/unload paths use _ollama_generate_raw / warm_model /
    # unload_model. Real decision calls must not run while gold is not quoting.
    if prompt:
        market = gold_market_open()
        if not market.get("open"):
            raise RuntimeError(
                f"Qwen call blocked; market closed ({market.get('reason')})"
            )

    from io_performance_log import log_qwen_generate

    selected_model = model or MODEL
    return log_qwen_generate(
        model=selected_model,
        prompt=prompt,
        num_ctx=num_ctx,
        num_predict=num_predict,
        timeout=timeout,
        format_schema=format_schema,
        caller="review_shared.ollama_generate",
        fn=lambda: _ollama_generate_raw(
            prompt,
            keep_alive=keep_alive,
            timeout=timeout,
            num_predict=num_predict,
            num_ctx=num_ctx,
            format_schema=format_schema,
            model=selected_model,
        ),
    )


def gpu_residency(model: str = MODEL) -> dict:
    """Where the model actually sits right now, per Ollama's own accounting.

    Returns {"state": "gpu"|"mixed"|"cpu"|"unloaded"|"unknown", "vram_share":
    float|None, "detail": str}. Never raises -- a residency probe must not be
    able to stop trading, only to describe it.
    """
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=5) as response:
            running = json.loads(response.read().decode("utf-8")).get("models", [])
    except Exception as error:
        return {"state": "unknown", "vram_share": None, "detail": str(error)}

    resident = next(
        (
            row for row in running
            if row.get("name") == model
            or str(row.get("name") or "").startswith(model.split(":")[0])
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
    elif share >= MIN_VRAM_SHARE:
        state = "gpu"
    else:
        state = "mixed"
    return {
        "state": state,
        "vram_share": round(share, 3),
        "detail": f"{vram/1e9:.1f}GB of {size/1e9:.1f}GB in VRAM",
    }


def require_gpu(owner: str = "") -> dict:
    """Assert the model is on the GPU. Alarm loudly when it is not.

    2026-08-12 -- why this is separate from forcing num_gpu
    -------------------------------------------------------
    Setting num_gpu asks for full GPU placement, but Ollama can still fall back
    -- another model squatting on VRAM, a driver reset, a smaller card than the
    model needs. Asking is not the same as verifying.

    On CPU this system does not degrade gracefully; it stops functioning while
    appearing to function. Decisions take 190-455s against a 60-second proposal
    TTL, so every answer arrives after the question expired: 106 proposals, 4
    fills, and not one error in the log.

    The alarm is deliberately CRITICAL and names the fix, because the symptom
    (no trades) looks nothing like the cause (model on CPU) unless someone
    thinks to compare decision latency against the TTL.
    """
    residency = gpu_residency()
    state = residency["state"]
    if state == "gpu":
        logging.info(
            "model on GPU%s: %s", f" ({owner})" if owner else "", residency["detail"]
        )
        return residency

    level = logging.error if state in ("cpu", "mixed") else logging.warning
    level(
        "ALARM CRITICAL model:not_on_gpu :: %s is %s (%s). Decisions take "
        "190-455s on CPU against a %ss proposal TTL, so every proposal expires "
        "before its answer arrives -- the system will appear to run and take "
        "almost no trades. Free VRAM (check `ollama ps` for stale models) and "
        "restart.",
        MODEL, state, residency["detail"], 60,
    )
    return residency


def warm_model() -> None:
    ollama_generate("", keep_alive=-1)
    residency = require_gpu("warm_model")
    logging.info(
        "Qwen model loaded and pinned: %s (%s)", MODEL, residency["state"]
    )


def unload_model() -> None:
    """Drop the trading model from Ollama memory (keep_alive=0)."""
    _ollama_generate_raw("", keep_alive=0, timeout=60, num_predict=1, num_ctx=512)
    logging.info("Qwen model unloaded from Ollama: %s", MODEL)


def unload_stale_models(keep: str | list[str] | tuple[str, ...] | None = None) -> list[str]:
    """Evict any resident qwen-trading-* model that is not the active one.

    2026-08-10 INCIDENT. warm_model() pins with keep_alive=-1, which Ollama
    reports as expires_at in the year 2318 -- i.e. never. unload_model() only
    ever unloads MODEL, so when MODEL was switched v003 -> v004 nothing evicted
    v003. Both sat resident at ~11.2 GB each, Ollama ran out of VRAM, and the
    warmup call started returning HTTP 500. Qualification could not complete and
    the whole trading chain stayed down.

    Switching model version is exactly when this bites, because that is the only
    time two trading models are ever wanted at once -- and they never are.

    Called on startup so a version switch cannot silently double VRAM.
    """
    keep_models = set(
        configured_models()
        if keep is None
        else ([keep] if isinstance(keep, str) else keep)
    )
    evicted: list[str] = []
    try:
        with urllib.request.urlopen(OLLAMA_PS, timeout=10) as response:
            running = json.loads(response.read().decode("utf-8")).get("models", [])
    except Exception as error:
        logging.warning("could not query Ollama for resident models: %s", error)
        return evicted

    for row in running:
        name = str(row.get("name") or row.get("model") or "")
        if not name or name in keep_models:
            continue
        if "qwen-trading" not in name:
            continue  # never touch models this system did not load
        try:
            request = urllib.request.Request(
                OLLAMA_GENERATE,
                data=json.dumps({
                    "model": name, "prompt": "", "stream": False, "keep_alive": 0,
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=60):
                pass
            evicted.append(name)
            logging.info(
                "evicted stale resident model %s (configured models are %s)",
                name, sorted(keep_models),
            )
        except Exception as error:
            logging.warning("failed to evict stale model %s: %s", name, error)
    return evicted


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def calendar_gold_market_open(now: datetime | None = None) -> bool:
    """Broker-style XAUUSD weekend/daily close window (UTC)."""
    moment = now or _utc_now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    weekday = moment.weekday()  # Mon=0 … Sun=6
    hour = moment.hour
    if weekday == 5:
        return False
    if weekday == 6:
        return hour >= 22
    if weekday == 4 and hour >= 21:
        return False
    return True


def mt5_quote_is_fresh(
    symbol: str = GOLD_SYMBOL,
    *,
    max_age_ms: int = MAX_QUOTE_AGE_MS_MARKET_OPEN,
    terminal: str = DEFAULT_TERMINAL,
) -> tuple[bool, str]:
    """True when MT5 has a recent tick — ground truth for 'price is changing'."""
    initialized = mt5.initialize(path=terminal) or mt5.initialize()
    if not initialized:
        return False, f"mt5_unavailable:{mt5.last_error()}"
    try:
        # A newly attached process can receive the terminal's last cached tick
        # for a symbol that is not selected, even while the cache process has
        # a live subscription.  Explicit selection requests a current stream
        # before freshness is judged.
        if not mt5.symbol_select(symbol, True):
            return False, f"mt5_symbol_select_failed:{mt5.last_error()}"
        tick = mt5.symbol_info_tick(symbol)
        if tick is None or int(getattr(tick, "time_msc", 0) or 0) <= 0:
            return False, "mt5_no_tick"
        age_ms = int(time.time() * 1000) - int(tick.time_msc)
        if age_ms > max_age_ms:
            return False, f"mt5_tick_stale_{age_ms}ms"
        return True, f"mt5_tick_age_{age_ms}ms"
    finally:
        mt5.shutdown()


def gold_market_open(
    now: datetime | None = None,
    *,
    symbol: str = GOLD_SYMBOL,
) -> dict:
    """Decide whether gold is actively quoting and models may run."""
    moment = now or _utc_now()
    if not calendar_gold_market_open(moment):
        return {
            "open": False,
            "reason": "calendar_closed",
            "checked_at_utc": moment.astimezone(timezone.utc).isoformat(),
        }
    fresh, detail = mt5_quote_is_fresh(symbol)
    if not fresh:
        return {
            "open": False,
            "reason": detail,
            "checked_at_utc": moment.astimezone(timezone.utc).isoformat(),
        }
    return {
        "open": True,
        "reason": detail,
        "checked_at_utc": moment.astimezone(timezone.utc).isoformat(),
    }


def _read_model_residency() -> dict:
    try:
        return json.loads(MODEL_RESIDENCY_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {"state": "unknown"}


def _write_model_residency(state: str, reason: str) -> None:
    MODEL_RESIDENCY_FILE.write_text(
        json.dumps(
            {
                "state": state,
                "reason": reason,
                "model": MODEL,
                "updated_at_utc": _utc_now().isoformat(),
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def sync_model_residency(market: dict | None = None) -> dict:
    """Load Qwen only while gold is quoting; unload and skip calls when closed."""
    market = market if market is not None else gold_market_open()
    desired = "loaded" if market.get("open") else "unloaded"
    current = _read_model_residency().get("state")
    if current == desired:
        return {
            "state": desired,
            "changed": False,
            "market": market,
        }
    try:
        if desired == "loaded":
            warm_model()
        else:
            unload_model()
        _write_model_residency(desired, str(market.get("reason") or desired))
        logging.info(
            "Model residency -> %s (market_open=%s reason=%s)",
            desired,
            market.get("open"),
            market.get("reason"),
        )
        return {"state": desired, "changed": True, "market": market}
    except Exception:
        logging.exception("Model residency sync failed desired=%s", desired)
        return {"state": current or "unknown", "changed": False, "market": market, "error": True}


def normalize_confidence(value, default=0) -> int:
    """Normalize Qwen confidence without inventing qualification when absent."""
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, dict):
        for key in ("score", "value", "level", "confidence"):
            if key in value:
                return normalize_confidence(value[key], default)
        logging.warning("Confidence object has no recognized value: %r", value)
        return default
    if isinstance(value, (int, float)):
        numeric = float(value)
        return max(0, min(100, round(numeric)))

    text = str(value).strip().lower()
    labels = {
        "very low": 50,
        "low": 50,
        "medium": 60,
        "moderate": 60,
        "high": 80,
        "very high": 90,
    }
    if text in labels:
        return labels[text]

    try:
        numeric = float(text.rstrip("%"))
        return max(0, min(100, round(numeric)))
    except ValueError:
        logging.warning("Unrecognized confidence value %r; using %d", value, default)
        return default


def normalize_text(value, default: str) -> str:
    """Convert structured model output into stable text for the dashboard."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def normalize_invalidation(value, execution_plan=None) -> str:
    """Turn structured Qwen invalidation data into concise dashboard language."""
    if isinstance(execution_plan, dict) and execution_plan.get("status") == "wait":
        return "No active paper thesis to invalidate."
    if value is None:
        return "No invalidation returned."
    if isinstance(value, str):
        return value.strip() or "No invalidation returned."

    items = []

    def collect(node):
        if isinstance(node, list):
            for child in node:
                collect(child)
            return
        if isinstance(node, dict):
            if node.get("message"):
                items.append(str(node["message"]))
                return
            level_id = node.get("level_id") or node.get("level")
            if isinstance(level_id, str):
                label = level_id.replace("_", " ").title()
                if node.get("price") is not None:
                    label += f" at {float(node['price']):.3f}"
                items.append(label)
                return
            for child in node.values():
                collect(child)
            return
        if node is not None:
            items.append(str(node))

    collect(value)
    unique = list(dict.fromkeys(item for item in items if item))
    return (
        "Thesis invalidates at: " + "; ".join(unique)
        if unique
        else "No invalidation returned."
    )


def is_qwen_owned(position) -> bool:
    return (
        position.magic == QWEN_MAGIC
        and str(position.comment).startswith(QWEN_COMMENT_PREFIX)
    )


def connect_mt5() -> None:
    if mt5.initialize(path=DEFAULT_TERMINAL) or mt5.initialize():
        return
    raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")


def self_test_market_hours() -> None:
    saturday = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)  # Sat
    sunday_morning = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    sunday_evening = datetime(2026, 8, 9, 22, 30, tzinfo=timezone.utc)
    friday_evening = datetime(2026, 8, 7, 21, 30, tzinfo=timezone.utc)
    monday = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
    assert calendar_gold_market_open(saturday) is False
    assert calendar_gold_market_open(sunday_morning) is False
    assert calendar_gold_market_open(sunday_evening) is True
    assert calendar_gold_market_open(friday_evening) is False
    assert calendar_gold_market_open(monday) is True
    print("review_shared market-hours self-test passed")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        self_test_market_hours()
