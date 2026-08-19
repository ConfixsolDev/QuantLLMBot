# Dual-Side Sanity Check — Problem & Complete Solution Draft

**Status:** Design draft for operator review (discussion / study). **Not an implementation order.**  
**Date:** 2026-08-13  
**Scope:** Live paper system + V5 curriculum + doctrine (Brooks / Grimes / Dalton).  
**Non-goal:** Do not invent a second entry doctrine. Do not force opens from dual scores.

---

## 0. One-sentence thesis

Markets always offer two sides; our **direction is usually right**, but we sometimes enter when the **opposite side’s setup is more complete** (or ours is incomplete). Cure: keep current side as governor; use dual-side only as a **sanity veto** — confirm, wait, or revise — never as a second broker engine.

---

## 1. The problem (what is actually broken)

### 1.1 Symptom (last ~2 trading days)

Closed-trade audit (Aug 12–13) showed a clear split:

| Form | Count | Net | Meaning |
|------|------:|----:|---------|
| Well-formed location/geometry | 5 | ~+$908 | Pullback / room / cleaner stack |
| Not well-formed | 11 | ~−$1,400 | Spike / structure low / HTF + micro stop |
| Unclear | 10 | ~+$1,160 | Mixed |

Standout failures:

- Sell ~4429 (−147): correct bearish lean, **sold expand / spike** before pullback.  
- Sell ~4406 (−162): correct bearish lean, **sold structure low** before pullback.  
- Later hours printed **better sell prices** (pullback highs ~4412–4414).  

**Verdict:** Side accuracy was often good. **Location / completeness** was not.

### 1.2 Root causes (layered)

```
Regime unclear or ignored
    → Location wrong (extreme / mid-range / before pullback)
        → Trigger too early (M1 pin as “enough”)
            → Confidence fake (flat ~68 live; train opens often 80%+)
                → System opens a one-sided story without asking:
                   “Is the other side more complete?”
```

Concrete gaps:

1. **One-sided narrative** — Model emits a sell story; does not formally score the buy case (or vice versa).  
2. **Pin vocabulary overweight** — “M1/M5 pin + level name → ready” dominates training/live summaries.  
3. **Pullback underweight** — Topics 07 teach L2 / breakout-pullback; live still fires at extremes.  
4. **Confidence uncalibrated** — High % does not mean complete stack; live ready often stuck ~60–69.  
5. **Cooldown / gates ≠ edge** — Long loss cooldown hid repeat low-pins; did not select better prices.  
6. **Prior full dual-side revive** — `entry_policy` dual path was studied as partly inert/redundant; full revive would disturb a direction path that already works.

### 1.3 What is *not* the problem

- Not “we never know the side.”  
- Not “we need ICT confluence stacks.”  
- Not “ATR alone invents direction.”  
- Not “always be in both long and short” (Barmish SLS-style).  

---

## 2. Why dual possibility always exists (doctrine)

Governing books (already distilled):

| Job | Books | Topic |
|-----|-------|-------|
| Trend / pullback / always-in | Brooks *Trends*, Grimes, Dalton | `07_trend_trading.md` |
| Range / two-sided / mid skip | Brooks *Ranges*, Dalton | `08_range_trading.md` |
| Reversal restraint | Brooks *Reversals*, Grimes | `09_reversal_trading.md` |
| TF hierarchy (M1 noise, M5 timing) | Elder, Brooks, Grimes | `04_timeframe_relations.md` |

Load-bearing ideas:

- **Always-in (Brooks):** If forced to choose a side, which? That is a *bias*, not a command to open.  
- **Ranges are two-sided:** Both fades can be valid at outer thirds; middle ≈ 50/50 → skip.  
- **Grimes after a large move:** The real question is continuation vs fade — two hypotheses.  
- **Reversals usually birth a range**, not an instant opposite trend.  

So: dual-side thinking is **native to the books**. Dual-side *forcing an open* is not.

---

## 3. Why we need a cure (motivation)

### 3.1 Without a sanity check

- Primary sell can fire while buy-at-support is the complete stack (flush hold).  
- Primary sell can fire while short case itself is incomplete (no pullback).  
- Operator sees “high confidence” and assumes the other side was considered — it was not.  
- Training reinforces one story → one-sided drift risk (historical 44 sell / 1 buy days).  

### 3.2 With the agreed sanity check

Ask only: **“Could the opposite side be more complete?”**

| Opposite side | Action |
|---------------|--------|
| More complete than primary | **Wait or revise** (do not open primary) |
| Weak / missing pullback / mid-range | **Confirm primary** (leave direction path alone) |
| Both mid / both incomplete | **Wait** — never open because both got a number |

This protects location quality **without rewriting direction doctrine**.

### 3.3 External research cousins (study list)

Not identical products — same *job*:

| Source | Lesson |
|--------|--------|
| AQR — *To Trade or Not to Trade?* | Primary plan; secondary signal **confirms or cancels**; conflict → wait |
| Aligrithm — long/short tested separately | Two hypotheses, not one mirrored indicator |
| Meta-gating ensembles | Meta-rule **creates no trades**; only veto/confirm |
| Brooks / Grimes / Dalton | Always-in + two-sided range + sit out when unclear |

