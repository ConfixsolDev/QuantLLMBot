# Stage 1 + 2 — Implementation & Validation Report

**Branch:** `feat/decision-layer-stage1-2` (off `dev`)
**Scope:** Stage 1 (safety net + observability) and Stage 2 (judgment/policy split)
**Live system:** left running throughout. All code changes are inert until restart.
**Tests:** 59 passing. **Replay:** 489 real decisions from 2026-08-10.

---

## Verdict up front

| | Status |
|---|---|
| Code correctness (tests, syntax, wiring, schema) | **Validated** |
| Guards would have caught the incident | **Validated on real data** |
| Bias detection and rejection | **Validated on real data** |
| **Trading actually restored** | **NOT yet proven — 15 samples, 93% still zero** |

The engineering is done and verified. **The behavioural fix is not confirmed.** Detail in section 5 — please read it before restarting.

---

## 1. What changed

### Stage 1 — safety net and observability

| Change | File |
|---|---|
| Added missing `import logging` (3 usages, caused ~3 failed proposals/day) | `paper_executor.py` |
| Contract rolled back to **v1.10 = a true v1.8 restore**; the v1.9 trap list removed entirely | `store/sop.md` |
| `check_legacy_contradiction()` — rejects `status=ready` with sub-threshold confidence, logs a stable code | `entry_policy.py`, wired in `reviewer.py` |
| Wait reason now names the real cause instead of blaming the cache | `reviewer.py` |
| `dealsheet:generation_failed` reason code + exception detail, replacing a bare unactionable string | `reviewer.py` |
| `entry_contract_version()` — stamps every decision with the contract that produced it | `reviewer.py` |
| **New:** 8 liveness invariants with alarm codes | `decision_liveness.py` |

### Stage 2 — judgment/policy split

| Change | File |
|---|---|
| **New:** deterministic policy engine — composes confidence, selects side, applies traps, enforces invariants | `entry_policy.py` |
| **New:** contract **v2.0** `qwen_dual_side_entry` — model returns observations for **both** sides, never a verdict | `store/sop.md` |
| **New:** `dual_side_observation_schema()` — both sides `required`, no `conditional`, no `status`, no overall confidence | `reviewer.py` |
| Feature flag `QWEN_POLICY_V2` (default **off**) | `reviewer.py` |

### Bug found *during* validation

`load_prompt_section()` did not strip HTML comments, so everything in the section body was sent to the model as instructions.

My own rollback commit added a maintainer note explaining that the previous contract *"returned confidence 0 while still emitting status ready"* — and that explanation was shipped to the model. **The fix reproduced the bug.** Replay caught it: v1.10 was still 100% zero-confidence.

Fixed three ways: the loader now strips comments (`keep_comments=True` for tooling), the maintainer note was moved outside the prompt marker, and `tests/test_prompt_hygiene.py` fails if maintainer commentary ever reaches the model again.

---

## 2. Test results — 59 passing

```
tests/test_entry_policy.py        31 passed
tests/test_decision_liveness.py   14 passed
tests/test_prompt_hygiene.py      14 passed
```

Each test names the failure it prevents. Representative:

- `test_confidence_zero_impossible_with_positive_scores` — the v1.9 signature
- `test_missing_side_is_a_contract_violation` — the 44-sell/1-buy drift
- `test_m1_trigger_cannot_fire_an_h4_zone` — the timeframe mismatch
- `test_advisory_trap_reduces_confidence_but_does_not_zero_it` — the v1.9 lesson
- `test_no_priming_phrases_reach_the_model` — the bug I introduced
- `test_ready_rate_collapse_alarms` — the 2h20m silence

---

## 3. Replay against 489 real decisions

### Attribution — the table that did not exist during the incident

| contract | n | mean conf | zero % |
|---|---|---|---|
| 1.3 | 236 | 69.2 | 0% |
| 1.6 | 35 | 63.3 | 0% |
| 1.7 | 49 | 74.4 | 0% |
| 1.8 | 2 | 81.0 | 0% |
| **1.9** | **109** | **0.0** | **100%** |
| 1.10 (new) | 15 | 2.0 | 93% |

The v1.9 regression is unambiguous and now automatically attributable.

### Guards, measured on real data

**Contradictions caught: 123 of 489.** Note these only exist in `raw_response` — the stored `execution_plan` had already been normalised to a wait, which is precisely why nobody saw them.

**Alarms that would have fired:**

| Alarm | Would have fired at |
|---|---|
| `zero_confidence_streak` | 00:35:57 UTC |
| `ready_rate_collapse` | 01:27:32 UTC |
| `contract_version_changed` | 03:09:26 UTC |
| `model_latency_high` | 04:21:03 UTC (mean 25.1s vs 30s loop) |

The incident ran unnoticed for 2h20m. The first alarm fires within five decisions.

