# Final design: freeze the build, make the logs teach

**Aim (stated):** stop development shortly, freeze the application, and shift
focus to strategy. The logs must then carry three jobs — improve the strategy,
teach the code, and produce clean training data for v5 and v6.

**Constraint accepted:** this is designed as *one* change set, applied once and
verified once. No more section-by-section edits.

Companion evidence: `dual_side_policy_study.md`.

---

## The single problem

> An outcome cannot be attributed to a cause.

That is one defect with four symptoms. Fixing them separately is what made the
work feel scattered; they are the same fix seen from four sides.

| # | Symptom | Measured |
|---|---|---|
| 1 | Prompt cannot be joined to outcome | `proposal_id` null on **3,703 / 3,703** entry decisions |
| 2 | ~~Prompt often not stored~~ **corrected** — no prompt exists for 1,878 deterministic waits (off-session, cache not ready); prompt and call-duration are perfectly correlated. Not a defect. Fixed by recording `model_called` so the two cases are distinguishable. | 1,946 model calls / 1,878 no-call |
| 3 | No record of which build produced a trade | **0 / 71** closed trades carry a build identity |
| 4 | Decision rows buried in heartbeat rows | **52,986 / 54,809** rows (96.7%), 36.1 MB of 37.4 MB |

Symptom 3 is why the study could conclude almost nothing: confidence band,
structure metadata and side mix are each near-perfectly confounded with the day
the code changed. Symptom 1 is why live trading has never fed model training.

---

## Design

Five parts. They share one idea: **every record states what produced it.**

### A. Repair the learning loop

`reviewer.py` writes the entry decision at line 1842. The proposal is not
created until line 1859. The id therefore does not exist yet.

**Change:** mint the proposal id *before* the model call and thread it through
both writes.

- Extract id generation from `append_paper_proposal()` into `new_proposal_id()`.
- Generate it at the top of the entry cycle.
- Pass it to `append_qwen_decision(proposal_id=...)` and to
  `append_paper_proposal(proposal_id=...)`.
- Store `prompt_text` unconditionally — the 51% that is dropped today is
  dropped on wait decisions, which are exactly the examples that teach
  restraint.

**Result:** `prompt → decision → proposal → fill → outcome` becomes one joinable
chain. This is the prerequisite for every training pack that follows.

### B. Build identity on every record

New `build_manifest.py`:

```
build_id = short_hash(
    source digest of the decision-relevant modules
      entry_policy, trade_geometry, management_policy, trade_manager,
      paper_executor, paper_runner, reviewer, trade_management, session_planner
  + tunables  MIN_ENTRY_CONFIDENCE, MIN_REWARD_RISK, TF_MIN_STOP, TF_MIN_TARGET,
              MAX_RISK_MULTIPLE, INITIAL_REBRACKET_SECONDS, R3_MAX_PROGRESS,
              MAX_INVALIDATION_GAP, INITIAL_STOP_DISTANCE, INITIAL_TAKE_PROFIT_DISTANCE
  + model name  + qualification_contract_hash
)
```

Stamped on: every proposal, every `mt5_execution_closed`, every management
decision. One field, `build_id`, plus `build_dirty: true` when the working tree
differs from the manifest.

Why a digest rather than a git SHA: uncommitted edits are the normal state here,
and a git SHA would have called all four of this week's distinct behaviours the
same build.

### C. Freeze, declared after this batch lands

Per your choice, the freeze is declared *after* these changes are verified over
one full session — so the baseline is the fixed system, not the broken one.

- `tools/freeze_build.py --declare` writes `frozen-build.json`.
- Every entrypoint compares its manifest at startup and logs
  `ERROR build drift: <field> changed` if it differs.
- Drift is an alarm, not a block. It must never stop trading; it must be
  impossible to miss.
- Strategy work continues through *parameters*, which are versioned in the
  manifest, so a threshold change is visible as a new build rather than an
  invisible one.

### D. Log hygiene: separate the heartbeat

- `mt5_execution_monitor` rows move to their own family,
  `paper-path-<date>.jsonl`.
- `paper-executions-<date>.jsonl` keeps only decision-bearing events —
  started, fill, skipped, closed, geometry_observation.
- Retention: path files pruned after a configurable window (default 14 days);
  decision files never auto-pruned.
- The tick path is preserved, because trade management needs MFE/MAE/giveback —
  it is simply not mixed in with the decisions.

**Effect:** the file every analysis and training script reads shrinks by ~30×.

### E. Two reports that cannot lie

**`tools/strategy_report.py`** — groups closed trades by
`build_id × (frame | side | session | trigger_tf | geometry_source)`, reusing
the existing `configuration_ledger` key. It:

- refuses to pool across `build_id`s and says so;
- refuses to state a verdict below the sample threshold, printing the n
  required instead;
- excludes `pnl_is_complete: false`.

This is the artifact strategy work runs against.

**`tools/export_training_pairs.py`** — emits one row per closed trade:
prompt · model response · decision · realised outcome · exit reason ·
management decision context · `build_id`. Homogeneous by build, so a v5 or v6
set is never assembled from mixed behaviour.

---

## What this deliberately does not do

- **No dual-side / `QWEN_POLICY_V2`.** The study found its side-commitment
  benefit already delivered by the existing funnel, its frame-coherence rule
  inert on all 71 trades, and its component scores never emitted and therefore
  unmeasured. It costs a contract change plus a retrain. Not now.
- **No threshold or geometry tuning.** Those are strategy decisions, and the
  point of this batch is to make them measurable first.
- **No training changes.** Deferred as instructed.
- **The unread `QWEN_POLICY_V2` flag is deleted.** A switch that promises a
  behaviour change and delivers none costs someone an afternoon later.

---

## Order of work

1. A + B together — they touch the same call sites in `reviewer.py`.
2. D — routing and retention.
3. E — the two reports, which are read-only and cannot affect trading.
4. Full suite + one live session verified end to end.
5. **Then** C: declare the freeze against that verified state.

Steps 1–3 are one commit. Step 5 is a separate, deliberate act.

## How we will know it worked

| check | today | target |
|---|---|---|
| closed trades joinable to their prompt | 0 / 71 | 100% |
| closed trades carrying a build identity | 0 / 71 | 100% |
| decision rows as a share of the execution log | 3.3% | >90% |
| strategy report pooling across builds | n/a | impossible by construction |

After the freeze, the honest expectation from the study stands: distinguishing a
+$20/trade improvement needs roughly 900 trades per arm. The freeze does not
make results arrive faster. It makes them mean something when they do.
