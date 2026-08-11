# Target Design — How the Trading System Should Work

**Purpose:** not a fix list. This describes the shape the system should have so that today's failures become *structurally impossible* rather than repeatedly patched.

**Grounded in:** 2026-08-10 audit — 433 proposals, 45 ready, 22 closed, net −248.60, 27.3% win rate, 97.8% sell-only, 2h20m silent outage from a prompt edit.

---

## 1. The underlying problem

Every failure found today traces to **one architectural mistake**:

> The language model is being asked to *decide*, when it should only be asked to *observe*.

Because the model holds the decision, one prose edit (v1.8 → v1.9) silently changed policy for the entire system. Nothing broke, nothing errored — the system just quietly stopped trading for 2h20m. That is the signature of policy living inside a prompt.

The same mistake produces the other findings:

| Symptom | Root |
|---|---|
| `confidence: 0` + `status: "ready"` | Model owns both measurement and permission — they can contradict |
| 97.8% sell-only | Nothing structurally requires both sides to be considered |
| M1 entry + H4 stop + fixed $3 | Three different timeframes, no rule binding them |
| Qwen closes turn +247 into −20 | Unbounded discretion in-trade |
| 2h outage unnoticed | No invariant that says "this state is impossible" |
| Bare `generation failed` | Errors as prose, not as codes |

**Fixing v1.9 restores trading. It does not stop the next v2.0 from doing the same thing.**

---

## 2. Governing principle

> **The model judges. The code decides. The broker executes.**

Three consequences:

1. **The model never emits a verdict.** No `ready`. No `wait`. It emits *observations with scores*.
2. **Permission is computed by deterministic code** from those observations. Policy is versioned, testable, diffable — not paragraphs of English.
3. **Any change to policy is a code change with a test**, not a prompt edit that ships silently.

---

## 3. Layer architecture

| Layer | Owns | Must never |
|---|---|---|
| **Perception** (cache) | Facts: candles, levels, sessions, volume, playbooks | Have an opinion |
| **Judgment** (Qwen) | Reading structure, scoring quality per side | Grant permission, size, or pick the bracket |
| **Policy** (code) | Gating, side selection, geometry, risk, cooldowns | Call the model |
| **Execution** (runner) | Placing and reconciling orders | Interpret anything |
| **Supervision** (monitors) | Liveness, distributions, drift, rollback | Be optional |

Today, Judgment and Policy are fused inside one prompt. Splitting them is the whole design.

---

## 4. The decision contract, redesigned

### 4a. What the model returns today (broken)

```json
{ "bias": "buy", "confidence": 0,
  "execution_plan": { "status": "ready", "reason": "bullish bias confirmed" } }
```

One opaque number, plus a verdict, which can contradict it — and did, 72 times in two hours.

### 4b. What it should return

The model scores **both sides, every call**, on named components. It never says yes or no.

```json
{
  "read": {
    "htf_auction": "bullish_unfinished",
    "htf_timeframe": "H4",
    "location": "at_M30_previous_low",
    "acceptance": "none"
  },
  "long": {
    "zone_id": "M30_PREVIOUS_LOW",
    "invalidation_id": "H1_PREVIOUS_LOW",
    "trigger_tf": "M5",
    "scores": { "location": 8, "response": 6, "participation": 5, "htf_alignment": 9, "plan_fit": 7 },
    "response_observed": true,
    "traps_triggered": []
  },
  "short": {
    "zone_id": "M15_PREVIOUS_HIGH",
    "invalidation_id": "H4_PREVIOUS_HIGH",
    "trigger_tf": "M1",
    "scores": { "location": 4, "response": 3, "participation": 2, "htf_alignment": 1, "plan_fit": 2 },
    "response_observed": false,
    "traps_triggered": ["fade_acceptance", "sell_into_support"]
  },
  "acknowledged_epochs": { ... },
  "evidence_ids": [ ... ]
}
```

### 4c. Why this shape fixes things

- **Confidence is computed, not declared.** Code composes the five sub-scores into a confidence with a fixed, versioned weighting. `confidence: 0` alongside a bullish narrative becomes arithmetically impossible — a 0 would require every component to be 0, which contradicts the observations the model itself supplied.
- **Contradiction becomes detectable.** `traps_triggered: []` with `scores` near zero is an internal inconsistency the code can reject and log, instead of silently waiting.
- **Traps become data, not instructions.** The model *reports* which traps it sees. Code decides what a trap costs. Adding trap #10 no longer risks zeroing the entire confidence distribution — the failure mode of v1.9.
- **Both sides are always priced.** Which leads directly to the bias fix.

---

## 5. Bias elimination by construction

Today: 44 sell, 1 buy. Nothing in the design required the long case to ever be considered.

