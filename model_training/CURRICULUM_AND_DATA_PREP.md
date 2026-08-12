# QuantLLMBot — Curriculum, Data Prep & Training

**THE ONLY process document** for curriculum, data preparation, tick→train loop, and Colab training.

Last updated: 2026-08-10

---

## 0. Binding rules for every model / agent / chat

**READ AND FOLLOW THIS FILE. DO NOT CREATE ANOTHER.**

| MUST | MUST NOT |
|------|----------|
| Use **this file** as the sole process source for training and data prep | Create new `.md` guides, quick-starts, plans, READMEs, or “notes” on the same topics |
| Edit **this file** when process/policy changes | Overlook, fork, summarize into a parallel doc, or invent a second curriculum |
| Point users/agents here (`model_training/CURRICULUM_AND_DATA_PREP.md`) | Write START_HERE / QUICK_START / v00x_plan / TRAINING_NOTES / etc. |
| Put **new model-job Python** only in `python_utilities_for_models/` (read folder first) | Scatter new `.py` under `model_training/` or invent satellite folders |
| Leave live system code in `apps/qwen_trade_software/` and Colab train pipeline in repo `scripts/` | Mix system runtime code into model utilities |

Architecture overview may still live in `SYSTEM_THREE_PARTS.md` / `AGENTS.md` (pointers only).  
Live doctrine stays in `store/core_skill.md` + `store/sop.md`.  
**Everything about how we collect data, mature curriculum, and train = this file only.**

### Folder layout (keep this clean)

```text
model_training/
  CURRICULUM_AND_DATA_PREP.md          ← THIS FILE (only process doc)
  knowledge/
    stage_01..04_*.jsonl               ← SFT curriculum (train data)
    topics/01..09_*.md + maps          ← distilled doctrine source
    _pdf_extract/                      ← KEEP — full book plain-text corpus for learning
  tick_data/YYYY-MM-DD/*.jsonl         ← live evidence archive (grows daily)
  datasets/raw/                        ← optional MT5 export output
  python_utilities_for_models/         ← ALL model/agent Python for curriculum jobs
apps/qwen_trade_software/              ← live SYSTEM code (separate)
scripts/                               ← Colab train/eval pipeline (system)
store/                                 ← live LLM template (core_skill + sop)
```

**Do not delete** `knowledge/_pdf_extract/` — it is the checked-in book corpus used for learning and topic distillation (plain `.txt` extracts). Distilled topics in `topics/` are the operating doctrine; the extracts stay as source material.

---

## 0.1 Hard rules (strategy)

1. **One doc** — this file is the process source of truth for training and data prep.
2. **Three-part system** — tick archive grows forever; store stays lean; code stabilizes (`SYSTEM_THREE_PARTS.md`, `AGENTS.md`).
3. **Code owns where** — levels, Floor/Fib pivots, session gates, news/shock cool-down.
4. **Qwen owns what happens at the level** — auction_state → open|wait|skip; in-trade hold|protect|close.
5. **Never invent** levels, fib anchors, news, or SMC narratives in training labels.
6. **News / shock** — calendar and ATR cool-down are **code gates**, not curriculum to predict.
7. **No satellite docs** — see §0 table. Zero exceptions for “temporary” markdown.
8. **Weekly retrain cadence (v4+)** — improve from **maturing live ticks + distilled skill**, not from a fresh MT5 bulk export every train. See §0.2.

### 0.2 Operating model — mature daily, train weekly

**Intent:** each week’s LoRA (v4, v5, …) should outperform the prior week because the *same* evidence streams got sharper — not because we re-downloaded history.

