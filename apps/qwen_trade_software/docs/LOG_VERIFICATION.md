# Log verification — Phases 1–4

Use this while paper-trading. Each check is a **pass/fail** against a real log line. If the fail line appears, the phase is not working.

Log folder: `apps/qwen_trade_software/backend/logs/`

Dated JSONL (today’s date):

- `qwen-io-YYYY-MM-DD.jsonl` — every Ollama call, including ATR
- `qwen-decisions-YYYY-MM-DD.jsonl` — entry and management decisions
- `reviews-YYYY-MM-DD.jsonl` — management cycle record
- `paper-executions-YYYY-MM-DD.jsonl` — fills and skips
- `paper-proposals-YYYY-MM-DD.jsonl` — ready/wait plans
- `trade-management.log` — management process text log
- `reviewer.log` — entry process text log
- `paper-executor` warnings also go to the executor log / process output

---

## Phase 1 — ATR and regime computation (log only)

**Pass**

| What | Where | Look for |
|------|--------|----------|
| ATR from cache | `qwen-io-*.jsonl` | `"source": "cache"` and `"ok": true` on `request.atr` |
| Both ATR legs | `trade-management.log` or `reviewer.log` | `atr_m1_51=` a number, `atr_m1_3=` a number, not `None` |
| Regime hint each management M1 | `trade-management.log` | `regime_hint=range` or `trend` or `breakout` or `exhaustion` or `unknown` |
| Transition flag | `trade-management.log` | `transition=True` when the hint changes; `False` otherwise |

**Fail**

| Bad line | Meaning |
|----------|---------|
| `mt5_not_connected` or `No IPC connection` on ATR | Still calling MT5 for ATR |
| `"ok": false` with `no_cached_m1_bars` on every call | Cache worker not filling M1 bars |
| No `regime_hint=` after a management cycle with an open position | Phase 1 wiring missing |

---

## Phase 2 — Qwen manages; guard is safety/timeout only

**Pass**

| What | Where | Look for |
|------|--------|----------|
| Qwen ran management | `reviews-*.jsonl` | `"model"` is the Qwen tag (e.g. `qwen-trading-v005:latest`), not a guard name, on routine cycles |
| Regime in facts | `reviews-*.jsonl` → `snapshot.management_facts.regime_context` | `regime_hint` present |
| Hard invalidation only | `trade-management.log` | `Safety guard ticket=` **and** summary about M1+M5 beyond stop |
| Timeout only after 3 misses | `trade-management.log` | `Qwen failure 1/3` then `2/3` then `Timeout guard activated: 3` |

**Fail**

| Bad line | Meaning |
|----------|---------|
| `model_used` / `"model": "deterministic-confirmation-guard"` on a normal close | Old pre-empting guard is back |
| Safety guard closing on `M5_PREVIOUS_LOW` bounce-back with no invalidation | Guard is managing again |
| `Timeout guard activated: 1` | Timeout fired too early |

On a **range** timeout (Qwen actually down 3 cycles): log summary should contain `Range scalp` and M1 still favorable. On **trend** timeout: M15+ rejection, not M5 noise for an M15 thesis.

---

## Phase 3 — Entry gate, target mode, qualified levels

**Pass**

| What | Where | Look for |
|------|--------|----------|
| Wait inside zone without M1 fail | executor log | `inside_zone_waiting_m1_failure` |
| Fill only when armed | executor log **and** `paper-executions-*.jsonl` | `entry_gate=armed_m1_failure` and fill field `"entry_gate": "armed_m1_failure"` |
| Regime on entry | `reviewer.log` | `entry_regime hint=... suggested_target_mode=... qwen_target_mode=...` |
| Range suggestion | same | `hint=range suggested_target_mode=scalp` |
| Trend/breakout suggestion | same | `suggested_target_mode=starter_basket` |
| Plan carries mode | `paper-proposals-*.jsonl` → `qwen.execution_plan` | `regime_hint`, `suggested_target_mode`, and `target_mode` on ready plans |
| Cited levels remembered | `reviewer.log` / `trade-management.log` | `qualified_levels count=` growing when Qwen names levels |
| Dashboard split | `management-dashboard-state.json` | `level_display.qualified` vs `level_display.candidate`; each level has `"display": "qualified"` or `"candidate"` |

**Fail**

| Bad line | Meaning |
|----------|---------|
| Fill with `entry_gate` missing or while logs still show only `inside_zone` with no `armed_m1_failure` | Fill on first zone touch |
| Ready proposal with no `regime_hint` after a Qwen entry call | Stamp not running |
| Every dashboard level `"qualified": true` with empty Qwen citations | Qualification not tied to decisions |
| `entry_regime` never appears on days the cache is ready | Entry facts missing regime_context |

---

## Phase 4 — Confirmation labels (curriculum + live facts)

**Pass**

| What | Where | Look for |
|------|--------|----------|
| Confirmation packet on entry | `reviewer.log` | `entry_confirm` followed by `none` or `m1_choch=` / `m5_bos=` / `m1_sweep=` / `m5_fvg=` |
| Labels in facts | `paper-proposals-*.jsonl` or entry I/O | `confirmation_context` with `m1` and `m5` keys |
| Doctrine loaded | store | `core_skill.md` section `[regime-reading]`; sop entry version 1.12 |

**Fail**

| Bad line | Meaning |
|----------|---------|
| Every `entry_confirm` missing after cache-ready entries | `snapshot_confirmations` not wired |
| Fills that mention CHoCH as the executor gate | Labels leaked into the fill gate (should stay M1 failure) |

---

## One-pass greps (PowerShell)

From `apps/qwen_trade_software/backend/logs` (adjust the date):

```powershell
$d = Get-Date -Format yyyy-MM-dd

# Phase 1 ATR
Select-String -Path "qwen-io-$d.jsonl" -Pattern '"ok": false|"mt5_not_connected"|"source": "cache"' | Select-Object -Last 20
Select-String -Path "trade-management.log" -Pattern "regime_hint=" | Select-Object -Last 20

# Phase 2 guard names
Select-String -Path "reviews-$d.jsonl" -Pattern "deterministic-confirmation-guard|safety_guard_invalidation|timeout_guard|qwen-trading" | Select-Object -Last 20
Select-String -Path "trade-management.log" -Pattern "Safety guard|Timeout guard|Qwen failure" | Select-Object -Last 20

# Phase 3 entry
Select-String -Path "reviewer.log" -Pattern "entry_regime |entry_confirm |qualified_levels count=" | Select-Object -Last 20
Select-String -Path "paper-executions-$d.jsonl" -Pattern "armed_m1_failure|inside_zone_waiting_m1_failure" | Select-Object -Last 20
```

---

## Session verdict

After a paper session, you should be able to answer:

1. Did ATR stay non-null from cache?  
2. Did `regime_hint` match the chart often enough to trust?  
3. Did Qwen (not the old bounce-back guard) manage open trades?  
4. Did fills wait for an M1 failure at the hunt band?  
5. In a range, did `suggested_target_mode=scalp` show up? In a trend, `starter_basket`?  
6. Did `level_display.qualified` stay smaller than the full candidate list?  
7. Did `entry_confirm` appear, and did fills still wait for `armed_m1_failure` rather than CHoCH alone?

If 1–3 fail, do not treat Phase 3 fills as a valid test. If 4–6 fail, Phase 3 is not live yet. If 7 fails, Phase 4 labels are not reaching Qwen.