**Rule: every decision call scores long *and* short. Code takes the higher-scoring side, if it clears the bar.**

This removes one-sided drift structurally — the model cannot "forget" a direction, because an empty long block is a schema violation, not a silent omission.

Add two supervisory controls on top:

1. **Rolling symmetry monitor.** Over the trailing 50 ready decisions, if one side exceeds ~75%, raise an alert and require a higher score for that side until balance recovers. A genuinely trending day will still trade one-sided — but it does so *visibly*, with the imbalance recorded, rather than invisibly.
2. **Side-neutral prompt discipline.** No example, no phrasing, no trap in the contract may name a direction asymmetrically. Every rule stated for buy must have its mirror stated for sell, in the same words. Today's trap list does this correctly; the confidence guidance does not.

**Also enforce the enum.** `bias: "conditional"` appeared in 71% of decisions despite the contract forbidding it. Prose instructions do not constrain output — **schemas do**. If the value isn't allowed, it must not be in the response schema.

---

## 6. Timeframe coherence law

This is the largest money leak. Today: **M1 entry trigger → H4 invalidation → fixed $3 stop**. Three unrelated frames. The stop sat a median **1.18** inside the structural invalidation, so ordinary noise removed the position before the H4 thesis could resolve. All five −153.5 losses came from this.

The evidence is unambiguous:

| Anchor | n | net | win rate |
|---|---|---|---|
| **M30** | 6 | **+385** | **67%** |
| H4 | 7 | −117 | 14% |
| H1 | 6 | −316 | 17% |
| M15 | 2 | −198 | 0% |

### The law

> **A trade has one frame. Trigger, invalidation, and target must all belong to it, and the stop must sit beyond the invalidation — never inside it.**

Concretely:

