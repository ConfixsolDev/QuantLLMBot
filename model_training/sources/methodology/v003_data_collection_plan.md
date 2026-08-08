# v003 data collection plan

**Updated priority (2026-08-07):** Collect and distill **candle-moment + session
handoff knowledge** first. MT5 bulk export and curriculum scripts come **after**
the minimum knowledge pack in `knowledge/CANDLE_MOMENT_AND_SESSION_DISTILLATION.md`.

See also: `knowledge/CANDLE_MOMENT_AND_SESSION_DISTILLATION.md`

---

## Goal

Produce:

```text
model_training/datasets/complete_market_structure_v003/
├── manifest.json
├── train.jsonl          ← ordered curriculum (like v001)
├── eval.jsonl           ← held-out days (optional but recommended)
└── raw/
    ├── candles/         ← normalized MT5 export (source of truth)
    └── export_log.jsonl ← what was fetched, when, gaps
```

Train with existing `qwen7b_complete_market_structure_v001/train_qwen7b_qlora_colab.py`
(hyperparameters already documented in `TRAINING_INVENTORY.md`).

---

## What v001 actually used (target format)

| Stage | Count (v001) | Input source | Output |
|-------|--------------|--------------|--------|
| `01_principle_foundation` | 10 | Hand-authored from `store/core_skill.md` | Compact principle JSON pairs |
| `02_multi_h4_sequence` | 40 | Closed candles, multi-H4 windows | H4 sequence + level double-check |
| `03_internal_h4_flow_level_volume` | 80 | One completed H4 + M1/M5/M15/M30/H1 inside it | Internal flow + volume effort |
| `04_decision_contract_examples` | 120 | Full market snapshots + decision JSON | Entry contract (open/wait/skip) |

**Important:** v001 stages 02–03 used **closed OHLC candles + tick_volume**, not
raw tick prints. MT5 `copy_rates_range` is the right fetch API.

Stage 04 in v001 was harvested from jul13 replay runs and was mostly
`decision_quality_label: unreviewed`. For v003 we should **review** stage 04
before training.

---

## Three-layer pipeline

```text
Layer 0 — MT5 export (months of candles)
    ↓
Layer 1 — Normalized candle store (CSV or SQLite)
    ↓
Layer 2 — Curriculum builder → train.jsonl (4 stages)
    ↓
Layer 3 — Human review gate (especially stage 04)
    ↓
Layer 4 — QLoRA train fresh from base → export v003 Ollama
```

---

## Layer 0 — MT5 historical export

### What to fetch

| Timeframe | Role in curriculum | Suggested lookback per snapshot |
|-----------|-------------------|--------------------------------|
| M1 | Stage 03 minute trace, stage 04 timing | 1–2 hours inside H4 |
| M5 | Local map, session breaks | 1–2 days |
| M15, M30 | Level checks, path | 3–7 days |
| H1, H4 | Sequence stages 02–03 | 10–20 H4 bars |
| D1 | Pivot / daily structure (stage 04) | 30–60 days |

**Symbol:** `XAUUSDr` (same as live app).

**Date range (proposed default):** pick **3 calendar months** first, e.g.
`2026-05-01 → 2026-07-31` (matches v001 window). Expand to 6–12 months after
the pipeline is validated.

### Export rules (no lookahead)

1. Only candles with `time + timeframe_duration <= snapshot_time`.
2. Store `is_complete=true` for training rows; never use forming candles in labels.
3. Log gaps (MT5 missing bars, connection errors) in `export_log.jsonl`.
4. Export in **monthly chunks** (MT5 range limits + easier resume).

### Proposed storage (Layer 1)

**Option A — CSV per month (matches old RandDData style)**

```text
model_training/datasets/raw/candles/XAUUSDr/
├── 2026-05_M1.csv
├── 2026-05_M5.csv
...
```

Columns (normalized, same spirit as `market_context_cache._normalize_rate`):

`symbol, timeframe, time_utc, open, high, low, close, tick_volume, spread, real_volume, source`

**Option B — SQLite single DB** (reuse patterns from `market_context_cache.py`)

Recommended if we also want to reuse level/projection logic later.

**Decision:** start with **CSV monthly files** (simple, diffable, matches v001
manifest reference) unless export volume makes SQLite clearly better.

### New script (to build)

`model_training/scripts/export_mt5_candles.py`

- Connect MT5 (same as `review_shared.connect_mt5()`).
- Args: `--symbol`, `--from-date`, `--to-date`, `--timeframes M1,M5,...`, `--out-dir`.
- Monthly chunk loop with progress log.
- Idempotent: skip month file if already complete unless `--force`.

---

## Layer 2 — Curriculum builder

The v001 builder script was **not kept in the repo**. We rebuild it as:

