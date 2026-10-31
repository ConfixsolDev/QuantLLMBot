"""A strategy is DATA: rules for code + doctrine for Qwen, versioned and hashed.

Files live in ``strategy/library/<id>.v<version>.json``. One strategy is
active at a time (``trading`` settings name it). Loading is strict, like the
structure config: unknown or missing keys fail, so a typo can never silently
change how candidates are built.

Why a hash: every Qwen decision and every trade stores the strategy id,
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

RULE_KEYS = {
    "kind": str, "decision_point": str, "sides": list, "sessions": list, "max_test_no": int, "approaches": list,
    "rejection_within_bars": int, "entry_window_bars": int, "stop_buffer_atr": float,
    "min_stop_atr": float, "plan_stop_allowance_atr": float, "target": str,
    "fallback_target_r": float, "min_target_atr": float, "min_rr": float, "min_confidence": int,
    "close_on_stalled_followthrough": bool, "max_candidates": int,
}
PROMPT_KEYS = {"max_bytes": int, "max_levels": int, "max_evidence": int}
TOP_KEYS = {"id", "version", "name", "rules", "prompt", "doctrine", "legend", "answer"}
KINDS = {"htf_level_rejection"}          # rule kinds candidates.py knows how to build
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
    _typed(body["rules"], RULE_KEYS, "rules")
    _typed(body["prompt"], PROMPT_KEYS, "prompt")
    r = body["rules"]
    if r["kind"] not in KINDS:
        raise StrategyError(f"rules.kind {r['kind']!r} unknown; known {sorted(KINDS)}")
    if r["decision_point"] not in ("test", "rejection"):
        raise StrategyError("rules.decision_point: 'test' (ask when price reaches the level) or "
                            "'rejection' (ask at the M1 rejection)")
    if not set(r["sides"]) <= {"buy", "sell"} or not r["sides"]:
        raise StrategyError("rules.sides: buy and/or sell")
    if not set(r["sessions"]) <= SESSIONS:
        raise StrategyError(f"rules.sessions: from {sorted(SESSIONS)}")
    if not 0 < r["min_confidence"] <= 100:
        raise StrategyError("rules.min_confidence: 1-100")
    for part in ("doctrine", "legend"):
        if not isinstance(body[part], list) or not all(isinstance(x, str) and x for x in body[part]):
            raise StrategyError(f"{part}: list of non-empty strings")
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return Strategy(body["id"], int(body["version"]), body["name"], r, body["prompt"],
                    tuple(body["doctrine"]), tuple(body["legend"]), body["answer"],
                    hashlib.sha1(canon.encode()).hexdigest()[:10])


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