1. **Declare the trade frame** (e.g. M30). It is the frame the *zone* belongs to.
2. **Trigger timeframe** may be the frame or one step below (M30 frame → M15 or M30 trigger). An M1 wick may never trigger an H4 trade — the model already states this correctly as trap #6; it must become a code constraint.
3. **Invalidation** is the named structural level *of that frame*.
4. **Stop is placed beyond invalidation**, plus a volatility buffer (e.g. a fraction of the frame's ATR). Never a constant.
5. **If the resulting stop distance exceeds the risk budget, the trade is not taken** — it is not re-cut down to $3. Sizing adapts, or the trade is skipped.
6. **Target is a structural level of the same frame**, and the trade is only permitted if `reward / risk` clears the minimum after costs.

### Why fixed $3 / $5 must go

Fixed geometry gave a nominal 1:1.61, requiring a **38.3%** win rate to break even. The system delivered **27.3%**. But the fixed stop is itself a *cause* of the low win rate — it converts "thesis wrong" into "noise stopped me out". The bracket must be a consequence of structure and volatility, not a constant applied to every setup regardless of frame.

**Position size becomes the free variable, not the stop.** Risk per trade is fixed in currency; the stop is where structure says it is; size = risk ÷ stop distance.

---

## 7. In-trade management: rules, with discretion only in one direction

Today's numbers are stark:

| | n | avg |
|---|---|---|
| Left alone to TP | 3 | **+247.38** |
| Qwen chose to close | 8 | **−20.22** |

Discretionary closing is negative-expectancy. But the answer is not "remove the model" — it is **to bound what discretion can do**.

> **The model may improve the trade's risk. It may not end the trade on opinion.**

Permitted model actions in-trade:

- **Tighten stop** toward breakeven or behind a newly formed structural level
- **Flag named invalidation breached** — a specific level ID, with the closed candle that breached it

Not permitted:

- Closing because the read "changed"
- Closing on unrealised P&L
- Moving the target closer

Exits become deterministic: **target reached**, **stop hit**, **named invalidation closed through**, or **time stop** (the frame's expected resolution window elapsed). Every exit carries a reason code that maps to one of these — no free-text.

This preserves the model's genuine strength (recognising that structure has broken) and removes its demonstrated weakness (impatience).

---

## 8. Change control — the fix for the 2-hour outage

The v1.9 edit went live with no test, no comparison, no alarm. That is the real incident; confidence-0 was only the symptom.

**Any change to contract or policy must pass through:**

1. **Versioned artifact.** Contract version is already stamped (`v1.8`, `v1.9`) — good. It must also be *recorded on every decision*, so a distribution shift can be attributed instantly.
2. **Replay.** Run the new contract over a stored set of recent decision inputs. Compare against the old: confidence distribution, side balance, ready-rate, trap frequency.
3. **Acceptance gates.** Block promotion if, versus baseline: ready-rate collapses, zero-confidence rate exceeds a small threshold, side balance skews past the symmetry limit, or mean confidence shifts beyond tolerance. **v1.9 would have failed on the first gate** — ready-rate went to zero.
4. **Shadow, then canary.** New contract runs alongside the live one, scoring but not trading, until N decisions agree within tolerance.
5. **Automatic rollback.** If the live contract produces a zero-confidence streak or a ready-rate collapse, revert to the last known-good version and alert. Two hours of silence should have been ninety seconds.

The principle: **a prompt is production code.** It gets versions, tests, staged rollout, and rollback — or it will keep taking the system down quietly.

---

## 9. Liveness invariants

The system had no notion of an impossible state. It should. Each of these is a condition that, if true, means something is wrong regardless of what the logs say:

- `market_open ∧ cache_ready ∧ no_open_position ∧ no_ready_proposal` sustained beyond a short window → **alarm** (would have fired at 06:30 UTC)
- `status = ready ∧ confidence = 0` → **reject and alarm** (fired 72 times, silently)
- N consecutive zero-confidence decisions → **alarm + rollback candidate**
- No proposal generated while `trade_permitted = true` for more than a few minutes → **alarm** (the silent 61-minute stall)
- Rolling side balance beyond the symmetry limit → **alarm**
- Any position closed by a party other than the system → **incident**, not a log line

**On the last point:** six trades (27%) exited `external_position_close` at exactly −3.50 — pure spread, closed within seconds by something outside the system. Under this design every position has an owner and a reconciliation loop, and an unattributed close raises an incident with the terminal state captured. It should never have been possible for a quarter of the day's trades to die this way without anyone noticing.

**And errors must carry codes.** `ERROR Automatic deal-sheet generation failed` is unactionable. Every failure gets a stable reason code plus the exception — so failures can be counted, grouped, and alerted on rather than read.

---

## 10. Learning loop

Right now nothing feeds outcomes back into permission. Today's data already contains a clear signal — M30 anchors +385 at 67%, H1/H4 anchors −433 at ~15% — and the system has no way to act on it.

**Configurations should earn the right to trade.**

- Attribute every closed trade by **frame, side, session, setup type, trigger TF**
- Maintain rolling expectancy per configuration
- Configurations below a minimum sample stay in **observation** — scored and logged, not traded
- Configurations with proven negative expectancy are **demoted** automatically
- Promotion and demotion are logged decisions, not manual edits

This turns the audit I ran by hand into something the system does continuously. On today's evidence, H1- and H4-framed entries would have been demoted to observation after the fifth loss, and the day would have ended far closer to flat.

---

## 11. What today would have looked like

| Event | Today | Under this design |
|---|---|---|
| v1.9 contract edit | Silent 2h20m outage | Fails replay gate — never promoted |
| `confidence 0` + `ready` | 72 silent contradictions | Rejected and alarmed on first occurrence |
| 44 sell / 1 buy | Invisible | Symmetry alarm; both sides scored every call |
| M1 trigger + H4 stop | Five −153.5 losses | Rejected — trigger and frame incoherent |
| Fixed $3 stop inside invalidation | Noise-stopped repeatedly | Stop beyond invalidation; size adapts |
| Qwen closing winners | 8 closes, −20 avg | Not permitted — TP, invalidation, or time only |
| 6 external closes at −3.50 | Unnoticed | Six incidents raised |
| 61-min stall | Unnoticed | Alarm within minutes |

---

## 12. Migration order

Sequenced so each step is safe on its own and the system keeps trading throughout.

**Stage 1 — stop the bleeding, keep behaviour**
Roll back to v1.8. Add the `ready ∧ confidence=0` rejection and the liveness alarms. Fix the `logging` import. *No behaviour change; the system simply becomes observable.*

**Stage 2 — split judgment from policy**
Move gating out of the prompt into code. Model emits component scores for both sides; code composes confidence and grants permission. *This is the change that makes every later step possible.*

**Stage 3 — timeframe coherence and structural geometry**
Enforce one frame per trade. Stop beyond invalidation, size as the free variable. *Expect fewer trades and a materially better win rate — today's five −153.5 losses disappear.*

**Stage 4 — bounded in-trade management**
Restrict the model to tightening and invalidation flags. Deterministic exits.

**Stage 5 — change control**
Replay, gates, shadow, canary, auto-rollback for every contract version.

**Stage 6 — learning loop**
Per-configuration expectancy with automatic promotion and demotion.

---

## 13. In one line

> Today the model decides and the code obeys, so a paragraph of English can halt trading for two hours and a timeframe mismatch can quietly cost −808. The system should invert that: **the model reports what it sees on both sides, deterministic policy decides what that permits, one coherent timeframe governs entry and risk together, discretion may only reduce risk — and every prompt version must earn promotion the way code does.**
