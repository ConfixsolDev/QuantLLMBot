<!-- document: QuantLLMBot proven harmful changes | version: 1.0 | audience: coding agents and human reviewers -->
# Proven Harmful Changes — Do Not Reintroduce Register

## Purpose and authority

This file preserves negative engineering knowledge: changes that appeared
safer or stricter but were shown by replay or MT5 demo evidence to suppress
valid behavior, create contradictory execution, or contaminate decisions.
Coding agents must read this file before changing entry validation, freshness,
confidence, evidence-citation, cache-provenance, or outcome-feedback behavior.

This is an engineering change-control register. It does not replace the market
doctrine in `store/core_skill.md`, the model contract in `store/sop.md`, or the
research approval process in `RESEARCH_LOOP.md`.

## Mandatory coding-agent procedure

Before adding, tightening, relaxing, or moving a gate:

1. Search this register for the proposed mechanism and its functional
   equivalent, not only the same variable or function name.
2. Reproduce the original evidence and the protected counter-case.
3. State why the proposal does not reintroduce an active rejected pattern.
4. Preserve the listed safe replacement and companion controls.
5. Add or update a deterministic regression invariant.
6. Run `validation/validate_e2e.py`.
7. Obtain explicit human approval before reopening an active rejection.

Renaming a rejected gate, moving it to another layer, or expressing it through
a prompt is still reintroduction. A code cleanup, safety argument, loss, or
single profitable example is not sufficient reopening evidence.

## Active do-not-reintroduce register

### PHC-001 — Exact post-Qwen M1/M5 identity gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Require current M1/M5 epochs, named-level IDs, or
  named-level prices to remain exactly equal to the entry snapshot after Qwen
  returns.
- **Evidence:** On 2026-08-05, proposal
  `paper-20260805T055843-3f41f811` returned a coherent confidence-73 buy. The
  exact-level runtime gate rejected it through
  `current_level_entry_low_id_changed`,
  `current_level_entry_high_id_changed`, and
  `current_level_target_level_id_changed`. These low-timeframe references had
  rotated during the approximately eight-minute CPU calculation.
- **Observed harm:** With uncapped Qwen time, M1/M5 objects normally advance
  before the response. Exact equality converts routine calculation latency
  into a near-universal no-trade rule.
- **Safe replacement:** Validate the cache-qualified snapshot and Qwen's
  acknowledged provenance before proposal creation. At execution, require
  confidence/direction coherence, current cache readiness, the same permitted
  UTC session/date, unchanged structural/playbook context, the same model
  digest, a current MT5 tick, live entry-zone eligibility, and the 60-second
  post-response lifetime.
- **Protected counter-case:** Proposal
  `paper-20260805T060621-c8536c12` crossed the 06:00 UTC H1 close and was
  correctly rejected because H1 changed from rejection/inside-range to
  acceptance/above-range. Higher-timeframe structural change must remain a
  runtime rejection.
- **Regression invariant:** Runner freshness compares only stable
  structural/playbook epochs; it must not compare current M1/M5 level identity
  or the minute/levels epochs for exact equality.
- **Introduced/removal boundary:** The harmful exact-level check was removed in
  Git commit `05c3fb7` after live-chain verification.
- **Reopening criteria:** A preregistered alternative must distinguish routine
  low-timeframe rotation from semantic invalidation, preserve materially more
  eligible decisions than exact equality, and pass untouched replay plus demo
  shadow evidence with explicit human approval.

### PHC-002 — Universal mandatory M1-and-M5 citation gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Require every ready entry to cite both an M1 candle and
  an M5 candle, regardless of which supplied timeframes establish the setup.
- **Evidence:** Proposal `paper-20260805T021044-08c9dcd7` cited closed
  D1/H4/H1/M30/M15 evidence, returned a coherent confidence-73 buy, and closed
  at broker-net `+1403.70`. It did not cite M1 or M5.
- **Observed harm:** Citation lists identify the facts Qwen relied on; they are
  not a checklist requiring every timeframe. A universal dual-timeframe gate
  would reject valid higher-timeframe structure even though M1/M5 facts remain
  supplied for timing and deterministic geometry.
- **Safe replacement:** Require a non-empty citation list that is a subset of
  the cache-owned evidence IDs. Keep M1/M5 data available and distinguish
  completed from forming candles, but let the cited evidence reflect the
  actual thesis.
- **Regression invariant:** Provenance validation checks ownership and
  existence of cited evidence; it does not require both M1 and M5 membership.
- **Reopening criteria:** Only multi-cohort evidence showing that a specific
  setup class requires named low-timeframe confirmation may support a scoped
  rule. A universal requirement remains prohibited without explicit human
  approval.

### PHC-003 — Recent profit/loss as a direction or entry gate

- **Status:** `DO_NOT_REINTRODUCE`
- **Rejected behavior:** Feed recent execution outcomes into the next market
  snapshot or block/force buy, sell, or wait because recent trades won or lost.
- **Evidence:** The user-approved research principle is that a logically valid
  trade may lose. Outcome analysis is already isolated from the entry packet,
  and the E2E validator protects the absence of `recent_execution_outcomes`
  from reviewer entry context.
- **Observed harm:** Outcome-conditioned direction introduces recency bias and
  allows P&L to override current closed market facts. It also makes entry
  behavior non-reproducible across otherwise identical snapshots.
- **Safe replacement:** Use outcomes only in the separate evidence/research
  loop. Promote a behavior change only after preregistered, repeated evidence
  and human review.
- **Regression invariant:** The next entry snapshot contains market facts and
  approved knowledge, never recent win/loss direction feedback.
- **Reopening criteria:** None through an ordinary code change. This requires a
  separately approved research hypothesis and a versioned model contract.

## Companion controls that must remain

Relaxing a harmful gate does not authorize removal of these controls:

- Ready entries require confidence 51–100.
- Confidence is a coherence qualification, not a profit guarantee.
- Bias must be explicit buy or sell and must agree with plan side.
- Missing or malformed confidence is zero, not an invented passing default.
- Qwen citations must be non-empty and cache-owned.
- Current cache readiness, UTC trading date/session permission, stable
  structural/playbook context, and model identity are rechecked before entry.
- The executor rechecks MT5 demo mode, current tick, live entry range, geometry,
  one-position ownership, and the 60-second post-response deadline.
- A real H1/H4 structural change during inference expires the proposal.
- Previous wins and losses do not decide the next direction.

Historical evidence includes two confidence-zero fills on 2026-08-05:
`paper-20260805T034422-942a705d` closed `-21.85`, and
`paper-20260805T044406-b6480bf7` closed `-153.50`. Their combined loss of
`-175.35` does not prove every low-confidence trade loses; it proves that a
ready plan must not contradict an explicit zero-confidence judgment.

## Record template for future findings

```text
Pattern ID:
Status: CANDIDATE | DO_NOT_REINTRODUCE | SUPERSEDED
Rejected behavior:
Evidence IDs and version boundary:
Observed harm and mechanism:
Safe replacement:
Protected counter-case:
Required regression invariant:
Removal commit or deployment boundary:
Reopening criteria:
Human approval:
```

Add a record only after evidence identifies the mechanism. Do not turn a
preference, one loss, or one win into permanent negative knowledge.