| Cadence | What happens |
|---------|----------------|
| **Every trading day** | Live app archives ticks → `tick_data/YYYY-MM-DD/` (including hierarchical trade-idea stack H4→H1→M15 + hourly layer validation for v004 fuel). Human/agent review → promote lessons into lean `store/` + curated stage_02/04 rows. Distilled topics stay the doctrine source. |
| **Through the week** | Curriculum JSONL and store mature in place (append packs only when evidence warrants). No requirement to re-export raw MT5 for the weekend train. |
| **Weekend train** | Freeze current `knowledge/stage_0*.jsonl` + store versions → zip → Colab QLoRA → eval holdout → export GGUF. Compare to last week’s eval. |
| **MT5 historical export** | Optional / one-time / rare tooling for structure research. **Not** the weekly training fuel for v4+. |

**Success metric:** holdout + live discipline improve week over week as tick evidence and distilled labels improve — not “more CSV from the broker.”

---

## 1. Strategy (what we train the model to do)

| Layer | Owner | Job |
|-------|--------|-----|
| Levels / Fib / pivots / sessions / news gate | Code | Supply named facts |
| Auction at level (accept / reject / transition) | Qwen | Decide open\|wait\|skip |
| Management | Qwen | hold\|protect\|close |
| Timing | M1 EMA **3/14/31** only | Reclaim at mapped level — not all-TF EMA |
| Fib | Supplied H4/daily IDs | Consume location — never recalculate |

Doctrine live prompts: `store/core_skill.md`, `store/sop.md`.

### 1.1 v004 SL/TP geometry (gold price, zone-based)

`$N` in curriculum SL/TP means **gold price change** (XAU points), not account P&L dollars.
Open-entry samples place stop/target on **named support/resistance**, not a tiny fixed pad.

| Structure TF | Min SL | Min TP | Placement |
|--------------|--------|--------|-----------|
| M15 / M30 | **5** | **5** | Beyond named invalidation / next opposing named level |
| H1 | **7** | **10** | Same mid ladder |
| H4 / D1 | **10** | **20** | Proper H4/D1 S/R; pad to mins if nearer level is tighter |

Rules: prefer `key_levels` prices on the correct side of entry; if nearer than the TF min, pad **beyond that level** to the min; no inventing geometry when no usable opposing level → wait/skip with SL/TP N/A. Repair util: `python_utilities_for_models/repair_zone_sl_tp_v004.py`.

### 1.2 v004 reason + candle confirmation (teach concepts, not entries alone)

Every stage_04 row (open / wait / skip / management) must carry:

| Field | Purpose |
|-------|---------|
| `trade_reason` | Distilled **concept** from `knowledge/topics/` + why this side/action at the named zone |
| `confirmation_reason` | Which **closed** candle/response proves (or is still missing for) that direction |

Sample Prepared text (`scripts/utils.py`) must show both lines. Forming candles are never confirmation. Read distilled topics when enriching — do not invent SMC narratives. Enrich util: `python_utilities_for_models/enrich_trade_reasons_v004.py`.

Aim for LoRA capability: location → auction → closed response → side, with explicit reasons — not price memorization.

### 1.3 v004 sideways / three-regime pack

Gold is sideways/balance most of the time (Brooks/Dalton). Curriculum must teach:

| Regime | Playbook | Management |
|--------|----------|------------|
| **Sideways** | Outer-third fades + failed breakouts; skip mid/barbwire | **HOLD** normal giveback/rotation inside the box; **CLOSE** only on accepted break against the entry edge |
| **Trend** | With unfinished acceptance; do not fade local wicks | Losing the breakout level can invalidate (not “mid magnet”) |
| **Reversal** | Prior trend + TL break + failed retest | Usually births a **new range**, not an instant opposite trend |

Operator gap this pack fixes: cutting sideways fades on temporary gold loss while price recovers to mid. Util: `python_utilities_for_models/append_sideways_regime_v004.py`.

---

## 2. Data sources (two streams)

### 2.1 Live tick archive (decision ticks) — already wired

**True:** the live app dual-writes every observation to JSONL:

- Hot: `apps/qwen_trade_software/backend/logs/{name}-YYYY-MM-DD.jsonl`
- Permanent: `model_training/tick_data/YYYY-MM-DD/{name}.jsonl`

