from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT.parent / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from strategy.lifecycle import CandidateLifecycle

def test_candidate_lifecycle_preserves_explicit_transitions():
    lifecycle = CandidateLifecycle("scalp-v1")
    assert lifecycle.advance("ELIGIBLE").state == "ELIGIBLE"
    assert lifecycle.advance("WATCHING").state == "WATCHING"
