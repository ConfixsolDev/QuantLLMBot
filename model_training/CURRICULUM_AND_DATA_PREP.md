# QuantLLMBot — Curriculum, Data Prep & Training

**THE ONLY process document** for curriculum, data preparation, tick→train loop, and Colab training.

Last updated: 2026-08-09

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
| **Every trading day** | Live app archives ticks → `tick_data/YYYY-MM-DD/`. Human/agent review → promote lessons into lean `store/` + curated stage_02/04 rows. Distilled topics stay the doctrine source. |
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

**Current size (v7):** ~389 aligned examples (379 train / 10 holdout at end).  
**Config:** `scripts/config.py` → `training_lines_end=379`, `test_lines_end=389`.

Append packs (idempotent scripts, same holdout IDs):  
`model_training/python_utilities_for_models/append_*.py` — extend existing or add one new pack script **in that folder only**.

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
{"example_id":"04_40","role":"entry","action":"open","direction":"buy","confidence":80,"auction_state":"rejection","skip_reason_code":null,"target_mode":"scalp","key_levels":"H4_FIB_618=2655.2,...","entry_price":2656.0,"sl_price":2653.0,"tp_price":2660.0,"sl_usd":3.0,"tp_usd":4.0,"trade_decision":"Long scalp","conviction_score":0.8,"evidence_label":"strong","missing_fact":null}
```

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
