"""The prompt: strategy doctrine + outlook + candidates + evidence, as JSON, <= 6 KB.

Two messages:

  system  the strategy's doctrine and the answer format. It is IDENTICAL for
          every call of one strategy version, so the model server can keep it
          cached and only read the short user message each time.
  user    compact JSON:
            {"strategy": "<id@vN#hash>", "outlook": {...},
             "candidates": [{"id": "C1", ...}],
             "evidence": {"E1": "12:00 M15 BOS dn close beyond 3965.03", ...}}

Evidence ids E1, E2 ... are mapped back to engine event ids in
``Prompt.evidence_map``; Qwen may only cite those ids (qwen/contract.py
checks it), so every reason it gives points at a real, stored event.

Size budget (``strategy.prompt.max_bytes``, UTF-8 bytes of both messages):
when over, the oldest market evidence is dropped first, then the farthest
level of the outlook; candidate evidence is kept. If it still does not fit,
PromptTooLarge is raised — the call is not made, nothing is silently cut.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


class PromptTooLarge(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    bytes: int
    sha: str                          # hash of both messages (journal: prompt identity)
    candidate_map: dict               # "C1" -> candidate key
    evidence_map: dict                # "E1" -> engine event id
    trimmed: dict                     # what was dropped to fit: {"evidence": n, "levels": n}


def system_message(strategy) -> str:
    lines = [f"STRATEGY {strategy.id} v{strategy.version}: {strategy.name}", *strategy.doctrine,
             "Reply with ONE JSON object and nothing else:",
             json.dumps(strategy.answer, separators=(",", ":"))]
    return "\n".join(lines)


def _user(strategy, outlook: dict, cands_view: list, evidence: dict) -> str:
    return json.dumps({"strategy": strategy.ref, "outlook": outlook, "candidates": cands_view,
                       "evidence": evidence}, separators=(",", ":"), ensure_ascii=False)


def build(strategy, outlook: dict, candidates: list, evidence: list[tuple[str, str]]) -> Prompt:
    """``candidates``: Candidate objects; ``evidence``: (engine event id, text), most important first."""
    limit = strategy.prompt["max_bytes"]
    cands = candidates[: strategy.rules["max_candidates"]]
    cmap = {f"C{i + 1}": c.key for i, c in enumerate(cands)}
    view = [c.prompt_view(label) for label, c in zip(cmap, cands)]
    n_cand_ev = len({eid for c in cands for eid in c.evidence})
    system = system_message(strategy)
    ev = list(evidence)
    outlook = dict(outlook)
    trimmed = {"evidence": 0, "levels": 0}
    while True:
        emap = {f"E{i + 1}": eid for i, (eid, _) in enumerate(ev)}
        user = _user(strategy, outlook, view, {f"E{i + 1}": txt for i, (_, txt) in enumerate(ev)})
        size = len(system.encode()) + len(user.encode())
        if size <= limit:
            break
        if len(ev) > n_cand_ev:                      # drop the oldest market evidence
            ev.pop()
            trimmed["evidence"] += 1
        elif len(outlook.get("levels", [])) > 1:     # then the farthest outlook level
            outlook["levels"] = outlook["levels"][:-1]
            trimmed["levels"] += 1
        else:
            raise PromptTooLarge(f"prompt is {size} bytes > {limit} even after trimming")
    sha = hashlib.sha1((system + "\n" + user).encode()).hexdigest()[:16]
    return Prompt(system, user, size, sha, cmap, emap, trimmed)
