# Trade Cycle Audit — 2026-08-10

**Audit window:** 22:01 UTC (2026-08-09) → 08:43 UTC (2026-08-10)
**Proposals generated:** 433 | **Ready:** 45 | **Executed & closed:** 22
**Net result:** **−248.60** | Win rate **27.3%** | Expectancy **−11.30 / trade**

> **Correction to my earlier message:** I previously reported ~56% win rate from a partial log read. The full ledger is **27.3% (6W / 16L), net −248.60**. The earlier number was wrong — it counted only `qwen_confirmed_close` exits and missed the five `managed_or_safety_sl` losses.

---

## 1. Why no trade for the last ~2 hours

**Short answer: the entry prompt contract was upgraded from v1.8 → v1.9 at 06:21:50 UTC, and since that moment Qwen has returned `confidence: 0` on every single decision.**

The pipeline is fully healthy otherwise:

| Component | Status | Evidence |
|---|---|---|
| Market open | ✅ | `session=london`, `trade_permitted=True` |
| Cache | ✅ | `Context cycle status=ready failures=[]` (every 30s, unbroken) |
| Model loaded | ✅ | `Qwen remains loaded` |
| Qwen responding | ✅ | `ok=True`, ~16s latency, valid JSON |
| Proposals generating | ✅ | 21 in the 08:00 hour alone |
| Runner alive | ✅ | idle — **nothing ready to execute** |

**The exact break:**

```
06:16:23 UTC  prompt=9151 chars  contract v1.8  confidence=82  → TRADED (+249.15)
06:21:50 UTC  prompt=10383 chars contract v1.9  confidence=0   → wait
...
08:40:13 UTC  prompt=10301 chars contract v1.9  confidence=0   → wait
```

**Confidence by hour (UTC):**

| Hour | n | nonzero | avg (nonzero) |
|---|---|---|---|
| 01:00 | 107 | 107 | 67 |
| 02:00 | 110 | 109 | 71 |
| 03:00 | 79 | 79 | 67 |
| 04:00 | 23 | 23 | 70 |
| 05:00 | 26 | 26 | 78 |
| **06:00** | **49** | **1** | 82 |
| **07:00** | **2** | **0** | — |
| **08:00** | **21** | **0** | — |

100% of the last 72 decisions returned confidence 0. `Qwen confidence 0 is below the 51 entry minimum` is now the #1 wait reason (69 occurrences).

### The model is self-contradicting

Raw output from 08:40:13 UTC:

```json
{ "bias": "buy",
  "confidence": 0,
  "summary": "bullish bias: price approaching D1 floor pivot at 4337.985",
  "execution_plan": { "status": "ready",
                      "reason": "bullish bias confirmed by D1 floor pivot" } }
```

It says **"ready"**, it says **"confirmed"**, it names a directional bias — and then stamps **confidence 0**. That is not the model declining a trade; that is the model losing its confidence calibration.

### What v1.9 changed

v1.9 replaced a 5-line "never fade acceptance" paragraph with a **9-item "Hard traps — wait (do not ready) when any apply"** list (+1,240 chars), and inserted `any hard trap` into the wait clause.

The result is a prompt whose prohibition section is now larger than its permission section. There is no counterweight instruction telling the model what confidence to assign when *no* trap fires. The model resolves the ambiguity by collapsing confidence to zero while still narrating a bullish read.

**This is a prompt regression, not a market condition.** London session, cache ready, price active — and the system has been flat for 2h20m.

---

## 2. Complete trade cycle (as actually observed)

```
MT5 ticks
   │
   ├─► market_context_cache.py ── 30s cycle ──► SQLite + manifest
   │      builds: structural / levels / session / playbooks / minute
   │      gate: status must == "ready", epochs must match manifest
   │
   ├─► session_planner.py ── 20s ──► day plan → session plan → hourly → verdict
   │
   ├─► reviewer.py (entry) ── 30s when flat ─┐
   │      latest_entry_context()  [cache gate]
   │      build_entry_prompt() = contract v1.x + ENTRY FACTS (~10KB)
   │      ollama_generate()  16–31s  ◄── THE BOTTLENECK
   │      → paper-proposals-*.jsonl
   │                                          │
   ├─► paper_runner.py ── 0.25s poll ─────────┘
   │      gates: confidence ≥51 · age ≤60s · loss cooldown 120s · cap 100/day
   │      → MT5 order, magic 26072401, fixed $3 SL / $5 TP, 0.5 lot
   │
   └─► trade_management.py ── 30s ──► in-trade Qwen review → close decision
          exits: managed_or_safety_tp / _sl / qwen_confirmed_close / external
```

**Geometry is fixed, not structural.** Every ready proposal used `stop_distance: 3.0` and `target_distance: 5.0` (44/44). Qwen names the *zones*; runtime imposes the bracket. So:

- SL hit = **−153.5** (3.0 × 50 + spread)
- TP hit = **+246.5 / +249.15** (5.0 × 50 − spread)
- Nominal R:R **1 : 1.61** → **breakeven win rate 38.3%**
- Actual win rate **27.3%** → structurally losing

---

## 3. Bias findings

### 3a. Directional bias — severe

| | count | share |
|---|---|---|
| Ready proposals **SELL** | 44 | **97.8%** |
| Ready proposals **BUY** | 1 | 2.2% |

Yet raw bias across all 433 proposals was `conditional 309 / buy 66 / sell 58`. So the model *reads* both directions, but **only sell setups ever survive to `ready`**. One-sided exposure on a day that was not one-directional.

And note the flip: every ready proposal this morning was SELL; every zero-confidence proposal in the last two hours is BUY. The system was permitted to sell all morning and is now blocked from buying — the exact inverse bias, arriving at the moment it stopped trading.