**Nobody must ship “our exact LLM dual entry” for the idea to be sound.** The conservative branch (governor + veto) is how robust systems resolve dual possibility.

---

## 4. Solution definition (what “done” means)

### 4.1 Product rule (immutable)

1. **Primary path unchanged** — plan / always-in / current entry decision still owns side.  
2. **Sanity layer** — after a candidate ready (or strong lean), score opposite completeness.  
3. **Sanity may only:** `confirm_primary` | `wait` | `revise` (revise = soften to wait / ask for missing fact).  
4. **Sanity may never:** force open, flip side solely from a mid score, or require dual opens every tick.  

### 4.2 Completeness stack (shared language)

Both sides scored with the **same** checklist (book order):

```
1. Regime   — trend vs range (ATR3/51 ratio = hint only, not governor)
2. Location — pullback / outer third / not mid / not climax extreme
3. Trigger  — closed M5 preferred; M1 pin alone = incomplete
4. Confidence — reflects stack completeness, not pin loudness
```

**Complete** ≈ regime clear + location valid + closed M5 (or equivalent closed response) + no hard skip.  
**Incomplete** ≈ missing pullback, mid-range, expand-at-extreme chase, M1-only, climax restraint, etc.

### 4.3 Decision table

| Primary | Opposite | Sanity outcome |
|---------|----------|----------------|
| Complete | Incomplete | `confirm_primary` → allow ready |
| Complete | Also complete, similar score | `wait` (gap small → coin flip) |
| Complete | More complete | `wait` or `revise` |
| Incomplete | Anything | `wait` (primary should not have been ready) |
| Either | Mid-range only | `wait` |

---

## 5. Complete cure by area

### 5.1 Doctrine / skill (store + topics)

**Cure:** Do not add a new “dual entry doctrine.” Annotate operating rule:

- Always-in / plan = **primary side**.  
- Opposite side = **challenge question**, not a second always-in.  
- Cite topics 07–09 + 04 only.

**Keep lean:** one short principle in curriculum (already seeded: dual-side compare / regime→location→trigger). Avoid bloating `core_skill.md` until live v1 proves useful.

### 5.2 Curriculum / model training

**Cure:** Teach the *habit*, not a second live contract yet.

Already prepared (V5 packs):

- Regime + ATR3/51 + pullback + conf hygiene (`append_regime_atr_v5.py`)  
- Dual-side idea rows with `side_ideas` + pick/wait (`append_dual_side_ideas_v5.py`)  
- M5 confirm / M1 noise (`append_m5_confirm_v5.py`)  
- FVG/OB as literature zones only (`append_fvg_ob_literature_v5.py`)  

**Training posture:**

- Opens: conf mostly **58–72** when stack complete; reserve 80+ for rare A+.  
- Pin-only / before-pullback: **wait**, conf ≤62.  
- Dual rows: always show long + short cases; pick or wait.  
- Sample Prepared already surfaces ATR3/51 ratio, Trigger TF, Side Ideas.  

**Weekend train:** freeze → Colab QLoRA → holdout; promote only if wait/skip quality does not degrade.

**Explicit:** Live dual `entry_policy.decide()` revive remains **deferred** until sanity v1 is proven.

### 5.3 Live runtime (technical shape — when approved)

Recommended sequence (light → heavy):

**Phase A — Code sanity checklist (v1)**  
After primary `ready`:

- Build opposite case from **existing facts** (levels, session extreme, pullback flag, closed M5 if available, mid-range, expand hint from `atr_ratio_3_51`).  
- If opposite_complete > primary_complete → downgrade to `wait` + reason.  
- If opposite weak → no-op (confirm).  
- Log every sanity decision for audit.  

**Phase B — Optional narrow model call**  
Same model, tiny schema: `sanity: confirm_primary|wait|revise`, `opposite_missing_fact`, optional scores.  
Cannot emit a new ready open.  

**Phase C — Train absorbs habit**  
After A/B data exists, next LoRA sees real confirm/wait labels from live logs.

**Do not start with** full dual observation schema as the only entry path.

### 5.4 Prompts / contracts

**Cure when Phase B is wanted:**

- Keep current entry prompt for primary.  
- Add **appendix or second call**: “Opposite-side completeness only; outcomes confirm|wait|revise.”  
- Enum-constrain outputs (no `conditional` drift, no silent omission of opposite).  

Primary contract remains the doctrine carrier.

### 5.5 Confidence

**Cure:**

- Confidence = completeness of **chosen** stack.  
- Sanity wait does not invent 90% on the other side.  
- If both sides ~tied → wait at ~50, not “pick the 62 over the 60.”  

### 5.6 ATR / regime helpers

**Cure already in motion:**

- Live + V5: `atr_m1_51`, `atr_m1_3`, `atr_ratio_3_51`.  
- Use as **expand/compress hint** inside completeness (e.g. expand-at-extreme → primary short incomplete).  
- **No hard-coded ratio gates** as the edge.  

### 5.7 Timeframes (M1 vs M5)

**Cure:**