Code: `apps/qwen_trade_software/backend/tick_data_archive.py`  
Synced by `software_runtime.py`. **Never auto-delete** `tick_data/`.

| File | Meaning |
|------|---------|
| `paper-proposals.jsonl` | Entry decision + market snapshot |
| `paper-executions.jsonl` | Fill / close / skip execution ticks |
| `reviews.jsonl` | In-trade management cycles |
| `qwen-decisions.jsonl` | Unified decision tree per price/time |
| `qwen-io.jsonl` | Full Qwen request / response |
| `mt5-io.jsonl` | MT5 API I/O |
| `day-plans.jsonl` | Day plan + validator |
| `session-plans.jsonl` | Session plan |
| `hourly-updates.jsonl` | Hourly plan delta |
| `session-verdicts.jsonl` | Session close review |
| `manifest.json` | Day inventory |

These are **process ticks** (price + context + decision), not only MT5 bid/ask prints. Raw bid/ask also sit in `cache/market_context.sqlite3` (`ticks` table).

### 2.2 Historical MT5 export (optional — not weekly v4+ fuel)

Script: `model_training/python_utilities_for_models/export_mt5_market_data.py`  
Lib: `model_training/python_utilities_for_models/mt5_export_lib.py`  
Default out: `model_training/datasets/raw/`

Downloads (requires MT5 terminal logged in):

| Type | How | Files (side by side) |
|------|-----|----------------------|
| Ticks | `copy_ticks` daily chunks | `{day}_ticks.csv` **+** `{day}_ticks.jsonl` (volume/spread) |
| M1 | position-based max history | `{month}_M1.csv` **+** `.jsonl` (levels + volume) |
| H1 | MT5 rates | `{month}_H1.csv` **+** `.jsonl` (prior H/L + floor pivots + swing fib + volume) |
| M5/M15/M30 | resampled from M1 (UTC) | `{month}_{TF}.csv` **+** `.jsonl` (prior H/L + volume) |
| H4 | resampled from H1 (NY 4h buckets) | `{month}_H4_NY.csv` **+** `.jsonl` (prior H/L + floor pivots + swing fib + volume) |
| Log | append-only | `export_log.jsonl` |
| Manifest | summary | `manifest.json` |

**JSONL rule:** CSV stays lean OHLC (+ tick columns). JSONL is the **enriched** training/prep row: same bar **plus** `volume` block and `levels` / `level_objects` for that TF (distilled ownership — see §4).

```powershell
cd E:\QuantLLMBot\model_training\python_utilities_for_models
..\..\apps\qwen_trade_software\backend\.venv\Scripts\python.exe export_mt5_market_data.py --symbol XAUUSDr
```

Optional: `--from-date`, `--to-date`, `--skip-ticks`, `--force`.

### 2.3 `python_utilities_for_models/` (mandatory for agents)

Before writing any new Python for curriculum / data / zip / audit / append packs:

1. **List and read** this folder.
2. **Reuse or extend** an existing script.
3. Only if nothing fits, **add a new `.py` here** (not elsewhere).
4. Never put live trading system logic here — that stays in `apps/qwen_trade_software/`.

---

## 3. Curriculum stages (SFT JSONL)

Path: `model_training/knowledge/`

| Stage | File | Role |
|-------|------|------|
| 01 | `stage_01_principle_foundation.jsonl` | Distilled principles (P00x) |
| 02 | `stage_02_structured_data.jsonl` | Setup / decision / invalidation |
| 03 | `stage_03_detector_definitions.jsonl` | Detector logic for the setup |
| 04 | `stage_04_decision_contract.jsonl` | Action, levels, SL/TP, auction, skips, mgmt |
| 05 | `stage_05_live_contract.jsonl` | **Live inference output contract** (see 3.1) |

### 3.0 Version definition — READ BEFORE BUILDING OR TRAINING

Two version numbers exist and they are **not** the same thing. Keep them straight
or the exported model will not match the data that produced it.

