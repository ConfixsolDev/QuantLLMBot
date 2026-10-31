# QuantLLMBot — agent entry

Read **[`XAUUSD_SYSTEM_ARCHITECTURE_V3.md`](XAUUSD_SYSTEM_ARCHITECTURE_V3.md)** first.
It is the one and only document: architecture, code layout, rules, the
proven-harmful-changes register (A5), the change process (A6), MT5 connection
(Part D) and commands (Part F). Improve it in place; do not create other
Markdown docs, READMEs, guides or reports.

Binding:

1. Training / data / curriculum → only `model_training/CURRICULUM_AND_DATA_PREP.md`;
   new utilities only in `model_training/python_utilities_for_models/`.
2. Live code → `apps/qwen_trade_software/backend/goldflow/` (packages, absolute
   imports). `backend/*.py` are launch shims only — never add logic there.
3. Market structure (Module 1) → `apps/qwen_trade_software/backend/structure_engine/`:
   standard library only, every threshold in its JSON config, every change
   passes `python -m pytest structure_engine/tests`.
4. Live doctrine → `store/core_skill.md` + `store/sop.md` (improve, don't inflate).
5. Comment code for the next reader: a header per file (what it does, what
   feeds it, what it outputs) and a "why" next to every threshold and tricky branch.
