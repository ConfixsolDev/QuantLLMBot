from __future__ import annotations

from vnext.strategy.lifecycle import CandidateLifecycle

def test_candidate_lifecycle_preserves_explicit_transitions():
    lifecycle = CandidateLifecycle("scalp-v1")
    assert lifecycle.advance("ELIGIBLE").state == "ELIGIBLE"
    assert lifecycle.advance("WATCHING").state == "WATCHING"
