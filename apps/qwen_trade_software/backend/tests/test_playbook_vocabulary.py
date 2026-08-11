"""Playbook-condition vocabulary must accept legitimate synonyms.

2026-08-10 incident
-------------------
Deploying the v004 model took the entire trading chain offline. Not because the
model was wrong -- because it used a different word.

    v004 wrote:  sell: "invalidated below H1_PREVIOUS_HIGH"
    validator wanted one of: close / accept / retest / reject / reclaim / fail
    result:      playbook:...:sell:not_closed_response  x3
                 -> qualification failed
                 -> run-qualification.ps1 does not restart on failure
                 -> every process down

A retry 22 seconds later phrased the identical idea as "rejection below" and
passed. So the gate was a coin flip on synonym choice, and when it lost it
halted trading with a message that pointed at the model rather than at itself.

These tests pin the vocabulary: legitimate structural phrasings pass, and
content-free phrasings still fail. Extend RESPONSE_TOKENS when a model uses a
real synonym; do not tighten it to force one wording.
"""

from __future__ import annotations

import os
import sys
import types

import pytest


@pytest.fixture(scope="module")
def tokens():
    class _Fake(types.ModuleType):
        def __getattr__(self, name):
            if name.isupper() or name.startswith("TIMEFRAME_"):
                return 0
            return lambda *a, **k: None

    sys.modules.setdefault("MetaTrader5", _Fake("MetaTrader5"))
    msvcrt = types.ModuleType("msvcrt")
    msvcrt.locking = lambda *a, **k: None
    msvcrt.LK_NBLCK, msvcrt.LK_UNLCK = 1, 0
    sys.modules.setdefault("msvcrt", msvcrt)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import market_context_cache as mcc

    return mcc.RESPONSE_TOKENS, mcc.BUY_REVERSAL_TOKENS, mcc.SELL_REVERSAL_TOKENS


def accepts(tokens, side: str, condition: str) -> bool:
    response, buy_rev, sell_rev = tokens
    low = condition.lower()
    ok = any(t in low for t in response)
    if side == "buy" and "below" in low:
        ok = ok and any(t in low for t in buy_rev)
    if side == "sell" and "above" in low:
        ok = ok and any(t in low for t in sell_rev)
    return ok


# --- the exact strings that took the system down ---------------------------

@pytest.mark.parametrize("condition", [
    "invalidated below H1_PREVIOUS_HIGH",
    "invalidated below H4_PREVIOUS_HIGH",
    "invalidated below M30_PREVIOUS_LOW",
])
def test_v004_invalidated_phrasing_is_accepted(tokens, condition):
    assert accepts(tokens, "sell", condition), (
        "this phrasing halted the trading chain on 2026-08-10"
    )


def test_v003_phrasing_still_accepted(tokens):
    """The retry that happened to pass must keep passing."""
    assert accepts(tokens, "buy", "acceptance above H1_PREVIOUS_HIGH")
    assert accepts(tokens, "sell", "rejection below H1_PREVIOUS_HIGH")


# --- synonyms a future model version might reasonably use ------------------

@pytest.mark.parametrize("side,condition", [
    ("buy",  "closed above M30_PREVIOUS_LOW with volume"),
    ("buy",  "reclaim of H1_PREVIOUS_LOW after sweep"),
    ("buy",  "failure to hold below H4_PREVIOUS_LOW"),
    ("sell", "swept H1_PREVIOUS_HIGH then closed back below"),
    ("sell", "rejection at M15_PREVIOUS_HIGH"),
    ("sell", "broke and retested M30_PREVIOUS_LOW"),
    ("sell", "held below H4_PREVIOUS_HIGH"),
    ("buy",  "respected M30_PREVIOUS_LOW"),
])
def test_legitimate_synonyms_accepted(tokens, side, condition):
    assert accepts(tokens, side, condition)


# --- genuine junk must still be refused ------------------------------------

@pytest.mark.parametrize("side,condition", [
    ("sell", "price goes down a bit"),
    ("buy",  "looks bullish"),
    ("buy",  "momentum is strong"),
    ("sell", "bearish sentiment"),
])
def test_content_free_conditions_still_rejected(tokens, side, condition):
    assert not accepts(tokens, side, condition), (
        "the gate must still refuse conditions that name no response"
    )


def test_wrong_side_continuation_still_rejected(tokens):
    """A buy condition describing price simply being below, with no reversal."""
    assert not accepts(tokens, "buy", "price drifting below H1_PREVIOUS_LOW")


def test_vocabulary_is_not_accidentally_narrowed(tokens):
    """Guard the fix itself: these anchors must remain present."""
    response, _, _ = tokens
    for required in ("close", "accept", "reject", "invalidat", "fail"):
        assert required in response, f"{required!r} removed from RESPONSE_TOKENS"
