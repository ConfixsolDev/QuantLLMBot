"""Module 2b — Qwen: ask the local model, check its answer.

    client.py     HTTP client for Ollama or any OpenAI-compatible server (stdlib only)
    contract.py   the answer contract: decision / confidence / cites / why, checked by code
    __main__.py   python -m qwen ping | ask <prompt.json>

Qwen only CHOOSES among candidates built by code (strategy/), or says wait.
It never sets a price; trading/ never reads model text. See V3 Part F.
"""

from .client import QwenClient, QwenError, QwenSettings, Reply, load_settings
from .contract import Verdict, check

__all__ = ["QwenClient", "QwenError", "QwenSettings", "Reply", "load_settings", "Verdict", "check"]