| What | Current | Where it is set |
|------|---------|-----------------|
| **Model / LoRA version** | **v4** (`qwen-trading-v004`) | `export_lora_to_ollama_colab.py` `--outfile-prefix`; `QWEN_MODEL` env, default in `review_shared.py` + `market_context_cache.py` |
| **Curriculum / dataset version** | **v9** | this file, §3 size line below |

**v4 is the model trained on curriculum v9** (712 aligned rows, packs in §3.1
and §3.2). Anything built from an earlier dataset is not v4, whatever it is
named.

Model version history:

| Model | Trained on | Notes |
|-------|-----------|-------|
| v002 | early curriculum | export script default was still stuck here until 2026-08-10 |
| v003 | ~389 rows | live through 2026-08-10; buy-blind — scored buy non-zero only **14%** of the time against **82%** for sell |
| **v004** | **712 rows, curriculum v9** | balanced buy/sell confidence, M30 coverage, frame-coherence skips, live-outcome grounding, trade-management pack. Holdout eval: **direction agreement 100%**, action 90% |

> **Note on the number 4.** `v004` names *two different things* in this repo:
> the **model build** (above) and the **geometry/reason conventions** in §1.1
> and §1.2, which are curriculum rules. Same number, different scope. When
> writing about either, say "the v004 *model*" or "the v004 *geometry*".

**Deployment is a separate step from training.** Exporting `qwen-trading-v004`
to Ollama does not switch the live system over. Until you switch it, the bot
keeps running v003.

```bash
# 1. confirm the model actually exists in Ollama first
ollama list | grep qwen-trading-v004

# 2. point the runtime at it (both processes read the same variable)
set QWEN_MODEL=qwen-trading-v004:latest      # Windows
export QWEN_MODEL=qwen-trading-v004:latest   # bash

# 3. restart the stack
```

`review_shared.MODEL` and `market_context_cache.MODEL` both read `QWEN_MODEL`
and **must stay in lockstep** — the qualification certificate is keyed on
`model_digest`, so a mismatch invalidates the cache on every cycle and blocks
entry with `qwen_validation_not_run`.

Switching model **invalidates the qualification certificate by design** (new
digest). The always-on cache child runs `--no-qwen` and cannot mint a new one,
so run a qualification pass after switching:

```bash
python market_context_cache.py --once     # without --no-qwen
```

Default stays v003 in code so an exported-but-unverified model cannot silently
break live trading. Flip `DEFAULT_MODEL` in `review_shared.py` only after v004
has run a clean session.

**Current size (curriculum v9):** 712 aligned stage_02/04 examples
(702 train / 10 holdout at end) + 321 stage_05 rows.  
**Config:** `scripts/config.py` → `training_lines_end=702`, `test_lines_end=712`.

> **Bounds are absolute row indices, not proportions.** After any `append_*.py`
> run you MUST bump both values or the appended rows — which land at the end of
> the file — are silently dropped from training *and* holdout.
> `audit_training_dataset.py` prints the current totals.

> **stage_02 and stage_04 are paired POSITIONALLY** by `scripts/01_preprocess.py`
> (`zip`, not a join on `example_id`). Append the same IDs in the same order to
> both files, and re-run the alignment check in the audit.

Append packs (idempotent scripts, same holdout IDs):  
`model_training/python_utilities_for_models/append_*.py` — extend existing or add one new pack script **in that folder only**.
Packs append to the tail, so the canonical 10 holdout IDs are moved back to the
end afterwards; the audit prints them.

### 3.1 v004 packs (2026-08-10) — added to close measured live failures

Each pack exists because of a specific production loss, not to grow the dataset.

