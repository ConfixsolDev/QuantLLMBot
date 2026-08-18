"""Guard the qualification certificate identity.

2026-08-10 incident (self-inflicted during remediation)
-------------------------------------------------------
load_prompt_section() was changed to strip HTML comments so maintainer notes
would stop being shipped to the model as instructions. That change was correct.

But QwenContextShadow.qualification_contract_hash is computed from the same
function, and it is the IDENTITY of the qualification certificate stored in
cache_objects. Stripping comments moved the hash:

    aa0f5f0c...  (raw text, what every stored certificate is bound to)
 -> 3d1bb9d3...  (comment-stripped)

_qualification_is_valid() then rejected a certificate that was still current,
still passing, and still bound to the right model digest. The cache child
starts with --no-qwen; auto-requalify must stay in place so a hash or digest
change can mint a replacement instead of sitting on qwen_validation_not_run.

Cache ready through 15:03:17 -> blocked from 15:03:42, four seconds after the
edit landed and the stack restarted.

These tests fail if the hash input is ever changed again without a deliberate
re-qualification.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest


def _find_sop() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "store" / "sop.md"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("store/sop.md not found")


SOP = _find_sop()

# The six sections that compose the qualification contract identity.
QUALIFICATION_PROMPTS = (
    "qwen_history_chunk",
    "qwen_cache_warmup",
    "qwen_playbook_interpretation",
    "qwen_session_warmup",
    "qwen_context_challenge",
    "qwen_minute_shadow",
)

# The hash every certificate currently on disk is bound to.
KNOWN_CERTIFICATE_HASH = (
    "sha256:aa0f5f0c2d5fdabc5fcd6f8ec944dcd00610e851eeb52e5c65dd9d2a1e302f35"
)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(value) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_section(name: str, *, keep_comments: bool) -> str:
    sop = SOP.read_text(encoding="utf-8")
    marker = f"<!-- prompt:{name} -->"
    start = sop.find(marker)
    if start < 0:
        pytest.skip(f"section {name} missing")
    body_start = sop.find("\n", start) + 1
    next_marker = sop.find("<!-- prompt:", body_start)
    body = sop[body_start : next_marker if next_marker >= 0 else len(sop)]
    if not keep_comments:
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def qualification_hash(*, keep_comments: bool) -> str:
    return content_hash({
        "qualification_version": 2,
        "prompts": {
            name: load_section(name, keep_comments=keep_comments)
            for name in QUALIFICATION_PROMPTS
        },
    })


def test_hash_matches_the_certificate_on_disk():
    """The stored certificate must still validate. This is the whole incident."""
    assert qualification_hash(keep_comments=True) == KNOWN_CERTIFICATE_HASH


def test_stripping_comments_would_change_the_identity():
    """Documents why keep_comments=True is load-bearing, not cosmetic."""
    assert qualification_hash(keep_comments=False) != KNOWN_CERTIFICATE_HASH


def test_qualification_sections_still_exist():
    for name in QUALIFICATION_PROMPTS:
        assert len(load_section(name, keep_comments=True)) > 100


def test_production_code_hashes_raw_text():
    """Fail loudly if someone drops keep_comments=True from the hash input."""
    source = (Path(__file__).resolve().parents[1] / "market_context_cache.py").read_text(
        encoding="utf-8"
    )
    start = source.find("self.qualification_contract_hash = content_hash(")
    assert start > 0, "qualification hash construction not found"
    window = source[start : start + 700]
    assert "keep_comments=True" in window, (
        "qualification_contract_hash must hash RAW section text. Removing "
        "keep_comments=True invalidates every stored certificate."
    )
