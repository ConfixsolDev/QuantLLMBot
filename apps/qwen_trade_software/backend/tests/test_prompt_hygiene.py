"""Prompt hygiene: what reaches the model must be instructions, nothing else.

Caught during the 2026-08-10 remediation. The rollback commit added a maintainer
note to sop.md explaining that the previous contract had "returned confidence 0
while still emitting status ready". Because load_prompt_section() did not strip
HTML comments, that note was shipped to the model as part of its instructions --
an explanation of the bug became a demonstration of the bug. Replay showed the
new contract still producing 100% zero-confidence decisions.

These tests fail if that class of mistake returns.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _find_sop() -> Path:
    """Walk up until store/sop.md is found, so the test is location-independent."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "store" / "sop.md"
        if candidate.exists():
            return candidate
    raise FileNotFoundError("store/sop.md not found above this test file")


SOP = _find_sop()

# Phrases that describe a failure mode rather than instruct the model. Any of
# these reaching the model risks priming the exact behaviour being described.
PRIMING_PHRASES = (
    "incident",
    "regression",
    "rollback",
    "returned confidence 0",
    "collapsed",
    "maintainer",
    "2026-08-10",
    "do not reintroduce",
)

MODEL_FACING_SECTIONS = (
    "qwen_cached_entry",
    "qwen_entry_trend",
    "qwen_entry_range",
    "qwen_entry_reversal",
    "qwen_dual_side_entry",
    "qwen_trade_management",
    "qwen_intraday_observer",
)


def load_section(name: str, *, keep_comments: bool = False) -> str:
    """Mirror of market_context_cache.load_prompt_section, without the MT5 import."""
    sop = SOP.read_text(encoding="utf-8")
    marker = f"<!-- prompt:{name} -->"
    start = sop.find(marker)
    if start < 0:
        pytest.skip(f"section {name} not present")
    body_start = sop.find("\n", start) + 1
    next_marker = sop.find("<!-- prompt:", body_start)
    body = sop[body_start : next_marker if next_marker >= 0 else len(sop)]
    if not keep_comments:
        body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)
        body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


@pytest.mark.parametrize("section", MODEL_FACING_SECTIONS)
def test_no_html_comments_reach_the_model(section):
    assert "<!--" not in load_section(section)


@pytest.mark.parametrize("section", MODEL_FACING_SECTIONS)
def test_no_priming_phrases_reach_the_model(section):
    body = load_section(section).lower()
    leaked = [phrase for phrase in PRIMING_PHRASES if phrase in body]
    assert not leaked, f"{section} ships maintainer commentary to the model: {leaked}"


@pytest.mark.parametrize("section", MODEL_FACING_SECTIONS)
def test_section_is_not_empty_after_stripping(section):
    assert len(load_section(section)) > 200


def test_version_marker_is_still_parseable_from_raw():
    raw = load_section("qwen_cached_entry", keep_comments=True)
    assert re.search(r"<!--\s*version:\s*[0-9]+\.[0-9]+", raw)


def test_live_entry_contract_uses_one_direction_not_dual_assessment():
    body = load_section("qwen_cached_entry").lower()
    assert "return exactly one conclusion: buy, sell, or\nwait" in body
    assert "both sides before deciding" not in body
    assert "build one directional assessment rather than separate long and short" in body


def test_shared_entry_contract_keeps_strategy_inside_regime_modules():
    body = load_section("qwen_cached_entry").lower()
    assert "shared structure, location, closed-response" in body
    assert "range uses scalp" not in body
    assert "trend/breakout uses" not in body
    assert "use the matching playbook to organize the evidence" in body
    assert "fresh mapped-level response" in body


def test_live_entry_contract_has_no_prohibition_wall():
    """v1.9's nine-item prohibition list zeroed the confidence distribution.

    Traps belong in the dual-side contract as reported data, not here as rules.

    The cap is 8 rather than 6 because symmetrising the HTF paragraph
    (2026-08-11) legitimately added one mirrored prohibition: the bullish case
    already said "Do not sell an M1 rejection at that broken high", so the
    bearish case needs "Do not buy an M1 bounce at that broken low". Balance
    costs one prohibition per direction and that is correct.

    What this guards against is a WALL -- v1.9 had nine numbered items. See the
    balance assertion below, which is the property that actually matters.
    """
    body = load_section("qwen_cached_entry")
    assert "Hard traps" not in body
    assert body.lower().count("do not ") <= 8


def test_range_playbook_repeats_edges_and_skips_only_to_mapped_next_level():
    body = load_section("qwen_entry_range").lower()
    assert "repeating two-sided auction" in body
    assert "buying completed\nfailures at its lower boundary" in body
    assert "selling completed failures at its upper\nboundary" in body
    assert "wait for the next mapped support or\nresistance" in body
    assert "runtime promotes the market to breakout_confirmed" in body
    assert "never promotes\nthe regime from expectation alone" in body


def test_prohibitions_are_directionally_balanced():
    """A prohibition aimed at one side must have its mirror.

    This is the real defect v1.9 introduced and that the raw count only
    approximates: instructions that constrain one direction more than the other.
    """
    body = load_section("qwen_cached_entry").lower()
    # Each directional warning should appear with both a buy and a sell form.
    assert body.count("do not sell") == body.count("do not buy"), (
        "directional prohibitions are unbalanced"
    )


def test_dual_side_contract_requires_both_directions():
    body = load_section("qwen_dual_side_entry")
    assert "long" in body and "short" in body
    assert "Never omit a side" in body or "never omit a side" in body.lower()


def test_dual_side_contract_does_not_ask_for_a_verdict():
    """The v2.0 model must not own ready/wait or an overall confidence."""
    body = load_section("qwen_dual_side_entry").lower()
    assert "you do not decide" in body
    assert "status ready|wait" not in body


def test_no_conditional_bias_in_dual_side_contract():
    """bias=conditional was 65-71% of decisions; the enum removes it."""
    assert "conditional" not in load_section("qwen_dual_side_entry").lower()
