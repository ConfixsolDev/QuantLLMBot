# Training datasets (local, gitignored)

Generated or recovered SFT files live here. Nothing in this folder is committed.

## Layout

| Subfolder | Contents |
|-----------|----------|
| `doctrine_sft/` | Instruction pairs from store + TRADING_KNOWLEDGE_BASE |
| `tick_derived_sft/` | Human-curated examples from tick archive (optional) |
| `raw/` | **MT5 historical export** (ticks + candles) |

## MT5 raw export (`raw/`)

Built by `scripts/export_mt5_market_data.py`:

```text
raw/
├── manifest.json
├── export_log.jsonl
├── ticks/XAUUSDr/
│   └── YYYY-MM-DD_ticks.csv
└── candles/XAUUSDr/
    ├── M1/YYYY-MM_M1.csv          ← direct from MT5 (max history)
    ├── M5/YYYY-MM_M5.csv          ← derived from M1 (UTC)
    ├── M15/YYYY-MM_M15.csv        ← derived from M1 (UTC)
    ├── M30/YYYY-MM_M30.csv        ← derived from M1 (UTC)
    ├── H1/YYYY-MM_H1.csv          ← direct from MT5
    └── H4/YYYY-MM_H4_NY.csv       ← derived from H1 (4h NY buckets)
```

**H4 rule:** 4-hour candles use `America/New_York` boundaries (00, 04, 08, 12, 16, 20 NY) built from H1 bars.

**Requires:** MetaTrader 5 terminal running and logged in (same as live app).

```powershell
cd E:\QuantLLMBot\model_training
C:\ProgramData\Miniconda3\python.exe scripts\export_mt5_market_data.py --symbol XAUUSDr
```

Options: `--from-date`, `--to-date`, `--force`, `--skip-ticks`, `--skip-derived`.

## Build doctrine SFT

```powershell
cd E:\QuantLLMBot\model_training
python scripts/build_doctrine_sft.py --out datasets/doctrine_sft/v003_doctrine.jsonl
```

Review the JSONL before any Colab training run.
