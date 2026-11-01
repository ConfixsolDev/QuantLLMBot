"""Module 2b — the decision model: ask the local LLM, check its answer.

Model: Bonsai 2 27B (prism-ml/Ternary-Bonsai-2-27B-gguf, Qwen3.8-27B in ternary
weights) served by the PrismML fork of llama.cpp — ``Start-LLM.bat``.

    client.py     HTTP client: llama_server (default) | openai | ollama; stdlib only
    contract.py   the answer contract (decision / confidence / cites / why) + its JSON schema
    decider.py    LLMDecider (the model) and take_all (the baseline lane)
    __main__.py   python -m llm ping | ask <prompt.json> | bench --dataset <dir>

The model only CHOOSES among candidates built by code (strategy/), or says
wait. It never sets a price; trading/ never reads model text. See V3 Part F.
"""

from .client import LLMClient, LLMError, LLMSettings, Reply, load_settings
from .contract import Verdict, answer_schema, check

__all__ = ["LLMClient", "LLMError", "LLMSettings", "Reply", "load_settings", "Verdict", "answer_schema", "check"]