| Pack | Script | Fixes |
|------|--------|-------|
| Live contract | `build_stage05_live_contract.py` | stage_04 teaches `direction/action`; the runtime asks for `bias / acknowledged_epochs / execution_plan`. Occurrences of `execution_plan` and `conditional` in stage_04: **0**. The model mapped trained `direction: "none"` onto `bias: "conditional"` in 65–71% of live decisions, so almost nothing reached ready, and it had never practised copying five epoch hashes verbatim — which blew the response token cap. |
| Frame coherence + M30 | `append_frame_coherence_m30.py` | M30 was the only profitable live anchor (**+385.45, 67%**) with **1** training example, while H1/H4 (**−433, ~15%**) had 271. Also teaches that an M1 zone defended by an H4/D1 invalidation is a skip: gap ≥5 cost **−1070 over 14 trades at 7% win**. Built from real cache candles and real level snapshots. |
| Live outcomes | `append_live_outcome_examples.py` | Grounds the curriculum in realised P&L. Across 27 closed trades the stop's distance *inside* the structural invalidation separated outcomes: winners averaged **1.71 inside**, losers **3.76**. Also teaches patience — hold-to-target averaged **+247.38**, discretionary closes **−20.22**. |
| Trade management | `append_trade_management_pack.py` | **6 of 508 rows** taught any in-trade decision, while management was the largest single loss source. Teaches the four named close conditions from topic 10 plus the prohibition, grounded in real level snapshots. |

### 3.2 Topic 10 — trade management (2026-08-10)

`knowledge/topics/10_trade_management.md`, distilled from `brooks_trends`,
`brooks_reversals`, `brooks_ranges`, `grimes_art_science`, `carter_mastering`,
`douglas_zone`, `dalton_mind_over_markets` with page citations.

Management **may close whenever the idea is genuinely dead** — that is doctrine
(`grimes p.172`: *"it is often advisable to scratch the trade"*). What it may not
do is close because the position is uncomfortable. Douglas gives the mechanism
(`p.99`): a holder who fears losing *"will gather information against the trade"*,
manufacturing the justification it already wants. That is the likeliest reading
of our −20.22 average discretionary close.

So every close must name one of four checkable conditions:

| | Condition | Source | Live enum |
|---|---|---|---|
| **R1** | Named invalidation failed on a closed candle of its own timeframe | `grimes pp.60, 172` | `thesis_invalidation_confirmed` |
| **R2** | Always-in flip — the opposite entry would now be taken with confidence | `brooks_reversals p.11` | `always_in_flip_confirmed` |
| **R3** | Remaining reward no longer clears remaining risk | `brooks_trends p.326` | `reward_risk_inverted` |
| **R4** | Frame budget elapsed with no structural progress | `carter pp.180, 201` | `time_stop_expired` |
| **R5** | *Prohibition:* a close supported only by open P&L | measured, `douglas p.99` | — |

**The hold:close ratio is itself a lesson.** A curriculum where close outnumbers
hold teaches the model to close. `audit_training_dataset.py` gates on
`hold >= close` and on all four conditions being present.

Live contract: `store/sop.md → prompt:qwen_trade_management` **v2.0**.
Runtime enforcement: `management_policy.classify_close_request()`.

**Readiness gates:** `audit_training_dataset.py` now ends with a RETRAIN
READINESS block (side balance, confidence symmetry, no zero-confidence
directional rows, M30 coverage, frame-incoherence coverage, outcome grounding,
patience lessons, geometry). Do not train while any gate reads FAIL.

**Known limitation:** `stage_03_detector_definitions.jsonl` was not extended by
these packs (389 rows vs 508). `01_preprocess.py` does not consume stage_03, so
training is unaffected — but the file is no longer 1:1 with stage_02/04.

Topic digests (doctrine source, not raw PDFs):  
`model_training/knowledge/topics/01_market.md` … `09_reversal_trading.md`.

Bridge to instruction/response: `scripts/utils.py` → `create_instruction_response_pair`.

---

## 4. JSONL schemas (one example per data type)

Levels follow distilled TF ownership (`core_skill` + topics):  
**H4/H1/D1** = location map (prior H/L, floor pivots, swing fib).  
**M30/M15/M5/M1** = prior H/L only (path/timing — no invent fib).  
Volume uses **`tick_volume`** (+ ratio vs 20-bar median) — same signal family as live cache.