- M1: ATR + probe context (noise for breaks).  
- M5: preferred **closed trigger** for completeness.  
- M5 impulse must not flip H4 bias (topic 04).  

### 5.8 FVG / Order block

**Cure:** Optional location *aliases* (micro gap / impulse origin) under HTF bias — never ICT stacks, never dual-side story fuel.

### 5.9 Risk / geometry / cooldown

**Cure:**

- HTF thesis + micro $3 bracket remains a geometry/process issue (separate from dual-side).  
- Cooldown = hygiene after loss; **not** the dual-side cure.  
- Sanity wait is preferred over long cooldown as the location teacher.  

### 5.10 Observation / evaluation

**Cure — measure before celebrating:**

| Metric | Intent |
|--------|--------|
| % ready blocked by `opposite_more_complete` | Sanity is firing |
| P&L of blocked vs would-have-taken (paper shadow) | Did veto help? |
| Primary side hit-rate before vs after | Doctrine not harmed |
| Wait rate / opportunity cost | Not freezing the system |
| Conf calibration (open conf vs outcome) | Less fake certainty |

Shadow mode first: log what sanity *would* do for N days without blocking.

### 5.11 What we explicitly will not do

- Replace Brooks/Dalton regime with ATR-only regime.  
- Force open when both sides score mid.  
- Revive full live dual-side decide as the main path without Phase A proof.  
- Stack cooldowns + many new gates in one PR.  
- Treat SLS “always long-and-short controllers” as the model for gold scalps.  

---

## 6. End-to-end flow (target)

```text
Facts (levels, session, ATR3/51, candles)
        │
        ▼
Primary decision path (unchanged doctrine)
        │
        ├─ wait/skip ─────────────────────────────► done
        │
        └─ ready candidate
                │
                ▼
        Opposite completeness score
                │
                ├─ opposite stronger ──► wait / revise
                ├─ both mid / tied ────► wait
                └─ opposite weak ──────► confirm_primary ► execute
```

---

## 7. Phased rollout (operator checklist)

| Phase | Work | Gate to next |
|-------|------|--------------|
| **0 Study** | Read Grimes continuation-vs-fade; Brooks always-in/range; AQR confirm/cancel; this draft | Operator agrees rules |
| **1 Shadow** | Code checklist logs only; no block | ≥ few days; vetoes look sane on known bad trades (−147/−162 class) |
| **2 Enforce** | Sanity can downgrade ready→wait | Direction hit-rate stable; fewer extreme entries |
| **3 Optional prompt** | Narrow second call | Latency OK; schema obeyed |
| **4 Train** | Next weekend LoRA includes live sanity labels + existing packs | Holdout wait/skip OK |
| **5 Revisit full dual decide** | Only if Phase 2–4 still insufficient | Fresh study vs old inert dual_side findings |

---

## 8. Mapping to known bad / good trades (worked intuition)

| Event | Primary | Opposite | Sanity should |
|-------|---------|----------|---------------|
| Sell 4429 spike | Sell incomplete (expand extreme) | Buy not necessarily complete | **Wait** (primary incomplete) |
| Sell 4406 day low | Sell incomplete (no pullback) | Buy-at-support may be forming | **Wait** (and/or revise) |
| Pullback sell at ~4414–4418 after fail | Sell complete (location+trigger) | Buy weak | **Confirm** |
| Well buy ~4407 after flush | Buy complete | Sell-the-low incomplete | **Confirm** buy |
| Mid-box pin either side | Either incomplete | Other incomplete | **Wait** |

---

## 9. Ownership of artifacts

| Area | Owner artifact |
|------|----------------|
| Process / curriculum size / ATR fields | `model_training/CURRICULUM_AND_DATA_PREP.md` |
| Distilled books | `model_training/knowledge/topics/07–09, 04` |
| Live ATR | `apps/qwen_trade_software/backend/market_atr.py` |
| Parked full dual decide note | `reviewer.py` comment; this draft supersedes missing study for *sanity* scope |
| This design | `apps/qwen_trade_software/docs/research/dual_side_sanity_check_design.md` |

Pack utils (already in repo for training fuel):

- `append_regime_atr_v5.py`  
- `append_dual_side_ideas_v5.py`  
- `append_m5_confirm_v5.py`  
- `append_fvg_ob_literature_v5.py`  

---

## 10. Success definition

We are cured when:

1. Direction doctrine still drives side (no dual-engine drift).  
2. Extreme / before-pullback readies are **waited** more often (shadow→enforce).  
3. Well-formed pullback / outer-third / compress-at-edge trades still reach ready.  
4. Confidence tracks completeness, not pin volume.  
5. Operator can read one log line: `sanity=confirm|wait` + opposite missing fact.  

---

## 11. Operator decision (required before any code)

Choose one:

- **A)** Study only (this draft + reading list) — no engineering.  
- **B)** Phase 1 shadow checklist only.  
- **C)** Phase 1–2 enforce wait.  
- **D)** Include Phase 3 narrow prompt.  

Default recommendation: **A → B → C**; train (Phase 4) on the next weekend cycle after shadow looks right.

---

*End of draft. Implementation starts only on explicit operator request.*
