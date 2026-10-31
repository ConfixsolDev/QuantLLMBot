"""structure_engine — Module 1 of QuantLLM: deterministic market structure.

Closed M1 bars in -> confirmed structure events + a snapshot out.
Standard library only; never calls Qwen, a strategy or a broker.
Full design: XAUUSD_SYSTEM_ARCHITECTURE_V3.md (repository root), Part B.

Quick use::

    from structure_engine import StructureEngine, load_config, load_m1
    engine = StructureEngine(load_config())
    for bar in load_m1("XAUUSD_M1.csv"):
        events = engine.push(bar)
    state = engine.snapshot()
"""

from .bars import Bar, load_m1
from .config import load_config
from .engine import StructureEngine
from .events import Event, fingerprint

__all__ = ["Bar", "Event", "StructureEngine", "fingerprint", "load_config", "load_m1"]