### 3b. `bias: "conditional"` — 71% of all decisions

The v1.8/v1.9 contract explicitly says: *"Do not stay bias=conditional when your own read already favors buy or sell."* The model ignores this **309 out of 433 times**. This instruction is not working.

### 3c. Timeframe anchor bias — "aiming high" is confirmed and it is losing

**Entry zones are almost entirely M1:**

| Entry level ID | uses |
|---|---|
| M1_PREVIOUS_LOW | 39 |
| M1_PREVIOUS_HIGH | 38 |
| H4_PREVIOUS_HIGH | 5 |
| H1_PREVIOUS_HIGH | 4 |
| all others | ≤1 |

**But stops are anchored high:**

| Stop level ID | uses |
|---|---|
| H4_PREVIOUS_HIGH | 20 |
| D1_FLOOR_PIVOT | 8 |
| H1 / D1 / M30 others | 17 |

**Result — P&L by structural anchor timeframe:**

| Anchor | n | net | win rate |
|---|---|---|---|
| **M30** | 6 | **+385.45** | **66.7%** |
| D1 | 1 | −3.50 | 0% |
| **H4** | 7 | **−116.85** | 14.3% |
| **M15** | 2 | **−197.50** | 0% |
| **H1** | 6 | **−316.20** | 16.7% |

**M30 is the only profitable anchor.** H1 and H4 anchors lost −433 combined at ~15% win rate. This is exactly the "aiming high" failure: an **M1 entry trigger** paired with an **H4/H1 structural frame** and then a **fixed $3 stop**. The $3 stop sits a median **1.18** (max **7.81**) *inside* the structural invalidation level — so price does normal noise, takes out the fixed stop, and the H4 thesis never gets a chance to be right or wrong.

That single mismatch produced all five −153.5 losses (−808.00 total).

### 3d. Qwen's discretionary exits are destroying the edge

| Exit reason | n | net | avg |
|---|---|---|---|
| **managed_or_safety_tp** (left alone → TP) | 3 | **+742.15** | **+247.38** |
| external_position_close | 6 | −21.00 | −3.50 |
| **qwen_confirmed_close** (Qwen intervened) | 8 | **−161.75** | **−20.22** |
| **managed_or_safety_sl** | 5 | **−808.00** | −161.60 |

When a trade is **left alone to reach TP, it averages +247**. When **Qwen decides to close it, it averages −20**. Qwen's in-trade management is converting winners into scratches and small losses — 8 interventions, net −161.75.

### 3e. Missing / anomalous

- **6 trades exited `external_position_close` at exactly −3.50** — that is the spread and nothing else. Position opened, then closed by something outside the system within seconds. 27% of all trades. Unexplained; needs investigation (runner restart? terminal? duplicate magic?).
- **61.6-minute proposal gap 07:00:33 → 08:02:12 UTC** during active London — no proposals at all, no error logged. Silent stall.
- **`ERROR Automatic deal-sheet generation failed`** repeating in session-planner.log with no traceback or reason attached.
- **`bias: "conditional"` is not in the documented enum handling** — it maps to no side and always becomes a wait.
- **Decision latency 16–31s** against a **30s** loop interval and a **60s** proposal freshness window. At 31s the system spends more time thinking than the gap between thoughts; a proposal can be nearly half-stale on arrival.

---

## 4. Recommended improvements

### P0 — restores trading (do first)

1. **Roll the entry contract back to v1.8.** It is the single change that stopped trading. Confirm confidence returns to the 67–82 band, then re-introduce v1.9 deliberately.
2. **Re-introduce the trap list with a confidence anchor.** The traps are good ideas, badly framed. Add an explicit rule such as: *"Traps govern `status` only. Always score `confidence` on setup quality independently — never emit confidence 0 alongside a directional bias."*
3. **Add a schema guard:** reject/flag any response where `status == "ready"` and `confidence == 0`. That contradiction has occurred 72 times in two hours and nothing caught it.
4. **Fix `paper_executor.py:571`** — add `import logging`. Still costing ~3 proposals/day at the execution step.

### P1 — fixes the losing expectancy

5. **Stop pairing M1 entries with H4/H1 stops under a fixed $3 bracket.** Either size the stop off the structural level, or restrict ready proposals to the anchor that works. On today's data, **M30-anchored trades were +385 at 67%** while **H1+H4 were −433 at ~15%**.
6. **Reduce or gate Qwen's discretionary closes.** Left alone: **+247/trade**. With intervention: **−20/trade**. Suggest letting TP run unless a *named structural invalidation* is breached, rather than on general review.
7. **Investigate the six −3.50 `external_position_close` exits.** A quarter of all trades dying at spread cost is either a bug or outside interference, and it is silently taxing every session.

### P2 — hygiene

8. **Alert on confidence-0 streaks.** A 5-in-a-row zero-confidence run should page, not sit silent for two hours.
9. **Alert on proposal gaps > 10 min while `trade_permitted=True`.** The 61-minute stall was invisible.
10. **Attach the exception to `Automatic deal-sheet generation failed`** — currently unactionable.
11. **Enforce the bias enum.** 71% `conditional` means the instruction is failing; make it a schema constraint rather than a prose request.
12. **Reconsider the 30s loop vs 16–31s inference.** Consider raising the interval or trimming the ~10KB prompt so decisions are not near-stale on arrival.

---

## 5. One-line summary

The system is not broken, it is **muted** — a v1.9 prompt regression at 06:21:50 UTC zeroed Qwen's confidence and has kept it flat for 2h20m; underneath that, the day's real ledger is **−248.60 at 27.3%**, driven by a **97.8% sell-only bias**, an **M1-entry / H4-stop / fixed-$3-bracket mismatch** that only M30 anchors survive, and **in-trade interventions that turn +247 average winners into −20 average scratches**.
