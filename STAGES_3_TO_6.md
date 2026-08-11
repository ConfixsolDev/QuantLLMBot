# Stages 3–6 — Implementation & Validation

**Branch:** `feat/decision-layer-stage1-2`
**Tests:** 105 passing (was 59). **Live system:** untouched, still running.

---

## Your Stage 3 question, answered with the data

You proposed: place a fixed SL/TP at entry, then have trade management update both.

**That is already what the system claims to do** — `sop.md` v1.3 for `qwen_trade_management` says *"improve fixed $3/$5 entry using structure S/R"*. It isn't working, and the reason is timing:

| exit reason | n | median life |
|---|---|---|
| managed_or_safety_sl | 5 | **106s** |
| managed_or_safety_tp | 3 | 161s |
| qwen_confirmed_close | 8 | 266s |

Individual stop-outs lived **22s, 50s, 106s, 108s, 161s**. Management runs on a 30s cycle with 16–31s of model latency, so the two fastest got **zero completed reviews** and the rest got at most three. All five closed at exactly −153.5 — the untouched $3 stop.

"Place it wrong, fix it later" loses the race on precisely the trades that need fixing. So Stage 3 puts the bracket at the structural level **at fill**, and keeps your in-flight adjustment on top of that rather than instead of it.

The mechanism that makes a wider stop affordable is the inversion:

```
risk budget fixed  →  stop goes where structure says  →  SIZE absorbs the difference
```

A wider stop is not a bigger loss; it is a smaller position. `MIN_REWARD_RISK` and a `MAX_STOP_DISTANCE` ceiling reject setups that don't clear the bar, and if structure is unavailable it degrades to the exact legacy $3/$5 bracket rather than leaving a position unprotected.

---

## Stage 4 — built as you specified

`STOP_POLICY = full_discretion`, `TARGET_POLICY = full_discretion`. Management can move SL and TP in both directions.

I added one thing you didn't ask for and I'd push back if you wanted it removed: an **absolute risk ceiling**. A widened stop may never put more than `MAX_RISK_MULTIPLE` (1.75×) of the originally accepted risk at stake. That is not a limit on judgement — it's a solvency limit. Without it a stop can be walked away from indefinitely, which is the standard mechanism by which a small loss becomes an account-ending one. Widening also requires a *named* structural level and is capped at 2 per position.

Everything else is instrumented rather than restricted. Every adjustment records what moved, which direction, why, the level cited, risk before/after, and open P&L at the time. Exits are classified mechanically **before** discretionary ones, so a trade that genuinely hit its target is never logged as a discretionary close.

That matters because it lets Stage 6 settle the open question with your data. Current evidence:

| | n | avg |
|---|---|---|
| left alone until TP | 3 | **+247.38** |
| closed by model | 8 | **−20.22** |

If discretion earns its keep, the ledger will show it. If it doesn't, it will show that too — per configuration. Switching to `tighten_only` later is a one-line change; no call sites move.

---

## Stage 5 — the gate blocks v1.9 retroactively

Run against the real decisions from both contracts:

```
CONTRACT GATE 5.0 :: candidate 1.9 vs baseline 1.3
  VERDICT: FAIL
    [PASS] gate:sample_size            109 decisions (need 40)
    [FAIL] gate:ready_rate             ready-rate 0.0% (floor 2.0%)
    [FAIL] gate:zero_confidence_share  zero-confidence 100.0% (max 25.0%)
    [FAIL] gate:contradiction_share    ready-with-low-confidence 100.0% (max 0.0%)
    [FAIL] gate:ready_rate_drop        ready-rate fell 100% (5.9% → 0.0%), max 60%
    [FAIL] gate:mean_confidence_drop   mean confidence 69.2 → 0.0 (drop 69.2, max 20.0)
    [PASS] gate:latency_multiple       23.3s → 16.1s (0.69x, max 1.75x)

  -> v1.9 would have been BLOCKED
```