### 4.1 Market export — tick

```json
{"symbol":"XAUUSDr","time_utc":"2026-08-01T12:00:00Z","time_msc":1754056800123,"bid":2650.12,"ask":2650.28,"last":0.0,"volume":0,"flags":6,"source":"MT5","volume":{"tick_print_volume":0,"spread":0.16,"bid":2650.12,"ask":2650.28},"levels":{},"level_note":"levels_attached_on_candle_jsonl_per_timeframe"}
```

### 4.2 Market export — candle JSONL (H4 example — levels + volume)

```json
{
  "symbol": "XAUUSDr",
  "timeframe": "H4",
  "time_utc": "2026-08-01T12:00:00Z",
  "open": 2653.0, "high": 2656.0, "low": 2646.0, "close": 2651.0,
  "tick_volume": 1100, "spread": 16, "real_volume": 0,
  "source": "derived", "derived_from": "H1", "bar_timezone": "America/New_York",
  "volume": {
    "tick_volume": 1100,
    "real_volume": 0,
    "tick_volume_median_20": 900.0,
    "tick_volume_ratio": 1.2222,
    "spread": 16
  },
  "levels": {
    "H4_PREVIOUS_HIGH": 2662.0,
    "H4_PREVIOUS_LOW": 2651.0,
    "H4_FLOOR_PP": 2655.333333,
    "H4_FLOOR_R1": 2659.666667,
    "H4_FLOOR_S1": 2648.666667,
    "H4_SWING_HIGH": 2662.0,
    "H4_SWING_LOW": 2648.0,
    "H4_FIB_382": 2656.652,
    "H4_FIB_50": 2655.0,
    "H4_FIB_618": 2653.348
  },
  "level_objects": [
    {"level_id": "H4_PREVIOUS_HIGH", "timeframe": "H4", "zone_low": 2662.0, "zone_high": 2662.0, "role": "previous_high", "calculation_method": "latest_completed_candle"}
  ]
}
```

### 4.2b LTF candle JSONL (M15 — prior H/L + volume only)

```json
{
  "symbol": "XAUUSDr", "timeframe": "M15", "time_utc": "2026-08-01T12:00:00Z",
  "open": 2650.0, "high": 2652.0, "low": 2649.0, "close": 2651.0,
  "tick_volume": 400, "spread": 16, "real_volume": 0,
  "volume": {"tick_volume": 400, "real_volume": 0, "tick_volume_median_20": 350.0, "tick_volume_ratio": 1.1429, "spread": 16},
  "levels": {"M15_PREVIOUS_HIGH": 2653.0, "M15_PREVIOUS_LOW": 2648.5},
  "level_objects": []
}
```

### 4.3 Live archive — paper proposal (shape varies; keep fields stable)

```json
{"ts":"2026-08-09T08:00:00Z","symbol":"XAUUSDr","price":2655.2,"action":"skip","skip_reason_code":"news_window","snapshot":{}}
```

### 4.4 Live archive — qwen-io

```json
{"ts":"2026-08-09T08:00:01Z","role":"entry","request":{},"response":{},"model":"qwen"}
```

### 4.5 Curriculum stage_02

```json
{"example_id":"04_40","topic":"04_timeframe_relations","title":"H4 FIB 618 buy","setup":"LEVELS: H4_FIB_618=... | AUCTION=rejection | ...","decision":"Long scalp","invalidation":"...","why":"...","evidence":"strong","bucket":"A"}
```

### 4.6 Curriculum stage_04 (entry)

```json
{"example_id":"04_40","role":"entry","action":"open","direction":"buy","confidence":80,"auction_state":"rejection","skip_reason_code":null,"target_mode":"scalp","key_levels":"H4_FIB_618=2655.2,H4_PREVIOUS_LOW=2646.0,H1_RESISTANCE=2676.0","entry_price":2656.0,"sl_price":2646.0,"tp_price":2676.0,"sl_usd":10.0,"tp_usd":20.0,"trade_decision":"Long scalp","trade_reason":"Concept: H4/H1 locate the auction; M15 times the response. Reason: buy because auction reads rejection at H4_FIB_618.","confirmation_reason":"Confirmation: closed M5 bullish response at H4_FIB_618; forming candles are not proof.","conviction_score":0.8,"evidence_label":"strong","missing_fact":null}
```

