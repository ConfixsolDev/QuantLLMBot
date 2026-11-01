"""Module 2a — strategies: rules for code, doctrine for the model.

    model.py       load + validate a versioned strategy file (library/*.json)
    outlook.py     compact market outlook from the structure snapshot
    candidates.py  deterministic plans (on a level test) and triggers (on an M1 rejection)
    runner.py      follows the engine event stream for one strategy
    template.py    the model prompt: doctrine + outlook + candidates + evidence, <= 6 KB
    __main__.py    python -m strategy list | show <id> | preview --m1 <files> [--date D]

Nothing here talks to the model or the broker: ``llm/`` asks the model,
``trading/`` executes. See V3 document Part F.
"""

from .model import Strategy, StrategyError, available, load

__all__ = ["Strategy", "StrategyError", "available", "load"]
