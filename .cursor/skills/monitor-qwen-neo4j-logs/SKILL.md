---
name: monitor-qwen-neo4j-logs
description: Reviews QuantLLMBot training, Qwen, runtime, and Neo4j logs for accuracy and root causes; applies narrowly proven bug fixes with tests and requests approval before upgrades, dependency changes, model changes, or architectural changes. Use when monitoring training or live-system logs, checking Neo4j graph health, diagnosing Qwen failures, or performing the recurring 10-minute log review.
---

# Monitor Qwen and Neo4j Logs

Work in `E:/QuantLLMBot`. Treat `neoj` as Neo4j.

## Authorities and boundaries

1. Read and follow `AGENTS.md`.
2. For training, curriculum, data preparation, or model-job questions, use only `model_training/CURRICULUM_AND_DATA_PREP.md`. Do not create another training-process document.
3. For architecture, use only `XAUUSD_SYSTEM_ARCHITECTURE_V2.md` and improve it in place only after approval when the change is architectural.
4. Keep live code in `apps/qwen_trade_software/`, Colab pipeline code in `scripts/`, and any new curriculum/data Python in `model_training/python_utilities_for_models/` after inspecting that folder.
5. Preserve unrelated and pre-existing worktree changes. Inspect `git status --short` and relevant diffs before editing; do not overwrite or revert user changes.
6. Never expose secrets from environment variables, connection strings, logs, or configuration.

## Each monitoring run

1. Establish the review window from the prior run or, when unavailable, the last 15 minutes. Record the current UTC time and inspect only new or changed evidence first.
2. Determine whether training or evaluation is active. Inspect process state and the newest available training/evaluation output. Do not claim training accuracy from a runtime health log.
3. Review live evidence under:
   - `apps/qwen_trade_software/backend/logs/`
   - `model_training/tick_data/YYYY-MM-DD/`
   - `apps/qwen_trade_software/backend/cache/`
4. Review at minimum the current Qwen I/O and decision JSONL, reviewer/runtime logs, proposal/execution/review/trade-step JSONL, and Neo4j worker log plus graph health/context snapshots when present.
5. Validate log accuracy instead of trusting severity labels:
   - parse JSON/JSONL and count malformed or truncated records;
   - verify timestamps are parseable, monotonic where required, and within the review window;
   - correlate proposal, decision, execution, review, position, and episode identifiers;
   - compare hot logs with permanent tick-archive copies without modifying either;
   - check required Qwen contract fields, model name/digest, prompt/response success, latency, timeouts, empty responses, confidence, acknowledged epochs, and cited evidence;
   - distinguish expected `wait`, safety-gate, market-closed, and optional-service states from failures;
   - check Neo4j worker status, connection errors, outbox pending/failed counts, watermark/projection lag, snapshot freshness, schema version, and idempotent replay signals;
   - remember that SQLite and immutable evidence are authoritative and Neo4j is optional; Neo4j failure must not block collection, Qwen’s SQLite baseline, execution, protection, or reconciliation.
6. If curriculum files or the training pipeline changed, run the existing blocking dataset audit and relevant preprocessing/evaluation checks described by `model_training/CURRICULUM_AND_DATA_PREP.md`. Reuse utilities from `model_training/python_utilities_for_models/`; do not invent a parallel audit.
7. Trace every anomaly to the earliest supported cause using logs, code, configuration, process state, and targeted tests. Label an inference as an inference. Do not diagnose from a single error line when correlated evidence is available.

## Fix policy

Apply a fix automatically only when all are true:

- the defect is reproducible or strongly evidenced;
- the change is narrow, reversible, and consistent with the protected V2 architecture;
- it does not change trading strategy, risk limits, model weights/tag, prompts/doctrine, dataset labels, Neo4j schema, dependencies, credentials, deployment, or service configuration;
- it does not overlap unexplained user changes;
- a focused regression test can be added or an existing test proves the fix.

After editing, run the smallest relevant tests, then a broader nearby suite when practical. Re-read the new logs or reproduce the path when possible. Do not restart, deploy, retrain, switch models, or change a live service automatically.

If the evidence is insufficient, the fix fails verification, or the issue crosses a boundary above, leave files unchanged and report the blocker.

## Approval-gated improvements

Suggest, but do not apply, upgrades involving Qwen model selection or retraining, prompt/doctrine changes, Neo4j version/schema/index/topology changes, packages, infrastructure, performance tuning with behavioral risk, architecture, trading logic, thresholds, or risk controls.

For each suggestion provide: evidence, root cause, proposed change, expected benefit, risk, validation plan, rollback plan, and the exact approval requested. Wait for explicit user approval.

## Run report

Return a concise update in the task; do not create a report markdown file. Include:

- review window and training/runtime state;
- healthy checks and evidence freshness;
- anomalies ranked critical/high/medium/low with exact file or component evidence;
- root causes, separating confirmed findings from inferences;
- fixes applied, files changed, and tests run;
- unresolved risks;
- approval-required upgrade suggestions, or `None`;
- next monitoring action.

If nothing changed, say so briefly and include the latest evidence timestamp. Never imply that a model, Neo4j, training job, or live service was checked when its evidence was unavailable.
