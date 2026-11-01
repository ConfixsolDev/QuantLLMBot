"""A strategy is DATA: rules for code + doctrine for the model, versioned and hashed.

Files live in ``strategy/library/<id>.v<version>.json``. One strategy is
active at a time (``trading`` settings name it). Loading is strict, like the
structure config: unknown or missing keys fail, so a typo can never silently
change how candidates are built.

Why a hash: every model decision and every trade stores the strategy id,
version and hash (V3 Part E1: "source, prompt version, config hash ... must
be traceable for every decision"). Editing a file without bumping the
version still changes the hash, so the journal shows it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

LIBRARY = Path(__file__).resolve().parent / "library"

RULE_KEYS = {          # kind "htf_level_rejection" (v2, v3: fade an H1/H4 level after its M1 rejection)
    "kind": str, "decision_point": str, "sides": list, "sessions": list, "max_test_no": int, "approaches": list,
    "rejection_within_bars": int, "entry_window_bars": int, "stop_buffer_atr": float,
    "min_stop_atr": float, "stop_mode": str, "max_stop_atr": float, "plan_stop_allowance_atr": float, "target": str, "target_r": float,
    "fallback_target_r": float, "min_target_atr": float, "min_rr": float, "min_confidence": int,
    "close_on_stalled_followthrough": bool, "max_candidates": int,
}
SCALP_RULE_KEYS = {    # kind "m1_probe_failure" (strategy/scalp.py): M1 scalps at mapped locations
    "kind": str, "triggers": list, "vwap_anchors": list, "sides": list, "sessions": list,
    "atr_timeframe": str, "entry_window_bars": int, "entry_slack_atr": float, "stop_buffer_atr": float,
    "min_stop_atr": float, "max_stop_atr": float, "target": str, "target_r": float, "max_hold_bars": int,
    "confluence_minutes": int, "min_checks": int, "min_confidence": int, "max_candidates": int,
}
PROMPT_KEYS = {"max_bytes": int, "max_levels": int, "max_evidence": int}
TOP_KEYS = {"id", "version", "name", "rules", "prompt", "doctrine", "legend", "answer"}
KINDS = {"htf_level_rejection": RULE_KEYS, "m1_probe_failure": SCALP_RULE_KEYS}
TRIGGERS = {"level_rejection", "liquidity_sweep", "false_break", "vwap_band_reject"}
SESSIONS = {"ASIA", "LONDON", "NEW_YORK", "OFF"}


class StrategyError(ValueError):
    pass


@dataclass(frozen=True)
class Strategy:
    id: str
    version: int
    name: str
    rules: dict
    prompt: dict
    doctrine: tuple[str, ...]
    legend: tuple[str, ...]
    answer: dict
    hash: str

    @property
    def ref(self) -> str:
        """``id@vN#hash`` — how decisions and trades name the strategy."""
        return f"{self.id}@v{self.version}#{self.hash}"


def _typed(section: dict, spec: dict, where: str) -> None:
    unknown, missing = set(section) - set(spec), set(spec) - set(section)
    if unknown or missing:
        raise StrategyError(f"{where}: unknown {sorted(unknown)} / missing {sorted(missing)}")
    for k, t in spec.items():
        v = section[k]
        ok = isinstance(v, (int, float)) and not isinstance(v, bool) if t is float else \
            isinstance(v, t) and not (t is int and isinstance(v, bool))
        if not ok:
            raise StrategyError(f"{where}.{k}: expected {t.__name__}, got {v!r}")