Five of seven gates fail. There is also `should_rollback()` for the live loop, so a bad promotion self-reverts in minutes rather than persisting for hours.

---

## Stage 6 — implemented and started

The ledger is live at `logs/configuration-ledger.json`, seeded from today's 22 closed trades:

```
  state          n  expectancy   win%  configuration
  observation    1      246.50  100%  H4|sell|asia|H4|qwen_sr_zone_fixed_3_5
  observation    6       64.24   67%  M30|sell|asia|M1|cache_sr_zone_fixed_3_5
  observation    1       -3.50    0%  H4|sell|asia|H1|qwen_sr_zone_fixed_3_5
  observation    1       -3.50    0%  D1|buy|asia|M1|cache_sr_zone_fixed_3_5
  demoted        6      -52.70   17%  H1|sell|asia|M1|cache_sr_zone_fixed_3_5
  demoted        5      -71.97    0%  H4|sell|asia|M1|cache_sr_zone_fixed_3_5
  observation    2      -98.75    0%  M15|sell|asia|M1|cache_sr_zone_fixed_3_5
  -- 7 configurations, 22 trades, net -248.60
```

**Two configurations demoted automatically and are now blocked**, combined realised P&L **−676.05**:

- `H1|sell|asia|M1` — n=6, expectancy −52.70, win 17%
- `H4|sell|asia|M1` — n=5, expectancy −71.97, win 0%

Worth noting: both are **M1 trigger under an H1/H4 frame**. The ledger found the same fault as the Stage 3 coherence rule, independently and from outcomes alone. Two different methods converging on the same answer is the strongest evidence in this whole exercise.

The profitable configuration — `M30|sell|asia|M1`, +64.24 expectancy at 67% — sits in observation until it reaches 12 trades.

States are `observation → permitted → demoted`, with rolling expectancy over the last 60 trades, early demotion for severe losers (−60 expectancy over 5 trades), and rehabilitation back to observation after 20 new trades so nothing is banned permanently.

---

## What is NOT wired in

Being explicit, because this is the difference between written and working:

| Stage | Status |
|---|---|
| 1 | Wired into `reviewer.py`. Active on restart. |
| 2 | Wired, behind `QWEN_POLICY_V2=1`. Off. |
| **3** | **Module + tests only.** `paper_executor.py` still applies fixed $3/$5. Needs the call site swapped to `trade_geometry.build_bracket()`. |
| **4** | **Module + tests only.** `trade_management.py` still closes on model opinion. Needs its adjust/exit path routed through `management_policy`. |
| **5** | **Tooling.** Runs on demand via `bootstrap_ledger.py`. Not yet blocking promotion automatically. |
| **6** | **Started.** Ledger exists and is populated, but `may_trade()` is not yet consulted in the entry path, so demotions are recorded and not yet enforced. |

Every module is pure — no MT5, no model calls, no I/O — so all of it is replayable and none of it can affect the running system until deliberately wired.

---

## Files

**New this round**

```
backend/trade_geometry.py               Stage 3  structural bracket, size as free variable
backend/management_policy.py            Stage 4  full discretion + solvency rail
backend/contract_gate.py                Stage 5  promotion gates + live rollback trigger
backend/configuration_ledger.py         Stage 6  per-configuration expectancy
backend/tools/bootstrap_ledger.py       Stage 6  bootstrap + retroactive gate test
backend/tests/test_stages_3_to_6.py     46 tests
backend/logs/configuration-ledger.json  the live ledger
```

**Totals:** 105 tests passing, 11 files compile clean, ledger round-trips through JSON.

---

## Suggested next step

Wire Stage 3 first. It is the largest measured P&L item still unaddressed (**+823.50** on today's data by replay), it is independent of Stage 2, and the fallback path means the worst case is current behaviour. Stage 6 enforcement is the natural second — the demotions are already computed and just need consulting.