`model_training/scripts/build_market_structure_curriculum.py`

### Stage 01 — Principles (static)

- Source: current `store/core_skill.md` + `LESSON_LEDGER` approved lessons.
- ~10–15 examples (reuse v001 IDs where still valid; add new for v3 store changes).
- `decision_quality_label: approved_principle` only.

### Stage 02 — Multi-H4 sequence

- Walk export: every **4th completed H4** (or session-stratified sample) across the date range.
- For each anchor time, build user JSON keys matching v001:
  `sequence`, `current_h4_level_checks`, `current_h4_minute_trace`, `task`, ...
- Assistant: `carry_forward_effect`, `level_double_check`, `sequence_read`.
- Target: **~1 example per 2 trading days** → ~30–40 examples per 3 months.

### Stage 03 — Internal H4 flow

- One example per **completed H4** (sampled: max 1 per session block to avoid redundancy).
- User JSON keys: `completed_h4`, `minute_trace`, `level_behavior_checks`, `phase_reads`, ...
- Assistant: `auction_state`, `h4_flow_summary`, `phase_lessons`, `volume_rule`.
- Target: **~2–3× stage 02 count** → ~80–120 examples per 3 months.

### Stage 04 — Decision contract

Two sub-sources (combine):

| Sub-source | Pros | Cons |
|------------|------|------|
| **A. Replay builder** — run snapshot builder at historical times, label with rules + human review | Scales to thousands | Needs rebuilt replay harness |
| **B. Paper tick archive** — `tick_data/qwen-io.jsonl` after human review | High quality, real Qwen context | Slow; limited count initially |

**v003 rule:** stage 04 rows must have `decision_quality_label` in
`approved_decision | approved_skip | approved_wait` — **no unreviewed** (fix v001 weakness).

Target for first v003 train: **120–300** stage-04 examples.

### Output manifest

Same fields as v001 `manifest.json`:

```json
{
  "dataset_type": "complete_sequential_market_structure_curriculum",
  "version": "complete_market_structure_v003",
  "example_count": 0,
  "from_date": "YYYY-MM-DD",
  "to_date": "YYYY-MM-DD",
  "source_export": "model_training/datasets/raw/candles/XAUUSDr/",
  "stages": { "01_...": 0, "02_...": 0, "03_...": 0, "04_...": 0 },
  "no_lookahead_policy": "All examples use closed candles only at snapshot_time_utc.",
  "training_order": "Ordered principles → H4 sequence → internal H4 → decisions."
}
```

---

## Layer 3 — Review & split

1. **Chronological split** — e.g. last 2 weeks of range → `eval.jsonl`; rest → `train.jsonl`.
2. **Human spot-check** — 10 examples per stage before train.
3. **Stage 04** — reviewer marks each row approved/rejected in a sidecar CSV or
   `review_labels.jsonl` keyed by `example_id`.

---

## Layer 4 — Train v003 (unchanged recipe)

Reuse v001 script defaults unless eval loss says otherwise:

| Param | Value |
|-------|-------|
| Base | `Qwen/Qwen2.5-7B-Instruct` |
| Method | QLoRA 4-bit |
| LoRA r / alpha | 16 / 32 |
| LR | 2e-4 |
| Epochs | 1 (increase to 2 only if eval supports it) |
| Max seq | 4096 |

Export: `export_lora_to_ollama_colab.py --outfile-prefix qwen-trading-v003`

---

## Phased rollout (recommended)

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| **P0** | 2 weeks MT5 export | `raw/candles/` + export log |
| **P1** | Builder stages 01–03 only | `train.jsonl` ~100 rows, validate against v001 schema |
| **P2** | 3 months export | Full stages 02–03 |
| **P3** | Stage 04 from paper ticks + small replay | Reviewed decision examples |
| **P4** | Train v003 on Colab | Adapter + Ollama package |

Do **not** train until P1 schema validates against v001 examples.

---

## Decisions needed from you

1. **Date range:** 3 months (default) or 6 / 12?
2. **Stage 04 priority:** paper-reviewed ticks first, or bulk replay first?
3. **Export location:** `E:\QuantLLMBot\model_training\datasets\raw\` OK?
4. **Old CSV:** if `D:\QuantLLMBot\RandDData\` exists on another machine, copy it
   to `raw/candles/` to avoid re-fetching May–Jul 2026.

---

## What you provide next

```text
Preferred date range: YYYY-MM-DD to YYYY-MM-DD
Months to fetch from MT5: [3 / 6 / 12]
Stage 04 approach: [paper-reviewed / replay / both]
RandD CSV available elsewhere: [yes path / no — fetch all from MT5]
MT5 symbol confirmed: XAUUSDr
```

After you confirm, next code step is **`export_mt5_candles.py`** (Layer 0).
