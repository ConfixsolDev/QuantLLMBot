"""research_lab — fair comparisons on top of Module 1 (structure_engine).

Stage 0  dataset.py   decision points, structure features, outcome labels
Stage 1  forecast.py  Kronos (or the bootstrap yardstick) at every decision
Stage 2  compare.py   base rate vs forecasters vs XGBoost on structure,
                      with and without forecast features, walk-forward

Unlike structure_engine this package may use numpy/pandas/torch/xgboost.
It never feeds the live system; it produces evidence for decisions.
Full design: XAUUSD_SYSTEM_ARCHITECTURE_V3.md, Part B5.
"""
