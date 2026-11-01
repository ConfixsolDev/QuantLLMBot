"""The answer contract: what the model may say, checked by code before anything happens.

The model (Bonsai 2 27B, see client.py) must return ONE JSON object::

    {"decision": "C2" | "wait", "confidence": 0-100, "cites": ["E3", "E7"], "why": "..."}

``check(text, prompt, min_confidence)`` returns a Verdict. Only a Verdict with
``action == "take"`` can lead to a trade, and then only for a candidate that
exists in this prompt. Rules (V3 Part E2 companion controls):

* the text must contain a JSON object (a ```json fence is tolerated);
* ``decision`` is a candidate id of THIS prompt or "wait" — nothing else;
* a trade needs confidence >= the strategy's min_confidence (51); missing = 0;
* a trade needs at least one citation; every citation must be an evidence
  id of this prompt (E3) or a fact of one of its candidates (C1.rejection,
  C1.level.history ...) — nothing invented;
* ``why`` is kept (max 300 characters) for the journal.

Anything that breaks a rule is ``action == "invalid"`` with the reasons;
the system then does nothing for this candidate, and the reasons are journaled.

``answer_schema(prompt)`` is the same contract as a JSON schema, sent to
llama-server so the answer is grammar-constrained: "decision" can only be one
of THIS prompt's candidate ids or "wait". ``check`` still runs on every answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


@dataclass(frozen=True)
class Verdict:
    action: str                     # "take" | "wait" | "invalid"
    label: str | None               # "C2"
    candidate_key: str | None       # the stable candidate key behind "C2"
    confidence: int
    cites: tuple[str, ...]          # "E3", ...
    cited_events: tuple[str, ...]   # engine event ids behind them
    why: str
    errors: tuple[str, ...] = field(default_factory=tuple)
    parsed: dict | None = None


def _extract(text: str) -> dict | None:
    m = FENCE.search(text)
    candidates = [m.group(1)] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def check(text: str, prompt, min_confidence: int) -> Verdict:
    obj = _extract(text)
    if obj is None:
        return Verdict("invalid", None, None, 0, (), (), "", ("answer is not a JSON object",))
    errors: list[str] = []
    decision = str(obj.get("decision", "")).strip()
    try:
        conf = int(round(float(obj.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0
        errors.append("confidence is not a number")
    if not 0 <= conf <= 100:
        errors.append(f"confidence {conf} outside 0-100")
    cites_raw = obj.get("cites", [])
    if not isinstance(cites_raw, list):
        errors.append("cites is not a list")
        cites_raw = []
    cites = tuple(str(c).strip() for c in cites_raw)
    unknown = [c for c in cites if c not in prompt.evidence_map
               and c.split(".", 1)[0] not in prompt.candidate_map]
    if unknown:
        errors.append(f"cites unknown evidence {unknown}")
    why = str(obj.get("why", ""))[:300]
    cited_events = tuple(prompt.evidence_map[c] for c in cites if c in prompt.evidence_map)

    if decision.lower() == "wait":
        action, label, key = "wait", None, None
    elif decision in prompt.candidate_map:
        action, label, key = "take", decision, prompt.candidate_map[decision]
        if conf < min_confidence:
            errors.append(f"confidence {conf} < {min_confidence} for a trade")
        if not cites:
            errors.append("a trade needs at least one citation")
    else:
        action, label, key = "invalid", None, None
        errors.append(f"decision {decision!r} is not a candidate id {sorted(prompt.candidate_map)} or 'wait'")
    if errors and action == "take":
        action = "invalid"
    return Verdict(action, label, key, conf, cites, cited_events, why, tuple(errors), obj)


def answer_schema(prompt) -> dict:
    """JSON schema of the answer for one prompt (llama-server json_schema / grammar)."""
    ids = list(prompt.candidate_map) + ["wait"]
    cite_ids = list(prompt.evidence_map) + [f"{c}.{f}" for c in prompt.candidate_map
                                             for f in ("rejection", "level", "level.history", "approach",
                                                       "trade", "obstacles", "stretch_h1atr")]
    return {"type": "object",
            "properties": {"decision": {"type": "string", "enum": ids},
                           "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                           "cites": {"type": "array", "items": {"type": "string", "enum": cite_ids},
                                     "maxItems": 8},
                           "why": {"type": "string", "maxLength": 200}},
            "required": ["decision", "confidence", "cites", "why"],
            "additionalProperties": False}
