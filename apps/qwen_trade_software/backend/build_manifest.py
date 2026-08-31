"""Which build produced this trade.

2026-08-11 -- why this exists
----------------------------
An analysis of 71 closed trades across four days could conclude almost nothing,
because every split tested collapsed into a date effect. Confidence band,
structure metadata and side mix were each near-perfectly confounded with the day
the code changed:

    2026-08-06   14 of the 21 sub-80-confidence trades, no structure metadata
    2026-08-10   41 of the 50 high-confidence trades, all with structure metadata

So "high confidence loses money" and "trades with structure metadata lose money"
were both really "2026-08-10 lost money". Nothing in any record said which
version of the system produced it, so the four distinct behaviours that traded
that week were pooled into one dataset and cancelled each other out.

A build_id on every record makes that mistake impossible: results can be grouped
by the code that generated them, and a report can refuse to pool across builds.

Why a source digest rather than a git SHA
-----------------------------------------
Uncommitted edits are the normal working state of this repository -- 56 files
were dirty when this was written. A git SHA would have labelled all four of that
week's distinct behaviours identically, which is precisely the failure being
fixed. The digest covers the files and constants that actually change decisions,
so it moves when behaviour moves and stays still when a comment is reworded in
an unrelated module.

Cost: computed once at import, roughly a few milliseconds of hashing.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FROZEN_FILE = APP_DIR / "frozen-build.json"

MANIFEST_VERSION = "1.0"

# Modules whose contents change what the system decides or how it sizes and
# manages a trade. A change in any of these is a behaviour change, and results
# from before and after must not be pooled.
DECISION_MODULES = (
    # Decide what to trade, how to size it, and when to leave.
    "entry_policy.py",
    "entry_contract.py",
    "entry_geometry_menu.py",
    "entry_regime_prompts.py",
    "structure_response.py",
    "market_runtime.py",
    "trade_geometry.py",
    "management_policy.py",
    "trade_manager.py",
    "paper_executor.py",
    "paper_runner.py",
    "entry_safety.py",
    "cooldown_manager.py",
    "reviewer.py",
    "trade_management.py",
    "profit_protection.py",
      "profit_protection_policy.py",
      "regime_engine.py",
      "regime_policy.py",
    "session_planner.py",
    "opportunity_state.py",
    "plan_ladder.py",
    "plan_branches.py",
    # Shape what the model is asked and what it is allowed to answer. A prompt
    # or cache change alters behaviour just as surely as a threshold does.
    "market_context_cache.py",
    "candle_clock.py",
    "market_intelligence/store.py",
    "market_intelligence/projection.py",
    "market_intelligence/cross_market.py",
    "market_intelligence/retrieval.py",
    "market_intelligence/service.py",
    "pair_market_state.py",
    "timescale_store.py",
    "redis_context.py",
    "storage_config.py",
    "storage_factory.py",
    "timescale_context_store.py",
    "strategy_contract.py",
    "strategy_runtime.py",
    "strategy_statistics.py",
    "strategy_scheduler.py",
    "llm_arbitration.py",
    "storage_acceptance.py",
    "market_intelligence/collector.py",
    "market_intelligence/live_structure_updater.py",
    "market_intelligence/decision_events.py",
    "market_intelligence/execution_events.py",
    "market_intelligence/trade_journal.py",
    "broker_reconciliation_worker.py",
    "trade_journal_worker.py",
    "market_intelligence/historical_backfill.py",
    "market_memory_worker.py",
    "market_graph/config.py",
    "market_graph/temporal.py",
    "market_graph/client.py",
    "market_graph/context_compiler.py",
    "market_graph/projector.py",
    "market_graph/live_updater.py",
    "market_graph/market_state.py",
    "market_graph/rag_protocol.py",
    "market_graph/semantic_memory.py",
    "market_graph_worker.py",
    "market_history_backfill.py",
    "qwen_event_gate.py",
    "intraday_observer_worker.py",
    "intraday_observer/__init__.py",
    "intraday_observer/contracts.py",
    "intraday_observer/deterministic.py",
    "intraday_observer/service.py",
    "intraday_observer/scheduler.py",
    "instrument_config.py",
    "market_runtime.py",
    "prompt_composer.py",
    "runtime_config.py",
    "market_structure.py",
    "structure_tracker.py",
    "structural_event.py",
    "fvg_detector.py",
    "order_block.py",
    "ote_calculator.py",
    "liquidity_map.py",
    "zone_scorer.py",
    "review_shared.py",
    # Infrastructure the decision path runs THROUGH.
    #
    # These were left out of the first version of this list, on the reasoning
    # that they only move data around. Then on 2026-08-11 a one-line dictionary
    # omission in tick_data_archive.py raised on every monitor tick, killed the
    # executor, and cost seven trades their close records -- while build_id sat
    # unchanged, reporting the broken system and the fixed one as the same
    # build.
    #
    # The test is not "does this module make decisions" but "can a change here
    # change the outcome". For anything in the live path, it can.
    "tick_data_archive.py",
    "process_logging.py",
    "decision_liveness.py",
    "execution_funnel.py",
    "news_blackout.py",
)

# Tunables read at runtime. These can change behaviour without any source edit
# -- an env var flip is invisible to a file digest -- so they are hashed
# separately and reported in full, because "which threshold was live" is the
# first question any strategy review asks.
def _tunables() -> dict:
    """Read the tunables straight from source. No imports.

    2026-08-11 -- why this does not import
    --------------------------------------
    The first version called __import__ on each module and read attributes off
    it. Five of the modules it inspects import build_manifest themselves, so
    importing them from inside build_manifest's own module-level compute() hit a
    circular import: the inner `import build_manifest` returned a half-built
    module, the attribute lookup raised, and a bare `except` swallowed it.

    The result was a manifest that silently captured 0 of paper_runner's
    constants and 3 of paper_executor's. Changing LOSS_COOLDOWN_SECONDS would
    not have moved build_id at all -- the precise failure this module exists to
    make impossible, sitting inside the module itself.

    Parsing the source has no import side effects, no ordering dependence, and
    cannot be defeated by a circular reference. Values that are not literals
    (an env lookup, say) are recorded as their source expression, which still
    moves the hash when the expression changes; the env var's actual value is
    captured separately below.
    """
    values: dict[str, object] = {}

    def grab(module_name: str, *names: str) -> None:
        try:
            tree = ast.parse((APP_DIR / f"{module_name}.py").read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            values[f"{module_name}.<unreadable>"] = True
            return
        wanted = set(names)
        seen: set[str] = set()
        for node in tree.body:                      # module level only
            # Both forms matter: `X = 1` and the annotated `X: dict = {...}`.
            # Handling only ast.Assign missed SCORE_WEIGHTS, which is declared
            # with a type annotation -- caught immediately by the <missing>
            # marker below, which is what it is for.
            if isinstance(node, ast.Assign):
                targets, rhs = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, rhs = [node.target], node.value
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name) or target.id not in wanted:
                    continue
                try:
                    value = ast.literal_eval(rhs)
                    if isinstance(value, dict):
                        value = dict(sorted(value.items()))
                    elif isinstance(value, (set, frozenset)):
                        value = sorted(map(str, value))
                except (ValueError, SyntaxError):
                    # Not a literal -- e.g. os.environ.get(...). Keep the
                    # expression text so a change to it still moves the hash.
                    value = f"<expr:{ast.unparse(rhs)}>"
                values[f"{module_name}.{target.id}"] = value
                seen.add(target.id)
        missing = wanted - seen
        if missing:
            # Loud rather than silent. A constant that has been renamed or
            # moved would otherwise vanish from the manifest unnoticed, and
            # changing it would stop moving the build id.
            values[f"{module_name}.<missing>"] = sorted(missing)

    grab("entry_policy", "MIN_ENTRY_CONFIDENCE", "MAX_INVALIDATION_GAP",
         "POLICY_VERSION", "SCORE_WEIGHTS",
         # 2026-08-28: SYMMETRY_CONFIDENCE_SURCHARGE was halved (10->5) on
         # 2026-08-25 to allow "more one-sided day volume." That is exactly
         # the kind of change this manifest exists to make visible, and it
         # was not tracked -- the side-imbalance safeguard's own strength
         # could change with nothing here moving the build id. Tracking it
         # now does not change today's value; it only means the NEXT change
         # to it shows up as drift instead of disappearing silently.
         "SYMMETRY_WINDOW", "SYMMETRY_MAX_SHARE", "SYMMETRY_CONFIDENCE_SURCHARGE")
    grab("trade_geometry", "MIN_REWARD_RISK", "TF_MIN_STOP", "TF_MIN_TARGET",
         "ROUND_TRIP_COST", "VALUE_PER_PRICE_UNIT_PER_LOT")
    grab("management_policy", "MAX_RISK_MULTIPLE", "INITIAL_REBRACKET_SECONDS",
         "R3_MAX_PROGRESS", "STOP_POLICY", "TARGET_POLICY")
    grab("profit_protection_policy", "ARM_R", "ARM_ATR", "TRAIL_ATR",
         "GIVEBACK_MFE", "FRONT_LAYER_VOLUME_FRACTION",
         "FRONT_LAYER_START_ATR", "WIDE_LAYER_START_ATR",
         "LADDER_STEP_ATR", "FRONT_GAP_ATR", "WIDE_GAP_ATR")
    grab("paper_executor", "INITIAL_STOP_DISTANCE", "INITIAL_TAKE_PROFIT_DISTANCE",
         "STRUCTURAL_BRACKET_ENABLED")
    grab("paper_runner", "MIN_ENTRY_CONFIDENCE", "DAILY_PAPER_CAP",
         "LOSS_COOLDOWN_SECONDS", "WIN_COOLDOWN_SECONDS",
         "LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE",
         "LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK",
         "MAX_PROPOSAL_AGE_SECONDS")
    # paper_runner exposes these for compatibility, but cooldown_manager is
    # their modular source of truth. Resolve the actual literals so build
    # identity records behavior rather than an attribute-expression string.
    cooldown_names = (
        "LOSS_COOLDOWN_SECONDS", "WIN_COOLDOWN_SECONDS",
        "LOSS_COOLDOWN_BYPASS_MIN_CONFIDENCE",
        "LOSS_COOLDOWN_BYPASS_MIN_REWARD_RISK",
    )
    grab("cooldown_manager", *cooldown_names)
    for name in cooldown_names:
        values[f"paper_runner.{name}"] = values[f"cooldown_manager.{name}"]
    # Model placement decides whether a decision can beat its own TTL, so it
    # belongs in the build identity: GPU and CPU runs must never pool.
    grab("review_shared", "FORCE_GPU_LAYERS", "MIN_VRAM_SHARE")
    grab("reviewer", "GPU_PROBE_INTERVAL_SECONDS")
    # A blackout window change alters which trades are possible, so it is
    # part of the build identity: news-on and news-off runs must not pool.
    grab("news_blackout", "BLACKOUT_MINUTES_BEFORE", "BLACKOUT_MINUTES_AFTER",
         "BLOCK_CURRENCIES", "BLOCK_IMPACTS", "NEWS_ENABLED",
         "MAX_CACHE_AGE_HOURS")

    # Env switches that alter behaviour without touching a file.
    for var in (
        "QWEN_SKIP_ON_GEOMETRY", "QWEN_MIN_REWARD_RISK", "QWEN_MODEL",
        "QWEN_ENTRY_MODEL", "QWEN_MANAGEMENT_MODEL", "QWEN_PLANNER_MODEL",
        "QWEN_CONTEXT_MODEL", "QWEN_PRIMARY_SYMBOL",
        "QWEN_STRUCTURAL_BRACKET", "QWEN_REVIEW_INTERVAL_SECONDS",
    ):
        values[f"env.{var}"] = os.environ.get(var)
    return values


def _source_digest() -> tuple[str, dict]:
    """Hash of the decision-relevant sources, plus each file's own short hash."""
    per_file: dict[str, str] = {}
    combined = hashlib.sha256()
    for name in DECISION_MODULES:
        path = APP_DIR / name
        try:
            data = path.read_bytes()
        except OSError:
            per_file[name] = "missing"
            combined.update(b"missing:" + name.encode())
            continue
        digest = hashlib.sha256(data).hexdigest()
        per_file[name] = digest[:12]
        combined.update(name.encode() + digest.encode())
    return combined.hexdigest(), per_file


