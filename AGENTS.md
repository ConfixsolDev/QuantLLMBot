# QuantLLMBot — agent entry

Read **[`XAUUSD_SYSTEM_ARCHITECTURE_V3.md`](XAUUSD_SYSTEM_ARCHITECTURE_V3.md)** first — the one and
only document: rules (Part A), the structure engine (Part B), the application (Part C), MT5 (Part D),
and lessons for rebuilding Qwen (Part E). Improve it in place; do not create other Markdown files.

Binding:

1. `backend/structure_engine/` — deterministic, standard library only, every threshold in its JSON
   config, closed candles only. Keep `python -m pytest structure_engine/tests` green.
2. `backend/quantllm/` — the application (database, MT5 feed, service, API). Keep
   `python -m pytest quantllm/tests` green. It reads market data only; it places no orders.
3. `web/` — the website; it draws only what `/api/chart` and `/api/snapshot` return.
4. No dead code, no duplicate copies, no scratch files in the repo (use the git-ignored `_archive/`).
5. Comment for the next reader: a header per file (what it does, what feeds it, what it outputs) and a
   "why" next to every threshold and tricky branch.