def parse(raw: dict) -> Strategy:
    body = {k: v for k, v in raw.items() if not k.startswith("_")}
    if set(body) != TOP_KEYS:
        raise StrategyError(f"keys must be {sorted(TOP_KEYS)}, got {sorted(body)}")
    r = body["rules"]
    if not isinstance(r, dict) or r.get("kind") not in KINDS:
        raise StrategyError(f"rules.kind {r.get('kind') if isinstance(r, dict) else r!r} unknown; "
                            f"known {sorted(KINDS)}")
    _typed(r, KINDS[r["kind"]], "rules")
    _typed(body["prompt"], PROMPT_KEYS, "prompt")
    if r["kind"] == "m1_probe_failure":
        _check_scalp(r)
    else:
        _check_level(r)
    for part in ("doctrine", "legend"):
        if not isinstance(body[part], list) or not all(isinstance(x, str) and x for x in body[part]):
            raise StrategyError(f"{part}: list of non-empty strings")
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return Strategy(body["id"], int(body["version"]), body["name"], r, body["prompt"],
                    tuple(body["doctrine"]), tuple(body["legend"]), body["answer"],
                    hashlib.sha1(canon.encode()).hexdigest()[:10])


def _common(r: dict) -> None:
    if not set(r["sides"]) <= {"buy", "sell"} or not r["sides"]:
        raise StrategyError("rules.sides: buy and/or sell")
    if not set(r["sessions"]) <= SESSIONS:
        raise StrategyError(f"rules.sessions: from {sorted(SESSIONS)}")
    if not 0 < r["min_confidence"] <= 100:
        raise StrategyError("rules.min_confidence: 1-100")


def _check_scalp(r: dict) -> None:
    _common(r)
    if not r["triggers"] or not set(r["triggers"]) <= TRIGGERS:
        raise StrategyError(f"rules.triggers: from {sorted(TRIGGERS)}")
    if not set(r["vwap_anchors"]) <= {"day", "week", "session"}:
        raise StrategyError("rules.vwap_anchors: from day, week, session")
    if r["target"] != "r_multiple" or r["target_r"] <= 0:
        raise StrategyError("rules.target: 'r_multiple' with target_r > 0")
    if not 0 < r["min_stop_atr"] <= r["max_stop_atr"]:
        raise StrategyError("rules: 0 < min_stop_atr <= max_stop_atr")
    if r["entry_window_bars"] < 1 or r["max_hold_bars"] < 1 or r["confluence_minutes"] < 1:
        raise StrategyError("rules: entry_window_bars, max_hold_bars, confluence_minutes >= 1")
    if not 0 <= r["min_checks"] <= 5:
        raise StrategyError("rules.min_checks: 0-5 (there are five checks)")


def _check_level(r: dict) -> None:
    _common(r)
    if r["stop_mode"] not in ("atr", "beyond_next_level", "beyond_higher_level"):
        raise StrategyError("rules.stop_mode: 'atr' (min_stop_atr from entry, beyond the rejection candle), "
                            "'beyond_next_level' (just beyond the next level of the same side) or "
                            "'beyond_higher_level' (just beyond the next H4/day/week level); both <= max_stop_atr")
    if r["target"] not in ("next_htf_level", "r_multiple"):
        raise StrategyError("rules.target: 'next_htf_level' or 'r_multiple' (target_r x the real risk)")
    if r["decision_point"] not in ("test", "rejection"):
        raise StrategyError("rules.decision_point: 'test' (ask when price reaches the level) or "
                            "'rejection' (ask at the M1 rejection)")


def load(strategy_id: str, version: int | None = None, library: Path = LIBRARY) -> Strategy:
    """Load ``<id>.v<version>.json`` (latest version when ``version`` is None)."""
    files = sorted(library.glob(f"{strategy_id}.v*.json"), key=lambda p: int(p.stem.rsplit(".v", 1)[1]))
    if version is not None:
        files = [f for f in files if f.stem.endswith(f".v{version}")]
    if not files:
        raise StrategyError(f"no strategy file {strategy_id} v{version or '*'} in {library}")
    s = parse(json.loads(files[-1].read_text(encoding="utf-8")))
    if s.id != strategy_id or f".v{s.version}" not in files[-1].name:
        raise StrategyError(f"{files[-1].name}: id/version inside the file do not match its name")
    return s


def available(library: Path = LIBRARY) -> list[str]:
    return sorted(p.stem for p in library.glob("*.v*.json"))