def compute() -> dict:
    """The full manifest for the code currently loaded."""
    source_hash, per_file = _source_digest()
    tunables = _tunables()
    tunable_hash = hashlib.sha256(
        json.dumps(tunables, sort_keys=True, default=str).encode()
    ).hexdigest()

    # "unresolved" rather than None on failure. If an import breaks, the value
    # must not silently become None and read downstream as "the model changed"
    # -- a resolution failure and a real change would otherwise look identical
    # in the drift report.
    try:
        import review_shared
        model = getattr(review_shared, "MODEL", None) or "unresolved"
    except Exception:
        try:
            from runtime_config import ACTIVE_QWEN_MODEL
            model = ACTIVE_QWEN_MODEL
        except Exception:
            model = "unresolved:import_failed"

    try:
        import market_context_cache
        getter = getattr(market_context_cache, "qualification_contract_hash", None)
        contract_hash = getter() if callable(getter) else "unresolved:absent"
    except Exception:
        contract_hash = "unresolved:import_failed"

    build_id = hashlib.sha256(
        f"{source_hash}|{tunable_hash}|{model}|{contract_hash}".encode()
    ).hexdigest()[:12]

    return {
        "manifest_version": MANIFEST_VERSION,
        "build_id": build_id,
        "source_hash": source_hash[:16],
        "tunable_hash": tunable_hash[:16],
        "model": model,
        "contract_hash": contract_hash,
        "files": per_file,
        "tunables": tunables,
        "computed_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# Computed once per process. Behaviour cannot change mid-process without a
# restart, and a stamp that re-hashes on every proposal would cost more than it
# tells us.
MANIFEST = compute()
BUILD_ID = MANIFEST["build_id"]


def stamp() -> dict:
    """The compact identity to attach to a record.

    Two fields only. The full manifest lives in frozen-build.json and in the
    startup log; repeating it on 30,000 rows would bloat the artifacts this
    change exists to make readable.
    """
    return {"build_id": BUILD_ID, "build_dirty": drift_fields() != []}


def load_frozen() -> dict | None:
    try:
        return json.loads(FROZEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def drift_fields(frozen: dict | None = None) -> list[str]:
    """What differs between the running build and the declared freeze.

    Empty list means either "matches the freeze" or "no freeze declared yet".
    Never raises: a drift check must not be able to stop trading.
    """
    frozen = frozen if frozen is not None else load_frozen()
    if not frozen:
        return []
    changed: list[str] = []
    for name, digest in (frozen.get("files") or {}).items():
        if MANIFEST["files"].get(name) != digest:
            changed.append(f"file:{name}")
    for key, value in (frozen.get("tunables") or {}).items():
        if MANIFEST["tunables"].get(key) != value:
            changed.append(
                f"tunable:{key} {value!r}->{MANIFEST['tunables'].get(key)!r}"
            )
    for key in ("model", "contract_hash"):
        if frozen.get(key) != MANIFEST.get(key):
            changed.append(f"{key} {frozen.get(key)!r}->{MANIFEST.get(key)!r}")
    return changed


def log_identity(owner: str) -> None:
    """Announce the build at startup, and alarm if it has drifted from freeze.

    Drift is an ERROR, never a block. A frozen build that refuses to start is a
    worse failure than one that runs and says so.
    """
    frozen = load_frozen()
    logging.info(
        "build %s (%s) model=%s frozen=%s",
        BUILD_ID, owner, MANIFEST.get("model"),
        (frozen or {}).get("build_id", "not declared"),
    )
    changed = drift_fields(frozen)
    if changed:
        logging.error(
            "ALARM build:drift :: running build %s differs from the declared "
            "freeze %s in %d place(s): %s -- results from this process must NOT "
            "be pooled with frozen-build results",
            BUILD_ID, frozen.get("build_id"), len(changed), "; ".join(changed[:8]),
        )