**Invalidation coherence, cross-referenced against realised P&L:**

| | ready | traded | net P&L |
|---|---|---|---|
| Kept (gap ≤ 4) | 15 | 7 | **+574.90** |
| Rejected (gap ≥ 5) | 30 | 15 | **−823.50** |

Rejected patterns: `M1→H4` ×18, `M1→D1` ×10. Applying this rule to today would have improved realised P&L by **+823.50** — it removes exactly the M1-entry/H4-stop trades that produced every −153.5 loss.

**Directional balance:** 44 sell / 1 buy = 97.8%, against an 80% limit → **breach, alarm**. `bias=conditional` was 65.4% of decisions; the v2.0 enum removes the value entirely.

### v2.0 schema, functionally verified

```
required            : ['read', 'long', 'short', 'acknowledged_epochs', 'evidence_ids']
both sides required : True
'conditional'       : False
model can send status         : False
model can send overall conf   : False
score components    : location, response, participation, htf_alignment, plan_fit
```

The model can no longer express a verdict, an overall confidence, or a one-sided answer.

---

## 4. What is NOT fixed

**In-trade discretion (Stage 4).** Untouched. Qwen closing trades averaged **−20.22** against **+247.38** for trades left to reach TP. This is still live and still negative-expectancy.

**Fixed $3/$5 geometry (Stage 3).** Untouched. The coherence rule is implemented in `entry_policy` but only takes effect under `QWEN_POLICY_V2=1`; the legacy path still applies a constant bracket.

**Six `external_position_close` exits at exactly −3.50** (27% of trades). Still unexplained — no reconciliation loop yet.

**Change-control tooling (Stage 5).** The replay harness exists and would have caught v1.9, but nothing yet *blocks* promotion automatically.

---

## 5. The honest caveat — read before restarting

**I cannot yet confirm trading is restored.**

After the clean v1.10 went live, only 15 decisions have run against it, and 93% still return zero confidence. The three fully-clean samples were `0, 0, 30` — the `30` is the first non-zero score since 06:21 UTC, which is encouraging but is one data point.

There is also a **confound I could not resolve**, and it matters:

| | before 06:21:50 | after |
|---|---|---|
| `bias=buy` reads | 1 (conf **82**) | 111 (conf **0**, all) |
| `bias=sell` reads | 57 (conf **81.9** avg) | 1 (conf **0**) |

The market turned bullish at almost exactly the moment the contract changed. So "the prompt broke it" and "the model cannot score long setups" are nearly indistinguishable in this data.

The two crossover samples both favour the prompt explanation — a buy read *before* the change scored 82, and a sell read *after* it scored 0 — but that is one observation each. Thin.

**If, after restart, confidence recovers on bullish reads, it was the prompt.** If bullish reads keep scoring zero while sell reads recover, then `qwen-trading-v003` has a trained directional bias, and no prompt fix will address it — that would need retraining, and it would also explain the 97.8% sell skew as a model property rather than a market artifact.

Either way the symmetry monitor and the dual-side schema now make the answer visible within 50 decisions instead of invisible indefinitely.

---

## 6. Restart and rollout

Nothing is active yet — the running processes hold the old modules in memory.

1. **Restart the stack.** Stage 1 activates: contradiction guard, alarms, reason codes, contract-version stamping, and the `logging` fix.
2. **Watch for the first hour.** Expect `contract_version_changed` immediately. Then check `mean_confidence` recovers to the 63–81 band and `zero_confidence_streak` stops firing.
3. **Re-run the replay** — `python tools/replay_decisions.py` — and read row `1.10`.
4. **Only then** consider `QWEN_POLICY_V2=1` for Stage 2, ideally in shadow first.

### Git note

`.git/index.lock` is present (0 bytes) and blocked commits. I did not delete it — a live git process may own it, and that is your call, not mine. The branch `feat/decision-layer-stage1-2` exists and carries all work; your pre-existing uncommitted changes to 74 files came across with it and are intact. Once the lock clears, commit the baseline separately from this work if you want a clean diff.

---

## 7. Files

**New**

```
apps/qwen_trade_software/backend/entry_policy.py
apps/qwen_trade_software/backend/decision_liveness.py
apps/qwen_trade_software/backend/tools/replay_decisions.py
apps/qwen_trade_software/backend/tests/test_entry_policy.py
apps/qwen_trade_software/backend/tests/test_decision_liveness.py
apps/qwen_trade_software/backend/tests/test_prompt_hygiene.py
```

**Modified**

```
apps/qwen_trade_software/backend/reviewer.py             guard, alarms, v2 schema, codes
apps/qwen_trade_software/backend/paper_executor.py       import logging
apps/qwen_trade_software/backend/market_context_cache.py comment stripping
store/sop.md                                             v1.10 restore, v2.0 contract
```