`sl_usd` / `tp_usd` = gold price distance from entry. `trade_reason` + `confirmation_reason` are required for Sample Prepared / LoRA.

### 4.7 Curriculum stage_04 (management)

```json
{"example_id":"10_01","role":"management","management_action":"hold","direction":"buy","thesis_state":"valid","confirmation_type":"continuation_acceptance_confirmed","decision_level_ref":"M5_FLIP_2656","next_target_ref":"H1_RESISTANCE_2662","close_confirmed":false,"auction_state":"acceptance","action":"open","confidence":80}
```

---

## 5. From evidence → curriculum (do not skip)

```text
Live day → tick_data/YYYY-MM-DD/*.jsonl
    → human review (use daily_trade_review.py in utilities if helpful)
    → promote into store/core_skill.md or store/sop.md (lean)
    → optional curated rows into stage_02/04 (same schema)
    → never auto-dump unreviewed qwen-io into SFT
```

No separate review markdown templates. Checklist = this section.

---

## 6. Train (Colab Qwen2.5-14B QLoRA)

1. Build zip (local):  
   `python model_training/python_utilities_for_models/create_training_zip.py`  
   → `QuantLLMBot_training.zip` at repo root
2. Colab **A100**: upload zip, open `scripts/Train_Qwen14B_Colab.ipynb`
3. Cells: checklist → `01_preprocess.py` (expect **379** pairs) → `02_finetune.py` → `03_evaluate.py` → GGUF export
4. Deploy GGUF to Ollama; live app still loads `store/*` + code gates

Hyperparameters: repo `scripts/config.py` (5 epochs, warmup 5, QLoRA r=16).

---

## 7. Pack history (utilities only)

| Pack | Script (under `python_utilities_for_models/`) | Focus |
|------|--------|--------|
| v5 | `append_discipline_pack_v5.py` | Poison rewrite, holdout, action/direction |
| v6 | `append_sop_mgmt_m1_v6.py` | Skip codes, management, M1 double-test |
| v7 | `append_fib_ema_v7.py` | H4 fib consume + M1 EMA 3/14/31 |
| v004 geom | `repair_zone_sl_tp_v004.py` | Zone-based gold SL/TP mins (M15≥5/5, H1≥7/10, H4≥10/20) |
| v004 reasons | `enrich_trade_reasons_v004.py` | trade_reason + confirmation_reason from distilled topics |
| v004 sideways | `append_sideways_regime_v004.py` | Sideways regime + hold-through-giveback management vs trend/reversal contrast |
| v004 live SW | `append_sideways_live_20260812.py` | Live 2026-08-12 after 17:20 UTC box ~4397–4413; large-SL vs SL↔TP flip path |

Bump a row here when a pack lands. Do not create a second history doc.

---

## 8. Explicit non-goals

- Training the model to detect news from candle size (code cool-down).
- All-timeframe EMA relationship dumps / EMA9.
- SMC package (OB/FVG/BOS) as a peer doctrine.
- Auto-generating new markdown “guides” per chat.
- Fresh MT5 bulk export every weekend train (v4+).

---

## 9. What to read (nothing else for process)

| Path | Role |
|------|------|
| **This file** | Curriculum + data prep + train process |
| `store/core_skill.md` / `store/sop.md` | Live LLM doctrine |
| `SYSTEM_THREE_PARTS.md` / `AGENTS.md` | Architecture / agent pointers |
| `model_training/python_utilities_for_models/` | Model-job Python |
| `scripts/` | Colab train/eval (system pipeline) |
| `apps/.../tick_data_archive.py` | Live JSONL dual-write (system) |
