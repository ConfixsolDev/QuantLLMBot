# v002 recovery drop zone

Place recovered v002 training artifacts here. This folder is gitignored except
this README — large files stay local.

## Expected files

| File / folder | Purpose |
|---------------|---------|
| `train_lora.ipynb` or `.py` | Original Colab training notebook |
| `training_log.txt` | Loss, epochs, hyperparameters |
| `v002_sft.jsonl` | Instruction dataset used for v002 |
| `loss_curve.png` | Optional screenshot |

LoRA adapter weights go in `model_training/adapters/` (also gitignored).

After dropping files, update `sources/methodology/v002_training_record.md`.
